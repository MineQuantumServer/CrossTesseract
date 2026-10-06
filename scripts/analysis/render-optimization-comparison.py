#!/usr/bin/env python3
"""Render a completed offline_optimization_comparison JSON as Markdown.

Reads only the explicit aggregate input; does not follow raw/sequence references,
query backends, inspect processes, invoke tests, or infer frozen goal outcomes.
Relative paths are resolved against the portable repository root.
"""
import argparse
from copy import deepcopy
import hashlib
import html
import json
import math
from pathlib import Path
import re
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 64 * 1024 * 1024
QUANTILES = ("p50", "p95", "p99")
COSTS = (
    ("db_transactions", "SQL transactions"),
    ("transactions", "Completed worker tasks"),
    ("db_statements", "Sql-helper statement attempts"),
    ("wal_writes", "WAL writes"), ("wal_bytes", "WAL bytes"),
    ("wal_identical_skipped", "Identical WAL skips"),
    ("batch_devices", "Batch device appearances"),
    ("batch_records", "Batch record appearances"),
    ("batch_payload_bytes", "Batch payload bytes"),
    ("empty_batches", "Empty batches"),
    ("batch_calls", "Total batch calls (only if explicitly measured)"))


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def number(value):
    if not finite(value):
        return "UNMEASURED"
    if isinstance(value, int):
        return str(value)
    return format(value, ".12g")


def outcome(value):
    return "MET" if value is True else "NOT MET" if value is False else "UNMEASURED / NOT ASSESSED"


def check(value):
    return "TRUE" if value is True else "FALSE" if value is False else "UNMEASURED"


def text(value):
    if value is None:
        return "UNMEASURED"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return html.escape(str(value), quote=False).replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`").replace("\n", "<br>")


def table(headers, rows):
    lines = ["| " + " | ".join(text(item) for item in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(text(item) for item in row) + " |" for row in rows)
    return "\n".join(lines)


def json_block(value):
    body = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    fence = "`" * max(3, 1 + max((len(m.group()) for m in re.finditer(r"`+", body)), default=0))
    return fence + "json\n" + body + "\n" + fence


def percentile_triplet(container):
    return " / ".join(number(container.get(key)) for key in QUANTILES)


def median_value(case, key):
    return number(case.get("steady", {}).get(key, {}).get("median"))


def validate_aggregate(body):
    if not isinstance(body, dict) or body.get("schema_version") != 1 or body.get("report_kind") != "offline_optimization_comparison":
        raise ValueError("Expected a complete offline_optimization_comparison schema 1 object")
    if not isinstance(body.get("utc"), str) or not isinstance(body.get("scope"), dict):
        raise ValueError("Aggregate must include its recorded UTC and scope")
    profiles = body.get("profiles")
    if not isinstance(profiles, dict) or not 3 <= len(profiles) <= 32 or not all(key in profiles for key in ("baseline", "batch", "fast")):
        raise ValueError("Aggregate must retain baseline, batch and fast profiles, including NOT RUN entries")
    for profile in profiles.values():
        if not isinstance(profile, dict) or not isinstance(profile.get("status"), str) or not isinstance(profile.get("cases"), dict):
            raise ValueError("Every profile needs its recorded status and cases")
        if len(profile["cases"]) > 128:
            raise ValueError("Too many cases")
        for case in profile["cases"].values():
            if not isinstance(case, dict) or not isinstance(case.get("status"), str):
                raise ValueError("Every case needs its recorded status")
            for key in ("steady", "low_flow", "conservation", "error_totals"):
                if not isinstance(case.get(key), dict):
                    raise ValueError("Case is missing a completed aggregate field: " + key)
            repeats = case.get("repeats")
            if not isinstance(repeats, list) or len(repeats) > 1024 or any(not isinstance(sample, dict) for sample in repeats):
                raise ValueError("Case repeats must be a bounded list of recorded samples")
    for key in ("comparisons", "frozen_target_assessments"):
        value = body.get(key, [] if key == "frozen_target_assessments" else None)
        if not isinstance(value, list) or any(not isinstance(entry, dict) for entry in value):
            raise ValueError("Aggregate field must be a list of objects: " + key)
    return body


def read_aggregate(path):
    attributes = path.stat()
    if not stat.S_ISREG(attributes.st_mode) or attributes.st_size > MAX_BYTES:
        raise ValueError("Input must be a regular JSON file no larger than 64 MiB")
    with path.open("rb") as file:
        raw = file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Input grew beyond 64 MiB")

    def invalid_constant(value):
        raise ValueError("Non-JSON numeric constant: " + value)

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result

    body = json.loads(raw, parse_constant=invalid_constant, object_pairs_hook=unique_object)
    return validate_aggregate(body), hashlib.sha256(raw).hexdigest(), len(raw)


def render_targets(assessments):
    sections = ["## Frozen performance goals",
        "Goal outcomes below are copied exclusively from frozen_target_assessments. Functional passed status does not establish a performance goal. No goal is inferred when the assessment is absent or unmatched."]
    if not assessments:
        sections.append("NOT ASSESSED: frozen_target_assessments is absent or empty.")
    for assessment in assessments:
        sections.extend(["### " + text(assessment.get("baseline")) + " → " + text(assessment.get("profile")),
            "Recorded assessment status: " + text(assessment.get("status")),
            "Declared goals:", json_block(assessment.get("declared", {}))])
        if assessment.get("status") != "MATCHED_DESCRIPTIVE_EVALUATION":
            sections.append("NOT ASSESSED: " + text(assessment.get("reason", "No matched frozen-baseline evidence")))
        else:
            rows = []
            for path in assessment.get("database_transactions_by_path", []):
                rows.append([path.get("scenario"), number(path.get("target_reduction_percent")),
                    number(path.get("baseline_repeat_median")), number(path.get("current_repeat_median")),
                    number(path.get("reduction_percent")), outcome(path.get("repeat_median_goal_met")),
                    path.get("paired_repeat_reduction_percents", {}), outcome(path.get("all_paired_repeats_meet_goal"))])
            sections.append(table(["Path", "DB reduction goal %", "Baseline median", "Current median",
                "Observed reduction %", "Median goal", "All paired repeat reductions %", "All repeat goal"], rows))
            sections.append("All three path medians meet DB goal: " + outcome(assessment.get("all_three_path_repeat_medians_meet_DB_goal")))
            rows = []
            for key in ("same_server_low_flow_p95_reduction_percent", "cross_server_p95_max_regression_percent"):
                item = assessment.get(key, {})
                rows.append([key, number(item.get("declared_target_percent")),
                    number(item.get("observed_change_percent")), outcome(item.get("goal_met"))])
            sections.append(table(["Frozen latency goal", "Declared %", "Observed change %", "Recorded goal outcome"], rows))
        sections.extend(["Idle: " + text(assessment.get("idle_transactions")),
            "Integrity scope: " + text(assessment.get("integrity")),
            "Assessment scope: " + text(assessment.get("scope"))])
    return sections


def render_case(name, scenario, case):
    sections = ["### " + text(name) + " / " + text(scenario),
        "Case status: " + text(case["status"]) + "; missing/incomplete repeats: " + text(case.get("missing_or_incomplete_repeats", [])) +
        "; duplicate repeat IDs: " + check(case.get("duplicate_repeat_ids")),
        "Recorded topology:", json_block(case.get("topology", {}))]
    samples = case["repeats"]
    if not samples:
        sections.append("NOT RUN: no recorded repeat samples.")
    rows = []
    for sample in samples:
        business, cost = sample.get("business", {}), sample.get("cost_counters", {})
        rows.append([sample.get("repeat"), check(sample.get("reported_passed")), check(sample.get("complete")),
            number(sample.get("cost", {}).get("planned_input_attempts")), number(business.get("input_attempts")),
            number(business.get("accepted_FE")), number(sample.get("steady_actual_output_FE")),
            number(business.get("actual_extracted_FE_per_second")), number(sample.get("steady_tail_to_drain_FE")),
            number(cost.get("db_transactions")), number((sample.get("counter_delta", {}).get("statements") or {}).get("events"))])
    sections.append(table(["Repeat", "Reported pass", "Recorded complete", "Planned attempts", "Actual attempts",
        "Steady accepted FE", "Steady extracted FE", "Steady extracted FE/s", "Steady tail to drain FE",
        "SQL tx before final drain", "Account statements before final drain"], rows))
    rows = [[sample.get("repeat"), number(sample.get("low_probe_count")),
        percentile_triplet(sample.get("low_flow", {}).get("full_output_lower_ms", {})),
        percentile_triplet(sample.get("low_flow", {}).get("full_output_upper_ms", {}))] for sample in samples]
    sections.append(table(["Repeat", "Probes", "Full-output lower p50 / p95 / p99 ms", "Full-output upper p50 / p95 / p99 ms"], rows))
    rows = [[sample.get("repeat"), *[number(sample.get("cost_counters", {}).get(key)) for key, _ in COSTS]] for sample in samples]
    sections.append(table(["Repeat", *[label for _, label in COSTS]], rows))
    rows = []
    for sample in samples:
        delta = sample.get("counter_delta", {})
        checks = sample.get("checks", {})
        rows.append([sample.get("repeat"), number(delta.get("errors")), number(delta.get("queue_rejected")),
            number(delta.get("quarantined")), number(delta.get("db_deadlock_retries")),
            number(sample.get("SQL_statement_errors")), check(checks.get("all_steady_sinks_served")),
            number(sample.get("sink_Jain_index")), number(sample.get("max_sink_unserved_seconds")),
            sample.get("failure") if sample.get("failure") is not None else "No recorded failure"])
    sections.append(table(["Repeat", "Worker errors", "Queue rejected", "Quarantined", "Deadlock retries",
        "Account statement errors", "All steady recipients served", "Sink Jain index", "Max sink pull gap s", "Failure"], rows))
    for sample in samples:
        sections.append("#### Recorded repeat " + text(sample.get("repeat")))
        rows = []
        for endpoint, sink in sample.get("sinks", {}).items():
            rows.append([endpoint, sink.get("server"), number(sink.get("actual_extracted_FE")),
                number(sample.get("sink_output_shares", {}).get(endpoint)), number(sink.get("successful_pull_events")),
                number(sink.get("first_output_seconds")), number(sink.get("last_output_seconds")), number(sink.get("max_unserved_seconds"))])
        sections.append(table(["Recipient", "Server", "Steady extracted FE", "Output share", "Successful pulls",
            "First output s", "Last output s", "Max pull gap s"], rows))
        sections.extend(["All recorded checks:", json_block(sample.get("checks", {})),
            "Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):",
            json_block(sample.get("cumulative_conservation", {})),
            "This repeat's all-phase event ledger (warmup, steady, low-flow, drain):",
            json_block(sample.get("all_phase_event_ledger", {}))])
        windows = sample.get("captured_counter_window", {})
        rows = [[server, point.get("first_status_run_relative_interval"), point.get("last_status_run_relative_interval")]
            for server, point in windows.get("per_server", {}).items()]
        sections.append(table(["Server", "First status run-relative interval s", "Final status run-relative interval s"], rows))
        sections.extend(["WAL ring snapshots (diagnostic only):", json_block(sample.get("WAL_barrier_snapshots", {}))])
    sections.extend(["Recorded per-case error totals (missing measurements remain missing):", json_block(case.get("error_totals", {})),
        "Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):", json_block(case.get("conservation", {}))])
    return sections


def render(body, input_path, input_sha, input_bytes, renderer_sha):
    validate_aggregate(body)
    sections = ["# Offline optimization comparison",
        table(["Evidence", "Value"], [["Aggregate input", str(input_path)], ["Aggregate SHA-256", input_sha],
            ["Aggregate bytes", input_bytes], ["Aggregate recorded UTC", body["utc"]], ["Renderer SHA-256", renderer_sha]]),
        "This renderer ran no Minecraft, backend, fault, native, performance or profiling tests: NOT RUN by this tool. Driver statuses are supplied evidence; functional passed does not mean frozen performance goals were met.",
        "## Measurement boundaries",
        "Latency numbers are medians of per-repeat full_output p50/p95/p99, with separate RCON lower/upper bounds; they are not pooled percentiles. full_output ends when the probe's accepted asset has been fully pulled, using its last successful pull. It does not establish service to every configured recipient on every probe.",
        "Main-path SQL/WAL/worker counters end before the final conservation drain. Steady extraction can lag accepted input; tail work is not added to the fixed input window. Final conservation is reported separately and cumulatively for reused channels. Backpressure recovery, if present, follows its recorded counter scope.",
        "Account statement events differ from Sql-helper attempts; completed worker tasks differ from SQL commits. Batch devices/records are appearances, not distinct devices or batch calls. Total batch calls remain UNMEASURED unless explicitly captured. Missing original WAL counters are UNMEASURED, not zero.",
        "Recipient max pull gaps are gaps between successful pulls and phase boundaries, not measured demand-pending waits or a latency bound. Jain indices describe observed outputs and do not establish a fairness guarantee. WAL ring percentiles are per-JVM diagnostic snapshots with unknown window age; do not subtract, pool or call them phase-wide timings.",
        "Raw git_head is preserved as reported workspace metadata. Explicit sequence evidence can provide an operator-declared runtime revision bound by exact child SHA; it is not classloader attestation. Without that evidence no runtime revision is inferred from a label.",
        "No actual TPS or complete wall-clock MSPT is inferred. Comparison regression flags are descriptive hints, not additional frozen acceptance goals.",
        "## Profile identity and recorded status"]
    rows = []
    for name, profile in body["profiles"].items():
        rows.append([name, "NOT RUN" if profile["status"] == "not_run" else profile["status"], profile.get("source"),
            profile.get("source_sha256"), profile.get("git_head"), profile.get("declared_runtime_revision"),
            profile.get("runtime_revision_evidence", {}).get("status", "No explicit sequence evidence")])
    sections.append(table(["Profile", "Recorded state", "Driver source", "Driver SHA-256", "Raw workspace HEAD",
        "Declared runtime revision", "Identity evidence"], rows))
    for name, profile in body["profiles"].items():
        sections.extend(["### Conditions / " + text(name), json_block(profile.get("conditions", {}))])
        conditions = profile.get("conditions", {})
        seconds, period = conditions.get("steady_seconds"), conditions.get("feed_period_seconds")
        if finite(seconds) and seconds > 0 and finite(period) and period > 0:
            sections.append("Configured feed rounds per source per steady window: " + number(math.ceil(seconds / period)) +
                ". A 120 s / 0.5 s window has 240 rounds per source; total attempts depend on the actual fixture source count. Every repeat's planned and actual totals are retained below.")
        if profile.get("runtime_revision_evidence"):
            sections.extend(["Explicit identity source evidence:", json_block(profile["runtime_revision_evidence"])])
    sections.append("## Repeat-median main results")
    rows = []
    for name, profile in body["profiles"].items():
        for scenario, case in profile["cases"].items():
            low = case["low_flow"]
            rows.append([name, scenario, case["status"], str(case.get("complete_repeats")) + "/" + str(case.get("expected_repeats")),
                percentile_triplet(low.get("full_output_lower_ms", {}).get("repeat_percentile_medians", {})),
                percentile_triplet(low.get("full_output_upper_ms", {}).get("repeat_percentile_medians", {})),
                median_value(case, "input_attempts"), median_value(case, "db_transactions"), median_value(case, "SQL_statement_events"),
                median_value(case, "accepted_FE"), median_value(case, "actual_extracted_FE"), median_value(case, "actual_extracted_FE_per_second")])
    sections.append(table(["Profile", "Path", "Case state", "Complete/expected repeats", "Full lower p50 / p95 / p99 ms",
        "Full upper p50 / p95 / p99 ms", "Actual attempts/window", "SQL tx/window", "Account statements/window",
        "Steady accepted FE", "Steady extracted FE", "Steady extracted FE/s"], rows))
    rows = [[name, scenario, *[median_value(case, key) for key, _ in COSTS[1:]]]
        for name, profile in body["profiles"].items() for scenario, case in profile["cases"].items()]
    sections.append(table(["Profile", "Path", *[label + " / repeat median" for _, label in COSTS[1:]]], rows))
    rows = []
    for name, profile in body["profiles"].items():
        for scenario, case in profile["cases"].items():
            conservation = case["conservation"]
            ledger = conservation.get("all_phase_event_ledger", {})
            rows.append([name, scenario, number(ledger.get("accepted_FE")), number(ledger.get("extracted_FE")),
                number(conservation.get("latest_cumulative_accepted_FE")), number(conservation.get("latest_cumulative_extracted_FE")),
                check(conservation.get("latest_cumulative_matches_event_ledger"))])
    sections.append(table(["Profile", "Path", "All-phase input event ledger FE", "All-phase output event ledger FE",
        "Latest cumulative accepted FE after drain", "Latest cumulative extracted FE after drain", "Latest checkpoint matches ledger"], rows))
    if body.get("frozen_target_context"):
        sections.extend(["Frozen goal context source (as supplied by aggregator):", json_block(body["frozen_target_context"])])
    sections.extend(render_targets(body.get("frozen_target_assessments", [])))
    sections.append("## All recorded repeats, costs, recipient service and drain")
    for name, profile in body["profiles"].items():
        if not profile["cases"]:
            sections.append("### " + text(name) + ": " + ("NOT RUN" if profile["status"] == "not_run" else text(profile["status"])) + "; no recorded cases.")
        for scenario, case in profile["cases"].items():
            sections.extend(render_case(name, scenario, case))
    sections.append("## Recorded failures, warnings and regression evidence")
    for name, profile in body["profiles"].items():
        sections.extend(["### " + text(name), json_block({key: profile.get(key) for key in
            ("status", "report_passed", "failures", "regressions", "warnings", "other_live_backend_sessions")})])
    sections.extend(["## All pairwise comparison metrics and regression flags", json_block(body["comparisons"]),
        "## Supplied aggregate scope", json_block(body["scope"])])
    result = "\n\n".join(sections) + "\n"
    if len(result.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Rendered Markdown exceeds 64 MiB")
    return result


def resolve_argument(value):
    return (value if value.is_absolute() else ROOT / value).resolve()


def write_report(input_path, output_path):
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Markdown output cannot overwrite its aggregate input")
    body, digest, size = read_aggregate(input_path)
    rendered = render(body, input_path, digest, size, hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Existing reports are preserved; choose a new explicit path for regeneration.
    with output_path.open("x", encoding="utf-8", newline="\n") as file:
        file.write(rendered)


def self_test():
    low = {key: {"repeat_percentile_medians": {"p50": 1, "p95": 2, "p99": 3}}
        for key in ("full_output_lower_ms", "full_output_upper_ms")}
    sample = {"repeat": 1, "reported_passed": True, "complete": True, "low_probe_count": 40,
        "business": {"input_attempts": 240, "accepted_FE": 100, "actual_extracted_FE_per_second": 1},
        "cost": {"planned_input_attempts": 240}, "cost_counters": {"db_transactions": 3, "transactions": 5},
        "steady_actual_output_FE": 90, "steady_tail_to_drain_FE": 10,
        "counter_delta": {"db_transactions": 3, "errors": 0, "statements": {"events": 12}},
        "low_flow": {key: {"p50": 1, "p95": 2, "p99": 3} for key in low},
        "checks": {"all_steady_sinks_served": True}, "sink_Jain_index": 0.8, "max_sink_unserved_seconds": 2,
        "sinks": {"sink|A": {"server": "A", "actual_extracted_FE": 90, "max_unserved_seconds": 2}},
        "sink_output_shares": {"sink|A": 1}, "all_phase_event_ledger": {"accepted_FE": 110, "extracted_FE": 110},
        "cumulative_conservation": {"accepted_FE": 110, "extracted_FE": 110, "seconds": 1}}
    case = {"status": "complete", "expected_repeats": 3, "complete_repeats": 3, "repeats": [],
        "low_flow": low, "steady": {"input_attempts": {"median": 240}, "db_transactions": {"median": 3},
            "SQL_statement_events": {"median": 12}}, "conservation": {}, "error_totals": {}}
    for repeat in (1, 2, 3):
        entry = deepcopy(sample)
        entry["repeat"] = repeat
        case["repeats"].append(entry)
    profile = {"status": "passed", "git_head": "b" * 40, "declared_runtime_revision": "a" * 40,
        "conditions": {"steady_seconds": 120, "feed_period_seconds": .5}, "cases": {"same": case},
        "regressions": [{"message": "descriptive warning"}], "failures": []}
    body = {"schema_version": 1, "report_kind": "offline_optimization_comparison", "utc": "2026-10-06T00:00:00Z",
        "scope": {}, "profiles": {"baseline": profile, "batch": deepcopy(profile),
            "fast": {"status": "not_run", "cases": {}}}, "comparisons": [],
        "frozen_target_assessments": [{"baseline": "baseline", "profile": "batch", "status": "MATCHED_DESCRIPTIVE_EVALUATION",
            "database_transactions_by_path": [{"scenario": "same", "target_reduction_percent": 30,
                "repeat_median_goal_met": False, "all_paired_repeats_meet_goal": False}],
            "all_three_path_repeat_medians_meet_DB_goal": False}]}
    rendered = render(body, Path("reports/synthetic.json"), "0" * 64, 1, "1" * 64)
    assert rendered == render(body, Path("reports/synthetic.json"), "0" * 64, 1, "1" * 64)
    assert rendered.count("#### Recorded repeat") == 6 and "| 3 | TRUE | TRUE | 240 | 240 |" in rendered
    assert "NOT MET" in rendered and "NOT RUN" in rendered and "UNMEASURED" in rendered
    assert "sink\\|A" in rendered and "counter" in rendered and "before the final conservation drain" in rendered
    assert "b" * 40 in rendered and "a" * 40 in rendered and "not classloader attestation" in rendered
    assert "| 1 | 3 | 5 | UNMEASURED | UNMEASURED | UNMEASURED |" in rendered  # Missing helper/WAL counters stay missing.
    without_targets = deepcopy(body)
    without_targets.pop("frozen_target_assessments")
    assert "NOT ASSESSED: frozen_target_assessments is absent or empty" in render(without_targets, Path("x"), "x", 1, "x")
    unmatched = deepcopy(body)
    unmatched["frozen_target_assessments"][0]["status"] = "UNMEASURED_OR_UNMATCHED"
    unmatched["frozen_target_assessments"][0]["all_three_path_repeat_medians_meet_DB_goal"] = True
    assert "All three path medians meet DB goal: MET" not in render(unmatched, Path("x"), "x", 1, "x")
    with tempfile.TemporaryDirectory(prefix="ct-markdown-render-") as directory:
        source, output = Path(directory) / "input.json", Path(directory) / "output.md"
        source.write_text(json.dumps(body))
        original = source.read_bytes()
        write_report(source, output)
        assert source.read_bytes() == original and output.is_file()
        for target in (source, output):
            try:
                write_report(source, target)
            except (ValueError, FileExistsError):
                pass
            else:
                raise AssertionError("Input/existing output overwrite accepted")
        for invalid in (b'{"schema_version":1,', b'{"schema_version":1,"schema_version":1}', b'{"x":NaN}', b'{}'):
            source.write_bytes(invalid)
            fresh = Path(directory) / "never-created.md"
            try:
                write_report(source, fresh)
            except ValueError:
                assert not fresh.exists()
            else:
                raise AssertionError("Partial/invalid aggregate accepted")
    print("Offline renderer self-test: PASS (synthetic JSON and temporary files only).")
    print("Real archived report rendering: NOT RUN. Minecraft/backend/native/performance/JFR tests: NOT RUN.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Completed aggregate JSON; relative path uses repository root")
    parser.add_argument("--output", type=Path, help="New Markdown path; input and existing reports cannot be overwritten")
    parser.add_argument("--self-test", action="store_true", help="Synthetic offline checks only")
    args = parser.parse_args()
    if args.self_test:
        if args.input or args.output:
            parser.error("--self-test cannot be combined with real report paths")
        self_test()
        return 0
    if not args.input or not args.output:
        parser.error("Supply both --input and --output")
    try:
        write_report(resolve_argument(args.input), resolve_argument(args.output))
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        parser.error(str(error))
    print("Saved " + str(resolve_argument(args.output)))
    print("Rendering only; all live/backend/native/performance tests: NOT RUN by this tool.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
