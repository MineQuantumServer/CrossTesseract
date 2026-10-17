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
REVISION = "3647dede64cfc23e054dfa962fd127787cae14ec"
MAIN_SHA = "998b3fc31ae9fd813f5f916a345240451d476283a9b05672b1bcc6c80cf89504"
JAR_SHA = "1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f"
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


class BoundedLog:
    """Drain owned stdout continuously; retain a bounded prefix, never block a JVM on a full log."""
    def __init__(self, stream, target):
        self.stream, self.target, self.seen, self.kept, self.failure = stream, target, 0, 0, None
        self.thread=threading.Thread(target=self.collect,daemon=True);self.thread.start()

    def collect(self):
        try:
            with self.target.open('xb') as output:
                while chunk:=self.stream.read(32768):
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
        if referenced(controller["runtime_manifest"]) != self.manifest_path or self.seal["source_revision"] != REVISION:
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
            "soak_raw": metadata(self.soak_path), "source_main_sha256": MAIN_SHA, "mod_JAR_sha256": JAR_SHA,
            "source_revision": REVISION, "own_existing_lane": self.lane, "inputs": list(self.inputs.values()),
            "stages": [], "boots": [], "normal_stops": [], "config_switches": [], "events": [], "failures": [],
            "all_soak_SQL_checks": [], "probe_file_checks": [],
            "scope": "Same completed-soak worlds and existing endpoint IDs. Three new63FE native inputs per stage (189), two mixed same/cross-server native receivers. Normal stops only; no positive-asset crash, disk power loss or performance claim.",
            "accounting": "Native accepted/extracted plus SQL ownership; SQL/WAL/local are separate mirrors, never added. Phase database-clock watermark and exact new business IDs exclude prior soak transfers.",
            "failure_policy": "Retain all files/assets/current flags; do not replay an uncertain native command, refund, clean SQL, restore flags, force kill or restart a failed stage. A verified own JVM may receive one normal stop only.",
            "historical_fixtures_accessed": False, "SQL_mutations": False}

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

    def guard_observer(self, stopping=False):
        native, observers = processes()
        if observers:
            raise ValueError("Another local observer/build/controller remains active")
        own = {i["pid"] for i in self.identities.values()}
        if any(r["pid"] not in own for r in native):
            raise ValueError("An unrelated native JVM is active")
        if not stopping and any(log.seen>MAX_LOG or log.failure for log in self.logs.values()):
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
        if actual!=MAIN_SHA or self.seal["artifacts"]["JAR"]["sha256"]!=JAR_SHA:
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
                    raise ValueError("Actual frozen mod classes differ from the final1ae JAR")
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

    def all_soak_sql(self, name):
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
        if any(r['amount']!=0 for r in data['pool_rows']) or any(r['remaining']!=0 for r in data['allocation_rows']):
            raise ValueError('Another original soak channel has a positive SQL asset; do not consume or replay it')
        persistent={'quota_limit':data['quota_limit'],'policy_version':data['policy_version'],'grant_count':len(data['grants']),
            'desired_grant_count':sum(r['desired'] for r in data['grants']),'grants':sorted(data['grants'],key=lambda r:r['endpoint'])}
        if self.quota is None:self.quota=persistent
        elif persistent!=self.quota:raise ValueError('Original soak persistent quota/grant count or identity changed')
        self.report['all_soak_SQL_checks'].append({'name':name,'utc':utc(),'SQL':data,'persistent_quota':persistent,
            'all_resource_pool_zero':True,'all_resource_allocation_remaining_zero':True,
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
        old=dict(self.identities)
        for h in self.locks.values():h.close()
        self.locks={};self.children={};self.logs={}
        for server in PORTS:
            launch=self.seal['launches'][server]['launcher'];log=self.round/(stage+'-'+server+'.log')
            self.children[server]=subprocess.Popen(['bash',str(ROOT/'scripts/start-frozen-dev.sh'),server,launch],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            self.logs[server]=BoundedLog(self.children[server].stdout,log)
        def ready():
            for server,child in self.children.items():
                if child.poll() is not None:raise ValueError('Own launcher exited before ready: '+server)
            # Initial identities still name exited soak PIDs; read-only startup probes
            # are allowed only against this round's exact started frozen VM argfiles.
            now=processes()[0];allowed=[]
            for proc in now:
                argv=Path(f"/proc/{proc['pid']}/cmdline").read_bytes().split(b'\0')
                server=next((s for s in PORTS if ('@'+self.seal['launches'][s]['vm_args']).encode() in argv),None)
                if server is None:raise ValueError('Unrelated JVM during startup')
                self.identities[server]=dict(old[server],pid=proc['pid']);allowed.append(server)
            if len(set(allowed))!=3:return False
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

    def stop(self, stage, flags):
        self.files_gate(flags);self.guard_observer()
        for server in PORTS:
            key=(server,self.identities[server]['session_id'])
            if self.children.get(server) and self.children[server].poll() is None and key not in self.stop_requested:
                self.stop_requested.add(key)
                try:self.issue(server,'stop')
                except OSError:pass  # One normal stop request only; never replay a closed reply.
        self.wait(lambda:all(c.poll() is not None for c in self.children.values()),bool)
        exits={s:c.returncode for s,c in self.children.items()}
        if len(exits)!=3 or any(code!=0 for code in exits.values()):raise ValueError('Actual own launcher exit0 required')
        logs={s:log.finish() for s,log in self.logs.items()}
        self.report['normal_stops'].append({'stage':stage,'launcher_exit_codes':exits,'logs':logs,'utc':utc()});self.save()
        if any(not r['capture_complete'] or r['capture_failure'] or r['dropped_bytes'] for r in logs.values()):raise ValueError('Bounded native log capture failed/truncated')
        if any('RC_PROBE_CONTROL_FAILURE' in log.target.read_text(errors='replace') for log in self.logs.values()):raise ValueError('Restarted probe rejected old control state')
        self.acquire_stopped();data=self.stopped_sql();self.report['normal_stops'][-1]['SQL']=data
        self.probe_gate(stage+'_after_normal_stop');self.all_soak_sql(stage+'_stopped');self.save()

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

    def snapshot(self, watermark):
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
            local[endpoint['id']]=self.inspect(endpoint)
            if local[endpoint['id']] is None:raise ValueError('Confirmed original endpoint disappeared during observation')
            selected=ROOT/('run-'+endpoint['server'])/identity['level_name']/'cross_tesseract/journal'/(endpoint['id']+'.ctj')
            current=self.pure.decode_fe_wal(path(selected).read_bytes())
            if (current['endpoint'],current['world'],current['generation'])!=(endpoint['id'],identity['world_id'],row['generation']):raise ValueError('Owned WAL identity differs')
            wal[endpoint['id']]=current
        result.update(local=local,WAL=wal);self.event('owned_SQL_local_WAL_frame',value=result);return result

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

    def stage(self, name, flags):
        self.restart(name,flags)
        for endpoint in self.all_devices:
            self.wait(lambda e=endpoint:self.inspect(e),lambda p:p is not None and p['registered'] and not p['pause'] and p['channel']==endpoint['expected_channel'])
            if any(self.inspect(endpoint)[k] for k in ('txFE','rxFE','txItem','rxItem','txFluid','rxFluid')):raise ValueError('Prior-soak local asset is not empty; do not consume it')
            if any(self.read_mode(endpoint,kind)!='OFF' for kind in (FE,'cross_tesseract:item','cross_tesseract:fluid')):
                raise ValueError('All original soak resource modes must remain persisted OFF before new phase input')
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
        prior={value for old in self.report['stages'][:-1] for value in old.get('business_ids',[])}
        if set(ids)&prior:raise ValueError('A previous stage business ID was reused')
        self.all_soak_sql(name+'_after_new_output')
        stage.update(business_ids=ids,passed=True,duplicate_output=0);self.stop(name,flags)

    def run(self):
        if any(key in os.environ for key in ('CT_MYSQL_URL','CT_MYSQL_USER','CT_MYSQL_PASSWORD','CT_REDIS_URI','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')):raise ValueError('No backend/JVM environment overrides')
        self.round.mkdir(mode=0o700);self.stable={}
        with self.target.open('x') as output:json.dump(self.report,output)
        observer=(ROOT/'scratch/rc-normal-fallback-observer.lock').open('a')
        try:
            fcntl.flock(observer,fcntl.LOCK_EX|fcntl.LOCK_NB);self.guard_observer();self.acquire_stopped();self.files_gate(('true','true'));self.stopped_sql();self.probe_gate('completed_soak_before_any_restart');self.all_soak_sql('completed_soak_before_any_restart')
            self.stage('fast_initial',('true','true'));self.switch('fast_to_legacy',('true','true'),('false','false'))
            self.stage('legacy',('false','false'));self.switch('legacy_to_fast',('false','false'),('true','true'))
            if any(sha(self.configs[s])!=self.report['initial_config_snapshots'][s]['config_sha256'] for s in PORTS):raise ValueError('Exact original config bytes not restored')
            self.stage('fast_restored',('true','true'));self.files_gate(('true','true'))
            self.report.update(passed=True,state='COMPLETE_FUNCTIONAL_PASS_AND_NORMAL_STOP',utc_end=utc())
        except BaseException as error:
            self.report['failures'].append(type(error).__name__+': '+str(error));self.report.update(state='FAILED_RETAINED',utc_end=utc())
            # No repeated stop, force kill, failed-stage restart or flags restoration.
            for server,child in self.children.items():
                key=(server,self.identities[server]['session_id'])
                if child.poll() is None and key not in self.stop_requested:
                    self.stop_requested.add(key)
                    try:self.issue(server,'stop')
                    except Exception:pass
            until=time.monotonic()+self.args.timeout
            while any(c.poll() is None for c in self.children.values()) and time.monotonic()<until:time.sleep(.2)
            self.report['failure_own_launcher_exits']={s:c.poll() for s,c in self.children.items()}
            self.report['failure_bounded_logs']={s:log.finish() for s,log in self.logs.items()}
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
        def test_default_has_no_process_socket_config_or_SQL_effect(self):
            with patch('subprocess.Popen',side_effect=AssertionError('process')),patch('socket.socket',side_effect=AssertionError('socket')):
                self.assertEqual(main([]),0)
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
    parser.add_argument('--completion',type=Path);parser.add_argument('--manifest',type=Path);parser.add_argument('--label');parser.add_argument('--timeout',type=float,default=120);parser.add_argument('--poll',type=float,default=.2);parser.add_argument('--quiet',type=float,default=2.2)
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
