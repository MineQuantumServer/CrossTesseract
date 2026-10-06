#!/usr/bin/env python3
"""Offline workload-window slices of optimization process/GC/tick reports.

Reads JSON reports only: no RCON, SQL, /proc, jstat or build subprocesses.
Multiple runs are matched by scenario/repeat/phase and real input ordinal.
CPU/GC cumulative counters are never interpolated to a phase boundary.
"""
import argparse
import bisect
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORTS = (ROOT / "reports").resolve()
SERVERS = ("A", "B", "C")
METRICS = ("cpu_rss", "heap_gc", "tick")
GC_KEYS = ("YGC", "YGCT", "FGC", "FGCT", "CGC", "CGCT", "GCT")
WAL_KEYS = ("wal_writes", "wal_bytes", "wal_identical_skipped")
BUSINESS_KEYS = ("warmup_seconds", "steady_seconds", "low_flow_probes_per_path_per_repeat",
    "probe_idle_seconds", "probe_amount_FE", "poll_seconds", "feed_period_seconds",
    "input_attempt_FE", "sink_pull_request_FE", "resource")


def timestamp(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Report timestamp must include timezone")
    return date.timestamp()


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="microseconds")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values):
    values = sorted(v for v in values if finite(v))
    return {"samples": len(values), "mean": statistics.mean(values) if values else None,
        "min": min(values, default=None), "max": max(values, default=None),
        **{"p" + str(p): values[max(0, math.ceil(len(values) * p / 100) - 1)] if values else None
            for p in (50, 95, 99)}}


def safe_report_path(value, output=False):
    path = Path(value).resolve()
    if not path.is_relative_to(REPORTS) or path.suffix not in ((".json", ".csv") if output else (".json",)):
        raise ValueError("Only local reports/*.json inputs and reports JSON/CSV outputs are accepted")
    return path


def read_report(value, expected_kind=None):
    path = safe_report_path(value)
    raw = path.read_bytes()
    report = json.loads(raw)
    if expected_kind and report.get("report_kind") != expected_kind:
        raise ValueError("Unexpected report kind in " + str(path))
    evidence = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw), "label": report.get("label"), "passed": report.get("passed"),
        "failures": report.get("failures", []), "warnings": report.get("warnings", []),
        "conditions": report.get("conditions", {}), "coverage": report.get("coverage"),
        "identity": report.get("identity", {}), "hardware": report.get("hardware"),
        "measurement": report.get("measurement", {}), "source_provenance": report.get("source_provenance")}
    return report, evidence


def labeled(values, single=False):
    result = {}
    for value in values:
        label, separator, path = value.partition("=")
        if not separator or not label or not path or len(label) > 48:
            raise ValueError("Expected LABEL=reports/path.json")
        if single and label in result:
            raise ValueError("Duplicate benchmark label " + label)
        result.setdefault(label, []).append(path)
    return result


def make_phases(report, phases):
    """Recover observed stage boundaries, not unlogged initial idle or controls."""
    result = {}
    for sample in report.get("samples", []):
        scenario, repeat = sample.get("scenario"), sample.get("repeat")
        if scenario is None or repeat is None:
            continue
        for phase in phases:
            events = (sample.get("low_flow", {}).get("events", []) if phase == "low_flow" else
                sample.get("warmup_events", []) if phase == "warmup" else sample.get("events", []))
            inputs = sorted((e for e in events if e.get("kind") == "input" and finite(e.get("start"))),
                key=lambda e: e["start"])
            if not inputs:
                continue
            start = inputs[0]["start"]
            if phase == "warmup":
                seconds = sample.get("warmup", {}).get("seconds")
                if not finite(seconds):
                    continue
                end = start + seconds
                boundary = "First warmup input plus recorded drive duration; warmup drain excluded. First input follows drive entry by a small unlogged control interval."
            elif phase == "steady":
                end = sample.get("counter_end", {}).get("start")
                if not finite(end):
                    continue
                boundary = "First business input to final counter snapshot entry; excludes counter-start controls. Snapshot entry follows actual drive end by a small unlogged control interval."
            else:
                ends = [e["end"] for e in events if finite(e.get("end"))]
                if not ends:
                    continue
                end = max(ends)
                boundary = "First probe input to last recorded low-flow event; initial probe idle/control snapshots excluded."
            inputs = [e for e in inputs if start <= e["start"] < end]
            if not inputs or end <= start:
                continue
            grid = [e["start"] for e in inputs] + [end]
            if any(b <= a for a, b in zip(grid, grid[1:])):
                continue
            result[(scenario, repeat, phase)] = {"scenario": scenario, "repeat": repeat, "phase": phase,
                "start": start, "end": end, "seconds": end - start, "input_count": len(inputs), "grid": grid,
                "input_requested_FE": sum(e.get("requested", 0) for e in inputs),
                "input_accepted_FE": sum(e.get("amount", 0) for e in inputs),
                "sample_passed": sample.get("passed") is True, "sample_failure": sample.get("failure"),
                "boundary_method": boundary}
    return result


def progress(phase, relative_time):
    grid, count = phase["grid"], phase["input_count"]
    if relative_time <= grid[0]:
        return 0.0
    if relative_time >= grid[-1]:
        return float(count)
    index = bisect.bisect_right(grid, relative_time) - 1
    return index + (relative_time - grid[index]) / (grid[index + 1] - grid[index])


def at_progress(phase, ordinal):
    if ordinal >= phase["input_count"]:
        return phase["end"]
    index = max(0, int(math.floor(ordinal)))
    fraction = ordinal - index
    return phase["grid"][index] * (1 - fraction) + phase["grid"][index + 1] * fraction


def metric_points(benchmark, monitors, server, metric):
    points, rejected = [], []
    wanted = benchmark.get("identity", {}).get(server, {})
    for document, evidence in monitors:
        identity = document.get("identity", {}).get(server, {})
        if not wanted or identity.get("pid") != wanted.get("pid") or (
                wanted.get("argv_sha256") and identity.get("argv_sha256") != wanted["argv_sha256"]):
            rejected.append({"path": evidence["path"], "reason": "Benchmark/monitor JVM PID or argv hash differs"})
            continue
        for index, sample in enumerate(document.get("samples", [])):
            if sample.get("server") != server:
                continue
            ref = {"file_sha256": evidence["sha256"], "sample_index": index}
            if sample.get("error") or sample.get("pid") != wanted.get("pid"):
                rejected.append({**ref, "reason": sample.get("error", "Sample PID differs")})
                continue
            try:
                if metric == "tick":
                    lower, upper = timestamp(sample["utc_request_start"]), timestamp(sample["utc_reply_end"])
                    if not finite(sample.get("mc_recorded_tick_mean_ms")):
                        raise ValueError("Tick mean missing")
                    values = {key: sample.get(key) for key in ("mc_recorded_tick_mean_ms", "target_tickrate",
                        "state", "tick_window_p50_ms", "tick_window_p95_ms", "tick_window_p99_ms", "tick_window_samples", "rcon_ms")}
                else:
                    base, observer = timestamp(sample["utc"]), sample["observer_monotonic"]
                    if metric == "cpu_rss":
                        if not finite(sample.get("cpu_total_seconds")):
                            raise ValueError("CPU counter missing")
                        stop = sample.get("jstat_gc", {}).get("observer_start",
                            observer + sample.get("sample_duration_seconds", 0))
                        lower, upper = base, base + max(0, stop - observer)
                        values = {key: sample.get(key) for key in ("cpu_total_seconds", "rss_bytes", "fd_count", "threads")}
                    else:
                        gc = sample.get("jstat_gc", {})
                        if gc.get("error") or not gc.get("values"):
                            raise ValueError(gc.get("error", "jstat -gc missing"))
                        lower = base + gc["observer_start"] - observer
                        upper = base + gc["observer_end"] - observer
                        values = {**{key: gc["values"].get(key) for key in GC_KEYS},
                            **{key: sample.get(key) for key in ("heap_used_bytes", "heap_committed_bytes")}}
                if upper < lower:
                    raise ValueError("Observer read interval decreased")
                points.append({"lower": lower, "upper": upper, "values": values, "ref": ref,
                    "nominal_interval": document.get("conditions", {}).get("interval_seconds")})
            except (KeyError, ValueError, TypeError) as error:
                rejected.append({**ref, "reason": type(error).__name__ + ": " + str(error)})
    points.sort(key=lambda p: p["lower"])
    # Duplicate source paths/overlapping monitor copies do not create extra observations.
    unique = {}
    for point in points:
        unique[(point["ref"]["file_sha256"], point["ref"]["sample_index"])] = point
    return list(unique.values()), rejected


def contained(points, phase, anchor, margin, head_guard=0, input_start=None, input_end=None):
    start = phase["start"] + head_guard if input_start is None else at_progress(phase, input_start)
    end = phase["end"] if input_end is None else at_progress(phase, input_end)
    return [p for p in points if p["lower"] - anchor - margin >= start and
        p["upper"] - anchor + margin <= end]


def summarize(points, metric, phase, anchor):
    result = {"status": "OBSERVED" if points else "UNMEASURED", "samples": len(points),
        "phase_requested_seconds": phase["seconds"], "sample_refs": [p["ref"] for p in points]}
    if not points:
        return result
    first, last = points[0], points[-1]
    centers = [(p["lower"] + p["upper"]) / 2 for p in points]
    elapsed = centers[-1] - centers[0]
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    intervals = sorted({p["nominal_interval"] for p in points if finite(p["nominal_interval"])})
    result.update(first_read_utc=utc(first["lower"]), last_read_utc=utc(last["upper"]),
        first_input_progress_interval=[progress(phase, first[k] - anchor) for k in ("lower", "upper")],
        last_input_progress_interval=[progress(phase, last[k] - anchor) for k in ("lower", "upper")],
        sample_point_span_seconds=elapsed, sample_point_span_fraction_of_phase=elapsed / phase["seconds"],
        largest_sample_gap_seconds=max(gaps, default=None), nominal_sample_intervals_seconds=intervals,
        gaps_larger_than_2_5_intervals=sum(g > 2.5 * max(intervals) for g in gaps) if intervals else None,
        coverage_note="Point-span hull only; does not make heap/tick observations continuous or reconstruct missing samples.")
    if metric == "cpu_rss":
        for key in ("rss_bytes", "fd_count", "threads"):
            result[key + "_sample_distribution"] = distribution([p["values"].get(key) for p in points])
        if len(points) >= 2 and elapsed > 0:
            counters = [p["values"]["cpu_total_seconds"] for p in points]
            delta = counters[-1] - counters[0]
            if any(b < a for a, b in zip(counters, counters[1:])):
                result.update(status="INVALID_COUNTER", failure="Cumulative JVM CPU decreased")
            else:
                lower, upper = last["lower"] - first["upper"], last["upper"] - first["lower"]
                result["CPU_counter_slice"] = {"delta_seconds": delta, "observed_seconds": elapsed,
                    "elapsed_interval_seconds": [lower, upper], "process_percent": delta / elapsed * 100,
                    "process_percent_time_bounds": [delta / upper * 100, delta / lower * 100] if lower > 0 else None,
                    "scope": "All JVM threads; one CPU at 100%. Exact counter difference over these two read intervals; no boundary interpolation."}
        else:
            result["CPU_counter_slice"] = None
    elif metric == "heap_gc":
        for key in ("heap_used_bytes", "heap_committed_bytes"):
            result[key + "_sample_distribution"] = distribution([p["values"].get(key) for p in points])
        delta = {key: last["values"][key] - first["values"][key]
            if finite(first["values"].get(key)) and finite(last["values"].get(key)) else None for key in GC_KEYS}
        if any(p["values"].get(k) is not None and q["values"].get(k) is not None and q["values"][k] < p["values"][k]
                for p, q in zip(points, points[1:]) for k in GC_KEYS):
            result.update(status="INVALID_COUNTER", failure="Cumulative jstat GC decreased")
        result["GC_counter_slice"] = {"cumulative_delta": delta, "observed_seconds": elapsed,
            "elapsed_interval_seconds": [last["lower"] - first["upper"], last["upper"] - first["lower"]],
            "GCT_counter_fraction": delta["GCT"] / elapsed if elapsed > 0 and delta["GCT"] is not None else None,
            "scope": "jstat elapsed count/time counters (seconds), including concurrent work; not STW pause distribution or phase/tick CPU time."} if len(points) >= 2 else None
    else:
        result["queried_tick_window_means_ms"] = distribution([p["values"]["mc_recorded_tick_mean_ms"] for p in points])
        result["target_tickrates"] = sorted({p["values"]["target_tickrate"] for p in points if finite(p["values"].get("target_tickrate"))})
        states = {p["values"].get("state", "unknown") for p in points}
        result["states"] = {state: sum(p["values"].get("state", "unknown") == state for p in points) for state in sorted(states)}
        result["per_query_window_percentiles_sample_distributions_ms"] = {"p" + str(p):
            distribution([q["values"].get("tick_window_p" + str(p) + "_ms") for q in points]) for p in (50, 95, 99)}
        result["query_RTT_ms"] = distribution([p["values"].get("rcon_ms") for p in points])
        result["scope"] = "Samples of vanilla last-100-tick recorded work windows, rounded ~+/-0.05ms. Percentiles of query means or query-window percentiles are not phase-wide tick percentiles. Target rate is not actual TPS. Window wall-time age is unknown; head guard does not prove all 100 ticks are inside this phase. Whole-loop MSPT UNMEASURED."
    return result


def public_phase(phase):
    return {key: value for key, value in phase.items() if key != "grid"}


def wal_windows(benchmark):
    """Only instrumented cumulative WAL counters; absent baseline is never zero."""
    result = []
    for sample in benchmark.get("samples", []):
        first, last = sample.get("counter_start", {}), sample.get("counter_end", {})
        if not first or not last:
            continue
        row = {"scenario": sample.get("scenario"), "repeat": sample.get("repeat"),
            "phase": "steady_counter_snapshot_window", "sample_passed": sample.get("passed") is True,
            "fixed_business_input_attempts": sample.get("business", {}).get("input_attempts"),
            "fixed_business_accepted_input_events": sample.get("business", {}).get("accepted_input_events"),
            "fixed_business_input_attempt_FE": sample.get("business", {}).get("input_attempt_FE"),
            "fixed_business_accepted_FE": sample.get("business", {}).get("accepted_FE"),
            "per_server": {}, "summed_cumulative_delta": {}, "status": "UNMEASURED",
            "scope": "Benchmark's actual first/final ct_test status read intervals; includes ambient JVM work between reads. Independent of sidecar sampling. No SQL/WAL resource amounts added together."}
        for server in SERVERS:
            f, l = first.get("servers", {}).get(server, {}), last.get("servers", {}).get(server, {})
            values = {key: l.get("metrics", {}).get(key) - f.get("metrics", {}).get(key)
                if finite(f.get("metrics", {}).get(key)) and finite(l.get("metrics", {}).get(key)) else None for key in WAL_KEYS}
            row["per_server"][server] = {"cumulative_delta": values,
                "first_status_run_relative_interval": [f.get("start"), f.get("end")],
                "last_status_run_relative_interval": [l.get("start"), l.get("end")]}
        for key in WAL_KEYS:
            values = [row["per_server"][server]["cumulative_delta"][key] for server in SERVERS]
            row["summed_cumulative_delta"][key] = sum(values) if all(v is not None for v in values) else None
        if any(v is not None and v < 0 for x in row["per_server"].values() for v in x["cumulative_delta"].values()):
            row["status"] = "INVALID_COUNTER"
        elif all(v is not None for v in row["summed_cumulative_delta"].values()):
            row["status"] = "INSTRUMENTED_OBSERVED"
        result.append(row)
    return result


def build_summary(run_paths, process_paths, tick_paths, args):
    runs, provenance = {}, []
    for label, paths in run_paths.items():
        benchmark, evidence = read_report(paths[0])
        if benchmark.get("cluster") != "dev_three_v1":
            raise ValueError("Expected isolated dev_three_v1 benchmark report")
        provenance.append({"run": label, "role": "benchmark", **evidence})
        monitors = {}
        for metric, sources, kind in (("process", process_paths, "read_only_process_monitor"),
                ("tick", tick_paths, "read_only_minecraft_tick_monitor")):
            monitors[metric] = []
            for path in sources.get(label, []):
                document, monitor_evidence = read_report(path, kind)
                monitors[metric].append((document, monitor_evidence))
                provenance.append({"run": label, "role": metric, **monitor_evidence})
        if "utc" not in benchmark:
            raise ValueError("Benchmark UTC start missing for " + label)
        anchor = timestamp(benchmark["utc"])
        phases = make_phases(benchmark, args.phases)
        point_map, rejected = {}, {}
        for server in SERVERS:
            for metric in METRICS:
                documents = monitors["tick" if metric == "tick" else "process"]
                point_map[(server, metric)], rejected[(server, metric)] = metric_points(benchmark, documents, server, metric)
        runs[label] = {"benchmark": benchmark, "anchor": anchor, "phases": phases, "points": point_map, "rejected": rejected}
    report = {"schema_version": 1, "report_kind": "offline_common_monitor_windows",
        "utc_created": datetime.now(timezone.utc).isoformat(timespec="microseconds"), "provenance": provenance,
        "method": {"source": "JSON reports only; source snapshot SHA256 includes incomplete/failed reports.",
            "alignment": "Benchmark has only second-resolution UTC start, not an absolute monotonic anchor. Align observer UTC with run-relative events; no cross-JVM nanoTime arithmetic. Clock margin is an explicit approximation, not proof of an exact phase origin.",
            "benchmark_anchor_margin_seconds": args.clock_margin,
            "boundary_guard": "Include complete read intervals only, with clock margin on both sides. CPU interval ends before jstat starts; heap/GC uses -gc interval; tick uses RCON request/reply interval.",
            "matching": "Same scenario/repeat/phase and fixed requested input count/FE. Intersect actual sampled coverage, round inward to common real input boundaries. Low-flow progress follows actual probe inputs, not elapsed-duration percentages.",
            "counters": "CPU/GC deltas use only first/last real contained samples per run, so actual windows can be shorter than the common requested slice. Actual windows and refs retained; no interpolation/extrapolation.",
            "tick_phase_head_guard_seconds": args.tick_head_guard,
            "heap_tick_coverage": "A hull of sample times is not continuous coverage. Tick window age has no measured wall-time bound; no complete-phase or whole-loop MSPT / actual-TPS claim.",
            "WAL": "Baseline WAL count/time UNMEASURED. Instrumented C-B differences may be measured separately; no baseline zero implied.",
            "baseline_scale1000_idle": "Previously observed independent 118.000200710s / 862 DBtx = 7.30507232033 tx/s; not the entire 120s phase and not derived from this sidecar summary."},
        "runs": {}, "individual_windows": [], "common_windows": [], "warnings": []}
    for evidence in provenance:
        if evidence.get("passed") is not True:
            report["warnings"].append({"kind": "FAILED_OR_INCOMPLETE_SOURCE_RETAINED",
                "run": evidence["run"], "role": evidence["role"], "path": evidence["path"],
                "source_passed": evidence.get("passed"), "failures": evidence.get("failures", []),
                "scope": "Successful real samples retained only inside actual observed coverage; source failure is not converted to a complete phase or successful whole-monitor run."})
    for label, run in runs.items():
        benchmark = run["benchmark"]
        expected = {(s, r, p) for s in benchmark.get("conditions", {}).get("scenarios", [])
            for r in range(1, benchmark.get("conditions", {}).get("repeats", 0) + 1) for p in args.phases}
        report["runs"][label] = {"benchmark_passed": benchmark.get("passed"),
            "benchmark_failures": benchmark.get("failures", []), "benchmark_regressions": benchmark.get("regressions", []),
            "benchmark_UTC_anchor": benchmark["utc"], "alignment_is_approximate": True,
            "WAL_measurement_declared_by_driver": benchmark.get("measurement", {}).get("wal", "Not specified; no baseline zero assumed"),
            "WAL_status_snapshot_windows": wal_windows(benchmark),
            "missing_phase_units": [{"scenario": k[0], "repeat": k[1], "phase": k[2]} for k in sorted(expected - run["phases"].keys())],
            "rejected_monitor_samples": {s + ":" + m: values for (s, m), values in run["rejected"].items() if values}}
        for key, phase in run["phases"].items():
            for server in SERVERS:
                for metric in METRICS:
                    selected = contained(run["points"][(server, metric)], phase, run["anchor"], args.clock_margin,
                        args.tick_head_guard if metric == "tick" else 0)
                    report["individual_windows"].append({"run": label, "server": server, "metric": metric,
                        **public_phase(phase), "comparison_scope": "Individual observed stage slice; not independently a matched before/after comparison.",
                        "observed": summarize(selected, metric, phase, run["anchor"])})
    all_keys = set().union(*(run["phases"].keys() for run in runs.values()))
    for key in sorted(all_keys):
        for server in SERVERS:
            for metric in METRICS:
                group = {"scenario": key[0], "repeat": key[1], "phase": key[2], "server": server, "metric": metric,
                    "status": "NO_COMMON_MEASUREMENT", "runs": {}}
                report["common_windows"].append(group)
                if len(runs) < 2:
                    group["reason"] = "Only one run supplied; individual observations retained, no cross-run comparison"
                    continue
                if any(key not in run["phases"] or not run["phases"][key]["sample_passed"] for run in runs.values()):
                    group["reason"] = "Missing, unfinished or failed scenario/repeat/phase"
                    continue
                conditions = [tuple(run["benchmark"].get("conditions", {}).get(k) for k in BUSINESS_KEYS) for run in runs.values()]
                counts = {(run["phases"][key]["input_count"], run["phases"][key]["input_requested_FE"],
                    run["phases"][key]["input_accepted_FE"]) for run in runs.values()}
                if any(condition != conditions[0] for condition in conditions[1:]) or len(counts) != 1:
                    group["reason"] = "Fixed business input conditions/count/FE differ"
                    continue
                candidates = {label: contained(run["points"][(server, metric)], run["phases"][key], run["anchor"],
                    args.clock_margin, args.tick_head_guard if metric == "tick" else 0) for label, run in runs.items()}
                missing = [label for label, values in candidates.items() if len(values) < 2]
                if missing:
                    group.update(reason="Fewer than two contained real samples", missing_runs=missing)
                    continue
                cadences = [{p["nominal_interval"] for p in values} for values in candidates.values()]
                if any(cadence != cadences[0] for cadence in cadences[1:]):
                    group["reason"] = "Observer sampling cadence differs"
                    continue
                start = math.ceil(max(progress(runs[label]["phases"][key], values[0]["upper"] -
                    runs[label]["anchor"] + args.clock_margin) for label, values in candidates.items()))
                end = math.floor(min(progress(runs[label]["phases"][key], values[-1]["lower"] -
                    runs[label]["anchor"] - args.clock_margin) for label, values in candidates.items()))
                if end <= start:
                    group["reason"] = "Observed coverage has no inward-rounded common real-input interval"
                    continue
                group["common_input_boundary_interval"] = [start, end]
                group["common_requested_input_count"] = end - start
                for label, run in runs.items():
                    phase = run["phases"][key]
                    selected = contained(candidates[label], phase, run["anchor"], args.clock_margin,
                        input_start=start, input_end=end)
                    begin, finish = at_progress(phase, start), at_progress(phase, end)
                    group["runs"][label] = {"requested_slice_UTC": [utc(run["anchor"] + begin), utc(run["anchor"] + finish)],
                        "requested_slice_run_relative_seconds": [begin, finish],
                        "requested_slice_seconds": finish - begin,
                        "observed": summarize(selected, metric, phase, run["anchor"])}
                if any(value["observed"]["samples"] < 2 or value["observed"]["status"] != "OBSERVED" for value in group["runs"].values()):
                    group["reason"] = "Common input slice has fewer than two real contained samples or invalid counters; observations retained"
                else:
                    group["status"] = "COMMON_OBSERVED_SLICE"
    report["WAL_pairwise_comparisons"] = []
    labels = list(runs)
    for before_index, before in enumerate(labels):
        for after in labels[before_index + 1:]:
            previous = {(x["scenario"], x["repeat"]): x for x in report["runs"][before]["WAL_status_snapshot_windows"]}
            current = {(x["scenario"], x["repeat"]): x for x in report["runs"][after]["WAL_status_snapshot_windows"]}
            for key in sorted(previous.keys() | current.keys()):
                f, l = previous.get(key), current.get(key)
                entry = {"before_run": before, "after_run": after, "scenario": key[0], "repeat": key[1],
                    "status": "UNMEASURED_OR_UNMATCHED", "after_minus_before": None}
                if f and l and f["status"] == l["status"] == "INSTRUMENTED_OBSERVED" and f["sample_passed"] and l["sample_passed"] and \
                        tuple(f[k] for k in ("fixed_business_input_attempts", "fixed_business_accepted_input_events",
                            "fixed_business_input_attempt_FE", "fixed_business_accepted_FE")) == \
                        tuple(l[k] for k in ("fixed_business_input_attempts", "fixed_business_accepted_input_events",
                            "fixed_business_input_attempt_FE", "fixed_business_accepted_FE")) and \
                        all(runs[before]["benchmark"].get("conditions", {}).get(k) ==
                            runs[after]["benchmark"].get("conditions", {}).get(k) for k in BUSINESS_KEYS):
                    entry.update(status="INSTRUMENTED_FIXED_BUSINESS_COUNTER_COMPARISON", after_minus_before={
                        k: l["summed_cumulative_delta"][k] - f["summed_cumulative_delta"][k] for k in WAL_KEYS})
                report["WAL_pairwise_comparisons"].append(entry)
    # A missing sample in one run must not erase evidence that another pair
    # genuinely shares, or turn that pair's observations into three-way coverage.
    report["pairwise_common_windows"] = []
    if len(runs) > 2:
        for before_index, before in enumerate(labels):
            for after in labels[before_index + 1:]:
                pair = (before, after)
                subset = build_summary({label: run_paths[label] for label in pair},
                    {label: process_paths.get(label, []) for label in pair},
                    {label: tick_paths.get(label, []) for label in pair}, args)
                known_hashes = {e["path"]: e["sha256"] for e in provenance}
                if any(known_hashes.get(e["path"]) != e["sha256"] for e in subset["provenance"]):
                    raise ValueError("An input report changed while creating paired windows")
                report["pairwise_common_windows"].append({"run_labels": list(pair),
                    "scope": "Only this named pair shares these input-aligned observed slices. They cannot backfill missing third-run observations.",
                    "windows": subset["common_windows"], "warnings": subset["warnings"]})
    return report


def save_csv(report, path):
    fields = ("scope", "scenario", "repeat", "phase", "server", "metric", "run", "status", "group_status", "reason", "samples",
        "first_read_utc", "last_read_utc", "sample_point_span_seconds", "CPU_process_percent",
        "heap_used_sample_mean_bytes", "heap_used_sample_max_bytes", "GC_GCT_delta_seconds", "queried_tick_window_mean_ms")
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        groups = [("individual", row, {row["run"]: {"observed": row["observed"]}}) for row in report["individual_windows"]]
        groups += [("common", row, row["runs"] or {"ALL_SUPPLIED": {"observed": {"status": "UNMEASURED"}}})
            for row in report["common_windows"]]
        groups += [("pairwise:" + "+".join(pair["run_labels"]), row,
            row["runs"] or {"PAIR_SUPPLIED": {"observed": {"status": "UNMEASURED"}}})
            for pair in report.get("pairwise_common_windows", []) for row in pair["windows"]]
        for scope, group, runs in groups:
            for label, run in runs.items():
                observed = run["observed"]
                row = {"scope": scope, "run": label, **{k: group[k] for k in ("scenario", "repeat", "phase", "server", "metric")},
                    "group_status": group.get("status"), "reason": group.get("reason"),
                    **{k: observed.get(k) for k in ("status", "samples", "first_read_utc", "last_read_utc", "sample_point_span_seconds")},
                    "CPU_process_percent": (observed.get("CPU_counter_slice") or {}).get("process_percent"),
                    "heap_used_sample_mean_bytes": observed.get("heap_used_bytes_sample_distribution", {}).get("mean"),
                    "heap_used_sample_max_bytes": observed.get("heap_used_bytes_sample_distribution", {}).get("max"),
                    "GC_GCT_delta_seconds": (observed.get("GC_counter_slice") or {}).get("cumulative_delta", {}).get("GCT"),
                    "queried_tick_window_mean_ms": observed.get("queried_tick_window_means_ms", {}).get("mean")}
                writer.writerow(row)


def self_test():
    phase = {"start": 10.0, "end": 30.0, "seconds": 20.0, "input_count": 3, "grid": [10.0, 15.0, 28.0, 30.0]}
    assert progress(phase, 15) == 1 and progress(phase, 29) == 2.5
    assert at_progress(phase, 2.5) == 29
    points = [{"lower": t, "upper": t + .1, "nominal_interval": 5,
        "values": {"cpu_total_seconds": c}, "ref": {"sample_index": i}} for i, (t, c) in enumerate(((9, 1), (16, 3), (26, 5), (31, 6)))]
    selected = contained(points, phase, 0, 1)
    assert len(selected) == 2
    observed = summarize(selected, "cpu_rss", phase, 0)
    assert abs(observed["CPU_counter_slice"]["process_percent"] - 20) < .001
    assert len(contained(points, phase, 0, 1, input_start=1, input_end=2)) == 2
    first = {"servers": {s: {"metrics": {k: 10 for k in WAL_KEYS}} for s in SERVERS}}
    last = {"servers": {s: {"metrics": {k: 12 for k in WAL_KEYS}} for s in SERVERS}}
    sample = {"scenario": "same", "repeat": 1, "counter_start": first, "counter_end": last}
    assert wal_windows({"samples": [sample]})[0]["summed_cumulative_delta"]["wal_writes"] == 6
    assert wal_windows({"samples": [{**sample, "counter_start": {"servers": {}}}]})[0]["status"] == "UNMEASURED"
    try:
        safe_report_path(ROOT / "src/main/java/invalid.json")
    except ValueError:
        pass
    else:
        raise AssertionError("Non-report input accepted")
    print("Offline window/progress/counter checks passed; no backend/process access.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", default=[], metavar="LABEL=BENCHMARK_JSON")
    parser.add_argument("--process", action="append", default=[], metavar="LABEL=PROCESS_MONITOR_JSON")
    parser.add_argument("--tick", action="append", default=[], metavar="LABEL=TICK_MONITOR_JSON")
    parser.add_argument("--phases", default="low_flow,warmup,steady")
    parser.add_argument("--clock-margin", type=float, default=1.0, help="Explicit approximate benchmark UTC origin uncertainty, seconds")
    parser.add_argument("--tick-head-guard", type=float, default=10.0, help="Exclude initial phase queries; not a proven bound on last-100-tick window age")
    parser.add_argument("--output", help="reports/*.json; default timestamped summary")
    parser.add_argument("--csv", help="Optional reports/*.csv")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    try:
        args.phases = list(dict.fromkeys(args.phases.split(",")))
        if not args.phases or any(p not in ("low_flow", "warmup", "steady") for p in args.phases):
            raise ValueError("Supported phases: low_flow,warmup,steady")
        if not .5 <= args.clock_margin <= 60 or not 0 <= args.tick_head_guard <= 120:
            raise ValueError("Clock/tick guard outside bounded range")
        runs, process, ticks = labeled(args.run, True), labeled(args.process), labeled(args.tick)
        if not runs or set(process) - set(runs) or set(ticks) - set(runs):
            raise ValueError("Supply benchmarks for every monitor label")
        default = REPORTS / ("optimization-monitor-summary-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
        output = safe_report_path(args.output or default, True)
        if output.suffix != ".json":
            raise ValueError("Summary must be JSON")
        inputs = {safe_report_path(path) for sources in (runs, process, ticks) for paths in sources.values() for path in paths}
        if output in inputs:
            raise ValueError("Summary output cannot overwrite an input report")
        csv_path = None
        if args.csv:
            csv_path = safe_report_path(args.csv, True)
            if csv_path.suffix != ".csv":
                raise ValueError("CSV output must have .csv extension")
            if csv_path in {path.with_suffix(".csv") for path in inputs}:
                raise ValueError("CSV output cannot overwrite an input report's raw sidecar CSV")
        report = build_summary(runs, process, ticks, args)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        temporary.replace(output)
        if csv_path:
            save_csv(report, csv_path)
        print(json.dumps({"saved": str(output), "runs": list(runs),
            "individual_windows": len(report["individual_windows"]),
            "common_observed_slices": sum(g["status"] == "COMMON_OBSERVED_SLICE" for g in report["common_windows"]),
            "common_unmeasured_slices": sum(g["status"] != "COMMON_OBSERVED_SLICE" for g in report["common_windows"]),
            "pairwise_common_observed_slices": {"+".join(pair["run_labels"]): sum(
                g["status"] == "COMMON_OBSERVED_SLICE" for g in pair["windows"])
                for pair in report.get("pairwise_common_windows", [])}}))
        return 0
    except (ValueError, KeyError, OSError, TypeError) as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
