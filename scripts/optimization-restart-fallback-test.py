#!/usr/bin/env python3
"""Real same-world FE assets across fast -> legacy -> fast clean restarts.

Default and --self-test are offline. --execute is restricted to the existing
loopback dev_three_v1 ABC world-opt-regression-68f32db-fast fixtures and exact
68f32db launch assets. No build, force kill, backend lifecycle, SQL mutation,
world deletion or automatic failure cleanup. Run after the other fast regression
cases, with one RCON observer and no concurrent workloads/controllers.
"""
import argparse
import base64
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import functools
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CORE = "68f32db439f445b8f72faf92dc62fbc5b9dce738"
CLUSTER = "dev_three_v1"
PORTS = {"A": 25575, "B": 25576, "C": 25577}
FE = "cross_tesseract:fe"
FLAGS = ("transfer.channelBatches", "transfer.localFastPath")
FIXTURE = "regression-68f32db-fast"
MAX_WAL = 8_388_608
MAX_EVENTS = 25_000


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module(name, filename):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def bounded_file(path, limit=1_048_576):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Expected bounded regular fixture file: " + str(path))
    return path.read_bytes()


def properties(raw):
    values = {}
    for line in raw.decode("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        if "=" not in line or line.endswith("\\"):
            raise ValueError("Requires canonical non-continuation development properties")
        key, value = (part.strip() for part in line.split("=", 1))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", key) or key in values:
            raise ValueError("Non-canonical or duplicate property key")
        values[key] = value
    return values


def properties_semantic_sha(raw):
    """Hash all non-comment property bytes, including significant value spaces.

    Properties.store rewrites its date comment. Remove only comment lines and
    normalize line terminators; preserve every remaining byte and line order.
    Only the digest is recorded. First validate the restricted fixture syntax.
    """
    properties(raw)
    return sha(b"\n".join(line for line in raw.splitlines()
        if not line.lstrip().startswith((b"#", b"!"))))


def require_same_fixture_files(current, original):
    keys = ("server_id", "world_id", "level_name", "server_properties_semantic_sha256",
        "eula_sha256", "world_id_file_sha256")
    if any(current[key] != original[key] for key in keys):
        raise AssertionError("World/server/EULA identity or server.properties values changed")


def flag_rewrite(raw, expected, wanted):
    """Replace two literal values, preserving every other byte and line ending."""
    values = properties(raw)
    if tuple(values.get(key) for key in FLAGS) != expected:
        raise ValueError("Flags changed unexpectedly; refusing replacement")
    changed = raw
    for key, value in zip(FLAGS, wanted):
        pattern = rb"(?m)^([ \t]*" + re.escape(key.encode()) + rb"[ \t]*=[ \t]*)(?:true|false)([ \t]*\r?$)"
        changed, count = re.subn(pattern, lambda match: match[1] + value.encode() + match[2], changed)
        if count != 1:
            raise ValueError("Flag must have one canonical explicit definition")
    before, after = properties(raw), properties(changed)
    if {key: value for key, value in before.items() if key not in FLAGS} != {
            key: value for key, value in after.items() if key not in FLAGS}:
        raise AssertionError("A non-flag property changed")
    if flag_rewrite_check(changed, wanted, expected) != raw:
        raise AssertionError("Flag replacement cannot restore identical original bytes")
    return changed


def flag_rewrite_check(raw, expected, wanted):
    if tuple(properties(raw).get(key) for key in FLAGS) != expected:
        raise ValueError("Wrong intermediate flags")
    for key, value in zip(FLAGS, wanted):
        pattern = rb"(?m)^([ \t]*" + re.escape(key.encode()) + rb"[ \t]*=[ \t]*)(?:true|false)([ \t]*\r?$)"
        raw, count = re.subn(pattern, lambda match: match[1] + value.encode() + match[2], raw)
        if count != 1:
            raise ValueError("Noncanonical intermediate flag")
    return raw


def decode_fe_wal(data):
    """Bounded CTT1 v1/v2 reader matching LocalJournal; FE-only, no Java launch.

    Java writeUTF is read only for the fixed ASCII FE kind, with an empty payload.
    Unknown resources, duplicate IDs, thermal assets, trailing bytes and a bad
    SHA256 trailer are rejected rather than partially decoded.
    """
    if not 36 <= len(data) <= MAX_WAL or sha(data[:-32]) != data[-32:].hex():
        raise ValueError("Invalid WAL size/checksum")
    body, offset = data[:-32], 0

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(body):
            raise ValueError("Truncated WAL")
        value = body[offset:offset + size]
        offset += size
        return value

    def number(fmt):
        return struct.unpack(fmt, take(struct.calcsize(fmt)))[0]

    def identity():
        return str(uuid.UUID(bytes=take(16)))

    def count():
        value = number(">i")
        if not 0 <= value <= 64:
            raise ValueError("WAL entry bound exceeded")
        return value

    def resource():
        n = number(">H")
        if n != len(FE.encode()) or take(n) != FE.encode() or number(">i") != 0:
            raise ValueError("Only fixed ASCII empty-payload native FE WAL is accepted")
        return {"kind": FE, "payload_hex": "", "payload_sha256": sha(b"")}

    magic, version = number(">i"), number(">i")
    if magic != 0x43545431 or version not in (1, 2):
        raise ValueError("Unsupported WAL format")
    result = {"format": version, "endpoint": identity(), "world": identity(),
        "generation": number(">q"), "revision": number(">q"), "deposits": [], "credits": []}
    if result["generation"] < 0 or result["revision"] < 0:
        raise ValueError("Negative WAL generation/revision")
    ids = set()
    for kind in ("deposits", "credits"):
        for _ in range(count()):
            entry = {"transaction": identity(), "channel": identity(), "resource": resource()}
            entry["amount" if kind == "deposits" else "original"] = number(">q")
            if kind == "credits":
                entry["remaining"] = number(">q")
            amount = entry.get("amount", entry.get("original"))
            if amount <= 0 or not 0 <= entry.get("remaining", 0) <= amount or entry["transaction"] in ids:
                raise ValueError("Invalid/duplicate WAL transaction")
            ids.add(entry["transaction"])
            result[kind].append(entry)
    thermal = {"microjoules": 0, "residual": 0.0, "pending": False}
    if version == 2:
        thermal = {"microjoules": number(">q"), "residual": number(">d"), "pending": bool(number(">B"))}
    if thermal != {"microjoules": 0, "residual": 0.0, "pending": False} or not math.isfinite(thermal["residual"]):
        raise ValueError("Thermal/unknown assets outside this FE-only fixture")
    if offset != len(body):
        raise ValueError("Trailing WAL bytes")
    return {**result, "thermal": thermal, "sha256": sha(data), "size_bytes": len(data),
        "checksum_verified": True, "raw_base64": base64.b64encode(data).decode()}


def mode_reply(reply, endpoint):
    match = re.fullmatch(r'\s*(-?\d+),\s*(-?\d+),\s*(-?\d+) has the following block data:\s*"(OFF|SEND|RECEIVE|BOTH)"\s*', reply)
    if not match or tuple(map(int, match.group(1, 2, 3))) != (endpoint.x, 64, endpoint.z):
        raise ValueError("Mode read must match the owned block coordinates and one literal mode")
    return match[4]


def asset_ledger(accepted, extracted, pool, owned):
    if min(accepted, extracted, pool, owned) < 0 or accepted != extracted + pool + owned:
        raise AssertionError("Independent FE ledger does not conserve assets")
    return {"actually_accepted_FE": accepted, "actually_extracted_FE": extracted,
        "SQL_pool_FE": pool, "SQL_owned_remaining_FE": owned,
        "conserved": True, "scope": "SQL ownership ledger; local/WAL receipts are verified mirrors, not additional assets."}


def require_fe_resource_rows(rows):
    # bench.sql strips the whole TSV response. A final empty HEX(payload)
    # would lose its trailing tab; an explicit prefix preserves that column.
    if rows and (len(rows) != 1 or len(rows[0]) != 4 or rows[0][1:] != [FE, "1", "hex:"]):
        raise AssertionError("Unexpected resource identity in native FE channel")


def sole_checkpoint_progress(values, predicate):
    """Classify a read skew without treating the adjusted view as real evidence.

    Only the copied SQL endpoint checkpoint may be raised to that SAME endpoint's
    observed WAL revision. Every other asset/credit/business-ID predicate must
    still pass. The original read view is never changed or accepted as quiet.
    """
    view, ahead = copy.deepcopy(values), []
    for channel, point in view.items():
        for endpoint, wal in point["WAL"].items():
            if wal is None:
                continue
            row = point["endpoint_rows"][endpoint]
            checkpoint, revision = int(row["checkpoint"]), wal["revision"]
            if revision > checkpoint:
                ahead.append({"channel": channel, "endpoint": endpoint,
                    "observed_SQL_checkpoint": checkpoint, "observed_WAL_revision": revision})
                row["checkpoint"] = str(revision)
    return ahead if ahead and predicate(view) else []


def bounded_state(method):
    @functools.wraps(method)
    def run(self, *args, **kwargs):
        previous = self.read_deadline
        until = time.monotonic() + self.args.timeout
        self.read_deadline = until if previous is None else min(until, previous)
        try:
            return method(self, *args, **kwargs)
        finally:
            self.read_deadline = previous
    return run


class RestartFallback:
    def __init__(self, args):
        self.args = args
        self.started = time.monotonic()
        self.token = uuid.uuid4().hex
        self.phase = "NOT_RUN"
        self.target = ROOT / "reports" / ("optimization-restart-fallback-68f32db-" +
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + self.token[:8] + ".json")
        self.backups = ROOT / "scratch/optimization/restart-fallback" / self.token
        self.top = self.bench = self.container = None
        self.initial_files = {}
        self.current_config = {}
        self.launches = {}
        self.held = {}
        self.locks = {}
        self.read_deadline = None
        self.report = {"schema_version": 1, "utc_start": utc(), "passed": False,
            "execution_status": "NOT_RUN", "operator_runtime_revision": CORE, "cluster": CLUSTER,
            "method": "Same worlds/server/world UUIDs and immutable class selection through clean fast->legacy->fast restarts, two new native FE channels only.",
            "conditions": {"fixture_label": FIXTURE, "timeout_each_state_seconds": args.timeout,
                "minimum_quiet_seconds": args.quiet, "poll_seconds": args.poll,
                "initial_input_FE": 128, "initial_actual_output_FE": 53,
                "held_LOCAL_FE": 75, "second_input_shared_pool_FE": 61, "final_actual_output_FE": 136,
                "demand_TTL_seconds": 6, "layouts": ["A->A different chunks", "A->B"]},
            "scope_notes": {"clock": "One Python monotonic observer, request/reply/read spans; no cross-JVM nanoTime subtraction or exact world-save timestamp.",
                "asset_accounting": "Actual inputs189 and outputs53 + SQL LOCAL remaining75 + shared pool61 per channel before restart. SQL/WAL/local mirrors never added.",
                "WAL": "Own endpoint .ctj bytes only, bounded SHA256/CTT1 protocol decode linked to exact SQL business IDs. File evidence and clean-stop SQL acknowledgement, not an independent fsync instrument.",
                "RCON": "Single observer, raw command bodies retained; native shared console bodies have no request-specific business nonce.",
                "not_tested": ["Physical chest", "ITEM/fluid/EU/thermal", "Crash/rollback atomicity", "Performance/TPS/capacity", "Online-player identity/GUI"],
                "failure": "No replay of unknown input/extraction, no automatic flags restore/stop/cleanup/force kill. Keep last actual configuration and assets for operator diagnosis.",
                "cleanup": "Keep the four validated empty devices and own vanilla load tickets on success for parent normal stop; no world deletion."},
            "raw_events": [], "business_events": [], "identity_boots": [], "states": {},
            "config_switches": [], "process_lifecycle": [], "warnings": [], "cleanup": [], "failures": []}
        self.report["script_file"] = {"path": str(Path(__file__)), "sha256": sha(Path(__file__).read_bytes())}

    def save(self):
        self.report["phase"] = self.phase
        self.report["elapsed_seconds"] = time.monotonic() - self.started
        if self.top is not None:
            self.report["fixtures"] = [{"name": f.name, "owner": f.owner, "channel": f.channel,
                "sources": [asdict(e) for e in f.sources], "sinks": [asdict(e) for e in f.sinks],
                "actual_accepted_FE": f.accepted, "actual_extracted_FE": f.extracted,
                "input_calls": f.input_calls, "actual_sink_totals_FE": f.sink_totals} for f in self.top.fixtures]
            self.report["retained_vanilla_tickets"] = sorted(self.top.tickets)
        self.target.parent.mkdir(exist_ok=True)
        temporary = self.target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(self.target)

    def record(self, kind, start, **values):
        if len(self.report["raw_events"]) >= MAX_EVENTS:
            raise AssertionError("Raw evidence bound exceeded; no evidence is discarded")
        event = {"index": len(self.report["raw_events"]), "phase": self.phase, "kind": kind,
            "start": start, "end": time.monotonic() - self.started, **values}
        self.report["raw_events"].append(event)
        return event

    def remaining_timeout(self, maximum):
        remaining = maximum if self.read_deadline is None else min(maximum, self.read_deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Bounded state deadline expired")
        return remaining

    def issue(self, server, value, dimension="minecraft:overworld", harness=True):
        if server not in PORTS or dimension != "minecraft:overworld":
            raise ValueError("Only the owned ABC overworld fixtures are supported")
        command = ("ct_test " if harness else "") + value
        mutation = not (value.startswith(("inspect ", "data get ", "forceload query ", "execute if block ")) or value in ("status", "pid"))
        start = time.monotonic() - self.started
        try:
            timeout = self.remaining_timeout(10)
            reply = self.bench.command(PORTS[server], command, timeout=timeout)
        except Exception as error:
            self.record("rcon", start, server=server, port=PORTS[server], command=command,
                mutation=mutation, outcome="UNKNOWN_NO_REPLAY" if mutation else "READ_FAILED",
                exception=type(error).__name__ + ": " + str(error))
            raise
        if len(reply.encode()) > 65536:
            raise ValueError("RCON reply exceeds bounded evidence collection")
        self.record("rcon", start, server=server, port=PORTS[server], command=command,
            mutation=mutation, outcome="REPLY_OBSERVED", reply=reply)
        if "ERROR " in reply:
            raise AssertionError(server + ": " + reply)
        return reply

    def sql(self, statement, columns):
        start = time.monotonic() - self.started
        try:
            # The reused isolated SELECT helper has a20s bounded subprocess.
            # Do not begin it with less remaining state budget.
            if self.read_deadline is not None and self.read_deadline - time.monotonic() < 20:
                raise TimeoutError("Insufficient remaining state budget for bounded SQL SELECT")
            rows = self.bench.sql(statement)
        except Exception as error:
            self.record("SQL_SELECT", start, statement=statement, columns=columns,
                exception=type(error).__name__ + ": " + str(error))
            raise
        self.record("SQL_SELECT", start, statement=statement, columns=columns, rows=rows)
        if len(rows) > 128 or any(len(row) != len(columns) for row in rows):
            raise AssertionError("Unexpected/bounded SQL observation")
        return rows

    def wait(self, read, predicate):
        until = time.monotonic() + self.args.timeout
        previous_deadline = self.read_deadline
        self.read_deadline = until if previous_deadline is None else min(until, previous_deadline)
        last = None
        try:
            while time.monotonic() < self.read_deadline:
                last = read()  # Only read functions are supplied; mutations are never polled.
                if predicate(last):
                    return last
                time.sleep(self.args.poll)
            raise AssertionError("State timeout, last recorded observation: " + repr(last)[:1500])
        finally:
            self.read_deadline = previous_deadline

    def environment_gate(self):
        if os.environ.get("CT_TEST_CLUSTER", CLUSTER) != CLUSTER:
            raise ValueError("Only dev_three_v1 is allowed")
        if any(key in os.environ for key in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI",
                "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "JAVA_TOOL_OPTIONS")):
            raise ValueError("Backend/JVM override environment is not accepted; wrapper supplies its own proxy/CA options")

    def files_gate(self, expected_flags):
        self.environment_gate()
        result = {}
        for server, port in PORTS.items():
            run = ROOT / ("run-" + server)
            if run.is_symlink() or not run.is_dir():
                raise ValueError("Expected repository-owned fixture cwd")
            config_path = run / "cross-tesseract.properties"
            config_raw = bounded_file(config_path)
            vanilla_raw, eula_raw = bounded_file(run / "server.properties"), bounded_file(run / "eula.txt")
            config, vanilla, eula = properties(config_raw), properties(vanilla_raw), properties(eula_raw)
            if not (config.get("cluster.id") == CLUSTER and config.get("backend.enabled") == "true"
                    and config.get("server.id") == "opt-" + FIXTURE + "-" + server
                    and config.get("mysql.user") == "ct_dev"
                    and config.get("mysql.url", "").startswith("jdbc:mysql://127.0.0.1:13306/cross_tesseract?")
                    and config.get("redis.uri") == "redis://127.0.0.1:16379"
                    and vanilla.get("server-ip") == "127.0.0.1" and vanilla.get("rcon.port") == str(port)
                    and vanilla.get("enable-rcon") == "true" and eula.get("eula") == "true"
                    and vanilla.get("level-name") == "world-opt-" + FIXTURE + "-" + server
                    and tuple(config.get(key) for key in FLAGS) == expected_flags):
                raise ValueError("Refusing a different/non-isolated regression fixture or flags: " + server)
            world = run / vanilla["level-name"]
            if world.is_symlink() or not world.is_dir():
                raise ValueError("Same existing world directory required")
            local_state = world / "cross_tesseract"
            if local_state.is_symlink() or local_state.resolve().parent != world.resolve():
                raise ValueError("World local state must not escape through a symlink")
            world_id_path = world / "cross_tesseract/world-id"
            world_raw = bounded_file(world_id_path, 128)
            world_id = str(uuid.UUID(world_raw.decode().strip()))
            item = {"server_id": config["server.id"], "world_id": world_id,
                "level_name": vanilla["level-name"], "config_path": str(config_path),
                "config_sha256": sha(config_raw), "server_properties_sha256": sha(vanilla_raw),
                "server_properties_semantic_sha256": properties_semantic_sha(vanilla_raw),
                "eula_sha256": sha(eula_raw), "world_id_file_sha256": sha(world_raw),
                "transfer_flags": dict(zip(FLAGS, expected_flags))}
            if self.initial_files:
                original = self.initial_files[server]
                require_same_fixture_files(item, original)
                if config_raw != self.current_config[server]:
                    raise AssertionError("Configuration changed outside the two controlled flags")
            else:
                self.current_config[server] = config_raw
            result[server] = item
        return result

    def source_gate(self):
        path = ROOT / "reports/optimization-artifact-ready-final.json"
        raw = bounded_file(path)
        expected = json.loads(raw)
        sources = sorted((ROOT / "src/main/java").rglob("*.java"))
        digest = sha(b"".join(str(p.relative_to(ROOT)).encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest() for p in sources))
        artifact = next(a for a in expected["artifacts"] if a["path"] == "build/libs/cross_tesseract-0.1.0-dev.jar")
        jar = ROOT / artifact["path"]
        if expected["source_revision"] != CORE or digest != expected["source_manifest_sha256"] or sha(bounded_file(jar, 32 * 1024 * 1024)) != artifact["sha256"]:
            raise ValueError("Source/JAR no longer matches exact68 regression revision")
        manifest = self.container.jar_manifest(jar)
        self.expected_jar_files = {item["relative_path"]: item["sha256"] for item in manifest["files"]}
        selected = [ROOT / "scripts" / name for name in ("optimization-benchmark.py", "three-server-test.py",
            "optimization-topology-test.py", "optimization-container-benchmark.py", "start-frozen-dev.sh")]
        selected += [ROOT / name for name in ("src/main/java/dev/crosstesseract/backend/LocalJournal.java",
            "src/main/java/dev/crosstesseract/core/LocalSnapshot.java", "src/main/java/dev/crosstesseract/runtime/RuntimeService.java",
            "src/main/java/dev/crosstesseract/block/TesseractBlockEntity.java")]
        self.report["source_evidence"] = {"artifact_ready_file": str(path), "artifact_ready_sha256": sha(raw),
            "declared_revision": CORE, "source_manifest_sha256": digest, "current_JAR": str(jar),
            "current_JAR_sha256": artifact["sha256"], "own_script_sha256": sha(Path(__file__).read_bytes()),
            "helpers_and_protocol_sources": [{"path": str(p), "sha256": sha(p.read_bytes())} for p in selected]}

    def provenance(self, stage, expected_flags, restarted=False):
        files = self.files_gate(expected_flags)
        self.source_gate()
        previous = self.report["identity_boots"][-1]["identity"] if self.report["identity_boots"] else None
        self.top.verify_isolation()
        identities = json.loads(json.dumps(self.report["identity"]))
        server_ids = ",".join("'" + item["server_id"] + "'" for item in identities.values())
        others = self.sql("SELECT cluster_id,server_id FROM ct_servers WHERE lease_until>CURRENT_TIMESTAMP(6) "
            "AND NOT (cluster_id='dev_three_v1' AND server_id IN (" + server_ids + "))", ["cluster", "server_id"])
        if others:
            raise AssertionError("Other live backend sessions; no isolated restart test")
        generation = self.sql("SELECT recovery_generation FROM ct_clusters WHERE cluster_id='dev_three_v1'", ["generation"])
        if len(generation) != 1:
            raise AssertionError("Missing unique cluster recovery generation")
        self.generation = int(generation[0][0])
        for server, identity in identities.items():
            if identity["world_id"] != files[server]["world_id"] or identity["server_id"] != files[server]["server_id"]:
                raise AssertionError("RCON/SQL/file identities disagree")
            vm = identity["vm_argfiles"]
            if len(vm) != 1:
                raise ValueError("Exactly one bounded original VM argfile is required")
            directory = Path(vm[0]["path"]).parent
            if directory.parent != ROOT / "scratch/dev-launch" or not re.fullmatch(r"[0-9a-f]{32}", directory.name):
                raise ValueError("An existing immutable dev freeze is required")
            launch = directory / ("runServer" + server + ".sh")
            checked = subprocess.run(["bash", str(ROOT / "scripts/start-frozen-dev.sh"), "--check", server, str(launch)],
                cwd=ROOT, capture_output=True, text=True, timeout=self.remaining_timeout(20))
            if checked.returncode:
                raise ValueError("Frozen launch file check rejected: " + checked.stderr[:700])
            argv_raw = Path(f"/proc/{identity['pid']}/cmdline").read_bytes()
            argv = [part.decode() for part in argv_raw.split(b"\0") if part]
            selected = "-Dfml.modFolders=cross_tesseract%%" + str(directory / "classes") + ":cross_tesseract%%" + str(directory / "resources")
            if argv.count(selected) != 1 or any(a.startswith("-Dfml.modFolders=") and a != selected for a in argv):
                raise ValueError("JVM does not select only its own recorded frozen mod folders")
            manifests = [self.container.class_manifest(directory / suffix) for suffix in ("classes", "resources")]
            own_class_names = set()
            for manifest in manifests:
                for item in manifest["files"]:
                    name = item["relative_path"]
                    if name.startswith("dev/crosstesseract/") and name.endswith(".class"):
                        own_class_names.add(name)
                        if self.expected_jar_files.get(name) != item["sha256"]:
                            raise AssertionError("Launch class differs from exact68 ready JAR: " + name)
            expected_class_names = {name for name in self.expected_jar_files if name.startswith("dev/crosstesseract/") and name.endswith(".class")}
            if not own_class_names or own_class_names != expected_class_names:
                raise AssertionError("Selected native mod class set differs from exact68 ready JAR")
            asset = {"launcher": str(launch), "launcher_sha256": sha(bounded_file(launch)),
                "argument_files": [{"path": str(directory / ("server" + server + suffix + ".txt")),
                    "sha256": sha(bounded_file(directory / ("server" + server + suffix + ".txt")))}
                    for suffix in ("RunVmArgs", "RunProgramArgs", "RunClasspath")],
                "selected_fml_argument": selected, "selected_launch_manifests": manifests,
                "wrapper_file_only_check": json.loads(checked.stdout),
                "resolution_limit": "Selected folders and byte equality with ready JAR; no independent class-loader CodeSource attestation."}
            if self.launches:
                first = self.launches[server]
                if any(asset[key] != first[key] for key in ("launcher", "launcher_sha256", "argument_files", "selected_fml_argument", "selected_launch_manifests")):
                    raise AssertionError("Actual frozen class/resource/launch files changed across restart")
            else:
                # All three entries are collected before installing the baseline map below.
                pass
            identity.update(launch_provenance=asset, observed_files=files[server], recovery_generation=self.generation)
            if restarted:
                old = previous[server]
                if identity["pid"] == old["pid"] or identity["session_id"] == old["session_id"] or identity["fencing_epoch"] != old["fencing_epoch"] + 1:
                    raise AssertionError("Expected one new clean fenced session/PID on same world")
                if any(identity[key] != old[key] for key in ("server_id", "world_id", "level_name", "java_executable", "recovery_generation")):
                    raise AssertionError("Same-world/runtime identity changed")
        if not self.launches:
            self.launches = {server: identities[server]["launch_provenance"] for server in PORTS}
        self.report["identity"] = identities
        self.report["identity_boots"].append({"stage": stage, "utc": utc(), "identity": identities,
            "files": files, "transfer_flags": dict(zip(FLAGS, expected_flags)), "baseline_counters": self.top.counters()})
        self.report["effective_quiet_seconds"] = self.top.quiet
        self.save()

    def wal(self, endpoint):
        identity = self.report["identity"][endpoint.server]
        world = ROOT / ("run-" + endpoint.server) / identity["level_name"]
        root = world / "cross_tesseract/journal"
        path = root / (endpoint.id + ".ctj")
        if not path.exists():
            return None
        if root.is_symlink() or not root.resolve().is_relative_to(world.resolve()) or path.resolve().parent != root.resolve() or path.is_symlink():
            raise ValueError("Endpoint WAL escaped its owned world journal")
        start = time.monotonic() - self.started
        result = decode_fe_wal(bounded_file(path, MAX_WAL))
        if (result["endpoint"], result["world"], result["generation"]) != (endpoint.id, identity["world_id"], self.generation):
            raise AssertionError("Endpoint WAL identity/generation changed")
        self.record("owned_WAL_read", start, path=str(path), decoded=result)
        return result

    def frame(self, fixture):
        observed = self.top.observed(fixture)
        endpoint_ids = ",".join("'" + e.id + "'" for e in fixture.endpoints)
        columns = ["endpoint", "server", "world", "channel", "owner", "state", "pause", "checkpoint", "epoch", "generation", "x", "y", "z", "dimension"]
        rows = self.sql("SELECT endpoint_id,server_id,world_id,COALESCE(channel_id,''),device_owner,state,pause_reason,"
            "checkpoint,last_epoch,recovery_generation,pos_x,pos_y,pos_z,dimension_id FROM ct_endpoints "
            f"WHERE cluster_id='{CLUSTER}' AND endpoint_id IN ({endpoint_ids}) ORDER BY endpoint_id", columns)
        if len(rows) != 2:
            raise AssertionError("Missing/duplicate persisted original endpoint IDs")
        locations = {row[0]: dict(zip(columns, row)) for row in rows}
        for endpoint in fixture.endpoints:
            row, identity = locations[endpoint.id], self.report["identity"][endpoint.server]
            expected = [identity["server_id"], identity["world_id"], fixture.channel, fixture.owner, "ACTIVE", ""]
            if [row[k] for k in ("server", "world", "channel", "owner", "state", "pause")] != expected:
                raise AssertionError("Original endpoint location/ownership/state changed")
            if [row[k] for k in ("x", "y", "z", "dimension")] != [str(endpoint.x), "64", str(endpoint.z), "minecraft:overworld"]:
                raise AssertionError("Original endpoint moved")
            if int(row["epoch"]) != identity["fencing_epoch"] or int(row["generation"]) != self.generation:
                raise AssertionError("Endpoint was not restored under the current fenced session")
        demands = self.sql("SELECT endpoint_id,room,CAST(expires_at AS CHAR),expires_at>CURRENT_TIMESTAMP(6),last_grant "
            f"FROM ct_demands WHERE cluster_id='{CLUSTER}' AND channel_id='{fixture.channel}' AND kind='{FE}' ORDER BY endpoint_id",
            ["endpoint", "room", "expires_at", "unexpired", "last_grant"])
        resources = self.sql("SELECT DISTINCT r.resource_id,r.kind,r.format_version,CONCAT('hex:',HEX(r.payload)) FROM ct_resources r "
            "JOIN ct_transfers t ON t.cluster_id=r.cluster_id AND t.resource_id=r.resource_id "
            f"WHERE t.cluster_id='{CLUSTER}' AND t.channel_id='{fixture.channel}' ORDER BY r.resource_id",
            ["resource_id", "kind", "format", "payload_hex_prefixed"])
        require_fe_resource_rows(resources)
        observed.update(endpoint_rows=locations, WAL={e.id: self.wal(e) for e in fixture.endpoints},
            demands=demands, resource_rows=resources, observer_end=time.monotonic() - self.started)
        return observed

    def credit_state(self, fixture, value, accepted, extracted, pool, remaining, allocation_count):
        assets, buffers = value["assets"], value["buffers"]
        if not (fixture.accepted == accepted and fixture.extracted == extracted and assets["deposited"] == accepted
                and assets["pool"] == pool and assets["owned"] == remaining and assets["allocation_count"] == allocation_count
                and not assets["quarantined"] and all(b["registered"] and not b["pause"] and b["txFE"] == 0
                    and all(b[key] == 0 for key in ("txItem", "rxItem", "txFluid", "rxFluid")) for b in buffers.values())
                and buffers[fixture.sources[0].id]["rxFE"] == 0 and buffers[fixture.sinks[0].id]["rxFE"] == remaining):
            return False
        allocations = [t for t in assets["transfers"] if t["kind"] == "ALLOCATE"]
        if any(t["state"] != ("LOCAL" if t["remaining"] else "CONSUMED") for t in allocations):
            return False
        for endpoint in fixture.endpoints:
            wal = value["WAL"][endpoint.id]
            if wal is None or wal["deposits"] or wal["revision"] > int(value["endpoint_rows"][endpoint.id]["checkpoint"]):
                return False
            known = {t["id"]: t for t in allocations if t["endpoint_id"] == endpoint.id}
            for credit in wal["credits"]:
                transfer = known.get(credit["transaction"])
                if transfer is None or credit["channel"] != fixture.channel or (credit["original"], credit["remaining"]) != (transfer["amount"], transfer["remaining"]):
                    return False
            positive = {c["transaction"]: (c["channel"], c["original"], c["remaining"]) for c in wal["credits"] if c["remaining"] > 0}
            owned = {t["id"]: (fixture.channel, t["amount"], t["remaining"]) for t in allocations
                if t["endpoint_id"] == endpoint.id and t["remaining"] > 0}
            if positive != owned:
                return False
        asset_ledger(accepted, extracted, pool, remaining)
        return True

    def fe(self, fixture, endpoint, kind, amount, expected, purpose):
        entry = {"phase": self.phase, "channel": fixture.channel, "fixture": fixture.name,
            "endpoint": endpoint.id, "kind": kind, "requested_FE": amount, "actual_FE": None,
            "purpose": purpose, "outcome": "UNKNOWN_NO_REPLAY", "raw_event_index": len(self.report["raw_events"])}
        self.report["business_events"].append(entry)
        self.save()  # Unknown is persisted before the one native mutation attempt.
        reply = self.issue(endpoint.server, f"{'push' if kind == 'input' else 'pull'}-fe {endpoint.x} {endpoint.z} {amount}")
        word = "ACCEPTED" if kind == "input" else "EXTRACTED"
        match = re.fullmatch(r"\s*" + word + r" (\d+)\s*", reply)
        if not match or not 0 <= int(match[1]) <= amount:
            raise AssertionError("Uncertain/noncanonical native FE result; no retry")
        actual = int(match[1])
        entry.update(actual_FE=actual, outcome="ACTUAL_REPLY_CONFIRMED",
            request_reply_interval={key: self.report["raw_events"][-1][key] for key in ("start", "end")}, reply=reply)
        if kind == "input":
            fixture.accepted += actual
            fixture.input_calls += 1
        else:
            fixture.extracted += actual
            fixture.sink_totals[endpoint.id] = fixture.sink_totals.get(endpoint.id, 0) + actual
        self.save()
        if actual != expected or fixture.extracted > fixture.accepted:
            raise AssertionError("Native FE amount differs from the fixed accepted/extracted ledger")
        return entry

    def read_mode(self, endpoint):
        return mode_reply(self.issue(endpoint.server,
            f'data get block {endpoint.x} 64 {endpoint.z} ports."{FE}".mode', harness=False), endpoint)

    def quiet(self, name, read, predicate):
        previous_deadline = self.read_deadline
        until = time.monotonic() + self.args.timeout
        self.read_deadline = until if previous_deadline is None else min(until, previous_deadline)
        result = {"quiet_seconds": 0, "snapshots": [], "passed": False,
            "checkpoint_in_progress_raw_indexes": [], "continuous_snapshot_start_index": None,
            "scope": "All actual read attempts retained. Only the final uninterrupted full-predicate guard counts; checkpoint-only skew resets it. Sampled reads, not an atomic cross-JVM snapshot."}
        self.report["states"][name] = result
        start = None
        try:
            # A just-completed external pull may still be checkpointing its
            # SQL remaining. Preserve the original convergence gate, within the
            # SAME total deadline. Strict quiet begins only at its first pass.
            first = self.wait(read, predicate)
            result["snapshots"].append(first)
            start = time.monotonic()
            result["continuous_snapshot_start_index"] = 0
            while time.monotonic() < self.read_deadline:
                time.sleep(self.args.poll)
                observed_start = time.monotonic() - self.started
                point = read()
                result["snapshots"].append(point)
                if time.monotonic() >= self.read_deadline:
                    raise AssertionError("Quiet-state timeout; observation crossed the fixed deadline")
                if not predicate(point):
                    ahead = sole_checkpoint_progress(point, predicate)
                    if not ahead:
                        raise AssertionError("Assets changed during guarded quiet state")
                    result["checkpoint_in_progress_raw_indexes"].append(len(self.report["raw_events"]))
                    self.record("quiet_checkpoint_in_progress", observed_start, quiet_state=name,
                        checkpoint_differences=ahead, actual_snapshot=point,
                        disposition="RESET_CONTINUOUS_QUIET_TIMER; adjusted copy only classified read skew, not accepted evidence")
                    start = None
                    result["continuous_snapshot_start_index"] = None
                    result["quiet_seconds"] = 0
                    self.save()
                else:
                    if start is None:
                        start = time.monotonic()
                        result["continuous_snapshot_start_index"] = len(result["snapshots"]) - 1
                    result["quiet_seconds"] = time.monotonic() - start
                    if result["quiet_seconds"] >= self.top.quiet:
                        result["passed"] = True
                        self.save()
                        return result
            raise AssertionError("Quiet-state timeout; fixed deadline was not extended by checkpoint read skew")
        finally:
            self.read_deadline = previous_deadline

    def prepare(self):
        for index, (name, sink_server) in enumerate((("same", "A"), ("cross", "B"))):
            fixture = self.top.fixture("restart_" + name)
            x = (self.top.base // 16) * 16 + 4 + index * 128
            for position, server in ((x, "A"), (x + 64, sink_server)):
                self.top.acquire_chunk(server, "minecraft:overworld", position, 768)
                air = self.issue(server, f"execute if block {position} 64 768 minecraft:air", harness=False)
                if air.strip() != "Test passed":
                    raise AssertionError("Fresh owned fixture location is not confirmed air")
            source = self.top.endpoint(fixture, "restart_" + name + "_source", "A", x, z=768)
            sink = self.top.endpoint(fixture, "restart_" + name + "_sink", sink_server, x + 64, z=768, role="sink")
            self.top.mode(source, "SEND")
            self.top.mode(sink, "RECEIVE")
            self.top.verify_locations(fixture)
            self.fe(fixture, source, "input", 128, 128, "initial input, never replayed")
            received = self.wait(lambda: self.frame(fixture), lambda value: self.credit_state(fixture, value, 128, 0, 0, 128, 1))
            allocation = next(t for t in received["assets"]["transfers"] if t["kind"] == "ALLOCATE")
            self.fe(fixture, sink, "output", 53, 53, "partial actual external capability extraction")
            self.top.mode(sink, "OFF")
            off_end = self.report["raw_events"][-1]["end"]
            if self.read_mode(sink) != "OFF":
                raise AssertionError("Receiver did not enter OFF")
            partial = self.wait(lambda: self.frame(fixture), lambda value: self.credit_state(fixture, value, 128, 53, 0, 75, 1)
                and value["observer_end"] - off_end >= 6.2 and all(row[3] == "0" for row in value["demands"]))
            self.fe(fixture, source, "input", 61, 61, "second fixed input after actual demand expiry")
            pending = self.wait(lambda: self.frame(fixture), lambda value: self.credit_state(fixture, value, 189, 53, 61, 75, 1)
                and all(row[3] == "0" for row in value["demands"]))
            deposits = [t for t in pending["assets"]["transfers"] if t["kind"] == "DEPOSIT"]
            if sorted(t["amount"] for t in deposits) != [61, 128] or allocation["id"] not in {t["id"] for t in pending["assets"]["transfers"]}:
                raise AssertionError("Original allocation or exact two deposit identities changed")
            self.held[fixture.channel] = {"original_allocation_id": allocation["id"], "deposits": deposits,
                "initial_received": received, "OFF_durable75_demand_expired": partial,
                "pending_before_restart": pending, "ledger": asset_ledger(189, 53, 61, 75),
                "OFF_reply_end": off_end, "observed_TTL_wait_seconds": partial["observer_end"] - off_end}
            self.report["held_business_ids"] = self.held
            self.save()
        self.quiet("fast_pending_both_channels", self.all_frames, self.pending_all)

    def all_frames(self):
        return {f.channel: self.frame(f) for f in self.top.fixtures}

    def pending_all(self, values):
        for fixture in self.top.fixtures:
            value, saved = values[fixture.channel], self.held[fixture.channel]
            if not self.credit_state(fixture, value, 189, 53, 61, 75, 1) or any(row[3] != "0" for row in value["demands"]):
                return False
            original = [t for t in value["assets"]["transfers"] if t["kind"] == "ALLOCATE"]
            deposits = [t for t in value["assets"]["transfers"] if t["kind"] == "DEPOSIT"]
            if len(original) != 1 or original[0]["id"] != saved["original_allocation_id"] or original[0]["amount"] != 128 or deposits != saved["deposits"]:
                raise AssertionError("Original positive business IDs were duplicated/replaced")
        return True

    def running(self):
        found = {server: [] for server in (*PORTS, "perf")}
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                raw = (proc / "cmdline").read_bytes()
                argv = [arg for arg in raw.split(b"\0") if arg]
                if not argv or Path(argv[0].decode()).name != "java":
                    continue
                cwd = (proc / "cwd").resolve()
                for server in found:
                    title = "Perf" if server == "perf" else server
                    if cwd == ROOT / ("run-" + server) or any(("server" + title + "RunVmArgs.txt").encode() in arg for arg in argv):
                        found[server].append(int(proc.name))
            except FileNotFoundError:
                continue
            except PermissionError as error:
                raise ValueError("Cannot confirm all supervised test JVMs") from error
        return found

    def acquire_stopped_locks(self):
        acquired = {}
        try:
            for server in PORTS:
                path = ROOT / "scratch" / ("server-" + server + ".launch.lock")
                if path.is_symlink():
                    raise ValueError("Launch lock symlink is not accepted")
                handle = path.open("a")
                acquired[server] = handle
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if any(self.running().values()):
                raise BlockingIOError("A selected test JVM is still running")
            return acquired
        except (BlockingIOError, OSError):
            for handle in acquired.values():
                handle.close()
            return None
        except Exception:
            for handle in acquired.values():
                handle.close()
            raise

    @bounded_state
    def stop_clean(self, name, expected_flags):
        self.files_gate(expected_flags)
        before = self.running()
        if before.get("perf") or any(before[server] != [self.report["identity"][server]["pid"]] for server in PORTS):
            raise AssertionError("Process set changed before normal stop")
        self.report["process_lifecycle"].append({"name": name, "action": "normal_stop_requested_once_per_server", "utc": utc(), "PIDs": before})
        self.save()
        for server in PORTS:
            try:
                self.issue(server, "stop", harness=False)
            except Exception:
                # No replay. Process exit + clean SQL marker below can resolve a
                # closed response. Never enqueue RCON status while shutting down.
                pass
        self.locks = self.wait(self.acquire_stopped_locks, bool)
        self.files_gate(expected_flags)
        columns = ["server", "world", "session", "epoch", "status", "clean_stop", "unexpired"]
        rows = self.sql("SELECT server_id,world_id,session_id,fencing_epoch,status,clean_stop,lease_until>CURRENT_TIMESTAMP(6) "
            "FROM ct_servers WHERE cluster_id='dev_three_v1' AND server_id IN (" +
            ",".join("'" + self.report["identity"][s]["server_id"] + "'" for s in PORTS) + ") ORDER BY server_id", columns)
        expected = sorted([[i["server_id"], i["world_id"], i["session_id"], str(i["fencing_epoch"]), "STOPPED", "1", "0"]
            for i in self.report["identity"].values()])
        if rows != expected:
            raise AssertionError("Native shutdown did not acknowledge clean, same-session stops")
        self.report["process_lifecycle"].append({"name": name, "action": "all_PIDs_gone_all_launch_locks_held_clean_SQL_stop", "utc": utc(), "SQL_rows": rows})
        self.save()

    def switch_flags(self, name, before, after):
        if set(self.locks) != set(PORTS) or any(self.running().values()):
            raise AssertionError("Must hold all stopped launch locks before flag edits")
        self.files_gate(before)
        directory = self.backups / name
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.report["config_switches"].append({"name": name, "from": dict(zip(FLAGS, before)),
            "to": dict(zip(FLAGS, after)), "backup_directory": str(directory), "files": [], "complete": False})
        entry = self.report["config_switches"][-1]
        self.save()
        for server in PORTS:
            path = ROOT / ("run-" + server) / "cross-tesseract.properties"
            raw = bounded_file(path)
            if raw != self.current_config[server] or any(self.running().values()):
                raise AssertionError("Process/config changed under stopped launch locks")
            backup = directory / (server + "-cross-tesseract.properties")
            with backup.open("xb") as stream:
                os.chmod(backup, 0o600)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            changed = flag_rewrite(raw, before, after)
            temporary = path.with_name(path.name + ".restart-fallback-" + self.token)
            with temporary.open("xb") as stream:
                os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
                stream.write(changed)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
            self.current_config[server] = changed
            entry["files"].append({"server": server, "path": str(path), "backup_path": str(backup),
                "before_sha256": sha(raw), "after_sha256": sha(changed), "only_two_flag_values_changed": True})
            self.save()
        self.files_gate(after)
        entry["complete"] = True
        self.save()

    @bounded_state
    def restart(self, name, flags):
        self.files_gate(flags)
        if set(self.locks) != set(PORTS) or any(self.running().values()):
            raise AssertionError("Restart requires stopped guarded fixtures")
        launches = []
        for server in PORTS:
            launch = self.launches[server]
            if sha(bounded_file(Path(launch["launcher"]))) != launch["launcher_sha256"]:
                raise AssertionError("Frozen launcher changed")
        # Release only after all configurations and original launch files passed.
        for handle in self.locks.values():
            handle.close()
        self.locks = {}
        for server in PORTS:
            log = ROOT / "logs" / ("optimization-restart-fallback-" + self.token[:8] + "-" + name + "-" + server + ".log")
            with log.open("x") as stream:
                process = subprocess.Popen(["bash", str(ROOT / "scripts/start-frozen-dev.sh"), server,
                    self.launches[server]["launcher"]], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            launches.append({"server": server, "launcher_PID": process.pid, "log": str(log), "process": process})
        self.report["process_lifecycle"].append({"name": name, "action": "same_immutable_launches_requested_once", "utc": utc(),
            "launches": [{key: value for key, value in item.items() if key != "process"} for item in launches]})
        self.save()

        def ready():
            result = {}
            for item in launches:
                if item["process"].poll() is not None:
                    raise AssertionError("Original frozen restart wrapper exited; retained log " + item["log"])
                try:
                    result[item["server"]] = self.issue(item["server"], "status")
                except OSError:
                    result[item["server"]] = "starting (read failed)"
            return result

        self.wait(ready, lambda values: all("STATUS online" in reply for reply in values.values()))
        self.provenance(name, flags, restarted=True)
        for fixture in self.top.fixtures:
            self.wait(lambda: [self.top.inspect(e) for e in fixture.endpoints],
                lambda values: all(v["registered"] and not v["pause"] and v["channel"] == fixture.channel for v in values))
            for endpoint in fixture.endpoints:
                expected = "SEND" if endpoint in fixture.sources else ("OFF" if name == "legacy" else "RECEIVE")
                if self.read_mode(endpoint) != expected:
                    raise AssertionError("Persisted native mode changed across the same-world restart")

    def empty_all(self, values):
        for fixture in self.top.fixtures:
            point = values[fixture.channel]
            if not self.credit_state(fixture, point, 189, 189, 0, 0, 2):
                return False
            transfers = point["assets"]["transfers"]
            saved = self.held[fixture.channel]
            deposits = [t for t in transfers if t["kind"] == "DEPOSIT"]
            allocations = [t for t in transfers if t["kind"] == "ALLOCATE"]
            if deposits != saved["deposits"] or sorted(t["amount"] for t in allocations) != [61, 128]:
                raise AssertionError("Original deposits were replayed or allocation amounts changed")
            original = [t for t in allocations if t["id"] == saved["original_allocation_id"]]
            if len(original) != 1 or original[0]["state"] != "CONSUMED" or original[0]["remaining"] != 0:
                raise AssertionError("Original allocation did not remain uniquely consumed")
            if {t["id"] for t in allocations} != {saved["original_allocation_id"], saved["legacy61_allocation_id"]}:
                raise AssertionError("The independently allocated61FE business ID changed")
        return True

    def execute(self):
        self.environment_gate()
        self.phase = "initial_fast_preflight"
        self.report["execution_status"] = "RUNNING"
        self.save()
        top_module = module("ct_restart_topology_helpers", "optimization-topology-test.py")
        self.bench = top_module.BENCH
        self.container = module("ct_restart_container_metadata_helpers", "optimization-container-benchmark.py")
        namespace = argparse.Namespace(label="restart-fallback", cases=[], timeout=self.args.timeout, quiet=self.args.quiet)
        self.top = top_module.Topology(namespace)
        self.top.started = self.started
        self.top.report = self.report
        self.top.issue, self.top.sql, self.top.wait, self.top.save, self.top.record = self.issue, self.sql, self.wait, self.save, self.record
        self.initial_files = self.files_gate(("true", "true"))
        self.provenance("initial_fast", ("true", "true"))
        self.phase = "fast_prepare_positive_assets"
        self.prepare()
        self.report["initial_fast_end_counters"] = self.top.counters()
        self.phase = "clean_stop_and_switch_to_legacy"
        self.stop_clean("fast_to_legacy", ("true", "true"))
        self.switch_flags("fast_to_legacy", ("true", "true"), ("false", "false"))
        self.restart("legacy", ("false", "false"))
        self.phase = "legacy_restored_positive_assets"
        self.quiet("legacy_same_original_RX75_pool61", self.all_frames, self.pending_all)
        for fixture in self.top.fixtures:
            sink = fixture.sinks[0]
            self.fe(fixture, sink, "output", 2_147_483_647, 0, "restored OFF capability cannot expose its75FE")
            self.top.mode(sink, "RECEIVE")
            point = self.wait(lambda: self.frame(fixture), lambda value: self.credit_state(fixture, value, 189, 53, 0, 136, 2))
            allocations = [t for t in point["assets"]["transfers"] if t["kind"] == "ALLOCATE"]
            new = [t for t in allocations if t["id"] != self.held[fixture.channel]["original_allocation_id"]]
            if len(new) != 1 or new[0]["amount"] != 61:
                raise AssertionError("New shared61FE did not get one distinct allocation")
            self.held[fixture.channel]["legacy61_allocation_id"] = new[0]["id"]
            self.held[fixture.channel]["legacy61_allocation_at_receive"] = new[0]
            self.report["states"][fixture.name + "_legacy_RX136"] = point
            self.fe(fixture, sink, "output", 136, 136, "actual extraction of restored75 plus independently allocated61")
            self.fe(fixture, sink, "output", 2_147_483_647, 0, "immediate duplicate pull")
        self.quiet("legacy_all_assets_empty", self.all_frames, self.empty_all)
        for fixture in self.top.fixtures:
            self.fe(fixture, fixture.sinks[0], "output", 2_147_483_647, 0, "duplicate pull after SQL/WAL quiet checkpoint")
        self.report["legacy_end_counters"] = self.top.counters()
        self.phase = "clean_stop_and_restore_fast_flags"
        self.stop_clean("legacy_to_fast", ("false", "false"))
        self.switch_flags("legacy_to_fast", ("false", "false"), ("true", "true"))
        if any(sha(self.current_config[server]) != self.initial_files[server]["config_sha256"] for server in PORTS):
            raise AssertionError("Restored fast configuration does not match exact original bytes")
        self.restart("fast_again", ("true", "true"))
        self.phase = "fast_again_same_IDs_empty"
        self.quiet("fast_again_all_assets_still_empty", self.all_frames, self.empty_all)
        for fixture in self.top.fixtures:
            self.fe(fixture, fixture.sinks[0], "output", 2_147_483_647, 0, "duplicate pull after restored fast restart")
        final = self.all_frames()
        if not self.empty_all(final):
            raise AssertionError("Final original IDs/assets no longer empty")
        self.report["states"]["final_same_world_empty"] = final
        self.report["final_counters"] = self.top.counters()
        self.report["final_ledgers"] = {f.channel: asset_ledger(f.accepted, f.extracted, 0, 0) for f in self.top.fixtures}
        self.files_gate(("true", "true"))
        self.report.update(passed=True, execution_status="COMPLETE_FUNCTIONAL_PASS", utc_end=utc(),
            final_process_policy="Original worlds running with restored true,true flags; parent performs its normal stop.")
        self.phase = "COMPLETE"
        self.save()

    def fail(self, error):
        self.report["failures"].append({"phase": self.phase, "error": type(error).__name__ + ": " + str(error)})
        self.report.update(passed=False, execution_status="FAILED_ASSETS_CONFIG_PROCESSES_RETAINED", utc_end=utc())
        diagnostic = {}
        for server in PORTS:
            try:
                path = ROOT / ("run-" + server) / "cross-tesseract.properties"
                raw = bounded_file(path)
                selected = properties(raw)
                diagnostic[server] = {"config_sha256": sha(raw), "flags": {key: selected.get(key) for key in FLAGS}}
            except Exception as detail:
                diagnostic[server] = {"file_read_failure": type(detail).__name__ + ": " + str(detail)}
        self.report["failure_configuration_file_observations"] = diagnostic
        self.report["failure_policy_applied"] = "No cleanup, input/pull replay, configuration restore, force kill or automatic server stop. Last raw asset/WAL/SQL states retained."
        self.save()

    def release_locks(self):
        for handle in self.locks.values():
            handle.close()
        self.locks = {}


def self_test():
    # No files/config/processes/backends except Python helper/source loading.
    helper = module("ct_restart_offline_helper_check", "optimization-topology-test.py")
    raw = b"# fixture\r\nmysql.password=not-logged\r\n transfer.channelBatches = true \r\ntransfer.localFastPath=true\r\nserver.id=opt-fixture-A\r\n"
    legacy = flag_rewrite(raw, ("true", "true"), ("false", "false"))
    assert flag_rewrite(legacy, ("false", "false"), ("true", "true")) == raw
    for invalid in (raw + b"transfer.localFastPath=true\r\n", raw.replace(b"true", b"TRUE", 1), raw.replace(b"server.id=", b"server.id:")):
        try:
            flag_rewrite(invalid, ("true", "true"), ("false", "false"))
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid property fixture accepted")
    before_properties = b"#Minecraft server properties\n#Tue Oct 06 19:24:21 UTC 2026\nlevel-name=world-owned\nrcon.password=not-logged\nserver-ip=127.0.0.1\n"
    after_properties = before_properties.replace(b"19:24:21", b"20:24:21")
    identity = {key: "fixed" for key in ("server_id", "world_id", "level_name", "eula_sha256", "world_id_file_sha256")}
    original = dict(identity, server_properties_sha256=sha(before_properties),
        server_properties_semantic_sha256=properties_semantic_sha(before_properties))
    changed = dict(identity, server_properties_sha256=sha(after_properties),
        server_properties_semantic_sha256=properties_semantic_sha(after_properties))
    assert original["server_properties_sha256"] != changed["server_properties_sha256"]
    require_same_fixture_files(changed, original)
    for edit in (after_properties.replace(b"world-owned", b"world-other"),
            after_properties.replace(b"not-logged", b"changed-not-logged"),
            after_properties.replace(b"not-logged", b"not-logged "), after_properties + b"new-key=value\n"):
        try:
            require_same_fixture_files(dict(changed,
                server_properties_semantic_sha256=properties_semantic_sha(edit)), original)
        except AssertionError:
            pass
        else:
            raise AssertionError("Real server.properties key/value change accepted")
    assert asset_ledger(189, 53, 61, 75)["conserved"]
    try:
        asset_ledger(189, 53, 61, 150)
    except AssertionError:
        pass
    else:
        raise AssertionError("WAL/SQL mirror was double-counted")
    endpoint, world, transaction, channel = [uuid.uuid4() for _ in range(4)]
    kind = FE.encode()
    body = struct.pack(">ii", 0x43545431, 2) + endpoint.bytes + world.bytes + struct.pack(">qqi", 0, 7, 0)
    body += struct.pack(">i", 1) + transaction.bytes + channel.bytes + struct.pack(">H", len(kind)) + kind + struct.pack(">iqq", 0, 128, 75)
    body += struct.pack(">qdB", 0, 0.0, 0)
    encoded = body + hashlib.sha256(body).digest()
    decoded = decode_fe_wal(encoded)
    assert decoded["credits"][0]["remaining"] == 75 and decoded["credits"][0]["transaction"] == str(transaction)
    for invalid in (encoded[:-1], bytes([encoded[0] ^ 1]) + encoded[1:], encoded + b"x"):
        try:
            decode_fe_wal(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Corrupt WAL accepted")
    point = argparse.Namespace(x=1000004, z=768)
    assert mode_reply('1000004, 64, 768 has the following block data: "OFF"', point) == "OFF"
    try:
        mode_reply('1000005, 64, 768 has the following block data: "OFF"', point)
    except ValueError:
        pass
    else:
        raise AssertionError("Foreign block mode accepted")
    rows = [["transfer", str(uuid.uuid4()), "source", "r", "DEPOSIT", "COMMITTED", "128", "0", "1"],
        ["transfer", str(uuid.uuid4()), "source", "r", "DEPOSIT", "COMMITTED", "61", "0", "1"],
        ["transfer", str(transaction), "sink", "r", "ALLOCATE", "LOCAL", "128", "75", "1"],
        ["balance", "r", "", "r", "", "", "61", "0", "0"]]
    totals = helper.asset_totals(rows)
    assert totals["pool"] == 61 and totals["owned"] == 75 and totals["deposited"] == 189
    # Reproduce the frozen helper's response.strip()/line.split('\t') behavior.
    plain = "resource\t" + FE + "\t1\t\n"
    assert len(plain.strip().splitlines()[0].split("\t")) == 3
    prefixed = "resource\t" + FE + "\t1\thex:\n"
    parsed = [line.split("\t") for line in prefixed.strip().splitlines()]
    assert len(parsed[0]) == 4
    require_fe_resource_rows(parsed)
    require_fe_resource_rows([])
    for bad in ([["resource", FE, "1"]], [["resource", FE, "1", "hex:00"]],
            [["resource", FE, "2", "hex:"]], [["resource", "cross_tesseract:fluid", "1", "hex:"]]):
        try:
            require_fe_resource_rows(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError("Unknown/corrupt FE resource or stripped payload column accepted")
    # Exercise the real complete predicate and quiet loop using memory-only
    # snapshots/a deterministic clock. No constructor, files or live readers.
    source, sink = argparse.Namespace(id="offline-source"), argparse.Namespace(id="offline-sink")
    fixture = argparse.Namespace(channel="offline-channel", accepted=189, extracted=189,
        sources=[source], sinks=[sink], endpoints=[source, sink])
    deposits = [{"id": "deposit128", "kind": "DEPOSIT", "amount": 128},
        {"id": "deposit61", "kind": "DEPOSIT", "amount": 61}]
    allocations = [{"id": "allocate128", "kind": "ALLOCATE", "endpoint_id": sink.id,
        "amount": 128, "remaining": 0, "state": "CONSUMED"},
        {"id": "allocate61", "kind": "ALLOCATE", "endpoint_id": sink.id,
        "amount": 61, "remaining": 0, "state": "CONSUMED"}]
    empty_buffer = dict(registered=True, pause="", txFE=0, rxFE=0,
        txItem=0, rxItem=0, txFluid=0, rxFluid=0)
    point = {"assets": dict(deposited=189, pool=0, owned=0, allocation_count=2, quarantined=0,
            transfers=deposits + allocations),
        "buffers": {source.id: dict(empty_buffer), sink.id: dict(empty_buffer)},
        "endpoint_rows": {source.id: {"checkpoint": "9"}, sink.id: {"checkpoint": "8"}},
        "WAL": {source.id: dict(revision=9, deposits=[], credits=[]),
            sink.id: dict(revision=10, deposits=[], credits=[])}}
    values = {fixture.channel: point}
    check = object.__new__(RestartFallback)
    check.top = argparse.Namespace(fixtures=[fixture], quiet=2.2)
    check.held = {fixture.channel: dict(deposits=deposits,
        original_allocation_id="allocate128", legacy61_allocation_id="allocate61")}
    untouched = json.dumps(values, sort_keys=True)
    assert not check.empty_all(values)
    assert sole_checkpoint_progress(values, check.empty_all) == [{"channel": fixture.channel,
        "endpoint": sink.id, "observed_SQL_checkpoint": 8, "observed_WAL_revision": 10}]
    assert json.dumps(values, sort_keys=True) == untouched
    complete = copy.deepcopy(values)
    complete[fixture.channel]["endpoint_rows"][sink.id]["checkpoint"] = "10"
    assert check.empty_all(complete) and not sole_checkpoint_progress(complete, check.empty_all)
    for target, key, value in (("assets", "pool", 1), ("buffers", sink.id, dict(empty_buffer, rxFE=1)),
            ("WAL", sink.id, dict(revision=10, deposits=[], credits=[dict(transaction="allocate128",
                channel=fixture.channel, original=128, remaining=1)]))):
        bad = copy.deepcopy(values)
        bad[fixture.channel][target][key] = value
        assert not sole_checkpoint_progress(bad, check.empty_all)
    bad_ids = copy.deepcopy(values)
    bad_ids[fixture.channel]["assets"]["transfers"][-1]["id"] = "replayed-allocation"
    try:
        sole_checkpoint_progress(bad_ids, check.empty_all)
    except AssertionError:
        pass
    else:
        raise AssertionError("Checkpoint skew hid changed business allocation IDs")
    from unittest.mock import patch
    clock = [0.0]
    def offline_sleep(seconds):
        clock[0] += seconds
    check.args = argparse.Namespace(timeout=6, poll=1)
    check.started, check.phase, check.read_deadline = 0.0, "offline_selftest", None
    check.report = {"states": {}, "raw_events": []}
    check.save = lambda: None
    sequence = iter([complete, values, complete, complete, complete, complete])
    with patch.object(time, "monotonic", lambda: clock[0]), patch.object(time, "sleep", offline_sleep):
        result = check.quiet("offline_reset", lambda: next(sequence), check.empty_all)
    assert result["passed"] and result["continuous_snapshot_start_index"] == 2 and result["quiet_seconds"] == 3
    assert len(result["checkpoint_in_progress_raw_indexes"]) == 1 and len(result["snapshots"]) == 6
    assert json.dumps(values, sort_keys=True) == untouched
    clock[0] = 0.0
    check.report = {"states": {}, "raw_events": []}
    check.args.timeout = 5
    initial = [complete]
    with patch.object(time, "monotonic", lambda: clock[0]), patch.object(time, "sleep", offline_sleep):
        try:
            check.quiet("offline_fixed_deadline", lambda: initial.pop() if initial else values, check.empty_all)
        except AssertionError as error:
            assert "fixed deadline" in str(error)
        else:
            raise AssertionError("Endless checkpoint skew extended quiet deadline")
    assert clock[0] == 5 and check.read_deadline is None
    clock[0] = 0.0
    initial = [complete]
    with patch.object(time, "monotonic", lambda: clock[0]), patch.object(time, "sleep", offline_sleep):
        try:
            check.quiet("offline_real_mismatch", lambda: initial.pop() if initial else bad, check.empty_all)
        except AssertionError as error:
            assert "Assets changed" in str(error)
        else:
            raise AssertionError("Real credit mismatch was tolerated during quiet")
    assert clock[0] == 1
    # Before strict quiet starts, unsettled SQL/assets must be allowed to
    # converge. They cannot extend the total deadline or count as quiet samples.
    unsettled = copy.deepcopy(complete)
    unsettled[fixture.channel]["assets"]["pool"] = 136
    clock[0] = 0.0
    initial = [unsettled, complete]
    with patch.object(time, "monotonic", lambda: clock[0]), patch.object(time, "sleep", offline_sleep):
        result = check.quiet("offline_initial_convergence", lambda: initial.pop(0) if initial else complete, check.empty_all)
    assert result["passed"] and result["snapshots"][0] == complete and result["continuous_snapshot_start_index"] == 0
    assert clock[0] == 4 and result["quiet_seconds"] == 3
    clock[0] = 0.0
    with patch.object(time, "monotonic", lambda: clock[0]), patch.object(time, "sleep", offline_sleep):
        try:
            check.quiet("offline_initial_never_stable", lambda: unsettled, check.empty_all)
        except AssertionError as error:
            assert "State timeout" in str(error)
        else:
            raise AssertionError("Unsettled initial state was accepted or extended deadline")
    assert clock[0] == 5 and check.read_deadline is None
    print(json.dumps({"offline_checks_passed": True, "native_execution": "NOT_RUN", "passed_live_test": False,
        "checks": ["Read-only helper loading", "Only two flag bytes changed and exact restoration", "Invalid properties rejected",
            "Minecraft date comments allowed with raw SHA retained; any key/value change rejected without logging values",
            "Independent189=53+61+75 ledger", "CTT1 v2 FE WAL checksum/identity/remaining decode", "Corrupt WAL rejected", "Owned mode coordinates", "Exact SQL transfer totals", "Frozen TSV strip preserves prefixed empty FE payload",
            "Checkpoint-only read skew classified using a copy; real snapshots unchanged",
            "Amount/positive credit/business ID mismatches reject immediately",
            "Strict quiet timer resets; continuous guard required; fixed deadline never extended",
            "Initial unsettled assets converge before quiet; never-stable initial state times out in same budget"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run the controlled same-world restart test on existing fast regression ABC fixtures only")
    parser.add_argument("--self-test", action="store_true", help="Offline helper/ledger/config/WAL/metadata checks; no JVM or backend")
    parser.add_argument("--timeout", type=float, default=120, help="Per read-only state wait, at most120 seconds")
    parser.add_argument("--quiet", type=float, default=2.2, help="Minimum quiet guard; enlarged to configured idle poll +0.5s")
    parser.add_argument("--poll", type=float, default=0.2, help="Read-only state polling interval")
    args = parser.parse_args()
    if not 30 <= args.timeout <= 120 or not 2.2 <= args.quiet <= 10 or not 0.1 <= args.poll <= 1:
        parser.error("Require30<=timeout<=120,2.2<=quiet<=10,0.1<=poll<=1; SELECT observer reserves20s")
    if args.execute and args.self_test:
        parser.error("--self-test cannot accompany --execute")
    if args.self_test:
        self_test()
        return 0
    if not args.execute:
        print(json.dumps({"execution_status": "NOT_RUN", "passed": False, "fixture": FIXTURE,
            "revision": CORE, "scope": "Two native FE channels, same-world fast->legacy->fast clean restarts",
            "requires": "--execute only after other fast regression cases; one observer, exact frozen68 source/JAR, accepted EULA and loopback ABC fixtures",
            "input_per_channel_FE": 189, "partial_output_FE": 53, "held_RX_FE": 75, "pool_FE": 61,
            "failure_policy": "Retain actual assets/config/processes, no replay/automatic cleanup/force kill"}, indent=2))
        return 0
    test = RestartFallback(args)
    try:
        test.execute()
    except BaseException as error:
        test.fail(error)
        print(str(error), file=sys.stderr)
        print("FAILED; preserved", test.target, file=sys.stderr)
        return 1
    finally:
        test.release_locks()
    print("PASS; parent normal stop remains required; report", test.target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
