#!/usr/bin/env python3
"""Prepare/collect exact Authority allocation EXPLAINs on isolated dev_perf_v1.

Default and --self-test are offline. --execute performs read-only collection,
only after the operator has finished timed measurement and enabled a populated
1000-endpoint active fixture. No schema, data or instrumentation changes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/main/java/dev/crosstesseract/backend/Authority.java"
CLUSTER = "dev_perf_v1"
KIND = "cross_tesseract:fe"
PORT = 25578
MYSQL_IMAGE = "mysql@sha256:0426ec38c7a10aa45ba383887df7878f74ee70e2fd589c7b69207f3577901903"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def java_strings(line):
    return [json.loads('"' + value + '"') for value in re.findall(r'"((?:\\.|[^"\\])*)"', line)]


def source_queries(text, endpoint_count, known_count):
    """Use exact scalar literals; render only the verified allocationRows branches."""
    lines = text.splitlines()
    candidate = [(index + 1, line) for index, line in enumerate(lines)
        if '"SELECT d.endpoint_id,d.room,d.profile_hash,d.quantum FROM ct_demands d JOIN ct_endpoints' in line]
    count = [(index + 1, line) for index, line in enumerate(lines)
        if '"SELECT COUNT(*) AS n FROM ct_transfers t JOIN ct_resources r ON' in line]
    rows = [(index + 1, line) for index, line in enumerate(lines)
        if "ROW_NUMBER() OVER(PARTITION BY endpoint_id ORDER BY created_at,transfer_id)" in line and "query(c," in line]
    unseen = [line for line in lines if "String unseen=known.isEmpty()" in line]
    if not (len(candidate) == len(count) == len(rows) == len(unseen) == 1):
        raise ValueError("Authority allocation source shape changed; inspect exact query before collection")
    candidate_sql, count_sql = java_strings(candidate[0][1])[0], java_strings(count[0][1])[0]
    fragments = java_strings(rows[0][1])
    exclusion = java_strings(unseen[0])
    limits = re.search(r"\(activeOnly\?(\d+):(\d+)\)", rows[0][1])
    if not (len(fragments) == 8 and fragments[1:3] == [",", "?"] and
            fragments[4:6] == [" AND state<>'QUARANTINED'", ""] and
            len(exclusion) == 5 and exclusion == ["", " AND transfer_id NOT IN (", ",", "?", ")"] and limits):
        raise ValueError("Dynamic allocationRows expression changed; no approximate query substituted")
    placeholders = ",".join("?" for _ in range(endpoint_count))
    known = exclusion[1] + ",".join("?" for _ in range(known_count)) + exclusion[4] if known_count else ""
    specs = {}
    for name, (number, line), statement, bindings in (
            ("global_candidate", candidate[0], candidate_sql, ["cluster", "channel", "kind"]),
            ("outstanding_kind_count", count[0], count_sql, ["cluster", "endpoint", "kind"])):
        if statement.count("?") != len(bindings):
            raise ValueError("Scalar allocation bind shape changed")
        specs[name] = {"template": statement, "bind_order": bindings, "source_line": number,
            "java_source_line": line.strip(), "template_sha256": hashlib.sha256(statement.encode()).hexdigest()}
    for active, limit in ((True, int(limits[1])), (False, int(limits[2]))):
        statement = (fragments[0] + placeholders + fragments[3] + (fragments[4] if active else fragments[5]) +
            known + fragments[6] + str(limit) + fragments[7])
        name = "outstanding_payloads_active" if active else "outstanding_payloads_recovery"
        specs[name] = {"template": statement, "source_line": rows[0][0], "java_source_line": rows[0][1].strip(),
            "bind_order": ["cluster"] + ["endpoint"] * endpoint_count + ["known_transfer"] * known_count,
            "active_only": active, "row_bound_per_endpoint": limit, "endpoint_count": endpoint_count,
            "known_transfer_count": known_count, "template_sha256": hashlib.sha256(statement.encode()).hexdigest(),
            "branch_note": "Source-exact SQL branch. Empty known set is a valid source branch, not proof of the running Java request's actual local credits."}
    return specs


def quote(value):
    # All values are developer-cluster/kind constants or validated identities.
    if not re.fullmatch(r"[A-Za-z0-9_:\-]{1,128}", str(value)):
        raise ValueError("Invalid SQL identity literal")
    return "'" + str(value) + "'"


def bind(template, values):
    fragments = template.split("?")
    if len(fragments) != len(values) + 1:
        raise ValueError("SQL parameter count mismatch")
    return "".join(part + (quote(values[i]) if i < len(values) else "") for i, part in enumerate(fragments))


def readonly(statement):
    normalized = statement.strip().rstrip(";").strip()
    if ";" in normalized or re.search(r"/\*|--|#", normalized):
        raise ValueError("Multi-statements/comments are not accepted")
    if not re.match(r"^(?:EXPLAIN\s+(?:FORMAT=JSON\s+|ANALYZE\s+)?)?SELECT\s", normalized, re.IGNORECASE):
        raise ValueError("Only SELECT and SELECT EXPLAIN are accepted")
    if re.search(r"\b(?:INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|SET|CALL|KILL|INTO|OUTFILE|DUMPFILE)\b",
                 normalized, re.IGNORECASE):
        raise ValueError("Mutating/locking SQL is not accepted")
    if re.search(r"\b(?:FOR\s+SHARE|LOCK\s+IN\s+SHARE\s+MODE)\b", normalized, re.IGNORECASE):
        raise ValueError("Locking SELECT is not accepted")
    return normalized


class Explain:
    def __init__(self, args, specs, source_sha256):
        self.args = args
        self.specs = specs
        self.source_sha256 = source_sha256
        self.started = time.monotonic()
        stem = "optimization-explain-" + args.label + "-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
        self.path = ROOT / "reports" / (stem + ".json")
        self.report = {"schema_version": 1, "report_kind": "read_only_authority_explain",
            "label": args.label, "utc_start": utc_now(), "observer_monotonic_start": self.started,
            "cluster": CLUSTER, "resource_kind": KIND, "port": PORT, "passed": False,
            "conditions": {"endpoints_per_channel_plan": args.endpoints, "analyze": args.analyze,
                "include_recovery": args.include_recovery, "timeout_seconds": args.timeout,
                "known_transfer_count": len(args.known_transfer)},
            "scope": {"timing": "Post-measurement diagnostic. EXPLAIN ANALYZE executes these read-only SELECTs, warms caches and adds load; not timed-run throughput/E2E.",
                "session": "Root account in established isolated local dev MySQL; no ct_dev observer pollution.",
                "locking": "SELECT-only autocommit snapshot; Authority normally holds its channel lock. This helper does not emulate mutation/lock context.",
                "statement_units": "Observer SELECT count and plan count separately recorded; not mod JDBC call frequency.",
                "identity": "Actual live RCON perf fixture and matching SQL world/session/fencing generation required.",
                "source": "Templates extracted from current Authority worktree, source line/hash/git evidence recorded; not assumed equal to loaded JVM without operator build evidence."},
            "source_provenance": {"path": str(SOURCE), "sha256": source_sha256},
            "query_specs": specs, "SQL_observer_trace": [], "RCON_observer_trace": [],
            "plans": [], "failures": [], "warnings": []}
        self.helpers = None
        self.docker_env = {key: value for key, value in os.environ.items() if key not in
            ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(self.path)

    def docker(self, args, statement=None):
        return subprocess.run(["docker", "--host=unix:///var/run/docker.sock", *args],
            input=statement, text=True, capture_output=True, timeout=self.args.timeout, env=self.docker_env)

    def sql(self, statement, name):
        statement = readonly(statement)
        trace = {"name": name, "statement": statement, "utc_request_start": utc_now(),
            "observer_start": time.monotonic(), "observer_account": "isolated dev root"}
        self.report["SQL_observer_trace"].append(trace)
        try:
            result = self.docker(["exec", "-i", "-e", "MYSQL_PWD=ct_dev_root_only", "ct-dev-mysql",
                "mysql", "-u", "root", "--batch", "--raw", "--skip-column-names", "cross_tesseract"], statement + ";\n")
            trace.update(exit_code=result.returncode, raw_stdout=result.stdout, raw_stderr=result.stderr)
            if result.returncode:
                raise RuntimeError("Read-only MySQL operation failed: " + result.stderr.strip()[:700])
        except subprocess.TimeoutExpired as error:
            trace["failure"] = "MySQL observer timeout"
            raise RuntimeError("MySQL observer timeout") from error
        finally:
            trace.update(utc_reply_end=utc_now(), observer_end=time.monotonic())
            self.save()
        return result.stdout

    def rows(self, statement, name):
        return [line.split("\t") for line in self.sql(statement, name).strip().splitlines() if line]

    def rcon(self, command):
        if command not in ("ct_test status", "ct_test bulk-status", "ct_test pid"):
            raise ValueError("Only read-only perf fixture identity commands are accepted")
        trace = {"command": command, "port": PORT, "utc_request_start": utc_now(),
            "observer_start": time.monotonic()}
        self.report["RCON_observer_trace"].append(trace)
        try:
            reply = self.helpers.command(PORT, command)
            trace["raw_reply"] = reply
            return reply
        finally:
            trace.update(utc_reply_end=utc_now(), observer_end=time.monotonic())
            self.save()

    def preflight(self):
        if any(key in os.environ for key in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI")):
            raise ValueError("Backend override variables are not accepted")
        spec = importlib.util.spec_from_file_location("ct_explain_isolation_helpers", ROOT / "scripts/optimization-benchmark.py")
        self.helpers = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.helpers
        spec.loader.exec_module(self.helpers)
        config_path = ROOT / "run-perf/cross-tesseract.properties"
        config = self.helpers.properties(config_path)
        vanilla = self.helpers.properties(ROOT / "run-perf/server.properties")
        sid = config.get("server.id", "")
        if not (config.get("cluster.id") == CLUSTER and config.get("backend.enabled") == "true"
                and re.fullmatch(r"(?:dev|opt)-[A-Za-z0-9_-]{1,60}", sid)
                and config.get("mysql.url", "").startswith("jdbc:mysql://127.0.0.1:13306/cross_tesseract?")
                and config.get("mysql.user") == "ct_dev" and config.get("redis.uri") == "redis://127.0.0.1:16379"
                and vanilla.get("rcon.port") == str(PORT) and vanilla.get("enable-rcon") == "true"):
            raise ValueError("Refusing non-isolated perf backend/config")
        status = self.rcon("ct_test status")
        bulk = self.rcon("ct_test bulk-status")
        metrics, bulk_metrics = self.helpers.numeric_fields(status), self.helpers.numeric_fields(bulk)
        if "STATUS online" not in status or not (bulk_metrics.get("count") == bulk_metrics.get("registered") ==
                bulk_metrics.get("bound") == 1000 and metrics.get("active_endpoints") == 1000):
            raise ValueError("Requires existing populated, bound, ACTIVE 1000-endpoint fixture after timed measurement")
        pid_reply = self.rcon("ct_test pid")
        pid_match = re.fullmatch(r"PID (\d+)\s*", pid_reply)
        if pid_match is None:
            raise ValueError("Unrecognized perf JVM PID response")
        pid = int(pid_match[1])
        proc = Path(f"/proc/{pid}")
        argv_raw = (proc / "cmdline").read_bytes()
        argv = [value.decode() for value in argv_raw.split(b"\0") if value]
        expanded, files = self.helpers.expanded_vm_args(argv, "Perf", (proc / "cwd").resolve())
        props = {arg[2:].split("=", 1)[0]: arg.split("=", 1)[1] for arg in expanded if arg.startswith("-D") and "=" in arg}
        if props.get("cross_tesseract.testHarness") != "true" or props.get("cross_tesseract.config") != str(config_path):
            raise ValueError("Perf JVM does not use the fixed development harness/config")
        world_name = vanilla.get("level-name", "world")
        if world_name != "world" and not re.fullmatch(r"world-opt-[A-Za-z0-9_-]{1,64}", world_name):
            raise ValueError("Unexpected perf fixture world")
        world = str(uuid.UUID((ROOT / "run-perf" / world_name / "cross_tesseract/world-id").read_text().strip()))
        inspect = self.docker(["inspect", "--format", "{{json .NetworkSettings.Ports}}|{{.Config.Image}}|{{.State.Running}}", "ct-dev-mysql"])
        if inspect.returncode:
            raise RuntimeError(inspect.stderr)
        ports, image, running = inspect.stdout.strip().rsplit("|", 2)
        bindings = json.loads(ports).get("3306/tcp") or []
        if running != "true" or image not in (MYSQL_IMAGE, "mysql:8.4.7") or not any(
                b.get("HostIp") == "127.0.0.1" and b.get("HostPort") == "13306" for b in bindings):
            raise ValueError("Refusing unrelated MySQL container/binding")
        database = self.rows("SELECT VERSION(),@@port,@@hostname,CURRENT_TIMESTAMP(6),CURRENT_USER(),DATABASE()", "mysql_identity")
        if len(database) != 1 or database[0][0] != "8.4.7" or database[0][1] != "3306" or \
                database[0][4].split("@", 1)[0] != "root" or database[0][5] != "cross_tesseract":
            raise ValueError("Requires actual existing MySQL 8.4.7")
        sessions = self.rows("SELECT s.world_id,s.session_id,s.fencing_epoch,s.protocol_version,s.format_version,"
            "s.lease_until,CURRENT_TIMESTAMP(6),s.capabilities,p.recovery_generation,s.status "
            "FROM ct_servers s JOIN ct_clusters p ON p.cluster_id=s.cluster_id WHERE s.cluster_id=" +
            quote(CLUSTER) + " AND s.server_id=" + quote(sid) + " AND s.lease_until>CURRENT_TIMESTAMP(6)", "live_SQL_session")
        if len(sessions) != 1 or sessions[0][0] != world or sessions[0][3:5] != ["1", "1"] or \
                KIND not in sessions[0][7].split(",") or sessions[0][9] != "ONLINE":
            raise ValueError("No matching live, protocol-valid SQL perf session")
        self.report["identity"] = {"pid": pid, "server_id": sid, "world_id": world, "world_name": world_name,
            "session_id": sessions[0][1], "fencing_epoch": int(sessions[0][2]),
            "recovery_generation": int(sessions[0][8]), "SQL_session_row": sessions[0],
            "mysql_identity": database[0], "argv_sha256": hashlib.sha256(argv_raw).hexdigest(),
            "vm_argfiles": files, "rcon_status": status, "rcon_bulk_status": bulk}
        if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != self.source_sha256:
            raise ValueError("Authority source changed after exact query extraction")
        self.report["source_provenance"].update({
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
            "Authority_worktree_status": subprocess.run(["git", "status", "--short", "--", str(SOURCE)],
                cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()})

    def fixture(self):
        info = self.report["identity"]
        session_scope = ("e.cluster_id=" + quote(CLUSTER) + " AND e.server_id=" + quote(info["server_id"]) +
            " AND e.world_id=" + quote(info["world_id"]) + " AND e.last_epoch=" + str(info["fencing_epoch"]) +
            " AND e.recovery_generation=" + str(info["recovery_generation"]) +
            " AND e.state='ACTIVE' AND e.channel_id IS NOT NULL")
        endpoints = self.rows("SELECT COUNT(*),COUNT(DISTINCT e.device_owner),COUNT(DISTINCT e.channel_id) FROM ct_endpoints e WHERE " +
            session_scope, "actual_endpoint_counts")
        if int(endpoints[0][0]) < 1000:
            raise ValueError("SQL fixture does not contain 1000 matching live session endpoints")
        channel_filter = " AND d.channel_id=" + quote(str(uuid.UUID(self.args.channel))) if self.args.channel else ""
        demands = self.rows("SELECT d.channel_id,COUNT(DISTINCT d.endpoint_id),MIN(d.expires_at),MAX(d.expires_at) "
            "FROM ct_demands d JOIN ct_endpoints e ON e.cluster_id=d.cluster_id AND e.endpoint_id=d.endpoint_id WHERE " +
            session_scope + " AND e.channel_id=d.channel_id AND d.kind=" + quote(KIND) +
            " AND d.room>=d.quantum AND d.expires_at>CURRENT_TIMESTAMP(6)" + channel_filter +
            " GROUP BY d.channel_id ORDER BY COUNT(DISTINCT d.endpoint_id) DESC,d.channel_id", "actual_live_demands")
        if not demands:
            raise ValueError("No actual unexpired FE demands in the populated live fixture")
        chosen = None
        for demand in demands:
            channel = str(uuid.UUID(demand[0]))
            rows = self.rows("SELECT e.endpoint_id,COUNT(t.transfer_id) FROM ct_endpoints e "
                "JOIN ct_demands d ON d.cluster_id=e.cluster_id AND d.endpoint_id=e.endpoint_id AND d.channel_id=e.channel_id "
                "JOIN ct_transfers t ON t.cluster_id=e.cluster_id AND t.endpoint_id=e.endpoint_id "
                "JOIN ct_resources r ON r.cluster_id=t.cluster_id AND r.resource_id=t.resource_id WHERE " +
                session_scope + " AND e.channel_id=" + quote(channel) + " AND d.kind=" + quote(KIND) +
                " AND d.room>=d.quantum AND d.expires_at>CURRENT_TIMESTAMP(6) AND t.kind='ALLOCATE' AND t.remaining>0 "
                "AND t.state<>'QUARANTINED' AND r.kind=" + quote(KIND) +
                " GROUP BY e.endpoint_id ORDER BY COUNT(t.transfer_id) DESC,e.endpoint_id LIMIT " + str(self.args.endpoints),
                "actual_populated_outstanding_" + channel)
            if len(rows) == self.args.endpoints:
                chosen = (channel, demand, rows)
                break
        if chosen is None:
            raise ValueError("Requires requested number of actual demanding endpoints with positive outstanding allocations; no empty fixture plan accepted")
        channel, demand, rows = chosen
        ids = [str(uuid.UUID(row[0])) for row in rows]
        known = [str(uuid.UUID(value)) for value in self.args.known_transfer]
        if known:
            check = self.rows("SELECT transfer_id FROM ct_transfers WHERE cluster_id=" + quote(CLUSTER) +
                " AND endpoint_id IN (" + ",".join(map(quote, ids)) + ") AND kind='ALLOCATE' AND transfer_id IN (" +
                ",".join(map(quote, known)) + ")", "known_transfer_membership")
            if {row[0] for row in check} != set(known):
                raise ValueError("Known transfer IDs do not belong to selected real endpoints")
        pool = self.rows("SELECT COALESCE(SUM(b.amount),0),COUNT(*) FROM ct_balances b JOIN ct_resources r "
            "ON r.cluster_id=b.cluster_id AND r.resource_id=b.resource_id WHERE b.cluster_id=" + quote(CLUSTER) +
            " AND b.channel_id=" + quote(channel) + " AND r.kind=" + quote(KIND), "actual_pool_diagnostic")
        if int(pool[0][0]) == 0:
            self.report["warnings"].append("Observed FE pool is empty. Global-candidate execution may reject all candidates; this is not evidence for a successful allocation path.")
        self.report["fixture"] = {"SQL_endpoint_counts": endpoints[0], "chosen_channel": channel,
            "live_demand_evidence": demand, "endpoint_outstanding_counts": rows, "selected_endpoints": ids,
            "known_transfer_ids": known, "pool_evidence": pool,
            "warning": "All selections are real observed rows. Active fixture can advance between read snapshots; no fake IDs or frozen data used."}
        return channel, ids, known

    def run(self):
        self.save()
        try:
            self.preflight()
            channel, endpoints, known = self.fixture()
            selected = ("global_candidate", "outstanding_kind_count", "outstanding_payloads_active")
            if self.args.include_recovery:
                selected += ("outstanding_payloads_recovery",)
            for name in selected:
                spec = self.specs[name]
                values = ([CLUSTER, channel, KIND] if name == "global_candidate" else
                    [CLUSTER, endpoints[0], KIND] if name == "outstanding_kind_count" else [CLUSTER, *endpoints, *known])
                statement = readonly(bind(spec["template"], values))
                # Count actual SELECT result rows without exposing payload bytes.
                count_rows = self.rows("SELECT COUNT(*) FROM (" + statement + ") observed_exact_query",
                    "result_row_count_" + name)
                if name == "global_candidate" and int(count_rows[0][0]) == 0:
                    self.report["warnings"].append("Exact global-candidate SELECT returned zero rows in the count snapshot. Plans still use the exact real populated fixture, but no selected candidate/successful allocation is claimed.")
                count_value = None
                if name == "outstanding_kind_count":
                    scalar_rows = self.rows(statement, "actual_outstanding_kind_count")
                    count_value = int(scalar_rows[0][0])
                modes = (("EXPLAIN FORMAT=JSON ", "estimated_json"),)
                if self.args.analyze:
                    modes += (("EXPLAIN ANALYZE ", "actual_tree"),)
                for prefix, mode in modes:
                    raw = self.sql(prefix + statement, name + "_" + mode)
                    plan_path = self.path.with_name(self.path.stem + "-" + name + "-" + mode + ".txt")
                    plan_path.write_text(raw)
                    self.report["plans"].append({"name": name, "mode": mode, "statement": statement,
                        "bound_parameters": values, "observed_result_rows": int(count_rows[0][0]),
                        "observed_scalar_outstanding_count": count_value,
                        "source_line": spec["source_line"], "template_sha256": spec["template_sha256"],
                        "raw_plan": raw, "raw_plan_file": str(plan_path),
                        "known_set_scope": spec.get("branch_note")})
                    self.save()
            info = self.report["identity"]
            final = self.rows("SELECT s.world_id,s.session_id,s.fencing_epoch,p.recovery_generation FROM ct_servers s "
                "JOIN ct_clusters p ON p.cluster_id=s.cluster_id WHERE s.cluster_id=" + quote(CLUSTER) +
                " AND s.server_id=" + quote(info["server_id"]) + " AND s.lease_until>CURRENT_TIMESTAMP(6)", "final_live_session")
            if final != [[info["world_id"], info["session_id"], str(info["fencing_epoch"]), str(info["recovery_generation"])]]:
                raise ValueError("SQL session changed/expired during diagnostic")
            if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != self.source_sha256:
                raise ValueError("Authority source changed during diagnostic")
            self.report["passed"] = True
        except Exception as error:
            self.report["failures"].append(type(error).__name__ + ": " + str(error))
        finally:
            trace = self.report["SQL_observer_trace"]
            self.report["observer_statement_counts"] = {"total_attempted": len(trace),
                "SELECT_attempted": sum(t["statement"].startswith("SELECT ") for t in trace),
                "EXPLAIN_estimated_attempted": sum(t["statement"].startswith("EXPLAIN FORMAT=JSON ") for t in trace),
                "EXPLAIN_ANALYZE_attempted": sum(t["statement"].startswith("EXPLAIN ANALYZE ") for t in trace)}
            self.report.update(utc_end=utc_now(), elapsed_seconds=time.monotonic() - self.started)
            self.save()
        print("Saved " + str(self.path))
        if self.report["failures"]:
            print(json.dumps(self.report["failures"], ensure_ascii=False), file=sys.stderr)
        return 0 if self.report["passed"] else 1


def self_test(specs):
    assert specs["global_candidate"]["template"].count("?") == 3
    assert specs["outstanding_kind_count"]["template"].count("?") == 3
    assert "ROW_NUMBER()" in specs["outstanding_payloads_active"]["template"]
    assert "state<>'QUARANTINED'" in specs["outstanding_payloads_active"]["template"]
    assert "state<>'QUARANTINED'" not in specs["outstanding_payloads_recovery"]["template"]
    assert readonly(bind("SELECT ? AS cluster", [CLUSTER])) == "SELECT 'dev_perf_v1' AS cluster"
    for invalid in ("DELETE FROM ct_demands", "SELECT 1; DROP TABLE ct_demands", "SELECT 1 FOR UPDATE",
                    "SELECT 1 FOR SHARE", "SELECT 1 LOCK IN SHARE MODE", "SET SESSION max_execution_time=1"):
        try:
            readonly(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Non-read-only SQL accepted")
    print("Offline source-query and SQL guard checks passed; no JVM/MySQL contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="current-perf1000")
    parser.add_argument("--endpoints", type=int, default=16, help="1..16 real endpoints for channelBatch allocationRows")
    parser.add_argument("--channel", help="Optional actual populated dev_perf_v1 channel UUID")
    parser.add_argument("--known-transfer", action="append", default=[], help="Optional real local-known transfer UUID; no guess from SQL ownership")
    parser.add_argument("--include-recovery", action="store_true", help="Also explain exact non-active recovery branch (64 rows/endpoint)")
    parser.add_argument("--analyze", action="store_true", help="Include EXPLAIN ANALYZE actual execution after measurement")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--execute", action="store_true", help="Perform real read-only collection; default is offline template preview")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label) or not 1 <= args.endpoints <= 16 or not 1 <= args.timeout <= 120 or len(args.known_transfer) > 1024:
        parser.error("Invalid bounded diagnostic parameters")
    if len(set(args.known_transfer)) != len(args.known_transfer):
        parser.error("Duplicate known transfer IDs")
    if args.channel:
        args.channel = str(uuid.UUID(args.channel))
    args.known_transfer = [str(uuid.UUID(value)) for value in args.known_transfer]
    source_bytes = SOURCE.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    specs = source_queries(source_bytes.decode(), args.endpoints, len(args.known_transfer))
    if args.self_test:
        self_test(specs)
        return 0
    if not args.execute:
        print(json.dumps({"mode": "OFFLINE_TEMPLATE_PREVIEW_NO_BACKEND_ACCESS", "source": str(SOURCE),
            "source_sha256": source_sha256, "query_specs": specs}, indent=2))
        return 0
    return Explain(args, specs, source_sha256).run()


if __name__ == "__main__":
    sys.exit(main())
