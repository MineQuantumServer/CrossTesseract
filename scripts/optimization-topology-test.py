#!/usr/bin/env python3
"""Verify bounded FE topology and lifecycle behavior on three real A/B/C JVMs.

Connects to existing loopback dev_three_v1 servers only. Never starts, stops, or
reconfigures processes/containers. Creates fresh console fixtures; the report
contains raw RCON replies and read-only SQL observations, including failures.
Online-player login, GUI, positive-balance sealed recovery, and crash/restart
recovery are outside this script's scope.
"""
import argparse
import concurrent.futures
from dataclasses import asdict, dataclass, field
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from rcon import command

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = "dev_three_v1"
PORTS = {"A": 25575, "B": 25576, "C": 25577}
FE = "cross_tesseract:fe"
OVERWORLD = "minecraft:overworld"
NETHER = "minecraft:the_nether"
CASES = ("different_chunks", "cross_dimension", "mixed_endpoints", "mode_resume", "replacement")
COUNTERS = ("db_transactions", "db_deadlock_retries", "errors", "queue_rejected", "quarantined")
ASSET_COLUMNS = ("record_type", "id", "endpoint_id", "resource_id", "kind", "state", "amount", "remaining", "epoch")


def helper(name, filename):
    # Register before loading: the benchmark helper contains @dataclass classes.
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


THREE = helper("ct_topology_three_helpers", "three-server-test.py")
BENCH = helper("ct_topology_benchmark_helpers", "optimization-benchmark.py")


@dataclass
class Endpoint:
    name: str
    server: str
    dimension: str
    x: int
    z: int
    owner: str
    id: str = ""
    channel: str = ""
    present: bool = True
    retired: bool = False


@dataclass
class Fixture:
    name: str
    owner: str
    channel: str
    sources: list = field(default_factory=list)
    sinks: list = field(default_factory=list)
    accepted: int = 0
    extracted: int = 0
    input_calls: int = 0
    sink_totals: dict = field(default_factory=dict)

    @property
    def endpoints(self):
        return self.sources + self.sinks


def asset_totals(rows):
    """SQL/local copies represent the same asset; never add both copies."""
    transfers = [dict(zip(ASSET_COLUMNS, row)) for row in rows if row[0] == "transfer"]
    if any(len(row) != len(ASSET_COLUMNS) or row[0] not in ("transfer", "balance") for row in rows):
        raise AssertionError("Malformed asset observation")
    for transfer in transfers:
        for key in ("amount", "remaining", "epoch"):
            transfer[key] = int(transfer[key])
        if transfer["kind"] not in ("DEPOSIT", "ALLOCATE") or not (
                0 <= transfer["remaining"] <= transfer["amount"] and transfer["amount"] > 0):
            raise AssertionError("Invalid transfer: " + repr(transfer))
    deposits = [t for t in transfers if t["kind"] == "DEPOSIT"]
    allocations = [t for t in transfers if t["kind"] == "ALLOCATE"]
    if any(t["state"] != "COMMITTED" or t["remaining"] for t in deposits):
        raise AssertionError("Deposit is not exclusively committed")
    if any(t["state"] not in ("RESERVED", "LOCAL", "CONSUMED", "QUARANTINED") for t in allocations):
        raise AssertionError("Unknown allocation state")
    pool = sum(int(row[6]) for row in rows if row[0] == "balance")
    if pool < 0:
        raise AssertionError("Negative channel balance")
    return {"pool": pool, "owned": sum(t["remaining"] for t in allocations),
            "deposited": sum(t["amount"] for t in deposits),
            "allocated": sum(t["amount"] for t in allocations),
            "deposit_count": len(deposits), "allocation_count": len(allocations),
            "quarantined": [t["id"] for t in allocations if t["state"] == "QUARANTINED"],
            "transfers": transfers}


class Topology:
    def __init__(self, args):
        self.args = args
        self.started = time.monotonic()
        self.token = uuid.uuid4().hex[:10]
        # Stay inside the vanilla world border, far from the other dev fixtures.
        self.base = 1_000_000 + int(self.token[:5], 16) * 16
        self.fixtures = []
        self.devices = []
        self.tickets = set()
        self.lock = threading.Lock()
        self.target = ROOT / "reports" / ("optimization-topology-" + args.label + "-" +
                      time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + self.token[:6] + ".json")
        self.quiet = args.quiet
        self.report = {"schema_version": 1, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "label": args.label, "cluster": CLUSTER, "passed": False,
            "scope": "Three independently verified Minecraft JVMs, real native FE capabilities, real MySQL, trusted console fixtures",
            "conditions": {"cases": args.cases, "operation_timeout_seconds": args.timeout,
                "requested_quiet_seconds": args.quiet, "mixed_rounds": 9, "mixed_input_FE_per_source_per_round": 128,
                "resource": FE, "chunk_separation_blocks": 64},
            "measurement": {"clock": "One Python observer's monotonic clock; event intervals bound observation times",
                "sql": "Read-only SELECTs through the existing isolated development root observer; no SQL mutations",
                "conservation": "Accepted FE = extracted FE + channel pool + SQL-owned remaining. SQL/local/WAL copies are not added together.",
                "dedup": "After actual extraction and SQL consumption, compare exact transfer IDs/amounts/states/remaining and pool rows across at least one configured idle-poll interval",
                "fairness": "Every registered receiving endpoint must receive positive FE; equal shares are not required. Raw global SQL last_grant values are retained.",
                "counters": "Raw cumulative baselines and deltas include ambient fixtures. Earlier quota_exhausted errors and deadlock retries remain in the baseline; aggregate errors do not identify error codes.",
                "wal": "The live runtime persists through its actual world journal; this script observes capabilities and SQL, and does not independently parse WAL bytes or measure fsync.",
                "revision": "Checkout HEAD is recorded; loaded JVM code revision is supplied by the operator and is not independently proven by this harness"},
            "not_tested": ["Online-player authentication and GUI", "ITEM/fluid/EU/chemical/thermal/AE compatibility",
                "Large or sustained performance workload", "Positive-balance removal followed by operator reclaim",
                "Crash, server restart, or world rollback recovery", "Forced unload/reload during an in-flight transaction"],
            "cases": {}, "fixtures": [], "raw_events": [], "warnings": [], "cleanup": []}

    def record(self, kind, start, **values):
        with self.lock:
            if len(self.report["raw_events"]) >= 20_000:
                raise AssertionError("Raw observation bound exceeded; refusing to discard evidence")
            self.report["raw_events"].append({"index": len(self.report["raw_events"]), "kind": kind,
                "start": start, "end": time.monotonic() - self.started, **values})

    def save(self):
        self.report["fixtures"] = [{"name": f.name, "owner": f.owner, "channel": f.channel,
            "sources": [asdict(e) for e in f.sources], "sinks": [asdict(e) for e in f.sinks],
            "accepted_FE": f.accepted, "extracted_FE": f.extracted, "input_calls": f.input_calls,
            "sink_totals_FE": f.sink_totals} for f in self.fixtures]
        self.report["elapsed_seconds"] = time.monotonic() - self.started
        self.target.parent.mkdir(exist_ok=True)
        with self.lock:
            raw = json.dumps(self.report, ensure_ascii=False, indent=2) + "\n"
        temporary = self.target.with_suffix(".json.tmp")
        temporary.write_text(raw)
        temporary.replace(self.target)

    def issue(self, server, value, dimension=OVERWORLD, harness=True):
        if server not in PORTS or dimension not in (OVERWORLD, NETHER):
            raise ValueError("Unsupported fixture server/dimension")
        text = ("ct_test " if harness else "") + value
        if dimension != OVERWORLD:
            text = "execute in " + dimension + " run " + text
        start = time.monotonic() - self.started
        try:
            reply = command(PORTS[server], text, timeout=10)
        except Exception as error:
            self.record("rcon", start, server=server, port=PORTS[server], command=text,
                        exception=type(error).__name__ + ": " + str(error))
            raise
        self.record("rcon", start, server=server, port=PORTS[server], command=text, reply=reply)
        if "ERROR " in reply:
            raise AssertionError(server + ": " + reply)
        return reply

    def sql(self, statement, columns):
        start = time.monotonic() - self.started
        try:
            rows = BENCH.sql(statement)
        except Exception as error:
            self.record("sql", start, statement=statement, columns=columns,
                        exception=type(error).__name__ + ": " + str(error))
            raise
        self.record("sql", start, statement=statement, columns=columns, rows=rows)
        if any(len(row) != len(columns) for row in rows):
            raise AssertionError("SQL observer returned unexpected columns")
        return rows

    def wait(self, read, predicate):
        return THREE.poll(read, predicate, seconds=self.args.timeout)

    def inspect(self, endpoint):
        observed = BENCH.device_fields(self.issue(endpoint.server,
            f"inspect {endpoint.x} {endpoint.z}", endpoint.dimension))
        if endpoint.id and observed["id"] != endpoint.id:
            raise AssertionError("Fixture identity changed: " + repr(asdict(endpoint)))
        return observed

    def counters(self):
        values = {}
        for server in PORTS:
            text = self.issue(server, "status")
            if "STATUS online" not in text:
                raise AssertionError(server + " backend is not online: " + text)
            fields = BENCH.numeric_fields(text)
            if any(key not in fields for key in COUNTERS):
                raise AssertionError("Missing cumulative runtime counters: " + server)
            values[server] = fields
        return values

    def verify_isolation(self):
        if os.environ.get("CT_TEST_CLUSTER", CLUSTER) != CLUSTER or THREE.CLUSTER != CLUSTER:
            raise ValueError("Only the existing dev_three_v1 cluster is accepted")
        if any(key in os.environ for key in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI")):
            raise ValueError("Refusing backend override environment variables")
        identity = {}
        for server, port in PORTS.items():
            directory = ROOT / ("run-" + server)
            path = directory / "cross-tesseract.properties"
            config, vanilla = BENCH.properties(path), BENCH.properties(directory / "server.properties")
            if not (config.get("backend.enabled") == "true" and config.get("cluster.id") == CLUSTER
                    and (config.get("server.id") == "dev-" + server or re.fullmatch(
                        r"opt-[A-Za-z0-9_-]{1,48}-" + server, config.get("server.id", "")))
                    and config.get("mysql.url", "").startswith("jdbc:mysql://127.0.0.1:13306/cross_tesseract?")
                    and config.get("mysql.user") == "ct_dev" and config.get("redis.uri") == "redis://127.0.0.1:16379"
                    and vanilla.get("enable-rcon") == "true" and vanilla.get("rcon.port") == str(port)):
                raise ValueError("Refusing non-isolated configuration: " + server)
            self.wait(lambda: self.issue(server, "status"), lambda text: "STATUS online" in text)
            pid_reply = self.issue(server, "pid")
            match = re.search(r"PID (\d+)", pid_reply)
            if not match:
                raise AssertionError("Unrecognized PID response: " + pid_reply)
            pid = int(match[1])
            raw_argv = Path(f"/proc/{pid}/cmdline").read_bytes()
            argv = [a.decode(errors="replace") for a in raw_argv.split(b"\0") if a]
            expanded, argfiles = BENCH.expanded_vm_args(argv, server, Path(f"/proc/{pid}/cwd").resolve())
            system = {a[2:].split("=", 1)[0]: a.split("=", 1)[1] for a in expanded if a.startswith("-D") and "=" in a}
            if system.get("cross_tesseract.testHarness") != "true" or system.get("cross_tesseract.config") != str(path.resolve()):
                raise ValueError("JVM does not use the isolated fixture config: " + server)
            level = vanilla.get("level-name", "world")
            if level != "world" and not re.fullmatch(r"world-opt-[A-Za-z0-9_-]{1,64}", level):
                raise ValueError("Unexpected fixture world directory: " + server)
            world = str(uuid.UUID((directory / level / "cross_tesseract/world-id").read_text().strip()))
            capacity = int(config.get("buffers.fe", "2000000"))
            if capacity < 8192:
                raise ValueError("This bounded fixture requires at least 8192 FE capacity: " + server)
            idle = 2000
            # Select this non-secret property without logging the config file.
            for line in path.read_text().splitlines():
                if "=" in line and line.split("=", 1)[0].strip() == "transfer.idlePollMillis":
                    idle = int(line.split("=", 1)[1].strip())
            if not 500 <= idle <= 6000:
                raise ValueError("Unexpected transfer idle polling interval")
            self.quiet = max(self.quiet, idle / 1000 + .5)
            identity[server] = {"pid": pid, "port": port, "server_id": config["server.id"], "world_id": world,
                "level_name": level, "buffer_capacity_FE": capacity, "idle_poll_millis": idle,
                "java_executable": str(Path(f"/proc/{pid}/exe").resolve()),
                "argv_sha256": hashlib.sha256(raw_argv).hexdigest(), "vm_argfiles": argfiles,
                "verified_system_properties": {key: system[key] for key in (
                    "cross_tesseract.testHarness", "cross_tesseract.config")}}
        if len({i["pid"] for i in identity.values()}) != 3 or len({i["world_id"] for i in identity.values()}) != 3:
            raise ValueError("Three distinct Minecraft PIDs and world identities are required")
        inspected = BENCH.docker(["inspect", "--format",
            "{{json .NetworkSettings.Ports}}|{{.Config.Image}}|{{.State.Running}}", "ct-dev-mysql"])
        ports, image, running = inspected.rsplit("|", 2)
        if image not in (BENCH.MYSQL_IMAGE, "mysql:8.4.7") or running != "true" or not any(
                p.get("HostIp") == "127.0.0.1" and p.get("HostPort") == "13306"
                for p in json.loads(ports).get("3306/tcp") or []):
            raise ValueError("Refusing unrelated MySQL container or non-loopback binding")
        for server, info in identity.items():
            rows = self.sql(f"SELECT world_id,session_id,fencing_epoch FROM ct_servers WHERE cluster_id='{CLUSTER}' "
                f"AND server_id='{info['server_id']}' AND lease_until>CURRENT_TIMESTAMP(6)",
                ["world_id", "session_id", "fencing_epoch"])
            if len(rows) != 1 or rows[0][0] != info["world_id"]:
                raise ValueError("Missing matching live backend session: " + server)
            info.update(session_id=rows[0][1], fencing_epoch=int(rows[0][2]))
        self.report["identity"] = identity
        self.report["effective_quiet_seconds"] = self.quiet
        self.report["baseline_counters"] = self.counters()
        self.report["git_head"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        self.report["git_worktree_status"] = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
            capture_output=True, text=True, check=True, timeout=10).stdout.splitlines()
        self.record("isolation", time.monotonic() - self.started, mysql=image, running=running, ports=json.loads(ports))
        self.save()

    def fixture(self, name):
        owner, channel_name = str(uuid.uuid4()), "top_" + self.token + "_" + name
        self.issue("A", f"create {owner} {channel_name}")
        rows = self.wait(lambda: self.sql(f"SELECT channel_id FROM ct_channels WHERE cluster_id='{CLUSTER}' "
            f"AND owner_uuid='{owner}' AND name='{channel_name}'", ["channel_id"]), bool)
        if len(rows) != 1:
            raise AssertionError("Ambiguous fresh fixture channel")
        fixture = Fixture(name, owner, str(uuid.UUID(rows[0][0])))
        self.fixtures.append(fixture)
        self.save()
        return fixture

    def acquire_chunk(self, server, dimension, x, z):
        ticket = (server, dimension, x // 16, z // 16)
        if ticket in self.tickets:
            return
        reply = self.issue(server, f"forceload query {x} {z}", dimension, harness=False)
        if "marked for force loading" in reply.lower() and "not" not in reply.lower():
            raise AssertionError("Fresh fixture chunk already force loaded; refusing to reuse an ambient ticket")
        reply = self.issue(server, f"forceload add {x} {z}", dimension, harness=False)
        if "marked" not in reply.lower() or "already" in reply.lower() or "no chunks" in reply.lower():
            raise AssertionError("Fresh chunk ticket could not be acquired: " + reply)
        self.tickets.add(ticket)

    def endpoint(self, fixture, name, server, x, z=384, dimension=OVERWORLD, role="source", bind=True):
        self.acquire_chunk(server, dimension, x, z)
        reply = self.issue(server, f"spawn {x} {z} {fixture.owner}", dimension)
        match = re.search(r"SPAWN ([\w-]+)", reply)
        if not match:
            raise AssertionError("No new endpoint identity: " + reply)
        endpoint = Endpoint(name, server, dimension, x, z, fixture.owner, str(uuid.UUID(match[1])))
        self.devices.append(endpoint)
        (fixture.sources if role == "source" else fixture.sinks).append(endpoint)
        self.save()  # Retain the ID even if registration/binding subsequently fails.
        self.wait(lambda: self.inspect(endpoint), lambda d: d["registered"])
        self.mode(endpoint, "OFF")
        if bind:
            self.bind(endpoint, fixture.channel)
        return endpoint

    def bind(self, endpoint, channel):
        self.issue(endpoint.server, f"bind {endpoint.x} {endpoint.z} {channel}", endpoint.dimension)
        self.wait(lambda: self.inspect(endpoint), lambda d: d["channel"] == channel and not d["pause"])
        endpoint.channel = channel

    def mode(self, endpoint, mode):
        self.issue(endpoint.server, f"mode {endpoint.x} {endpoint.z} {FE} {mode}", endpoint.dimension)

    def fe(self, endpoint, direction, amount):
        reply = self.issue(endpoint.server, f"{direction}-fe {endpoint.x} {endpoint.z} {amount}", endpoint.dimension)
        word = "ACCEPTED" if direction == "push" else "EXTRACTED"
        match = re.search(word + r" (\d+)", reply)
        if not match:
            raise AssertionError("Unrecognized real FE capability response: " + reply)
        result = int(match[1])
        if not 0 <= result <= amount:
            raise AssertionError("Invalid FE capability quantity")
        return result

    def feed(self, fixture, source, amount):
        accepted = self.fe(source, "push", amount)
        fixture.accepted += accepted
        fixture.input_calls += 1
        if accepted != amount:
            raise AssertionError("Bounded real FE fixture rejected input: " + repr(asdict(source)))

    def assets(self, fixture):
        # One SELECT, hence one consistent InnoDB read view for balances + transfers.
        predicate = f"cluster_id='{CLUSTER}' AND channel_id='{fixture.channel}'"
        rows = self.sql("SELECT 'transfer',transfer_id,endpoint_id,resource_id,kind,state,CAST(amount AS CHAR),"
            "CAST(remaining AS CHAR),CAST(epoch AS CHAR) FROM ct_transfers WHERE " + predicate +
            " UNION ALL SELECT 'balance',resource_id,'',resource_id,'','',CAST(amount AS CHAR),'0','0' "
            "FROM ct_balances WHERE " + predicate + " ORDER BY 1,2", list(ASSET_COLUMNS))
        return {"rows": rows, **asset_totals(rows)}

    def observed(self, fixture):
        return {"buffers": {e.id: self.inspect(e) for e in fixture.endpoints if e.present},
                "assets": self.assets(fixture)}

    def await_received(self, fixture):
        pending = fixture.accepted - fixture.extracted
        def settled(value):
            buffers, assets = value["buffers"], value["assets"]
            return (all(b["txFE"] == 0 for b in buffers.values())
                and sum(buffers[e.id]["rxFE"] for e in fixture.sinks) == pending
                and all(buffers[e.id]["rxFE"] == 0 for e in fixture.sources)
                and assets["pool"] == 0 and assets["owned"] == pending
                and assets["deposited"] == fixture.accepted and assets["allocated"] == fixture.accepted)
        result = self.wait(lambda: self.observed(fixture), settled)
        if result["assets"]["quarantined"]:
            raise AssertionError("Healthy fixture asset was quarantined")
        return result

    def drain(self, fixture):
        expected = fixture.accepted - fixture.extracted
        taken = 0
        for sink in fixture.sinks:
            amount = self.fe(sink, "pull", 2_147_483_647)
            fixture.sink_totals[sink.id] = fixture.sink_totals.get(sink.id, 0) + amount
            fixture.extracted += amount
            taken += amount
        if taken != expected:
            raise AssertionError(f"Actual extraction {taken} differs from outstanding {expected}")

    def verify_locations(self, fixture):
        for endpoint in fixture.endpoints:
            info = self.report["identity"][endpoint.server]
            rows = self.sql(f"SELECT server_id,world_id,dimension_id,pos_x,pos_y,pos_z,device_owner,"
                f"COALESCE(channel_id,'<null>'),state FROM ct_endpoints WHERE cluster_id='{CLUSTER}' "
                f"AND endpoint_id='{endpoint.id}'", ["server_id", "world_id", "dimension_id", "x", "y", "z", "owner", "channel", "state"])
            expected = [[info["server_id"], info["world_id"], endpoint.dimension, str(endpoint.x), "64", str(endpoint.z),
                         endpoint.owner, endpoint.channel or "<null>", "ACTIVE"]]
            if rows != expected:
                raise AssertionError("Persisted endpoint identity/location/binding differs: " + repr(rows))

    def demands(self, fixture):
        return self.sql("SELECT d.endpoint_id,e.server_id,d.room,d.last_grant FROM ct_demands d JOIN ct_endpoints e "
            "ON e.cluster_id=d.cluster_id AND e.endpoint_id=d.endpoint_id "
            f"WHERE d.cluster_id='{CLUSTER}' AND d.channel_id='{fixture.channel}' AND d.kind='{FE}' "
            "AND d.expires_at>CURRENT_TIMESTAMP(6) ORDER BY d.endpoint_id", ["endpoint_id", "server_id", "room", "last_grant"])

    def stationary(self, fixture):
        def empty(observed):
            return (all(b["txFE"] == b["rxFE"] == 0 for b in observed["buffers"].values())
                and observed["assets"]["pool"] == observed["assets"]["owned"] == 0
                and all(t["state"] == "CONSUMED" for t in observed["assets"]["transfers"] if t["kind"] == "ALLOCATE"))
        before = self.wait(lambda: self.observed(fixture), empty)
        assets = before["assets"]
        if not (fixture.accepted == fixture.extracted == assets["deposited"] == assets["allocated"]
                and assets["deposit_count"] == fixture.input_calls and not assets["quarantined"]):
            raise AssertionError("Exact transfer business IDs/quantities do not match actual capability calls")
        resources = self.sql("SELECT DISTINCT r.resource_id,r.kind,r.format_version,"
            "COALESCE(NULLIF(HEX(r.payload),''),'<empty>') FROM ct_resources r "
            "JOIN ct_transfers t ON t.cluster_id=r.cluster_id AND t.resource_id=r.resource_id "
            f"WHERE t.cluster_id='{CLUSTER}' AND t.channel_id='{fixture.channel}' ORDER BY r.resource_id",
            ["resource_id", "kind", "format_version", "payload_hex"])
        if len(resources) != 1 or resources[0][1:] != [FE, "1", "<empty>"]:
            raise AssertionError("Unexpected native FE resource identity: " + repr(resources))
        quiet_start = time.monotonic()
        time.sleep(self.quiet)
        after = self.observed(fixture)
        if not empty(after) or before["assets"]["rows"] != after["assets"]["rows"]:
            raise AssertionError("Asset rows changed or local FE reappeared during stationary dedup check")
        return {"quiet_seconds": time.monotonic() - quiet_start,
            "accepted_FE": fixture.accepted, "actual_extracted_FE": fixture.extracted,
            "before": before, "after": after, "resource_rows": resources,
            "proof": "Exact SQL transfer IDs and quantities stable; all local FE and SQL remaining/pool zero"}

    def pair(self, name, source_server, target_server, cross_dimension=False):
        fixture = self.fixture(name)
        x = self.base + CASES.index(name) * 512
        source = self.endpoint(fixture, name + "_source", source_server, x)
        sink = self.endpoint(fixture, name + "_sink", target_server,
            x if cross_dimension else x + 64, dimension=NETHER if cross_dimension else OVERWORLD, role="sink")
        self.mode(source, "SEND")
        self.mode(sink, "RECEIVE")
        self.verify_locations(fixture)
        return fixture, source, sink

    def different_chunks(self):
        fixture, source, sink = self.pair("different_chunks", "A", "A")
        if source.x // 16 == sink.x // 16 or sink.x - source.x != 64:
            raise AssertionError("Same-server chunk fixture does not cover distinct chunks")
        self.feed(fixture, source, 4096)
        delivered = self.await_received(fixture)
        self.drain(fixture)
        return {"delivery": delivered, "stationary": self.stationary(fixture)}

    def cross_dimension(self):
        fixture, source, sink = self.pair("cross_dimension", "A", "A", cross_dimension=True)
        if (source.x, source.z) != (sink.x, sink.z) or source.dimension == sink.dimension:
            raise AssertionError("Cross-dimension fixture is not at the same coordinates in different dimensions")
        self.feed(fixture, source, 3072)
        delivered = self.await_received(fixture)
        self.drain(fixture)
        return {"delivery": delivered, "stationary": self.stationary(fixture)}

    def mixed_endpoints(self):
        fixture = self.fixture("mixed_endpoints")
        x = self.base + CASES.index("mixed_endpoints") * 512
        for index, server in enumerate(PORTS):
            self.endpoint(fixture, "mixed_source_" + server, server, x + index * 64)
            self.endpoint(fixture, "mixed_sink_" + server, server, x + index * 64 + 256, role="sink")
        for source in fixture.sources:
            self.mode(source, "SEND")
        for sink in fixture.sinks:
            self.mode(sink, "RECEIVE")
        self.verify_locations(fixture)
        sink_ids = {e.id for e in fixture.sinks}
        registered = self.wait(lambda: self.demands(fixture), lambda rows:
            {row[0] for row in rows} == sink_ids and all(int(row[2]) > 0 for row in rows))
        rounds = []
        for index in range(9):
            # Actual RCON calls overlap across three separate game processes.
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                accepted = list(executor.map(lambda e: self.fe(e, "push", 128), fixture.sources))
            fixture.accepted += sum(accepted)
            fixture.input_calls += len(accepted)
            if accepted != [128, 128, 128]:
                raise AssertionError("Mixed source capability admission failed: " + repr(accepted))
            delivered = self.await_received(fixture)
            grants = self.demands(fixture)
            self.drain(fixture)
            rounds.append({"round": index + 1, "input_FE_by_source": dict(zip((e.id for e in fixture.sources), accepted)),
                "delivery": delivered, "global_sql_last_grant": grants, "cumulative_extracted_by_endpoint": dict(fixture.sink_totals)})
            self.save()
        if any(fixture.sink_totals.get(sink.id, 0) <= 0 for sink in fixture.sinks):
            raise AssertionError("A registered endpoint starved in the shared local/remote fairness protocol")
        final_grants = self.demands(fixture)
        if ({row[0] for row in final_grants} != sink_ids
                or any(int(row[3]) <= 0 for row in final_grants)
                or len({int(row[3]) for row in final_grants}) != 3):
            raise AssertionError("Mixed receiving endpoints did not retain distinct positive global SQL grant positions")
        return {"initial_registered_demands": registered, "rounds": rounds,
                "final_global_sql_last_grant": final_grants,
                "per_endpoint_extracted_FE": fixture.sink_totals, "stationary": self.stationary(fixture)}

    def mode_resume(self):
        fixture, source, sink = self.pair("mode_resume", "A", "B")
        self.feed(fixture, source, 256)
        first = self.await_received(fixture)
        self.mode(sink, "OFF")
        if self.fe(sink, "pull", 64) != 0 or self.fe(sink, "push", 32) != 0:
            raise AssertionError("OFF mode exposed a native resource capability")
        self.feed(fixture, source, 128)
        def held(value):
            a = value["assets"]
            return (value["buffers"][source.id]["txFE"] == 0 and a["deposited"] == 384
                    and a["pool"] + a["owned"] == 384)
        off = self.wait(lambda: self.observed(fixture), held)
        if not 256 <= off["buffers"][sink.id]["rxFE"] <= 384 or off["assets"]["quarantined"]:
            raise AssertionError("Mode change lost the existing receiver allocation")
        time.sleep(self.quiet)
        if self.fe(sink, "pull", 2_147_483_647) != 0:
            raise AssertionError("OFF capability became readable after background completion")
        self.mode(sink, "RECEIVE")
        resumed = self.await_received(fixture)
        self.drain(fixture)
        return {"initial_delivery": first, "while_OFF": off, "after_RECEIVE": resumed,
            "mode_semantics": "OFF denies local input/output; an earlier registered/in-flight allocation may remain exclusively owned until RECEIVE resumes",
            "stationary": self.stationary(fixture)}

    def replacement(self):
        old, source, sink = self.pair("replacement", "A", "B")
        self.feed(old, source, 321)
        old_delivery = self.await_received(old)
        self.drain(old)
        old_stationary = self.stationary(old)
        self.mode(sink, "OFF")
        self.issue(sink.server, f"remove {sink.x} {sink.z}", sink.dimension)
        sink.present = False
        retired = self.wait(lambda: self.sql(f"SELECT state,COALESCE(channel_id,'<null>') FROM ct_endpoints "
            f"WHERE cluster_id='{CLUSTER}' AND endpoint_id='{sink.id}'", ["state", "channel_id"]),
            lambda rows: rows == [["RETIRED", "<null>"]])
        sink.retired = True
        sink.channel = ""
        fresh = self.fixture("replacement_fresh")
        replacement = self.endpoint(fresh, "replacement_new_owner", sink.server, sink.x, sink.z,
            sink.dimension, role="sink", bind=False)
        if replacement.id == sink.id or replacement.owner == sink.owner:
            raise AssertionError("Replacement inherited old endpoint/owner identity")
        initial = self.inspect(replacement)
        if initial["channel"] != "null" or initial["txFE"] or initial["rxFE"]:
            raise AssertionError("Replacement inherited old binding or local assets")
        self.verify_locations(fresh)
        history = self.sql(f"SELECT COUNT(*) FROM ct_transfers WHERE cluster_id='{CLUSTER}' "
            f"AND endpoint_id='{replacement.id}'", ["transfer_count"])
        grants = self.sql(f"SELECT COUNT(*) FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' "
            f"AND endpoint_id='{replacement.id}'", ["grant_count"])
        inherited_membership = self.sql(f"SELECT COUNT(*) FROM ct_members WHERE cluster_id='{CLUSTER}' "
            f"AND channel_id='{old.channel}' AND player_uuid='{fresh.owner}'", ["membership_count"])
        if history != [["0"]] or grants != [["0"]] or inherited_membership != [["0"]]:
            raise AssertionError("New identity inherited SQL assets, ticket authority, or old membership")
        self.mode(replacement, "BOTH")
        if self.fe(replacement, "push", 17) != 0 or self.fe(replacement, "pull", 17) != 0:
            raise AssertionError("Unbound replacement exposed old resource authority")
        self.mode(replacement, "OFF")
        self.bind(replacement, fresh.channel)
        fresh_source = self.endpoint(fresh, "replacement_fresh_source", "A", source.x + 64)
        self.mode(fresh_source, "SEND")
        self.mode(replacement, "RECEIVE")
        self.verify_locations(fresh)
        self.feed(fresh, fresh_source, 97)
        new_delivery = self.await_received(fresh)
        self.drain(fresh)
        new_stationary = self.stationary(fresh)
        if self.assets(old)["rows"] != old_stationary["after"]["assets"]["rows"]:
            raise AssertionError("Old endpoint transfer history replayed during replacement traffic")
        return {"old_delivery": old_delivery, "old_stationary": old_stationary, "old_endpoint_retired": retired,
            "new_unbound_device": initial, "new_identity_SQL_counts": {"transfers": history, "grants": grants,
                "old_channel_membership": inherited_membership}, "new_delivery": new_delivery,
            "new_stationary": new_stationary,
            "scope": "Old 321 FE was actually extracted before removal; empty sealed endpoint retired. Positive sealed assets and manual reclaim are explicitly untested."}

    def cleanup(self, fixtures, passed):
        endpoints = [e for f in fixtures for e in f.endpoints]
        for endpoint in endpoints:
            if not endpoint.present:
                continue
            try:
                self.mode(endpoint, "OFF")
                if not passed:
                    self.report["cleanup"].append({"endpoint": endpoint.id, "action": "retained", "reason": "failed fixture retained with native mode OFF"})
                    continue
                current = self.inspect(endpoint)
                remaining = self.sql(f"SELECT COALESCE(SUM(remaining),0) FROM ct_transfers WHERE cluster_id='{CLUSTER}' "
                    f"AND endpoint_id='{endpoint.id}' AND kind='ALLOCATE'", ["owned_remaining"])
                if current["txFE"] or current["rxFE"] or remaining != [["0"]]:
                    raise AssertionError("Cleanup refused an endpoint with unconsumed assets")
                self.issue(endpoint.server, f"remove {endpoint.x} {endpoint.z}", endpoint.dimension)
                endpoint.present = False
                self.wait(lambda: self.sql(f"SELECT state FROM ct_endpoints WHERE cluster_id='{CLUSTER}' "
                    f"AND endpoint_id='{endpoint.id}'", ["state"]), lambda rows: rows == [["RETIRED"]])
                endpoint.retired = True
                endpoint.channel = ""
                self.report["cleanup"].append({"endpoint": endpoint.id, "action": "removed_empty_and_retired"})
            except Exception as error:
                self.report["warnings"].append("Cleanup retained fixture/ticket for inspection: " + endpoint.id + " " + str(error)[:700])
        for ticket in list(self.tickets):
            server, dimension, cx, cz = ticket
            related = [e for e in self.devices if (e.server, e.dimension, e.x // 16, e.z // 16) == ticket]
            if related and all(not e.present and e.retired for e in related):
                try:
                    self.issue(server, f"forceload remove {cx * 16} {cz * 16}", dimension, harness=False)
                    self.tickets.remove(ticket)
                    self.report["cleanup"].append({"ticket": ticket, "action": "removed_owned_vanilla_ticket"})
                except Exception as error:
                    self.report["warnings"].append("Vanilla fixture ticket retained: " + repr(ticket) + " " + str(error)[:700])
        self.report["retained_vanilla_tickets"] = sorted(self.tickets)
        self.save()

    def verify_sessions_unchanged(self):
        for server, original in self.report["identity"].items():
            pid = self.issue(server, "pid")
            if not re.search(r"PID " + str(original["pid"]) + r"\b", pid):
                raise AssertionError("Minecraft JVM restarted during topology verification")
            rows = self.sql(f"SELECT world_id,session_id,fencing_epoch FROM ct_servers WHERE cluster_id='{CLUSTER}' "
                f"AND server_id='{original['server_id']}' AND lease_until>CURRENT_TIMESTAMP(6)",
                ["world_id", "session_id", "fencing_epoch"])
            if rows != [[original["world_id"], original["session_id"], str(original["fencing_epoch"])]]:
                raise AssertionError("Backend session or fencing epoch changed during verification")

    def run(self):
        try:
            self.verify_isolation()
            for name in self.args.cases:
                start, first_fixture = time.monotonic(), len(self.fixtures)
                case = self.report["cases"][name] = {"passed": False}
                try:
                    case["result"] = getattr(self, name)()
                    case["passed"] = True
                except Exception as error:
                    case["failure"] = {"type": type(error).__name__, "message": str(error)[:4000]}
                finally:
                    case["elapsed_seconds"] = time.monotonic() - start
                    self.save()
                    self.cleanup(self.fixtures[first_fixture:], case["passed"])
                print(name + ": " + ("PASS" if case["passed"] else "FAIL"), flush=True)
            self.verify_sessions_unchanged()
            final = self.report["final_counters"] = self.counters()
            baseline = self.report["baseline_counters"]
            changes = {server: {key: final[server][key] - baseline[server][key] for key in COUNTERS} for server in PORTS}
            if any(delta < 0 for values in changes.values() for delta in values.values()):
                raise AssertionError("Cumulative runtime counter reset during verification")
            self.report["counter_deltas"] = changes
            if any(values["errors"] or values["quarantined"] for values in changes.values()):
                self.report["warnings"].append("Runtime errors/quarantines increased; cumulative counters include ambient devices. Review raw fixture evidence and server logs for attribution.")
            self.report["passed"] = all(case["passed"] for case in self.report["cases"].values())
        except Exception as error:
            self.report["fatal_failure"] = {"type": type(error).__name__, "message": str(error)[:4000]}
            if self.devices:
                self.cleanup(self.fixtures, False)
        finally:
            self.save()
            print("report: " + str(self.target), flush=True)
        return 0 if self.report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="verify", help="Non-secret report label")
    parser.add_argument("--timeout", type=float, default=45, help="Bounded per-operation wait, seconds (10..120)")
    parser.add_argument("--quiet", type=float, default=3, help="Dedup observation wait, seconds (3..15); raised to configured idle poll + .5")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label):
        parser.error("label must be 1..48 letters, digits, underscores, or hyphens")
    if not 10 <= args.timeout <= 120 or not 3 <= args.quiet <= 15:
        parser.error("timeout or quiet interval outside the bounded range")
    if len(set(args.cases)) != len(args.cases):
        parser.error("duplicate cases are not accepted")
    return Topology(args).run()


if __name__ == "__main__":
    sys.exit(main())
