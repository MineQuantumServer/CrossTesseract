#!/usr/bin/env python3
"""Offline, closed-evidence RC soak summary. Never opens RCON/SQL/JDK/proc."""
from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
GC_FIELDS = ("YGC", "YGCT", "FGC", "FGCT", "CGC", "CGCT", "GCT")
QUEUE_FIELDS = ("worker_queue", "completion_admitted", "ready_channels", "ready_devices", "closing_devices", "db_active_connections")
TIMINGS = ("input_to_source_bounds", "source_to_first_output_bounds", "source_to_full_output_bounds", "input_to_full_output_bounds")
NOTES = [
    "20 endpoints / 6 channels is this given-load cohort, not1000-endpoint or peak-capacity evidence.",
    "The workload uses only two stable ITEM payload variants, each32 items per batch. Payload cardinality is2; repeated batches do not increase component-type coverage.",
    "Assets are validated input/output ledgers. SQL/WAL/local credit mirrors and transfer record amounts are never added as assets.",
    "Fixed SQL/WAL counters end before final drain. Lifecycle costs include recorded tail drain/quiet, not indefinite future maintenance.",
    "Success-to-success output gaps are observer intervals, not proof of continuously pending demand. Controlled FE hold overlaps are separate; cold channels deliberately have gaps between inputs.",
    "Process points labeled0/30/60min are actual scheduled samples with their read spans. Sampled RSS/heap/queue maxima are not continuous peaks or a memory-leak proof.",
    "GC deltas are cumulative jstat counter/time differences, not pause p95/p99 or CPU time. FGC0 does not establish no leakage.",
    "Full probe histograms measure selected mod main-thread root wall spans per complete logical tick and whole tickServer calls; no claim of all mod CPU or uninstrumented GUI/compat code.",
    "All business bounds use the single Python monotonic observer. No raw nanoTime subtraction across JVMs and no world-save/durability latency claim.",
    "History is post-stop retained-created reconstruction, not continuous row/physical-size monitoring. Removed records cannot be recovered from final created_at rows.",
    "Allocation rate and exact per-reason asset-bearing work ratio are UNMEASURED. reason_effective includes checkpoint work.",
]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def meta(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}


def ref_path(value):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if path.is_symlink():
        raise ValueError("Regular evidence files required")
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT):
        raise ValueError("Evidence outside repository")
    return path


def read_ref(ref):
    path = ref_path(ref["path"])
    if digest(path) != ref["sha256"]:
        raise ValueError("Evidence SHA mismatch")
    return path, json.loads(path.read_text())


def resolve_archived_evidence(original_ref, archived_ref, root=ROOT):
    """Missing-original fallback only; a changed original never selects a copy."""
    def candidate(value):
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        if path.is_symlink():
            raise ValueError("Symlink evidence forbidden")
        path = path.resolve()
        if not path.is_relative_to(root):
            raise ValueError("Evidence outside selected repository root")
        return path

    original = candidate(original_ref["path"])
    if original.exists():
        if not original.is_file() or digest(original) != original_ref["sha256"]:
            raise ValueError("Existing original evidence SHA mismatch; archive cannot mask it")
        selected, used_archive = original, False
    else:
        if archived_ref is None or archived_ref["sha256"] != original_ref["sha256"]:
            raise ValueError("Missing original requires an archive ref with exactly the original SHA")
        selected = candidate(archived_ref["path"])
        if not selected.is_file() or digest(selected) != original_ref["sha256"]:
            raise ValueError("Archived copy bytes do not match original evidence SHA")
        used_archive = True
    resolution = {"original_ref": original_ref,
                  "selected": {"path": str(selected.relative_to(root)), "sha256": digest(selected)},
                  "used_archive": used_archive,
                  "reason": "original_missing_byte_identical_archive" if used_archive else "verified_existing_original"}
    return selected, resolution


def compact_hist(value):
    return {key: number for key, number in value.items() if key != "histogram_upper_ns_count"}


def quantiles(values):
    ordered = sorted(values)
    return {"samples": len(ordered), "p50": statistics.median(ordered) if ordered else None,
            "p95": ordered[math.ceil(len(ordered) * .95) - 1] if ordered else None,
            "p99": ordered[math.ceil(len(ordered) * .99) - 1] if ordered else None,
            "max": max(ordered) if ordered else None}


def ledger_delta(before, after):
    result = {}
    for lane, resources in after.items():
        result[lane] = {}
        for resource, final in resources.items():
            initial = before[lane][resource]
            value = {"unit": final["unit"], "accepted": final["accepted"] - initial["accepted"],
                     "external_output": final["external_output"] - initial["external_output"]}
            for key in ("input_by_endpoint", "output_by_endpoint"):
                value[key] = {endpoint: amount - initial[key].get(endpoint, 0) for endpoint, amount in final[key].items()}
            result[lane][resource] = value
    return result


def explicit_receiver_service(raw, ledgers):
    """Show actual zeros for every intended recipient; unused resource types stay unused."""
    result = deepcopy(ledgers)
    for case, lanes in raw["fixtures"].items():
        for lane in lanes:
            intended = {endpoint["name"] for endpoint in lane["sinks"]}
            for resource, ledger in result[lane["name"]].items():
                if case != "mixed" and resource != "FE":
                    continue
                if set(ledger["output_by_endpoint"]) - intended:
                    raise ValueError("Output recipient outside actual fixture identity")
                ledger["output_by_endpoint"] = {name: ledger["output_by_endpoint"].get(name, 0) for name in sorted(intended)}
    return result


def gap_record(previous, current):
    return {"previous_success": previous, "next_success": current,
            "reply_completion_gap_seconds": current["end"] - previous["end"],
            "lower_seconds": max(0, current["start"] - previous["end"]),
            "upper_seconds": current["end"] - previous["start"]}


def journal_summary(path, raw):
    pressure = {e["name"] for lanes in raw["fixtures"].values() for lane in lanes
                if lane["name"] == "backpressure" for e in lane["sinks"]}
    holds = [(hold["start"], hold["release_at"]) for hold in raw["holds"]]
    groups, inputs = {}, {}
    records = 0
    with path.open() as source:
        for line in source:
            records += 1
            point = json.loads(line)
            if point["stream"] != "observation:business":
                continue
            event = point["record"]
            if event.get("kind") not in ("input", "output") or "resource" not in event:
                continue
            key = event["endpoint"] + "/" + event["resource"]
            if event["kind"] == "input":
                value = inputs.setdefault(key, {"attempts": 0, "requested": 0, "actually_accepted": 0, "partial_or_zero_attempts": 0})
                value["attempts"] += 1; value["requested"] += event["requested"]; value["actually_accepted"] += event["amount"]
                value["partial_or_zero_attempts"] += event["amount"] != event["requested"]
                continue
            if event["amount"] <= 0:
                continue
            value = groups.setdefault(key, {"successful_outputs": 0, "actually_output": 0, "first": None, "last": None,
                                           "max_gap_without_controlled_hold": None, "max_gap_overlapping_controlled_hold": None})
            current = {k: event[k] for k in ("start", "end", "amount")}
            if value["last"] is not None:
                previous = value["last"]; gap = gap_record(previous, current)
                overlaps = (event["endpoint"] in pressure and event["resource"] == "FE"
                            and any(previous["end"] < end and current["end"] > start for start, end in holds))
                field = "max_gap_overlapping_controlled_hold" if overlaps else "max_gap_without_controlled_hold"
                if value[field] is None or gap["reply_completion_gap_seconds"] > value[field]["reply_completion_gap_seconds"]:
                    value[field] = gap
            value["successful_outputs"] += 1; value["actually_output"] += event["amount"]
            value["first"] = value["first"] or current; value["last"] = current
    if records != raw["streamed_evidence"]["records"]:
        raise ValueError("Complete journal record count mismatch")
    return {"record_count": records, "observation_inputs_by_endpoint_resource": inputs,
            "positive_external_outputs_by_endpoint_resource": groups,
            "scope": "Only observation:business records counted, excluding duplicate RCON traces and separate tail. Gaps are observations, never inferred pending-demand starvation."}


def process_summary(samples):
    selected = {}
    for scheduled in (0, 1800, 3600):
        points = [p for p in samples if p["scheduled"] == scheduled]
        if len(points) != 1:
            selected[str(scheduled)] = {"measurement": "UNMEASURED", "matching_samples": len(points)}
            continue
        point = points[0]
        selected[str(scheduled)] = {"utc": point["utc"], "observer_start": point["start"], "observer_end": point["end"],
            "processes": {p["server"]: {key: p.get(key) for key in ("pid", "starttime_ticks", "utc", "observer_monotonic", "offset_seconds", "sample_duration_seconds", "rss_bytes", "heap_used_bytes", "heap_committed_bytes", "cpu_total_seconds", *GC_FIELDS)} for p in point["process"]}}
    queues = {}
    for server in "ABC":
        data = [p for point in samples for p in point["process"] if p["server"] == server]
        maximum = {key: max(p[key] for p in data if p.get(key) is not None) for key in ("rss_bytes", "heap_used_bytes", "heap_committed_bytes")}
        qmax = {}
        for key in QUEUE_FIELDS:
            values = [point["runtime_SQL_counters"]["servers"][server]["metrics"].get(key) for point in samples]
            values = [v for v in values if v is not None]
            qmax[key] = max(values) if values else "UNMEASURED"
        queues[server] = {"sampled_memory_max_bytes": maximum, "sampled_queue_max": qmax}
    deltas = {}
    for start, end in ((0, 1800), (1800, 3600), (0, 3600)):
        if "processes" not in selected[str(start)] or "processes" not in selected[str(end)]:
            deltas[f"{start}_{end}"] = "UNMEASURED"; continue
        values = {}
        for server in "ABC":
            first = selected[str(start)]["processes"][server]; last = selected[str(end)]["processes"][server]
            if (first["pid"], first["starttime_ticks"]) != (last["pid"], last["starttime_ticks"]):
                raise ValueError("Process identity changed between GC samples")
            values[server] = {key: None if first[key] is None or last[key] is None else last[key] - first[key] for key in GC_FIELDS}
            values[server]["actual_process_sample_interval_seconds"] = last["observer_monotonic"] - first["observer_monotonic"]
        deltas[f"{start}_{end}"] = values
    return {"actual_0_30_60min_samples": selected, "cumulative_GC_deltas": deltas,
            "sampled_maxima": queues, "sample_count": len(samples), "leak_freedom": "UNMEASURED", "GC_pause_quantiles": "UNMEASURED", "allocation_rate": "UNMEASURED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", type=Path)
    parser.add_argument("--history-report", type=Path)
    parser.add_argument("--output-prefix", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        gap = gap_record({"start": 1.0, "end": 1.1}, {"start": 4.0, "end": 4.2})
        assert abs(gap["lower_seconds"] - 2.9) < 1e-9 and abs(gap["upper_seconds"] - 3.2) < 1e-9
        assert quantiles([1, 2, 3])["p50"] == 2 and quantiles([])["p95"] is None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "reports").mkdir()
            archive = root / "reports/report.json"; archive.write_text('{"closed":true}\n')
            wanted = digest(archive)
            original_ref = {"path": "scratch/report.json", "sha256": wanted}
            archive_ref = {"path": "reports/report.json", "sha256": wanted}
            selected, resolution = resolve_archived_evidence(original_ref, archive_ref, root)
            assert selected == archive and resolution["used_archive"]
            # The same generic resolver must also handle byte-identical JSONL.
            event_archive = root / "reports/events.jsonl"; event_archive.write_text('{"record":1}\n')
            event_sha = digest(event_archive)
            _, resolution = resolve_archived_evidence({"path": "scratch/events.jsonl", "sha256": event_sha},
                                                      {"path": "reports/events.jsonl", "sha256": event_sha}, root)
            assert resolution["used_archive"]
            (root / "scratch").mkdir(); original = root / original_ref["path"]
            original.write_bytes(archive.read_bytes())
            selected, resolution = resolve_archived_evidence(original_ref, archive_ref, root)
            assert selected == original and not resolution["used_archive"]
            original.write_text("changed")
            try:
                resolve_archived_evidence(original_ref, archive_ref, root)
            except ValueError:
                pass
            else:
                raise AssertionError("Changed existing original masked by archive")
            original.unlink()
            try:
                resolve_archived_evidence(original_ref, dict(archive_ref, sha256="0" * 64), root)
            except ValueError:
                pass
            else:
                raise AssertionError("Wrong archive identity accepted")
        print("PASS: offline interval/quantiles; missing-original report+JSONL archive fallback; changed-original/wrong-archive rejection")
        return 0
    if args.controller is None or args.output_prefix is None:
        parser.error("Explicit closed controller and unique output prefix required")
    cp = ref_path(str(args.controller)); controller = json.loads(cp.read_text())
    if any(controller.get(k) is not True for k in ("passed", "qualified_passed", "functional_passed", "sixty_minute_gate", "all_own_launchers_exited_and_locks_free")):
        raise ValueError("Closed qualified complete3600s controller required")
    if any(p["exit_code"] != 0 for p in controller["own_launcher_exits"].values()):
        raise ValueError("Normal own launcher EXIT0 required")
    archives = controller.get("archived_raw_evidence", {})
    rp, raw_resolution = resolve_archived_evidence(controller["raw_report"], archives.get("report.json"))
    raw = json.loads(rp.read_text())
    if not raw.get("passed") or raw.get("60min_gate") is not True:
        raise ValueError("Closed raw full gate required")
    evidence = raw["streamed_evidence"]
    journal, journal_resolution = resolve_archived_evidence(evidence, archives.get("events.jsonl"))
    cohort_path = ROOT / "scripts/analysis/rc-soak-history-audit.py"
    spec = importlib.util.spec_from_file_location("rc_soak_summary_cohort", cohort_path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    group = module.cohort(raw)
    batches = []
    for batch in raw["item_batches"]:
        batches.append({"sequence": batch["sequence"], "passed": batch["passed"],
            "validated_actual_input_by_variant": batch["validated_staged_source"]["by_variant"],
            "variants": {name: {**{key: variant.get(key) for key in TIMINGS}, "output_by_receiver": variant["outputs_by_sink"],
                                 "expected_fixed_input_items": 32,
                                 "actual_source_decrement": batch["validated_staged_source"]["by_variant"][name] - variant["last_source"]["count"],
                                 "confirmed_external_items": sum(variant["outputs_by_sink"].values())}
                         for name, variant in batch["variants"].items()}})
    bounds = {variant: {timing: {bound: quantiles([b["variants"][variant][timing][bound] for b in batches])
                               for bound in ("lower_ms", "upper_ms")} for timing in TIMINGS} for variant in ("A", "B")}
    probe = {}
    for phase in ("probe_fixed_window", "probe_full_lifecycle"):
        probe[phase] = {}
        for server, entry in raw[phase].items():
            data = entry["data"]
            probe[phase][server] = {"valid": data["mod_roots"]["valid"], "ticks": data["ticks"], "actual_tps": data["actual_tps"],
                "logical_main_mod_roots": compact_hist(data["mod_roots"]["per_complete_logical_tick_cycle"]),
                "whole_MC_tick": compact_hist(data["spans"]["server_tick"]["inclusive"]),
                "scope": data["mod_roots"]["logical_tick_cycle_scope"], "coverage_limits": data["mod_roots"]["coverage_limits"]}
    result = {"recipe": meta(Path(__file__).resolve()), "controller": meta(cp), "raw": meta(rp), "journal": meta(journal),
              "evidence_resolution": {"report.json": raw_resolution, "events.jsonl": journal_resolution},
              "operator_runtime_revision": raw["operator_runtime_revision"], "raw_git_head": raw["git_head"],
              "runtime_manifest": controller["runtime_manifest"],
              "actual_runtime_JAR": raw["probe_configuration"]["artifacts"]["JAR"],
              "probe_artifacts": raw["probe_configuration"]["probe"]["artifacts"],
              "cohort": group, "endpoint_count": len(group["endpoints"]), "channel_count": len(group["channels"]),
              "conditions": raw["conditions"], "coverage_checks": raw["coverage_checks"], "notes": NOTES,
              "ITEM_payloads": raw["actual_native_ITEM_codec_payloads"], "ITEM_payload_cardinality": len(raw["actual_native_ITEM_codec_payloads"]),
              "ITEM_batches": batches, "ITEM_descriptive_bounds_ms_by_variant": bounds,
              "fixed_business_delta": explicit_receiver_service(raw, ledger_delta(raw["ledger_before_observation"], raw["observation"]["ledger_at_end"])),
              "observation_and_tail_business_delta": explicit_receiver_service(raw, raw["observation_and_tail_business_delta"]),
              "fixed_counter_delta": raw["observation_counter_delta"], "lifecycle_counter_delta": raw["observation_and_tail_counter_delta"],
              "holds": raw["holds"], "service_observations": journal_summary(journal, raw),
              "process_and_queues": process_summary(raw["observation"]["monitor_samples"]), "complete_window_probe": probe,
              "allocation_rate": "UNMEASURED", "exact_reason_asset_work_ratio": "UNMEASURED", "native_1000_endpoint_capacity": "UNMEASURED"}
    if args.history_report:
        hp = ref_path(str(args.history_report)); history = json.loads(hp.read_text())
        result["post_stop_history"] = {"source": meta(hp), "passed": history["passed"],
            "table_row_counts": history.get("table_row_counts", "UNMEASURED"), "scope": history["scope"]}
    prefix = args.output_prefix if args.output_prefix.is_absolute() else ROOT / args.output_prefix
    prefix = prefix.resolve()
    if not prefix.is_relative_to(ROOT):
        raise ValueError("Repository output prefix required")
    files = [prefix.with_suffix(suffix) for suffix in (".json", ".csv", ".md")]
    if any(path.exists() for path in files):
        raise ValueError("Refusing to overwrite summary")
    rows = []
    for scope, lanes in (("fixed", result["fixed_business_delta"]), ("fixed_and_tail", result["observation_and_tail_business_delta"])):
        for lane, resources in lanes.items():
            for resource, ledger in resources.items():
                for receiver, amount in ledger["output_by_endpoint"].items():
                    rows.append({"scope": scope, "lane": lane, "resource": resource, "receiver": receiver,
                                 "actual_external_output": amount, "unit": ledger["unit"], "actual_accepted_lane_total": ledger["accepted"]})
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with files[0].open("x") as output:
        json.dump(result, output, indent=2); output.write("\n")
    with files[1].open("x", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    lines = ["Closed RC full-soak evidence", "", f"Measured cohort: {len(group['endpoints'])} endpoints / {len(group['channels'])} channels; {len(batches)} ITEM pairs,32 A+32 B each; two payload types.", "",
             f"Actual ITEM payload bytes: {', '.join(str(p['actual_payload_bytes']) for p in result['ITEM_payloads'])}.", "",
             "Each receiver's actual fixed/tail service is in CSV; JSON retains every batch bound, controlled-hold gaps,0/30/60min samples, cumulative GC deltas, sampled queue maxima and fixed/full costs.", "", *["- " + note for note in NOTES], "", f"Raw: `{result['raw']['path']}` SHA256 `{result['raw']['sha256']}`", ""]
    with files[2].open("x") as output:
        output.write("\n".join(lines))
    print(json.dumps({"outputs": [meta(path) for path in files]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
