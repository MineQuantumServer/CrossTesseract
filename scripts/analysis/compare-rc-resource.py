#!/usr/bin/env python3
"""Offline comparison of the three closed RC/v2 mixed-resource stages.

Reads only JSON evidence. Never imports a workload or opens RCON/SQL. The parent
sequence may still be running later stages; each of the three selected children
must already be closed, SHA verified, qualified and normally stopped.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
PROFILES = {"f3Bmix": "f3_batch", "finalBmix": "final_batch", "finalFastMix": "final_fast"}
RESOURCES = ("FE", "water", "item_A", "item_B")
TIMINGS = ("input_to_source_bounds", "source_to_first_output_bounds",
           "source_to_full_output_bounds", "input_to_full_output_bounds")
NOTES = [
    "One independently scheduled ITEM pair per profile, two stable component variants; no population p95/p99 or 30-batch claim.",
    "Identical attempts do not establish identical accepted input: actual validated acceptance is retained for every resource.",
    "Fixed counters end before tail drain; lifecycle counters include recorded drain/quiet, not indefinite future maintenance.",
    "SQL, WAL and local credit mirrors are not additional assets. local_input/output_units mix units and are not throughput.",
    "ITEM bounds use a single Python monotonic observer and actual vanilla chests. FE/water use native capability acceptance/extraction; not physical fluid containers or world-save latency.",
    "Probe histograms contain complete measured tick windows, selected main-thread mod root wall spans, not CPU or all mod code. Max of per-JVM quantiles is not a pooled percentile.",
    "Trace times retain per-JVM nano values and wall-anchor intervals; raw nanoTime values from different JVMs are never subtracted. Cross-JVM mapped intervals allow 1ms anchor quantization plus observed drift, not an absolute clock guarantee.",
    "Successful wal_return hooks can include identical-write skips; actual WAL counters are reported separately. local_input has no business ID and is not assigned to A/B by order.",
    "reason_effective includes checkpoint scheduling; an asset-carrying business-work ratio is UNMEASURED. Optional compat hooks with no calls are unexercised.",
    "This supplement does not replace frozen primary FE cost/latency gates and is not peak capacity or instantaneous TPS.",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Evidence outside repository: {path}")
    return path


def read_ref(ref: dict) -> tuple[Path, dict]:
    path = ref_path(ref["path"])
    if digest(path) != ref["sha256"]:
        raise ValueError(f"Evidence SHA mismatch: {path}")
    return path, json.loads(path.read_text())


def evidence(path: Path) -> dict:
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}


def compact_hist(hist: dict) -> dict:
    return {k: v for k, v in hist.items() if k != "histogram_upper_ns_count"}


def probe_summary(probe: dict) -> dict:
    result = {}
    for server, entry in probe.items():
        p = entry["data"]
        roots = p["mod_roots"]
        result[server] = {
            "valid": roots["valid"], "window_closed": p["window_closed"],
            "ticks": p["ticks"], "actual_tps": p["actual_tps"],
            "logical_main_mod_roots": compact_hist(roots["per_complete_logical_tick_cycle"]),
            "inside_frame_mod_roots": compact_hist(roots["per_complete_tick"]),
            "outside_tick_main_roots": compact_hist(roots["outside_tick_main_thread_roots"]),
            "whole_MC_tick": compact_hist(p["spans"]["server_tick"]["inclusive"]),
            "selected_sites": roots["included_sites"], "coverage_limits": roots["coverage_limits"],
            "invalid_ticks": roots["invalid_ticks"], "invalid_cycles": roots["invalid_cycles"],
            "frame_overflow_calls": p["frame_overflow_calls"],
            "trace_events_dropped": p["trace_events_dropped"], "trace_errors": p["trace_errors"],
        }
    return result


def mapped_event(event: dict, clock: dict) -> dict:
    # Each endpoint's conversion is independent. Do not subtract JVM nano values.
    start_ns, end_ns = clock["nano_start"], clock["nano_end"]
    delta = event["nano_time"] - start_ns
    start_est = clock["wall_start_ms"] * 1_000_000 + delta
    end_est = clock["wall_end_ms"] * 1_000_000 + event["nano_time"] - end_ns
    return {**event, "mapped_wall_lower_ns": min(start_est, end_est) - 1_000_000,
            "mapped_wall_upper_ns": max(start_est, end_est) + 1_000_000,
            "observed_anchor_drift_ns": abs(start_est - end_est)}


def trace_summary(sample: dict) -> dict:
    audit = sample["trace_resource_identity_after_seal"]
    operations = {key: {**value, "events": []} for key, value in audit["operations"].items()}
    anonymous = []
    for server, entry in sample["probe_full_lifecycle"].items():
        data = entry["data"]
        for event in data["item_events"]:
            row = {"server": server, **mapped_event(event, data["clock"])}
            op = event.get("operation")
            if op in operations:
                operations[op]["events"].append(row)
            else:
                anonymous.append(row)
    return {"status": audit["status"], "operations": operations,
            "unassigned_events": anonymous, "missing_business_IDs": audit["missing_business_IDs"],
            "identity_basis": "Actual post-seal transfer/resource JOIN and bounded canonical payload decode; not event order."}


def load_profile(run: dict) -> dict:
    if run["state"] != "PASS" or run.get("exit_code") != 0:
        raise ValueError(f"Selected child not complete/PASS: {run['name']}")
    cp, controller = read_ref(run["child_controller"])
    for field in ("passed", "functional_passed", "qualified_passed", "all_own_launchers_exited_and_locks_free"):
        if controller.get(field) is not True:
            raise ValueError(f"Closed controller lacks {field}: {cp}")
    if any(v["exit_code"] != 0 for v in controller["own_launcher_exits"].values()):
        raise ValueError(f"Nonzero launcher exit: {cp}")
    rp, raw = read_ref(controller["raw_report"])
    if not raw.get("passed") or len(raw.get("samples", [])) != 1:
        raise ValueError(f"Expected one complete passing resource window: {rp}")
    sample = raw["samples"][0]
    if not sample.get("passed") or not sample["conservation"]["passed"]:
        raise ValueError(f"Resource sample/conservation failed: {rp}")
    batches = [{"repeat": b["repeat"], "sequence": b["sequence"], "passed": b["passed"],
                "variants": {name: {k: v.get(k) for k in (*TIMINGS, "outputs_by_sink")}
                             for name, v in b["variants"].items()}}
               for b in raw["item_batches"] if b["phase"] == "steady"]
    fixed = probe_summary(sample["probe_fixed_window"])
    full = probe_summary(sample["probe_full_lifecycle"])
    if any(not data["valid"] for phase in (fixed, full) for data in phase.values()):
        raise ValueError(f"Invalid root window: {rp}")
    return {
        "raw": evidence(rp), "controller": evidence(cp),
        "runtime_manifest": controller["runtime_manifest"],
        "runtime_revision": controller["runtime_revision"], "raw_git_head": raw["git_head"],
        "operator_runtime_revision": raw["operator_runtime_revision"],
        "source_runtime_qualified": controller["qualified_passed"],
        "conditions": raw["conditions"], "probe_agent": raw["probe_configuration"]["probe"],
        "repeat": sample["repeat"], "input_completeness": sample["steady"]["input_completeness"],
        "steady_ledger": sample["steady"]["ledger_change"],
        "steady_plus_tail_ledger": sample["steady_and_tail_ledger_change"],
        "steady_throughput": sample["steady"]["throughput"],
        "item_batches": batches, "fixed_counters": sample["counter_delta"],
        "lifecycle_counters": sample["lifecycle_counter_delta"],
        "recovered_SQL_failures": sample["recovered_SQL_failures"],
        "observer_cost": sample["steady"]["observer_cost"],
        "observer_saturated": sample["steady"]["observer_saturated"],
        "fixed_probe": fixed, "full_probe": full,
        "item_trace": trace_summary(sample), "raw_failures": raw["failures"],
        "raw_regressions": raw["regressions"],
        "own_launcher_exits": controller["own_launcher_exits"],
    }


def compare(profiles: dict) -> dict:
    probe_bytes = {tuple(sorted((Path(a["path"]).name, a["sha256"])
                               for a in p["probe_agent"]["artifacts"]))
                   for p in profiles.values()}
    if len(probe_bytes) != 1:
        raise ValueError("Different test-agent bytes cannot be compared")
    reference = profiles["f3_batch"]
    result = {}
    base_upper = [v["input_to_full_output_bounds"]["upper_ms"]
                  for b in reference["item_batches"] for v in b["variants"].values()]
    for name, p in profiles.items():
        upper = [v["input_to_full_output_bounds"]["upper_ms"]
                 for b in p["item_batches"] for v in b["variants"].values()]
        median = statistics.median(upper)
        result[name] = {
            "two_variant_median_input_to_full_upper_ms": median,
            "sample_median_below_15s": median < 15000,
            "sample_median_at_least_50pct_below_f3B": median <= statistics.median(base_upper) * .5,
            "independently_scheduled_ITEM_pairs": len(p["item_batches"]),
            "at_least_30_independent_batches": "UNVERIFIED",
            "actual_accepted_equal_to_f3B": {r: p["input_completeness"][r]["actually_accepted"] == reference["input_completeness"][r]["actually_accepted"] for r in RESOURCES},
            "fixed_counter_change_pct": {}, "lifecycle_counter_change_pct": {},
        }
        for key in ("fixed_counters", "lifecycle_counters"):
            out = result[name][key.replace("counters", "counter_change_pct")]
            for field, value in p[key]["sum"].items():
                previous = reference[key]["sum"].get(field)
                out[field] = None if previous in (None, 0) else (value / previous - 1) * 100
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sequence", type=Path)
    ap.add_argument("--output-prefix", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        event = {"nano_time": 1500, "phase": "test"}
        mapped = mapped_event(event, {"nano_start": 1000, "nano_end": 2000, "wall_start_ms": 10, "wall_end_ms": 10})
        assert mapped["mapped_wall_lower_ns"] <= 10_000_500 <= mapped["mapped_wall_upper_ns"]
        assert mapped["observed_anchor_drift_ns"] == 1000
        assert "histogram_upper_ns_count" not in compact_hist({"count": 0, "histogram_upper_ns_count": []})
        assert statistics.median([7000, 7100]) == 7050
        print("PASS: offline clock interval, histogram compaction and two-variant median")
        return 0
    if args.sequence is None or args.output_prefix is None:
        ap.error("--sequence and --output-prefix are required; no live operations exist")
    sequence_path = ref_path(str(args.sequence))
    sequence_bytes = sequence_path.read_bytes()
    sequence = json.loads(sequence_bytes)
    runs = {r["name"]: r for r in sequence["runs"]}
    profiles = {label: load_profile(runs[name]) for name, label in PROFILES.items()}
    comparisons = compare(profiles)
    result = {"schema": 1, "recipe": evidence(Path(__file__).resolve()),
              "sequence_snapshot": {"path": str(sequence_path.relative_to(ROOT)),
                                    "sha256": hashlib.sha256(sequence_bytes).hexdigest(),
                                    "state": sequence["state"], "passed": sequence["passed"]},
              "selected_children_complete_and_qualified": True, "notes": NOTES,
              "profiles": profiles, "descriptive_comparisons": comparisons}
    prefix = ref_path(str(args.output_prefix))
    outputs = [prefix.with_suffix(s) for s in (".json", ".csv", ".md")]
    if any(p.exists() for p in outputs):
        raise ValueError("Refusing to overwrite an existing output")
    rows = []
    for name, p in profiles.items():
        for resource in RESOURCES:
            inp = p["input_completeness"][resource]
            variant = resource.removeprefix("item_") if resource.startswith("item_") else None
            timings = p["item_batches"][0]["variants"][variant] if variant else {}
            row = {"profile": name, "repeat": p["repeat"], "resource": resource,
                         "actual_attempts": inp["attempts"], "requested": inp["requested"],
                         "actually_accepted": inp["actually_accepted"],
                         "partial_or_zero_attempts": inp["partial_or_zero_acceptance_attempts"],
                         "steady_external_output": p["steady_ledger"][resource]["external_output"],
                         "steady_plus_tail_external_output": p["steady_plus_tail_ledger"][resource]["external_output"],
                         "steady_receiver_service": json.dumps(p["steady_ledger"][resource]["output_by_endpoint"], sort_keys=True),
                         "full_receiver_service": json.dumps(p["steady_plus_tail_ledger"][resource]["output_by_endpoint"], sort_keys=True)}
            for timing in TIMINGS:
                for bound in ("lower_ms", "upper_ms"):
                    row[timing + "_" + bound] = timings.get(timing, {}).get(bound)
            rows.append(row)
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    md = ["Matched RC/v2 mixed-resource samples (one window per profile)", "",
          "| Profile | ITEM A input→full bounds (s) | ITEM B input→full bounds (s) | Fixed/full SQL tx | Fixed/full SQL statements |",
          "|---|---:|---:|---:|---:|"]
    for name, p in profiles.items():
        variants = p["item_batches"][0]["variants"]
        bounds = lambda v: f"{v['lower_ms']/1000:.3f}–{v['upper_ms']/1000:.3f}"
        md.append(f"| {name} | {bounds(variants['A']['input_to_full_output_bounds'])} | {bounds(variants['B']['input_to_full_output_bounds'])} | {p['fixed_counters']['sum']['db_transactions']}/{p['lifecycle_counters']['sum']['db_transactions']} | {p['fixed_counters']['sum']['db_statements']}/{p['lifecycle_counters']['sum']['db_statements']} |")
    md += ["", *[f"- {note}" for note in NOTES], "", "Raw evidence:", ""]
    md += [f"- `{p['raw']['path']}` SHA256 `{p['raw']['sha256']}`" for p in profiles.values()]
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for path, content in zip(outputs, (json.dumps(result, indent=2, ensure_ascii=False) + "\n", stream.getvalue(), "\n".join(md) + "\n")):
        with path.open("x") as output:
            output.write(content)
    print(json.dumps({"outputs": [evidence(p) for p in outputs]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
