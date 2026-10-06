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
import stat
import statistics
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
QUANTILES = ("p50", "p95", "p99")
LATENCIES = ("full_output_lower_ms", "full_output_upper_ms", "first_output_lower_ms", "first_output_upper_ms")
COUNTERS = ("db_transactions", "db_deadlock_retries", "transactions", "errors", "queue_rejected", "quarantined")
SERVERS = ("A", "B", "C")
SNAPSHOT_COUNTERS = COUNTERS + ("db_transaction_attempts", "db_statements",
    "deferred_registry_decodes", "dropped_wake_hints", "local_exchange_calls",
    "local_input_units", "local_output_units", "batch_devices", "batch_records",
    "batch_payload_bytes", "local_wakes", "remote_hint_wakes", "poll_fallback",
    "empty_batches", "allocation_misses", "local_credit_publications",
    "wal_writes", "wal_bytes", "wal_identical_skipped")
DIAGNOSTIC_COUNTERS = tuple(key for key in SNAPSHOT_COUNTERS if key not in COUNTERS)
MAX_DRIVER_BYTES = 64 * 1024 * 1024
MAX_SEQUENCE_BYTES = 256 * 1024
SEQUENCE_EVIDENCE_SCOPE = ("Operator-declared runtime revision from an explicitly supplied completed orchestrator, "
    "bound to the exact profile report by a unique path reference and SHA-256. This is not classloader attestation. "
    "The raw git_head remains the reported workspace checkout; functional/resource checks and profile status are unchanged.")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def snapshot_counters(sample):
    """Extract cumulative counters already captured by the unchanged driver."""
    first, last = sample.get("counter_start", {}), sample.get("counter_end", {})
    result = {"scope": "Actual per-server first/final ct_test status read intervals; includes ambient JVM work between reads. No new observations or timing interpolation.",
        "per_server": {}, "summed_cumulative_delta": {}, "counter_status": {},
        "missing_keys_by_server": {}, "invalid_keys_by_server": {}}
    for server in SERVERS:
        f, l = first.get("servers", {}).get(server, {}), last.get("servers", {}).get(server, {})
        fm, lm = f.get("metrics", {}), l.get("metrics", {})
        values, missing, invalid = {}, [], []
        for key in SNAPSHOT_COUNTERS:
            old, new = fm.get(key), lm.get(key)
            if not finite(old) or not finite(new):
                values[key] = None
                missing.append(key)
            else:
                values[key] = new - old
                if old < 0 or new < 0 or new < old:
                    invalid.append(key)
        result["per_server"][server] = {"first_status_run_relative_interval": [f.get("start"), f.get("end")],
            "last_status_run_relative_interval": [l.get("start"), l.get("end")],
            "first_cumulative": {key: fm.get(key) for key in SNAPSHOT_COUNTERS},
            "last_cumulative": {key: lm.get(key) for key in SNAPSHOT_COUNTERS},
            "cumulative_delta": values}
        result["missing_keys_by_server"][server] = missing
        result["invalid_keys_by_server"][server] = invalid
    for key in SNAPSHOT_COUNTERS:
        values = [result["per_server"][server]["cumulative_delta"][key] for server in SERVERS]
        invalid = any(key in result["invalid_keys_by_server"][server] for server in SERVERS)
        status = "INVALID_COUNTER" if invalid else "UNMEASURED" if any(v is None for v in values) else "INSTRUMENTED_OBSERVED"
        result["counter_status"][key] = status
        result["summed_cumulative_delta"][key] = sum(values) if status == "INSTRUMENTED_OBSERVED" else None
    result["scope_notes"] = {
        "counter_window": "Main-path counter_end precedes final conservation drain: cost per fixed input window, not the complete drained resource lifecycle. Backpressure includes its recovery before counter_end. Tail SQL/WAL work is not backfilled.",
        "transactions": "Completed backend worker tasks; not database commits. Use db_transactions for successful SQL transactions.",
        "db_statements": "Instrumented Sql.query/update call attempts, including retries/failures; excludes JDBC transaction controls and statements outside those helpers. Distinct from account-wide performance_schema events.",
        "batch_devices": "Device appearances processed by batch calls; not a count of distinct fixture endpoints.",
        "batch_records": "Records processed by batch calls; not a count of SQL statements or external business events.",
        "local_credit_publications": "Includes credits delivered after cross-server SQL allocation; cannot identify same-server-source fast-path hits.",
        "WAL": "Absent keys are UNMEASURED, never zero. Writes/bytes are independent cost counters; no SQL/WAL/local resource copies are added."}
    return result


def barrier_snapshots(sample):
    """WAL barrier percentiles are ring snapshots, never cumulative counters."""
    result = {"scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values.",
        "per_server": {}}
    for server in SERVERS:
        entry = {}
        for name in ("start", "end"):
            point = sample.get("counter_" + name, {}).get("servers", {}).get(server, {})
            metrics = point.get("metrics", {})
            values = {key: metrics.get("wal_barrier_ms_" + key) for key in (*QUANTILES, "samples")}
            status = "UNMEASURED" if not all(finite(v) for v in values.values()) else (
                "NO_RECORDED_BARRIERS" if values["samples"] == 0 else "INSTRUMENTED_SNAPSHOT")
            entry[name] = {"status": status, "status_run_relative_interval": [point.get("start"), point.get("end")], **values}
        result["per_server"][server] = entry
    return result


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
    captured = snapshot_counters(sample)
    captured_delta = captured["summed_cumulative_delta"]
    costs = {key: captured_delta.get(key) if captured_delta.get(key) is not None else delta.get(key)
        if key in COUNTERS and captured["counter_status"][key] == "UNMEASURED" else None for key in SNAPSHOT_COUNTERS}
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
        "low_E2E_bounds_valid": all(0 <= p["full_output"]["lower_ms"] <= p["full_output"]["upper_ms"] for p in probes) if probes else None,
        "instrumented_cumulative_counters_nondecreasing": not any(captured["invalid_keys_by_server"].values()),
        "captured_original_counters_match_driver_delta": all(captured_delta[key] == delta[key]
            for key in COUNTERS if captured_delta.get(key) is not None and key in delta)}
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
        "captured_counter_window": captured, "cost_counters": costs,
        "cost_counters_per_input_attempt": {key: value / actual_inputs if value is not None and actual_inputs else None
            for key, value in costs.items()},
        "WAL_barrier_snapshots": barrier_snapshots(sample),
        "cost": {"planned_input_attempts": expected_inputs,
            "DBtransactions_per_input_attempt": costs["db_transactions"] / actual_inputs if costs["db_transactions"] is not None and actual_inputs else None,
            "SQL_statement_events_per_input_attempt": statements["events"] / actual_inputs if statements and actual_inputs else None,
            "DBtransactions_per_accepted_event": costs["db_transactions"] / accepted_events if costs["db_transactions"] is not None and accepted_events else None,
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
    for key in ("transactions", *DIAGNOSTIC_COUNTERS):
        steady[key] = summary(s["cost_counters"].get(key) for s in complete)
        steady[key]["status"] = "INSTRUMENTED_OBSERVED" if complete and steady[key]["samples"] == len(complete) else "PARTIALLY_MEASURED" if steady[key]["samples"] else "UNMEASURED"
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
        "WAL_barrier_end_snapshot_summaries_by_server": {server: {
            q: summary(s["WAL_barrier_snapshots"]["per_server"][server]["end"][q]
                for s in complete if s["WAL_barrier_snapshots"]["per_server"][server]["end"]["status"] == "INSTRUMENTED_SNAPSHOT")
            for q in QUANTILES} for server in SERVERS},
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
        if len(raw) > MAX_DRIVER_BYTES:
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


def sequence_report_path(value, root, limit):
    """Only regular, bounded archived reports; relative references use workspace root."""
    root = Path(root).resolve()
    supplied = Path(value)
    candidate = supplied if supplied.is_absolute() else root / supplied
    path = candidate.resolve(strict=True)
    if not path.is_relative_to(root / "reports"):
        raise ValueError("Sequence evidence must be inside workspace reports/")
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError("Sequence evidence cannot use symlink paths")
    attributes = path.stat()
    if not stat.S_ISREG(attributes.st_mode) or attributes.st_size > limit:
        raise ValueError("Sequence evidence must be a regular file within its size bound")
    return path


def bounded_sequence_json(path, limit):
    # Read limit+1 rather than trusting a prior stat if a file changes concurrently.
    with path.open("rb") as file:
        raw = file.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Sequence evidence grew beyond its size bound")
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("Sequence evidence must be a JSON object")
    return body, raw


def declared_revision(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise ValueError("Sequence runtime revision must be a full 40-hex declaration")
    return value.lower()


def bind_sequence_evidence(profile, profile_path, sequence_path, root=ROOT):
    """Add identity evidence only; never replace the input report's outcome or git_head."""
    parent_path = sequence_report_path(sequence_path, root, MAX_SEQUENCE_BYTES)
    parent, parent_raw = bounded_sequence_json(parent_path, MAX_SEQUENCE_BYTES)
    if parent.get("passed") is not True or parent.get("failures") or parent.get("stop_failure"):
        raise ValueError("Sequence must have passed without a recorded functional/stop failure")
    if "procedure_completed" in parent and parent["procedure_completed"] is not True:
        raise ValueError("Sequence procedure is explicitly incomplete")
    end = parent.get("utc_end")
    if not isinstance(end, str):
        raise ValueError("Sequence must record utc_end")
    ended = datetime.fromisoformat(end.replace("Z", "+00:00"))
    if ended.tzinfo is None or ended.utcoffset().total_seconds() != 0:
        raise ValueError("Sequence utc_end must be a timezone-aware UTC timestamp")
    revision = declared_revision(parent.get("loaded_source_revision_declared"))
    runs = parent.get("runs")
    if not isinstance(runs, list) or not 1 <= len(runs) <= 128 or any(not isinstance(run, dict) for run in runs):
        raise ValueError("Sequence runs must be a nonempty bounded list of objects")
    # aggregate_report uses the caller's path semantics; resolve that exact input,
    # while orchestrator child references are rooted at the workspace.
    input_path = sequence_report_path(Path(profile_path).resolve(), root, MAX_DRIVER_BYTES)
    children = []
    matching = []
    for index, run in enumerate(runs):
        reference = run.get("report")
        if not isinstance(reference, str) or not reference:
            raise ValueError("Every sequence run needs a report reference")
        child_path = sequence_report_path(reference, root, MAX_DRIVER_BYTES)
        children.append(str(child_path))
        if child_path == input_path:
            matching.append((index, run))
    if len(matching) != 1:
        raise ValueError("Sequence must reference the supplied profile input exactly once")
    index, run = matching[0]
    if declared_revision(run.get("loaded_source_revision_declared")) != revision:
        raise ValueError("Sequence and selected child runtime declarations disagree")
    expected_sha = run.get("report_sha256")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha):
        raise ValueError("Selected sequence child needs a full SHA-256")
    child, child_raw = bounded_sequence_json(input_path, MAX_DRIVER_BYTES)
    actual_sha = hashlib.sha256(child_raw).hexdigest()
    if expected_sha.lower() != actual_sha:
        raise ValueError("Selected sequence child SHA-256 does not match the supplied profile input")
    if profile.get("source_sha256") != actual_sha or profile.get("source_bytes") != len(child_raw):
        raise ValueError("Profile input differs from its already aggregated snapshot")
    if profile.get("git_head") != child.get("git_head"):
        raise ValueError("Profile workspace git_head differs from the verified child snapshot")
    profile["declared_runtime_revision"] = revision
    profile["runtime_revision_evidence"] = {
        "status": "VERIFIED_SEQUENCE_REFERENCE", "scope": SEQUENCE_EVIDENCE_SCOPE,
        "sequence": {"path": str(parent_path), "sha256": hashlib.sha256(parent_raw).hexdigest(),
            "bytes": len(parent_raw), "metadata": deepcopy(parent),
            "completion_policy": "explicit procedure_completed=true, passed=true and utc_end" if "procedure_completed" in parent
                else "legacy schema: passed=true and utc_end; procedure_completed absent"},
        "selected_run_index": index, "selected_run": deepcopy(run),
        "profile_input": {"path": str(input_path), "sha256": actual_sha, "bytes": len(child_raw)},
        "raw_workspace_git_head": profile.get("git_head"),
        "referenced_child_paths": children,
        "other_children_hash_verification": "Only the selected profile child SHA is verified by this binding"}


def runtime_revision_identity(profile):
    verified = profile.get("runtime_revision_evidence", {}).get("status") == "VERIFIED_SEQUENCE_REFERENCE"
    return {"revision": profile.get("declared_runtime_revision") if verified else profile.get("git_head"),
        "basis": "explicit verified sequence operator declaration" if verified else "raw report git_head fallback",
        "raw_workspace_git_head": profile.get("git_head"),
        "scope": SEQUENCE_EVIDENCE_SCOPE if verified else "Unchanged legacy git_head rule; no explicit runtime sequence evidence supplied"}


def profile_complete_for_targets(profile):
    return (profile.get("status") in ("passed", "completed_with_reported_regressions") and
        not profile.get("failures") and bool(profile.get("cases")) and
        all(case.get("status") == "complete" for case in profile["cases"].values()))


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
            ("steady_actual_extracted_FE_per_second", before["steady"]["actual_extracted_FE_per_second"]["median"], after["steady"]["actual_extracted_FE_per_second"]["median"], -1, 0),
            ("steady_max_sink_unserved_seconds", before["steady"]["max_sink_unserved_seconds"]["median"], after["steady"]["max_sink_unserved_seconds"]["median"], 1, .1)]
        optional = {"steady_" + key + "_fixed_input_count": key for key in ("transactions", *DIAGNOSTIC_COUNTERS)}
        for metric, key in optional.items():
            # Device/record/wake counts show work distribution, not an independently
            # established performance objective. Cost regressions use actual SQL/WAL.
            direction = 1 if key in ("db_transaction_attempts", "db_statements", "wal_writes", "wal_bytes") else 0
            metrics.append((metric, before["steady"][key]["median"], after["steady"][key]["median"], direction, 0))
        for q in QUANTILES:
            metrics.append(("low_full_output_upper_ms_" + q,
                before["low_flow"]["full_output_upper_ms"]["repeat_percentile_medians"][q],
                after["low_flow"]["full_output_upper_ms"]["repeat_percentile_medians"][q], 1, 10))
        for key, old, new, direction, minimum_absolute in metrics:
            instrumented = (key not in optional or all(case["steady"][optional[key]]["status"] == "INSTRUMENTED_OBSERVED"
                for case in (before, after)))
            status = "UNMEASURED" if old is None or new is None else "PARTIALLY_MEASURED" if not instrumented else "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES"
            change = (new / old - 1) * 100 if instrumented and old is not None and new is not None and old else None
            regression = change is not None and direction * change > threshold and direction * (new - old) > minimum_absolute
            reason = None
            if key == "steady_SQL_statement_events_fixed_input_count" and not sql_scope_clear:
                regression = False
                reason = "Account-wide ct_dev scope has other/unknown live backend sessions; changes are diagnostic, not attributed to this workload"
            entry = {"scenario": scenario, "metric": key, "baseline": old, "current": new,
                "change_percent": change, "regression": regression,
                "measurement_status": status,
                "comparison_limitation": reason,
                "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time." if key == "steady_max_sink_unserved_seconds" else "Three repeat percentiles' median for latency; repeat median for fixed business counters"}
            result["metrics"].append(entry)
            if regression:
                result["regressions"].append(entry)
        for server in SERVERS:
            for q in QUANTILES:
                old = before["WAL_barrier_end_snapshot_summaries_by_server"][server][q]
                new = after["WAL_barrier_end_snapshot_summaries_by_server"][server][q]
                matched = (old["samples"] == before["complete_repeats"] and new["samples"] == after["complete_repeats"])
                result["metrics"].append({"scenario": scenario, "server": server,
                    "metric": "WAL_barrier_end_ring_snapshot_ms_" + q, "baseline": old["median"], "current": new["median"],
                    "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC" if matched else "PARTIALLY_MEASURED" if old["samples"] and new["samples"] else "UNMEASURED",
                    "change_percent": (new["median"] / old["median"] - 1) * 100 if matched and old["median"] else None,
                    "regression": False, "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
                    "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile."})
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
                    "worker_completed_tasks": sample["cost_counters"].get("transactions"),
                    "db_deadlock_retries": sample["counter_delta"].get("db_deadlock_retries"),
                    "worker_errors": sample["counter_delta"].get("errors"), "queue_rejected": sample["counter_delta"].get("queue_rejected"),
                    "quarantined": sample["counter_delta"].get("quarantined"), "SQL_statement_errors": sample["SQL_statement_errors"],
                    "sink_Jain_index": sample["sink_Jain_index"], "max_sink_unserved_seconds": sample["max_sink_unserved_seconds"],
                    "conserved": sample["checks"]["cumulative_resource_conserved"],
                    "residue_empty": sample["checks"]["local_and_SQL_residue_empty_independently"]}
                row.update({key: sample["cost_counters"].get(key) for key in DIAGNOSTIC_COUNTERS})
                for server in SERVERS:
                    barrier = sample["WAL_barrier_snapshots"]["per_server"][server]["end"]
                    for key in (*QUANTILES, "samples"):
                        row[server + "_WAL_barrier_end_ring_" + key] = barrier[key] if barrier["status"] != "UNMEASURED" else None
                for q in QUANTILES:
                    row["low_full_lower_ms_" + q] = sample["low_flow"]["full_output_lower_ms"][q]
                    row["low_full_upper_ms_" + q] = sample["low_flow"]["full_output_upper_ms"][q]
                rows.append(row)
    return rows


def frozen_targets(baseline, current, context, comparison):
    """Do not change the original per-path goals after observing current data."""
    declared = context.get("frozen_targets", {})
    result = {"baseline": baseline["name"], "profile": current["name"], "status": "UNMEASURED_OR_UNMATCHED",
        "declared": declared, "database_transactions_by_path": [],
        "baseline_runtime_identity": runtime_revision_identity(baseline),
        "profile_runtime_identity": runtime_revision_identity(current),
        "scope": "Successful database transaction count per identical fixed external workload, individually for same/cross/mixed. Repeat-median changes and all paired repeats retained; worker task count is separate. No restriction of the original generic workload goal to same-server cases.",
        "idle_transactions": "UNMEASURED by this FE driver; separate loaded-endpoint OFF measurement required",
        "integrity": "Native recovery/lifecycle/fault tests are separate evidence, not established by this FE latency report alone"}
    if not profile_complete_for_targets(baseline) or not profile_complete_for_targets(current):
        result["reason"] = "Failed, incomplete or unfinalized profile outcomes cannot be elevated by runtime identity metadata"
        return result
    if (comparison.get("status") != "matched" or not declared or not context.get("head") or
            result["baseline_runtime_identity"]["revision"] != context.get("head")):
        return result
    target = declared.get("transactions_per_fixed_external_workload_reduction_percent")
    if not finite(target):
        return result
    result["status"] = "MATCHED_DESCRIPTIVE_EVALUATION"
    for name in ("same", "cross", "mixed"):
        old, new = baseline["cases"].get(name), current["cases"].get(name)
        if not old or not new:
            result["database_transactions_by_path"].append({"scenario": name, "status": "UNMEASURED"})
            continue
        before, after = old["steady"]["db_transactions"]["median"], new["steady"]["db_transactions"]["median"]
        reductions = {}
        by_repeat = {s["repeat"]: s for s in new["repeats"]}
        for sample in old["repeats"]:
            matched = by_repeat.get(sample["repeat"])
            original = sample["cost_counters"]["db_transactions"]
            now = matched["cost_counters"]["db_transactions"] if matched else None
            reductions[sample["repeat"]] = (1 - now / original) * 100 if original and now is not None else None
        reduction = (1 - after / before) * 100 if before and after is not None else None
        result["database_transactions_by_path"].append({"scenario": name, "target_reduction_percent": target,
            "baseline_repeat_median": before, "current_repeat_median": after, "reduction_percent": reduction,
            "repeat_median_goal_met": reduction >= target if reduction is not None else None,
            "paired_repeat_reduction_percents": reductions,
            "all_paired_repeats_meet_goal": all(value is not None and value >= target for value in reductions.values())})
    result["all_three_path_repeat_medians_meet_DB_goal"] = len(result["database_transactions_by_path"]) == 3 and all(
        row.get("repeat_median_goal_met") is True for row in result["database_transactions_by_path"])
    for scenario, target_key, mode in (("same", "same_server_low_flow_p95_reduction_percent", "reduction"),
            ("cross", "cross_server_p95_max_regression_percent", "regression")):
        old, new = baseline["cases"].get(scenario), current["cases"].get(scenario)
        if old and new and finite(declared.get(target_key)):
            before = old["low_flow"]["full_output_upper_ms"]["repeat_percentile_medians"]["p95"]
            after = new["low_flow"]["full_output_upper_ms"]["repeat_percentile_medians"]["p95"]
            change = (after / before - 1) * 100 if before and after is not None else None
            result[target_key] = {"declared_target_percent": declared[target_key], "observed_change_percent": change,
                "goal_met": ((-change >= declared[target_key]) if mode == "reduction" else (change <= declared[target_key])) if change is not None else None,
                "scope": "Median of the three per-repeat low-flow full-output upper-bound p95 values; descriptive result, not a confidence interval"}
    return result


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


def sequence_self_test(report):
    # Local temporary archives only; no processes, sockets or backend calls.
    with tempfile.TemporaryDirectory(prefix="ct-comparison-sequence-") as directory:
        root = Path(directory)
        archive = root / "reports"
        archive.mkdir()
        child_path, parent_path = archive / "driver.json", archive / "sequence.json"
        workspace_revision, loaded_revision = "b" * 40, "a" * 40
        driver = {**deepcopy(report), "schema_version": 1, "passed": True,
            "git_head": workspace_revision, "failures": [], "regressions": [], "other_live_backend_sessions": []}

        def archive_pair(body=driver):
            child_path.write_text(json.dumps(body))
            parent = {"passed": True, "procedure_completed": True, "utc_end": "2026-10-06T15:48:17Z",
                "loaded_source_revision_declared": loaded_revision,
                "runs": [{"report": "reports/driver.json", "loaded_source_revision_declared": loaded_revision,
                    "report_sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}]}
            parent_path.write_text(json.dumps(parent))
            return parent

        parent = archive_pair()
        profile = aggregate_report("baseline", child_path)
        current = aggregate_report("fast", child_path)
        context = {"head": loaded_revision,
            "frozen_targets": {"transactions_per_fixed_external_workload_reduction_percent": 30}}
        comparison = comparisons(profile, current, 10)
        assert frozen_targets(profile, current, context, comparison)["status"] == "UNMEASURED_OR_UNMATCHED"
        original_outcome = deepcopy({key: profile[key] for key in ("status", "cases", "report_passed", "git_head", "failures")})
        bind_sequence_evidence(profile, child_path, parent_path, root)
        assert profile["declared_runtime_revision"] == loaded_revision
        assert all(profile[key] == value for key, value in original_outcome.items())
        assert profile["git_head"] == workspace_revision
        assessed = frozen_targets(profile, current, context, comparison)
        assert assessed["status"] == "MATCHED_DESCRIPTIVE_EVALUATION"
        assert assessed["baseline_runtime_identity"]["revision"] == loaded_revision
        assert assessed["baseline_runtime_identity"]["raw_workspace_git_head"] == workspace_revision
        assert "not classloader attestation" in profile["runtime_revision_evidence"]["scope"]
        legacy = deepcopy(parent)
        del legacy["procedure_completed"]
        parent_path.write_text(json.dumps(legacy))
        legacy_profile = aggregate_report("baseline", child_path)
        bind_sequence_evidence(legacy_profile, child_path, parent_path, root)
        assert "legacy schema" in legacy_profile["runtime_revision_evidence"]["sequence"]["completion_policy"]

        def rejected(body):
            parent_path.write_text(json.dumps(body))
            fresh = aggregate_report("baseline", child_path)
            try:
                bind_sequence_evidence(fresh, child_path, parent_path, root)
            except (OSError, ValueError):
                assert "declared_runtime_revision" not in fresh
            else:
                raise AssertionError("Invalid sequence evidence accepted")

        for change in ({"passed": False}, {"procedure_completed": False}, {"procedure_completed": None},
                {"utc_end": None}, {"utc_end": "2026-10-06T15:48:17"},
                {"loaded_source_revision_declared": "label-87bf217"}, {"runs": []}):
            rejected({**deepcopy(parent), **change})
        wrong_sha = deepcopy(parent)
        wrong_sha["runs"][0]["report_sha256"] = "0" * 64
        rejected(wrong_sha)
        duplicate = deepcopy(parent)
        duplicate["runs"].append({**duplicate["runs"][0], "report": "reports/./driver.json"})
        rejected(duplicate)
        different_revision = deepcopy(parent)
        different_revision["runs"][0]["loaded_source_revision_declared"] = workspace_revision
        rejected(different_revision)
        different_input = deepcopy(parent)
        other = archive / "other.json"
        other.write_text(child_path.read_text())
        different_input["runs"][0]["report"] = "reports/other.json"
        rejected(different_input)
        outside = root / "outside.json"
        outside.write_text(child_path.read_text())
        bad_path = deepcopy(parent)
        bad_path["runs"][0]["report"] = "outside.json"
        rejected(bad_path)
        alias = archive / "alias.json"
        alias.symlink_to(child_path)
        bad_path["runs"][0]["report"] = "reports/alias.json"
        rejected(bad_path)

        # A passed operator sequence identifies source; it cannot cure resource
        # errors, missing repeats or an explicitly failed/unfinalized driver.
        failed = {**deepcopy(driver), "passed": False, "failures": ["recorded functional failure"]}
        wrong_resource = deepcopy(driver)
        wrong_resource["samples"][1]["conservation"]["extracted_FE"] = 19
        incomplete = deepcopy(driver)
        incomplete["samples"].pop()
        unfinalized = {**deepcopy(driver), "passed": False}
        for invalid_driver, expected_status in ((failed, "failed"), (wrong_resource, "failed"),
                (incomplete, "incomplete"), (unfinalized, "complete_samples_not_finalized_or_not_passed")):
            archive_pair(invalid_driver)
            bad_profile = aggregate_report("baseline", child_path)
            before = deepcopy(bad_profile)
            bind_sequence_evidence(bad_profile, child_path, parent_path, root)
            assert bad_profile["status"] == expected_status
            assert all(bad_profile[key] == value for key, value in before.items())
            assert frozen_targets(bad_profile, current, context, comparisons(bad_profile, current, 10))["status"] == "UNMEASURED_OR_UNMATCHED"
            assert frozen_targets(profile, {**bad_profile, "name": "fast"}, context,
                comparisons(profile, {**bad_profile, "name": "fast"}, 10))["status"] == "UNMEASURED_OR_UNMATCHED"

        # Refuse to attach evidence to a different already-aggregated snapshot.
        archive_pair()
        stale = aggregate_report("baseline", child_path)
        archive_pair({**driver, "label": "changed after aggregation"})
        try:
            bind_sequence_evidence(stale, child_path, parent_path, root)
        except ValueError:
            assert "declared_runtime_revision" not in stale
        else:
            raise AssertionError("Changed profile snapshot accepted")
        parent_path.write_bytes(b" " * (MAX_SEQUENCE_BYTES + 1))
        try:
            bind_sequence_evidence(stale, child_path, parent_path, root)
        except ValueError:
            pass
        else:
            raise AssertionError("Unbounded sequence accepted")


def self_test():
    # Synthetic evidence and local temporary files; no socket/backend/process calls.
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
    assert complete["steady"]["wal_writes"]["status"] == "UNMEASURED"
    assert complete["steady"]["wal_writes"]["median"] is None
    instrumented = deepcopy(report)
    for sample in instrumented["samples"]:
        first, last = {}, {}
        for index, server in enumerate(SERVERS):
            fm = {key: 0 for key in COUNTERS}
            lm = {**fm, "db_transactions": 1, "transactions": 2, "wal_writes": 2,
                "wal_bytes": 100, "wal_identical_skipped": 0, "batch_devices": 4, "batch_records": 3,
                "db_statements": 5, "local_credit_publications": 2}
            fm.update({key: 0 for key in lm})
            fm.update({"wal_barrier_ms_p50": 1, "wal_barrier_ms_p95": 2, "wal_barrier_ms_p99": 3, "wal_barrier_ms_samples": 2048})
            lm.update({"wal_barrier_ms_p50": 2, "wal_barrier_ms_p95": 3, "wal_barrier_ms_p99": 4, "wal_barrier_ms_samples": 2048})
            first[server] = {"start": index * .001, "end": (index + 1) * .001, "metrics": fm}
            last[server] = {"start": 1 + index * .001, "end": 1 + (index + 1) * .001, "metrics": lm}
        sample.update(counter_start={"servers": first}, counter_end={"servers": last})
    current = aggregate_case(instrumented, "same")
    assert current["status"] == "complete"
    assert current["steady"]["wal_writes"]["median"] == 6
    assert current["steady"]["transactions"]["median"] == 6
    assert current["steady"]["db_statements"]["median"] == 15
    assert current["repeats"][0]["WAL_barrier_snapshots"]["per_server"]["A"]["end"]["samples"] == 2048
    a = {"name": "baseline", "status": "passed", "conditions": report["conditions"], "cases": {"same": complete}, "other_live_backend_sessions": []}
    b = {**a, "name": "batch", "cases": {"same": current}}
    optional = [x for x in comparisons(a, b, 10)["metrics"] if x["metric"] == "steady_wal_writes_fixed_input_count"][0]
    assert optional["measurement_status"] == "UNMEASURED" and optional["change_percent"] is None
    ring = [x for x in comparisons(b, {**b, "name": "fast"}, 10)["metrics"] if x["metric"] == "WAL_barrier_end_ring_snapshot_ms_p95"]
    assert len(ring) == 3 and all(x["measurement_status"] == "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC" and not x["regression"] for x in ring)
    broken = deepcopy(instrumented)
    broken["samples"][0]["counter_end"]["servers"]["A"]["metrics"]["wal_writes"] = -1
    assert aggregate_case(broken, "same")["status"] == "failed"
    unknown = deepcopy(instrumented["samples"][0])
    del unknown["counter_end"]["servers"]["B"]["metrics"]["wal_bytes"]
    assert snapshot_counters(unknown)["summed_cumulative_delta"]["wal_bytes"] is None
    assert barrier_snapshots({})["per_server"]["A"]["end"]["status"] == "UNMEASURED"
    goal = frozen_targets({**a, "git_head": "original"}, b,
        {"head": "original", "frozen_targets": {"transactions_per_fixed_external_workload_reduction_percent": 30}}, comparisons(a, b, 10))
    assert goal["database_transactions_by_path"][0]["reduction_percent"] == 0
    assert not goal["database_transactions_by_path"][0]["repeat_median_goal_met"]
    assert not goal["all_three_path_repeat_medians_meet_DB_goal"]  # No narrowing to measured same-only workload.
    sequence_self_test(report)
    print("Offline comparison checks passed; no backend/process contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--fast", type=Path)
    parser.add_argument("--report", action="append", default=[], metavar="NAME=PATH", help="Additional named driver report")
    parser.add_argument("--sequence", action="append", default=[], metavar="PROFILE=PATH",
        help="Explicit completed orchestrator in reports/ for a supplied profile; verifies unique child path/SHA and operator-declared runtime revision, not classloader attestation")
    parser.add_argument("--target-context", type=Path, help="Original frozen baseline context JSON; report per-path target results without replacing missing evidence")
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
    sequences = {}
    for item in args.sequence:
        if "=" not in item:
            parser.error("--sequence needs PROFILE=PATH")
        name, path = item.split("=", 1)
        if name not in paths or paths[name] is None or name in sequences or not path:
            parser.error("Sequence profile must name one supplied input, once, with a nonempty path")
        sequences[name] = Path(path)
    if not any(paths.values()):
        parser.error("Supply at least one driver report")
    if not 0 <= args.max_regression_percent <= 100:
        parser.error("Regression percent outside 0..100")
    aggregate = {"schema_version": 1, "report_kind": "offline_optimization_comparison",
        "utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "scope": {
            "latency": "Actual capability accept -> actual capability pull; lower/upper RCON bounds, not world-save latency",
            "RCON_reply_attribution": "MC 1.21.1 DedicatedServer shares one RconConsoleSource output buffer across clients; concurrent commands can cross-contaminate payloads while returning the correct protocol request ID. Prefix, fixed-input and conservation checks retained; the original driver does not preserve complete raw business replies or request-specific body tags.",
            "percentiles": "Every repeat retained; aggregate is median of repeat percentiles, not pooled p95",
            "business": "Fixed source attempts/rounds; all acceptance and output ledger checks retained",
            "SQL": "ct_dev account statement/sql events; root observer excluded; other-live-session caveat retained",
            "instrumented_counters": "Actual first/final per-server status snapshots supply worker task, batch, Sql-helper and WAL differences. Absent counters are UNMEASURED. local_credit_publications includes cross delivery, so topology/event ledgers must establish source path.",
            "WAL_barriers": "Per-server ring percentile snapshots are diagnostic and not phase-wide latency. No subtraction or pooling of JVM percentiles; baseline WAL absent.",
            "conservation": "Latest cumulative per reused channel, not sum of repeat cumulative figures; SQL/WAL/local copies never added",
            "topology": "Overworld console fixtures may share one chunk. NeighborPump skips neighboring Tesseracts. Different chunks/dimensions/real chests require separate correctness tests.",
            "runtime_identity": "An explicit --sequence can bind a completed orchestrator's operator-declared revision to an exact profile child path/SHA. It is not classloader attestation, never overwrites raw git_head, and cannot upgrade functional/resource outcomes. Without it, frozen targets retain the git_head fallback rule.",
            "unmeasured": "No fabricated absent runs, failed-run performance success, phase-wide WAL timing, uncollected early-repeat MC tick means or actual TPS"},
        "profiles": {name: aggregate_report(name, path) for name, path in paths.items()}}
    for name, sequence_path in sequences.items():
        try:
            bind_sequence_evidence(aggregate["profiles"][name], paths[name], sequence_path)
        except (OSError, ValueError, TypeError) as error:
            parser.error("Invalid --sequence for " + name + ": " + str(error))
    profiles = list(aggregate["profiles"].values())
    aggregate["comparisons"] = [comparisons(before, after, args.max_regression_percent)
        for index, before in enumerate(profiles) for after in profiles[index + 1:]]
    if args.target_context:
        raw_context = args.target_context.read_bytes()
        context = json.loads(raw_context)
        aggregate["frozen_target_context"] = {"path": str(args.target_context.resolve()),
            "sha256": hashlib.sha256(raw_context).hexdigest(), "context": context}
        aggregate["frozen_target_assessments"] = [frozen_targets(aggregate["profiles"]["baseline"], current, context, comparison)
            for current, comparison in ((aggregate["profiles"][c["profile"]], c) for c in aggregate["comparisons"]
                if c["baseline"] == "baseline")]
    rows = table_rows(aggregate)
    input_paths = {path.resolve() for path in paths.values() if path is not None}
    for profile in aggregate["profiles"].values():
        evidence = profile.get("runtime_revision_evidence")
        if evidence:
            input_paths.add(Path(evidence["sequence"]["path"]))
            input_paths.update(Path(path) for path in evidence["referenced_child_paths"])
    if args.target_context:
        input_paths.add(args.target_context.resolve())
    if any(path.resolve() in input_paths for path in (args.output, args.csv) if path is not None):
        parser.error("Comparison output cannot overwrite an input report")
    if args.output and args.csv and args.output.resolve() == args.csv.resolve():
        parser.error("JSON and CSV outputs must have distinct paths")
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
