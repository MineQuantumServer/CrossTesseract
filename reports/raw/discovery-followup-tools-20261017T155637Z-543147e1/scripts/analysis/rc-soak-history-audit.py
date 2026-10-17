#!/usr/bin/env python3
"""Post-stop, cohort-scoped row counts and retained transfer creation buckets.

Offline by default. --execute requires a closed, passing real3600s controller
with normal ABC exits. Reads isolated local MySQL only after all launch locks
are held and no selected JVM is running. No RCON/schema/instrumentation writes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rc_runtime_identity import ORIGINAL_FINAL_REVISION, ORIGINAL_FINAL_JAR, manifest_identity
CLUSTER = "dev_three_v1"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def cohort(raw):
    channels, endpoints = set(), {}
    servers = {server: info["server_id"] for server, info in raw["identity"].items()}
    if set(servers) != {"A", "B", "C"}:
        raise ValueError("Exactly three verified server identities required")
    if any(not re.fullmatch(r"opt-rc-soak-[a-z0-9-]{1,48}-[ABC]", name) for name in servers.values()):
        raise ValueError("Fresh isolated soak server identities required")
    for lanes in raw["fixtures"].values():
        for lane in lanes:
            channel = str(uuid.UUID(lane["channel"])); channels.add(channel)
            for endpoint in lane["sources"] + lane["sinks"]:
                eid = str(uuid.UUID(endpoint["id"]))
                if endpoint["server"] not in servers or eid in endpoints:
                    raise ValueError("Duplicate/unknown cohort endpoint")
                endpoints[eid] = {"server_id": servers[endpoint["server"]], "channel_id": channel}
    attempted = {str(uuid.UUID(endpoint["id"])) for endpoint in raw["attempted_endpoints"]}
    if attempted != set(endpoints) or not 1 <= len(channels) <= 16 or not 1 <= len(endpoints) <= 64:
        raise ValueError("Fixture/attempted endpoint cohort mismatch or bound")
    return {"cluster": CLUSTER, "servers": servers, "channels": sorted(channels), "endpoints": endpoints}


def clauses(group):
    quoted = lambda values: ",".join("'" + value + "'" for value in sorted(values))
    channels = quoted(group["channels"]); endpoints = quoted(group["endpoints"])
    servers = quoted(group["servers"].values())
    transfer = f"t.cluster_id='{CLUSTER}' AND t.endpoint_id IN ({endpoints}) AND t.channel_id IN ({channels})"
    transfer_ids = f"SELECT t.transfer_id FROM ct_transfers t WHERE {transfer}"
    subject = f"subject_id IN ({endpoints},{channels}) OR subject_id IN ({transfer_ids})"
    return channels, endpoints, servers, transfer, subject


def queries(group):
    channels, endpoints, servers, transfer, subject = clauses(group)
    scoped = f"cluster_id='{CLUSTER}'"
    epchan = f"endpoint_id IN ({endpoints}) AND channel_id IN ({channels})"
    tables = {
        "ct_servers": f"server_id IN ({servers})",
        "ct_endpoints": f"endpoint_id IN ({endpoints}) AND server_id IN ({servers}) AND channel_id IN ({channels})",
        "ct_channels": f"channel_id IN ({channels})", "ct_members": f"channel_id IN ({channels})",
        "ct_invites": f"channel_id IN ({channels})", "ct_chunk_grants": f"endpoint_id IN ({endpoints})",
        "ct_balances": f"channel_id IN ({channels})", "ct_transfers": epchan,
        "ct_demands": epchan, "ct_thermal_pools": f"channel_id IN ({channels})",
        "ct_heat_exchanges": epchan, "ct_ae_networks": epchan, "ct_stock_requests": epchan,
        "ct_operations_attributable_subject": "(" + subject + ")",
        "ct_audit_attributable_subject": "(" + subject + ")",
        "ct_outbox_subject_or_target_server": "(" + subject + f" OR target_server IN ({servers}))",
        "ct_inbox_server": f"server_id IN ({servers})",
        "ct_quarantine_endpoint_or_transfer": f"(endpoint_id IN ({endpoints}) OR transfer_id IN (SELECT t.transfer_id FROM ct_transfers t WHERE {transfer}))",
        "ct_history_buckets_server": f"server_id IN ({servers})",
    }
    base_tables = {"ct_operations_attributable_subject": "ct_operations", "ct_audit_attributable_subject": "ct_audit",
                   "ct_outbox_subject_or_target_server": "ct_outbox", "ct_inbox_server": "ct_inbox",
                   "ct_quarantine_endpoint_or_transfer": "ct_quarantine", "ct_history_buckets_server": "ct_history_buckets"}
    counts = " UNION ALL ".join(f"SELECT '{label}',COUNT(*) FROM {base_tables.get(label, label)} WHERE {scoped} AND {condition}"
                                for label, condition in tables.items())
    referenced = (f"SELECT r.resource_id,r.kind,r.format_version,OCTET_LENGTH(r.payload) FROM ct_resources r WHERE r.cluster_id='{CLUSTER}' AND "
                  f"(EXISTS(SELECT 1 FROM ct_transfers t WHERE {transfer} AND t.resource_id=r.resource_id) OR "
                  f"EXISTS(SELECT 1 FROM ct_balances b WHERE b.cluster_id=r.cluster_id AND b.channel_id IN ({channels}) AND b.resource_id=r.resource_id)) ORDER BY r.resource_id")
    curves = {}
    for width in (30, 60):
        curves[width] = (f"SELECT FLOOR(UNIX_TIMESTAMP(t.created_at)/{width})*{width},t.kind,t.state,COUNT(*) "
                         f"FROM ct_transfers t WHERE {transfer} GROUP BY 1,t.kind,t.state ORDER BY 1,t.kind,t.state")
    return {
        "database_clock_version": "SELECT @@version,@@session.time_zone,@@system_time_zone,UTC_TIMESTAMP(6),NOW(6),UNIX_TIMESTAMP(UTC_TIMESTAMP(6))",
        "endpoint_cohort_validation": f"SELECT endpoint_id,server_id,channel_id FROM ct_endpoints WHERE {scoped} AND endpoint_id IN ({endpoints}) ORDER BY endpoint_id",
        "server_clean_stop": f"SELECT server_id,status,clean_stop,fencing_epoch,IF(lease_until>CURRENT_TIMESTAMP(6),1,0) FROM ct_servers WHERE {scoped} AND server_id IN ({servers}) ORDER BY server_id",
        "table_counts": counts, "referenced_resource_rows": referenced,
        "history_quota_counters": f"SELECT server_id,used FROM ct_history_buckets WHERE {scoped} AND server_id IN ({servers}) ORDER BY server_id",
        "transfer_kind_state_counts": f"SELECT t.kind,t.state,COUNT(*) FROM ct_transfers t WHERE {transfer} GROUP BY t.kind,t.state ORDER BY t.kind,t.state",
        "transfer_created_30s": curves[30], "transfer_created_60s": curves[60],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--soak-controller", type=Path)
    parser.add_argument("--expected-revision", default=ORIGINAL_FINAL_REVISION)
    parser.add_argument("--expected-jar-sha256", default=ORIGINAL_FINAL_JAR)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sample = {"identity": {s: {"server_id": "opt-rc-soak-unit-" + s} for s in "ABC"},
                  "fixtures": {"mixed": [{"channel": "00000000-0000-0000-0000-000000000001",
                      "sources": [{"id": "00000000-0000-0000-0000-000000000002", "server": "A"}], "sinks": []}]},
                  "attempted_endpoints": [{"id": "00000000-0000-0000-0000-000000000002"}]}
        group = cohort(sample); statements = queries(group)
        assert all(q.startswith("SELECT ") and ";" not in q for q in statements.values())
        assert "FLOOR(UNIX_TIMESTAMP(t.created_at)/30)*30" in statements["transfer_created_30s"]
        assert "endpoint_id IN" in statements["transfer_created_60s"] and "channel_id IN" in statements["transfer_created_60s"]
        assert "server_id,status,clean_stop" in statements["server_clean_stop"]
        sample["attempted_endpoints"] = []
        try:
            cohort(sample)
        except ValueError:
            pass
        else:
            raise AssertionError("Mismatched endpoint identity accepted")
        print("PASS: offline strict cohort identity, bounded single-SELECT queries and UTC bucket construction")
        return 0
    if not args.execute:
        print(json.dumps({"execution": "NOT_RUN", "requires": "--execute --soak-controller CLOSED_QUALIFIED_3600s_AFTER_NORMAL_STOP"}))
        return 0
    if args.soak_controller is None:
        parser.error("Closed passing full-soak controller required")
    if any(k in os.environ for k in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI")):
        raise ValueError("Backend overrides forbidden")
    guard = load("rc_soak_history_closed_guards", ROOT / "scripts/analysis/run-rc-f3-fast-resource-after-soak.py")
    cp = args.soak_controller.resolve(strict=True)
    if not cp.is_relative_to(ROOT):
        raise ValueError("Repository controller required")
    controller = json.loads(cp.read_text()); guard.closed_controller(controller)
    if controller.get("sixty_minute_gate") is not True or controller.get("runtime_revision") != args.expected_revision:
        raise ValueError("Exact explicitly expected candidate real3600s pass required")
    runtime_path, runtime = guard.read_ref(controller["runtime_manifest"])
    runtime_identity = manifest_identity(runtime, args.expected_revision, args.expected_jar_sha256)
    rp, raw = guard.read_ref(controller["raw_report"])
    if raw.get("passed") is not True or raw.get("60min_gate") is not True or raw.get("cluster") != CLUSTER:
        raise ValueError("Raw real3600s/cohort gate failed")
    if (raw.get("operator_runtime_revision") != args.expected_revision
            or raw.get("probe_configuration", {}).get("artifacts", {}).get("JAR", {}).get("sha256") != args.expected_jar_sha256):
        raise ValueError("Raw soak runtime revision/JAR differs from explicit expected identity")
    group = cohort(raw)
    base = load("rc_soak_history_existing_SQL", ROOT / "scripts/optimization-benchmark.py")
    preparation = guard.load_preparation()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    target = ROOT / "reports/rc-20261017" / ("soak-history-post-stop-" + stamp + ".json")
    report = {"passed": False, "generated_utc": datetime.now(timezone.utc).isoformat(),
              "recipe": guard.meta(Path(__file__).resolve()), "controller": guard.meta(cp), "raw": guard.meta(rp),
              "runtime_manifest": guard.meta(runtime_path), "expected_runtime_identity": runtime_identity,
              "runtime_identity_guard": guard.meta(Path(__file__).with_name("rc_runtime_identity.py")),
              "guard_helper": guard.meta(ROOT / "scripts/analysis/run-rc-f3-fast-resource-after-soak.py"),
              "local_SQL_helper": guard.meta(ROOT / "scripts/optimization-benchmark.py"),
              "observer_window_reference": {
                  "raw_utc_start": raw["utc_start"],
                  "observation_start_relative_seconds": raw["observation"]["start"],
                  "observation_end_relative_seconds": raw["observation"]["end"],
                  "boundary_samples": [{key: sample[key] for key in ("scheduled", "utc", "start", "end")}
                                       for sample in (raw["observation"]["monitor_samples"][0], raw["observation"]["monitor_samples"][-1])],
                  "scope": "Raw observer-relative bounds and independent UTC sample anchors; no assertion that natural UTC creation buckets equal exact input/counter windows."},
              "cohort": group, "queries": [], "failures": [],
              "scope": ["Post-stop read-only endpoint/channel/server-scoped terminal rows, not live instrumentation.",
                        "created_at UTC buckets reconstruct surviving rows at audit time; removed history, update volume, peak live rows and continuous physical database/index size are UNMEASURED.",
                        "Creation buckets are sparse UTC epoch30s/60s intervals; absent intervals have zero retained rows, not proof of zero historical inserts before retention.",
                        "Transfer state is state at audit time, not the state at creation. Counts are records, never additional assets.",
                        "ct_resources reports distinct referenced rows; exclusive row creation is UNMEASURED because resources can be shared across fixtures.",
                        "Subject-scoped operation/audit rows are attributable IDs only; other subject types remain UNMEASURED. Target-server outbox/inbox rows describe this cohort's server delivery scope.",
                        "Shared ct_clusters/ct_player_guards and physical SQL/table/WAL byte growth are UNMEASURED. History used is a quota counter, separate from actual row counts."]}

    def save():
        pending = target.with_suffix(".json.pending"); pending.write_text(json.dumps(report, indent=2) + "\n"); pending.replace(target)

    try:
        save()
        with guard.stopped_locks(preparation):
            for server, info in raw["identity"].items():
                path = ROOT / ("run-" + server) / "cross-tesseract.properties"
                config = preparation.properties(path)
                if (guard.sha(path) != info["config_file_start_sha256"] or config.get("cluster.id") != CLUSTER
                        or config.get("server.id") != info["server_id"] or config.get("mysql.user") != "ct_dev"
                        or not config.get("mysql.url", "").startswith("jdbc:mysql://127.0.0.1:13306/cross_tesseract?")
                        or config.get("redis.uri") != "redis://127.0.0.1:16379"):
                    raise ValueError("Stopped isolated full-soak config changed; no SQL")
            inspect = json.loads(base.docker(["inspect", "ct-dev-mysql"]))[0]
            ports = inspect["HostConfig"]["PortBindings"].get("3306/tcp", [])
            if (inspect["Config"]["Image"] not in (base.MYSQL_IMAGE, "mysql:8.4.7") or inspect["State"]["Running"] is not True
                    or not ports or any(p["HostIp"] != "127.0.0.1" or p["HostPort"] != "13306" for p in ports)):
                raise ValueError("Pinned isolated local MySQL Docker identity mismatch")
            result = {}
            for name, statement in queries(group).items():
                record = {"name": name, "statement": statement, "observer_start": time.monotonic(),
                          "utc_request": datetime.now(timezone.utc).isoformat(), "account": "isolated local dev root; post-stop"}
                report["queries"].append(record)
                record["rows"] = base.sql(statement); record["observer_end"] = time.monotonic(); result[name] = record["rows"]
                if name == "database_clock_version" and not record["rows"][0][0].startswith("8.4.7"):
                    raise ValueError("MySQL8.4.7 required")
                if name == "endpoint_cohort_validation":
                    observed = {row[0]: {"server_id": row[1], "channel_id": row[2]} for row in record["rows"]}
                    if observed != group["endpoints"]:
                        raise ValueError("SQL endpoint/server/channel cohort mismatch")
                if name == "server_clean_stop":
                    if (len(record["rows"]) != 3 or any(row[1] != "STOPPED" or row[2] != "1" or row[4] != "0" for row in record["rows"])):
                        raise ValueError("SQL server clean stop/lease proof failed")
                save()
            counts = {name: int(number) for name, number in result["table_counts"]}
            total = counts["ct_transfers"]
            if any(sum(int(row[3]) for row in result[name]) != total for name in ("transfer_created_30s", "transfer_created_60s")):
                raise ValueError("Post-stop transfer count/bucket totals disagree")
            report["table_row_counts"] = counts
            report["cohort_referenced_resource_rows"] = len(result["referenced_resource_rows"])
            report["all_ABC_launch_locks_held_and_no_selected_JVM_for_all_SQL"] = True
            report["passed"] = True
    except BaseException as error:
        report["failures"].append(type(error).__name__ + ": " + str(error))
    finally:
        report["utc_end"] = datetime.now(timezone.utc).isoformat(); save()
    if report["passed"]:
        try:
            csv = target.with_suffix(".csv")
            with csv.open("x") as output:
                output.write("resolution_seconds,bucket_start_epoch_UTC,transfer_kind,state_at_audit,retained_rows_created\n")
                for width in (30, 60):
                    for row in result["transfer_created_" + str(width) + "s"]:
                        output.write(str(width) + "," + ",".join(row) + "\n")
            report["creation_bucket_CSV"] = guard.meta(csv)
        except BaseException as error:
            report["passed"] = False
            report["failures"].append("CSV evidence: " + type(error).__name__ + ": " + str(error))
        finally:
            save()
    print(json.dumps({"report": guard.meta(target), "passed": report["passed"]}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
