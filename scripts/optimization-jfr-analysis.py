#!/usr/bin/env python3
"""Bounded, offline JFR evidence for matched 1000-endpoint observed windows.

Default: print a plan from saved JSON only. --parse-jfr explicitly starts a
single-CPU Java 21 RecordingFile reader; use it only after timed work stops.
No attach, JFR.start, /proc, RCON, SQL, Docker, build or network operations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
BASE_REV = "87bf217fcaffcceb2629c36bb54d5158b9f461e8"
NEW_REV = "75392af252744f240253d134d1da565a49b2cc9f"
DEFAULTS = {
    "baseline_jfr": "reports/raw/opt-baseline-87bf217.jfr",
    "current_jfr": "reports/raw/opt-fast-75392af.jfr",
    "baseline_monitor": "reports/optimization-scale-baseline-scale-late-20261006T100021Z-09d5b0.json",
    "current_monitor": "reports/optimization-scale-fast-scale-fixed-75392af-20261006T135146Z-3eebad.json",
}
LIMITATIONS = [
    "Only conservative inner intervals of post-reset observed 1000 OFF/ACTIVE are selected; not whole nominal 120-second phases.",
    "The monitor's reset marker is indirect. Both archived drivers reset metrics after five-second warmup; raw request/reply and reset evidence remain in the plan.",
    "JFR Instant and observer UTC are aligned as same-host wall clocks. No cross-JVM nanoTime subtraction or clock interpolation is used; wall/monotonic drift is checked, not corrected.",
    "The original RCON buffer has no body nonce; saved replies do not independently attest per-event response attribution.",
    "Execution/native samples are separate counts, sampling fractions and samples/second, never measured CPU milliseconds, tick duration or causal attribution.",
    "Recorded GC/park/monitor/sleep durations are threshold/configuration-dependent. Edge-crossing duration events are excluded, and nested GC phases are not added together.",
    "ObjectAllocationSample weights are sampled allocation estimates, not exact object counts, all allocation bytes or retained heap.",
    "Source references use the declared frozen revision and recorded line table; the legacy harness has no class-loader source attestation.",
    "No whole-server wall MSPT, actual TPS, per-tick p95 attribution, factory-container persistence or longitudinal capacity result is created.",
]


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("UTC timestamps must contain an explicit timezone")
    return result.astimezone(timezone.utc)


def iso(value):
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def report_path(value, suffix, limit):
    path = (ROOT / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if not path.is_relative_to(REPORTS.resolve()) or path.suffix != suffix:
        raise ValueError(f"Expected a local reports/*{suffix} path: {value}")
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f"Missing input or size limit exceeded: {path}")
    return path


def evidence(path, with_hash=False):
    result = {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size}
    if with_hash:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1 << 20), b""):
                digest.update(chunk)
        result["sha256"] = digest.hexdigest()
    return result


def windows(path, args):
    report = json.loads(path.read_text())
    if report.get("report_kind") != "read_only_single_perf_scale_monitor":
        raise ValueError(f"Unexpected monitor schema: {path}")
    samples = report.get("samples", [])
    if not 1 <= len(samples) <= 20000:
        raise ValueError("Monitor sample count outside bounds")
    groups = {}
    for sample in samples:
        groups.setdefault(sample.get("observed_phase_id"), []).append(sample)
    selected = []
    expected_pid = report.get("identity", {}).get("pid")
    expected_starttime = report.get("identity", {}).get("starttime_ticks")
    for mode in ("OFF_observed", "ACTIVE_observed"):
        candidates = []
        for phase, group in groups.items():
            group = sorted(group, key=lambda row: row["round"])
            first, last = group[0], group[-1]
            if first.get("observed_mode") != mode or not first.get("window_reset_observed"):
                continue
            if first.get("bulk", {}).get("metrics", {}).get("count") != 1000:
                continue
            if any(row.get("error") or row.get("observed_mode") != mode for row in group):
                raise ValueError("Mixed/failed sample inside selected monitor phase")
            for index, row in enumerate(group):
                status, bulk = row["status"]["metrics"], row["bulk"]["metrics"]
                if any(bulk.get(key) != 1000 for key in ("count", "registered", "bound")):
                    raise ValueError("1000 registered/bound endpoint evidence is incomplete")
                if status.get("registered_loaded_endpoints") != 1000 or status.get("active_endpoints") != (1000 if mode == "ACTIVE_observed" else 0):
                    raise ValueError("Loaded/active endpoint evidence does not match phase")
                if expected_starttime is not None and row.get("proc", {}).get("starttime_ticks") != expected_starttime:
                    raise ValueError("Monitor JVM identity changed")
                if index and (row["round"] != group[index-1]["round"] + 1 or row.get("window_reset_observed")):
                    raise ValueError("Sample gap or extra reset inside phase")
                if index and row["status"]["observer_start"] - group[index-1]["status"]["observer_start"] > 5:
                    raise ValueError("Monitor gap exceeds five seconds")
            start = instant(first["status"]["utc_reply_end"])
            end = instant(last["status"]["utc_request_start"])
            seconds = (end-start).total_seconds()
            if not args.min_window_seconds <= seconds <= args.max_window_seconds:
                continue
            offsets = [instant(row["status"]["utc_request_start"]).timestamp()-row["status"]["observer_start"] for row in group]
            offset_range_ms = (max(offsets)-min(offsets))*1000
            if offset_range_ms > args.max_clock_drift_ms:
                raise ValueError("Observer UTC/monotonic offset drift exceeds limit; no clock correction attempted")
            prior = next((row for row in samples if row["round"] == first["round"]-1), None)
            counters = {}
            for key in ("db_transactions", "db_deadlock_retries", "transactions", "errors", "queue_rejected", "quarantined"):
                before, after = first["status"]["metrics"].get(key), last["status"]["metrics"].get(key)
                if finite(before) and finite(after):
                    if after < before:
                        raise ValueError("Cumulative monitor counter decreased")
                    counters[key] = after-before
            candidates.append({"name": mode.removesuffix("_observed"), "endpoints": 1000,
                "phase_id": phase, "first_round": first["round"], "last_round": last["round"],
                "monitor_samples": len(group), "start_utc_inclusive": iso(start), "end_utc_exclusive": iso(end),
                "inner_utc_seconds": seconds,
                "outer_first_request_utc": first["status"]["utc_request_start"],
                "outer_last_reply_utc": last["status"]["utc_reply_end"],
                "status_request_monotonic_span_seconds": last["status"]["observer_start"]-first["status"]["observer_start"],
                "utc_monotonic_offset_range_ms": offset_range_ms, "first_reset_observed": True,
                "reset_interval": {"previous_request_utc": prior["status"]["utc_request_start"] if prior else None,
                    "first_reply_utc": first["status"]["utc_reply_end"]},
                "counter_deltas_between_status_snapshots": counters,
                "counter_delta_scope": "Snapshot deltas bracket the outer uncertain request/reply interval, not exact counters for the inner JFR interval.",
                "jvm_pid": expected_pid})
        if len(candidates) != 1:
            raise ValueError(f"Expected exactly one post-reset stable 1000 {mode} window, found {len(candidates)}")
        selected.extend(candidates)
    return {"monitor": evidence(path), "monitor_identity": report.get("identity"), "windows": selected}


def compare_recordings(recordings):
    result = []
    for mode in ("OFF", "ACTIVE"):
        pair = [next(row for row in recordings[label]["windows"] if row["name"] == mode) for label in ("baseline", "current")]
        row = {"mode": mode, "comparisons_are_descriptive_not_causal": True}
        for label, window in zip(("baseline", "current"), pair):
            main = window["sampling"].get("jdk.ExecutionSample:MAIN", {})
            count, runtime = main.get("samples", 0), main.get("runtime_tick_inclusive_samples", 0)
            row[label] = {"window_seconds": window["seconds"], "main_execution_samples": count,
                "runtime_tick_inclusive_samples": runtime,
                "runtime_fraction_of_main_execution_samples": runtime/count if count else None,
                "main_execution_samples_per_second": count/window["seconds"],
                "recorded_gc": window["duration_events"].get("jdk.GarbageCollection:GLOBAL"),
                "recorded_top_level_gc_pauses": window["duration_events"].get("jdk.GCPhasePause:GLOBAL")}
        result.append(row)
    return result


def parse_recording(label, jfr, revision, plan, args, directory):
    helper = ROOT / "scripts/OptimizationJfr.java"
    output = directory / f"{label}.json"
    command = [str(Path(args.java).resolve()), "-Xmx384m", "-XX:ActiveProcessorCount=1", "--add-modules", "jdk.jfr", "--source", "21", str(helper),
        str(jfr), str(output), str(args.max_jfr_mib*1024*1024), str(args.max_events), str(args.top), str(args.max_frames),
        str(args.max_stacks), str(args.max_methods), str(args.max_output_mib*1024*1024), revision]
    for window in plan["windows"]:
        command.extend((window["name"], window["start_utc_inclusive"], window["end_utc_exclusive"]))
    stamp = (jfr.stat().st_size, jfr.stat().st_mtime_ns)
    with (directory / f"{label}.stderr").open("wb") as error_log:
        completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=error_log, timeout=args.timeout_seconds, check=False)
    if completed.returncode:
        raise ValueError("Java reader failed: " + (directory / f"{label}.stderr").read_bytes()[:4096].decode(errors="replace"))
    if stamp != (jfr.stat().st_size, jfr.stat().st_mtime_ns):
        raise ValueError("Recording changed during offline read")
    if not output.is_file() or output.stat().st_size > args.max_output_mib*1024*1024:
        raise ValueError("Reader output exceeds limit")
    result = json.loads(output.read_text())
    expected_pid = plan["monitor_identity"].get("pid")
    pids = {str(value["pid"]) for value in result.get("jvm_information", []) if "pid" in value}
    if pids and pids != {str(expected_pid)}:
        raise ValueError("JFR JVMInformation PID does not match monitor")
    result["monitor_pid_match"] = bool(pids and str(expected_pid) in pids)
    concerns = []
    if not pids:
        concerns.append("JVMInformation PID was not recorded; monitor/JFR PID identity is not independently confirmed.")
    if result.get("all_recording_event_counts", {}).get("jdk.DataLoss", 0):
        concerns.append("DataLoss events exist in the recording; their timestamps do not prove all lost events fall outside selected windows.")
    if any(len(values) > 1 for values in result.get("observed_active_settings", {}).values()):
        concerns.append("Relevant recording settings changed somewhere in the file; sampling counts are not normalized to a known constant window-local sampling period.")
    for window in result["windows"]:
        main = window["sampling"].get("jdk.ExecutionSample:MAIN", {})
        if main.get("samples", 0) < 100 or main.get("runtime_tick_inclusive_samples", 0) < 20:
            concerns.append(window["name"]+": sparse main/Runtime execution samples; percentile attribution and stable hotspot rankings are not established.")
        if any(bucket.get("truncated_stack_samples", 0) for bucket in window["sampling"].values()):
            concerns.append(window["name"]+": recorded/capped stack truncation exists; inclusive method coverage is incomplete.")
    result["coverage_concerns"] = concerns
    result["input"] = evidence(jfr, with_hash=True)
    result["reader_source"] = evidence(helper, with_hash=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in DEFAULTS.items():
        parser.add_argument("--"+name.replace("_", "-"), default=default)
    parser.add_argument("--baseline-revision", default=BASE_REV)
    parser.add_argument("--current-revision", default=NEW_REV)
    parser.add_argument("--parse-jfr", action="store_true", help="Start the offline Java reader; only after timed work has stopped")
    parser.add_argument("--java", default=str(ROOT/"scratch/jdk/jdk-21.0.8+9/bin/java"))
    parser.add_argument("--output", help="New reports/*.json file; never overwrite saved evidence")
    parser.add_argument("--max-jfr-mib", type=int, default=64)
    parser.add_argument("--max-output-mib", type=int, default=8)
    parser.add_argument("--max-events", type=int, default=5000000)
    parser.add_argument("--max-stacks", type=int, default=2048)
    parser.add_argument("--max-methods", type=int, default=16384)
    parser.add_argument("--max-frames", type=int, default=64)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--min-window-seconds", type=float, default=115)
    parser.add_argument("--max-window-seconds", type=float, default=125)
    parser.add_argument("--max-clock-drift-ms", type=float, default=50)
    args = parser.parse_args()
    if not (1 <= args.max_jfr_mib <= 256 and 1 <= args.max_output_mib <= 32 and 1 <= args.max_events <= 20000000
            and 1 <= args.max_stacks <= 4096 and 1 <= args.max_methods <= 32768 and 1 <= args.max_frames <= 96
            and 1 <= args.top <= 100 and 1 <= args.timeout_seconds <= 60
            and 5 <= args.min_window_seconds <= args.max_window_seconds <= 600 and 1 <= args.max_clock_drift_ms <= 1000):
        raise ValueError("Analysis limits outside accepted bounds")
    target = None
    if args.output:
        target = (ROOT/args.output).resolve()
        if not target.is_relative_to(REPORTS.resolve()) or target.suffix != ".json" or target.exists():
            raise ValueError("Output must be a new reports/*.json file")
    plans, paths = {}, {}
    for label in ("baseline", "current"):
        monitor = report_path(getattr(args, label+"_monitor"), ".json", 8*1024*1024)
        paths[label] = report_path(getattr(args, label+"_jfr"), ".jfr", args.max_jfr_mib*1024*1024)
        plans[label] = windows(monitor, args)
        plans[label]["recording"] = evidence(paths[label])
        plans[label]["declared_source_revision"] = getattr(args, label+"_revision")
    if paths["baseline"] == paths["current"]:
        raise ValueError("Baseline and current recordings must differ")
    report = {"schema_version": 1, "report_kind": "offline_matched_scale_jfr_evidence", "analysis_executed": False,
        "window_policy": "Half-open first status reply end to last status request start; stable post-reset 1000 endpoints only.",
        "plans": plans, "limitations": LIMITATIONS,
        "limits": {name: getattr(args, name) for name in ("max_jfr_mib", "max_output_mib", "max_events", "max_stacks", "max_methods", "max_frames", "top", "timeout_seconds")}}
    if args.parse_jfr:
        with tempfile.TemporaryDirectory(prefix="ct-offline-jfr-") as temporary:
            directory = Path(temporary)
            report["recordings"] = {label: parse_recording(label, paths[label], getattr(args, label+"_revision"), plans[label], args, directory)
                for label in ("baseline", "current")}
        report["analysis_executed"] = True
        report["sampling_comparison"] = compare_recordings(report["recordings"])
        report["generated_utc"] = iso(datetime.now(timezone.utc))
    encoded = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    if len(encoded.encode()) > args.max_output_mib*1024*1024:
        raise ValueError("Combined JSON output exceeds limit")
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x") as destination:
            destination.write(encoded)
        print(str(target.relative_to(ROOT)))
    else:
        print(encoded, end="")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"OFFLINE_JFR_ANALYSIS_FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
