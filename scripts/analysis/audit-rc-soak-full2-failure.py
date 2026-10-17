#!/usr/bin/env python3
"""Independent, read-only terminal asset audit of the retained failed full2 run.

No game startup, RCON, SQL mutations, refunds or config changes. This audit can
pass its reconciliation while the original workload/controller remain FAILED.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
CONTROLLER = ROOT / "reports/rc-20261017/rc-soak-v2-3647-full2-controller-20261017T125157Z-21551942.json"
CONTROLLER_SHA = "8e049e67b0127794eda6c05d7d424a24923adc800d39b86eb1373845be044511"
RAW_SHA = "65c60ca1b0f29bf656e72c25314622a5a2ce94850baadc1aa78c2bd76c4bea40"
CLUSTER = "dev_three_v1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def meta(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); sys.modules[name] = value; spec.loader.exec_module(value)
    return value


def decode_wal(data):
    if not 36 <= len(data) <= 8_388_608 or sha(data[:-32]) != data[-32:].hex():
        raise ValueError("WAL checksum/size mismatch")
    body, offset = data[:-32], 0
    def take(n):
        nonlocal offset
        if n < 0 or offset+n > len(body): raise ValueError("Truncated WAL")
        value=body[offset:offset+n]; offset+=n; return value
    def num(fmt): return struct.unpack(fmt,take(struct.calcsize(fmt)))[0]
    def uid(): return str(uuid.UUID(bytes=take(16)))
    def count():
        n=num(">i")
        if not 0 <= n <= 64: raise ValueError("WAL entry count")
        return n
    def resource():
        n=num(">H")
        if not 1 <= n <= 64: raise ValueError("WAL kind length")
        kind=take(n).decode("ascii")
        if kind not in ("cross_tesseract:fe","cross_tesseract:fluid","cross_tesseract:item"): raise ValueError("Unknown resource")
        n=num(">i")
        if not 0 <= n <= 65536: raise ValueError("WAL payload bound")
        payload=take(n)
        return {"kind":kind,"payload_hash":sha(payload),"payload_bytes":n}
    if num(">i") != 0x43545431: raise ValueError("WAL magic")
    version=num(">i")
    if version not in (1,2): raise ValueError("WAL version")
    result={"format":version,"endpoint":uid(),"world":uid(),"generation":num(">q"),"revision":num(">q"),"deposits":[],"credits":[]}
    ids=set()
    for kind in ("deposits","credits"):
        for _ in range(count()):
            entry={"transaction":uid(),"channel":uid(),"resource":resource()}
            entry["amount" if kind=="deposits" else "original"]=num(">q")
            if kind=="credits": entry["remaining"]=num(">q")
            amount=entry.get("amount",entry.get("original"))
            if amount<=0 or not 0<=entry.get("remaining",0)<=amount or entry["transaction"] in ids: raise ValueError("WAL amount/ID")
            ids.add(entry["transaction"]);result[kind].append(entry)
    thermal={"energy":0,"residual":0.0,"pending":False}
    if version==2: thermal={"energy":num(">q"),"residual":num(">d"),"pending":bool(num(">B"))}
    if thermal!={"energy":0,"residual":0.0,"pending":False} or not math.isfinite(thermal["residual"]) or offset!=len(body): raise ValueError("Unexpected thermal/trailing WAL assets")
    result.update(checksum_verified=True,sha256=sha(data),size_bytes=len(data),thermal=thermal)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--execute",action="store_true");args=p.parse_args()
    if not args.execute:
        print(json.dumps({"execution":"NOT_RUN","scope":"retained full2 only; independent terminal audit, never changes original failed gates"}));return 0
    if any(k in os.environ for k in ("CT_MYSQL_URL","CT_MYSQL_USER","CT_MYSQL_PASSWORD","CT_REDIS_URI")): raise ValueError("Backend override forbidden")
    if sha(CONTROLLER.read_bytes())!=CONTROLLER_SHA: raise ValueError("Failed controller bytes changed")
    controller=json.loads(CONTROLLER.read_text());rp=ROOT/controller["raw_report"]["path"]
    if sha(rp.read_bytes())!=RAW_SHA: raise ValueError("Failed raw bytes changed")
    raw=json.loads(rp.read_text())
    if (controller.get("passed") is not False or raw.get("passed") is not False or raw.get("60min_gate") is not False
            or controller.get("all_own_launchers_exited_and_locks_free") is not True
            or set(controller.get("own_launcher_exits",{}))!={"A","B","C"}
            or any(x["exit_code"]!=0 for x in controller["own_launcher_exits"].values())): raise ValueError("Exact failed/cleanly stopped state required")
    history=load("rc_failure_history_queries",ROOT/"scripts/analysis/rc-soak-history-audit.py")
    guard=load("rc_failure_stopped_guard",ROOT/"scripts/analysis/run-rc-f3-fast-resource-after-soak.py")
    base=load("rc_failure_local_SQL",ROOT/"scripts/optimization-benchmark.py")
    group=history.cohort(raw)
    if len(group["endpoints"])!=20 or len(group["channels"])!=6: raise ValueError("Exact20EP/6channel cohort required")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8]
    target=ROOT/"reports/rc-20261017"/("full2-failure-assets-"+stamp+".json")
    report={"schema":1,"audit_passed":False,"original_workload_passed":False,"original_sixty_minute_gate":False,
            "utc_start":datetime.now(timezone.utc).isoformat(),"recipe":meta(Path(__file__).resolve()),"controller":meta(CONTROLLER),"raw":meta(rp),
            "cohort":group,"queries":[],"WAL":{},"failures":[],"scope":[
                "Independent stopped-terminal read-only asset reconciliation; original full2 failure/gates are unchanged.",
                "Input/output debt is external accepted minus actual output, with zero period-start net assets. SQL exclusive ownership is pool plus positive ALLOCATE remaining; WAL/BE mirrors are not added.",
                "No startup, RCON, asset mutation, refund, schema change or config modification.",
                "Mode evidence is last acknowledged workload command, not an independent stopped-NBT decode. Unsaved uncommitted BE assets are not inferred from historic samples."]}
    def save():
        tmp=target.with_suffix(".json.pending");tmp.write_text(json.dumps(report,indent=2)+"\n");tmp.replace(target)
    def query(name,sql):
        if not sql.startswith("SELECT ") or ";" in sql: raise ValueError("Single SELECT only")
        row={"name":name,"statement":sql,"start":time.monotonic(),"utc":datetime.now(timezone.utc).isoformat()};report["queries"].append(row)
        row["rows"]=base.sql(sql);row["end"]=time.monotonic();save();return row["rows"]
    try:
        save()
        with guard.stopped_locks(guard.load_preparation()):
            live=[]
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
                try: argv=(proc/"cmdline").read_bytes().split(b"\0")
                except (FileNotFoundError,PermissionError):continue
                if argv and argv[0].endswith(b"/java"):live.append(int(proc.name))
                elif argv and b"python" in argv[0] and any(b"rc-soak" in a or b"rc-v2" in a or b"optimization-monitor" in a for a in argv[1:]):live.append(int(proc.name))
            if live:raise ValueError("Live observer/JVM conflict: "+str(live))
            report["no_other_observer_or_Java_PIDs"]={"pids":live,"utc":datetime.now(timezone.utc).isoformat()}
            cfg=guard.load_preparation()
            report["stopped_configs"]={}
            for server,identity in raw["identity"].items():
                path=ROOT/("run-"+server)/"cross-tesseract.properties";props=cfg.properties(path)
                if (sha(path.read_bytes())!=identity["config_file_start_sha256"] or props.get("cluster.id")!=CLUSTER or props.get("server.id")!=identity["server_id"]
                        or props.get("mysql.user")!="ct_dev" or not props.get("mysql.url","").startswith("jdbc:mysql://127.0.0.1:13306/cross_tesseract?") or props.get("redis.uri")!="redis://127.0.0.1:16379"): raise ValueError("Isolated exact stopped config mismatch")
                vanilla=cfg.properties(ROOT/("run-"+server)/"server.properties")
                if vanilla.get("level-name")!=identity["level_name"]:raise ValueError("World changed")
                report["stopped_configs"][server]={**meta(path),"flags":{k:props[k] for k in ("transfer.channelBatches","transfer.localFastPath")},"world":vanilla["level-name"]}
            inspected=json.loads(base.docker(["inspect","ct-dev-mysql"]))[0];ports=inspected["HostConfig"]["PortBindings"].get("3306/tcp",[])
            if inspected["Config"]["Image"] not in (base.MYSQL_IMAGE,"mysql:8.4.7") or not inspected["State"]["Running"] or not ports or any(x!={"HostIp":"127.0.0.1","HostPort":"13306"} for x in ports):raise ValueError("Pinned loopback MySQL mismatch")
            for name in ("database_clock_version","endpoint_cohort_validation","server_clean_stop"):
                rows=query(name,history.queries(group)[name])
                if name=="database_clock_version" and not rows[0][0].startswith("8.4.7"):raise ValueError("Wrong SQL version")
                if name=="endpoint_cohort_validation" and {r[0]:{"server_id":r[1],"channel_id":r[2]} for r in rows}!=group["endpoints"]:raise ValueError("SQL cohort mismatch")
                if name=="server_clean_stop" and (len(rows)!=3 or any(r[1]!="STOPPED" or r[2]!="1" or r[4]!="0" for r in rows)):raise ValueError("Unclean/live SQL server")
            channels,endpoints,servers,transfer,_=history.clauses(group)
            ep_rows=query("endpoint_checkpoints",f"SELECT endpoint_id,server_id,world_id,channel_id,checkpoint,recovery_generation,last_epoch,state,CONCAT('pause:',pause_reason) FROM ct_endpoints WHERE cluster_id='{CLUSTER}' AND endpoint_id IN ({endpoints}) ORDER BY endpoint_id")
            ep_map={r[0]:r for r in ep_rows}
            for eid,expected in group["endpoints"].items():
                server=next(s for s,v in group["servers"].items() if v==expected["server_id"]);identity=raw["identity"][server];row=ep_map[eid]
                if (row[1],row[2],row[3],int(row[6]))!=(identity["server_id"],identity["world_id"],expected["channel_id"],identity["fencing_epoch"]):raise ValueError("Endpoint world/epoch identity mismatch")
            resource_rows=query("referenced_resources",f"SELECT r.resource_id,r.kind,r.format_version,r.payload_hash,CONCAT('hex:',HEX(r.payload)) FROM ct_resources r WHERE r.cluster_id='{CLUSTER}' AND (EXISTS(SELECT 1 FROM ct_transfers t WHERE {transfer} AND t.resource_id=r.resource_id) OR EXISTS(SELECT 1 FROM ct_balances b WHERE b.cluster_id=r.cluster_id AND b.channel_id IN ({channels}) AND b.resource_id=r.resource_id)) ORDER BY r.resource_id")
            resources={r[0]:{"kind":r[1],"format":int(r[2]),"payload_hash":r[3],"payload_bytes":len(bytes.fromhex(r[4][4:]))} for r in resource_rows}
            for r in resource_rows:
                if not r[4].startswith("hex:") or sha(bytes.fromhex(r[4][4:]))!=r[3] or r[2]!="1":raise ValueError("Resource identity mismatch")
            pools=query("pool",f"SELECT b.channel_id,b.resource_id,b.amount FROM ct_balances b WHERE b.cluster_id='{CLUSTER}' AND b.channel_id IN ({channels}) ORDER BY b.channel_id,b.resource_id")
            positive=query("positive_allocations",f"SELECT t.transfer_id,t.endpoint_id,t.channel_id,t.resource_id,t.kind,t.state,t.amount,t.remaining FROM ct_transfers t WHERE {transfer} AND t.kind='ALLOCATE' AND t.remaining>0 ORDER BY t.transfer_id")
            states=query("transfer_stage_totals",f"SELECT t.channel_id,r.kind,t.kind,t.state,COUNT(*),SUM(t.amount),SUM(t.remaining) FROM ct_transfers t JOIN ct_resources r ON r.cluster_id=t.cluster_id AND r.resource_id=t.resource_id WHERE {transfer} GROUP BY t.channel_id,r.kind,t.kind,t.state ORDER BY t.channel_id,r.kind,t.kind,t.state")
            query("server_session_epoch",f"SELECT server_id,world_id,session_id,fencing_epoch,status,clean_stop,IF(lease_until>CURRENT_TIMESTAMP(6),1,0) FROM ct_servers WHERE cluster_id='{CLUSTER}' AND server_id IN ({servers}) ORDER BY server_id")
            for endpoint,expected in group["endpoints"].items():
                server=next(s for s,v in group["servers"].items() if v==expected["server_id"]);identity=raw["identity"][server]
                root=ROOT/("run-"+server)/identity["level_name"]/"cross_tesseract/journal";path=root/(endpoint+".ctj")
                if root.is_symlink() or path.is_symlink() or path.resolve().parent!=root.resolve():raise ValueError("Unsafe owned WAL path")
                data=path.read_bytes();wal=decode_wal(data)
                if (wal["endpoint"],wal["world"],str(wal["generation"]),str(wal["revision"]))!=(endpoint,identity["world_id"],ep_map[endpoint][5],ep_map[endpoint][4]):raise ValueError("WAL SQL identity/checkpoint mismatch")
                if wal["deposits"]:raise ValueError("Outstanding source WAL deposits require explicit ownership review")
                for credit in wal["credits"]:
                    if credit["channel"]!=expected["channel_id"]:raise ValueError("Wrong WAL channel")
                    if not any(all(credit["resource"][k]==r[k] for k in ("kind","payload_hash","payload_bytes")) for r in resources.values()):raise ValueError("Unknown WAL resource")
                report["WAL"][endpoint]={**wal,"source":meta(path),"server":server}
            sql_credit={r[0]:(r[1],r[2],resources[r[3]]["kind"],resources[r[3]]["payload_hash"],int(r[6]),int(r[7])) for r in positive}
            wal_credit={c["transaction"]:(eid,c["channel"],c["resource"]["kind"],c["resource"]["payload_hash"],c["original"],c["remaining"]) for eid,w in report["WAL"].items() for c in w["credits"] if c["remaining"]>0}
            if len(wal_credit)!=sum(c["remaining"]>0 for w in report["WAL"].values() for c in w["credits"]) or wal_credit!=sql_credit:raise ValueError("Positive WAL/SQL exclusive credit mismatch")
            owned=defaultdict(int)
            for channel,rid,amount in pools:owned[(channel,resources[rid]["kind"])]+=int(amount)
            for r in positive:owned[(r[2],resources[r[3]]["kind"])]+=int(r[7])
            lane_channels={l["name"]:l["channel"] for lanes in raw["fixtures"].values() for l in lanes};ledger={}
            for name,entries in raw["observation"]["ledger_at_end"].items():
                ledger[name]={}
                for kind,last in entries.items():
                    before=raw["ledger_before_observation"][name][kind];debt=last["accepted"]-last["external_output"]
                    if before["accepted"]-before["external_output"]!=0:raise ValueError("Nonzero period-start assets")
                    rk={"FE":"cross_tesseract:fe","water":"cross_tesseract:fluid","item_A":"cross_tesseract:item","item_B":"cross_tesseract:item"}[kind]
                    actual=owned[(lane_channels[name],rk)]
                    if debt!=actual:raise ValueError("Input-output debt/SQL ownership mismatch: "+name+":"+kind)
                    ledger[name][kind]={"period_start_net_assets":0,"observation_accepted":last["accepted"]-before["accepted"],"observation_external_output":last["external_output"]-before["external_output"],"residual_debt":debt,"terminal_SQL_exclusive_assets":actual,"unit":last["unit"],"reconciled":True}
            for evidence in report["WAL"].values():
                if sha((ROOT/evidence["source"]["path"]).read_bytes())!=evidence["sha256"]:raise ValueError("Owned WAL changed during stopped audit")
            report.update(asset_ledger=ledger,positive_WAL_SQL_credit_identity_match=True,all_source_WAL_deposits_empty=True,
                          owned_WAL_hashes_unchanged_during_audit=True,all_three_launch_locks_held=True,audit_passed=True)
            save()
    except BaseException as error:report["failures"].append(type(error).__name__+": "+str(error))
    finally:
        report["utc_end"]=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({"report":meta(target),"audit_passed":report["audit_passed"],"original_sixty_minute_gate":False}));return 0 if report["audit_passed"] else 1


if __name__=="__main__":raise SystemExit(main())
