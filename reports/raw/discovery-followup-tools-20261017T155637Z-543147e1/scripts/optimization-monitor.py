#!/usr/bin/env python3
"""Read-only /proc + Java 21 jstat sidecar for isolated optimization runs.

Only RCON command: ct_test pid, once per server. Never starts JFR or changes
Minecraft, Docker, configuration, world, or backend state.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import uuid

from rcon import command

ROOT = Path(__file__).resolve().parents[1]
PORTS = {"A": 25575, "B": 25576, "C": 25577}
GC_KEYS = ("YGC", "YGCT", "FGC", "FGCT", "CGC", "CGCT", "GCT")
CSV_FIELDS = ("utc", "offset_seconds", "server", "pid", "cpu_total_seconds", "cpu_process_percent",
    "rss_bytes", "rss_high_water_bytes", "fd_count", "threads", "heap_committed_bytes", "heap_used_bytes",
    "YGC", "YGCT", "FGC", "FGCT", "CGC", "CGCT", "GCT", "sample_duration_seconds", "error")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def parse_stat(text):
    # comm may contain spaces/parentheses. Indexes are relative to field 3.
    fields = text[text.rfind(")") + 2:].split()
    ticks = os.sysconf("SC_CLK_TCK")
    return {"cpu_total_seconds": (int(fields[11]) + int(fields[12])) / ticks,
            "starttime_ticks": int(fields[19]), "threads": int(fields[17])}


def parse_status(text):
    result = {}
    for key, output in (("VmRSS", "rss_bytes"), ("VmHWM", "rss_high_water_bytes"),
                        ("VmSize", "virtual_bytes"), ("RssAnon", "rss_anonymous_bytes"), ("RssFile", "rss_file_bytes")):
        match = re.search(r"^" + key + r":\s+(\d+)\s+kB$", text, re.MULTILINE)
        result[output] = int(match[1]) * 1024 if match else None
    return result


def parse_jstat(text):
    lines = [line.split() for line in text.splitlines() if line.strip()]
    if len(lines) != 2 or len(lines[0]) != len(lines[1]):
        raise ValueError("Unrecognized single-sample jstat output")
    result = {}
    for name, value in zip(lines[0], lines[1]):
        if value == "-":
            result[name] = None
        else:
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError("Nonfinite jstat counter")
            result[name] = int(numeric) if name in ("YGC", "FGC", "CGC") else numeric
    return result


def heap_bytes(gc):
    committed = [gc.get(key) for key in ("S0C", "S1C", "EC", "OC")]
    used = [gc.get(key) for key in ("S0U", "S1U", "EU", "OU")]
    # jstat -gc capacities/usages are KiB. Exclude metaspace and CCS.
    return {"heap_committed_bytes": int(sum(committed) * 1024) if all(v is not None for v in committed) else None,
            "heap_used_bytes": int(sum(used) * 1024) if all(v is not None for v in used) else None}


class Monitor:
    def __init__(self, args):
        self.args = args
        self.start = time.monotonic()
        token = uuid.uuid4().hex[:6]
        stem = "optimization-monitor-" + args.label + "-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + token
        self.path = ROOT / "reports" / (stem + ".json")
        self.csv_path = self.path.with_suffix(".csv")
        self.identity = {}
        self.previous = {}
        self.report = {"schema_version": 1, "report_kind": "read_only_process_monitor", "label": args.label,
            "utc_start": utc_now(), "observer_monotonic_start": self.start,
            "conditions": {"seconds": args.seconds, "interval_seconds": args.interval,
                           "jstat_timeout_seconds": args.jstat_timeout, "ports": PORTS},
            "measurement": {
                "CPU": "/proc/PID/stat utime+stime; process percent has one CPU at 100%, may exceed 100%",
                "RSS": "Linux process resident memory; includes heap, native allocations, code and mappings",
                "heap": "jstat -gc observed region capacities/usages; excludes metaspace/CCS; samples, not allocation rate",
                "GC": "jstat cumulative GC count/time deltas; times are elapsed seconds, not tick time or pause distribution",
                "jstat_raw": "Both -gc and -gcutil raw stdout preserved with independent read intervals",
                "MSPT": "Not measured. No full-server JFR, tick instrumentation or stop-the-world pause claim.",
                "sidecar": "Read-only observer creates short jstat processes; match its sampling before/after."},
            "samples": [], "warnings": [], "failures": [], "passed": False}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(self.path)

    def preflight(self):
        for server, port in PORTS.items():
            config_path = ROOT / ("run-" + server) / "cross-tesseract.properties"
            selected = {}
            for line in config_path.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith(("#", "!")):
                    key, value = line.split("=", 1)
                    if key.strip() in ("cluster.id", "server.id", "backend.enabled"):
                        selected[key.strip()] = value.strip()
            sid = selected.get("server.id", "")
            if selected.get("cluster.id") != "dev_three_v1" or selected.get("backend.enabled") != "true" or not (
                    sid == "dev-" + server or re.fullmatch(r"opt-[A-Za-z0-9_-]{1,48}-" + server, sid)):
                raise ValueError("Refusing non-isolated config for " + server)
            reply = command(port, "ct_test pid")
            match = re.fullmatch(r"PID (\d+)\s*", reply)
            if not match:
                raise ValueError("Cannot identify real JVM from RCON: " + server)
            pid = int(match[1])
            proc = Path(f"/proc/{pid}")
            initial = parse_stat((proc / "stat").read_text())
            argv_raw = (proc / "cmdline").read_bytes()
            java = (proc / "exe").resolve()
            if java.name != "java":
                raise ValueError("RCON PID is not a Java process")
            jstat = java.parent / "jstat"
            if not jstat.is_file() or not os.access(jstat, os.X_OK):
                jstat = ROOT / "scratch/jdk/jdk-21.0.8+9/bin/jstat"
            self.identity[server] = {"pid": pid, "server_id": sid, "starttime_ticks": initial["starttime_ticks"],
                "java_executable": str(java), "argv_sha256": hashlib.sha256(argv_raw).hexdigest(),
                "jstat": str(jstat) if jstat.is_file() and os.access(jstat, os.X_OK) else None}
            if self.identity[server]["jstat"] is None:
                self.report["warnings"].append(server + ": jstat unavailable; heap/GC unmeasured, /proc sampling continues")
        self.report["identity"] = self.identity
        self.report["hardware"] = {"logical_cpus": os.cpu_count(), "clock_ticks_per_second": os.sysconf("SC_CLK_TCK")}

    def jstat(self, identity, option):
        started = time.monotonic()
        record = {"observer_start": started, "option": option, "command": [identity["jstat"], option, str(identity["pid"])]}
        try:
            result = subprocess.run(record["command"], capture_output=True, text=True,
                                    timeout=self.args.jstat_timeout, check=False,
                                    env=dict(os.environ, LC_ALL="C"))
            record.update(stdout=result.stdout, stderr=result.stderr, exit_code=result.returncode)
            if result.returncode:
                raise RuntimeError("jstat exit " + str(result.returncode))
            record["values"] = parse_jstat(result.stdout)
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as error:
            record["error"] = type(error).__name__ + ": " + str(error)
        record["observer_end"] = time.monotonic()
        return record

    def sample(self, server):
        identity = self.identity[server]
        started = time.monotonic()
        sample = {"server": server, "pid": identity["pid"], "utc": utc_now(),
                  "observer_monotonic": started, "offset_seconds": started - self.start}
        try:
            proc = Path(f"/proc/{identity['pid']}")
            stat = parse_stat((proc / "stat").read_text())
            if stat["starttime_ticks"] != identity["starttime_ticks"]:
                raise RuntimeError("PID reused; JVM identity changed")
            sample.update(stat, **parse_status((proc / "status").read_text()))
            sample["fd_count"] = len(list((proc / "fd").iterdir()))
            if identity["jstat"]:
                sample["jstat_gc"] = self.jstat(identity, "-gc")
                sample["jstat_gcutil"] = self.jstat(identity, "-gcutil")
                gc = sample["jstat_gc"].get("values", {})
                sample.update(heap_bytes(gc))
                sample.update({key: gc.get(key) for key in GC_KEYS})
            previous = self.previous.get(server)
            if previous:
                elapsed = started - previous["observer_monotonic"]
                delta = sample["cpu_total_seconds"] - previous["cpu_total_seconds"]
                if delta < 0:
                    raise RuntimeError("CPU counter decreased; process identity changed")
                sample["cpu_process_percent"] = delta / elapsed * 100
                sample["cpu_host_percent"] = sample["cpu_process_percent"] / max(1, os.cpu_count() or 1)
                sample["sample_interval_seconds"] = elapsed
            else:
                sample["cpu_process_percent"] = None
            self.previous[server] = sample
        except (OSError, RuntimeError, ValueError, IndexError) as error:
            sample["error"] = type(error).__name__ + ": " + str(error)
        sample["sample_duration_seconds"] = time.monotonic() - started
        return sample

    def summarize(self):
        summary = {}
        for server in PORTS:
            records = [s for s in self.report["samples"] if s["server"] == server and "error" not in s]
            values = lambda key: [s[key] for s in records if s.get(key) is not None]
            entry = {"samples": len(records), "CPU_process_percent_mean": statistics.mean(values("cpu_process_percent")) if values("cpu_process_percent") else None,
                     "CPU_process_percent_observed_max": max(values("cpu_process_percent"), default=None),
                     "RSS_bytes_observed_max": max(values("rss_bytes"), default=None),
                     "heap_used_bytes_observed_max": max(values("heap_used_bytes"), default=None),
                     "heap_committed_bytes_observed_max": max(values("heap_committed_bytes"), default=None),
                     "fd_count_observed_max": max(values("fd_count"), default=None)}
            if len(records) > 1:
                first, last = records[0], records[-1]
                elapsed = last["observer_monotonic"] - first["observer_monotonic"]
                cpu_delta = last["cpu_total_seconds"] - first["cpu_total_seconds"]
                entry.update(observed_seconds=elapsed, CPU_seconds_delta=cpu_delta,
                             CPU_process_percent_duration_weighted=cpu_delta / elapsed * 100)
            gc_records = [s for s in records if s.get("jstat_gc", {}).get("values")]
            entry["GC_cumulative_delta"] = None
            if len(gc_records) > 1:
                first, last = gc_records[0], gc_records[-1]
                delta = {key: last[key] - first[key] if first.get(key) is not None and last.get(key) is not None else None
                         for key in GC_KEYS}
                if any(value is not None and value < 0 for value in delta.values()):
                    self.report["warnings"].append(server + ": jstat cumulative counters decreased; GC delta invalid")
                else:
                    entry["GC_cumulative_delta"] = delta
                    entry["GC_observed_seconds"] = last["jstat_gc"]["observer_end"] - first["jstat_gc"]["observer_end"]
            summary[server] = entry
        self.report["summary"] = summary

    def run(self):
        self.save()
        try:
            self.preflight()
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            with self.csv_path.open("w", newline="") as csv_file, ThreadPoolExecutor(max_workers=3) as executor:
                writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
                writer.writeheader()
                rounds = math.ceil(self.args.seconds / self.args.interval)
                started = time.monotonic()
                for index in range(rounds):
                    delay = started + index * self.args.interval - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    records = list(executor.map(self.sample, PORTS))
                    self.report["samples"].extend(records)
                    for record in records:
                        writer.writerow(record)
                        if record.get("error"):
                            self.report["failures"].append(record["server"] + ": " + record["error"])
                    csv_file.flush()
                    if index % 6 == 0:
                        self.save()
                        print(json.dumps({"sample_round": index, "offset_seconds": time.monotonic() - self.start,
                            "servers": [{k: s.get(k) for k in ("server", "pid", "cpu_process_percent", "rss_bytes", "heap_used_bytes", "fd_count", "error")} for s in records]}), flush=True)
                    if self.report["failures"]:
                        break
        except KeyboardInterrupt:
            self.report["operator_stopped"] = True
        except Exception as error:
            self.report["failures"].append(type(error).__name__ + ": " + str(error))
        finally:
            self.summarize()
            self.report["elapsed_seconds"] = time.monotonic() - self.start
            self.report["utc_end"] = utc_now()
            self.report["passed"] = not self.report["failures"] and bool(self.report["samples"])
            self.report["csv"] = str(self.csv_path)
            self.save()
        print("Saved " + str(self.path) + " and " + str(self.csv_path), flush=True)
        return 0 if self.report["passed"] else 1


def self_test():
    fields = ["S0C", "S1C", "S0U", "S1U", "EC", "EU", "OC", "OU", "YGC", "YGCT", "FGC", "FGCT", "CGC", "CGCT", "GCT"]
    gc = parse_jstat(" ".join(fields) + "\n100 100 0 10 1000 200 2000 300 7 0.12 0 0.0 2 0.02 0.14\n")
    assert heap_bytes(gc) == {"heap_committed_bytes": 3200 * 1024, "heap_used_bytes": 510 * 1024}
    assert gc["YGC"] == 7 and isinstance(gc["YGC"], int)
    assert parse_jstat("CGC CGCT\n- -\n") == {"CGC": None, "CGCT": None}
    assert parse_status("VmRSS:\t2048 kB\nVmHWM:\t4096 kB\n")["rss_bytes"] == 2097152
    print("Offline monitor parser checks passed; no process/backend contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--seconds", type=float, default=6000)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--jstat-timeout", type=float, default=2)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label):
        parser.error("invalid label")
    if not 1 <= args.seconds <= 86400 or not 1 <= args.interval <= 60 or not .1 <= args.jstat_timeout <= 10:
        parser.error("monitor parameters outside bounded range")
    return Monitor(args).run()


if __name__ == "__main__":
    sys.exit(main())
