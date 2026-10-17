#!/usr/bin/env python3
"""Same final artifact/worlds/endpoint IDs across normally stopped fast/legacy/fast boots.

Default and --self-test are offline. --execute is for AFTER a completed, normally
stopped full RC soak, with its controller completion and exact frozen manifest.
No build, backend lifecycle, new endpoint/channel, historical fixture, asset
replay/refund, SQL mutation, force kill or automatic configuration restoration.
Only the two explicit flags in this round's snapshotted A/B/C properties change.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid
import zipfile
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "build.gradle").is_file() and (p / "src/main/java").is_dir())
REVIEWED_ARTIFACTS = {
    "3647dede64cfc23e054dfa962fd127787cae14ec": {
        'main_sha256': "998b3fc31ae9fd813f5f916a345240451d476283a9b05672b1bcc6c80cf89504",
        'jar_sha256': "1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f"},
    "0113ef30f2269f9ea51e7c15e585792828fd2a51": {
        'main_sha256': "99837a57935c9f35543024d05e28b192d3d93b721e41cd5463d3df6ad6917434",
        'jar_sha256': "70a02e49900dee34fc996bfcf95360689ea9e42c35996c581c52df2ee6fdb07c"},
}
PORTS = {"A": 25575, "B": 25576, "C": 25577}
FE, FLAGS = "cross_tesseract:fe", ("transfer.channelBatches", "transfer.localFastPath")
MAX_FILE, MAX_REPORT, MAX_EVENTS = 8_388_608, 67_108_864, 10_000
MAX_LOG = 8_388_608
PROBE_SOURCES = {
    'scripts/rcprobe/ProbeAgent.java': '81cc57f8c4c8ef0f86d880d99991037995d96781241ae308bf6540f6ec1a4eb8',
    'scripts/rcprobe/WindowStats.java': 'c5997f82d92399b378e275c96485ca8ee4fa9763d2ed9fa45c8f6225051908f0'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def path(value, limit=MAX_FILE, directory=False):
    selected = Path(value)
    if ".." in selected.parts:
        raise ValueError("Parent traversal rejected")
    selected = selected if selected.is_absolute() else ROOT / selected
    if not selected.is_relative_to(ROOT):
        raise ValueError("Only repository-owned paths allowed")
    for parent in (selected, *selected.parents):
        if parent.is_symlink():
            raise ValueError("Symlink path rejected")
        if parent == ROOT:
            break
    if directory:
        if not selected.is_dir():
            raise ValueError("Existing owned directory required")
    elif not selected.is_file() or selected.stat().st_size > limit:
        raise ValueError("Bounded regular file required: " + str(selected))
    return selected


def metadata(selected):
    return {"path": str(selected.relative_to(ROOT)), "sha256": sha(selected.read_bytes())}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def document(selected, limit=MAX_REPORT):
    return json.loads(path(selected, limit).read_text(), object_pairs_hook=unique)


def referenced(point, limit=MAX_REPORT):
    selected = path(point["path"], limit)
    if not re.fullmatch("[0-9a-f]{64}", point["sha256"]) or sha(selected.read_bytes()) != point["sha256"]:
        raise ValueError("Referenced input digest mismatch")
    return selected


def load(name, filename):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def completed_controller(controller):
    if not (controller.get("passed") is True and controller.get("functional_passed") is True
            and controller.get("qualified_passed") is True and controller.get("sixty_minute_gate") is True
            and controller.get("kind") == "full" and controller.get("requested_observation_seconds") == 3600
            and controller.get("workload_exit") == 0 and controller.get("utc_end")
            and controller.get("state") == "COMPLETE" and not controller.get("failures")
            and controller.get("all_own_launchers_exited_and_locks_free") is True
            and all(controller.get(key, {}).get("matches_expected") is True
                    for key in ("source_before", "source_after_workload", "source_after_stop"))):
        raise ValueError("Completed, qualified, normally stopped full soak required")
    exits = controller.get("own_launcher_exits", {})
    if set(exits) != set(PORTS) or any(row.get("exit_code") != 0 for row in exits.values()):
        raise ValueError("Actual original A/B/C launcher exit0 evidence required")
    return exits


def verify_initial_config(raw, identity):
    expected = identity.get('config_file_start_sha256')
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected) or sha(raw) != expected:
        raise ValueError('Initial configuration bytes differ from the completed soak start SHA')
    # The custom soak did not record an end SHA. Do not synthesize or require it.


def reviewed_artifact(revision, jar_sha256):
    selected = REVIEWED_ARTIFACTS.get(revision)
    if selected is None or selected['jar_sha256'] != jar_sha256:
        raise ValueError('Exact reviewed full source revision and matching mod JAR SHA required')
    return dict(selected, source_revision=revision)


def boot_boundary(identities):
    return {server: {key: row[key] for key in ('pid', 'session_id', 'fencing_epoch')}
            for server, row in identities.items()}


def closed_entrypoint(original, failed, closure, audit, expected_devices, owner, artifact):
    """Only the evidenced single zero-input failed boot may advance the initial boot."""
    if (failed.get('passed') is not False or failed.get('state') != 'FAILED_RETAINED'
            or failed.get('stages') != [] or failed.get('config_switches') != [] or failed.get('positive_handoffs', []) != []
            or failed.get('failure_own_launcher_exits') != {s: 0 for s in PORTS}
            or len(failed.get('boots', [])) != 1
            or failed.get('source_revision') != artifact['source_revision']
            or failed.get('source_main_sha256') != artifact['main_sha256']
            or failed.get('mod_JAR_sha256') != artifact['jar_sha256']):
        raise ValueError('Entrypoint requires this exact artifact, one closed failed boot and no asset stage/config switch')
    captures = failed.get('failure_bounded_logs', {})
    if set(captures) != set(PORTS) or any(not v.get('capture_complete') or v.get('capture_failure') or v.get('dropped_bytes') for v in captures.values()):
        raise ValueError('Failed-entrypoint actual owned logs/exit evidence is incomplete')
    if (closure.get('actual_CLI_exit_code') != 1 or closure.get('actual_original_Popen_launcher_exits') != {s: 0 for s in PORTS}
            or closure.get('all_four_launch_and_own_observer_locks_free') is not True
            or closure.get('remaining_native') != [] or closure.get('remaining_observers') != []
            or closure.get('remaining_java_javac_jstat') != [] or closure.get('new_native_input') != 0
            or closure.get('stages') != [] or closure.get('config_switches') != []
            or closure.get('actual_log_capture') != captures):
        raise ValueError('Entrypoint closure must prove actual exits/empty stages and retain original log capture')
    if (audit.get('mysql_exit') != 0 or audit.get('passed_poststop_audit') is not True
            or audit.get('new_input') != 0 or audit.get('config_switches') != 0
            or audit.get('SQL_mutations') is not False or audit.get('WAL_read_write') is not False):
        raise ValueError('Entrypoint needs the scoped read-only zero-asset post-stop SQL audit')
    data = audit['SQL']; rows = {v['server']: v for v in data['servers']}
    scope = audit['SQL_scope']
    if (scope['cluster'] != 'dev_three_v1' or set(scope['endpoint_IDs']) != {v['id'] for v in expected_devices}
            or set(scope['channel_IDs']) != {v['expected_channel'] for v in expected_devices}
            or set(scope['server_IDs']) != {v['server_id'] for v in original.values()}
            or json.loads(audit['raw_stdout']) != data):
        raise ValueError('Entrypoint SQL scope/raw response differs from the exact original cohort')
    boot = failed['boots'][0]; actual_boot = {v['server']: v for v in boot['SQL']['servers']}
    if len(rows) != 3 or set(rows) != {v['server_id'] for v in original.values()} or set(actual_boot) != set(rows):
        raise ValueError('Entrypoint server set differs from the original full cohort')
    expected = {v['id']: v for v in expected_devices}; actual = {v['id']: v for v in data['endpoints']}
    if len(actual) != len(data['endpoints']) or set(actual) != set(expected):
        raise ValueError('Entrypoint endpoint set differs from the original full cohort')
    for eid, ep in expected.items():
        row = actual[eid]; identity = original[ep['server']]
        if [row[k] for k in ('channel', 'server', 'world', 'owner', 'state', 'x', 'y', 'z', 'dimension')] != [ep['expected_channel'], identity['server_id'], identity['world_id'], owner, 'ACTIVE', ep['x'], 64, ep['z'], 'minecraft:overworld']:
            raise ValueError('Entrypoint stable endpoint/owner/binding/location mismatch')
    if any(v['amount'] != 0 for v in data['pool_rows']) or any(v['remaining'] != 0 for v in data['allocation_summary']):
        raise ValueError('Entrypoint prior cohort has positive SQL assets; no replay/adoption allowed')
    adopted = {}
    for server, identity in original.items():
        if failed['initial_config_snapshots'][server]['config_sha256'] != identity['config_file_start_sha256']:
            raise ValueError('Entrypoint configuration differs from original full start bytes')
        row = rows[identity['server_id']]; recorded = actual_boot[identity['server_id']]
        if (row['world'] != identity['world_id'] or row['status'] != 'STOPPED' or row['clean_stop'] != 1 or row['lease_live']
                or row['epoch'] != identity['fencing_epoch'] + 1 or row['session'] == identity['session_id']
                or (row['world'], row['session'], row['epoch']) != (recorded['world'], recorded['session'], recorded['epoch'])):
            raise ValueError('Entrypoint is not the single evidenced fresh clean-stopped boot')
        adopted[server] = {'pid': boot['identity'][server]['pid'], 'session_id': row['session'], 'fencing_epoch': row['epoch']}
    return adopted


def positive_state(frame, accepted, extracted, pool, owned, allocation_count, channel):
    """Exact new business ledger plus SQL/WAL mirrors; old zero tombstones may remain."""
    if (accepted != extracted + pool + owned or frame['pool'] != pool or frame['owned'] != owned
            or frame['quarantined'] or frame['stopped'] not in (True, False)):
        return False
    transfers = frame['new_transfers']; ids = [v['id'] for v in transfers]
    deposits = [v for v in transfers if v['kind'] == 'DEPOSIT']; allocations = [v for v in transfers if v['kind'] == 'ALLOCATE']
    if (len(ids) != len(set(ids)) or len(deposits) + len(allocations) != len(transfers)
            or any(v['endpoint'] not in frame['WAL'] for v in transfers)
            or any(v['endpoint'] != frame.get('source_endpoint', v['endpoint']) for v in deposits)
            or sorted(v['amount'] for v in deposits) != ([128] if accepted == 128 else [61, 128])
            or any(v['state'] != 'COMMITTED' or v['remaining'] != 0 for v in deposits)
            or len(allocations) != allocation_count or sum(v['remaining'] for v in allocations) != owned
            or any(v['state'] != ('LOCAL' if v['remaining'] else 'CONSUMED') for v in allocations)):
        return False
    for eid, wal in frame['WAL'].items():
        if wal['deposits'] or wal['revision'] > next(v['checkpoint'] for v in frame['endpoints'] if v['id'] == eid):
            return False
        rows = {v['id']: v for v in allocations if v['endpoint'] == eid}
        positive = {v['transaction']: (v['channel'], v['original'], v['remaining']) for v in wal['credits'] if v['remaining'] > 0}
        wanted = {key: (channel, v['amount'], v['remaining']) for key, v in rows.items() if v['remaining'] > 0}
        if positive != wanted:
            return False
        for credit in wal['credits']:
            if credit['transaction'] in rows:
                row = rows[credit['transaction']]
                if (credit['channel'], credit['original'], credit['remaining']) != (channel, row['amount'], row['remaining']):return False
        if not frame['stopped']:
            value = frame['local'][eid]
            if (not value['registered'] or value['pause'] or value['txFE'] != 0
                    or value['rxFE'] != sum(v['remaining'] for v in rows.values())
                    or any(value[k] for k in ('txItem', 'rxItem', 'txFluid', 'rxFluid'))):return False
    return True


def processes():
    native, observers = [], []
    names = re.compile(r"(?:optimization-(?:benchmark|container-benchmark|resource-mix|monitor|topology-test|final-sequence)|rc-(?:soak|probe-benchmark|probe-mix|native-matrix|normal-fallback)|run-rc-v2-(?:stage|soak))\.py$")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            raw = (proc / "cmdline").read_bytes()
            argv = [part.decode() for part in raw.split(b"\0") if part]
            if not argv:
                continue
            if Path(argv[0]).name == "java":
                text = " ".join(argv)
                if re.search(r"(?:server[ABC]|serverPerf|gameTestServer)RunVmArgs\.txt|net\.minecraft\.server\.Main|forgeserverdev", text):
                    native.append({"pid": int(proc.name), "argv_sha256": sha(raw), "cwd": str((proc / "cwd").resolve())})
                elif "GradleDaemon" in text or "GradleWrapperMain" in text:
                    observers.append({"pid": int(proc.name), "kind": "build JVM"})
            elif any(names.search(Path(value).name) for value in argv[1:] if not value.startswith("-")):
                observers.append({"pid": int(proc.name), "kind": "other workload/controller/observer"})
        except (FileNotFoundError, ProcessLookupError):
            continue
    return native, observers


def process_snapshot(pid):
    """Read one bounded /proc identity; argv stays private to ownership checks."""
    proc = Path('/proc') / str(pid)
    try:
        raw = (proc / 'cmdline').read_bytes()
        status = (proc / 'stat').read_text()
        if len(raw) > 65536 or len(status) > 4096:
            raise ValueError('Process identity exceeds bounds')
        fields = status[status.rfind(')') + 2:].split()
        return {'pid': int(pid), 'ppid': int(fields[1]), 'start_ticks': int(fields[19]),
                'state': fields[0], 'argv': [v.decode() for v in raw.split(b'\0') if v],
                'argv_sha256': sha(raw), 'cwd': str((proc / 'cwd').resolve(strict=True)),
                'exe': str((proc / 'exe').resolve(strict=True))}
    except (FileNotFoundError, ProcessLookupError):
        return None


def owned_native_proof(candidate, anchor, expected, reader=None):
    """Exact frozen command AND this Popen's birth/ancestor chain, never argv alone."""
    if (candidate is None or candidate['state'] == 'Z'
            or candidate['argv'] != expected['argv'] or candidate['cwd'] != expected['cwd']
            or candidate['exe'] != expected['exe']):
        return None
    reader = reader or process_snapshot
    chain, seen, link = [], set(), candidate
    while link is not None and len(chain) < 32 and link['pid'] not in seen:
        seen.add(link['pid'])
        chain.append({k: link[k] for k in ('pid', 'ppid', 'start_ticks')})
        if link['pid'] == anchor['pid']:
            if link['start_ticks'] != anchor['start_ticks']:
                return None
            return {'pid': candidate['pid'], 'argv_sha256': candidate['argv_sha256'],
                    'cwd': candidate['cwd'], 'exe': candidate['exe'], 'ancestor_chain': chain,
                    'launcher': expected['launcher'], 'launcher_sha256': expected['launcher_sha256'],
                    'vm_args': expected['vm_args'], 'vm_args_sha256': expected['vm_args_sha256']}
        if link['ppid'] <= 1:
            break
        link = reader(link['ppid'])
    return None


def proc_parent_index(proc_root):
    """Bounded PPID metadata fallback for kernels without task/children support."""
    result, seen = {}, 0
    for proc in proc_root.iterdir():
        if not proc.name.isdigit():
            continue
        seen += 1
        if seen > 16384:
            raise ValueError('PPID fallback scan exceeds process bound')
        try:
            raw = (proc / 'stat').read_text()
            if len(raw) > 4096:
                raise ValueError('PPID fallback stat exceeds bound')
            fields = raw[raw.rfind(')') + 2:].split()
            result.setdefault(int(fields[1]), []).append(int(proc.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return result


def owned_tree(anchor, proc_root=Path('/proc')):
    """Inspect only this launcher's bounded descendant tree, independently of globals."""
    root = process_snapshot(anchor['pid'])
    if root is None or root['start_ticks'] != anchor['start_ticks']:
        return []
    queue, seen, result, parents = [root], set(), [], None
    while queue:
        candidate = queue.pop()
        if candidate['pid'] in seen:
            continue
        seen.add(candidate['pid'])
        if len(seen) > 64:
            raise ValueError('Owned process tree exceeds bounds')
        result.append(candidate)
        children = proc_root / str(candidate['pid']) / 'task' / str(candidate['pid']) / 'children'
        try:
            raw = children.read_text()
            if len(raw) > 4096 or len(raw.split()) > 64:
                raise ValueError('Owned process children exceed bounds')
            selected = [int(pid) for pid in raw.split()]
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            if parents is None:
                parents = proc_parent_index(proc_root)
            selected = parents.get(candidate['pid'], [])
        for pid in selected:
            child = process_snapshot(int(pid))
            if child is not None:
                queue.append(child)
    return result


class BoundedLog:
    """Drain owned stdout continuously; retain a bounded prefix, never block a JVM on a full log."""
    def __init__(self, stream, target):
        self.stream, self.target, self.seen, self.kept, self.failure = stream, target, 0, 0, None
        self.thread=threading.Thread(target=self.collect,daemon=False);self.thread.start()

    def collect(self):
        try:
            with self.target.open('xb') as output:
                while chunk:=self.stream.read1(32768):
                    self.seen+=len(chunk);part=chunk[:max(0,MAX_LOG-self.kept)];output.write(part);self.kept+=len(part)
        except BaseException as error:self.failure=type(error).__name__+': '+str(error)
        finally:self.stream.close()

    def finish(self):
        self.thread.join(timeout=5)
        return {'path':str(self.target.relative_to(ROOT)),'seen_bytes':self.seen,'retained_bytes':self.kept,
            'dropped_bytes':self.seen-self.kept,'capture_complete':not self.thread.is_alive(),
            'capture_failure':self.failure,'sha256':sha(self.target.read_bytes()) if self.target.is_file() else None}


class Fallback:
    def __init__(self, args):
        self.args, self.started, self.token = args, time.monotonic(), uuid.uuid4().hex
        # Import only offline definitions. Never construct/execute the historical
        # RestartFallback controller: its fixed worlds, inputs and reports differ.
        self.pure = load("rc_fallback_pure_protocol_helpers", "optimization-restart-fallback-test.py")
        self.base = load("rc_fallback_readonly_native_helpers", "optimization-benchmark.py")
        self.completion_path, self.manifest_path = path(args.completion), path(args.manifest)
        if any(not p.is_relative_to(ROOT / "reports/rc-20261017") for p in (self.completion_path, self.manifest_path)):
            raise ValueError("Only this RC report directory can identify the full-soak cohort")
        controller, self.seal = document(self.completion_path), document(self.manifest_path)
        exits = completed_controller(controller)
        self.artifact = reviewed_artifact(self.seal['source_revision'], self.seal['artifacts']['JAR']['sha256'])
        if referenced(controller["runtime_manifest"]) != self.manifest_path:
            raise ValueError("Soak controller and explicit final runtime manifest differ")
        self.soak_path = referenced(controller["raw_report"])
        self.soak = document(self.soak_path)
        if (self.soak.get("passed") is not True or self.soak.get("60min_gate") is not True
                or self.soak.get("smoke") is not False or not self.soak.get("utc_end")
                or self.soak.get("observation", {}).get("actual_observation_seconds", 0) < 3600
                or self.soak.get("conditions", {}).get("observation_seconds") != 3600
                or self.soak.get("final_drain", {}).get("passed") is not True):
            raise ValueError("The referenced real 3600-second soak is not a completed pass")
        self.prefix = "world-opt-" + controller["label"]
        if not re.fullmatch(r"world-opt-rc-soak-[a-z0-9-]{1,24}", self.prefix):
            raise ValueError("Only this round's strict RC soak worlds allowed")
        self.identities = self.soak["identity"]
        if set(self.identities) != set(PORTS):
            raise ValueError("Exactly three archived server identities required")
        for server, identity in self.identities.items():
            entry = self.seal["launches"][server]
            if (identity["level_name"] != self.prefix + "-" + server
                    or identity["server_id"] != "opt-" + controller["label"] + "-" + server
                    or exits[server]["launcher"] != entry["launcher"]
                    or exits[server]["launcher_sha256"] != entry["launcher_sha256"]):
                raise ValueError("Original world/server/launcher exit proof mismatch")
        lane = self.soak["fixtures"]["backpressure"]
        if len(lane) != 1 or len(lane[0]["sources"]) != 1 or [r["server"] for r in lane[0]["sources"]] != ["A"] or sorted(r["server"] for r in lane[0]["sinks"]) != ["A", "B"]:
            raise ValueError("One existing A source and A/B mixed receivers required")
        self.lane, self.channel, self.owner = lane[0], str(uuid.UUID(lane[0]["channel"])), str(uuid.UUID(self.soak["owner"]))
        self.devices = self.lane["sources"] + self.lane["sinks"]
        self.all_devices = [dict(e, expected_channel=case["channel"]) for group in self.soak["fixtures"].values() for case in group for e in case["sources"] + case["sinks"]]
        if len(self.all_devices) > 64 or len({e["id"] for e in self.all_devices}) != len(self.all_devices):
            raise ValueError("Bounded unique own-soak endpoint inventory required")
        for e in self.all_devices:
            uuid.UUID(e["id"])
            uuid.UUID(e['expected_channel'])
            if e["server"] not in PORTS or type(e["x"]) is not int or type(e["z"]) is not int or abs(e["x"]) > 29_000_000 or abs(e["z"]) > 29_000_000:
                raise ValueError("Invalid own endpoint coordinates/server")
        self.configs, self.files, self.locks, self.children, self.stop_requested, self.logs = {}, {}, {}, {}, set(), {}
        self.owners = {}
        self.probe_files, self.quota = None, None
        for server, identity in self.identities.items():
            frozen=Path(self.seal['launches'][server]['launcher']).parent
            wanted={str(frozen/('server'+server+suffix+'.txt')) for suffix in ('RunVmArgs','RunProgramArgs','RunClasspath')}
            recorded=identity.get('all_launch_argfiles',[])
            if len(recorded)!=3 or {r['path'] for r in recorded}!=wanted:
                raise ValueError('The completed soak must attest all three actual frozen argument files')
            for row in recorded:
                selected=referenced(row)
                self.files[str(selected)]={'path':str(selected.relative_to(ROOT)),'sha256':row['sha256']}
        self.inputs = {str(p): metadata(p) for p in (self.completion_path, self.manifest_path, self.soak_path, Path(__file__).resolve(), ROOT / "scripts/optimization-restart-fallback-test.py", ROOT / "scripts/optimization-benchmark.py", ROOT / "scripts/rcon.py", ROOT / "scripts/start-frozen-dev.sh", *(ROOT/p for p in PROBE_SOURCES))}
        self.round = ROOT / "scratch" / ("rc-normal-fallback-" + args.label + "-" + self.token[:12])
        self.target = ROOT / "reports/rc-20261017" / ("normal-fallback-" + args.label + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + self.token[:8] + ".json")
        self.report = {"report_kind": "RC_same_artifact_same_world_normal_configuration_fallback", "utc_start": utc(), "passed": False,
            "state": "PREPARED_NOT_RUN", "completion": metadata(self.completion_path), "runtime_manifest": metadata(self.manifest_path),
            "soak_raw": metadata(self.soak_path), "source_main_sha256": self.artifact['main_sha256'], "mod_JAR_sha256": self.artifact['jar_sha256'],
            "source_revision": self.artifact['source_revision'], "own_existing_lane": self.lane, "inputs": list(self.inputs.values()),
            "stages": [], "positive_handoffs": [], "boots": [], "normal_stops": [], "config_switches": [], "events": [], "failures": [],
            "all_soak_SQL_checks": [], "probe_file_checks": [],
            "scope": "Same completed-soak worlds and endpoint IDs: three189FE empty-to-empty stages plus two189FE positive handoffs (945 total). Each handoff actually extracts53, carries original LOCAL75 and pool61 across a normal config restart, verifies OFF extraction0 and exact original IDs, then drains136 through the A/B recipients. No asset crash, disk power loss or performance claim.",
            "accounting": "Native accepted/extracted plus SQL ownership; SQL/WAL/local are separate mirrors, never added. Phase database-clock watermark and exact new business IDs exclude prior soak transfers.",
            "failure_policy": "Retain all files/assets/current flags; do not replay an uncertain native command, refund, clean SQL, restore flags, force kill or restart a failed stage. A verified own JVM may receive one normal stop only.",
            "historical_fixtures_accessed": False, "SQL_mutations": False}
        if getattr(args, 'entrypoint_audit', None) is not None:
            self.adopt_entrypoint(args.entrypoint_audit)

    def adopt_entrypoint(self, supplied):
        selected = path(supplied)
        if not selected.is_relative_to(ROOT / 'reports/rc-20261017'):
            raise ValueError('Explicit entrypoint evidence must be a public RC report')
        chain = document(selected)
        if chain.get('kind') != 'explicit_closed_zero_input_failed_fallback_entrypoint':
            raise ValueError('Explicit closed-entrypoint chain required')
        points = {key: chain[key] for key in ('full_controller', 'runtime_manifest', 'soak_raw', 'failed_attempt', 'closure', 'poststop_SQL_audit')}
        for point in points.values():referenced(point)
        if (points['full_controller'] != metadata(self.completion_path)
                or points['runtime_manifest'] != metadata(self.manifest_path)
                or points['soak_raw']['sha256'] != metadata(self.soak_path)['sha256']):
            raise ValueError('Entrypoint chain belongs to a different full/runtime/raw')
        failed = document(referenced(points['failed_attempt']))
        closure = document(referenced(points['closure']))
        audit = document(referenced(points['poststop_SQL_audit']))
        if (failed['completion'] != points['full_controller'] or failed['runtime_manifest'] != points['runtime_manifest']
                or failed['soak_raw']['sha256'] != points['soak_raw']['sha256']
                or closure['failed_report'] != points['failed_attempt'] or audit['failed_report'] != points['failed_attempt']):
            raise ValueError('Entrypoint failed/closure/SQL references do not bind the same actual attempt')
        for server, identity in self.identities.items():
            if failed['initial_config_snapshots'][server]['config_sha256'] != identity['config_file_start_sha256']:
                raise ValueError('Entrypoint changed original full configuration bytes')
        original = boot_boundary(self.identities)
        adopted = closed_entrypoint(self.identities, failed, closure, audit, self.all_devices, self.owner, self.artifact)
        for server, row in adopted.items():self.identities[server].update(row)
        for point in [metadata(selected), *points.values()]:self.inputs[str(referenced(point))] = point
        self.report['inputs'] = list(self.inputs.values())
        self.report['explicit_initial_entrypoint'] = {'chain': metadata(selected), 'references': points,
            'original_full_boot': original, 'adopted_closed_boot': adopted,
            'scope': 'Only this single proven zero-input failed boot advances the initial expected identity. Original full/failed reports remain unchanged. Current SQL must still exactly match this adopted stopped boot before any launch.'}

    def save(self):
        raw = (json.dumps(self.report, indent=2, allow_nan=False) + "\n").encode()
        if len(raw) > MAX_REPORT:
            raise ValueError("Bounded evidence report exceeded; retain assets")
        pending = self.target.with_suffix(".pending.json")
        with pending.open("wb") as output:
            output.write(raw)
        pending.replace(self.target)

    def event(self, kind, **values):
        if len(self.report["events"]) >= MAX_EVENTS:
            raise ValueError("Bounded event count exceeded")
        row = {"index": len(self.report["events"]), "kind": kind, "utc": utc(), "start": time.monotonic()-self.started, **values}
        self.report["events"].append(row)
        return row

    def launcher_identity(self, server):
        entry = self.seal['launches'][server]
        launcher = referenced({'path': entry['launcher'], 'sha256': entry['launcher_sha256']})
        vm = referenced({'path': entry['vm_args'], 'sha256': entry['vm_args_sha256']})
        lex = shlex.shlex(launcher.read_text(), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ''
        tokens = list(lex)
        run = str(ROOT / ('run-' + server))
        folder = launcher.parent
        wanted = ['@' + str(folder / ('server' + server + 'RunClasspath.txt')),
                  '@' + str(vm), '-Dfml.modFolders=cross_tesseract%%' + str(folder / 'classes')
                  + ':cross_tesseract%%' + str(folder / 'resources'), 'net.neoforged.devlaunch.Main',
                  '@' + str(folder / ('server' + server + 'RunProgramArgs.txt'))]
        if (len(tokens) != 12 or tokens[:5] != ['(', 'cd', run, ';', 'exec']
                or tokens[-1] != ')' or tokens[6:11] != wanted):
            raise ValueError('Owned launcher differs from the exact frozen command')
        java = path(tokens[5], directory=False).resolve(strict=True)
        if java.name != 'java' or not java.is_relative_to(ROOT / 'scratch/jdk'):
            raise ValueError('Owned JVM must use the exact frozen repository JDK')
        return {'argv': tokens[5:11], 'cwd': run, 'exe': str(java),
                'launcher': str(launcher), 'launcher_sha256': entry['launcher_sha256'],
                'vm_args': str(vm), 'vm_args_sha256': entry['vm_args_sha256']}

    def owned_candidates(self, native):
        owned, foreign = {}, []
        for row in native:
            candidate = process_snapshot(row['pid'])
            if candidate is None:
                continue
            matches = []
            for server, owner in self.owners.items():
                expected = owner['expected']
                if candidate['argv'] != expected['argv']:
                    continue
                # Recheck both sealed files before using this proof, including stop.
                referenced({'path': expected['launcher'], 'sha256': expected['launcher_sha256']})
                referenced({'path': expected['vm_args'], 'sha256': expected['vm_args_sha256']})
                proof = owned_native_proof(candidate, owner['anchor'], expected)
                if proof is not None:
                    matches.append((server, proof))
            if len(matches) != 1 or matches[0][0] in owned:
                foreign.append(row)
            else:
                owned[matches[0][0]] = matches[0][1]
        return owned, foreign

    def guard_evidence(self, message, native, observers, owned=None):
        records = self.report.setdefault('process_guard_evidence', [])
        if len(records) >= 16:
            records.pop(0)
            self.report['older_guard_evidence_dropped'] = self.report.get('older_guard_evidence_dropped', 0) + 1
        records.append({'utc': utc(), 'failure': message, 'native_count': len(native),
            'observer_count': len(observers), 'native': native[:64], 'observers': observers[:64],
            'verified_owned': owned or {}, 'own_identities': {s: {k: i.get(k) for k in
                ('pid', 'server_id', 'world_id', 'session_id', 'fencing_epoch')} for s, i in self.identities.items()},
            'Popen_roots': {s: owner['anchor'] for s, owner in self.owners.items()},
            'scope': 'Bounded process metadata and argument SHA only; no raw argv, config bytes or credentials.'})
        self.save()

    def guard_observer(self, stopping=False):
        native, observers = processes()
        try:
            if len(native) > 64 or len(observers) > 64:
                raise ValueError('Process scanner evidence exceeds bounds')
            owned, foreign = self.owned_candidates(native)
            if observers:
                raise ValueError("Another local observer/build/controller remains active")
            if foreign:
                raise ValueError("An unrelated native JVM is active")
        except Exception as error:
            self.guard_evidence(type(error).__name__ + ': ' + str(error), native, observers, locals().get('owned'))
            raise
        for server, proof in owned.items():
            # restart holds these objects while RCON probes re-enter this guard.
            # Keep the object so its subsequent fresh session/epoch update lands
            # in the live map rather than a detached copy.
            self.identities[server]['pid'] = proof['pid']
        if not stopping and any(log.seen>MAX_LOG or log.failure for log in self.logs.values()):
            self.guard_evidence('Owned output limit/capture failure', native, observers, owned)
            raise ValueError('Owned native output exceeded the bounded retained prefix or capture failed')
        return native

    def issue(self, server, command):
        self.guard_observer(stopping=command=='stop'); row = self.event("RCON", server=server, command=command, outcome="UNKNOWN_NO_REPLAY");self.save()
        try:
            reply = self.base.command(PORTS[server], command, timeout=5)
            row.update(reply=reply, outcome="REPLY_OBSERVED")
            if len(reply.encode()) > 65536 or "ERROR " in reply:
                raise ValueError("Native reply rejected")
            return reply
        except Exception as error:
            row["exception"] = type(error).__name__ + ": " + str(error);raise
        finally:
            row["end"] = time.monotonic()-self.started;self.save()

    def verified_stop_candidate(self, server):
        owner = self.owners.get(server)
        if owner is None:
            return None
        if self.launcher_identity(server) != owner['expected']:
            raise ValueError('Owned frozen launch identity changed before normal stop')
        proofs = []
        for candidate in owned_tree(owner['anchor']):
            proof = owned_native_proof(candidate, owner['anchor'], owner['expected'])
            if proof is not None:
                proofs.append(proof)
        if len(proofs) > 1:
            raise ValueError('Ambiguous own JVM descendants; no stop issued')
        return proofs[0] if proofs else None

    def request_owned_normal_stop(self, server):
        """Cleanup only: foreign-workload rejection never authorizes or blocks this stop."""
        child = self.children.get(server)
        if child is None or child.poll() is not None:
            return True
        owner = self.owners.get(server)
        if owner is None:
            return False
        key = (server, owner['anchor']['pid'], owner['anchor']['start_ticks'])
        if key in self.stop_requested:
            return True  # An uncertain stop response is never replayed.
        proof = self.verified_stop_candidate(server)
        if proof is None:
            return False  # A late exec or already-closing launcher may have no JVM yet.
        readiness = self.report.setdefault('owned_stop_readiness', {}).setdefault(server, {'attempts': 0})
        readiness.update(attempts=readiness['attempts'] + 1, utc=utc(), process=proof)
        self.save()
        try:
            reply = self.base.command(PORTS[server], 'ct_test pid', timeout=5)
        except OSError as error:
            readiness['last_exception'] = type(error).__name__ + ': ' + str(error)[:500]
            self.save()
            return False  # Retry this read-only readiness probe, never an asset command.
        if not re.fullmatch(r'PID ' + str(proof['pid']) + r'\s*', reply):
            raise ValueError('RCON does not belong to the independently verified own JVM')
        current = self.verified_stop_candidate(server)
        if current != proof:
            raise ValueError('Owned JVM identity changed between PID confirmation and stop')
        self.stop_requested.add(key)
        event = self.event('OWNED_NORMAL_STOP', server=server, command='stop', process=proof,
                           outcome='UNKNOWN_NO_REPLAY', global_foreign_guard_bypassed_for_cleanup_only=True)
        self.save()
        try:
            event.update(reply=self.base.command(PORTS[server], 'stop', timeout=5), outcome='REPLY_OBSERVED')
        except Exception as error:
            event['exception'] = type(error).__name__ + ': ' + str(error)[:500]
        finally:
            event['end'] = time.monotonic() - self.started
            self.save()
        return True

    def retain_failed_children(self):
        """Keep Popen handles, observer lock and log drainers until actual owned exits."""
        deadline = time.monotonic() + self.args.timeout
        pending_notified = False
        def save_cleanup():
            try:
                self.save()
            except Exception as error:
                self.report['cleanup_evidence_save_failure'] = type(error).__name__ + ': ' + str(error)[:1000]
        while (any(child.poll() is None for child in self.children.values())
               or any(log.thread.is_alive() for log in self.logs.values())):
            for server, child in self.children.items():
                if child.poll() is None:
                    try:
                        self.request_owned_normal_stop(server)
                    except (Exception, KeyboardInterrupt) as error:
                        records = self.report.setdefault('owned_normal_stop_refusals', {})
                        prior = records.get(server, {})
                        records[server] = {'utc': utc(), 'count': prior.get('count', 0) + 1,
                                          'error': type(error).__name__ + ': ' + str(error)[:1000]}
                        save_cleanup()
            if time.monotonic() >= deadline and not pending_notified:
                self.report.update(state='FAILED_RETAINED_CLEANUP_PENDING',
                    pending_cleanup='Own launcher has not exited. Controller/Popen/logs retained; no hard kill, stop replay, failed-stage restart or asset command.')
                save_cleanup()
                print(json.dumps({'state': self.report['state'], 'report': str(self.target.relative_to(ROOT)),
                                  'action_required': 'Inspect retained own processes; controller will wait for their actual exit.'}), flush=True)
                pending_notified = True
            try:
                time.sleep(self.args.poll)
            except KeyboardInterrupt:
                self.report['cleanup_interrupt_received'] = utc()
                save_cleanup()  # Do not orphan children or drop the only log readers.
        self.report['failure_own_launcher_exits'] = {s: child.poll() for s, child in self.children.items()}
        self.report['failure_bounded_logs'] = {s: log.finish() for s, log in self.logs.items()}
        self.report.update(state='FAILED_RETAINED', utc_end=utc())
        self.save()

    def sql(self, statement):
        self.guard_observer();row=self.event("SQL_SELECT",statement=statement)
        values=self.base.sql(statement)
        if len(values)!=1 or len(values[0])!=1 or len(values[0][0].encode())>1_048_576:
            raise ValueError("One bounded JSON SELECT result required")
        result=json.loads(values[0][0],object_pairs_hook=unique);row.update(result=result,end=time.monotonic()-self.started);return result

    def wait(self, read, predicate):
        until=time.monotonic()+self.args.timeout
        while time.monotonic()<until:
            result=read()
            if predicate(result):return result
            time.sleep(self.args.poll)
        raise TimeoutError("Fixed state deadline; last raw read retained")

    def source_gate(self):
        paths=sorted((ROOT/"src/main/java").rglob("*.java"))
        if len(paths)>1024 or sum(p.stat().st_size for p in paths)>8_388_608:
            raise ValueError("Main source bounds")
        actual=sha(b"".join(str(p.relative_to(ROOT)).encode()+b"\0"+hashlib.sha256(path(p).read_bytes()).digest() for p in paths))
        if actual!=self.artifact['main_sha256'] or self.seal["artifacts"]["JAR"]["sha256"]!=self.artifact['jar_sha256']:
            raise ValueError("Final main/JAR identity changed")
        jar=referenced(self.seal["artifacts"]["JAR"],32*1024*1024)
        with zipfile.ZipFile(jar) as archive:
            names=[n for n in archive.namelist() if n.startswith("dev/crosstesseract/") and n.endswith(".class")]
            if not names or len(names)>4096 or sum(archive.getinfo(n).file_size for n in names)>32*1024*1024:
                raise ValueError("Bounded final mod class set required")
            expected={n:sha(archive.read(n)) for n in names}
        for server in PORTS:
            entry=self.seal["launches"][server];launcher=referenced({"path":entry["launcher"],"sha256":entry["launcher_sha256"]})
            folder=launcher.parent
            if folder.parent!=ROOT/"scratch/dev-launch" or launcher.name!="runServer"+server+".sh" or not re.fullmatch("[0-9a-f]{32}",folder.name):
                raise ValueError("Exact previously frozen server launch required")
            referenced({"path":entry["vm_args"],"sha256":entry["vm_args_sha256"]})
            for kind in ("classes","resources"):
                wanted={row["relative_path"]:row["sha256"] for row in self.seal["artifacts"][kind]["files"]}
                selected=list(path(folder/kind,directory=True).rglob("*"))
                if len(selected)>8192 or any(p.is_symlink() for p in selected) or sum(p.stat().st_size for p in selected if p.is_file())>32*1024*1024:
                    raise ValueError("Bounded frozen directory without symlinks required")
                actual={str(p.relative_to(folder/kind)):sha(path(p).read_bytes()) for p in selected if p.is_file()}
                if actual!=wanted:raise ValueError("Frozen class/resource content differs from reviewed manifest")
                if kind=="classes" and {n:h for n,h in actual.items() if n.startswith("dev/crosstesseract/") and n.endswith(".class")}!=expected:
                    raise ValueError("Actual frozen mod classes differ from the exact reviewed mod JAR")
            for suffix in ("RunVmArgs","RunProgramArgs","RunClasspath"):
                argument=path(folder/("server"+server+suffix+".txt"))
                current=metadata(argument)
                if self.files.get(str(argument))!=current:raise ValueError("Frozen argument file changed since the actual soak")
        for filename, point in self.inputs.items():referenced(point)

    def probe_gate(self, name):
        """An old sealed STOP only sets pendingStop in a fresh JVM with no active Session.

        Reviewed configure/watch/enter create no result in that state; transformed
        metadata remains in RAM. All result writes use CREATE_NEW. Do not clear a
        control or alter any original report: require the exact sealed STOP and
        retain full content/mtime inventories before and after every own boot.
        """
        if self.soak.get('probe_window_measurement_status')!='MEASURED_FIXED_AND_FULL':
            raise ValueError('Completed sealed v2 soak probe evidence required')
        probe=referenced({'path':self.seal['probe_manifest'],'sha256':self.seal['probe_manifest_sha256']})
        agent=document(probe)
        if agent.get('recorder_revision')!='v2_mod_roots':raise ValueError('Reviewed v2 recorder only')
        for filename,expected in PROBE_SOURCES.items():
            if agent['sources'].get(filename)!=expected or sha(path(ROOT/filename).read_bytes())!=expected:
                raise ValueError('Probe source changed since the STOP-restart safety review')
        for point in agent['artifacts']:referenced(point,32*1024*1024)
        observed={}
        for server in PORTS:
            entry=self.seal['launches'][server];control=path(entry['control'],4096);output=path(entry['output'],directory=True)
            if not control.is_relative_to(ROOT/'scratch') or not (output.is_relative_to(ROOT/'scratch') or output.is_relative_to(ROOT/'reports/rc-20261017')):
                raise ValueError('Only this manifest explicit probe control/output scope allowed')
            sealed=self.soak['probe_full_lifecycle'][server]
            final=referenced(sealed['source']);token=str(uuid.UUID(sealed['data']['token']))
            if final.parent!=output or final.name!=token+'.json' or sealed['data'].get('window_closed') is not True or control.read_bytes().strip()!=('stop '+token).encode('ascii'):
                raise ValueError('Old control must be the exact completed-soak sealed STOP token')
            vm=shlex.split(path(entry['vm_args']).read_text(),comments=True)
            wanted=str(control)+';'+str(output)
            if len([v for v in vm if v.startswith('-javaagent:') and v.partition('=')[2]==wanted])!=1:
                raise ValueError('Actual frozen probe paths differ from sealed control/output')
            entries=sorted(output.iterdir())
            if len(entries)>512 or any(p.is_symlink() or not p.is_file() for p in entries) or sum(p.stat().st_size for p in entries)>128*1024*1024:
                raise ValueError('Probe output inventory bounds or file types changed')
            files=[dict(metadata(path(p,MAX_REPORT)),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in entries]
            observed[server]={'control':dict(metadata(control),bytes=control.stat().st_size,mtime_ns=control.stat().st_mtime_ns),
                'sealed_token':token,'output':str(output.relative_to(ROOT)),'output_mtime_ns':output.stat().st_mtime_ns,'files':files}
        if self.probe_files is None:
            self.probe_files=observed;self.report['original_probe_file_inventory']=observed
        elif observed!=self.probe_files:raise ValueError('Original soak probe control/output content or mtime changed')
        self.report['probe_file_checks'].append({'name':name,'utc':utc(),'unchanged':True,'inventory_sha256':sha(json.dumps(observed,sort_keys=True,separators=(',',':')).encode()),'control_mutations':False})

    def all_soak_sql(self, name, held=None):
        channels=','.join("'"+str(uuid.UUID(e['expected_channel']))+"'" for e in {v['expected_channel']:v for v in self.all_devices}.values())
        worlds=','.join("'"+str(uuid.UUID(i['world_id']))+"'" for i in self.identities.values())
        ids=','.join("'"+str(uuid.UUID(e['id']))+"'" for e in self.all_devices)
        data=self.sql("SELECT JSON_OBJECT('endpoints',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('id',endpoint_id,'channel',channel_id,'owner',device_owner,'server',server_id,'world',world_id,'state',state)) FROM ct_endpoints WHERE cluster_id='dev_three_v1' AND world_id IN ("+worlds+")),JSON_ARRAY()),'pool_rows',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('channel',b.channel_id,'resource',b.resource_id,'kind',r.kind,'amount',b.amount)) FROM ct_balances b JOIN ct_resources r ON r.cluster_id=b.cluster_id AND r.resource_id=b.resource_id WHERE b.cluster_id='dev_three_v1' AND b.channel_id IN ("+channels+")),JSON_ARRAY()),'allocation_rows',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('channel',a.channel_id,'resource',a.resource_id,'kind',a.resource_kind,'state',a.state,'count',a.n,'remaining',a.remaining)) FROM (SELECT t.channel_id,t.resource_id,r.kind AS resource_kind,t.state,COUNT(*) AS n,SUM(t.remaining) AS remaining FROM ct_transfers t JOIN ct_resources r ON r.cluster_id=t.cluster_id AND r.resource_id=t.resource_id WHERE t.cluster_id='dev_three_v1' AND t.channel_id IN ("+channels+") AND t.kind='ALLOCATE' GROUP BY t.channel_id,t.resource_id,r.kind,t.state) a),JSON_ARRAY()),'grants',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('endpoint',endpoint_id,'player',player_uuid,'slot',slot_no,'request',request_id,'desired',desired,'policy',policy_version)) FROM ct_chunk_grants WHERE cluster_id='dev_three_v1' AND endpoint_id IN ("+ids+")),JSON_ARRAY()),'quota_limit',(SELECT quota_limit FROM ct_clusters WHERE cluster_id='dev_three_v1'),'policy_version',(SELECT policy_version FROM ct_clusters WHERE cluster_id='dev_three_v1'))")
        rows={r['id']:r for r in data['endpoints']}
        if set(rows)!={e['id'] for e in self.all_devices}:raise ValueError('Original full-soak SQL endpoint set changed')
        for endpoint in self.all_devices:
            row=rows[endpoint['id']];identity=self.identities[endpoint['server']]
            if [row[k] for k in ('channel','owner','server','world','state')]!=[endpoint['expected_channel'],self.owner,identity['server_id'],identity['world_id'],'ACTIVE']:
                raise ValueError('Original full-soak SQL endpoint identity changed')
        selected_pool = sum(r['amount'] for r in data['pool_rows'] if r['channel']==self.channel and r['kind']==FE) if held is not None else 0
        selected_owned = sum(r['remaining'] for r in data['allocation_rows'] if r['channel']==self.channel and r['kind']==FE and r['state']=='LOCAL') if held is not None else 0
        if held is None:
            if any(r['amount']!=0 for r in data['pool_rows']) or any(r['remaining']!=0 for r in data['allocation_rows']):
                raise ValueError('Another original soak channel has a positive SQL asset; do not consume or replay it')
        elif (selected_pool != 61 or selected_owned != 75
                or any(r['amount'] for r in data['pool_rows'] if r['channel']!=self.channel or r['kind']!=FE)
                or any(r['remaining'] for r in data['allocation_rows'] if r['channel']!=self.channel or r['kind']!=FE or r['state']!='LOCAL')):
            raise ValueError('Only the exact selected positive61 pool/75 LOCAL handoff may remain; all other original cohort assets must stay zero')
        persistent={'quota_limit':data['quota_limit'],'policy_version':data['policy_version'],'grant_count':len(data['grants']),
            'desired_grant_count':sum(r['desired'] for r in data['grants']),'grants':sorted(data['grants'],key=lambda r:r['endpoint'])}
        if self.quota is None:self.quota=persistent
        elif persistent!=self.quota:raise ValueError('Original soak persistent quota/grant count or identity changed')
        self.report['all_soak_SQL_checks'].append({'name':name,'utc':utc(),'SQL':data,'persistent_quota':persistent,
            'all_resource_pool_zero':all(r['amount']==0 for r in data['pool_rows']),
            'all_resource_allocation_remaining_zero':all(r['remaining']==0 for r in data['allocation_rows']),
            'selected_positive_handoff':None if held is None else held['name'],
            'scope':'Every original soak channel/resource checked separately; no cross-resource or SQL/WAL asset sum.'})

    def files_gate(self, flags):
        self.source_gate()
        for server, identity in self.identities.items():
            run=ROOT/("run-"+server);cfg=path(run/"cross-tesseract.properties");raw=cfg.read_bytes()
            vanilla=path(run/"server.properties").read_bytes();eula=path(run/"eula.txt").read_bytes()
            props=self.pure.properties(raw);sp=self.pure.properties(vanilla);ep=self.pure.properties(eula);mysql=urlsplit(props.get("mysql.url","").removeprefix("jdbc:"))
            if not(props.get("backend.enabled")=="true" and props.get("cluster.id")=="dev_three_v1" and props.get("server.id")==identity["server_id"]
                    and props.get("mysql.user")=="ct_dev" and mysql.scheme=="mysql" and mysql.hostname=="127.0.0.1" and mysql.port==13306 and mysql.path=="/cross_tesseract" and not mysql.username and not mysql.password
                    and props.get("redis.uri")=="redis://127.0.0.1:16379" and tuple(props.get(k) for k in FLAGS)==flags
                    and sp.get("server-ip")=="127.0.0.1" and sp.get("enable-rcon")=="true" and sp.get("rcon.port")==str(PORTS[server]) and sp.get("level-name")==identity["level_name"] and ep.get("eula")=="true"):
                raise ValueError("Only exact stopped-soak loopback configs/worlds and flags allowed")
            world=path(run/identity["level_name"],directory=True);wid=path(world/"cross_tesseract/world-id",128).read_bytes()
            if str(uuid.UUID(wid.decode().strip()))!=identity["world_id"]:raise ValueError("Same world UUID required")
            stable={"world_id":sha(wid),"server_properties":self.pure.properties_semantic_sha(vanilla),"eula":sha(eula)}
            if server in self.configs:
                if raw!=self.configs[server] or stable!=self.stable[server]:raise ValueError("External config/world properties changed")
            else:
                verify_initial_config(raw,identity)
                self.configs[server]=raw;self.stable[server]=stable
                backup=self.round/(server+"-initial-cross-tesseract.properties")
                with backup.open("xb") as output:os.chmod(backup,0o600);output.write(raw)
                self.report.setdefault("initial_config_snapshots",{})[server]={"snapshot":metadata(backup),"config_sha256":sha(raw),"stable_files":stable}

    def acquire_stopped(self):
        handles={}
        try:
            if processes()[0]:raise ValueError("All native processes must already be stopped")
            for server in PORTS:
                p=ROOT/"scratch"/("server-"+server+".launch.lock")
                if p.is_symlink():raise ValueError("No symlink launch lock")
                handle=p.open("a");handles[server]=handle;fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.locks=handles
        except BaseException:
            for handle in handles.values():handle.close()
            raise

    def server_rows(self):
        ids=",".join("'"+i["server_id"]+"'" for i in self.identities.values())
        return self.sql("SELECT JSON_OBJECT('servers',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('server',server_id,'world',world_id,'session',session_id,'epoch',fencing_epoch,'status',status,'clean_stop',clean_stop,'lease_live',lease_until>CURRENT_TIMESTAMP(6))) FROM ct_servers WHERE cluster_id='dev_three_v1' AND server_id IN ("+ids+")),JSON_ARRAY()),'other_live', (SELECT COUNT(*) FROM ct_servers WHERE lease_until>CURRENT_TIMESTAMP(6) AND NOT(cluster_id='dev_three_v1' AND server_id IN ("+ids+"))))")

    def stopped_sql(self):
        data=self.server_rows();rows={r['server']:r for r in data['servers']}
        if data['other_live'] or len(rows)!=3:raise ValueError("Unique isolated three-server SQL set required")
        for identity in self.identities.values():
            row=rows[identity['server_id']]
            if (row['world'],row['session'],row['epoch'],row['status'],row['clean_stop'],row['lease_live'])!=(identity['world_id'],identity['session_id'],identity['fencing_epoch'],'STOPPED',1,False):
                raise ValueError("Actual same-session SQL clean_stop acknowledgement missing")
        return data

    def restart(self, stage, flags):
        self.files_gate(flags);self.probe_gate(stage+'_before_restart')
        if set(self.locks)!=set(PORTS):raise ValueError("Hold all stopped launch locks before restart")
        old=boot_boundary(self.identities)
        for h in self.locks.values():h.close()
        self.locks={};self.children={};self.logs={};self.owners={}
        for server in PORTS:
            launch=self.seal['launches'][server]['launcher'];log=self.round/(stage+'-'+server+'.log')
            expected = self.launcher_identity(server)
            self.children[server]=subprocess.Popen(['bash',str(ROOT/'scripts/start-frozen-dev.sh'),server,launch],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            self.logs[server]=BoundedLog(self.children[server].stdout,log)
            anchor = process_snapshot(self.children[server].pid)
            if anchor is None:
                raise ValueError('Own launcher exited before its birth identity could be bound')
            self.owners[server] = {'anchor': {key: anchor[key] for key in ('pid', 'start_ticks')}, 'expected': expected}
        self.report.setdefault('owned_launch_roots', []).append({'stage': stage, 'utc': utc(),
            'roots': {s: {'anchor': owner['anchor'], 'launcher': owner['expected']['launcher'],
                'launcher_sha256': owner['expected']['launcher_sha256'],
                'vm_args_sha256': owner['expected']['vm_args_sha256']} for s, owner in self.owners.items()}})
        self.save()
        def ready():
            for server,child in self.children.items():
                if child.poll() is not None:raise ValueError('Own launcher exited before ready: '+server)
            # Fresh ownership derives from this round's Popen ancestry, including
            # late bash-to-Java exec, rather than the completed soak's exited PIDs.
            native = self.guard_observer()
            owned, _ = self.owned_candidates(native)
            if set(owned) != set(PORTS):return False
            try:return all('STATUS online' in self.issue(s,'ct_test status') for s in PORTS)
            except OSError:return False  # Startup reads only, never repeat a native asset mutation.
        self.wait(ready,bool);data=self.server_rows();rows={r['server']:r for r in data['servers']}
        if data['other_live']:raise ValueError('Other live SQL sessions')
        for server,identity in self.identities.items():
            row=rows[identity['server_id']]
            pid=int(re.fullmatch(r'PID (\d+)\s*',self.issue(server,'ct_test pid'))[1])
            if row['world']!=identity['world_id'] or row['epoch']!=old[server]['fencing_epoch']+1 or row['session']==old[server]['session_id'] or not row['lease_live'] or row['status']!='ONLINE' or pid!=identity['pid'] or pid==old[server]['pid']:
                raise ValueError('Fresh fenced boot on original world required')
            identity.update(session_id=row['session'],fencing_epoch=row['epoch'])
        self.report['boots'].append({'stage':stage,'identity':json.loads(json.dumps(self.identities)),'flags':flags,'SQL':data,'utc':utc()});self.files_gate(flags);self.save()

    def stop(self, stage, flags, held=None):
        self.files_gate(flags);self.guard_observer()
        self.wait(lambda:all(self.request_owned_normal_stop(server) for server in PORTS),bool)
        self.wait(lambda:all(c.poll() is not None for c in self.children.values()),bool)
        exits={s:c.returncode for s,c in self.children.items()}
        if len(exits)!=3 or any(code!=0 for code in exits.values()):raise ValueError('Actual own launcher exit0 required')
        logs={s:log.finish() for s,log in self.logs.items()}
        self.report['normal_stops'].append({'stage':stage,'launcher_exit_codes':exits,'logs':logs,'utc':utc()});self.save()
        if any(not r['capture_complete'] or r['capture_failure'] or r['dropped_bytes'] for r in logs.values()):raise ValueError('Bounded native log capture failed/truncated')
        if any('RC_PROBE_CONTROL_FAILURE' in log.target.read_text(errors='replace') for log in self.logs.values()):raise ValueError('Restarted probe rejected old control state')
        self.acquire_stopped();data=self.stopped_sql();self.report['normal_stops'][-1]['SQL']=data
        self.probe_gate(stage+'_after_normal_stop');self.all_soak_sql(stage+'_stopped',held)
        if held is not None:
            value=self.snapshot(held['watermark_db_session'],stopped=True)
            if not self.held_positive(held,value):raise ValueError('Original positive SQL/WAL IDs or amounts changed during normal stop')
            held['stopped_before_switch']=value
        self.save()

    def switch(self, name, before, after):
        self.files_gate(before)
        if set(self.locks)!=set(PORTS) or processes()[0]:raise ValueError('All stopped launch locks required for config edit')
        self.stopped_sql();record={'name':name,'before':before,'after':after,'files':[],'complete':False};self.report['config_switches'].append(record);self.save()
        for server in PORTS:
            selected=path(ROOT/('run-'+server)/'cross-tesseract.properties');raw=selected.read_bytes()
            if raw!=self.configs[server]:raise ValueError('Config compare failed immediately before edit')
            backup=self.round/(name+'-'+server+'.properties')
            with backup.open('xb') as output:os.chmod(backup,0o600);output.write(raw);output.flush();os.fsync(output.fileno())
            changed=self.pure.flag_rewrite(raw,before,after);temporary=selected.with_name(selected.name+'.rc-fallback-'+self.token)
            with temporary.open('xb') as output:os.chmod(temporary,stat.S_IMODE(selected.stat().st_mode));output.write(changed);output.flush();os.fsync(output.fileno())
            temporary.replace(selected);fd=os.open(selected.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            self.configs[server]=changed;record['files'].append({'server':server,'backup':metadata(backup),'before_sha256':sha(raw),'after_sha256':sha(changed)});self.save()
        self.files_gate(after);record['complete']=True;self.save()

    def inspect(self, endpoint):
        try:reply=self.issue(endpoint['server'],f"ct_test inspect {endpoint['x']} {endpoint['z']}")
        except ValueError:
            if self.report['events'][-1].get('reply','').strip()=='ERROR endpoint_not_found':return None
            raise
        value=self.base.device_fields(reply)
        expected=endpoint.get('expected_channel',self.channel)
        if value['id']!=endpoint['id'] or value['channel'] not in (expected,'null') or value['registered'] and value['channel']!=expected:
            raise ValueError('Existing native endpoint identity/binding changed')
        return value

    def mode(self, endpoint, value):
        if self.issue(endpoint['server'],f"ct_test mode {endpoint['x']} {endpoint['z']} {FE} {value}").strip()!='MODE '+value:raise ValueError('Mode acknowledgement missing')

    def read_mode(self, endpoint, kind):
        reply=self.issue(endpoint['server'],f'data get block {endpoint["x"]} 64 {endpoint["z"]} ports."{kind}".mode')
        return self.pure.mode_reply(reply,argparse.Namespace(x=endpoint['x'],z=endpoint['z']))

    def snapshot(self, watermark, stopped=False):
        mark='1000-01-01 00:00:00.000000' if watermark is None else watermark
        if not re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{6}',mark):raise ValueError('Database-clock watermark format')
        c="cluster_id='dev_three_v1' AND channel_id='"+self.channel+"'"
        statement="SELECT JSON_OBJECT('db_time',DATE_FORMAT(CURRENT_TIMESTAMP(6),'%Y-%m-%d %H:%i:%s.%f'),'pool',COALESCE((SELECT SUM(amount) FROM ct_balances WHERE "+c+"),0),'owned',COALESCE((SELECT SUM(remaining) FROM ct_transfers WHERE "+c+" AND kind='ALLOCATE'),0),'quarantined', (SELECT COUNT(*) FROM ct_transfers WHERE "+c+" AND state='QUARANTINED'),'new_transfers',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('id',transfer_id,'endpoint',endpoint_id,'resource',resource_id,'kind',kind,'state',state,'amount',amount,'remaining',remaining)) FROM (SELECT * FROM ct_transfers WHERE "+c+" AND created_at>='"+mark+"' ORDER BY transfer_id LIMIT 33) t),JSON_ARRAY()),'resources',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('id',r.resource_id,'kind',r.kind,'format',r.format_version,'bytes',OCTET_LENGTH(r.payload),'hash',r.payload_hash)) FROM ct_resources r WHERE r.cluster_id='dev_three_v1' AND EXISTS(SELECT 1 FROM ct_transfers t WHERE t.cluster_id=r.cluster_id AND t.resource_id=r.resource_id AND t.channel_id='"+self.channel+"')),JSON_ARRAY()),'endpoints',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('id',endpoint_id,'server',server_id,'world',world_id,'owner',device_owner,'checkpoint',checkpoint,'epoch',last_epoch,'generation',recovery_generation,'state',state,'x',pos_x,'y',pos_y,'z',pos_z,'dimension',dimension_id)) FROM ct_endpoints WHERE "+c+"),JSON_ARRAY()),'demands',COALESCE((SELECT JSON_ARRAYAGG(JSON_OBJECT('endpoint',endpoint_id,'room',room,'live',expires_at>CURRENT_TIMESTAMP(6),'last_grant',last_grant)) FROM ct_demands WHERE "+c+" AND kind='"+FE+"'),JSON_ARRAY()))"
        result=self.sql(statement)
        if len(result['new_transfers'])>32:raise ValueError('Unexpected phase transfer bound; refusing truncated evidence')
        if result['resources'] and (len(result['resources'])!=1 or {k:result['resources'][0][k] for k in ('kind','format','bytes','hash')}!={'kind':FE,'format':1,'bytes':0,'hash':sha(b'')}):raise ValueError('Existing channel is not exclusively fixed native FE')
        rows={r['id']:r for r in result['endpoints']}
        if set(rows)!={e['id'] for e in self.devices}:raise ValueError('Unexpected channel endpoint inventory')
        local={};wal={}
        for endpoint in self.devices:
            row=rows[endpoint['id']];identity=self.identities[endpoint['server']]
            if [row[k] for k in ('server','world','owner','state','x','y','z','dimension','epoch')]!=[identity['server_id'],identity['world_id'],self.owner,'ACTIVE',endpoint['x'],64,endpoint['z'],'minecraft:overworld',identity['fencing_epoch']]:raise ValueError('Existing SQL endpoint ownership/location/epoch differs')
            if not stopped:
                local[endpoint['id']]=self.inspect(endpoint)
                if local[endpoint['id']] is None:raise ValueError('Confirmed original endpoint disappeared during observation')
            selected=ROOT/('run-'+endpoint['server'])/identity['level_name']/'cross_tesseract/journal'/(endpoint['id']+'.ctj')
            current=self.pure.decode_fe_wal(path(selected).read_bytes())
            if (current['endpoint'],current['world'],current['generation'])!=(endpoint['id'],identity['world_id'],row['generation']):raise ValueError('Owned WAL identity differs')
            wal[endpoint['id']]=current
        result.update(local=local,WAL=wal,stopped=stopped,source_endpoint=self.lane['sources'][0]['id'],
            local_scope='Runtime buffers not observed while stopped' if stopped else 'Actual native endpoint inspection')
        self.event('owned_SQL_local_WAL_frame',value=result);return result

    @staticmethod
    def zero(frame):
        return (frame['pool']==frame['owned']==frame['quarantined']==0
            and all(p['registered'] and not p['pause'] and all(p[k]==0 for k in ('txFE','rxFE','txItem','rxItem','txFluid','rxFluid')) for p in frame['local'].values())
            and all(not w['deposits'] and all(c['remaining']==0 for c in w['credits']) and w['revision']<=next(e['checkpoint'] for e in frame['endpoints'] if e['id']==ep) for ep,w in frame['WAL'].items()))

    def quiet(self, watermark):
        until=time.monotonic()+self.args.timeout;since=None;points=[]
        while time.monotonic()<until:
            value=self.snapshot(watermark);points.append(value)
            if self.zero(value):
                if since is None:since=time.monotonic()
                if time.monotonic()-since>=self.args.quiet:return {'passed':True,'quiet_seconds':time.monotonic()-since,'snapshots':points}
            else:since=None  # Actual skew/nonzero read retained; adjusted evidence is never accepted.
            time.sleep(self.args.poll)
        raise TimeoutError('No full uninterrupted strict SQL/local/WAL quiet within the original deadline')

    def native(self, stage, endpoint, kind, amount):
        event={'endpoint':endpoint['id'],'kind':kind,'requested':amount,'actual':None,'outcome':'UNKNOWN_NO_REPLAY'};stage['native_events'].append(event);self.save()
        reply=self.issue(endpoint['server'],f"ct_test {'push' if kind=='input' else 'pull'}-fe {endpoint['x']} {endpoint['z']} {amount}")
        match=re.fullmatch(('ACCEPTED' if kind=='input' else 'EXTRACTED')+r' (\d+)\s*',reply)
        if not match or not 0<=int(match[1])<=amount:raise ValueError('Uncertain native result; never replay')
        value=int(match[1]);event.update(actual=value,outcome='CONFIRMED_NATIVE_AMOUNT')
        if kind=='input':stage['accepted']+=value
        else:stage['output']+=value;stage['per_receiver'][endpoint['id']]+=value
        self.save()
        if stage['output']>stage['accepted']:raise ValueError('Duplicate native output')
        return value

    def quiet_positive(self, held):
        deadline=time.monotonic()+self.args.timeout;since=None;frames=[]
        while time.monotonic()<deadline:
            frame=self.snapshot(held['watermark_db_session']);frames.append(frame)
            if self.held_positive(held,frame):
                if since is None:since=time.monotonic()
                if time.monotonic()-since>=self.args.quiet:return {'passed':True,'quiet_seconds':time.monotonic()-since,'snapshots':frames}
            else:since=None
            time.sleep(self.args.poll)
        raise TimeoutError('Original positive handoff did not remain coherent within its fixed deadline')

    def held_positive(self, held, frame):
        if not positive_state(frame,189,53,61,75,1,self.channel):return False
        if sorted(frame['new_transfers'],key=lambda r:r['id'])!=held['held_transfers']:
            raise ValueError('Original positive business ID/endpoint/resource/amount/remaining changed across restart')
        return True

    def fresh_business_ids(self, ids, current):
        prior={value for group in self.report['stages']+self.report['positive_handoffs'] if group is not current for value in group.get('business_ids',[])}
        if len(ids)!=len(set(ids)) or set(ids)&prior:raise ValueError('An earlier phase business ID was reused')

    def prepare_positive(self, name, receiver):
        initial=self.quiet('9999-12-31 23:59:59.999999')
        held={'name':name,'watermark_db_session':initial['snapshots'][-1]['db_time'],'accepted':0,'output':0,
            'per_receiver':{e['id']:0 for e in self.lane['sinks']},'native_events':[], 'initial_empty':initial,
            'held_receiver':receiver['id'],'prepared':False,'passed':False}
        self.report['positive_handoffs'].append(held);self.save()
        source=self.lane['sources'][0]
        active=lambda frame:[v for v in frame['demands'] if v['live'] and v['room']>0]
        self.wait(lambda:self.snapshot(held['watermark_db_session']),lambda f:self.zero(f) and not active(f))
        self.mode(source,'SEND');self.mode(receiver,'RECEIVE')
        self.wait(lambda:self.snapshot(held['watermark_db_session']),lambda f:any(v['endpoint']==receiver['id'] for v in active(f)) and all(v['endpoint']==receiver['id'] for v in active(f)))
        if self.native(held,source,'input',128)!=128:raise ValueError('New positive128 input was partial/uncertain; never replay')
        received=self.wait(lambda:self.snapshot(held['watermark_db_session']),lambda f:positive_state(f,128,0,0,128,1,self.channel) and next(v for v in f['new_transfers'] if v['kind']=='ALLOCATE')['endpoint']==receiver['id'])
        held['original_allocation_id']=next(v['id'] for v in received['new_transfers'] if v['kind']=='ALLOCATE');held['initial_LOCAL128']=received
        if self.native(held,receiver,'output',53)!=53:raise ValueError('Positive partial native53 extraction was not exact')
        self.mode(receiver,'OFF');off=time.monotonic()
        held['durable_LOCAL75_OFF_demand_expired']=self.wait(lambda:self.snapshot(held['watermark_db_session']),lambda f:positive_state(f,128,53,0,75,1,self.channel) and not active(f) and time.monotonic()-off>=6.2)
        held['actual_OFF_TTL_wait_seconds']=time.monotonic()-off
        if self.native(held,source,'input',61)!=61:raise ValueError('New positive61 pool input was partial/uncertain; never replay')
        pending=self.wait(lambda:self.snapshot(held['watermark_db_session']),lambda f:positive_state(f,189,53,61,75,1,self.channel) and not active(f))
        held['held_transfers']=sorted(pending['new_transfers'],key=lambda r:r['id']);ids=[r['id'] for r in held['held_transfers']];self.fresh_business_ids(ids,held);held['business_ids']=ids
        self.mode(source,'OFF')
        held['prepared_positive_quiet']=self.quiet_positive(held);held['prepared']=True
        held['ledger_before_restart']=self.pure.asset_ledger(189,53,61,75)
        self.all_soak_sql(name+'_positive_prepared',held);self.save();return held

    def recover_positive(self, held, name):
        held['restored_positive_quiet']=self.quiet_positive(held)
        for receiver in self.lane['sinks']:
            if self.read_mode(receiver,FE)!='OFF' or self.native(held,receiver,'output',189)!=0:
                raise ValueError('Restored OFF receiver exposed positive native assets')
        old=next(e for e in self.lane['sinks'] if e['id']==held['held_receiver']);other=next(e for e in self.lane['sinks'] if e['id']!=old['id'])
        self.mode(other,'RECEIVE')
        def allocated(frame):
            if not positive_state(frame,189,53,0,136,2,self.channel):return False
            rows={v['id']:v for v in frame['new_transfers']}
            if any(rows.get(v['id'])!=v for v in held['held_transfers']):raise ValueError('Original positive transfer identity changed when allocating the held pool')
            new=[v for v in rows.values() if v['kind']=='ALLOCATE' and v['id']!=held['original_allocation_id']]
            return len(new)==1 and (new[0]['endpoint'],new[0]['amount'],new[0]['remaining'])==(other['id'],61,61)
        point=self.wait(lambda:self.snapshot(held['watermark_db_session']),allocated);held['restored_POOL61_new_allocation']=point
        ids=[r['id'] for r in point['new_transfers']];self.fresh_business_ids(ids,held);held['business_ids']=ids
        self.mode(old,'RECEIVE')
        self.wait(lambda:self.snapshot(held['watermark_db_session']),lambda f:allocated(f) and any(v['endpoint']==old['id'] and v['live'] and v['room']>0 for v in f['demands']))
        for receiver,amount in ((old,75),(other,61)):
            if self.native(held,receiver,'output',amount)!=amount:raise ValueError('Restored original75/newly allocated61 native output was not exact')
        held['after_drain_quiet']=self.quiet(held['watermark_db_session'])
        for receiver in self.lane['sinks']:
            if self.native(held,receiver,'output',189)!=0:raise ValueError('Positive handoff duplicate output')
        for endpoint in self.devices:self.mode(endpoint,'OFF')
        final=self.quiet(held['watermark_db_session']);frame=final['snapshots'][-1]
        if not positive_state(frame,189,189,0,0,2,self.channel) or held['accepted']!=held['output'] or held['output']!=189:
            raise ValueError('Positive handoff final exact business ledger is not conserved')
        held.update(final_empty=final,passed=True,restored_in_stage=name,duplicate_output=0,
                    ledger_after_restart=self.pure.asset_ledger(189,189,0,0))
        self.all_soak_sql(name+'_positive_recovered');self.save()

    def stage(self, name, flags, incoming=None, outgoing_receiver=None):
        self.restart(name,flags)
        for endpoint in self.all_devices:
            self.wait(lambda e=endpoint:self.inspect(e),lambda p:p is not None and p['registered'] and not p['pause'] and p['channel']==endpoint['expected_channel'])
            state=self.inspect(endpoint)
            for kind in ('txFE','rxFE','txItem','rxItem','txFluid','rxFluid'):
                expected=75 if incoming is not None and endpoint['id']==incoming['held_receiver'] and kind=='rxFE' else 0
                if state[kind]!=expected:raise ValueError('Original cohort buffer differs from the exact expected empty/positive handoff')
            if any(self.read_mode(endpoint,kind)!='OFF' for kind in (FE,'cross_tesseract:item','cross_tesseract:fluid')):
                raise ValueError('All original soak resource modes must remain persisted OFF before new phase input')
        if incoming is not None:
            self.all_soak_sql(name+'_restored_positive',incoming);self.recover_positive(incoming,name)
        self.all_soak_sql(name+'_before_new_input')
        # Sole selected lane; all other endpoints retain their persisted OFF modes.
        before=self.quiet('9999-12-31 23:59:59.999999');mark=before['snapshots'][-1]['db_time']
        stage={'name':name,'flags':flags,'watermark_db_session':mark,'accepted':0,'output':0,'per_receiver':{e['id']:0 for e in self.lane['sinks']},'native_events':[],'initial_empty':before,'rounds':[]};self.report['stages'].append(stage);self.save()
        self.mode(self.lane['sources'][0],'SEND')
        for receiver in self.lane['sinks']:self.mode(receiver,'RECEIVE')
        for number in range(3):
            def both_demand(frame):
                return all(any(d['endpoint']==e['id'] and d['room']>0 and d['live'] for d in frame['demands']) for e in self.lane['sinks'])
            self.wait(lambda:self.snapshot(mark),both_demand)
            if self.native(stage,self.lane['sources'][0],'input',63)!=63:raise ValueError('New bounded native input was not fully accepted')
            target=(number+1)*63
            def drain_once():
                for receiver in self.lane['sinks'][number%2:]+self.lane['sinks'][:number%2]:
                    if stage['output']<target:self.native(stage,receiver,'output',target-stage['output'])
                return stage['output']
            self.wait(drain_once,lambda n:n==target)
            stage['rounds'].append(self.quiet(mark));self.save()
        if stage['accepted']!=189 or stage['output']!=189 or any(n<=0 for n in stage['per_receiver'].values()):raise ValueError('All189 accepted/output and both mixed receivers required')
        for receiver in self.lane['sinks']:
            if self.native(stage,receiver,'output',189)!=0:raise ValueError('Duplicate pull was nonzero')
        for endpoint in self.devices:self.mode(endpoint,'OFF')
        stage['final_empty']=self.quiet(mark);transfers=stage['final_empty']['snapshots'][-1]['new_transfers'];ids=[r['id'] for r in transfers]
        if len(ids)!=len(set(ids)) or any(row['endpoint'] not in {e['id'] for e in self.devices} for row in transfers):raise ValueError('Duplicate/foreign phase business ID')
        deposits=[r for r in transfers if r['kind']=='DEPOSIT'];allocations=[r for r in transfers if r['kind']=='ALLOCATE']
        if not(len(deposits)==len(allocations)==3 and all(r['amount']==63 and r['remaining']==0 and r['state']=='COMMITTED' for r in deposits)
                and all(r['amount']==63 and r['remaining']==0 and r['state']=='CONSUMED' for r in allocations)):raise ValueError('Exactly three new committed deposits/consumed allocations required')
        self.fresh_business_ids(ids,stage)
        self.all_soak_sql(name+'_after_new_output')
        stage.update(business_ids=ids,passed=True,duplicate_output=0)
        held=self.prepare_positive(name+'_positive_to_next_config',outgoing_receiver) if outgoing_receiver is not None else None
        self.stop(name,flags,held);return held

    def run(self):
        if any(key in os.environ for key in ('CT_MYSQL_URL','CT_MYSQL_USER','CT_MYSQL_PASSWORD','CT_REDIS_URI','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')):raise ValueError('No backend/JVM environment overrides')
        self.round.mkdir(mode=0o700);self.stable={}
        with self.target.open('x') as output:json.dump(self.report,output)
        observer=(ROOT/'scratch/rc-normal-fallback-observer.lock').open('a')
        try:
            fcntl.flock(observer,fcntl.LOCK_EX|fcntl.LOCK_NB);self.guard_observer();self.acquire_stopped();self.files_gate(('true','true'));self.stopped_sql();self.probe_gate('completed_soak_before_any_restart');self.all_soak_sql('completed_soak_before_any_restart')
            remote=next(e for e in self.lane['sinks'] if e['server']=='B');local=next(e for e in self.lane['sinks'] if e['server']=='A')
            first=self.stage('fast_initial',('true','true'),outgoing_receiver=remote);self.switch('fast_to_legacy',('true','true'),('false','false'))
            second=self.stage('legacy',('false','false'),incoming=first,outgoing_receiver=local);self.switch('legacy_to_fast',('false','false'),('true','true'))
            if any(sha(self.configs[s])!=self.report['initial_config_snapshots'][s]['config_sha256'] for s in PORTS):raise ValueError('Exact original config bytes not restored')
            self.stage('fast_restored',('true','true'),incoming=second);self.files_gate(('true','true'))
            groups=self.report['stages']+self.report['positive_handoffs']
            if len(self.report['stages'])!=3 or len(self.report['positive_handoffs'])!=2 or any(not v['passed'] or v['accepted']!=189 or v['output']!=189 for v in groups):raise ValueError('Three empty stages and two positive handoffs must each preserve all189')
            self.report['native_totals']={'accepted_FE':sum(v['accepted'] for v in groups),'output_FE':sum(v['output'] for v in groups),'empty_stage_FE':567,'cross_config_positive_handoff_FE':378}
            self.report.update(passed=True,state='COMPLETE_FUNCTIONAL_PASS_AND_NORMAL_STOP',utc_end=utc())
        except BaseException as error:
            self.report['failures'].append(type(error).__name__+': '+str(error));self.report.update(state='FAILED_RETAINED',utc_end=utc())
            try:
                native, observers = processes()
                self.guard_evidence('Top-level failure: ' + type(error).__name__ + ': ' + str(error)[:1000], native, observers)
            except Exception as evidence_error:
                self.report['failure_process_evidence_error'] = type(evidence_error).__name__ + ': ' + str(evidence_error)[:1000]
            finally:
                # Foreign activity still forbids business/SQL work, but not one
                # independently verified normal stop of this controller's own JVM.
                self.retain_failed_children()
        finally:
            for handle in self.locks.values():handle.close()
            observer.close()
            try:self.save()
            except BaseException as error:
                self.report.update(passed=False,state='FAILED_EVIDENCE_FINALIZATION')
                self.report['failures'].append(type(error).__name__+': '+str(error))
                brief={'passed':False,'state':self.report['state'],'utc_end':utc(),'failures':self.report['failures'][-8:],
                    'main_report':str(self.target.relative_to(ROOT)),'current_configs_sha256':{s:sha(raw) for s,raw in self.configs.items()},
                    'stages':[{k:stage.get(k) for k in ('name','flags','accepted','output','per_receiver','native_events','business_ids','passed')} for stage in self.report['stages']],
                    'own_launcher_exits':{s:c.poll() for s,c in self.children.items()},'failure_policy':'Assets/current flags retained; no replay/refund/force kill.'}
                with (self.round/'failure-finalization.json').open('x') as output:json.dump(brief,output,indent=2)
        print(json.dumps({'report':str(self.target.relative_to(ROOT)),'passed':self.report['passed'],'state':self.report['state']}))
        return 0 if self.report['passed'] else 1


def self_test():
    class Tests(unittest.TestCase):
        def own_fixture(self):
            expected = {'argv': ['/repo/jdk/bin/java', '@/repo/frozen/serverARunVmArgs.txt'],
                'cwd': '/repo/run-A', 'exe': '/repo/jdk/bin/java', 'launcher': '/repo/frozen/runServerA.sh',
                'launcher_sha256': 'a' * 64, 'vm_args': '/repo/frozen/serverARunVmArgs.txt', 'vm_args_sha256': 'b' * 64}
            candidate = {'pid': 100, 'ppid': 90, 'start_ticks': 200, 'state': 'S',
                'argv': expected['argv'], 'cwd': expected['cwd'], 'exe': expected['exe'], 'argv_sha256': 'c' * 64}
            dummy = Fallback.__new__(Fallback)
            dummy.started = 0
            dummy.owners = {'A': {'anchor': {'pid': 100, 'start_ticks': 200}, 'expected': expected}}
            dummy.identities = {'A': {'pid': 1, 'session_id': 'prior-closed-session', 'fencing_epoch': 1}}
            dummy.children = {'A': type('Child', (), {'pid': 100, 'poll': lambda _: None})()}
            dummy.logs = {}
            dummy.stop_requested = set()
            dummy.report = {'events': [], 'passed': False}
            dummy.save = lambda: None
            dummy.launcher_identity = lambda _: expected
            return dummy, expected, candidate

        def test_late_exec_refreshes_ownership_without_reusing_old_soak_PID(self):
            dummy, expected, java = self.own_fixture()
            shell = dict(java, argv=['bash', expected['launcher']], exe='/usr/bin/bash', cwd='/repo')
            self.assertIsNone(owned_native_proof(shell, dummy.owners['A']['anchor'], expected))
            with patch.dict(globals(), {'processes': lambda: ([], [])}):
                dummy.guard_observer()
            self.assertEqual(dummy.identities['A']['pid'], 1)
            scan = [{'pid': java['pid'], 'argv_sha256': java['argv_sha256'], 'cwd': java['cwd']}]
            with patch.dict(globals(), {'processes': lambda: (scan, []),
                    'process_snapshot': lambda _: java, 'referenced': lambda _: None}):
                dummy.guard_observer()
            self.assertEqual(dummy.identities['A']['pid'], 100)
            self.assertEqual(owned_native_proof(java, dummy.owners['A']['anchor'], expected)['ancestor_chain'][0]['start_ticks'], 200)

        def test_reentrant_guard_keeps_live_identity_for_new_session_epoch_update(self):
            dummy, _, java = self.own_fixture()
            previous = boot_boundary(dummy.identities)
            identity = dummy.identities['A']  # restart's active for-loop reference
            scan = [{'pid': java['pid'], 'argv_sha256': java['argv_sha256'], 'cwd': java['cwd']}]
            with patch.dict(globals(), {'processes': lambda: (scan, []),
                    'process_snapshot': lambda _: java, 'referenced': lambda _: None}):
                dummy.guard_observer()  # Re-entered by ct_test pid inside restart.
                identity.update(session_id='fresh-boot-session', fencing_epoch=2)
                self.assertIs(dummy.identities['A'], identity)
                self.assertEqual(dummy.identities['A']['session_id'], 'fresh-boot-session')
                self.assertEqual(dummy.identities['A']['fencing_epoch'], 2)
                dummy.guard_observer()
                self.assertIs(dummy.identities['A'], identity)
                self.assertEqual((identity['pid'], identity['session_id'], identity['fencing_epoch']),
                                 (100, 'fresh-boot-session', 2))
            self.assertEqual(previous['A'], {'pid': 1, 'session_id': 'prior-closed-session', 'fencing_epoch': 1})
            self.assertNotEqual(identity['pid'], previous['A']['pid'])
            self.assertEqual(identity['fencing_epoch'], previous['A']['fencing_epoch'] + 1)

        def entrypoint_fixture(self):
            artifact = {'source_revision':'reviewed', 'main_sha256':'a'*64, 'jar_sha256':'b'*64}
            original = {s:{'pid':n,'session_id':'old-'+s,'fencing_epoch':1,'server_id':'own-'+s,
                'world_id':'world-'+s,'config_file_start_sha256':'c'*64} for n,s in enumerate(PORTS,1)}
            devices=[{'id':'ep-A','server':'A','expected_channel':'own-channel','x':4,'z':16}]
            captures={s:{'capture_complete':True,'capture_failure':None,'dropped_bytes':0,'sha256':'d'*64} for s in PORTS}
            stopped=[{'server':'own-'+s,'world':'world-'+s,'session':'new-'+s,'epoch':2,
                'status':'STOPPED','clean_stop':1,'lease_live':False} for s in PORTS]
            endpoint={'id':'ep-A','channel':'own-channel','server':'own-A','world':'world-A','owner':'owner',
                'state':'ACTIVE','x':4,'y':64,'z':16,'dimension':'minecraft:overworld'}
            data={'servers':stopped,'endpoints':[endpoint],'pool_rows':[],'allocation_summary':[]}
            failed={'passed':False,'state':'FAILED_RETAINED','stages':[],'config_switches':[],
                'failure_own_launcher_exits':{s:0 for s in PORTS},'failure_bounded_logs':captures,
                'source_revision':'reviewed','source_main_sha256':'a'*64,'mod_JAR_sha256':'b'*64,
                'initial_config_snapshots':{s:{'config_sha256':'c'*64} for s in PORTS},
                'boots':[{'SQL':{'servers':stopped},'identity':{s:{'pid':n+100} for n,s in enumerate(PORTS,1)}}]}
            closure={'actual_CLI_exit_code':1,'actual_original_Popen_launcher_exits':{s:0 for s in PORTS},
                'all_four_launch_and_own_observer_locks_free':True,'remaining_native':[], 'remaining_observers':[],
                'remaining_java_javac_jstat':[],'new_native_input':0,'stages':[],'config_switches':[], 'actual_log_capture':captures}
            audit={'mysql_exit':0,'passed_poststop_audit':True,'new_input':0,'config_switches':0,'SQL_mutations':False,'WAL_read_write':False,
                'SQL_scope':{'cluster':'dev_three_v1','endpoint_IDs':['ep-A'],'channel_IDs':['own-channel'],'server_IDs':['own-'+s for s in PORTS]},
                'SQL':data,'raw_stdout':json.dumps(data)}
            return original,failed,closure,audit,devices,'owner',artifact

        def test_explicit_closed_entrypoint_only_adopts_the_proven_zero_input_boot(self):
            values=self.entrypoint_fixture();adopted=closed_entrypoint(*values)
            self.assertEqual({r['fencing_epoch'] for r in adopted.values()},{2})
            self.assertEqual(values[0]['A']['fencing_epoch'],1)
            for field,changed in [('stages',[{'accepted':1}]),('config_switches',[{}]),('failure_own_launcher_exits',{'A':0}),('mod_JAR_sha256','other')]:
                x=list(self.entrypoint_fixture());x[1]=dict(x[1],**{field:changed})
                with self.assertRaises(ValueError):closed_entrypoint(*x)
            x=list(self.entrypoint_fixture());x[1]['initial_config_snapshots']['A']['config_sha256']='changed'
            with self.assertRaises(ValueError):closed_entrypoint(*x)
            for key,value in [('owner','other'),('world','other'),('channel','other')]:
                x=list(self.entrypoint_fixture());x[3]['SQL']['endpoints'][0][key]=value;x[3]['raw_stdout']=json.dumps(x[3]['SQL'])
                with self.assertRaises(ValueError):closed_entrypoint(*x)
            for mutation in ('positive','latest_epoch','unclean','wrong_scope'):
                x=list(self.entrypoint_fixture())
                if mutation=='positive':x[3]['SQL']['pool_rows']=[{'amount':1}]
                if mutation=='latest_epoch':x[3]['SQL']['servers'][0]['epoch']=3
                if mutation=='unclean':x[3]['SQL']['servers'][0]['clean_stop']=0
                if mutation=='wrong_scope':x[3]['SQL_scope']['endpoint_IDs']=['other']
                x[3]['raw_stdout']=json.dumps(x[3]['SQL'])
                with self.assertRaises(ValueError):closed_entrypoint(*x)

        def test_entrypoint_actual_hash_chain_preserves_original_records_and_rejects_cross_binding(self):
            values=self.entrypoint_fixture();original,failed,closure,audit,devices,owner,artifact=values
            with tempfile.TemporaryDirectory(prefix='entrypoint-offline-',dir=ROOT/'reports/rc-20261017') as folder:
                directory=Path(folder)
                def write(name,body):
                    target=directory/name;target.write_text(json.dumps(body));return metadata(target)
                full=write('full.json',{});manifest=write('runtime.json',{});raw=write('raw.json',{})
                failed.update(completion=full,runtime_manifest=manifest,soak_raw=raw)
                fail=write('failed.json',failed);closure['failed_report']=fail;audit['failed_report']=fail
                close=write('closure.json',closure);sql=write('sql.json',audit)
                chain={'kind':'explicit_closed_zero_input_failed_fallback_entrypoint','full_controller':full,'runtime_manifest':manifest,'soak_raw':raw,'failed_attempt':fail,'closure':close,'poststop_SQL_audit':sql}
                point=write('entrypoint.json',chain);before={p.name:p.read_bytes() for p in directory.iterdir()}
                dummy=Fallback.__new__(Fallback);dummy.completion_path=directory/'full.json';dummy.manifest_path=directory/'runtime.json';dummy.soak_path=directory/'raw.json'
                dummy.identities=original;dummy.artifact=artifact;dummy.all_devices=devices;dummy.owner=owner;dummy.inputs={};dummy.report={}
                dummy.adopt_entrypoint(directory/'entrypoint.json')
                self.assertEqual(dummy.identities['A']['fencing_epoch'],2)
                self.assertEqual(dummy.report['explicit_initial_entrypoint']['original_full_boot']['A']['fencing_epoch'],1)
                self.assertEqual(before,{p.name:p.read_bytes() for p in directory.iterdir()})
                closure['failed_report']=dict(fail,sha256='0'*64);chain['closure']=write('closure.json',closure);write('entrypoint.json',chain)
                with self.assertRaises(ValueError):dummy.adopt_entrypoint(directory/'entrypoint.json')

        def positive_fixture(self):
            rows=[{'id':'d128','kind':'DEPOSIT','amount':128,'remaining':0,'state':'COMMITTED','endpoint':'source'},
                  {'id':'d61','kind':'DEPOSIT','amount':61,'remaining':0,'state':'COMMITTED','endpoint':'source'},
                  {'id':'a128','kind':'ALLOCATE','amount':128,'remaining':75,'state':'LOCAL','endpoint':'sink'}]
            local=lambda n:{'registered':True,'pause':'','txFE':0,'rxFE':n,'txItem':0,'rxItem':0,'txFluid':0,'rxFluid':0}
            return {'pool':61,'owned':75,'quarantined':0,'stopped':False,'new_transfers':rows,
                'local':{'source':local(0),'sink':local(75)},'endpoints':[{'id':v,'checkpoint':8} for v in ('source','sink')],
                'WAL':{'source':{'deposits':[],'credits':[],'revision':8},
                    'sink':{'deposits':[],'revision':8,'credits':[{'transaction':'a128','channel':'own','original':128,'remaining':75},
                        {'transaction':'old-zero','channel':'own','original':32,'remaining':0}]}}}

        def test_positive_pool_and_partial_credit_require_conservation_exact_WAL_and_original_IDs(self):
            frame=self.positive_fixture();self.assertTrue(positive_state(frame,189,53,61,75,1,'own'))
            held={'held_transfers':sorted(frame['new_transfers'],key=lambda r:r['id'])};dummy=Fallback.__new__(Fallback);dummy.channel='own'
            self.assertTrue(dummy.held_positive(held,frame))
            for change in ('pool','remaining','ID','checkpoint'):
                altered=json.loads(json.dumps(frame))
                if change=='pool':altered['pool']=60
                if change=='remaining':altered['WAL']['sink']['credits'][0]['remaining']=76
                if change=='ID':altered['WAL']['sink']['credits'][0]['transaction']='replacement'
                if change=='checkpoint':altered['endpoints'][1]['checkpoint']=7
                self.assertFalse(positive_state(altered,189,53,61,75,1,'own'))
            changed=json.loads(json.dumps(frame));changed['new_transfers'][0]['id']='new-deposit-ID'
            with self.assertRaises(ValueError):dummy.held_positive(held,changed)
            stopped=dict(frame,stopped=True,local={})
            self.assertTrue(positive_state(stopped,189,53,61,75,1,'own'))
            self.assertTrue(positive_state(frame,189,53,61,75,1,'own'))

        def test_positive_handoff_orchestration_holds_original_IDs_OFF_then_serves_both_receivers(self):
            dummy=Fallback.__new__(Fallback);dummy.started=0;dummy.args=argparse.Namespace(timeout=120,poll=.2,quiet=2.2)
            source={'id':'source','server':'A','x':4,'z':16};local={'id':'local','server':'A','x':68,'z':16};remote={'id':'remote','server':'B','x':132,'z':16}
            dummy.devices=[source,local,remote];dummy.lane={'sources':[source],'sinks':[local,remote]};dummy.channel='own'
            dummy.report={'events':[],'stages':[],'positive_handoffs':[]};dummy.save=lambda:None
            dummy.pure=load('rc_positive_offline_helpers','optimization-restart-fallback-test.py')
            modes={v['id']:'OFF' for v in dummy.devices};model={'pool':0,'rows':[],'inputs':0,'outputs':0};actions=[];clock=[0.0]
            def allocate():
                available=[v for v in (local,remote) if modes[v['id']]=='RECEIVE']
                if model['pool'] and available:
                    amount=model['pool'];model['pool']=0
                    model['rows'].append({'id':'a'+str(amount),'kind':'ALLOCATE','endpoint':available[0]['id'],'amount':amount,'remaining':amount,'state':'LOCAL'})
            def mode(endpoint,value):
                modes[endpoint['id']]=value;actions.append(('mode',endpoint['id'],value,clock[0]));allocate()
            def issue(server,command):
                _,verb,x,z,amount=command.split();amount=int(amount);endpoint=next(v for v in dummy.devices if (v['server'],v['x'],v['z'])==(server,int(x),int(z)))
                if verb=='push-fe':
                    self.assertEqual(endpoint['id'],'source');self.assertEqual(modes['source'],'SEND')
                    model['inputs']+=amount;model['pool']+=amount;model['rows'].append({'id':'d'+str(amount),'kind':'DEPOSIT','endpoint':'source','amount':amount,'remaining':0,'state':'COMMITTED'});allocate();actual=amount;reply='ACCEPTED '
                else:
                    actual=0
                    if modes[endpoint['id']]=='RECEIVE':
                        for row in model['rows']:
                            if row['kind']=='ALLOCATE' and row['endpoint']==endpoint['id']:
                                taken=min(amount-actual,row['remaining']);row['remaining']-=taken;actual+=taken
                                row['state']='LOCAL' if row['remaining'] else 'CONSUMED'
                    model['outputs']+=actual;reply='EXTRACTED '
                actions.append((verb,endpoint['id'],actual,clock[0]));return reply+str(actual)
            def snapshot(_):
                allocations=[v for v in model['rows'] if v['kind']=='ALLOCATE'];buffers={};wal={}
                for ep in dummy.devices:
                    owned=[v for v in allocations if v['endpoint']==ep['id']]
                    buffers[ep['id']]={'registered':True,'pause':'','txFE':0,'rxFE':sum(v['remaining'] for v in owned),'txItem':0,'rxItem':0,'txFluid':0,'rxFluid':0}
                    wal[ep['id']]={'revision':8,'deposits':[],'credits':[{'transaction':v['id'],'channel':'own','original':v['amount'],'remaining':v['remaining']} for v in owned]}
                frame={'db_time':'2026-10-17 00:00:00.000000','pool':model['pool'],'owned':sum(v['remaining'] for v in allocations),'quarantined':0,'stopped':False,'source_endpoint':'source','new_transfers':model['rows'],'endpoints':[{'id':v['id'],'checkpoint':8} for v in dummy.devices],'local':buffers,'WAL':wal,'demands':[{'endpoint':v['id'],'live':modes[v['id']]=='RECEIVE','room':1000 if modes[v['id']]=='RECEIVE' else 0} for v in (local,remote)]}
                return json.loads(json.dumps(frame))
            dummy.snapshot=snapshot;dummy.mode=mode;dummy.issue=issue;dummy.read_mode=lambda ep,_:modes[ep['id']]
            dummy.quiet=lambda mark:{'passed':True,'snapshots':[snapshot(mark)]}
            dummy.all_soak_sql=lambda *args:None
            with patch('time.monotonic',side_effect=lambda:clock[0]),patch('time.sleep',side_effect=lambda value:clock.__setitem__(0,clock[0]+value)):
                held=dummy.prepare_positive('offline-carry',remote)
                self.assertEqual((model['inputs'],model['outputs'],model['pool']),(189,53,61))
                self.assertEqual({modes[v['id']] for v in dummy.devices},{'OFF'})
                self.assertGreaterEqual(held['actual_OFF_TTL_wait_seconds'],6.2)
                original=json.loads(json.dumps(held['held_transfers']))
                dummy.recover_positive(held,'restored-profile')
            self.assertEqual((model['inputs'],model['outputs'],model['pool']),(189,189,0))
            self.assertEqual(held['per_receiver'],{'local':61,'remote':128})
            self.assertEqual([v[2] for v in actions if v[0]=='push-fe'],[128,61])
            self.assertEqual(held['held_transfers'],original)
            self.assertEqual(len(held['business_ids']),4);self.assertTrue(held['passed'])
            pulls=[v for v in actions if v[0]=='pull-fe']
            self.assertEqual([v[2] for v in pulls[:3]],[53,0,0])

        def test_missing_proc_children_falls_back_to_bounded_PPIDs_and_rechecks_ancestry(self):
            dummy, expected, java = self.own_fixture()
            parent = dict(java, argv=['bash', expected['launcher']], exe='/usr/bin/bash', cwd='/repo')
            child = dict(java, pid=101, ppid=100, start_ticks=202)
            foreign = dict(java, pid=300, ppid=1, start_ticks=250)
            snapshots = {100: parent, 101: child, 300: foreign}
            tree = owned_tree
            with tempfile.TemporaryDirectory(prefix='rc-fallback-proc-offline-', dir=ROOT / 'scratch') as folder:
                directory = Path(folder)
                for pid, snapshot in snapshots.items():
                    selected = directory / str(pid)
                    selected.mkdir()
                    (selected / 'stat').write_text(str(pid) + ' (synthetic) S ' + str(snapshot['ppid']) + '\n')
                self.assertFalse((directory / '100/task/100/children').exists())
                with patch.dict(globals(), {'process_snapshot': lambda pid: snapshots.get(pid)}):
                    found = tree(dummy.owners['A']['anchor'], proc_root=directory)
                    self.assertEqual({p['pid'] for p in found}, {100, 101})
                    with patch.dict(globals(), {'owned_tree': lambda anchor: tree(anchor, proc_root=directory)}):
                        proof = dummy.verified_stop_candidate('A')
                self.assertEqual(proof['pid'], 101)
                self.assertEqual([p['pid'] for p in proof['ancestor_chain']], [101, 100])

        def test_same_arguments_without_own_ancestor_or_with_reused_PID_are_rejected(self):
            dummy, expected, java = self.own_fixture()
            foreign = dict(java, pid=300, ppid=1)
            self.assertIsNone(owned_native_proof(foreign, dummy.owners['A']['anchor'], expected))
            self.assertIsNone(owned_native_proof(dict(java, start_ticks=201), dummy.owners['A']['anchor'], expected))
            descendant = dict(java, pid=101, ppid=100, start_ticks=202)
            parent = dict(java, argv=['bash', expected['launcher']], exe='/usr/bin/bash')
            proof = owned_native_proof(descendant, dummy.owners['A']['anchor'], expected, reader=lambda _: parent)
            self.assertEqual([p['pid'] for p in proof['ancestor_chain']], [101, 100])
            with patch.dict(globals(), {'owned_tree': lambda _: [foreign]}):
                self.assertIsNone(dummy.verified_stop_candidate('A'))

        def test_foreign_guard_failure_still_allows_exactly_one_verified_own_stop(self):
            dummy, expected, java = self.own_fixture()
            foreign = dict(java, pid=300, ppid=1)
            scan = [{'pid': 300, 'argv_sha256': foreign['argv_sha256'], 'cwd': foreign['cwd']}]
            with patch.dict(globals(), {'processes': lambda: (scan, []),
                    'process_snapshot': lambda _: foreign, 'referenced': lambda _: None}):
                with self.assertRaises(ValueError):dummy.guard_observer()
            evidence = dummy.report['process_guard_evidence'][-1]
            self.assertEqual(evidence['native'][0]['pid'], 300)
            self.assertEqual(evidence['Popen_roots']['A'], {'pid': 100, 'start_ticks': 200})
            self.assertNotIn('argv', evidence['native'][0])
            calls = []
            def command(port, text, timeout):
                calls.append(text)
                if len(calls) == 1:raise ConnectionRefusedError('own RCON not ready')
                if text == 'ct_test pid':return 'PID 100'
                raise ConnectionError('uncertain stop response')
            dummy.base = type('Base', (), {'command': staticmethod(command)})()
            with patch.dict(globals(), {'owned_tree': lambda _: [java],
                    'processes': lambda: (_ for _ in ()).throw(AssertionError('cleanup must not call global scanner'))}):
                self.assertFalse(dummy.request_owned_normal_stop('A'))
                self.assertTrue(dummy.request_owned_normal_stop('A'))
                self.assertTrue(dummy.request_owned_normal_stop('A'))
            self.assertEqual(calls, ['ct_test pid', 'ct_test pid', 'stop'])
            self.assertEqual(dummy.report['events'][-1]['outcome'], 'UNKNOWN_NO_REPLAY')
            self.assertEqual(len(dummy.stop_requested), 1)

        def test_failed_cleanup_retains_handles_past_deadline_until_actual_exit(self):
            dummy, _, _ = self.own_fixture()
            clock = [0.0]
            dummy.args = argparse.Namespace(timeout=1, poll=.2)
            dummy.target = ROOT / 'reports/rc-20261017/offline-not-created.json'
            dummy.children = {'A': type('Child', (), {'poll': lambda _: 0 if clock[0] >= 1.6 else None})()}
            states, finished = [], []
            dummy.save = lambda: states.append(dummy.report.get('state'))
            dummy.request_owned_normal_stop = lambda _: True
            dummy.logs = {'A': type('Log', (), {'thread': type('Thread', (), {'is_alive': lambda _: clock[0] < 1.6})(),
                'finish': lambda _: finished.append(clock[0]) or {'capture_complete': True}})()}
            with patch('time.monotonic', side_effect=lambda: clock[0]), patch('time.sleep',
                    side_effect=lambda n: clock.__setitem__(0, clock[0] + n)), patch('builtins.print'):
                dummy.retain_failed_children()
            self.assertIn('FAILED_RETAINED_CLEANUP_PENDING', states)
            self.assertGreaterEqual(finished[0], 1.6)
            self.assertEqual(dummy.report['failure_own_launcher_exits'], {'A': 0})
            self.assertFalse(dummy.report['passed'])

        def test_default_has_no_process_socket_config_or_SQL_effect(self):
            with patch('subprocess.Popen',side_effect=AssertionError('process')),patch('socket.socket',side_effect=AssertionError('socket')):
                self.assertEqual(main([]),0)
        def test_artifact_allowlist_requires_the_exact_revision_JAR_and_main_tuple(self):
            old, new = list(REVIEWED_ARTIFACTS)
            for revision in (old, new):
                expected = REVIEWED_ARTIFACTS[revision]
                self.assertEqual(reviewed_artifact(revision, expected['jar_sha256'])['main_sha256'], expected['main_sha256'])
            with self.assertRaises(ValueError):reviewed_artifact(new[:7], REVIEWED_ARTIFACTS[new]['jar_sha256'])
            with self.assertRaises(ValueError):reviewed_artifact('f' * 40, REVIEWED_ARTIFACTS[new]['jar_sha256'])
            with self.assertRaises(ValueError):reviewed_artifact(new, REVIEWED_ARTIFACTS[old]['jar_sha256'])
            with self.assertRaises(ValueError):reviewed_artifact(old, REVIEWED_ARTIFACTS[new]['jar_sha256'])
        def test_full_controller_gate_never_promotes_partial_failed_or_smoke(self):
            item={'passed':True,'functional_passed':True,'qualified_passed':True,'sixty_minute_gate':True,'kind':'full','requested_observation_seconds':3600,'workload_exit':0,'utc_end':'closed','state':'COMPLETE','all_own_launchers_exited_and_locks_free':True,'source_before':{'matches_expected':True},'source_after_workload':{'matches_expected':True},'source_after_stop':{'matches_expected':True},'own_launcher_exits':{s:{'exit_code':0} for s in PORTS}}
            self.assertEqual(set(completed_controller(item)),set(PORTS))
            for key,value in (('passed',False),('kind','smoke'),('sixty_minute_gate',False),('utc_end',None),('workload_exit',1),('own_launcher_exits',{})):
                with self.assertRaises(ValueError):completed_controller(dict(item,**{key:value}))
        def test_only_flags_roundtrip_exact_bytes_and_unknown_assets_are_not_zero(self):
            pure=load('rc_fallback_offline_pure','optimization-restart-fallback-test.py')
            data=b'# preserved\r\ntransfer.channelBatches=true\r\ntransfer.localFastPath=true\r\nbuffers.fe=2000000\r\n'
            changed=pure.flag_rewrite(data,('true','true'),('false','false'))
            self.assertEqual(pure.flag_rewrite(changed,('false','false'),('true','true')),data)
            empty={'pool':0,'owned':0,'quarantined':0,'local':{},'WAL':{}}
            self.assertTrue(Fallback.zero(empty));self.assertFalse(Fallback.zero(dict(empty,owned=128)))
        def test_initial_snapshot_requires_exact_soak_start_bytes_without_inventing_end_SHA(self):
            raw=b'transfer.channelBatches=true\ntransfer.localFastPath=true\nbuffers.fe=2000000\n'
            identity={'config_file_start_sha256':sha(raw)}
            verify_initial_config(raw,identity)
            self.assertNotIn('config_file_end_sha256',identity)
            changed=raw.replace(b'2000000',b'2000001')
            with self.assertRaises(ValueError):verify_initial_config(changed,identity)
            with self.assertRaises(ValueError):verify_initial_config(raw,{})
        def test_source_paths_reject_external_and_parent_traversal(self):
            with self.assertRaises(ValueError):path('/tmp/foreign-report.json')
            with self.assertRaises(ValueError):path('scratch/../run-A/cross-tesseract.properties')
            self.assertEqual((63+63+63),189)
        def test_quiet_retains_checkpoint_skew_and_restarts_a_bounded_true_guard(self):
            endpoint='original';local={'registered':True,'pause':'','txFE':0,'rxFE':0,'txItem':0,'rxItem':0,'txFluid':0,'rxFluid':0}
            empty={'pool':0,'owned':0,'quarantined':0,'local':{endpoint:local},'WAL':{endpoint:{'deposits':[],'credits':[],'revision':8}},'endpoints':[{'id':endpoint,'checkpoint':8}]}
            skew=dict(empty,endpoints=[{'id':endpoint,'checkpoint':7}]);positive=dict(empty,owned=128)
            selected=[positive,empty,skew];clock=[0.0];seen=[]
            dummy=Fallback.__new__(Fallback);dummy.args=argparse.Namespace(timeout=10,poll=.2,quiet=2.2)
            def snapshot(_):
                row=selected.pop(0) if selected else empty;seen.append(row);return row
            dummy.snapshot=snapshot
            with patch('time.monotonic',side_effect=lambda:clock[0]),patch('time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
                result=dummy.quiet('unused')
            self.assertTrue(result['passed']);self.assertGreaterEqual(result['quiet_seconds'],2.2)
            self.assertIs(result['snapshots'][2],skew);self.assertEqual(skew['endpoints'][0]['checkpoint'],7)
            dummy.snapshot=lambda _:positive;clock[0]=0;dummy.args.timeout=1
            with patch('time.monotonic',side_effect=lambda:clock[0]),patch('time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
                with self.assertRaises(TimeoutError):dummy.quiet('unused')
        def test_probe_guard_preserves_old_stop_and_reports_and_rejects_start(self):
            with tempfile.TemporaryDirectory(prefix='rc-fallback-offline-',dir=ROOT/'scratch') as folder:
                directory=Path(folder);output=directory/'output';output.mkdir();token=str(uuid.uuid4())
                control=directory/'control.txt';control.write_text('stop '+token+'\n')
                sealed=output/(token+'.json');body={'token':token,'window_closed':True};sealed.write_text(json.dumps(body))
                vm=directory/'vm.txt';vm.write_text('-javaagent:'+str(directory/'agent.jar')+'='+str(control)+';'+str(output))
                agent=directory/'agent.json';agent.write_text(json.dumps({'recorder_revision':'v2_mod_roots','sources':PROBE_SOURCES,'artifacts':[]}))
                dummy=Fallback.__new__(Fallback);dummy.probe_files=None;dummy.report={'probe_file_checks':[]}
                dummy.seal={'probe_manifest':str(agent),'probe_manifest_sha256':sha(agent.read_bytes()),'launches':{s:{'control':str(control),'output':str(output),'vm_args':str(vm)} for s in PORTS}}
                dummy.soak={'probe_window_measurement_status':'MEASURED_FIXED_AND_FULL','probe_full_lifecycle':{s:{'source':metadata(sealed),'data':body} for s in PORTS}}
                before=control.read_bytes(),sealed.read_bytes();dummy.probe_gate('before');dummy.probe_gate('after')
                self.assertEqual(before,(control.read_bytes(),sealed.read_bytes()))
                control.write_text('start '+token+'\n')
                with self.assertRaises(ValueError):dummy.probe_gate('unsafe_start')
        def test_owned_stdout_drain_retains_only_bounded_prefix_and_counts_discarded_bytes(self):
            with tempfile.TemporaryDirectory(prefix='rc-fallback-offline-',dir=ROOT/'scratch') as folder,patch.dict(globals(),{'MAX_LOG':128}):
                target=Path(folder)/'native.log';capture=BoundedLog(io.BytesIO(b'x'*300),target);result=capture.finish()
                self.assertTrue(result['capture_complete']);self.assertIsNone(result['capture_failure'])
                self.assertEqual((result['seen_bytes'],result['retained_bytes'],result['dropped_bytes']),(300,128,172))
                self.assertEqual(target.stat().st_size,128)
        def test_other_soak_channel_positive_SQL_or_quota_change_blocks_the_whole_cohort(self):
            source,other,world,owner=(str(uuid.uuid4()) for _ in range(4));ids=[str(uuid.uuid4()),str(uuid.uuid4())]
            dummy=Fallback.__new__(Fallback);dummy.owner=owner;dummy.quota=None;dummy.report={'all_soak_SQL_checks':[]}
            dummy.all_devices=[{'expected_channel':channel,'id':endpoint,'server':'A'} for channel,endpoint in zip((source,other),ids)]
            dummy.identities={'A':{'world_id':world,'server_id':'own-A'}}
            rows=[{'id':endpoint,'channel':channel,'owner':owner,'server':'own-A','world':world,'state':'ACTIVE'} for endpoint,channel in zip(ids,(source,other))]
            data={'endpoints':rows,'pool_rows':[{'channel':other,'amount':1}],'allocation_rows':[],'grants':[],'quota_limit':2,'policy_version':1}
            dummy.sql=lambda _:data
            with self.assertRaises(ValueError):dummy.all_soak_sql('other_positive_pool')
            data['pool_rows'][0]['amount']=0;data['allocation_rows']=[{'channel':other,'remaining':128}]
            with self.assertRaises(ValueError):dummy.all_soak_sql('other_positive_remaining')
            data['allocation_rows']=[];dummy.all_soak_sql('empty_baseline')
            data['grants']=[{'endpoint':ids[1],'desired':1}]
            with self.assertRaises(ValueError):dummy.all_soak_sql('quota_changed')
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    print(json.dumps({'execution':'OFFLINE_SELF_TEST','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'native_SQL_config_lifecycle':'NOT_RUN'}))
    return 0 if result.wasSuccessful() else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group();mode.add_argument('--execute',action='store_true');mode.add_argument('--self-test',action='store_true')
    parser.add_argument('--completion',type=Path);parser.add_argument('--manifest',type=Path);parser.add_argument('--entrypoint-audit',type=Path,help='Explicit hash-bound closed zero-input failed-boot chain; never adopt arbitrary latest SQL epoch');parser.add_argument('--label');parser.add_argument('--timeout',type=float,default=120);parser.add_argument('--poll',type=float,default=.2);parser.add_argument('--quiet',type=float,default=2.2)
    args=parser.parse_args(argv)
    if args.self_test:return self_test()
    if not args.execute:
        print(json.dumps({'execution':'NOT_RUN','requires':'--execute --completion CLOSED_FULL_SOAK_CONTROLLER --manifest SAME_FROZEN_RUNTIME --label NEW_RC_LABEL; explicit root release after the full soak'}));return 0
    if not args.completion or not args.manifest or not args.label or not re.fullmatch(r'rc-[a-z0-9-]{1,24}',args.label) or not 60<=args.timeout<=180 or not .1<=args.poll<=1 or not 2.2<=args.quiet<=5:
        parser.error('Explicit completed full soak/final manifest/new safe RC label and bounded state limits required')
    try:return Fallback(args).run()
    except Exception as error:
        print(json.dumps({'passed':False,'execution':'PREFLIGHT_REJECTED','failure':type(error).__name__+': '+str(error)}));return 1


if __name__=='__main__':sys.exit(main())
