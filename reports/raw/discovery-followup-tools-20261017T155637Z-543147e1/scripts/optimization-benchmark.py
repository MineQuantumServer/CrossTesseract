#!/usr/bin/env python3
"""Matched, real-capability optimization benchmarks on the isolated A/B/C JVMs.

No process or container lifecycle operations. Mutates only newly created console
fixtures in dev_three_v1; run --help or --self-test for an offline check.
"""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import sys
import time
import uuid

from rcon import command

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = "dev_three_v1"
PORTS = {"A": 25575, "B": 25576, "C": 25577}
FE = "cross_tesseract:fe"
SCENARIOS = ("same", "cross", "mixed", "backpressure", "hotspot")
MYSQL_IMAGE = "mysql@sha256:0426ec38c7a10aa45ba383887df7878f74ee70e2fd589c7b69207f3577901903"
COUNTERS = ("db_transactions", "db_deadlock_retries", "transactions", "errors", "queue_rejected", "quarantined")


def quantiles(values):
    ordered = sorted(values)
    return {"samples": len(ordered), **{
        "p" + str(p): ordered[min(len(ordered) - 1, math.ceil(len(ordered) * p / 100) - 1)] if ordered else None
        for p in (50, 95, 99)}}


def numeric_fields(text):
    # Java Double.toString emits exponent notation for small timing values.
    # Keep plain integer counters exact, including values above 2**53, and
    # reject partial numeric tokens rather than taking their mantissa.
    values = {k: float(v) if "." in v or "e" in v.lower() else int(v)
            for k, v in re.findall(r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)=(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?=[, }]|$)", text)}
    if any(isinstance(value, float) and not math.isfinite(value) for value in values.values()):
        raise ValueError("Non-finite numeric status field")
    return values


def device_fields(text):
    match = re.search(r"DEVICE ([\w-]+) registered=(true|false) pause=(.*?) channel=(\S+) (.*)", text)
    if not match:
        raise AssertionError("Unrecognized inspect response: " + text)
    return dict(numeric_fields(match[5]), id=str(uuid.UUID(match[1])),
                registered=match[2] == "true", pause=match[3], channel=match[4])


def e2e_interval(source, target):
    # Both intervals come from THIS Python process's monotonic clock.
    return {"lower_ms": max(0.0, (target["start"] - source["end"]) * 1000),
            "upper_ms": (target["end"] - source["start"]) * 1000,
            "source_rcon_ms": (source["end"] - source["start"]) * 1000,
            "target_rcon_ms": (target["end"] - target["start"]) * 1000}


def properties(path):
    # Only select non-secret keys; never return or log the rest of the file.
    allowed = {"backend.enabled", "cluster.id", "server.id", "mysql.url", "mysql.user",
               "redis.uri", "buffers.fe", "limits.maxEndpointsPerChannel", "enable-rcon", "rcon.port", "level-name"}
    result = {}
    for line in path.read_text().splitlines():
        if not line.lstrip().startswith(("#", "!")) and "=" in line:
            key, value = line.split("=", 1)
            if key.strip() in allowed:
                result[key.strip()] = value.strip()
    return result


def expanded_vm_args(argv, server, process_cwd):
    """Read only this server's bounded, repository-owned Java VM argument file."""
    expanded = []
    evidence = []
    roots = ((ROOT / "build/moddev").resolve(), (ROOT / "scratch/dev-launch").resolve())
    for arg in argv:
        if not arg.startswith("@"):
            expanded.append(arg)
            continue
        candidate = Path(arg[1:])
        if not candidate.is_absolute():
            candidate = process_cwd / candidate
        candidate = candidate.resolve()
        # Program/classpath argfiles are not needed for identity verification.
        if candidate.name != "server" + server + "RunVmArgs.txt":
            expanded.append(arg)
            continue
        if not any(candidate.is_relative_to(root) for root in roots) or candidate.stat().st_size > 1048576:
            raise ValueError("Refusing untrusted or oversized JVM VM argument file")
        raw = candidate.read_bytes()
        values = shlex.split(raw.decode("utf-8"), comments=True, posix=True)
        if any(value.startswith("@") for value in values):
            raise ValueError("Nested JVM VM argument files are not accepted")
        expanded.extend(values)
        evidence.append({"path": str(candidate), "sha256": hashlib.sha256(raw).hexdigest(),
                         "size_bytes": len(raw)})
    return expanded, evidence


def docker(args, input_text=None):
    env = {k: v for k, v in os.environ.items() if k not in
           ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")}
    result = subprocess.run(["docker", "--host=unix:///var/run/docker.sock", *args],
                            input=input_text, text=True, capture_output=True, env=env, timeout=20)
    if result.returncode:
        raise RuntimeError("Isolated Docker read failed: " + result.stderr.strip()[:700])
    return result.stdout.strip()


def sql(statement):
    # The ct_dev account is reserved for the mod's statement counter. Our SELECTs
    # use the already-established LOCAL DEV root account, so they do not enter it.
    if not statement.lstrip().upper().startswith("SELECT ") or ";" in statement.rstrip("; \n"):
        raise ValueError("Benchmark SQL observer accepts one SELECT only")
    output = docker(["exec", "-i", "-e", "MYSQL_PWD=ct_dev_root_only", "ct-dev-mysql",
                     "mysql", "-u", "root", "--batch", "--skip-column-names", "cross_tesseract"], statement)
    return [line.split("\t") for line in output.splitlines() if line]


@dataclass
class Endpoint:
    name: str
    server: str
    x: int
    z: int
    id: str = ""


@dataclass
class Lane:
    name: str
    channel: str
    sources: list
    sinks: list
    accepted: int = 0
    extracted: int = 0
    source_totals: dict = field(default_factory=dict)
    sink_totals: dict = field(default_factory=dict)


class Benchmark:
    def __init__(self, args):
        self.args = args
        self.started = time.monotonic()
        self.owner = str(uuid.uuid4())
        self.token = uuid.uuid4().hex[:10]
        self.base_x = 1000000 + int(self.token[:5], 16) * 16
        self.target = ROOT / "reports" / ("optimization-" + args.label + "-" +
                      time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + self.token[:6] + ".json")
        self.cases = {}
        self.devices = []
        self.loaded_chunks = []
        self.pids = {}
        self.statements_available = False
        self.report = {
            "schema_version": 1, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "label": args.label, "cluster": CLUSTER, "owner": self.owner, "passed": False,
            "conditions": {"warmup_seconds": args.warmup, "steady_seconds": args.seconds,
                "repeats": args.repeats, "low_flow_probes_per_path_per_repeat": args.probes,
                "probe_idle_seconds": args.probe_idle, "probe_amount_FE": 1024,
                "poll_seconds": args.poll, "feed_period_seconds": args.feed_period,
                "input_attempt_FE": 32000, "sink_pull_request_FE": 2147483647,
                "workload": "Fixed ceil(seconds/feed_period) rounds; delayed rounds are retained and actual duration reported",
                "backpressure_hold_seconds": min(120.0, max(90.0, args.seconds)),
                "scenarios": args.scenarios, "hotspot_sources": 4, "hotspot_sinks": 4,
                "hotspot_channels": 4, "resource": FE},
            "measurement": {
                "clock": "One Python observer time.monotonic(); all event times are seconds since run start",
                "e2e": "Actual source capability acceptance -> actual target capability extraction; each event lies within its RCON request/reply interval. Bounds are not world-save times.",
                "polling": "Low-flow completion includes target polling cadence; output is not observed until an actual pull succeeds.",
                "db_transactions": "Sum of cumulative ct_test status db_transactions differences on A/B/C; includes controls, heartbeat/permission refresh and ambient loaded devices, excludes observer root SQL.",
                "sql_statement_events": "performance_schema account summary WHERE USER='ct_dev', statement/sql/* events only; counts attempts including retries, not JDBC round trips. Account-wide, including any running perf JVM.",
                "wal": "Not measured on unmodified baseline: no WAL timing/count instrumentation exists.",
                "conservation": "Accepted FE = actual extracted FE after drain; local buffers and SQL residue checked empty independently. SQL transfer remaining and local/WAL copies are never added together.",
                "steady_e2e": "Aggregate throughput/fairness only: overlapped FE inputs have no packet identity; no invented per-input steady latency.",
                "fixture": "Fresh console-owned blocks, vanilla chunk load tickets; no online-player, GUI, machine-container or injected network-latency claim."},
            "samples": [], "failures": [], "regressions": [], "warnings": [], "cleanup": []}

    def save(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(self.target)

    def issue(self, server, value, harness=True):
        start = time.monotonic() - self.started
        text = command(PORTS[server], ("ct_test " if harness else "") + value)
        end = time.monotonic() - self.started
        if "ERROR " in text:
            raise AssertionError(server + ": " + text)
        return {"start": start, "end": end, "reply": text}

    def inspect(self, endpoint):
        return device_fields(self.issue(endpoint.server, f"inspect {endpoint.x} {endpoint.z}")["reply"])

    def wait(self, read, predicate, seconds=60):
        until = time.monotonic() + seconds
        last = None
        while time.monotonic() < until:
            last = read()
            if predicate(last):
                return last
            time.sleep(self.args.poll)
        raise AssertionError("Timed out: " + repr(last)[:1000])

    def verify_isolation(self):
        if os.environ.get("CT_TEST_CLUSTER", CLUSTER) != CLUSTER:
            raise ValueError("Only the existing dev_three_v1 cluster is accepted")
        if any(key in os.environ for key in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI")):
            raise ValueError("Refusing backend override environment variables")
        identity = {}
        for server, port in PORTS.items():
            directory = ROOT / ("run-" + server)
            path = directory / "cross-tesseract.properties"
            config = properties(path)
            vanilla = properties(directory / "server.properties")
            if not (config.get("backend.enabled") == "true" and config.get("cluster.id") == CLUSTER
                    and (config.get("server.id") == "dev-" + server or re.fullmatch(r"opt-[A-Za-z0-9_-]{1,48}-" + server, config.get("server.id", "")))
                    and config.get("mysql.url", "").startswith("jdbc:mysql://127.0.0.1:13306/cross_tesseract?")
                    and config.get("mysql.user") == "ct_dev"
                    and config.get("redis.uri") == "redis://127.0.0.1:16379"
                    and vanilla.get("enable-rcon") == "true" and vanilla.get("rcon.port") == str(port)):
                raise ValueError("Refusing non-isolated configuration for " + server)
            self.wait(lambda: self.issue(server, "status")["reply"], lambda reply: "STATUS online" in reply)
            pid_reply = self.issue(server, "pid")["reply"]
            pid = int(re.search(r"PID (\d+)", pid_reply)[1])
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            decoded = [arg.decode(errors="replace") for arg in argv if arg]
            selected, argfiles = expanded_vm_args(decoded, server, Path(f"/proc/{pid}/cwd").resolve())
            system_properties = {arg[2:].split("=", 1)[0]: arg.split("=", 1)[1]
                                 for arg in selected if arg.startswith("-D") and "=" in arg}
            if system_properties.get("cross_tesseract.testHarness") != "true" or (
                    system_properties.get("cross_tesseract.config") != str(path.resolve())):
                raise ValueError("RCON process does not use the isolated dev fixture config for " + server)
            self.pids[server] = pid
            level_name = vanilla.get("level-name", "world")
            if level_name != "world" and not re.fullmatch(r"world-opt-[A-Za-z0-9_-]{1,64}", level_name):
                raise ValueError("Refusing unexpected fixture world path for " + server)
            world = str(uuid.UUID((directory / level_name / "cross_tesseract/world-id").read_text().strip()))
            identity[server] = {"port": port, "pid": pid, "server_id": config["server.id"],
                "world_id": world, "level_name": level_name, "java_executable": str(Path(f"/proc/{pid}/exe").resolve()),
                "jvm_heap": [arg for arg in selected if arg.startswith(("-Xmx", "-Xms"))],
                "argv_sha256": hashlib.sha256(b"\0".join(argv)).hexdigest(),
                "argv_launch": [arg if arg.startswith("@") or index == 0 else "<argument omitted>"
                                for index, arg in enumerate(decoded)],
                "vm_argfiles": argfiles,
                "verified_system_properties": [arg for arg in selected if arg.startswith(
                    ("-Dcross_tesseract.testHarness=", "-Dcross_tesseract.config="))],
                "buffer_capacity_FE": int(config.get("buffers.fe", "2000000"))}
        inspect = docker(["inspect", "--format", "{{json .NetworkSettings.Ports}}|{{.Config.Image}}|{{.State.Running}}", "ct-dev-mysql"])
        ports, image, running = inspect.rsplit("|", 2)
        binding = json.loads(ports).get("3306/tcp", [])
        if image not in (MYSQL_IMAGE, "mysql:8.4.7") or running != "true" or not any(
                b.get("HostIp") == "127.0.0.1" and b.get("HostPort") == "13306" for b in binding or []):
            raise ValueError("Refusing unrelated MySQL container or non-loopback binding")
        for server, info in identity.items():
            rows = sql("SELECT world_id,session_id,fencing_epoch FROM ct_servers WHERE cluster_id='" + CLUSTER +
                       "' AND server_id='" + info["server_id"] + "' AND lease_until>CURRENT_TIMESTAMP(6)")
            if len(rows) != 1 or rows[0][0] != info["world_id"]:
                raise ValueError("No matching live isolated backend session for " + server)
            info.update(session_id=rows[0][1], fencing_epoch=int(rows[0][2]))
        own_server_ids = ",".join("'" + info["server_id"] + "'" for info in identity.values())
        other = sql("SELECT cluster_id,server_id FROM ct_servers WHERE lease_until>CURRENT_TIMESTAMP(6) "
                    "AND NOT (cluster_id='dev_three_v1' AND server_id IN (" + own_server_ids + "))")
        self.report["other_live_backend_sessions"] = other
        if other:
            self.report["warnings"].append("ct_dev statement events are account-wide: other live sessions exist; they cannot be attributed to this workload.")
        self.report["identity"] = identity
        self.report["ambient_status"] = self.snapshot()["servers"]
        if any(s["metrics"]["active_endpoints"] for s in self.report["ambient_status"].values()):
            raise ValueError("Ambient active endpoints found; use the clean isolated development worlds")
        self.report["hardware"] = {"logical_cpus": os.cpu_count(),
            "cpu": next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                         if line.startswith("model name")), "unknown"),
            "memory": Path("/proc/meminfo").read_text().splitlines()[0]}
        self.report["git_head"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout.strip()
        self.report["git_worktree_status"] = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout.splitlines()
        self.report["runtime_revision_note"] = "git_head describes this checkout; loaded JVM revision is supplied by the operator and not proven by the old harness. PIDs/SQL sessions are checked unchanged."
        try:
            enabled = sql("SELECT @@performance_schema")
            consumers = sql("SELECT NAME,ENABLED FROM performance_schema.setup_consumers WHERE NAME IN "
                            "('global_instrumentation','thread_instrumentation','events_statements_current')")
            instruments = sql("SELECT COUNT(*),SUM(ENABLED='YES') FROM performance_schema.setup_instruments WHERE NAME LIKE 'statement/sql/%'")
            self.report["statement_instrumentation"] = {"performance_schema": enabled,
                "consumers": consumers, "instruments": instruments, "observer_account": "root (isolated development)"}
            self.statements_available = (enabled == [["1"]] and len(consumers) == 3
                and all(row[1] == "YES" for row in consumers) and instruments
                and int(instruments[0][0]) > 0 and instruments[0][0] == instruments[0][1])
            self.statements_available = bool(self.statements_available and self.statement_snapshot()["events"] > 0)
            if not self.statements_available:
                self.report["warnings"].append("SQL statement events not measured: existing performance_schema instrumentation/account counters unavailable; configuration left untouched.")
        except (RuntimeError, ValueError, IndexError) as error:
            self.report["warnings"].append("SQL statement events not measured: " + str(error)[:600])
            self.statements_available = False

    def statement_snapshot(self):
        rows = sql("SELECT EVENT_NAME,SUM(COUNT_STAR),SUM(SUM_TIMER_WAIT),SUM(SUM_ERRORS) FROM "
                   "performance_schema.events_statements_summary_by_account_by_event_name WHERE USER='ct_dev' "
                   "AND EVENT_NAME LIKE 'statement/sql/%' GROUP BY EVENT_NAME HAVING SUM(COUNT_STAR)>0 ORDER BY EVENT_NAME")
        return {"events": sum(int(row[1]) for row in rows),
                "timer_picoseconds": sum(int(row[2]) for row in rows),
                "errors": sum(int(row[3]) for row in rows),
                "by_event": {row[0]: int(row[1]) for row in rows},
                "observer_end": time.monotonic() - self.started}

    def snapshot(self):
        start = time.monotonic() - self.started
        servers = {}
        for server in PORTS:
            result = self.issue(server, "status")
            if "STATUS online" not in result["reply"]:
                raise AssertionError(server + " is not online: " + result["reply"])
            values = numeric_fields(result.pop("reply"))
            if not all(key in values for key in COUNTERS):
                raise AssertionError("Missing cumulative counters on " + server)
            servers[server] = dict(result, metrics=values)
        return {"start": start, "end": time.monotonic() - self.started, "servers": servers,
                "statements": self.statement_snapshot() if self.statements_available else None}

    def deltas(self, first, last):
        result = {key: sum(last["servers"][s]["metrics"][key] - first["servers"][s]["metrics"][key]
                           for s in PORTS) for key in COUNTERS}
        if any(v < 0 for v in result.values()):
            raise AssertionError("Cumulative counters reset or JVM restarted during measurement")
        result["per_server"] = {s: {key: last["servers"][s]["metrics"][key] - first["servers"][s]["metrics"][key]
                                   for key in COUNTERS} for s in PORTS}
        result["statements"] = None
        if first["statements"] and last["statements"]:
            result["statements"] = {key: last["statements"][key] - first["statements"][key]
                                    for key in ("events", "timer_picoseconds", "errors")}
            if result["statements"]["events"] < 0:
                raise AssertionError("MySQL performance_schema counters reset during measurement")
        return result

    def endpoint(self, server, name, channel):
        index = len(self.devices)
        endpoint = Endpoint(name, server, self.base_x + index % 16, 160 + index // 16)
        chunk = (server, endpoint.x // 16, endpoint.z // 16)
        if chunk not in self.loaded_chunks:
            # All coordinates are fresh; reject an existing vanilla load ticket.
            query = self.issue(server, f"forceload query {endpoint.x} {endpoint.z}", False)["reply"]
            if "marked for force loading" in query and "not" not in query.lower():
                raise AssertionError("Fresh benchmark chunk already force loaded; choose another run")
            response = self.issue(server, f"forceload add {endpoint.x} {endpoint.z}", False)["reply"]
            if "No chunks" in response or "already" in response.lower():
                raise AssertionError("Could not acquire a fresh vanilla load ticket: " + response)
            self.loaded_chunks.append(chunk)
        self.issue(server, f"spawn {endpoint.x} {endpoint.z} {self.owner}")
        self.devices.append(endpoint)  # Track immediately, including failed bind/setup.
        endpoint.id = self.wait(lambda: self.inspect(endpoint), lambda d: d["registered"])["id"]
        self.issue(server, f"bind {endpoint.x} {endpoint.z} {channel}")
        self.wait(lambda: self.inspect(endpoint), lambda d: d["channel"] == channel and not d["pause"])
        self.issue(server, f"mode {endpoint.x} {endpoint.z} {FE} OFF")
        return endpoint

    def lane(self, case, name, source_servers, sink_servers):
        channel_name = "opt_" + self.token + "_" + name
        self.issue("A", f"create {self.owner} {channel_name}")
        rows = self.wait(lambda: sql("SELECT channel_id FROM ct_channels WHERE cluster_id='" + CLUSTER +
                    "' AND owner_uuid='" + self.owner + "' AND name='" + channel_name + "'"), bool)
        channel = str(uuid.UUID(rows[0][0]))
        if len(source_servers) + len(sink_servers) > 256:
            raise ValueError("Baseline per-channel endpoint limit exceeded")
        lane = Lane(name, channel, [self.endpoint(s, name + "_source_" + str(i), channel) for i, s in enumerate(source_servers)],
                    [self.endpoint(s, name + "_sink_" + str(i), channel) for i, s in enumerate(sink_servers)])
        case.append(lane)

    def setup(self):
        for name in self.args.scenarios:
            lanes = self.cases.setdefault(name, [])
            if name == "same":
                self.lane(lanes, name, ["A"], ["A"])
            elif name == "cross":
                self.lane(lanes, name, ["A"], ["B"])
            elif name in ("mixed", "backpressure"):
                self.lane(lanes, name, ["A"], ["A", "B"])
            elif name == "hotspot":
                self.lane(lanes, "hot", ["A"] * 4, ["A", "B", "B", "C"])
                for index, server in enumerate(("A", "B", "C")):
                    self.lane(lanes, "cold" + str(index), ["A"], [server])
        self.report["fixtures"] = {name: [{"name": lane.name, "channel": lane.channel,
            "sources": [vars(e) for e in lane.sources], "sinks": [vars(e) for e in lane.sinks]} for lane in lanes]
            for name, lanes in self.cases.items()}
        self.save()

    def activate(self, lanes, active):
        for lane in lanes:
            for endpoint in lane.sources + lane.sinks:
                mode = ("SEND" if endpoint in lane.sources else "RECEIVE") if active else "OFF"
                self.issue(endpoint.server, f"mode {endpoint.x} {endpoint.z} {FE} {mode}")

    def push(self, lane, endpoint, amount, events):
        result = self.issue(endpoint.server, f"push-fe {endpoint.x} {endpoint.z} {amount}")
        match = re.search(r"ACCEPTED (\d+)", result.pop("reply"))
        if not match:
            raise AssertionError("Missing source acceptance")
        accepted = int(match[1])
        if not 0 <= accepted <= amount:
            raise AssertionError("Invalid accepted amount")
        lane.accepted += accepted
        lane.source_totals[endpoint.name] = lane.source_totals.get(endpoint.name, 0) + accepted
        event = dict(result, kind="input", lane=lane.name, endpoint=endpoint.name, requested=amount, amount=accepted)
        events.append(event)
        return event

    def pull(self, lane, endpoint, events):
        result = self.issue(endpoint.server, f"pull-fe {endpoint.x} {endpoint.z} 2147483647")
        match = re.search(r"EXTRACTED (\d+)", result.pop("reply"))
        if not match:
            raise AssertionError("Missing target extraction")
        amount = int(match[1])
        lane.extracted += amount
        lane.sink_totals[endpoint.name] = lane.sink_totals.get(endpoint.name, 0) + amount
        if lane.extracted > lane.accepted:
            raise AssertionError("Duplicate output/conservation failure in " + lane.name)
        event = dict(result, kind="output", lane=lane.name, endpoint=endpoint.name, amount=amount)
        events.append(event)
        return event

    def drive(self, lanes, seconds, events, feed=True, extract=True):
        started = time.monotonic()
        tick = 0
        late = 0
        max_lateness = 0.0
        rounds = math.ceil(seconds / self.args.feed_period)
        while tick < rounds:
            due = started + tick * self.args.feed_period
            delay = time.monotonic() - due
            if delay < 0:
                time.sleep(-delay)
            lateness = max(0.0, time.monotonic() - due)
            max_lateness = max(max_lateness, lateness)
            late += lateness >= self.args.feed_period
            # Rotate deterministic service order so a fixed first RCON sink has no privilege.
            ordered = lanes[tick % len(lanes):] + lanes[:tick % len(lanes)]
            for lane in ordered:
                if feed:
                    for endpoint in lane.sources:
                        self.push(lane, endpoint, 32000, events)
                if extract:
                    sinks = lane.sinks[tick % len(lane.sinks):] + lane.sinks[:tick % len(lane.sinks)]
                    for endpoint in sinks:
                        self.pull(lane, endpoint, events)
            tick += 1
        remaining = started + seconds - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        return {"seconds": time.monotonic() - started, "scheduled_rounds": tick,
                "planned_rounds": rounds,
                "late_rounds": late, "max_lateness_ms": max_lateness * 1000,
                "observer_saturated": max_lateness >= self.args.feed_period}

    def residue(self, lanes):
        # Diagnostic scopes deliberately kept separate; SQL allocations may mirror local credits.
        channels = ",".join("'" + lane.channel + "'" for lane in lanes)
        rows = sql("SELECT (SELECT COALESCE(SUM(amount),0) FROM ct_balances WHERE cluster_id='" + CLUSTER +
            "' AND channel_id IN (" + channels + ")), (SELECT COALESCE(SUM(remaining),0) FROM ct_transfers "
            "WHERE cluster_id='" + CLUSTER + "' AND channel_id IN (" + channels + ") AND kind='ALLOCATE')")
        return {"sql_pool_FE": int(rows[0][0]), "sql_allocation_remaining_FE": int(rows[0][1]),
                "local_buffers": {e.name: self.inspect(e) for lane in lanes for e in lane.sources + lane.sinks}}

    def drain(self, lanes, events, seconds=None):
        started = time.monotonic()
        timeout = seconds or max(60.0, self.args.seconds * 2)
        last = None
        while time.monotonic() - started < timeout:
            for lane in lanes:
                for endpoint in lane.sinks:
                    self.pull(lane, endpoint, events)
            if all(lane.accepted == lane.extracted for lane in lanes):
                last = self.residue(lanes)
                if last["sql_pool_FE"] == last["sql_allocation_remaining_FE"] == 0 and all(
                        d["txFE"] == d["rxFE"] == 0 for d in last["local_buffers"].values()):
                    return {"seconds": time.monotonic() - started, "residue": last,
                            "accepted_FE": sum(lane.accepted for lane in lanes),
                            "extracted_FE": sum(lane.extracted for lane in lanes)}
            time.sleep(self.args.poll)
        raise AssertionError("Drain/conservation timeout: " + repr({"lanes": [(l.name, l.accepted, l.extracted) for l in lanes], "residue": last})[:1400])

    def low_flow(self, lanes, sample):
        if not self.args.probes:
            return
        # Low-flow cases have one source and at most two receivers. Hotspots use aggregate outputs.
        if len(lanes) != 1 or len(lanes[0].sources) != 1:
            return
        lane = lanes[0]
        probe_report = sample.setdefault("low_flow", {"probes": [], "events": []})
        events = probe_report["events"]
        first = self.snapshot()
        for index in range(self.args.probes):
            time.sleep(self.args.probe_idle)
            accepted_before = lane.accepted
            source = self.push(lane, lane.sources[0], 1024, events)
            if source["amount"] != 1024:
                raise AssertionError("Isolated low-flow probe not fully accepted")
            targets = []
            limit = time.monotonic() + 30
            while lane.extracted < lane.accepted and time.monotonic() < limit:
                sinks = lane.sinks[index % len(lane.sinks):] + lane.sinks[:index % len(lane.sinks)]
                for endpoint in sinks:
                    target = self.pull(lane, endpoint, events)
                    if target["amount"]:
                        targets.append(target)
                if lane.extracted < lane.accepted:
                    time.sleep(self.args.poll)
            if lane.extracted != lane.accepted or not targets:
                raise AssertionError("Low-flow actual output timeout")
            probe_report["probes"].append({"index": index, "accepted_FE": lane.accepted - accepted_before,
                "first_output": e2e_interval(source, targets[0]), "full_output": e2e_interval(source, targets[-1]),
                "outputs": {e.name: sum(t["amount"] for t in targets if t["endpoint"] == e.name) for e in lane.sinks}})
            if (index + 1) % 10 == 0:
                self.save()
                print(f"{self.args.label}: {sample['scenario']} repeat {sample['repeat']} low-flow {index+1}/{self.args.probes}", flush=True)
        last = self.snapshot()
        probe_report["counter_delta"] = self.deltas(first, last)
        for endpoint in ("first_output", "full_output"):
            probe_report[endpoint + "_lower_ms"] = quantiles([p[endpoint]["lower_ms"] for p in probe_report["probes"]])
            probe_report[endpoint + "_upper_ms"] = quantiles([p[endpoint]["upper_ms"] for p in probe_report["probes"]])
        probe_report["input_rcon_ms"] = quantiles([p["full_output"]["source_rcon_ms"] for p in probe_report["probes"]])
        probe_report["output_rcon_ms"] = quantiles([p["full_output"]["target_rcon_ms"] for p in probe_report["probes"]])
        probe_report["drain"] = self.drain(lanes, events)

    def outputs(self, lanes, events, start, end):
        result = {}
        for lane in lanes:
            for endpoint in lane.sinks:
                successful = [e for e in events if e["kind"] == "output" and e["endpoint"] == endpoint.name and e["amount"]]
                times = [e["end"] for e in successful]
                gaps = [b - a for a, b in zip([start] + times, times + [end])]
                result[endpoint.name] = {"server": endpoint.server, "actual_extracted_FE": sum(e["amount"] for e in successful),
                    "successful_pull_events": len(successful), "max_unserved_seconds": max(gaps),
                    "first_output_seconds": times[0] - start if times else None,
                    "last_output_seconds": times[-1] - start if times else None}
        return result

    def measure(self, name, repetition):
        lanes = self.cases[name]
        sample = {"scenario": name, "repeat": repetition, "passed": False,
                  "warmup_events": [], "events": [], "drain_events": []}
        self.report["samples"].append(sample)
        self.activate(lanes, True)
        try:
            if name in ("same", "cross", "mixed"):
                self.low_flow(lanes, sample)
            sample["warmup"] = self.drive(lanes, self.args.warmup, sample["warmup_events"])
            sample["warmup_drain"] = self.drain(lanes, sample["warmup_events"])
            sample["counter_start"] = self.snapshot()
            started = time.monotonic() - self.started
            if name == "backpressure":
                sample["hold"] = self.drive(lanes, self.report["conditions"]["backpressure_hold_seconds"], sample["events"], extract=False)
                sample["held_residue"] = self.residue(lanes)
                local_held = sum(d["rxFE"] for d in sample["held_residue"]["local_buffers"].values())
                time.sleep(max(2.2, self.args.probe_idle))
                sample["held_residue_after_quiet"] = self.residue(lanes)
                quiet_held = sum(d["rxFE"] for d in sample["held_residue_after_quiet"]["local_buffers"].values())
                sample["backpressure_observed"] = (local_held > 0 and local_held == quiet_held
                    and sample["held_residue_after_quiet"]["sql_pool_FE"] > 0)
                backlog = sum(l.accepted - l.extracted for l in lanes)
                recovery = time.monotonic() - self.started
                sample["recovery"] = self.drain(lanes, sample["events"])
                successful = [e for e in sample["events"] if e["kind"] == "output" and e["amount"]]
                sample["recovery"]["first_actual_output_ms"] = (successful[0]["end"] - recovery) * 1000 if successful else None
                sample["recovery"]["residual_backlog_FE_before_recovery"] = backlog
            else:
                sample["drive"] = self.drive(lanes, self.args.seconds, sample["events"])
            ended = time.monotonic() - self.started
            sample["counter_end"] = self.snapshot()
            sample["counter_delta"] = self.deltas(sample["counter_start"], sample["counter_end"])
            inputs = [e for e in sample["events"] if e["kind"] == "input"]
            outputs = [e for e in sample["events"] if e["kind"] == "output"]
            accepted = sum(e["amount"] for e in inputs)
            extracted = sum(e["amount"] for e in outputs)
            sample["business"] = {"seconds": ended - started, "input_attempts": len(inputs),
                "accepted_input_events": sum(e["amount"] > 0 for e in inputs),
                "fully_accepted_input_events": sum(e["amount"] == e["requested"] for e in inputs),
                "input_attempt_FE": sum(e["requested"] for e in inputs), "accepted_FE": accepted,
                "actual_extracted_FE": extracted, "actual_extracted_FE_per_second": extracted / (ended - started),
                "accepted_FE_per_second": accepted / (ended - started),
                "DBtransactions_per_accepted_input_event": sample["counter_delta"]["db_transactions"] / max(1, sum(e["amount"] > 0 for e in inputs)),
                "DBtransactions_per_1024_extracted_FE": sample["counter_delta"]["db_transactions"] / max(1, extracted / 1024),
                "SQL_statement_events_per_accepted_input_event": sample["counter_delta"]["statements"]["events"] / max(1, sum(e["amount"] > 0 for e in inputs)) if sample["counter_delta"]["statements"] else None}
            sample["sinks"] = self.outputs(lanes, sample["events"], started, ended)
            sample["rcon_ms"] = quantiles([(e["end"] - e["start"]) * 1000 for e in sample["events"]])
            sample["conservation"] = self.drain(lanes, sample["drain_events"])
            sample["passed"] = (all(s["actual_extracted_FE"] > 0 for s in sample["sinks"].values())
                and sample["counter_delta"]["errors"] == sample["counter_delta"]["queue_rejected"] == sample["counter_delta"]["quarantined"] == 0
                and (name != "backpressure" or sample["backpressure_observed"]))
            if not sample["passed"]:
                self.report["failures"].append(f"{name} repeat {repetition}: missing sink service, errors/rejections/quarantine, or no observed backpressure; inspect sample")
            print(json.dumps({"scenario": name, "repeat": repetition, "passed": sample["passed"],
                "business": sample["business"], "sinks": sample["sinks"], "DBtransactions": sample["counter_delta"]["db_transactions"]}, ensure_ascii=False), flush=True)
        except Exception as error:
            sample["failure"] = type(error).__name__ + ": " + str(error)
            self.report["failures"].append(f"{name} repeat {repetition}: " + sample["failure"])
            raise
        finally:
            self.activate(lanes, False)
            self.save()

    def cleanup(self):
        # Do not destroy resources on failure. Preserve failed blocks/chunk tickets
        # as evidence; successful, fully drained fixtures can be retired safely.
        removable = not self.report["failures"] and all(s.get("passed") for s in self.report["samples"])
        for endpoint in self.devices:
            try:
                self.issue(endpoint.server, f"mode {endpoint.x} {endpoint.z} {FE} OFF")
                if removable:
                    state = self.inspect(endpoint)
                    if state["txFE"] or state["rxFE"]:
                        raise AssertionError("Unexpected resource residue; retaining fixture")
                    self.issue(endpoint.server, f"remove {endpoint.x} {endpoint.z}")
                self.report["cleanup"].append({"endpoint": endpoint.name, "removed": removable})
            except Exception as error:
                self.report["cleanup"].append({"endpoint": endpoint.name, "failure": str(error)})
                self.report["failures"].append("Fixture cleanup failed: " + endpoint.name)
                removable = False
        if removable:
            for server, cx, cz in self.loaded_chunks:
                try:
                    self.issue(server, f"forceload remove {cx * 16} {cz * 16}", False)
                except Exception as error:
                    self.report["failures"].append("Vanilla fixture ticket cleanup failed: " + str(error))
        self.report["fixture_retained_for_diagnosis"] = not removable

    def compare(self):
        if not self.args.baseline:
            return
        baseline = json.loads(self.args.baseline.read_text())
        if baseline.get("schema_version") != self.report["schema_version"] or baseline.get("conditions") != self.report["conditions"]:
            raise ValueError("Baseline conditions differ; cannot make a matched regression comparison")
        if not baseline.get("passed"):
            self.report["warnings"].append("Baseline contains functional failures; performance comparison remains diagnostic.")
        comparisons = []
        metrics = {"actual_extracted_FE_per_second": -1,
                   "DBtransactions_per_accepted_input_event": 1,
                   "DBtransactions_per_1024_extracted_FE": 1}
        for scenario in self.args.scenarios:
            old = [s for s in baseline["samples"] if s["scenario"] == scenario and "business" in s]
            new = [s for s in self.report["samples"] if s["scenario"] == scenario and "business" in s]
            if len(old) != self.args.repeats or len(new) != self.args.repeats:
                raise ValueError("Incomplete baseline/current repeated measurements")
            for key, direction in metrics.items():
                before = statistics.median(s["business"][key] for s in old)
                after = statistics.median(s["business"][key] for s in new)
                change = (after / before - 1) * 100 if before else None
                regression = change is not None and direction * change > self.args.max_regression_percent
                comparisons.append({"scenario": scenario, "metric": key, "baseline_median": before,
                                    "current_median": after, "change_percent": change, "regression": regression})
                if regression:
                    self.report["regressions"].append(f"{scenario} {key}: {change:+.1f}%")
            if all(s.get("low_flow", {}).get("probes") for s in old + new):
                before = statistics.median(s["low_flow"]["full_output_upper_ms"]["p95"] for s in old)
                after = statistics.median(s["low_flow"]["full_output_upper_ms"]["p95"] for s in new)
                change = (after / before - 1) * 100 if before else None
                regression = change is not None and change > self.args.max_regression_percent and after - before > 10
                comparisons.append({"scenario": scenario, "metric": "low_flow_full_output_upper_ms_p95",
                    "baseline_median": before, "current_median": after, "change_percent": change, "regression": regression})
                if regression:
                    self.report["regressions"].append(f"{scenario} low-flow p95 upper bound: {change:+.1f}%")
        self.report["comparison"] = {"baseline": str(self.args.baseline),
            "max_regression_percent": self.args.max_regression_percent, "metrics": comparisons}

    def run(self):
        self.save()
        try:
            self.verify_isolation()
            self.setup()
            for repetition in range(1, self.args.repeats + 1):
                # Rotate the case sequence between repeats to reduce ordering bias.
                offset = (repetition - 1) % len(self.args.scenarios)
                names = self.args.scenarios[offset:] + self.args.scenarios[:offset]
                for name in names:
                    self.measure(name, repetition)
            for server, pid in self.pids.items():
                if not re.fullmatch(r"PID " + str(pid) + r"\s*", self.issue(server, "pid")["reply"]):
                    raise AssertionError("JVM PID changed during run: " + server)
            self.compare()
        except KeyboardInterrupt:
            self.report["failures"].append("Run interrupted; accepted resources retained")
        except Exception as error:
            self.report["failures"].append(type(error).__name__ + ": " + str(error))
        finally:
            self.cleanup()
            self.report["elapsed_seconds"] = time.monotonic() - self.started
            self.report["passed"] = not self.report["failures"] and not self.report["regressions"]
            self.save()
        print("Saved " + str(self.target), flush=True)
        if self.report["failures"]:
            print("Failures: " + "; ".join(self.report["failures"]), file=sys.stderr)
        if self.report["regressions"]:
            print("Regressions: " + "; ".join(self.report["regressions"]), file=sys.stderr)
        return 0 if self.report["passed"] else 1


def self_test():
    # Offline checks for observability/conservation helpers; no sockets or SQL.
    status = "STATUS online tickets=0 {transactions=3, db_transactions=17, db_deadlock_retries=0, sql_ms_p95=2.4}"
    assert numeric_fields(status)["db_transactions"] == 17
    assert numeric_fields(status)["sql_ms_p95"] == 2.4
    exponent = numeric_fields("{tiny_ms=9.72E-4, rate=1e+3, negative=-2.5E-3, big=9007199254740993}")
    assert exponent == {"tiny_ms": .000972, "rate": 1000., "negative": -.0025, "big": 9007199254740993}
    assert isinstance(exponent["big"], int)
    assert numeric_fields("{bad=1.2E, truncated=9.72E-4suffix, 3fake=7, good=8}") == {"good": 8}
    try:
        numeric_fields("{overflow=1e999}")
    except ValueError:
        pass
    else:
        raise AssertionError("Non-finite exponent overflow accepted")
    d = device_fields("DEVICE 00000000-0000-4000-8000-000000000001 registered=true pause= channel=null txFE=0 rxFE=12 checkpoint=8")
    assert d["pause"] == "" and d["rxFE"] == 12 and d["registered"]
    interval = e2e_interval({"start": 1.0, "end": 1.1}, {"start": 1.6, "end": 1.7})
    assert abs(interval["lower_ms"] - 500) < 1e-8 and abs(interval["upper_ms"] - 700) < 1e-8
    assert e2e_interval({"start": 1, "end": 2}, {"start": 1.5, "end": 2.2})["lower_ms"] == 0
    assert quantiles(list(range(1, 101))) == {"samples": 100, "p50": 50, "p95": 95, "p99": 99}
    assert quantiles([])["p95"] is None
    print("Offline benchmark helper checks passed; no backend contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--warmup", type=float, default=30)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--probes", type=int, default=40, help="Low-flow probes for same/cross/mixed on every repeat; 0 disables")
    parser.add_argument("--probe-idle", type=float, default=2.2, help="Quiet seconds before every low-flow input")
    parser.add_argument("--poll", type=float, default=.1)
    parser.add_argument("--feed-period", type=float, default=.5, help="Identical attempted source/sink round cadence")
    parser.add_argument("--scenarios", default="same,cross,mixed,backpressure,hotspot", help="Comma-separated subset")
    parser.add_argument("--baseline", type=Path, help="Previous report with identical conditions")
    parser.add_argument("--max-regression-percent", type=float, default=10)
    parser.add_argument("--self-test", action="store_true", help="Offline helper checks only")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    args.scenarios = args.scenarios.split(",")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", args.label):
        parser.error("label must be 1..48 letters, digits, underscore or dash")
    if (not 0 <= args.warmup <= 600 or not 1 <= args.seconds <= 900 or not 1 <= args.repeats <= 20
            or not 0 <= args.probes <= 500 or not 0 <= args.probe_idle <= 30
            or not .02 <= args.poll <= 2 or not .05 <= args.feed_period <= 5
            or not 0 <= args.max_regression_percent <= 100):
        parser.error("benchmark parameter outside bounded development-test range")
    if not args.scenarios or len(set(args.scenarios)) != len(args.scenarios) or any(s not in SCENARIOS for s in args.scenarios):
        parser.error("scenarios must be a unique subset of " + ",".join(SCENARIOS))
    return Benchmark(args).run()


if __name__ == "__main__":
    sys.exit(main())
