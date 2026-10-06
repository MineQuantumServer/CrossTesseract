#!/usr/bin/env python3
"""Read-only 2s sampler of the existing isolated single-perf JVM.

Uses ct_test pid once, then only ct_test status and bulk-status. Observed
OFF/ACTIVE segments are partial windows, not reconstructed full benchmark phases.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from rcon import command

ROOT = Path(__file__).resolve().parents[1]
PORT = 25578
helper_spec = importlib.util.spec_from_file_location("ct_scale_proc_helpers", ROOT / "scripts/optimization-monitor.py")
helpers = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(helpers)
COUNTERS = ("db_transactions", "db_deadlock_retries", "transactions", "errors", "queue_rejected", "quarantined")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def numbers(reply):
    return {key: float(value) if any(marker in value for marker in ".eE") else int(value) for key, value in
        re.findall(r"([A-Za-z_]\w*)=(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?=[, }\r\n]|$)", reply)}


def observed_mode(status, bulk):
    count = bulk.get("count")
    if not count or bulk.get("registered") != count or bulk.get("bound") != count:
        return "setup_or_transition"
    active = status.get("active_endpoints")
    if active == 0:
        return "OFF_observed"
    if active == count:
        return "ACTIVE_observed"
    return "partial_or_other_workload"


class ScaleMonitor:
    def __init__(self, args):
        self.args = args
        self.start = time.monotonic()
        stem = "optimization-scale-" + args.label + "-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
        self.path = ROOT / "reports" / (stem + ".json")
        self.csv_path = self.path.with_suffix(".csv")
        self.previous = None
        self.phase = 0
        self.next_jstat = 0
        self.identity = {}
        self.report = {"schema_version": 1, "report_kind": "read_only_single_perf_scale_monitor", "label": args.label,
            "utc_start": utc_now(), "observer_monotonic_start": self.start,
            "conditions": {"port": PORT, "seconds": args.seconds, "interval_seconds": args.interval,
                "jstat_every_seconds": args.jstat_every, "rcon_timeout_seconds": args.rcon_timeout,
                "jstat_timeout_seconds": args.jstat_timeout},
            "coverage": {"earlier_intervals": "UNMEASURED", "note": args.coverage_note,
                "policy": "Only observed consecutive sample intervals. Mode/reset markers do not establish exact warmup or 120-second benchmark boundaries."},
            "measurement": {"DBtransactions": "ct_test status cumulative successful database transactions; difference only between observed snapshots",
                "SQL_statements": "UNMEASURED here; no SQL query or monitoring configuration change",
                "mode": "Inferred from bulk count/registered/bound and active_endpoints, not an independent authoritative bulk-active flag",
                "reset": "A drop in tick_ms_samples marks reset-metrics observed between requests; earlier/unsampled boundary remains uncertain",
                "tick_ms": "Existing mod RuntimeService tick histogram, not whole-Minecraft wall MSPT",
                "GC": "Optional jstat -gc/-gcutil raw output and cumulative counters; no JFR",
                "observer": "One Python monotonic observer; separate request/reply intervals for status and bulk-status"},
            "samples": [], "warnings": [], "failures": [], "passed": False}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(self.path)

    def issue(self, text):
        started = time.monotonic()
        result = {"observer_start": started, "utc_request_start": utc_now(), "command": "ct_test " + text}
        result["reply"] = command(PORT, result["command"], timeout=self.args.rcon_timeout)
        result["observer_end"] = time.monotonic()
        result["utc_reply_end"] = utc_now()
        result["rcon_ms"] = (result["observer_end"] - started) * 1000
        if "ERROR " in result["reply"]:
            raise RuntimeError(result["reply"])
        result["metrics"] = numbers(result["reply"])
        return result

    def preflight(self):
        selected = {}
        path = ROOT / "run-perf/cross-tesseract.properties"
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith(("#", "!")):
                key, value = line.split("=", 1)
                if key.strip() in ("cluster.id", "server.id", "backend.enabled", "mysql.url", "mysql.user", "redis.uri"):
                    selected[key.strip()] = value.strip()
        if (selected.get("cluster.id") not in ("dev_perf_v1", "dev_perfv1") or selected.get("backend.enabled") != "true"
                or not selected.get("mysql.url", "").startswith("jdbc:mysql://127.0.0.1:13306/cross_tesseract?")
                or selected.get("mysql.user") != "ct_dev" or selected.get("redis.uri") != "redis://127.0.0.1:16379"):
            raise ValueError("Refusing non-isolated perf configuration")
        pid_reply = self.issue("pid")["reply"]
        match = re.fullmatch(r"PID (\d+)\s*", pid_reply)
        if not match:
            raise ValueError("Cannot locate real perf JVM")
        pid = int(match[1])
        proc = Path(f"/proc/{pid}")
        java = (proc / "exe").resolve()
        if java.name != "java":
            raise ValueError("RCON PID is not Java")
        jstat = java.parent / "jstat"
        if not jstat.is_file() or not os.access(jstat, os.X_OK):
            jstat = ROOT / "scratch/jdk/jdk-21.0.8+9/bin/jstat"
        self.identity = {"pid": pid, "cluster": selected["cluster.id"], "server_id": selected.get("server.id"),
            "starttime_ticks": helpers.parse_stat((proc / "stat").read_text())["starttime_ticks"],
            "java_executable": str(java), "argv_sha256": hashlib.sha256((proc / "cmdline").read_bytes()).hexdigest(),
            "jstat": str(jstat) if jstat.is_file() and os.access(jstat, os.X_OK) else None}
        self.report["identity"] = self.identity

    def jstat(self, option):
        result = {"option": option, "observer_start": time.monotonic()}
        try:
            run = subprocess.run([self.identity["jstat"], option, str(self.identity["pid"])],
                capture_output=True, text=True, timeout=self.args.jstat_timeout, env=dict(os.environ, LC_ALL="C"))
            result.update(stdout=run.stdout, stderr=run.stderr, exit_code=run.returncode)
            if run.returncode:
                raise RuntimeError("jstat exit " + str(run.returncode))
            result["values"] = helpers.parse_jstat(run.stdout)
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as error:
            result["error"] = type(error).__name__ + ": " + str(error)
        result["observer_end"] = time.monotonic()
        return result

    def sample(self, index):
        started = time.monotonic()
        result = {"round": index, "utc": utc_now(), "observer_start": started, "offset_seconds": started - self.start}
        try:
            proc = Path(f"/proc/{self.identity['pid']}")
            stat = helpers.parse_stat((proc / "stat").read_text())
            if stat["starttime_ticks"] != self.identity["starttime_ticks"]:
                raise RuntimeError("Perf JVM identity changed")
            result["status"] = self.issue("status")
            if "STATUS online" not in result["status"]["reply"]:
                raise RuntimeError("Perf backend is not online")
            result["bulk"] = self.issue("bulk-status")
            result["proc"] = dict(stat, **helpers.parse_status((proc / "status").read_text()),
                fd_count=len(list((proc / "fd").iterdir())))
            status, bulk = result["status"]["metrics"], result["bulk"]["metrics"]
            if "db_transactions" not in status or "count" not in bulk:
                raise ValueError("Required status/bulk counter missing")
            result["observed_mode"] = observed_mode(status, bulk)
            reset = bool(self.previous and status.get("tick_ms_samples", 0) < self.previous["status"]["metrics"].get("tick_ms_samples", 0))
            result["window_reset_observed"] = reset
            signature = (bulk.get("count"), result["observed_mode"])
            previous_signature = (self.previous["bulk"]["metrics"].get("count"), self.previous["observed_mode"]) if self.previous else None
            if signature != previous_signature or reset:
                self.phase += 1
            result["observed_phase_id"] = self.phase
            if self.previous:
                duration = started - self.previous["observer_start"]
                cpu = result["proc"]["cpu_total_seconds"] - self.previous["proc"]["cpu_total_seconds"]
                result["proc"]["cpu_process_percent"] = cpu / duration * 100
                result["sample_interval_seconds"] = duration
                result["counter_delta_since_previous"] = {key: status[key] - self.previous["status"]["metrics"][key]
                    for key in COUNTERS if key in status and key in self.previous["status"]["metrics"]}
                if any(value < 0 for value in result["counter_delta_since_previous"].values()):
                    raise RuntimeError("Cumulative counters decreased")
            if self.args.jstat_every and self.identity["jstat"] and started >= self.next_jstat:
                result["jstat_gc"] = self.jstat("-gc")
                result["jstat_gcutil"] = self.jstat("-gcutil")
                result["heap"] = helpers.heap_bytes(result["jstat_gc"].get("values", {}))
                self.next_jstat = started + self.args.jstat_every
            if helpers.parse_stat((proc / "stat").read_text())["starttime_ticks"] != self.identity["starttime_ticks"]:
                raise RuntimeError("Perf JVM identity changed during sample")
            self.previous = result
        except (OSError, RuntimeError, ValueError, IndexError) as error:
            result["error"] = type(error).__name__ + ": " + str(error)
        result["observer_end"] = time.monotonic()
        result["sample_duration_seconds"] = result["observer_end"] - started
        return result

    def summarize(self):
        phases = {}
        for sample in self.report["samples"]:
            if "error" not in sample:
                phases.setdefault(sample["observed_phase_id"], []).append(sample)
        summaries = []
        for phase, records in phases.items():
            first, last = records[0], records[-1]
            before, after = first["status"]["metrics"], last["status"]["metrics"]
            db_delta = {key: after[key] - before[key] for key in COUNTERS if key in before and key in after}
            elapsed = last["status"]["observer_end"] - first["status"]["observer_end"]
            bulk_first, bulk_last = first["bulk"]["metrics"], last["bulk"]["metrics"]
            bulk_delta = {key: bulk_last[key] - bulk_first[key] for key in
                ("accepted", "extracted", "fixture_ms_total", "fixture_ticks") if key in bulk_first and key in bulk_last}
            summaries.append({"observed_phase_id": phase, "bulk_count": bulk_first.get("count"),
                "mode": first["observed_mode"], "samples": len(records),
                "first_status_request_utc": first["status"]["utc_request_start"],
                "last_status_reply_utc": last["status"]["utc_reply_end"],
                "observed_seconds": elapsed, "time_lower_seconds": max(0.0, last["status"]["observer_start"] - first["status"]["observer_end"]),
                "time_upper_seconds": last["status"]["observer_end"] - first["status"]["observer_start"],
                "counter_delta": db_delta, "bulk_counter_delta": bulk_delta,
                "DBtransactions_per_observed_second": db_delta.get("db_transactions", 0) / elapsed if elapsed > 0 else None,
                "fixture_ms_per_observed_tick": bulk_delta["fixture_ms_total"] / bulk_delta["fixture_ticks"]
                    if bulk_delta.get("fixture_ticks", 0) > 0 else None,
                "coverage": "Sampled subwindow only; may exclude/contain some warmup. Not an exact 120-second benchmark phase."})
        self.report["observed_phases"] = summaries

    def flat(self, sample):
        result = {key: sample.get(key) for key in ("round", "utc", "offset_seconds", "observed_phase_id", "observed_mode",
            "window_reset_observed", "sample_interval_seconds", "sample_duration_seconds", "error")}
        for prefix in ("status", "bulk"):
            for key, value in sample.get(prefix, {}).get("metrics", {}).items():
                result[prefix + "_" + key] = value
            result[prefix + "_reply"] = sample.get(prefix, {}).get("reply")
            result[prefix + "_observer_start"] = sample.get(prefix, {}).get("observer_start")
            result[prefix + "_observer_end"] = sample.get(prefix, {}).get("observer_end")
        for key, value in sample.get("proc", {}).items():
            result["proc_" + key] = value
        for key, value in sample.get("heap", {}).items():
            result[key] = value
        return result

    def run(self):
        self.save()
        try:
            self.preflight()
            started = time.monotonic()
            for index in range(math.ceil(self.args.seconds / self.args.interval)):
                delay = started + index * self.args.interval - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                sample = self.sample(index)
                self.report["samples"].append(sample)
                if sample.get("error"):
                    self.report["failures"].append(sample["error"])
                if index % 5 == 0 or sample.get("error"):
                    self.save()
                    print(json.dumps({key: sample.get(key) for key in ("round", "utc", "observed_phase_id", "observed_mode", "window_reset_observed", "error")}), flush=True)
                if sample.get("error"):
                    break
        except KeyboardInterrupt:
            self.report["operator_stopped"] = True
        except Exception as error:
            self.report["failures"].append(type(error).__name__ + ": " + str(error))
        finally:
            self.summarize()
            rows = [self.flat(sample) for sample in self.report["samples"]]
            if rows:
                fields = list(dict.fromkeys(key for row in rows for key in row))
                with self.csv_path.open("w", newline="") as file:
                    writer = csv.DictWriter(file, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            self.report.update(utc_end=utc_now(), elapsed_seconds=time.monotonic() - self.start,
                passed=not self.report["failures"] and bool(self.report["samples"]), csv=str(self.csv_path))
            self.save()
        print("Saved " + str(self.path) + " and " + str(self.csv_path), flush=True)
        return 0 if self.report["passed"] else 1


def self_test():
    status = numbers("STATUS online {db_transactions=17, db_deadlock_retries=2, tick_ms_p95=0.4, active_endpoints=0}")
    bulk = numbers("BULK count=500 registered=500 bound=500 accepted=900 extracted=800 fixture_ms_total=2.5")
    assert status["db_transactions"] == 17 and bulk["fixture_ms_total"] == 2.5
    assert observed_mode(status, bulk) == "OFF_observed"
    status["active_endpoints"] = 500
    assert observed_mode(status, bulk) == "ACTIVE_observed"
    bulk["bound"] = 499
    assert observed_mode(status, bulk) == "setup_or_transition"
    print("Offline scale-monitor parser checks passed; no JVM/backend contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="baseline-scale-late")
    parser.add_argument("--seconds", type=float, default=1800)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--rcon-timeout", type=float, default=3)
    parser.add_argument("--jstat-every", type=float, default=10, help="0 disables; default every 10 seconds")
    parser.add_argument("--jstat-timeout", type=float, default=1)
    parser.add_argument("--coverage-note", default="Sampling starts now; earlier scale phases/portions UNMEASURED.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label):
        parser.error("invalid label")
    if not 1 <= args.seconds <= 86400 or not 1 <= args.interval <= 30 or not .2 <= args.rcon_timeout <= 10 or not (
            args.jstat_every == 0 or 2 <= args.jstat_every <= 300) or not .1 <= args.jstat_timeout <= 10:
        parser.error("scale monitor parameters outside bounded range")
    return ScaleMonitor(args).run()


if __name__ == "__main__":
    sys.exit(main())
