#!/usr/bin/env python3
"""Offline aggregation of baseline/batch/fast optimization driver reports.

No RCON, SQL, process inspection or backend imports. Missing, failed and
incomplete runs remain visible; repeated cumulative conservation is not summed.
"""
import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
QUANTILES = ("p50", "p95", "p99")
LATENCIES = ("full_output_lower_ms", "full_output_upper_ms", "first_output_lower_ms", "first_output_upper_ms")
COUNTERS = ("db_transactions", "db_deadlock_retries", "transactions", "errors", "queue_rejected", "quarantined")


def quantiles(values):
    values = sorted(values)
    return {"samples": len(values), **{key: values[min(len(values) - 1, math.ceil(len(values) * int(key[1:]) / 100) - 1)]
        if values else None for key in QUANTILES}}


def median(values):
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def summary(values):
    present = [value for value in values if value is not None]
    return {"samples": len(present), "median": median(present),
        "min": min(present, default=None), "max": max(present, default=None)}


def measured_total(values):
    present = [value for value in values if value is not None]
    return {"measured_samples": len(present), "sum": sum(present) if present else None}


def checks_empty(conservation):
    if not conservation:
        return None
    residue = conservation.get("residue", {})
    local = residue.get("local_buffers", {})
    if not local or "sql_pool_FE" not in residue or "sql_allocation_remaining_FE" not in residue:
        return None
    return (residue["sql_pool_FE"] == residue["sql_allocation_remaining_FE"] == 0 and
        all(d.get("txFE") == d.get("rxFE") == 0 for d in local.values()))


def topology(report, scenario):
    lanes = report.get("fixtures", {}).get(scenario, [])
    chunks = {}
    normalized = []
    for lane in lanes:
        endpoints = lane.get("sources", []) + lane.get("sinks", [])
        for endpoint in endpoints:
            if all(key in endpoint for key in ("server", "x", "z")):
                chunks.setdefault(endpoint["server"], set()).add((endpoint["x"] // 16, endpoint["z"] // 16))
        normalized.append({"name": lane.get("name"),
            "sources": [e.get("server") for e in lane.get("sources", [])],
            "sinks": [e.get("server") for e in lane.get("sinks", [])]})
    return {"lanes": normalized, "per_server_chunk_counts": {server: len(coords) for server, coords in chunks.items()},
        "dimensions": ["minecraft:overworld (ct_test fixture contract)"],
        "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
        "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer"}


def sample_summary(sample, conditions, fixtures):
    business = sample.get("business", {})
    delta = sample.get("counter_delta", {})
    low = sample.get("low_flow", {})
    probes = low.get("probes", [])
    sources = sum(len(lane.get("sources", [])) for lane in fixtures)
    phase = sample.get("drive", sample.get("hold", {}))
    rounds = phase.get("planned_rounds")
    if rounds is None and conditions.get("steady_seconds") and conditions.get("feed_period_seconds"):
        seconds = conditions.get("backpressure_hold_seconds") if sample.get("scenario") == "backpressure" else conditions["steady_seconds"]
        rounds = math.ceil(seconds / conditions["feed_period_seconds"])
    expected_inputs = rounds * sources if rounds is not None and sources else None
    events = sample.get("events", [])
    input_events = [e for e in events if e.get("kind") == "input"]
    output_events = [e for e in events if e.get("kind") == "output"]
    event_input = sum(e.get("amount", 0) for e in input_events)
    event_output = sum(e.get("amount", 0) for e in output_events)
    conservation = sample.get("conservation", {})
    sinks = sample.get("sinks", {})
    sink_amounts = [sink.get("actual_extracted_FE", 0) for sink in sinks.values()]
    total_sink = sum(sink_amounts)
    shares = {name: sink.get("actual_extracted_FE", 0) / total_sink if total_sink else None for name, sink in sinks.items()}
    fairness = total_sink ** 2 / (len(sink_amounts) * sum(v * v for v in sink_amounts)) if sink_amounts and total_sink else None
    checks = {
        "sample_reported_pass": sample.get("passed"),
        "steady_fixed_input_attempts": business.get("input_attempts") == expected_inputs if business and expected_inputs is not None else None,
        "steady_all_inputs_fully_accepted": business.get("fully_accepted_input_events") == business.get("input_attempts") if business else None,
        "steady_input_event_ledger_matches": event_input == business.get("accepted_FE") and len(input_events) == business.get("input_attempts") if business and "events" in sample else None,
        "steady_output_event_ledger_matches": event_output == business.get("actual_extracted_FE") and total_sink == event_output if business and "events" in sample and sinks else None,
        "all_steady_sinks_served": all(value > 0 for value in sink_amounts) if sinks else None,
        "cumulative_resource_conserved": conservation.get("accepted_FE") == conservation.get("extracted_FE") if conservation else None,
        "local_and_SQL_residue_empty_independently": checks_empty(conservation),
        "low_probe_amounts_conserved": all(sum(p.get("outputs", {}).values()) == p.get("accepted_FE") for p in probes) if probes else None,
        "low_E2E_bounds_valid": all(0 <= p["full_output"]["lower_ms"] <= p["full_output"]["upper_ms"] for p in probes) if probes else None}
    if sample.get("scenario") in ("same", "cross", "mixed"):
        checks["low_probe_count_matches_conditions"] = len(probes) == conditions.get("low_flow_probes_per_path_per_repeat", 0)
    recalculated = {}
    for key in LATENCIES:
        endpoint = "full_output" if key.startswith("full") else "first_output"
        bound = "lower_ms" if "_lower_" in key else "upper_ms"
        values = [p[endpoint][bound] for p in probes if endpoint in p and bound in p[endpoint]]
        recalculated[key] = quantiles(values)
        if values and low.get(key):
            checks["low_" + key + "_quantiles_match"] = all(
                abs(recalculated[key][q] - low[key][q]) <= 1e-7 for q in QUANTILES)
    low_outputs = {}
    for probe in probes:
        for endpoint, value in probe.get("outputs", {}).items():
            low_outputs[endpoint] = low_outputs.get(endpoint, 0) + value
    low_delta = low.get("counter_delta", {})
    statements = delta.get("statements")
    actual_inputs = business.get("input_attempts", 0)
    accepted_events = business.get("accepted_input_events", 0)
    stats = {
        "scenario": sample.get("scenario"), "repeat": sample.get("repeat"), "reported_passed": sample.get("passed"),
        "failure": sample.get("failure"), "complete": bool(business and delta and conservation and sample.get("passed") is True),
        "checks": checks, "low_probe_count": len(probes),
        "low_flow": {**recalculated, "actual_extracted_FE_by_endpoint": low_outputs,
            "input_rcon_ms": low.get("input_rcon_ms"), "output_rcon_ms": low.get("output_rcon_ms"),
            "counter_delta": low_delta}, "business": business, "counter_delta": delta,
        "cost": {"planned_input_attempts": expected_inputs,
            "DBtransactions_per_input_attempt": delta.get("db_transactions", 0) / actual_inputs if delta and actual_inputs else None,
            "SQL_statement_events_per_input_attempt": statements["events"] / actual_inputs if statements and actual_inputs else None,
            "DBtransactions_per_accepted_event": delta.get("db_transactions", 0) / accepted_events if delta and accepted_events else None,
            "SQL_statement_events_per_accepted_event": statements["events"] / accepted_events if statements and accepted_events else None},
        "sinks": sinks, "sink_output_shares": shares, "sink_Jain_index": fairness,
        "max_sink_unserved_seconds": max((s.get("max_unserved_seconds", 0) for s in sinks.values()), default=None),
        "observer": phase, "cumulative_conservation": conservation,
        "error_counters": {key: delta.get(key) for key in COUNTERS if key not in ("db_transactions", "transactions")},
        "SQL_statement_errors": statements.get("errors") if statements else None,
        "steady_actual_output_FE": event_output if "events" in sample else business.get("actual_extracted_FE"),
        "steady_tail_to_drain_FE": business.get("accepted_FE", 0) - business.get("actual_extracted_FE", 0) if business else None}
    # Keep phase ledger totals separate from cumulative per-lane conservation.
    all_events = events + sample.get("warmup_events", []) + sample.get("drain_events", []) + low.get("events", [])
    stats["all_phase_event_ledger"] = {
        "accepted_FE": sum(e.get("amount", 0) for e in all_events if e.get("kind") == "input"),
        "extracted_FE": sum(e.get("amount", 0) for e in all_events if e.get("kind") == "output")}
    return stats


def aggregate_case(report, name):
    conditions = report.get("conditions", {})
    expected = conditions.get("repeats", 0)
    fixtures = report.get("fixtures", {}).get(name, [])
    samples = [sample_summary(s, conditions, fixtures) for s in report.get("samples", []) if s.get("scenario") == name]
    samples.sort(key=lambda s: s.get("repeat") or 0)
    complete = [s for s in samples if s["complete"]]
    duplicates = len({s["repeat"] for s in samples}) != len(samples)
    missing = [repeat for repeat in range(1, expected + 1) if not any(s["repeat"] == repeat and s["complete"] for s in samples)]
    probe_expected = conditions.get("low_flow_probes_per_path_per_repeat", 0) if name in ("same", "cross", "mixed") else 0
    valid = [s for s in complete if not any(value is False for value in s["checks"].values())]
    low = {}
    for key in LATENCIES:
        low[key] = {"repeat_percentile_medians": {q: median(
            s["low_flow"][key].get(q) for s in complete) for q in QUANTILES},
            "repeat_percentile_ranges": {q: summary(s["low_flow"][key].get(q) for s in complete) for q in QUANTILES}}
    steady = {}
    for key in ("db_transactions", "db_deadlock_retries", "errors", "queue_rejected", "quarantined"):
        steady[key] = summary(s["counter_delta"].get(key) for s in complete)
    steady["SQL_statement_events"] = summary((s["counter_delta"].get("statements") or {}).get("events") for s in complete)
    steady["SQL_statement_errors"] = summary(s["SQL_statement_errors"] for s in complete)
    for key in ("DBtransactions_per_input_attempt", "SQL_statement_events_per_input_attempt"):
        steady[key] = summary(s["cost"][key] for s in complete)
    for key in ("actual_extracted_FE_per_second", "accepted_FE", "actual_extracted_FE", "input_attempts"):
        steady[key] = summary(s["business"].get(key) for s in complete)
    steady["max_sink_unserved_seconds"] = summary(s["max_sink_unserved_seconds"] for s in complete)
    steady["sink_Jain_index"] = summary(s["sink_Jain_index"] for s in complete)
    ledger = {key: sum(s["all_phase_event_ledger"][key] for s in samples) for key in ("accepted_FE", "extracted_FE")}
    # Every repeat's conservation includes prior repeats on this same channel.
    # Use the most recent checkpoint, never sum repeated cumulative figures.
    cumulative = next((s["cumulative_conservation"] for s in reversed(samples) if s["cumulative_conservation"]), None)
    latest_matches = (cumulative["accepted_FE"] == ledger["accepted_FE"] and cumulative["extracted_FE"] == ledger["extracted_FE"]) if cumulative else None
    state = "complete" if expected and len(valid) == expected and not duplicates else "incomplete"
    if any(s["failure"] or s["reported_passed"] is False and s["business"] for s in samples) or any(
            any(value is False for value in s["checks"].values()) for s in complete):
        state = "failed"
    if cumulative and latest_matches is False and len(complete) == len(samples):
        state = "failed"
    sink_totals, low_sink_totals = {}, {}
    for sample in complete:
        for endpoint, sink in sample["sinks"].items():
            sink_totals[endpoint] = sink_totals.get(endpoint, 0) + sink.get("actual_extracted_FE", 0)
        for endpoint, amount in sample["low_flow"]["actual_extracted_FE_by_endpoint"].items():
            low_sink_totals[endpoint] = low_sink_totals.get(endpoint, 0) + amount
    error_totals = {"steady": {key: measured_total(s["counter_delta"].get(key) for s in complete)
        for key in ("db_deadlock_retries", "errors", "queue_rejected", "quarantined")},
        "low_flow": {key: measured_total(s["low_flow"]["counter_delta"].get(key) for s in complete)
        for key in ("db_deadlock_retries", "errors", "queue_rejected", "quarantined")}}
    error_totals["steady"]["SQL_statement_errors"] = measured_total(s["SQL_statement_errors"] for s in complete)
    error_totals["low_flow"]["SQL_statement_errors"] = measured_total(
        (s["low_flow"]["counter_delta"].get("statements") or {}).get("errors") for s in complete)
    return {"scenario": name, "status": state, "expected_repeats": expected,
        "complete_repeats": len(complete), "valid_repeats": len(valid), "missing_or_incomplete_repeats": missing,
        "duplicate_repeat_ids": duplicates, "expected_low_probes_per_repeat": probe_expected,
        "low_probe_counts_match": all(s["low_probe_count"] == probe_expected for s in complete) if probe_expected and complete else None,
        "low_flow": low, "steady": steady, "topology": topology(report, name), "repeats": samples,
        "error_totals": error_totals, "steady_output_FE_by_endpoint": sink_totals,
        "low_output_FE_by_endpoint": low_sink_totals,
        "conservation": {"all_phase_event_ledger": ledger,
            "latest_cumulative_accepted_FE": cumulative.get("accepted_FE") if cumulative else None,
            "latest_cumulative_extracted_FE": cumulative.get("extracted_FE") if cumulative else None,
            "latest_cumulative_matches_event_ledger": latest_matches,
            "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals."}}


def aggregate_report(name, path):
    result = {"name": name, "source": str(path) if path else None, "status": "not_run",
        "failures": [], "regressions": [], "cases": {}}
    if not path:
        return result
    try:
        raw = path.read_bytes()
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError("Driver report larger than 64 MiB")
        report = json.loads(raw)
        if report.get("schema_version") != 1 or "conditions" not in report or "samples" not in report or report.get("report_kind"):
            raise ValueError("Unsupported report; expected optimization driver schema 1")
        result.update(label=report.get("label"), source_sha256=hashlib.sha256(raw).hexdigest(), source_bytes=len(raw),
            conditions=report["conditions"], report_passed=report.get("passed"), git_head=report.get("git_head"),
            identity=report.get("identity"), warnings=report.get("warnings", []),
            other_live_backend_sessions=report.get("other_live_backend_sessions"),
            failures=report.get("failures", []), regressions=report.get("regressions", []),
            elapsed_seconds=report.get("elapsed_seconds"))
        names = list(dict.fromkeys(report["conditions"].get("scenarios", []) +
            [s.get("scenario") for s in report["samples"] if s.get("scenario")]))
        result["cases"] = {scenario: aggregate_case(report, scenario) for scenario in names}
        complete = bool(result["cases"]) and all(case["status"] == "complete" for case in result["cases"].values())
        if result["failures"] or any(case["status"] == "failed" for case in result["cases"].values()):
            result["status"] = "failed"
        elif not complete:
            result["status"] = "incomplete"
        elif result["regressions"]:
            result["status"] = "completed_with_reported_regressions"
        elif report.get("passed") is True:
            result["status"] = "passed"
        else:
            result["status"] = "complete_samples_not_finalized_or_not_passed"
    except FileNotFoundError as error:
        result.update(status="missing_file", failures=[str(error)])
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        result.update(status="invalid_report", failures=[type(error).__name__ + ": " + str(error)])
    return result


def comparisons(baseline, current, threshold):
    result = {"profile": current["name"], "baseline": baseline["name"],
        "status": "not_comparable", "reason": None, "metrics": [], "regressions": []}
    if not baseline.get("cases") or not current.get("cases"):
        result["reason"] = "Baseline or current profile has no completed case evidence"
        return result
    if baseline.get("conditions") != current.get("conditions"):
        result["reason"] = "conditions differ; no matched inference"
        return result
    for scenario, before in baseline["cases"].items():
        after = current["cases"].get(scenario)
        if not after or before["status"] != "complete" or after["status"] != "complete":
            result["reason"] = "Missing, failed or incomplete repeats; no matched inference"
            return result
        if before["topology"] != after["topology"]:
            result["reason"] = "fixture topology differs; no matched inference"
            return result
    result["status"] = "matched"
    result["functional_run_status"] = current["status"]
    sql_scope_clear = (baseline.get("other_live_backend_sessions") == [] and current.get("other_live_backend_sessions") == [])
    result["SQL_account_comparison_eligible"] = sql_scope_clear
    for scenario, before in baseline["cases"].items():
        after = current["cases"][scenario]
        metrics = [
            ("steady_DBtransactions_fixed_input_count", before["steady"]["db_transactions"]["median"], after["steady"]["db_transactions"]["median"], 1, 0),
            ("steady_SQL_statement_events_fixed_input_count", before["steady"]["SQL_statement_events"]["median"], after["steady"]["SQL_statement_events"]["median"], 1, 0),
            ("steady_actual_extracted_FE_per_second", before["steady"]["actual_extracted_FE_per_second"]["median"], after["steady"]["actual_extracted_FE_per_second"]["median"], -1, 0)]
        for q in QUANTILES:
            metrics.append(("low_full_output_upper_ms_" + q,
                before["low_flow"]["full_output_upper_ms"]["repeat_percentile_medians"][q],
                after["low_flow"]["full_output_upper_ms"]["repeat_percentile_medians"][q], 1, 10))
        for key, old, new, direction, minimum_absolute in metrics:
            change = (new / old - 1) * 100 if old is not None and new is not None and old else None
            regression = change is not None and direction * change > threshold and direction * (new - old) > minimum_absolute
            reason = None
            if key == "steady_SQL_statement_events_fixed_input_count" and not sql_scope_clear:
                regression = False
                reason = "Account-wide ct_dev scope has other/unknown live backend sessions; changes are diagnostic, not attributed to this workload"
            entry = {"scenario": scenario, "metric": key, "baseline": old, "current": new,
                "change_percent": change, "regression": regression,
                "comparison_limitation": reason,
                "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"}
            result["metrics"].append(entry)
            if regression:
                result["regressions"].append(entry)
    return result


def table_rows(aggregate):
    rows = []
    for profile, report in aggregate["profiles"].items():
        if not report["cases"]:
            rows.append({"profile": profile, "report_status": report["status"], "scenario": "UNMEASURED"})
        for scenario, case in report["cases"].items():
            if not case["repeats"]:
                rows.append({"profile": profile, "report_status": report["status"], "scenario": scenario, "sample_status": "not_run"})
            for sample in case["repeats"]:
                row = {"profile": profile, "report_status": report["status"], "scenario": scenario,
                    "repeat": sample["repeat"], "sample_status": "complete" if sample["complete"] else "failed_or_incomplete",
                    "low_probes": sample["low_probe_count"], "input_attempts": sample["business"].get("input_attempts"),
                    "accepted_FE": sample["business"].get("accepted_FE"), "steady_extracted_FE": sample["business"].get("actual_extracted_FE"),
                    "DBtransactions": sample["counter_delta"].get("db_transactions"),
                    "SQL_statement_events": (sample["counter_delta"].get("statements") or {}).get("events"),
                    "db_deadlock_retries": sample["counter_delta"].get("db_deadlock_retries"),
                    "worker_errors": sample["counter_delta"].get("errors"), "queue_rejected": sample["counter_delta"].get("queue_rejected"),
                    "quarantined": sample["counter_delta"].get("quarantined"), "SQL_statement_errors": sample["SQL_statement_errors"],
                    "sink_Jain_index": sample["sink_Jain_index"], "max_sink_unserved_seconds": sample["max_sink_unserved_seconds"],
                    "conserved": sample["checks"]["cumulative_resource_conserved"],
                    "residue_empty": sample["checks"]["local_and_SQL_residue_empty_independently"]}
                for q in QUANTILES:
                    row["low_full_lower_ms_" + q] = sample["low_flow"]["full_output_lower_ms"][q]
                    row["low_full_upper_ms_" + q] = sample["low_flow"]["full_output_upper_ms"][q]
                rows.append(row)
    return rows


def print_summary(aggregate):
    print("| Profile | State | Scenario | Repeats | Low-flow upper p50/p95/p99 ms | DBtxn / fixed inputs | SQL events / fixed inputs |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for name, report in aggregate["profiles"].items():
        if not report["cases"]:
            print(f"| {name} | {report['status']} | UNMEASURED | — | — | — | — |")
        for scenario, case in report["cases"].items():
            values = case["low_flow"]["full_output_upper_ms"]["repeat_percentile_medians"]
            latency = "/".join(f"{values[q]:.2f}" if values[q] is not None else "UNMEASURED" for q in QUANTILES)
            db = case["steady"]["db_transactions"]["median"]
            statements = case["steady"]["SQL_statement_events"]["median"]
            inputs = case["steady"]["input_attempts"]["median"]
            print(f"| {name} | {report['status']}/{case['status']} | {scenario} | {case['complete_repeats']}/{case['expected_repeats']} | {latency} | {db} / {inputs} | {statements} / {inputs} |")
        if report["failures"]:
            print(name + " failures: " + json.dumps(report["failures"], ensure_ascii=False))
        if report["regressions"]:
            print(name + " reported regressions: " + json.dumps(report["regressions"], ensure_ascii=False))


def self_test():
    # No filesystem/socket/backend calls: synthetic complete, incomplete, failure.
    report = {"conditions": {"repeats": 2, "steady_seconds": 1, "feed_period_seconds": 1,
        "scenarios": ["same"], "low_flow_probes_per_path_per_repeat": 0},
        "fixtures": {"same": [{"name": "same", "sources": [{"server": "A", "x": 0, "z": 0}],
            "sinks": [{"server": "A", "x": 1, "z": 0}]}]}, "samples": []}
    for repeat in (1, 2):
        report["samples"].append({"scenario": "same", "repeat": repeat, "passed": True,
            "business": {"input_attempts": 1, "accepted_input_events": 1, "fully_accepted_input_events": 1,
                "accepted_FE": 10, "actual_extracted_FE": 10, "actual_extracted_FE_per_second": 10},
            "counter_delta": {"db_transactions": 3, "statements": {"events": 12, "errors": 0}},
            "events": [{"kind": "input", "amount": 10}, {"kind": "output", "amount": 10}],
            "sinks": {"same_sink_0": {"actual_extracted_FE": 10, "max_unserved_seconds": 1}},
            "drive": {"planned_rounds": 1},
            "conservation": {"accepted_FE": repeat * 10, "extracted_FE": repeat * 10,
                "residue": {"sql_pool_FE": 0, "sql_allocation_remaining_FE": 0,
                    "local_buffers": {"source": {"txFE": 0, "rxFE": 0}, "sink": {"txFE": 0, "rxFE": 0}}}}})
    complete = aggregate_case(report, "same")
    assert complete["status"] == "complete"
    assert complete["conservation"]["latest_cumulative_accepted_FE"] == 20
    assert complete["conservation"]["latest_cumulative_matches_event_ledger"]
    assert complete["conservation"]["all_phase_event_ledger"]["accepted_FE"] == 20  # NOT 10+20
    partial = deepcopy(report)
    partial["samples"].pop()
    assert aggregate_case(partial, "same")["missing_or_incomplete_repeats"] == [2]
    broken = deepcopy(report)
    broken["samples"][1]["passed"] = False
    broken["samples"][1]["failure"] = "resource mismatch"
    assert aggregate_case(broken, "same")["status"] == "failed"
    assert quantiles(list(range(1, 101))) == {"samples": 100, "p50": 50, "p95": 95, "p99": 99}
    missing = aggregate_report("fast", None)
    assert missing["status"] == "not_run"
    assert comparisons({"name": "baseline", "cases": {}}, missing, 10)["status"] == "not_comparable"
    print("Offline comparison checks passed; no backend/process contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--fast", type=Path)
    parser.add_argument("--report", action="append", default=[], metavar="NAME=PATH", help="Additional named driver report")
    parser.add_argument("--output", type=Path, help="Optional aggregate JSON; stdout otherwise contains compact table")
    parser.add_argument("--csv", type=Path, help="Optional per-repeat flat table")
    parser.add_argument("--max-regression-percent", type=float, default=10)
    parser.add_argument("--strict", action="store_true", help="Nonzero exit for supplied incomplete/failed runs or detected regressions")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    paths = {"baseline": args.baseline, "batch": args.batch, "fast": args.fast}
    for item in args.report:
        if "=" not in item:
            parser.error("--report needs NAME=PATH")
        name, path = item.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", name) or name in paths or not path:
            parser.error("Additional report name must be unique and bounded")
        paths[name] = Path(path)
    if not any(paths.values()):
        parser.error("Supply at least one driver report")
    if not 0 <= args.max_regression_percent <= 100:
        parser.error("Regression percent outside 0..100")
    aggregate = {"schema_version": 1, "report_kind": "offline_optimization_comparison",
        "utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "scope": {
            "latency": "Actual capability accept -> actual capability pull; lower/upper RCON bounds, not world-save latency",
            "percentiles": "Every repeat retained; aggregate is median of repeat percentiles, not pooled p95",
            "business": "Fixed source attempts/rounds; all acceptance and output ledger checks retained",
            "SQL": "ct_dev account statement/sql events; root observer excluded; other-live-session caveat retained",
            "conservation": "Latest cumulative per reused channel, not sum of repeat cumulative figures; SQL/WAL/local copies never added",
            "topology": "Overworld console fixtures may share one chunk. NeighborPump skips neighboring Tesseracts. Different chunks/dimensions/real chests require separate correctness tests.",
            "unmeasured": "No fabricated absent runs, failed-run performance success, WAL timing, uncollected early-repeat MC tick means or actual TPS"},
        "profiles": {name: aggregate_report(name, path) for name, path in paths.items()}}
    aggregate["comparisons"] = [comparisons(aggregate["profiles"]["baseline"], report, args.max_regression_percent)
        for name, report in aggregate["profiles"].items() if name != "baseline"]
    rows = table_rows(aggregate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with args.csv.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    print_summary(aggregate)
    if args.output:
        print("Saved " + str(args.output))
    if args.csv:
        print("Saved " + str(args.csv))
    bad = any(r["status"] not in ("passed", "not_run") for r in aggregate["profiles"].values())
    regressions = any(c["regressions"] for c in aggregate["comparisons"])
    return 1 if args.strict and (bad or regressions) else 0


if __name__ == "__main__":
    sys.exit(main())
