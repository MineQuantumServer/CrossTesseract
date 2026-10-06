#!/usr/bin/env python3
"""Offline original87/batch68/fast68 resource-mix derivation from a finished sequence.

Run from any cwd:
  python3 /workspace/scripts/analysis/compare-resource-mix-68f32db.py --self-test
  python3 scripts/analysis/compare-resource-mix-68f32db.py \
    --sequence reports/optimization-extra-sequence-68f32db.json

Only archived JSON files are read. No workload/helper imports, subprocesses,
RCON, SQL, JVM, /proc, JFR, config changes or raw-report writes. Self-test uses
synthetic in-memory structures and does not read sequence/child reports. Actual
derivation refuses an unfinished sequence, verifies exact child names/revisions
and byte SHA256, retains failed child evidence, and writes JSON/CSV/MD with a
nonzero exit for an incomplete/invalid comparison. Existing outputs are refused.
"""
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
CORE = "68f32db439f445b8f72faf92dc62fbc5b9dce738"
OLD = "87bf217fcaffcceb2629c36bb54d5158b9f461e8"
PROFILES = {"original87": (OLD, "legacy", ("false", "false")),
    "batch68": (CORE, "batch", ("true", "false")),
    "fast68": (CORE, "fast", ("true", "true"))}
RESOURCES = {"FE": "FE", "water": "mB", "item_A": "items", "item_B": "items"}
KINDS = {"FE": "cross_tesseract:fe", "water": "cross_tesseract:fluid",
    "item_A": "cross_tesseract:item", "item_B": "cross_tesseract:item"}
VARIANTS = {"A": "CT mixed A", "B": "CT mixed B"}
COUNTERS = ("db_transactions", "db_deadlock_retries", "transactions", "errors",
    "queue_rejected", "quarantined", "db_transaction_attempts", "db_statements",
    "deferred_registry_decodes", "dropped_wake_hints", "local_exchange_calls",
    "local_input_units", "local_output_units", "batch_devices", "batch_records",
    "batch_payload_bytes", "local_wakes", "remote_hint_wakes", "poll_fallback",
    "empty_batches", "allocation_misses", "local_credit_publications", "wal_writes",
    "wal_bytes", "wal_identical_skipped")
UNMEASURED = "UNMEASURED"
LIMITS = {
    "scope": "Supplemental one-channel mixed A SEND -> A/B RECEIVE, simultaneous FE/water/two stable CUSTOM_NAME stone variants. Given fixed requests; not peak capacity, factory scale or TPS.",
    "frozen_primary_targets": "NOT_APPLICABLE. The primary per-path30% DB window goal and its latency goals are neither retargeted nor assessed by this supplement. No supplement-specific frozen performance goal exists.",
    "actual_inputs": "240 FE requests and240 water requests per observation, plus one32+32 stone pair. Matching attempts/request amounts do not prove equal actual FE/water inputs. Partial rejections and each variant are independent ledgers; different units never summed.",
    "output": "Within-window actual capability/chest outputs and separate tail outputs retained. Tail delivery is not120s throughput. Native FE/fluid have overlapped aggregate identities; no per-input E2E claim.",
    "ITEM_identity": "minecraft:stone with exactly stable CUSTOM_NAME CT mixed A / CT mixed B in source slots0/1. One batch in flight per window, no refeeding or per-event trace component. ITEM source wait remains visible even if120s output is0.",
    "counter_windows": "Fixed counter_start->counter_end encloses the observed steady drive and captures, before final drain. Steady+tail counter_start->counter_after_drain is this steady input/drain lifecycle, including final drain/quiet guard but excluding setup, warmup and cleanup. Warmup+its drain separate. These scopes overlap and must not be added; snapshot capture spans are retained.",
    "SQL": "Actual ct_test cumulative DB transactions acrossABC; account statement events include ct_dev SQL attempts/retries. SUM_TIMER_WAIT is summed statement elapsed/wait time, not CPU, whole phase wall time or a query percentile. Observer root SELECTs are not ct_dev statements.",
    "optional_counters": "Absent native worker/batch/WAL counters remain UNMEASURED, never0. Native transactions is a worker-task diagnostic, not SQL transactions. local_credit_publications includes cross delivery; mixed local_input/output_units are not external business totals.",
    "WAL_barriers": "Only writes/bytes/identical-skipped cumulative fields are present in the frozen resource-mix delta schema. Capped wal_barrier_ms_samples/end-ring percentiles do not reveal total barrier events. Barrier count and whole-window barrier percentiles UNMEASURED.",
    "assets": "Actual accepted input = actual external output after successful drain for each resource/variant. SQL remaining/local/WAL copies are mirrors, not additional assets. Zero source/target/local/SQL tests are checked separately.",
    "clock": "One observer time.monotonic() request/reply/read spans. Conservative ITEM input->source, source->first/full and input->first/full bounds include source/target observation widths, sequential reads, polling and RCON delay. No cross-JVM nanoTime subtraction; NotWorldSave.",
    "observer": "Single RCON observer, raw source reply bodies retained in linked reports. Shared console bodies have no business nonce despite protocol request IDs. No retrospective exact body-attribution proof. Observer elapsed spans include waiting, not CPU; lateness/actual phase seconds retained.",
    "fairness": "Every intended recipient has explicit per-resource and per-component service, including zeros, first/last output observations and phase-edge maximum observed output gap. No requirement that every variant reaches every recipient in every single batch; aggregate named-stone/FE/water service across all repeats is tested.",
    "provenance": "Operator/runtime revision and git HEAD are separate archived labels. PID/world/session/epoch plus archived launch-selected class/resource manifests and successful driver end rehash are retained; this script does not reread live launch files or establish class-loader CodeSource.",
    "statistics": "All three repeats retained. Repeat medians and >10% descriptive regressions are summaries, not confidence intervals, tail guarantees or acceptance targets. Zero baseline cannot produce a meaningful percentage; new positive cost is flagged separately.",
    "CSV": "One row per profile/repeat/resource. Phase-wide costs are repeated for convenient reading and cannot be summed across resource rows or attributed to one resource. JSON stores each repeat cost once.",
    "derivation": "Archived JSON/static script only; no online calls, backend mutation, process/JVM observation or JFR parsing."}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate archived JSON key: " + key)
        result[key] = value
    return result


def bad_constant(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def archived_path(value, suffix=".json"):
    """ROOT relative paths only, under the actual reports directory; no symlinks."""
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(ROOT)
        except ValueError as error:
            raise ValueError("Expected a ROOT reports path") from error
    if not candidate.parts or candidate.parts[0] != "reports" or ".." in candidate.parts or candidate.suffix != suffix:
        raise ValueError("Expected a bounded ROOT-relative reports file: " + str(value))
    result = ROOT / candidate
    if any(part.is_symlink() for part in (result, *result.parents) if part != ROOT.parent):
        raise ValueError("Archived evidence/output must not traverse symlinks")
    if not result.resolve().is_relative_to((ROOT / "reports").resolve()):
        raise ValueError("Archived path escapes reports")
    return result


def read_saved(path, maximum=512 * 1024 * 1024):
    if not path.is_file() or not 2 <= path.stat().st_size <= maximum:
        raise ValueError("Missing/oversized archived JSON: " + str(path))
    data = path.read_bytes()
    if len(data) > maximum:
        raise ValueError("Archived file grew beyond bound")
    saved = json.loads(data, object_pairs_hook=strict_object, parse_constant=bad_constant)
    if not isinstance(saved, dict):
        raise ValueError("Archived report must be a JSON object")
    return saved, {"path": str(path), "repo_relative_path": path.relative_to(ROOT).as_posix(),
        "sha256": digest(data), "size_bytes": len(data)}


def file_digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(part)
    return result.hexdigest()


def integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError("Expected exact nonnegative integer: " + name)
    return value


def number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Expected finite observation number: " + name)
    return value


def interval(point, name):
    start, end = number(point["start"], name + ".start"), number(point["end"], name + ".end")
    if start < 0 or end < start:
        raise ValueError("Invalid observer interval: " + name)
    return {"start": start, "end": end, "span_seconds": end - start}


def bounds(a, b):
    a, b = interval(a, "source"), interval(b, "target")
    return {"lower_ms": max(0.0, (b["start"] - a["end"]) * 1000),
        "upper_ms": max(0.0, (b["end"] - a["start"]) * 1000),
        "source_observation_span_ms": a["span_seconds"] * 1000,
        "target_observation_span_ms": b["span_seconds"] * 1000}


def option(command, key):
    if not isinstance(command, list) or not all(isinstance(v, str) for v in command) or command.count(key) != 1:
        raise ValueError("Requires one exact sequence command option: " + key)
    i = command.index(key)
    if i + 1 == len(command) or command[i + 1].startswith("--"):
        raise ValueError("Missing sequence option value: " + key)
    return command[i + 1]


def select_runs(sequence):
    if not sequence.get("utc_end") or sequence.get("state") not in ("completed", "failed"):
        raise ValueError("Sequence is unfinished; no partial files are analysed or outputs generated")
    runs = sequence.get("runs")
    if not isinstance(runs, list) or any("exit_code" not in r or not r.get("utc_end") for r in runs):
        raise ValueError("Sequence still has unfinished child entries")
    selected = {}
    for profile, (revision, mode, _) in PROFILES.items():
        matches = [r for r in runs if isinstance(r.get("command"), list)
            and len(r["command"]) >= 2 and Path(r["command"][1]).name == "optimization-resource-mix.py"
            and r["command"].count("--label") == 1 and option(r["command"], "--label") == profile]
        if len(matches) > 1:
            raise ValueError("Ambiguous exact resource-mix child label: " + profile)
        if not matches:
            selected[profile] = None  # A failed finished sequence may have never started later children.
            continue
        run = matches[0]
        command = run["command"]
        if "--execute" not in command or run.get("smoke_not_performance") is not False or run.get("mode") != mode or \
                run.get("runtime_revision") != revision or option(command, "--operator-revision") != revision:
            raise ValueError("Resource-mix child has different mode/revision/smoke classification: " + profile)
        for key, value in (("--scenarios", "mixed"), ("--warmup", "30"), ("--seconds", "120"), ("--repeats", "3"), ("--timeout", "1200")):
            if option(command, key) != value:
                raise ValueError("Different requested resource-mix protocol: " + profile + "/" + key)
        selected[profile] = run
    return selected


def counter_scope(first, last, saved=None):
    per_server, sums, status = {}, {}, {}
    if set(first["servers"]) != {"A", "B", "C"} or set(last["servers"]) != {"A", "B", "C"}:
        raise ValueError("Counter snapshots require exactly ABC")
    for server in ("A", "B", "C"):
        a, b = first["servers"][server]["metrics"], last["servers"][server]["metrics"]
        per_server[server] = {}
        for key in COUNTERS:
            value = None
            if key in a and key in b:
                value = integer(b[key], key) - integer(a[key], key)
                if value < 0:
                    raise ValueError("Cumulative native counter reset: " + server + "/" + key)
            per_server[server][key] = value
        for required in ("db_transactions", "transactions", "errors", "queue_rejected", "quarantined"):
            if per_server[server][required] is None:
                raise ValueError("Missing required native counter: " + server + "/" + required)
    for key in COUNTERS:
        values = [v[key] for v in per_server.values()]
        sums[key] = sum(values) if all(v is not None for v in values) else None
        status[key] = "MEASURED" if sums[key] is not None else UNMEASURED
    statements = None
    if first.get("statements") is not None and last.get("statements") is not None:
        statements = {key: integer(last["statements"][key], key) - integer(first["statements"][key], key)
            for key in ("events", "timer_picoseconds", "errors")}
        if any(v < 0 for v in statements.values()):
            raise ValueError("Cumulative ct_dev statement account reset")
    if saved is not None:
        if saved.get("sum") != sums or saved.get("per_server") != per_server or saved.get("account_statement_events") != statements:
            raise ValueError("Archived counter delta differs from exact captured snapshots")
    captures = {"first": interval(first, "first_capture"), "last": interval(last, "last_capture"),
        "per_server": {server: {"first": interval(first["servers"][server], server + " first"),
            "last": interval(last["servers"][server], server + " last")} for server in per_server},
        "first_statement_observer_end": (first.get("statements") or {}).get("observer_end"),
        "last_statement_observer_end": (last.get("statements") or {}).get("observer_end")}
    return {"sum": sums, "per_server": per_server, "measurement_status": status,
        "account_statement_events": statements,
        "account_statement_measurement_status": "MEASURED" if statements is not None else UNMEASURED,
        "SQL_statement_timer_wait_sum_seconds": statements["timer_picoseconds"] / 1e12 if statements is not None else None,
        "capture_observation_intervals": captures,
        "captured_native_end_snapshots": {s: last["servers"][s]["metrics"] for s in per_server},
        "wal_barrier_event_count": None, "wal_barrier_event_count_status": UNMEASURED,
        "scope": "Native/account cumulative snapshot differences. End timer rings/avg100 have unknown window coverage and are not phase-wide metrics; snapshot spans are observer evidence, not atomic same-time state."}


def events_ledger(events, key):
    """Unknown mutation results are retained, not replaced by accepted=0."""
    inputs, outputs, source = [], [], []
    for event in events:
        if event.get("resource") != key:
            continue
        if event.get("kind") == "input":
            inputs.append(event)
        elif event.get("kind") == "output":
            outputs.append(event)
        elif event.get("kind") == "source_chest_decrement":
            source.append(event)
    unknown = [e for e in inputs + outputs + source if type(e.get("amount")) is not int]
    known_inputs = [e for e in inputs if type(e.get("amount")) is int]
    for event in inputs + outputs + source:
        if type(event.get("amount")) is int:
            integer(event["amount"], "event.amount")
            if event["kind"] == "input" and event["amount"] > integer(event.get("requested"), "event.requested"):
                raise ValueError("Actual acceptance exceeds the one input request")
    def amounts(selected):
        return sum(e["amount"] for e in selected) if not any(type(e.get("amount")) is not int for e in selected) else None
    def by_endpoint(selected):
        result = {}
        for event in selected:
            name = event["endpoint"]
            if name not in result:
                result[name] = 0
            result[name] = result[name] + event["amount"] if result[name] is not None and type(event.get("amount")) is int else None
        return result
    requested = sum(integer(e["requested"], "requested") for e in inputs)
    return {"unit": RESOURCES[key], "input_attempts": len(inputs), "requested": requested,
        "accepted": amounts(inputs), "rejected_units": requested - amounts(inputs) if amounts(inputs) is not None else None,
        "fully_accepted_attempts": sum(e["amount"] == e["requested"] for e in known_inputs),
        "partial_or_zero_acceptance_attempts": sum(e["amount"] != e["requested"] for e in known_inputs),
        "known_accepted_subtotal": sum(e["amount"] for e in known_inputs),
        "external_output": amounts(outputs),
        "source_actual_decrement": amounts(source) if key.startswith("item_") else None,
        "input_by_endpoint": by_endpoint(inputs), "output_by_endpoint": by_endpoint(outputs),
        "unknown_events_verbatim": unknown, "complete_event_amounts": not unknown}


def check_ledger(saved, computed, purpose):
    for key in ("accepted", "external_output", "source_actual_decrement"):
        if saved.get(key) != computed[key]:
            raise ValueError("Archived " + purpose + " business ledger differs from actual events: " + key)
    for key in ("input_by_endpoint", "output_by_endpoint"):
        a, b = saved.get(key, {}), computed[key]
        if any(a.get(name, 0) != b.get(name, 0) for name in a.keys() | b.keys()):
            raise ValueError("Archived " + purpose + " endpoint ledger differs from actual events")


def zero_guard(guard):
    if guard.get("passed") is not True or number(guard.get("quiet_seconds"), "quiet") < 2.2:
        raise ValueError("Missing completed2.2s physical/local/SQL drain guard")
    snapshots = guard.get("snapshots", [])
    if not snapshots:
        raise ValueError("Drain guard has no actual observations")
    for point in snapshots:
        frame, residue = point["frame"], point["residue"]
        empty = frame["source"]["count"] == 0 and not any(frame["totals"].values())
        empty = empty and all(p["count"] == 0 for p in frame["targets"].values())
        empty = empty and all(residue["by_kind"][kind][field] == 0 for kind in set(KINDS.values())
            for field in ("pool", "allocation_remaining"))
        empty = empty and all(p.get("registered") is True and not p.get("pause") and all(p.get(k) == 0
            for k in ("txFE", "rxFE", "txItem", "rxItem", "txFluid", "rxFluid")) for p in residue["local_buffers"].values())
        if not residue["local_buffers"] or point.get("empty") is not empty:
            raise ValueError("Drain guard zero marker differs from actual independent zeros")
    if not snapshots[-1]["empty"]:
        raise ValueError("Final guarded observation is not actually empty")
    contiguous = []
    for point in reversed(snapshots):
        if not point["empty"]:
            break
        contiguous.append(number(point["at"], "guard.at"))
    if contiguous[0] - contiguous[-1] + 1e-6 < guard["quiet_seconds"]:
        raise ValueError("Drain quiet duration not supported by sampled observations")
    return {"passed": True, "quiet_seconds": guard["quiet_seconds"], "snapshots": len(snapshots),
        "observer_interval": interval(guard, "guard"), "final_independent_zero_observation": snapshots[-1],
        "scope": "Repeated zero observations over the guard; SQL/local/WAL copies are not asset totals or an atomic cross-server snapshot."}


def recipient_service(events, endpoints, key, start, end):
    result = {}
    for endpoint in endpoints:
        selected = [e for e in events if e.get("kind") == "output" and e.get("resource") == key and e.get("endpoint") == endpoint]
        unknown = [e for e in selected if type(e.get("amount")) is not int]
        positive = [e for e in selected if type(e.get("amount")) is int and e["amount"] > 0]
        observations = sorted((interval(e, "output") for e in positive), key=lambda e: e["end"])
        ends = [start] + [p["end"] for p in observations] + [end]
        gaps = [max(0, b - a) for a, b in zip(ends, ends[1:])]
        result[endpoint] = {"external_output": sum(e["amount"] for e in selected) if not unknown else None,
            "successful_output_observations": len(positive), "read_or_pull_observations": len(selected),
            "first_positive_observation": observations[0] if observations else None,
            "last_positive_observation": observations[-1] if observations else None,
            "maximum_observed_output_gap_seconds_including_phase_edges": max(gaps, default=end - start) if not unknown else None,
            "unknown_events_verbatim": unknown,
            "scope": "Positive reply/read-end gaps include phase edges and deliberate no-output periods; observational service gaps, not eligible-demand starvation proof or per-input latency."}
    return result


def item_timing(batch, variant):
    record = batch["variants"][variant]
    result = {"variant": variant, "item_id": "minecraft:stone", "CUSTOM_NAME": VARIANTS[variant],
        "batch_sequence": batch["sequence"], "batch_passed": batch.get("passed") is True,
        "batch_completed_observer_seconds": batch.get("completed"), "item_quiet_seconds": batch.get("item_quiet_seconds"),
        "injection": record.get("injection"), "source_first_decrement": record.get("source_first_decrement"),
        "source_empty_interval": record.get("source_empty_interval"), "first_output": record.get("first_output"),
        "full_output": record.get("full_output"), "outputs_by_sink": record.get("outputs_by_sink"),
        "conservative_bounds": {}, "clears_verbatim": batch.get("clears", []),
        "source_observation_count": len(batch.get("source_observations", [])),
        "physical_frame_count": len(batch.get("frames", [])), "item_quiet_check_count": len(batch.get("item_quiet_checks", []))}
    for name, a, b in (("input_to_source", "injection", "source_first_decrement"),
            ("input_to_first_output", "injection", "first_output"), ("input_to_full_output", "injection", "full_output"),
            ("source_to_first_output", "source_first_decrement", "first_output"),
            ("source_to_full_output", "source_first_decrement", "full_output")):
        if a not in record or b not in record:
            result["conservative_bounds"][name] = None
            continue
        actual = bounds(record[a], record[b])
        saved = record.get(name + "_bounds")
        if saved is None or any(not math.isclose(number(saved.get(key), key), value, rel_tol=1e-9, abs_tol=1e-6) for key, value in actual.items()):
            raise ValueError("ITEM archived interval bounds differ from their actual observation intervals: " + name)
        result["conservative_bounds"][name] = actual
    if batch.get("passed") is True:
        if result["item_quiet_seconds"] < 2.2 or any(value is None for value in result["conservative_bounds"].values()) or \
                sum(integer(v, "ITEM output") for v in result["outputs_by_sink"].values()) != 32 or not result["source_empty_interval"]:
            raise ValueError("Completed ITEM variant lacks32 actual outputs, source drain or bounds")
        if any(clear.get("result") != "CONFIRMED_CLEAR" for clear in batch.get("clears", [])):
            raise ValueError("Completed batch contains an uncertain destination clear")
        if sum(integer(c.get("confirmed_by_variant", {}).get(variant, 0), "cleared component") for c in batch.get("clears", [])) != 32:
            raise ValueError("Completed component output was not actually confirmed/cleared exactly32")
        checks = batch.get("item_quiet_checks", [])
        if not checks or checks[-1].get("zero") is not True:
            raise ValueError("Completed ITEM batch lacks actual static zero guard evidence")
        last = checks[-1]
        state = last["residue"]["by_kind"]["cross_tesseract:item"]
        if state["pool"] != 0 or state["allocation_remaining"] != 0 or \
                any(p.get("txItem") != 0 or p.get("rxItem") != 0 for p in last["residue"]["local_buffers"].values()) or \
                last["physical_frame"]["source"]["count"] != 0 or last["physical_frame"]["totals"] != {"A": 32, "B": 32}:
            raise ValueError("Actual ITEM guard does not support independent source/local/SQL zeros and64 external items")
        result["last_item_independent_zero_check_verbatim"] = last
    return result


def sample_summary(raw, sample, source_index, validate=True):
    repeat, scenario = sample.get("repeat"), sample.get("scenario")
    result = {"scenario": scenario, "repeat": repeat, "raw_sample_index": source_index,
        "raw_passed": sample.get("passed") is True, "validation_errors": [],
        "resources": {}, "costs": {}, "ITEM_variants": {}, "recovered_SQL_failures_verbatim": sample.get("recovered_SQL_failures")}
    steady, tail = sample.get("steady", {}), sample.get("conservation", {})
    fixture = next(iter(raw.get("fixtures", {}).get(scenario, [])), {})
    endpoints = [point["name"] for point in fixture.get("sinks", [])]
    result["fixture_verbatim"] = fixture
    result["steady_observer"] = {key: steady.get(key) for key in ("start", "end", "requested_seconds", "planned_rounds", "scheduled_rounds",
        "polls", "late_rounds", "observer_saturated", "observer_cost", "item_injection_entry")}
    result["tail_observer"] = {"start": tail.get("start"), "end": tail.get("end"), "passed": tail.get("passed"),
        "scope": "Post-observation drain through guarded empty state, independent of120s throughput."}
    result["warmup_observer"] = {key: sample.get("warmup", {}).get(key) for key in
        ("start", "end", "requested_seconds", "scheduled_rounds", "late_rounds", "observer_saturated", "observer_cost")}
    events = steady.get("events", []) + tail.get("events", [])
    for key, unit in RESOURCES.items():
        within = events_ledger(steady.get("events", []), key)
        drain = events_ledger(tail.get("events", []), key)
        combined = events_ledger(events, key)
        for phase, ledger in ((steady, within), (tail, drain)):
            ledger["phase_record_present"] = bool(phase)
            if not phase:
                for field in ("accepted", "rejected_units", "external_output", "source_actual_decrement"):
                    ledger[field] = None
                ledger["complete_event_amounts"] = False
        if key.startswith("item_"):
            uncertain = [attempt for attempt in steady.get("item_attempts", [])
                if attempt.get("variant") == key[-1] and attempt.get("accepted") is None]
            if uncertain:
                for ledger in (within, combined):
                    ledger["unknown_events_verbatim"].extend(uncertain)
                    ledger["input_attempts"] += len(uncertain)
                    ledger["requested"] += sum(integer(a["requested"], "uncertain ITEM requested") for a in uncertain)
                    ledger.update(accepted=None, rejected_units=None, complete_event_amounts=False)
                    for endpoint in fixture.get("sources", []):
                        ledger["input_by_endpoint"][endpoint["name"]] = None
        if not steady or not tail:
            combined["external_output"] = None
            combined["complete_event_amounts"] = False
        duration = (steady["end"] - steady["start"]) if "start" in steady and "end" in steady else None
        point = {"unit": unit, "steady": within, "tail": drain, "steady_plus_tail": combined,
            "actual_steady_external_output_per_second": within["external_output"] / duration
                if duration is not None and duration > 0 and within["external_output"] is not None else None,
            "conserved_after_drain": combined["accepted"] == combined["external_output"]
                if combined["complete_event_amounts"] else None,
            "recipient_service": {}}
        if key.startswith("item_") and combined["complete_event_amounts"]:
            point["conserved_after_drain"] = point["conserved_after_drain"] and combined["source_actual_decrement"] == combined["accepted"]
        if duration is not None and duration > 0:
            point["recipient_service"]["steady"] = recipient_service(steady.get("events", []), endpoints, key, steady["start"], steady["end"])
        if "start" in tail and "end" in tail:
            point["recipient_service"]["tail"] = recipient_service(tail.get("events", []), endpoints, key, tail["start"], tail["end"])
            point["recipient_service"]["steady_plus_tail"] = recipient_service(events, endpoints, key, steady.get("start", tail["start"]), tail["end"])
            result["tail_observer"]["actual_seconds"] = tail["end"] - tail["start"]
        result["resources"][key] = point
    for scope, first, last, provided in (("fixed_observation", "counter_start", "counter_end", "counter_delta"),
            ("steady_plus_tail", "counter_start", "counter_after_drain", "lifecycle_counter_delta"),
            ("warmup_plus_its_drain", "warmup_counter_start", "warmup_counter_end", "warmup_and_drain_counter_delta"),
            ("tail_only", "counter_end", "counter_after_drain", None)):
        if first in sample and last in sample:
            try:
                result["costs"][scope] = counter_scope(sample[first], sample[last], sample.get(provided) if provided else None)
            except (ValueError, KeyError, TypeError) as error:
                result["validation_errors"].append(scope + ": " + str(error))
        else:
            result["costs"][scope] = None
    selected_batches = [b for b in raw.get("item_batches", []) if b.get("lane") == fixture.get("name")
        and b.get("repeat") == repeat and b.get("phase") == "steady"]
    for batch in selected_batches:
        for variant in VARIANTS:
            try:
                timing = item_timing(batch, variant)
                if variant in result["ITEM_variants"]:
                    raise ValueError("Duplicate ITEM batch for the same window")
                result["ITEM_variants"][variant] = timing
            except (ValueError, KeyError, TypeError) as error:
                result["validation_errors"].append("ITEM " + variant + ": " + str(error))
    try:
        if validate:
            if scenario != "mixed" or type(repeat) is not int or repeat not in (1, 2, 3) or sample.get("passed") is not True:
                raise ValueError("Missing actual completed mixed repeat")
            if len(endpoints) != 2 or [point["server"] for point in fixture["sources"]] != ["A"] or \
                    [point["server"] for point in fixture["sinks"]] != ["A", "B"]:
                raise ValueError("Unexpected one-source/two-recipient mixed topology")
            if steady.get("planned_rounds") != 240 or steady.get("scheduled_rounds") != 240 or len(steady.get("rounds", [])) != 240:
                raise ValueError("Does not contain the fixed240 actual scheduled FE/water rounds")
            interval(steady, "steady")
            if steady["requested_seconds"] != 120 or steady["end"] <= steady["start"]:
                raise ValueError("Wrong requested observation/duration")
            for key in RESOURCES:
                within = result["resources"][key]["steady"]
                planned, amount = (1, 32) if key.startswith("item_") else (240, 32000 if key == "FE" else 1000)
                if not within["complete_event_amounts"] or within["input_attempts"] != planned or within["requested"] != planned * amount:
                    raise ValueError("Incomplete fixed requested input events: " + key)
                if any(e["requested"] != amount for e in steady["events"] if e.get("resource") == key and e.get("kind") == "input"):
                    raise ValueError("Changed per-attempt requested resource amount")
                if key.startswith("item_") and within["accepted"] != 32:
                    raise ValueError("ITEM variant does not have one actual accepted32 batch")
                if not result["resources"][key]["conserved_after_drain"] or result["resources"][key]["tail"]["input_attempts"]:
                    raise ValueError("Resource tail refeeding/failed exact external conservation: " + key)
                check_ledger(steady["ledger_change"][key], within, "steady " + key)
                check_ledger(sample["steady_and_tail_ledger_change"][key], result["resources"][key]["steady_plus_tail"], "steady+tail " + key)
                completeness = steady["input_completeness"][key]
                for source_key, computed_key in (("attempts", "input_attempts"), ("requested", "requested"),
                        ("actually_accepted", "accepted"), ("fully_accepted_attempts", "fully_accepted_attempts"),
                        ("partial_or_zero_acceptance_attempts", "partial_or_zero_acceptance_attempts")):
                    if completeness[source_key] != within[computed_key]:
                        raise ValueError("Input completeness differs from actual event ledger")
            for key in ("item_A", "item_B"):
                if events_ledger(sample["warmup"]["events"], key)["input_attempts"] != 0:
                    raise ValueError("ITEM was fed during warmup")
            if sample["warmup"]["requested_seconds"] != 30 or sample["warmup"]["scheduled_rounds"] != 60:
                raise ValueError("Wrong30s warmup protocol")
            result["tail_independent_zero_guard"] = zero_guard(tail["guard"])
            result["warmup_drain_independent_zero_guard"] = zero_guard(sample["warmup_drain"]["guard"])
            result["before_warmup_independent_zero_guard"] = zero_guard(sample["before_warmup"])
            if len(selected_batches) != 1 or not selected_batches[0].get("passed") or steady.get("item_batches") != [selected_batches[0]["sequence"]] or set(result["ITEM_variants"]) != set(VARIANTS):
                raise ValueError("Requires one completed finite ITEM pair with both component observation bounds")
            for variant in VARIANTS:
                given = result["ITEM_variants"][variant]["outputs_by_sink"]
                observed = result["resources"]["item_" + variant]["steady_plus_tail"]["output_by_endpoint"]
                if any(given.get(e, 0) != observed.get(e, 0) for e in given.keys() | observed.keys()):
                    raise ValueError("Component physical destination counts differ from independently accumulated output events")
            for scope in ("fixed_observation", "steady_plus_tail", "warmup_plus_its_drain", "tail_only"):
                cost = result["costs"].get(scope)
                if cost is None:
                    raise ValueError("Missing actual cost snapshots: " + scope)
                if any(cost["sum"][key] != 0 for key in ("errors", "queue_rejected", "quarantined")):
                    raise ValueError("Runtime error/rejection/quarantine retained in " + scope)
    except (ValueError, KeyError, TypeError) as error:
        result["validation_errors"].append(str(error))
    result["valid_complete_repeat"] = not result["validation_errors"] and result["raw_passed"] and validate
    return result


def missing_repeat(repeat, reason):
    return {"scenario": "mixed", "repeat": repeat, "raw_sample_index": None,
        "raw_passed": False, "valid_complete_repeat": False, "status": "NOT_RUN_OR_UNAVAILABLE",
        "validation_errors": [reason], "resources": {}, "costs": {}, "ITEM_variants": {}}


def profile_summary(name, raw, run, metadata):
    result = {"name": name, "source": metadata, "completed_sequence_child_verbatim": run,
        "declared_runtime_revision": PROFILES[name][0], "raw_passed": False,
        "validation_errors": [], "repeats": [], "valid_complete_profile": False}
    if raw is None:
        result["validation_errors"].append("Exact child/report never completed or unavailable in the finished sequence")
        result["repeats"] = [missing_repeat(i, result["validation_errors"][0]) for i in (1, 2, 3)]
        return result
    result.update(raw_passed=raw.get("passed") is True, operator_runtime_revision=raw.get("operator_runtime_revision"),
        git_checkout_HEAD=raw.get("git_head"), git_worktree_status=raw.get("git_worktree_status"),
        native_executed=raw.get("native_executed"), native_validation=raw.get("native_validation"),
        run_interval_utc={"start": raw.get("utc_start"), "end": raw.get("utc_end")},
        elapsed_seconds=raw.get("elapsed_seconds"), conditions_verbatim=raw.get("conditions"),
        raw_failures_verbatim=raw.get("failures"), raw_warnings_verbatim=raw.get("warnings"),
        raw_regressions_verbatim=raw.get("regressions"), fixture_retained_for_diagnosis=raw.get("fixture_retained_for_diagnosis"),
        inflight_item_batch_sequences_verbatim=raw.get("inflight_item_batch_sequences"),
        launch_identity_and_manifests_verbatim=raw.get("identity"), helper_sources_verbatim=raw.get("helper_sources"),
        archived_isolation_evidence={key: raw.get(key) for key in ("other_live_backend_sessions", "ambient_status", "statement_instrumentation")},
        measurement_verbatim=raw.get("measurement"), raw_resource_ledgers_verbatim=raw.get("resource_ledgers"),
        provided_receiver_services={key: raw.get(key) for key in ("all_phase_actual_receiver_service",
            "steady_window_actual_receiver_service", "steady_plus_tail_actual_receiver_service", "receiver_service_scope")})
    expected_conditions = {"scenarios": ["mixed"], "warmup_seconds": 30, "observation_seconds": 120,
        "repeats": 3, "feed_period_seconds": .5, "poll_seconds": .1,
        "fixed_attempts_per_round": {"FE": 32000, "water_mB": 1000},
        "item": "minecraft:stone", "CUSTOM_NAME": VARIANTS, "item_source_slots": {"A": 0, "B": 1},
        "maximum_inflight_item_batches": 1, "sources_per_channel": 1, "endpoint_spacing_blocks": 64,
        "be_y": 64, "chest_side": "EAST", "quiet_seconds": 2.2, "post_phase_drain_timeout_seconds": 1200,
        "observer": "single Python/RCON"}
    try:
        if run.get("exit_code") != 0 or run.get("passed") is not True or not result["raw_passed"] or raw.get("failures"):
            raise ValueError("Sequence child exit/pass or raw completed pass check failed; raw failure retained")
        if raw.get("label") != name or raw.get("operator_runtime_revision") != PROFILES[name][0] or raw.get("cluster") != "dev_three_v1":
            raise ValueError("Exact raw label/operator revision/cluster mismatch")
        if raw.get("report_kind") != "same_channel_real_resource_mix" or raw.get("native_executed") is not True or raw.get("native_validation") != "COMPLETED_REAL_GUARDED_WINDOWS":
            raise ValueError("No complete real native resource-mix validation")
        if not raw.get("utc_end") or any(raw.get("conditions", {}).get(key) != value for key, value in expected_conditions.items()):
            raise ValueError("Raw protocol differs from the fixed mixed30/120/3 supplement")
        pair = raw["conditions"]["fixed_item_pair_per_observation_window"]
        if [pair.get(k) for k in ("named_stone_A", "named_stone_B", "warmup_items")] != [32, 32, 0]:
            raise ValueError("Wrong fixed ITEM input/component protocol")
        if raw.get("inflight_item_batch_sequences"):
            raise ValueError("An ITEM batch remains in flight")
        identities = raw.get("identity", {})
        if set(identities) != {"A", "B", "C"} or any(len({i.get(key) for i in identities.values()}) != 3 for key in ("pid", "world_id", "session_id")):
            raise ValueError("Missing three distinct archived PID/world/session identities")
        for server, identity in identities.items():
            flags = identity.get("config_transfer_flags_observed", {})
            if tuple(flags.get(key) for key in ("transfer.channelBatches", "transfer.localFastPath")) != PROFILES[name][2]:
                raise ValueError("Observed config flags differ from this declared mode: " + server)
            if not re.fullmatch(r"[0-9a-f]{64}", identity.get("config_file_start_sha256", "")) or identity.get("config_file_start_sha256") != identity.get("config_file_end_sha256"):
                raise ValueError("Archived config start/end hash is missing/unstable")
            if not identity.get("launch_mod_artifact_manifests") or not re.fullmatch(r"[0-9a-f]{64}", identity.get("launch_crosstesseract_bytecode_sha256", "")):
                raise ValueError("Missing actual launch-selected artifact manifest")
    except (ValueError, KeyError, TypeError) as error:
        result["validation_errors"].append(str(error))
    samples = raw.get("samples", [])
    result["raw_sample_entry_index"] = [{"raw_sample_index": i, "scenario": s.get("scenario"),
        "repeat": s.get("repeat"), "passed": s.get("passed")} for i, s in enumerate(samples)]
    if len(samples) != 3:
        result["validation_errors"].append("Expected exactly three raw samples, actual=" + str(len(samples)))
    for repeat in (1, 2, 3):
        matches = [(i, s) for i, s in enumerate(samples) if s.get("scenario") == "mixed" and type(s.get("repeat")) is int and s["repeat"] == repeat]
        if not matches:
            result["repeats"].append(missing_repeat(repeat, "Raw mixed repeat missing; not imputed"))
            continue
        if len(matches) != 1:
            result["validation_errors"].append("Duplicate raw mixed repeat " + str(repeat))
        i, sample = matches[0]
        try:
            result["repeats"].append(sample_summary(raw, sample, i))
        except (ValueError, KeyError, TypeError) as error:
            failed = missing_repeat(repeat, "Malformed/partial raw sample: " + str(error))
            failed.update(raw_sample_index=i, raw_passed=sample.get("passed") is True,
                raw_partial_sample_keys=list(sample),
                unknown_business_events_verbatim=[e for phase in ("warmup", "warmup_drain", "steady", "conservation")
                    for e in sample.get(phase, {}).get("events", []) if type(e.get("amount")) is not int])
            result["repeats"].append(failed)
    lanes = raw.get("fixtures", {}).get("mixed", [])
    endpoints = [p["name"] for p in (lanes[0] if lanes else {}).get("sinks", [])]
    aggregates = {scope: {key: {e: 0 for e in endpoints} for key in RESOURCES}
        for scope in ("steady", "tail", "steady_plus_tail")}
    for repeat in result["repeats"]:
        for scope, resources in aggregates.items():
            for key, recipients in resources.items():
                observed = repeat.get("resources", {}).get(key, {}).get(scope, {}).get("output_by_endpoint", {})
                for endpoint in recipients:
                    if not repeat.get("resources"):
                        recipients[endpoint] = None
                    else:
                        value = observed.get(endpoint, 0)
                        recipients[endpoint] = recipients[endpoint] + value if recipients[endpoint] is not None and value is not None else None
    result["aggregate_actual_recipient_service_per_resource_and_component"] = aggregates
    result["intended_recipients_served_across_three_repeats"] = bool(endpoints) and all(
        amount is not None and amount > 0 for key in ("FE", "water") for amount in aggregates["steady_plus_tail"][key].values()) and all(
        aggregates["steady_plus_tail"]["item_A"][e] is not None and aggregates["steady_plus_tail"]["item_B"][e] is not None and
        aggregates["steady_plus_tail"]["item_A"][e] + aggregates["steady_plus_tail"]["item_B"][e] > 0 for e in endpoints)
    if not result["intended_recipients_served_across_three_repeats"]:
        result["validation_errors"].append("An intended recipient lacks known actual FE/water/named-stone service across all repeats")
    all_events = [e for s in samples for phase in ("warmup", "warmup_drain", "steady", "conservation") for e in s.get(phase, {}).get("events", [])]
    result["all_phase_actual_event_ledgers_including_warmup"] = {key: events_ledger(all_events, key) for key in RESOURCES}
    for variant in VARIANTS:
        uncertain = [a for s in samples for a in s.get("steady", {}).get("item_attempts", [])
            if a.get("variant") == variant and a.get("accepted") is None]
        if uncertain:
            ledger = result["all_phase_actual_event_ledgers_including_warmup"]["item_" + variant]
            ledger["unknown_events_verbatim"].extend(uncertain)
            ledger["input_attempts"] += len(uncertain)
            ledger["requested"] += sum(integer(a["requested"], "uncertain ITEM requested") for a in uncertain)
            ledger.update(accepted=None, rejected_units=None, complete_event_amounts=False)
    result["all_phase_actual_recipient_service_per_resource_and_component"] = {key: {
        e: result["all_phase_actual_event_ledgers_including_warmup"][key]["output_by_endpoint"].get(e, 0) for e in endpoints} for key in RESOURCES}
    try:
        if len(raw.get("item_batches", [])) != 3:
            raise ValueError("Wrong total finite ITEM batch count")
        ledgers = raw["resource_ledgers"][raw["fixtures"]["mixed"][0]["name"]]
        for key in RESOURCES:
            check_ledger(ledgers[key], result["all_phase_actual_event_ledgers_including_warmup"][key], "all phases " + key)
        for scope, raw_scope in (("steady", "steady_window_actual_receiver_service"), ("steady_plus_tail", "steady_plus_tail_actual_receiver_service")):
            saved = raw[raw_scope]["mixed"]
            expected = {"FE": aggregates[scope]["FE"], "water": aggregates[scope]["water"],
                "named_stone_total": {e: aggregates[scope]["item_A"][e] + aggregates[scope]["item_B"][e] for e in endpoints}}
            if saved != expected:
                raise ValueError("Provided aggregate service differs from all actual repeat events")
        saved = raw["all_phase_actual_receiver_service"]["mixed"]
        all_service = result["all_phase_actual_recipient_service_per_resource_and_component"]
        expected = {"FE": all_service["FE"], "water": all_service["water"],
            "named_stone_total": {e: all_service["item_A"][e] + all_service["item_B"][e] for e in endpoints}}
        if saved != expected:
            raise ValueError("Provided all-phase receiver service differs from actual events including warmup")
    except (ValueError, KeyError, TypeError) as error:
        result["validation_errors"].append(str(error))
    result["valid_complete_profile"] = not result["validation_errors"] and all(r["valid_complete_repeat"] for r in result["repeats"])
    result["load_provenance_resolution"] = "Archived launch-selected manifests/PID/session/world/epoch and successful driver end rehash; no new filesystem/class-loader attestation. Old config flags are observed file values, not proof old runtime supports them."
    return result


def get_cost(repeat, scope, key):
    cost = repeat.get("costs", {}).get(scope)
    if not cost:
        return None
    if key == "SQL_statement_events":
        return (cost.get("account_statement_events") or {}).get("events")
    if key == "SQL_statement_errors":
        return (cost.get("account_statement_events") or {}).get("errors")
    if key == "SQL_statement_timer_wait_sum_seconds":
        return cost.get(key)
    return cost.get("sum", {}).get(key)


def descriptive_change(a, b, direction, threshold):
    percent = (b / a - 1) * 100 if a is not None and b is not None and a != 0 else None
    new_positive_cost = a == 0 and b is not None and b > 0 and direction > 0
    return {"first": a, "second": b,
        "measurement_status": "MEASURED_BOTH" if a is not None and b is not None else UNMEASURED,
        "change_percent": percent,
        "descriptive_regression": percent is not None and direction * percent > threshold or new_positive_cost,
        "new_positive_cost_from_zero": new_positive_cost,
        "performance_target_status": "NO_SUPPLEMENT_SPECIFIC_FROZEN_TARGET"}


def median_measured(values):
    # A median cannot silently drop an absent or failed repeat.
    return statistics.median(values) if len(values) == 3 and all(v is not None for v in values) else None


def paired_comparisons(profiles, threshold):
    result = []
    cost_keys = ("db_transactions", "SQL_statement_events", "SQL_statement_errors",
        "SQL_statement_timer_wait_sum_seconds", "db_deadlock_retries", "transactions", "batch_devices",
        "batch_records", "batch_payload_bytes", "wal_writes", "wal_bytes", "wal_identical_skipped")
    for first, second in (("original87", "batch68"), ("original87", "fast68"), ("batch68", "fast68")):
        pairs, collected = [], {}
        for a, b in zip(profiles[first]["repeats"], profiles[second]["repeats"]):
            metrics, inputs = {}, {}
            valid = a["valid_complete_repeat"] and b["valid_complete_repeat"]
            for key in RESOURCES:
                x, y = a.get("resources", {}).get(key, {}), b.get("resources", {}).get(key, {})
                inputs[key] = {"same_requested_attempts_and_units": bool(x and y) and all(
                    x["steady"][k] == y["steady"][k] for k in ("input_attempts", "requested")),
                    "first_actually_accepted": x.get("steady", {}).get("accepted"),
                    "second_actually_accepted": y.get("steady", {}).get("accepted"),
                    "actual_accepted_equal": x.get("steady", {}).get("accepted") == y.get("steady", {}).get("accepted") if x and y else None}
                metrics[key + ".actual_steady_output_per_second"] = descriptive_change(
                    x.get("actual_steady_external_output_per_second") if valid else None,
                    y.get("actual_steady_external_output_per_second") if valid else None, -1, threshold)
            metrics["tail.seconds"] = descriptive_change(a.get("tail_observer", {}).get("actual_seconds") if valid else None,
                b.get("tail_observer", {}).get("actual_seconds") if valid else None, 1, threshold)
            for scope in ("fixed_observation", "steady_plus_tail", "tail_only", "warmup_plus_its_drain"):
                for key in cost_keys:
                    direction = 0 if key in ("batch_devices", "batch_records", "batch_payload_bytes", "wal_identical_skipped") else 1
                    metrics[scope + "." + key] = descriptive_change(get_cost(a, scope, key) if valid else None,
                        get_cost(b, scope, key) if valid else None, direction, threshold)
            for variant in VARIANTS:
                for timing in ("input_to_source", "source_to_first_output", "source_to_full_output", "input_to_full_output"):
                    for bound in ("lower_ms", "upper_ms"):
                        def timed(repeat):
                            return (repeat.get("ITEM_variants", {}).get(variant, {}).get("conservative_bounds", {}).get(timing) or {}).get(bound)
                        metrics["item_" + variant + "." + timing + "." + bound] = descriptive_change(timed(a) if valid else None,
                            timed(b) if valid else None, 1, threshold)
            for key, value in metrics.items():
                collected.setdefault(key, {"first": [], "second": []})
                for side in ("first", "second"):
                    collected[key][side].append(value[side])
            pairs.append({"repeat": a["repeat"], "valid_complete_pair": valid, "input_equivalence": inputs,
                "all_resources_actual_accepted_equal": all(v["actual_accepted_equal"] is True for v in inputs.values()), "metrics": metrics})
        medians = {}
        for key, values in collected.items():
            direction = -1 if "output_per_second" in key else 0 if any(key.endswith("." + k) for k in
                ("batch_devices", "batch_records", "batch_payload_bytes", "wal_identical_skipped")) else 1
            medians[key] = descriptive_change(median_measured(values["first"]), median_measured(values["second"]), direction, threshold)
        result.append({"first_profile": first, "second_profile": second, "pairs": pairs,
            "three_repeat_medians": medians, "descriptive_regression_threshold_percent": threshold,
            "scope": "Per-repeat and medians of all three complete repeats only. Input equivalence is actual per-resource, not inferred from equal attempts. Cost counts apply to their explicit captured scopes; these are descriptive changes, no primary/supplement target pass."})
    return result


def assemble(sequence, sequence_source, profiles, threshold, generator):
    parent_ok = sequence.get("passed") is True and sequence.get("state") == "completed" and not sequence.get("stop_failure") and \
        bool(sequence.get("runs")) and all(r.get("exit_code") == 0 and r.get("utc_end") for r in sequence["runs"])
    result = {"schema_version": 1, "report_kind": "offline_three_mode_same_channel_resource_mix_comparison",
        "generated_utc": datetime.now(timezone.utc).isoformat(), "generator": generator,
        "offline_file_derivation_only": True, "sequence_source": sequence_source,
        "finished_sequence_snapshot_verbatim": sequence, "parent_sequence_functional_pass": parent_ok,
        "profiles": profiles, "comparisons": paired_comparisons(profiles, threshold), "limits": LIMITS,
        "performance_goal_assessment": "NOT_APPLICABLE_NO_SUPPLEMENT_SPECIFIC_FROZEN_TARGET",
        "complete_valid_native_resource_mix_comparison": parent_ok and all(p["valid_complete_profile"] for p in profiles.values())}
    result["all_regressions"] = [{"first_profile": c["first_profile"], "second_profile": c["second_profile"],
        "scope": "repeat_pair", "repeat": pair["repeat"], "metric": metric, **value}
        for c in result["comparisons"] for pair in c["pairs"] for metric, value in pair["metrics"].items() if value["descriptive_regression"]]
    result["all_median_regressions"] = [{"first_profile": c["first_profile"], "second_profile": c["second_profile"],
        "scope": "three_repeat_median", "metric": metric, **value}
        for c in result["comparisons"] for metric, value in c["three_repeat_medians"].items() if value["descriptive_regression"]]
    return result


CSV_COST_KEYS = ("db_transactions", "SQL_statement_events", "SQL_statement_errors",
    "SQL_statement_timer_wait_sum_seconds", "db_deadlock_retries", "transactions",
    "errors", "queue_rejected", "quarantined", "db_transaction_attempts", "db_statements",
    "batch_devices", "batch_records", "batch_payload_bytes", "local_credit_publications",
    "wal_writes", "wal_bytes", "wal_identical_skipped")


def display(value, digits=6):
    if value is None:
        return UNMEASURED
    if type(value) is int:
        return str(value)
    if type(value) is float:
        return f"{value:.{digits}f}"
    return str(value)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def csv_text(summary):
    rows = []
    for name, profile in summary["profiles"].items():
        for repeat in profile["repeats"]:
            observer = repeat.get("steady_observer", {})
            for key, unit in RESOURCES.items():
                resource = repeat.get("resources", {}).get(key, {})
                steady, tail, total = (resource.get(k, {}) for k in ("steady", "tail", "steady_plus_tail"))
                row = {"profile": name, "repeat": repeat["repeat"], "resource": key, "unit": unit,
                    "operator_runtime_revision": profile.get("operator_runtime_revision", profile["declared_runtime_revision"]),
                    "git_checkout_HEAD": profile.get("git_checkout_HEAD"),
                    "raw_report": (profile.get("source") or {}).get("repo_relative_path"),
                    "raw_report_sha256": (profile.get("source") or {}).get("sha256"),
                    "valid_complete_repeat": repeat["valid_complete_repeat"],
                    "validation_errors_json": encoded(repeat["validation_errors"]),
                    "requested_attempts": steady.get("input_attempts"), "requested_units": steady.get("requested"),
                    "actually_accepted_units": steady.get("accepted"), "rejected_units": steady.get("rejected_units"),
                    "fully_accepted_attempts": steady.get("fully_accepted_attempts"),
                    "partial_or_zero_acceptance_attempts": steady.get("partial_or_zero_acceptance_attempts"),
                    "steady_actual_source_decrement": steady.get("source_actual_decrement"),
                    "steady_actual_external_output": steady.get("external_output"),
                    "steady_actual_output_per_second": resource.get("actual_steady_external_output_per_second"),
                    "tail_actual_source_decrement": tail.get("source_actual_decrement"),
                    "tail_actual_external_output": tail.get("external_output"),
                    "steady_plus_tail_actual_source_decrement": total.get("source_actual_decrement"),
                    "steady_plus_tail_actual_external_output": total.get("external_output"),
                    "conserved_after_drain": resource.get("conserved_after_drain"),
                    "steady_actual_seconds": observer.get("end") - observer.get("start")
                        if observer.get("start") is not None and observer.get("end") is not None else None,
                    "tail_actual_seconds": repeat.get("tail_observer", {}).get("actual_seconds"),
                    "scheduled_rounds": observer.get("scheduled_rounds"), "late_rounds": observer.get("late_rounds"),
                    "observer_saturated": observer.get("observer_saturated"),
                    "observer_cost_json": encoded(observer.get("observer_cost")),
                    "steady_recipient_service_json": encoded(resource.get("recipient_service", {}).get("steady")),
                    "tail_recipient_service_json": encoded(resource.get("recipient_service", {}).get("tail")),
                    "steady_plus_tail_recipient_service_json": encoded(resource.get("recipient_service", {}).get("steady_plus_tail")),
                    "unknown_business_events_json": encoded(total.get("unknown_events_verbatim")),
                    "source_first_decrement_origin": None, "actual_component_outputs_by_sink_json": None,
                    "native_WAL_barrier_count": UNMEASURED,
                    "cost_scope": "Phase-wide repeat counters repeated on each resource row; never add/attribute these rows as resource-specific costs."}
                timing = repeat.get("ITEM_variants", {}).get(key[-1]) if key.startswith("item_") else None
                if timing:
                    row["source_first_decrement_origin"] = (timing.get("source_first_decrement") or {}).get("origin")
                    row["actual_component_outputs_by_sink_json"] = encoded(timing.get("outputs_by_sink"))
                for scope in ("input_to_source", "source_to_first_output", "source_to_full_output", "input_to_first_output", "input_to_full_output"):
                    for bound in ("lower_ms", "upper_ms", "source_observation_span_ms", "target_observation_span_ms"):
                        row["ITEM_" + scope + "_" + bound] = (timing.get("conservative_bounds", {}).get(scope) or {}).get(bound) if timing else None
                for scope in ("fixed_observation", "steady_plus_tail", "tail_only", "warmup_plus_its_drain"):
                    for counter in CSV_COST_KEYS:
                        row[scope + "_" + counter] = get_cost(repeat, scope, counter)
                rows.append({k: UNMEASURED if v is None else v for k, v in row.items()})
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [])
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def markdown(summary):
    source_links = []
    lines = ["# 同频道真实资源混合：87 /68 batch /68 fast", "",
        "完成且有效：`" + str(summary["complete_valid_native_resource_mix_comparison"]).lower() + "`。本文件是完成 sequence 的离线派生；功能验证与描述性性能变化分开。", "",
        "每模式保留全部三个重复：30秒预热（不投 ITEM），每观察窗固定240次32000 FE请求、240次1000mB水请求，另投一次32+32个具有稳定 CUSTOM_NAME 的 stone。实际接受量与拒收量来自真实返回，不能仅凭尝试相同认定输入相同。", "",
        "单 observer monotonic 的保守区间包含 RCON/读取/轮询误差，NotWorldSave；FE/流体只有重叠总账，ITEM 使用单一在途组件批次。尾部排空输出不列入120秒吞吐。此补充不评估主路径冻结目标，也不证明峰值容量、总体尾分位、TPS或全阶段MSPT。", "",
        "## 原始来源与版本", "", "|模式|operator/runtime revision|git checkout HEAD|exit / raw passed|原始报告 SHA256|", "|---|---|---|---|---|"]
    for name, profile in summary["profiles"].items():
        run, source = profile.get("completed_sequence_child_verbatim") or {}, profile.get("source") or {}
        lines.append("|" + "|".join((name, profile.get("operator_runtime_revision", profile["declared_runtime_revision"]),
            str(profile.get("git_checkout_HEAD", UNMEASURED)), str(run.get("exit_code", UNMEASURED)) + " / " + str(profile["raw_passed"]), source.get("sha256", UNMEASURED))) + "|")
        if source:
            source_links.append(name + "：`" + source["repo_relative_path"] + "`。")
    lines += ["", *source_links, "", "加载来源、PID/world/session/epoch、配置首尾哈希和选定 class/resource manifests 保留在 JSON。operator 标签与 git HEAD 不充当独立 CodeSource 证明；旧版配置文件 flags 不证明旧代码支持该开关。", "",
        "## 每重复、每资源真实业务账", "", "|模式|r|资源|请求数|实际输入|拒收单位|窗内外输出|窗内输出/s|尾输出|源实际抽走（窗+尾）|最终总输出|", "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, profile in summary["profiles"].items():
        for repeat in profile["repeats"]:
            for key in RESOURCES:
                r = repeat.get("resources", {}).get(key, {})
                s, t, total = (r.get(k, {}) for k in ("steady", "tail", "steady_plus_tail"))
                lines.append("|" + "|".join((name, str(repeat["repeat"]), key, display(s.get("input_attempts")), display(s.get("accepted")),
                    display(s.get("rejected_units")), display(s.get("external_output")), display(r.get("actual_steady_external_output_per_second")),
                    display(t.get("external_output")), display(total.get("source_actual_decrement")), display(total.get("external_output")))) + "|")
    lines += ["", "A/B 组件及 FE/水的每接收端数量、首末实际输出和包含阶段边界的最大观察间隔都在 JSON/CSV；零服务保留。不同资源单位、SQL/WAL/local镜像不相加。", "",
        "## SQL、worker、WAL成本", "", "|模式|r|固定窗 DBtx / SQL语句|完整窗+尾 DBtx / SQL语句|尾部 DBtx / SQL语句|固定窗 worker / batch devices / records|固定窗 WAL writes / bytes|固定窗死锁重试 / SQL错误|尾秒|", "|---|---:|---|---|---|---|---|---|---:|"]
    for name, profile in summary["profiles"].items():
        for repeat in profile["repeats"]:
            def cost(scope, keys):
                return " / ".join(display(get_cost(repeat, scope, k)) for k in keys)
            lines.append("|" + "|".join((name, str(repeat["repeat"]), cost("fixed_observation", ("db_transactions", "SQL_statement_events")),
                cost("steady_plus_tail", ("db_transactions", "SQL_statement_events")), cost("tail_only", ("db_transactions", "SQL_statement_events")),
                cost("fixed_observation", ("transactions", "batch_devices", "batch_records")), cost("fixed_observation", ("wal_writes", "wal_bytes")),
                cost("fixed_observation", ("db_deadlock_retries", "SQL_statement_errors")), display(repeat.get("tail_observer", {}).get("actual_seconds")))) + "|")
    lines += ["", "固定窗 counter_end 在最后排空之前；完整生命周期窗口另用 counter_after_drain。预热+排空单列于 JSON/CSV，这些窗口重叠不能相加。账户 SUM_TIMER_WAIT 是语句耗时/等待之和，非CPU。原版缺失的 batch/WAL计数仍 UNMEASURED；capped barrier样本数不能当作累计barrier次数。", "",
        "## ITEM原始等待与端到端保守上下界", "", "单位秒；每组件32个。括号内为 lower–upper，保留 source 抽取前等待，三个重复不是总体尾保证。", "",
        "|模式|r|组件|输入→源首次抽取|源→首次外部到达|源→完整外部到达|完整输入→外部箱子|实际接收分配|", "|---|---:|---|---|---|---|---|---|"]
    for name, profile in summary["profiles"].items():
        for repeat in profile["repeats"]:
            for variant in VARIANTS:
                item = repeat.get("ITEM_variants", {}).get(variant, {})
                def timing(key):
                    b = item.get("conservative_bounds", {}).get(key)
                    return "(" + display(b["lower_ms"] / 1000) + "–" + display(b["upper_ms"] / 1000) + ")" if b else UNMEASURED
                lines.append("|" + "|".join((name, str(repeat["repeat"]), variant, timing("input_to_source"), timing("source_to_first_output"),
                    timing("source_to_full_output"), timing("input_to_full_output"), encoded(item.get("outputs_by_sink")))) + "|")
    lines += ["", "## 三重复中位数与回归", "", "这些变化是描述性；没有本补充专属冻结达成标准。实际输入不同的配对在 JSON 中逐资源明确标记。", "",
        "|比较|固定窗 DBtx变化|固定窗 SQL语句变化|生命周期 DBtx变化|FE窗内输出/s变化|水窗内输出/s变化|尾时间变化|", "|---|---:|---:|---:|---:|---:|---:|"]
    for comparison in summary["comparisons"]:
        medians = comparison["three_repeat_medians"]
        values = [display(medians[k]["change_percent"], 2) + "%" if medians[k]["change_percent"] is not None else UNMEASURED for k in
            ("fixed_observation.db_transactions", "fixed_observation.SQL_statement_events", "steady_plus_tail.db_transactions",
                "FE.actual_steady_output_per_second", "water.actual_steady_output_per_second", "tail.seconds")]
        lines.append("|" + "|".join([comparison["first_profile"] + "→" + comparison["second_profile"], *values]) + "|")
    lines += ["", "全部逐重复及中位数描述性回归保留在 JSON 的 all_regressions/all_median_regressions；零基准新成本单列，不编造百分比。worker/batch诊断变化、原始失败/警告、观察器饱和和恢复过的SQL错误均保留。", ""]
    for name, profile in summary["profiles"].items():
        errors = profile["validation_errors"] + ["r" + str(r["repeat"]) + ": " + e for r in profile["repeats"] for e in r["validation_errors"]]
        if errors:
            lines += ["**" + name + "验证未通过：**", "", *["- " + e.replace("\n", " ") for e in errors], ""]
    lines += ["完整复算：", "", "```bash", "python3 scripts/analysis/compare-resource-mix-68f32db.py --sequence reports/optimization-extra-sequence-68f32db.json", "```", "",
        "脚本拒绝在途 sequence、SHA不匹配、重复标签和既有派生输出；失败原始报告保持原样。JSON保存所有口径限制。", ""]
    return "\n".join(lines)


def verified_child_metadata(name, run, metadata):
    filename = Path(metadata["repo_relative_path"]).name
    if not re.fullmatch("optimization-resource-mix-" + name + r"-\d{8}T\d{6}Z-[0-9a-f]{6}\.json", filename):
        raise ValueError("Sequence child is not this profile's exact resource-mix filename: " + name)
    if not re.fullmatch(r"[0-9a-f]{64}", run.get("report_sha256", "")) or metadata["sha256"] != run["report_sha256"]:
        raise ValueError("Recorded child SHA256 differs from actual archived bytes: " + name)


def synthetic_profile(name):
    """Small, entirely in-memory protocol fixture; not a mocked native test pass."""
    revision, mode, flags = PROFILES[name]
    sinks, source = ["mixed_sink_0", "mixed_sink_1"], "mixed_source_0"
    raw = {"label": name, "cluster": "dev_three_v1", "report_kind": "same_channel_real_resource_mix",
        "passed": True, "failures": [], "warnings": [], "regressions": [], "native_executed": True,
        "native_validation": "COMPLETED_REAL_GUARDED_WINDOWS", "operator_runtime_revision": revision,
        "git_head": CORE, "utc_start": "2026-10-06T00:00:00+00:00", "utc_end": "2026-10-06T01:00:00+00:00",
        "conditions": {"scenarios": ["mixed"], "warmup_seconds": 30, "observation_seconds": 120, "repeats": 3,
            "feed_period_seconds": .5, "poll_seconds": .1, "fixed_attempts_per_round": {"FE": 32000, "water_mB": 1000},
            "item": "minecraft:stone", "CUSTOM_NAME": VARIANTS, "item_source_slots": {"A": 0, "B": 1},
            "maximum_inflight_item_batches": 1, "sources_per_channel": 1, "endpoint_spacing_blocks": 64, "be_y": 64,
            "chest_side": "EAST", "quiet_seconds": 2.2, "post_phase_drain_timeout_seconds": 1200, "observer": "single Python/RCON",
            "fixed_item_pair_per_observation_window": {"named_stone_A": 32, "named_stone_B": 32, "warmup_items": 0}},
        "fixtures": {"mixed": [{"name": "mixed", "channel": "in-memory-channel", "sources": [{"name": source, "server": "A"}],
            "sinks": [{"name": sinks[0], "server": "A"}, {"name": sinks[1], "server": "B"}]}]},
        "identity": {server: {"pid": 1000 + i, "world_id": "in-memory-world-" + server, "session_id": "in-memory-session-" + server,
            "fencing_epoch": 1, "config_transfer_flags_observed": dict(zip(("transfer.channelBatches", "transfer.localFastPath"), flags)),
            "config_file_start_sha256": "a" * 64, "config_file_end_sha256": "a" * 64,
            "launch_mod_artifact_manifests": [{"path": "IN_MEMORY_ONLY", "manifest_sha256": "b" * 64}],
            "launch_crosstesseract_bytecode_sha256": "c" * 64} for i, server in enumerate(("A", "B", "C"))},
        "inflight_item_batch_sequences": {}, "samples": [], "item_batches": []}

    def event(kind, key, endpoint, amount, at, requested=None):
        point = {"kind": kind, "resource": key, "endpoint": endpoint, "amount": amount, "start": at, "end": at + .001}
        if kind == "input":
            point["requested"] = amount if requested is None else requested
        return point

    def input_events(at, rounds, repeat):
        result = []
        for i in range(rounds):
            for key, amount in (("FE", 32000), ("water", 1000)):
                accepted = amount - (128 if name == "fast68" and repeat == 2 and rounds == 240 and i == 7 and key == "FE" else 0)
                result.append(event("input", key, source, accepted, at + i * .5, amount))
        return result

    def ledger(events):
        return {key: {field: point[field] for field in ("unit", "accepted", "source_actual_decrement", "external_output", "input_by_endpoint", "output_by_endpoint")}
            for key in RESOURCES for point in (events_ledger(events, key),)}

    def guard(end):
        snapshot = {"frame": {"source": {"count": 0}, "totals": {"A": 0, "B": 0},
            "targets": {e: {"count": 0} for e in sinks}}, "residue": {"by_kind": {kind: {"pool": 0, "allocation_remaining": 0} for kind in set(KINDS.values())},
            "local_buffers": {e: {"registered": True, "pause": "", **{k: 0 for k in ("txFE", "rxFE", "txItem", "rxItem", "txFluid", "rxFluid")}}
                for e in (source, *sinks)}}, "empty": True}
        return {"start": end - 3, "end": end, "passed": True, "quiet_seconds": 2.2,
            "snapshots": [dict(snapshot, at=end - 2.2), dict(snapshot, at=end)]}

    def snapshot(index, at):
        counter = {"db_transactions": 9007199254740993 + index * 100, "transactions": 1000 + index * 10,
            "db_deadlock_retries": 0, "errors": 0, "queue_rejected": 0, "quarantined": 0}
        if name != "original87":
            counter.update({key: index * 10 for key in COUNTERS if key not in counter})
        return {"start": at, "end": at + .01, "servers": {server: {"start": at + i * .001, "end": at + i * .001 + .001,
            "metrics": dict(counter)} for i, server in enumerate(("A", "B", "C"))},
            "statements": {"events": 9007199254740993 + index * 1000, "timer_picoseconds": index * 1000000,
                "errors": index * 3 if name == "original87" else 0, "observer_end": at + .011}}

    def delta(first, last):
        point = counter_scope(first, last)
        return {key: point[key] for key in ("sum", "per_server", "measurement_status", "account_statement_events")}

    for repeat in (1, 2, 3):
        base = repeat * 1000
        warm_events = input_events(base, 60, repeat)
        for key in ("FE", "water"):
            amount = events_ledger(warm_events, key)["accepted"]
            warm_events.extend(event("output", key, e, amount // 2, base + 29.9) for e in sinks)
        steady_events = input_events(base + 40, 240, repeat)
        tail_events = []
        for key in ("FE", "water"):
            amount = events_ledger(steady_events, key)["accepted"]
            within = amount * 9 // 10
            for i, e in enumerate(sinks):
                observed = within // 2 if i == 0 else within - within // 2
                steady_events.append(event("output", key, e, observed, base + 159.7 + i * .01))
                leftover = (amount - within) // 2 if i == 0 else amount - within - (amount - within) // 2
                tail_events.append(event("output", key, e, leftover, base + 161 + i * .01))
        batch = {"lane": "mixed", "phase": "steady", "repeat": repeat, "sequence": repeat, "passed": True,
            "variants": {}, "item_quiet_seconds": 2.2, "source_observations": [], "frames": [], "item_quiet_checks": [], "clears": []}
        delay = 200 if name == "original87" else 2
        for i, variant in enumerate(VARIANTS):
            key = "item_" + variant
            injection = {"start": base + 40 + i * .01, "end": base + 40 + i * .01 + .001}
            source_interval = {"start": base + 40 + delay + i, "end": base + 40 + delay + i + .005,
                "origin": "last_source_read_to_first_decrement"}
            output_interval = {"start": base + 40 + delay + i + .02, "end": base + 40 + delay + i + .03}
            record = {"injection": injection, "source_first_decrement": source_interval, "source_empty_interval": source_interval,
                "first_output": output_interval, "full_output": output_interval,
                "outputs_by_sink": {e: 32 if n == i else 0 for n, e in enumerate(sinks)}}
            for field, a, b in (("input_to_source", injection, source_interval), ("input_to_first_output", injection, output_interval),
                    ("input_to_full_output", injection, output_interval), ("source_to_first_output", source_interval, output_interval),
                    ("source_to_full_output", source_interval, output_interval)):
                record[field + "_bounds"] = bounds(a, b)
            batch["variants"][variant] = record
            steady_events.append(dict(injection, kind="input", resource=key, requested=32, amount=32, endpoint=source))
            destination = tail_events if name == "original87" else steady_events
            destination.extend((dict(source_interval, kind="source_chest_decrement", resource=key, amount=32, endpoint=source),
                dict(output_interval, kind="output", resource=key, amount=32, endpoint=sinks[i])))
        batch["completed"] = base + 40 + delay + 4
        batch["clears"] = [{"endpoint": sinks[i], "result": "CONFIRMED_CLEAR", "confirmed_by_variant": {
            variant: 32 if n == i else 0 for n, variant in enumerate(VARIANTS)}} for i in range(2)]
        batch["item_quiet_checks"] = [{"zero": True, "at": batch["completed"],
            "physical_frame": {"source": {"count": 0}, "totals": {"A": 32, "B": 32}},
            "residue": {"by_kind": {"cross_tesseract:item": {"pool": 0, "allocation_remaining": 0}},
                "local_buffers": {e: {"txItem": 0, "rxItem": 0} for e in (source, *sinks)}}}]
        raw["item_batches"].append(batch)
        end = base + 40 + max(delay + 6, 128)
        steady = {"name": "steady", "repeat": repeat, "start": base + 40, "end": base + 160,
            "requested_seconds": 120, "planned_rounds": 240, "scheduled_rounds": 240, "rounds": [{} for _ in range(240)],
            "item_batches": [repeat], "events": steady_events, "polls": 1200, "late_rounds": 0, "observer_saturated": False,
            "observer_cost": {"actual_seconds": 120, "RCON_commands": 2400, "RCON_request_reply_seconds_sum": 20},
            "ledger_change": ledger(steady_events), "input_completeness": {}}
        for key in RESOURCES:
            point = events_ledger(steady_events, key)
            steady["input_completeness"][key] = {field: point[source_field] for field, source_field in
                (("attempts", "input_attempts"), ("requested", "requested"), ("actually_accepted", "accepted"),
                    ("fully_accepted_attempts", "fully_accepted_attempts"), ("partial_or_zero_acceptance_attempts", "partial_or_zero_acceptance_attempts"))}
        sample = {"scenario": "mixed", "repeat": repeat, "passed": True, "before_warmup": guard(base - 1),
            "warmup": {"start": base, "end": base + 30, "requested_seconds": 30, "scheduled_rounds": 60, "events": warm_events},
            "warmup_drain": {"events": [], "guard": guard(base + 35)}, "steady": steady,
            "conservation": {"start": base + 160.02, "end": end, "events": tail_events, "guard": guard(end - .01), "passed": True},
            "steady_and_tail_ledger_change": ledger(steady_events + tail_events)}
        for key, index, at in (("warmup_counter_start", 0, base - .1), ("warmup_counter_end", 1, base + 35.1),
                ("counter_start", 2, base + 39.9), ("counter_end", 3, base + 160.01), ("counter_after_drain", 4, end + .01)):
            sample[key] = snapshot(index, at)
        for field, first, last in (("counter_delta", "counter_start", "counter_end"),
                ("lifecycle_counter_delta", "counter_start", "counter_after_drain"),
                ("warmup_and_drain_counter_delta", "warmup_counter_start", "warmup_counter_end")):
            sample[field] = delta(sample[first], sample[last])
        raw["samples"].append(sample)
    all_events = [e for sample in raw["samples"] for phase in ("warmup", "warmup_drain", "steady", "conservation") for e in sample[phase]["events"]]
    raw["resource_ledgers"] = {"mixed": ledger(all_events)}
    all_outputs = {key: events_ledger(all_events, key)["output_by_endpoint"] for key in RESOURCES}
    raw["all_phase_actual_receiver_service"] = {"mixed": {"FE": all_outputs["FE"], "water": all_outputs["water"],
        "named_stone_total": {e: all_outputs["item_A"].get(e, 0) + all_outputs["item_B"].get(e, 0) for e in sinks}}}
    for scope, target in (("steady", "steady_window_actual_receiver_service"), ("steady_plus_tail", "steady_plus_tail_actual_receiver_service")):
        selected = [e for s in raw["samples"] for phase in (("steady",) if scope == "steady" else ("steady", "conservation")) for e in s[phase]["events"]]
        by_resource = {key: events_ledger(selected, key)["output_by_endpoint"] for key in RESOURCES}
        raw[target] = {"mixed": {"FE": by_resource["FE"], "water": by_resource["water"],
            "named_stone_total": {e: by_resource["item_A"].get(e, 0) + by_resource["item_B"].get(e, 0) for e in sinks}}}
    run = {"command": ["python3", "scripts/optimization-resource-mix.py", "--execute", "--label", name,
        "--operator-revision", revision, "--scenarios", "mixed", "--warmup", "30", "--seconds", "120", "--repeats", "3", "--timeout", "1200"],
        "runtime_revision": revision, "mode": mode, "smoke_not_performance": False,
        "exit_code": 0, "passed": True, "utc_end": "2026-10-06T01:00:00Z",
        "report": "reports/optimization-resource-mix-" + name + "-20261006T000000Z-abcdef.json"}
    metadata = {"repo_relative_path": run["report"], "sha256": digest(encoded(raw).encode()), "size_bytes": len(encoded(raw))}
    run["report_sha256"] = metadata["sha256"]
    return raw, run, metadata


def self_test():
    fixtures = {name: synthetic_profile(name) for name in PROFILES}
    sequence = {"source_revision": CORE, "state": "completed", "passed": True, "utc_end": "2026-10-06T01:00:00Z",
        "runs": [point[1] for point in fixtures.values()]}
    selected = select_runs(sequence)
    profiles = {name: profile_summary(name, raw, run, metadata) for name, (raw, run, metadata) in fixtures.items()}
    errors = {name: [*p["validation_errors"], *[e for r in p["repeats"] for e in r["validation_errors"]]] for name, p in profiles.items()}
    assert all(p["valid_complete_profile"] for p in profiles.values()), errors
    for name, (_, run, metadata) in fixtures.items():
        verified_child_metadata(name, run, metadata)
    summary = assemble(sequence, {"sha256": "IN_MEMORY_ONLY"}, profiles, 10, {"path": "IN_MEMORY_ONLY"})
    assert summary["complete_valid_native_resource_mix_comparison"]
    baseline = profiles["original87"]["repeats"][0]
    assert get_cost(baseline, "fixed_observation", "db_transactions") == 300  # >2^53 snapshots, exact difference.
    assert get_cost(baseline, "fixed_observation", "SQL_statement_events") == 1000
    assert get_cost(baseline, "steady_plus_tail", "db_transactions") == 600
    assert baseline["costs"]["fixed_observation"]["sum"]["wal_writes"] is None
    assert baseline["costs"]["fixed_observation"]["measurement_status"]["wal_writes"] == UNMEASURED
    assert baseline["resources"]["item_A"]["steady"]["external_output"] == 0
    assert baseline["resources"]["item_A"]["tail"]["external_output"] == 32
    assert baseline["ITEM_variants"]["A"]["conservative_bounds"]["input_to_source"]["lower_ms"] > 199000
    pair = summary["comparisons"][1]["pairs"][1]
    assert pair["input_equivalence"]["FE"]["same_requested_attempts_and_units"] is True
    assert pair["input_equivalence"]["FE"]["actual_accepted_equal"] is False
    assert pair["all_resources_actual_accepted_equal"] is False
    assert profiles["fast68"]["repeats"][1]["resources"]["FE"]["steady"]["rejected_units"] == 128
    assert median_measured([1, None, 3]) is None
    assert len(list(csv.DictReader(io.StringIO(csv_text(summary))))) == 36
    assert "NotWorldSave" in markdown(summary) and "UNMEASURED" in markdown(summary)
    for broken in (dict(sequence, state="running", utc_end=None), dict(sequence, runs=sequence["runs"] + [sequence["runs"][0]])):
        try:
            select_runs(broken)
        except ValueError:
            pass
        else:
            raise AssertionError("Unfinished/duplicate sequence accepted")
    bad_meta = dict(fixtures["original87"][2], sha256="f" * 64)
    try:
        verified_child_metadata("original87", selected["original87"], bad_meta)
    except ValueError:
        pass
    else:
        raise AssertionError("Actual/report SHA mismatch accepted")
    unknown = events_ledger([{"kind": "input", "resource": "FE", "endpoint": "owned", "requested": 32000, "amount": None}], "FE")
    assert unknown["accepted"] is None and unknown["rejected_units"] is None and unknown["unknown_events_verbatim"]
    partial = sample_summary({"fixtures": {"mixed": fixtures["fast68"][0]["fixtures"]["mixed"]}},
        {"scenario": "mixed", "repeat": 1, "passed": False, "steady": {"start": 1, "end": 2, "events": [],
            "item_attempts": [{"variant": "B", "accepted": None, "requested": 32, "status": "UNKNOWN_MUTATION_RESULT"}]}}, 0, validate=False)
    assert partial["resources"]["item_B"]["steady"]["accepted"] is None
    assert partial["resources"]["item_B"]["steady"]["requested"] == 32
    assert partial["resources"]["item_B"]["steady"]["input_attempts"] == 1
    assert partial["resources"]["item_A"]["tail"]["external_output"] is None
    raw, run, metadata = fixtures["fast68"]
    broken = copy.deepcopy(raw)
    broken["passed"] = False
    broken["failures"] = ["synthetic failed window"]
    broken["samples"] = broken["samples"][:1]
    failed = profile_summary("fast68", broken, dict(run, exit_code=1, passed=False), metadata)
    assert not failed["valid_complete_profile"] and len(failed["repeats"]) == 3
    assert failed["raw_failures_verbatim"] == ["synthetic failed window"]
    assert failed["repeats"][1]["resources"] == {}
    print(json.dumps({"offline_structure_self_test": "PASS", "native_execution": "NOT_RUN", "reports_read_or_written": False,
        "checks": ["Exact finished sequence three-label/mode/revision selection", "SHA mismatch/unfinished/duplicate rejection",
            "All3 repeats/36 per-resource CSV rows", "Fixed240 attempts with unequal actual input/128 rejected FE preserved",
            "Exact integer counters above2^53", "Fixed/lifecycle/tail/warmup scopes separate",
            "Original absent WAL/batch UNMEASURED", "ITEM steady0/tail32 and200s source wait retained",
            "Independent variant and per-recipient service ledgers", "Unknown mutation is None, failed/missing repeats retained",
            "CSV/MD in-memory rendering, no supplement-specific target claim"]}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sequence", default="reports/optimization-extra-sequence-68f32db.json", help="Finished ROOT-relative extras sequence JSON")
    parser.add_argument("--output", default="reports/optimization-resource-mix-comparison-68f32db", help="ROOT-relative reports output stem; existing JSON/CSV/MD refused")
    parser.add_argument("--regression-percent", type=float, default=10, help="Descriptive flag only, never a frozen acceptance target")
    parser.add_argument("--self-test", action="store_true", help="Pure in-memory structure/counter/ledger/render checks; no sequence/child file reads")
    args = parser.parse_args()
    if not math.isfinite(args.regression_percent) or not 0 <= args.regression_percent <= 100:
        parser.error("Require0<=descriptive regression threshold<=100")
    if args.self_test:
        self_test()
        return 0
    sequence_path = archived_path(args.sequence)
    targets = {suffix: archived_path(args.output + "." + suffix, "." + suffix) for suffix in ("json", "csv", "md")}
    if any(path.exists() for path in targets.values()):
        raise ValueError("Existing derived outputs refused; choose a distinct --output stem")
    sequence, sequence_source = read_saved(sequence_path, 2 * 1024 * 1024)
    if sequence.get("source_revision") != CORE:
        raise ValueError("Extras sequence source revision is not the exact declared68 core")
    runs = select_runs(sequence)  # Gate finished status BEFORE reading any child file.
    profiles, read_sources = {}, [(sequence_path, sequence_source)]
    for name, run in runs.items():
        if run is None or not run.get("report"):
            profiles[name] = profile_summary(name, None, run, None)
            continue
        path = archived_path(run["report"])
        raw, metadata = read_saved(path)
        verified_child_metadata(name, run, metadata)
        profiles[name] = profile_summary(name, raw, run, metadata)
        read_sources.append((path, metadata))
        del raw  # Avoid retaining large raw chest-frame/RCON arrays across modes.
    own_file = Path(__file__).resolve()
    own_bytes = own_file.read_bytes()
    generator = {"path": str(own_file), "repo_relative_path": own_file.relative_to(ROOT).as_posix(), "sha256": digest(own_bytes)}
    summary = assemble(sequence, sequence_source, profiles, args.regression_percent, generator)
    outputs = {"json": json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        "csv": csv_text(summary), "md": markdown(summary)}
    for path, metadata in read_sources:
        if file_digest(path) != metadata["sha256"]:
            raise ValueError("Archived evidence changed during derivation; no outputs generated: " + str(path))
    if digest(own_file.read_bytes()) != generator["sha256"]:
        raise ValueError("Analysis generator changed during derivation")
    # Exclusive creates: raw reports and existing derived evidence are never overwritten.
    for suffix, path in targets.items():
        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(outputs[suffix])
    print(json.dumps({"complete_valid_native_resource_mix_comparison": summary["complete_valid_native_resource_mix_comparison"],
        "outputs": {suffix: str(path.relative_to(ROOT)) for suffix, path in targets.items()},
        "profile_errors": {name: p["validation_errors"] for name, p in profiles.items()},
        "performance_goals": "NOT_APPLICABLE_TO_THIS_SUPPLEMENT"}, ensure_ascii=False))
    return 0 if summary["complete_valid_native_resource_mix_comparison"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("Offline comparison refused: " + str(error), file=sys.stderr)
        sys.exit(1)
