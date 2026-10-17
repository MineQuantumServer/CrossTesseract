#!/usr/bin/env python3
"""Normal lifecycle for fresh v2 smoke60s/full3600s; offline by default.

The existing rc-soak.py owns the sole workload RCON observer. This controller
prepares stopped development properties and starts/stops only its own JVMs.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PORTS = {"A": 25575, "B": 25576, "C": 25577}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--kind", choices=("smoke", "full"), required=True)
    p.add_argument("--label", default=None)
    a = p.parse_args()
    if not a.execute:
        print(json.dumps({"execution": "NOT_RUN", "kind": a.kind,
                          "observation_seconds": 60 if a.kind == "smoke" else 3600,
                          "requires": "--execute --manifest --label; all primary windows completed"}))
        return 0
    import re
    if a.manifest is None or not a.label or not re.fullmatch(r"rc-soak-[a-z0-9-]{1,24}", a.label):
        p.error("Explicit reviewed final manifest/new rc-soak label required")
    if any(key in os.environ for key in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI")):
        raise ValueError("Backend overrides forbidden")
    helper = load("rc_v2_soak_stage_functions", ROOT / "scripts/analysis/run-rc-v2-stage.py")
    cfg = load("rc_v2_soak_config", ROOT / "scripts/configure-optimization.py")
    rcon = load("rc_v2_soak_lifecycle_rcon", ROOT / "scripts/rcon.py")
    manifest = a.manifest.resolve(strict=True)
    seal = json.loads(manifest.read_text())
    if seal["source_revision"] != "3647dede64cfc23e054dfa962fd127787cae14ec":
        raise ValueError("Final tested 3647 main only; never silently retarget")
    if seal["artifacts"]["JAR"]["sha256"] != "1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f":
        raise ValueError("Final actual JAR identity required")
    expected = {row["relative_path"][5:]: row["sha256"]
                for row in seal["artifacts"]["source_main"]["files"] if row["relative_path"].startswith("java/")}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    target = ROOT / "reports/rc-20261017" / (a.label + "-controller-" + stamp + ".json")
    seconds, capacity = (60, 64000) if a.kind == "smoke" else (3600, 2000000)
    report = {"passed": False, "functional_passed": False, "qualified_passed": False,
              "utc_start": helper.utc(), "kind": a.kind, "label": a.label,
              "requested_observation_seconds": seconds, "buffers.fe": capacity,
              "runtime_manifest": helper.meta(manifest), "runtime_revision": seal["source_revision"],
              "controller": helper.meta(Path(__file__).resolve()), "lifecycle": [], "failures": [],
              "scope": "Smoke never satisfies60min. Full requires3600s actual concurrent input, separate bounded tail drain, "
                       "strict checkout source pre/post and actual frozen runtime bytes. Single observer. Wall-scope histograms "
                       "include selected mod root cycles; uninstrumented GUI/other entries are not all mod CPU."}
    processes = {}

    def save():
        pending = target.with_suffix(".json.pending")
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.replace(target)

    def request(server, command):
        event = {"server": server, "command": command, "start": time.monotonic(), "utc": helper.utc()}
        report["lifecycle"].append(event)
        try:
            event["reply"] = rcon.command(PORTS[server], command, timeout=5)
            return event["reply"]
        except Exception as error:
            event["uncertain_no_replay"] = repr(error)
            raise
        finally:
            event["end"] = time.monotonic()

    try:
        if target.exists() or next((ROOT / "scratch").glob("rc-soak-" + a.label + "-*"), None):
            raise ValueError("Never overwrite or reuse retained soak evidence")
        save()
        report["source_before"] = helper.source_point(expected)
        if not report["source_before"]["matches_expected"]:
            raise ValueError("Main Java differs from final freeze; no startup")
        agent_path = Path(seal["probe_manifest"])
        agent = json.loads(agent_path.read_text())
        if helper.sha(agent_path) != seal["probe_manifest_sha256"] or agent.get("recorder_revision") != "v2_mod_roots":
            raise ValueError("Frozen v2 agent manifest mismatch")
        for row in agent["artifacts"]:
            if helper.sha(Path(row["path"])) != row["sha256"]:
                raise ValueError("Frozen agent dependency changed")
        if helper.sha(Path(seal["artifacts"]["JAR"]["path"])) != seal["artifacts"]["JAR"]["sha256"]:
            raise ValueError("Frozen JAR changed")
        handles = []
        try:
            for server in PORTS:
                handle = (ROOT / "scratch" / ("server-" + server + ".launch.lock")).open("a")
                handles.append(handle)
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if cfg.running(server):
                    raise ValueError("Selected JVM still active; no config changes")
                for port in (PORTS[server], PORTS[server] - 10):
                    with socket.socket() as test:
                        test.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        test.bind(("127.0.0.1", port))
                        test.listen(1)
            argv = ["python3", "scripts/configure-optimization.py", "--label", a.label, "--mode", "fast"]
            prepared = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
            report["preparation"] = {"argv": argv, "exit": prepared.returncode, "stdout": prepared.stdout, "stderr": prepared.stderr}
            if prepared.returncode:
                raise ValueError("Fresh loopback fixture preparation rejected")
            keys = dict(helper.DEFAULTS, **{"buffers.fe": str(capacity)})
            report["effective_test_keys"] = keys
            for server in PORTS:
                path = ROOT / ("run-" + server) / "cross-tesseract.properties"
                cfg.update(path, keys)
                values = cfg.properties(path)
                if any(values.get(key) != value for key, value in keys.items()):
                    raise ValueError("Prepared defaults/capacity mismatch")
        finally:
            for handle in handles:
                handle.close()
        for server in PORTS:
            entry = seal["launches"][server]
            if helper.sha(Path(entry["launcher"])) != entry["launcher_sha256"] or helper.sha(Path(entry["vm_args"])) != entry["vm_args_sha256"]:
                raise ValueError("Frozen launch changed")
            for kind in ("classes", "resources"):
                wanted = {row["relative_path"]: row["sha256"] for row in seal["artifacts"][kind]["files"]}
                if helper.contents(Path(entry["launcher"]).parent / kind) != wanted:
                    raise ValueError("Frozen launch contents changed")
            log = ROOT / "logs" / (a.label + "-" + stamp + "-" + server + ".log")
            with log.open("x") as output:
                process = subprocess.Popen(["bash", "scripts/start-frozen-dev.sh", server, entry["launcher"]], cwd=ROOT,
                                           stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            processes[server] = process
            report["lifecycle"].append({"action": "start_frozen_once", "server": server, "PID": process.pid,
                                         "launcher": entry["launcher"], "launcher_sha256": entry["launcher_sha256"],
                                         "vm_args": entry["vm_args"], "vm_args_sha256": entry["vm_args_sha256"],
                                         "log": str(log.relative_to(ROOT)), "utc": helper.utc()})
            save()
        deadline = time.monotonic() + 120
        ready = set()
        while time.monotonic() < deadline and ready != set(PORTS):
            for server, process in processes.items():
                if process.poll() is not None:
                    raise RuntimeError("Frozen JVM exited before workload")
                if server not in ready:
                    try:
                        if "STATUS online" in request(server, "ct_test status"):
                            ready.add(server)
                    except OSError:
                        pass
            if ready != set(PORTS):
                time.sleep(.5)
        if ready != set(PORTS):
            raise RuntimeError("Soak startup deadline")
        argv = ["python3", "scripts/rc-soak.py", "--execute", "--probe-manifest", str(manifest),
                "--label", a.label, "--world-prefix", "world-opt-" + a.label,
                "--operator-revision", seal["source_revision"], "--seconds", str(seconds)]
        if a.kind == "smoke":
            argv.append("--smoke")
        log = ROOT / "logs" / (a.label + "-" + stamp + "-driver.log")
        report.update(state="SOAK_WORKLOAD_RUNNING", argv=argv, driver=helper.meta(ROOT / "scripts/rc-soak.py"),
                      driver_log=str(log.relative_to(ROOT)), workload_utc_start=helper.utc())
        save()
        with log.open("x") as output:
            result = subprocess.run(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        report.update(workload_exit=result.returncode, workload_utc_end=helper.utc(), source_after_workload=helper.source_point(expected))
        added = list((ROOT / "scratch").glob("rc-soak-" + a.label + "-*/report.json"))
        if len(added) != 1:
            raise ValueError("Expected one new raw soak report")
        raw = added[0]
        data = json.loads(raw.read_text())
        report.update(raw_report=helper.meta(raw), raw_passed=data.get("passed"), sixty_minute_gate=data.get("60min_gate"))
        report["functional_passed"] = result.returncode == 0 and data.get("passed") is True and data.get("60min_gate") is (a.kind == "full")
        if not report["functional_passed"]:
            raise ValueError("Actual soak failed/incomplete; no replay or asset deletion")
        if not report["source_after_workload"]["matches_expected"]:
            raise ValueError("Checkout Java changed during soak")
    except BaseException as error:
        report["failures"].append(type(error).__name__ + ": " + str(error))
    finally:
        for server, process in processes.items():
            if process.poll() is None:
                try:
                    request(server, "stop")
                except Exception:
                    pass
        deadline = time.monotonic() + 120
        while any(process.poll() is None for process in processes.values()) and time.monotonic() < deadline:
            time.sleep(.5)
        report["own_launcher_exits"] = {server: {"exit_code": process.poll(),
            "launcher": seal["launches"][server]["launcher"], "launcher_sha256": seal["launches"][server]["launcher_sha256"]}
            for server, process in processes.items()}
        failed_exit = {server: process.poll() for server, process in processes.items() if process.poll() not in (None, 0)}
        if failed_exit:
            report["failures"].append("Own launcher normal-stop exit was nonzero: " + str(failed_exit))
        if any(process.poll() is None for process in processes.values()):
            report["failures"].append("Normal-stop deadline; no force kill")
        else:
            handles = []
            try:
                for server in processes:
                    handle = (ROOT / "scratch" / ("server-" + server + ".launch.lock")).open("a")
                    handles.append(handle)
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                report["all_own_launchers_exited_and_locks_free"] = True
            except BlockingIOError:
                report["failures"].append("Selected launch lock remains held")
            finally:
                for handle in handles:
                    handle.close()
        report["source_after_stop"] = helper.source_point(expected)
        report["qualified_passed"] = report["functional_passed"] and all(report.get(key, {}).get("matches_expected") is True
            for key in ("source_before", "source_after_workload", "source_after_stop")) and not report["failures"]
        report.update(passed=report["qualified_passed"], utc_end=helper.utc(), state="COMPLETE" if report["qualified_passed"] else "FAILED_RETAINED")
        if report.get("raw_report"):
            archive = target.with_suffix("")
            archive.mkdir()
            report["archived_raw_evidence"] = {}
            for name in ("manifest.json", "report.json", "events.jsonl"):
                source = ROOT / report["raw_report"]["path"]
                source = source.parent / name
                if source.is_file():
                    dest = archive / name
                    shutil.copyfile(source, dest)
                    if helper.sha(source) != helper.sha(dest):
                        raise ValueError("Evidence archive byte mismatch")
                    report["archived_raw_evidence"][name] = dict(helper.meta(dest), bytes=dest.stat().st_size)
        save()
    print(json.dumps({"controller": helper.meta(target), "passed": report["passed"], "raw_report": report.get("raw_report")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
