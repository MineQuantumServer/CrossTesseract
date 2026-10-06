#!/usr/bin/env python3
"""Read-only Minecraft 1.21.1 tick-query sampler for isolated A/B/C JVMs.

Records the Minecraft 100-tick work window, not full-loop wall MSPT or actual
TPS. Sampling begins now; earlier repeats are explicitly not covered.
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
import sys
import time
import uuid
import zipfile

from rcon import command

ROOT = Path(__file__).resolve().parents[1]
PORTS = {"A": 25575, "B": 25576, "C": 25577}
SOURCE = ROOT / "build/moddev/artifacts/neoforge-21.1.252-sources.jar"
CSV_FIELDS = ("round", "server", "pid", "utc_request_start", "utc_reply_end",
    "observer_start", "observer_end", "offset_seconds", "rcon_ms", "state",
    "target_tickrate", "target_tick_ms", "mc_recorded_tick_mean_ms", "tick_window_p50_ms",
    "tick_window_p95_ms", "tick_window_p99_ms", "tick_window_samples", "reply", "error")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def parse_query(reply):
    number = r"(\d+(?:[.,]\d+)?)"
    rate = re.search(r"Target tick rate:\s*" + number + r"\s+per second", reply, re.IGNORECASE)
    average = re.search(r"Average time per tick:\s*" + number + r"\s*ms", reply, re.IGNORECASE)
    target = re.search(r"\(Target:\s*" + number + r"\s*ms\)", reply, re.IGNORECASE)
    percentiles = re.search(r"P50:\s*" + number + r"ms\s+P95:\s*" + number +
        r"ms\s+P99:\s*" + number + r"ms,\s*sample:\s*(\d+)", reply, re.IGNORECASE)
    if not rate or not average or not percentiles:
        raise ValueError("Unrecognized tick query response; raw reply retained")
    numeric = lambda value: float(value.replace(",", "."))
    lower = reply.lower()
    if "game is sprinting" in lower:
        state = "sprinting"
    elif "game is frozen" in lower:
        state = "frozen"
    elif "can't keep up" in lower:
        state = "lagging"
    elif "game is running normally" in lower:
        state = "running"
    else:
        state = "unknown"
    return {"state": state, "target_tickrate": numeric(rate[1]),
        "target_tick_ms": numeric(target[1]) if target else None,
        "mc_recorded_tick_mean_ms": numeric(average[1]),
        "tick_window_p50_ms": numeric(percentiles[1]),
        "tick_window_p95_ms": numeric(percentiles[2]),
        "tick_window_p99_ms": numeric(percentiles[3]), "tick_window_samples": int(percentiles[4])}


def process_starttime(pid):
    text = Path(f"/proc/{pid}/stat").read_text()
    return int(text[text.rfind(")") + 2:].split()[19])


class TickMonitor:
    def __init__(self, args):
        self.args = args
        self.start = time.monotonic()
        stem = "optimization-tick-" + args.label + "-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
        self.path = ROOT / "reports" / (stem + ".json")
        self.csv_path = self.path.with_suffix(".csv")
        self.identity = {}
        self.report = {"schema_version": 1, "report_kind": "read_only_minecraft_tick_monitor",
            "label": args.label, "utc_start": utc_now(), "observer_monotonic_start": self.start,
            "conditions": {"seconds": args.seconds, "interval_seconds": args.interval,
                "rcon_timeout_seconds": args.rcon_timeout, "ports": PORTS},
            "coverage": {"note": args.coverage_note, "earlier_repeats": "UNMEASURED",
                "policy": "Only actual query intervals recorded here are covered. No backfill from later samples."},
            "measurement": {
                "version": "Minecraft 1.21.1 / NeoForge 21.1.252 / Java 21",
                "average_api": "MinecraftServer.getAverageTickTimeNanos(): long nanoseconds; divide by 1e6",
                "window": "Arithmetic mean of latest min(100,max(tickCount,1)) recorded ticks, normally latest 100",
                "scope": "tickServer elapsed work through tally; includes ServerTickEvent.Pre, worlds and autosave; excludes NeoForge ServerTickEvent.Post and idle/other outer-loop work",
                "percentiles": "Vanilla tick query sorted 100-slot tickTimesNanos window; not phase-wide percentiles",
                "console_rounding": "TickCommand.nanosToMilisString formats one decimal ms; approximately +/-0.05ms rounding",
                "target_tickrate": "Configured TickRateManager.tickrate(); not measured actual or instantaneous TPS",
                "whole_loop_MSPT": "UNMEASURED: full-loop/full-extension tick wall time not instrumented",
                "observer": "Concurrent read-only tick query per JVM; request/reply intervals preserved. No JVM nanoTime subtraction."},
            "samples": [], "failures": [], "warnings": [], "passed": False}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(self.path)

    def preflight(self):
        for server, port in PORTS.items():
            config = {}
            for line in (ROOT / ("run-" + server) / "cross-tesseract.properties").read_text().splitlines():
                if "=" in line and not line.lstrip().startswith(("#", "!")):
                    key, value = line.split("=", 1)
                    if key.strip() in ("cluster.id", "server.id", "backend.enabled"):
                        config[key.strip()] = value.strip()
            sid = config.get("server.id", "")
            if config.get("cluster.id") != "dev_three_v1" or config.get("backend.enabled") != "true" or not (
                    sid == "dev-" + server or re.fullmatch(r"opt-[A-Za-z0-9_-]{1,48}-" + server, sid)):
                raise ValueError("Refusing non-isolated configuration for " + server)
            reply = command(port, "ct_test pid", timeout=self.args.rcon_timeout)
            match = re.fullmatch(r"PID (\d+)\s*", reply)
            if not match:
                raise ValueError("Cannot identify real development JVM: " + server)
            pid = int(match[1])
            java = Path(f"/proc/{pid}/exe").resolve()
            if java.name != "java":
                raise ValueError("RCON PID is not Java")
            self.identity[server] = {"pid": pid, "server_id": sid,
                "starttime_ticks": process_starttime(pid), "java_executable": str(java),
                "argv_sha256": hashlib.sha256(Path(f"/proc/{pid}/cmdline").read_bytes()).hexdigest()}
        if len({value["pid"] for value in self.identity.values()}) != 3:
            raise ValueError("Three independent Minecraft JVMs required")
        self.report["identity"] = self.identity
        if SOURCE.is_file():
            source = {"path": str(SOURCE), "jar_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "entries": {}}
            with zipfile.ZipFile(SOURCE) as archive:
                for name in ("net/minecraft/server/MinecraftServer.java",
                             "net/minecraft/server/commands/TickCommand.java",
                             "net/minecraft/world/TickRateManager.java"):
                    source["entries"][name] = hashlib.sha256(archive.read(name)).hexdigest()
            self.report["source_provenance"] = source
        else:
            self.report["warnings"].append("Local source artifact unavailable; API verification was against NeoForge 21.1.252 sources during tool development.")

    def sample(self, server):
        identity = self.identity[server]
        started = time.monotonic()
        result = {"server": server, "pid": identity["pid"], "utc_request_start": utc_now(),
            "observer_start": started, "offset_seconds": started - self.start}
        try:
            if process_starttime(identity["pid"]) != identity["starttime_ticks"]:
                raise RuntimeError("JVM PID reused")
            result["reply"] = command(PORTS[server], "tick query", timeout=self.args.rcon_timeout)
            result["observer_end"] = time.monotonic()
            result["utc_reply_end"] = utc_now()
            result.update(parse_query(result["reply"]))
            if process_starttime(identity["pid"]) != identity["starttime_ticks"]:
                raise RuntimeError("JVM PID changed during query")
        except (OSError, RuntimeError, ValueError, IndexError) as error:
            result["error"] = type(error).__name__ + ": " + str(error)
        result.setdefault("observer_end", time.monotonic())
        result.setdefault("utc_reply_end", utc_now())
        result["rcon_ms"] = (result["observer_end"] - started) * 1000
        return result

    def summarize(self):
        result = {}
        for server in PORTS:
            records = [s for s in self.report["samples"] if s["server"] == server and "error" not in s]
            means = [s["mc_recorded_tick_mean_ms"] for s in records]
            result[server] = {"queries": len(records),
                "first_query_utc": records[0]["utc_request_start"] if records else None,
                "last_query_utc": records[-1]["utc_reply_end"] if records else None,
                "observed_mean_of_tick_window_means_ms": statistics.mean(means) if means else None,
                "observed_min_of_tick_window_means_ms": min(means, default=None),
                "observed_max_of_tick_window_means_ms": max(means, default=None),
                "target_tickrates": sorted({s["target_tickrate"] for s in records}),
                "states": {state: sum(s["state"] == state for s in records) for state in sorted({s["state"] for s in records})},
                "scope_note": "Statistics across query-window means only, not complete phase tick population."}
        self.report["summary"] = result

    def run(self):
        self.save()
        try:
            self.preflight()
            with self.csv_path.open("w", newline="") as file, ThreadPoolExecutor(max_workers=3) as executor:
                writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, extrasaction="ignore")
                writer.writeheader()
                started = time.monotonic()
                for index in range(math.ceil(self.args.seconds / self.args.interval)):
                    delay = started + index * self.args.interval - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    records = list(executor.map(self.sample, PORTS))
                    for record in records:
                        record["round"] = index
                        writer.writerow(record)
                        if record.get("error"):
                            self.report["failures"].append(record["server"] + ": " + record["error"])
                    file.flush()
                    self.report["samples"].extend(records)
                    self.save()
                    print(json.dumps({"round": index, "queries": [{key: s.get(key) for key in
                        ("server", "state", "mc_recorded_tick_mean_ms", "target_tickrate", "rcon_ms", "error")} for s in records]}), flush=True)
                    if self.report["failures"]:
                        break
        except KeyboardInterrupt:
            self.report["operator_stopped"] = True
        except Exception as error:
            self.report["failures"].append(type(error).__name__ + ": " + str(error))
        finally:
            self.summarize()
            self.report["utc_end"] = utc_now()
            self.report["elapsed_seconds"] = time.monotonic() - self.start
            self.report["csv"] = str(self.csv_path)
            self.report["passed"] = not self.report["failures"] and bool(self.report["samples"])
            self.save()
        print("Saved " + str(self.path) + " and " + str(self.csv_path), flush=True)
        return 0 if self.report["passed"] else 1


def self_test():
    reply = "The game is running normally\nTarget tick rate: 20.0 per second.\nAverage time per tick: 0.3ms (Target: 50.0ms)\nPercentiles: P50: 0.3ms P95: 0.4ms P99: 1.1ms, sample: 100\n"
    result = parse_query(reply)
    assert result["state"] == "running" and result["mc_recorded_tick_mean_ms"] == .3
    assert result["target_tickrate"] == 20 and result["target_tick_ms"] == 50
    assert result["tick_window_p99_ms"] == 1.1 and result["tick_window_samples"] == 100
    sprint = reply.replace("running normally", "sprinting").replace(" (Target: 50.0ms)", "")
    assert parse_query(sprint)["state"] == "sprinting" and parse_query(sprint)["target_tick_ms"] is None
    assert parse_query(reply.replace("0.3ms", "0,3ms"))["mc_recorded_tick_mean_ms"] == .3
    try:
        parse_query("Unknown command")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid query response accepted")
    print("Offline tick-query parser checks passed; no JVM/backend contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="baseline-late")
    parser.add_argument("--seconds", type=float, default=6000)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--rcon-timeout", type=float, default=3)
    parser.add_argument("--coverage-note", default="Sampling starts now; earlier baseline repeats are UNMEASURED.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label):
        parser.error("invalid label")
    if not 1 <= args.seconds <= 86400 or not 5 <= args.interval <= 120 or not .2 <= args.rcon_timeout <= 10:
        parser.error("tick monitor parameters outside bounded range")
    return TickMonitor(args).run()


if __name__ == "__main__":
    sys.exit(main())
