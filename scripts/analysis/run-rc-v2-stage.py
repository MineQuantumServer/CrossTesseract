#!/usr/bin/env python3
"""Explicit single-observer RC v2 FE/mixed/short-ablation stage; offline by default.

Run only after the operator releases the native/build window. Every invocation
uses new worlds and retains its own normal start/stop and strict Java-tree proof.
Runtime frozen bytes and the concurrent checkout source audit are separate facts.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rc_runtime_identity import manifest_identity, legacy_stage_pair
PORTS = {"A": 25575, "B": 25576, "C": 25577}
DEFAULTS = {"transfer.batchMillis": "200", "transfer.activeWakeMillis": "50",
            "transfer.notificationMillis": "100", "limits.localWorkBudgetMicros": "2000",
            "limits.endpointChecksPerTick": "16", "buffers.fe": "2000000"}


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def meta(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def contents(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Regular source/artifact tree required")
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("No source/artifact symlinks")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = sha(path)
    return result


def source_point(expected):
    start = time.monotonic()
    actual = contents(ROOT / "src/main/java")
    return {"utc": utc(), "observer_start": start, "observer_end": time.monotonic(),
            "files": actual,
            "canonical_sha256": hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "matches_expected": actual == expected,
            "added": sorted(actual.keys() - expected.keys()), "removed": sorted(expected.keys() - actual.keys()),
            "changed": sorted(name for name in actual.keys() & expected.keys() if actual[name] != expected[name])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--tree-manifest", type=Path,
                        help="Final frozen main-source manifest, also used while running old f3 bytes")
    parser.add_argument("--expected-revision")
    parser.add_argument("--expected-jar-sha256")
    parser.add_argument("--phase", choices=("fe", "mix", "ablation"), default="fe")
    parser.add_argument("--mode", choices=("fast", "batch"), default="fast")
    parser.add_argument("--variant", choices=("default", "notification1000", "active200"), default="default")
    parser.add_argument("--label")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"execution": "NOT_RUN", "phase": args.phase, "variant": args.variant,
                          "requires": "--execute --manifest --tree-manifest --label; operator quiet window"}))
        return 0
    if (args.manifest is None or args.tree_manifest is None or not args.label
            or not re.fullmatch(r"[a-z0-9-]{1,32}", args.label)
            or not args.label.startswith("resource-mix-" if args.phase == "mix" else "rc-fe-")
            or (args.phase != "ablation" and args.variant != "default")
            or (args.phase == "ablation" and args.mode != "fast")):
        parser.error("Explicit bounded RC stage arguments required")
    if any(name in os.environ for name in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI")):
        raise ValueError("Backend overrides forbidden")
    manifest_path = args.manifest.resolve(strict=True)
    tree_path = args.tree_manifest.resolve(strict=True)
    for path in (manifest_path, tree_path):
        if not path.is_relative_to(ROOT) or path.is_symlink():
            raise ValueError("Repository regular manifests only")
    seal = json.loads(manifest_path.read_text())
    tree_seal = json.loads(tree_path.read_text())
    explicit_identity = args.expected_revision is not None and args.expected_jar_sha256 is not None
    if (args.expected_revision is None) != (args.expected_jar_sha256 is None):
        raise ValueError("Supply both expected revision and expected JAR SHA")
    if not explicit_identity:
        args.expected_revision, args.expected_jar_sha256 = legacy_stage_pair(seal)
    runtime_identity = manifest_identity(seal, args.expected_revision, args.expected_jar_sha256, allow_baseline=True)
    runtime_identity["operator_explicit_pair"] = explicit_identity
    checkout_identity = manifest_identity(tree_seal, tree_seal["source_revision"], tree_seal["artifacts"]["JAR"]["sha256"])
    if sha(Path(seal["artifacts"]["JAR"]["path"])) != args.expected_jar_sha256:
        raise ValueError("Actual frozen runtime JAR differs from explicit expected identity")
    expected = {row["relative_path"][5:]: row["sha256"]
                for row in tree_seal["artifacts"]["source_main"]["files"] if row["relative_path"].startswith("java/")}
    if len(expected) < 20:
        raise ValueError("Complete final Java-tree manifest required")
    probe_manifest = Path(seal["probe_manifest"])
    if sha(probe_manifest) != seal["probe_manifest_sha256"]:
        raise ValueError("Frozen agent manifest changed")
    agent = json.loads(probe_manifest.read_text())
    if agent.get("recorder_revision") != "v2_mod_roots":
        raise ValueError("Both compared runtimes require the same v2 agent")
    for artifact in agent["artifacts"]:
        if sha(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("Frozen agent dependency changed")
    preparation = load("rc_v2_fixture_preparation", ROOT / "scripts/configure-optimization.py")
    rcon = load("rc_v2_lifecycle_rcon", ROOT / "scripts/rcon.py")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    target = ROOT / "reports/rc-20261017" / (args.label + "-controller-" + stamp + ".json")
    report = {"utc_start": utc(), "passed": False, "functional_passed": False, "qualified_passed": False,
              "phase": args.phase, "mode": args.mode, "variant": args.variant,
              "runtime_manifest": meta(manifest_path), "runtime_revision": seal["source_revision"],
              "expected_runtime_identity": runtime_identity, "checkout_source_identity": checkout_identity,
              "runtime_identity_guard": meta(Path(__file__).with_name("rc_runtime_identity.py")),
              "checkout_source_guard_manifest": meta(tree_path), "source_guard_expected_revision": tree_seal["source_revision"],
              "controller": meta(Path(__file__).resolve()), "lifecycle": [], "failures": [],
              "scope": "n1; single RCON workload observer, normal stopped fresh-world config changes only. "
                       "Short ablations never replace the primary40/30/120 windows or frozen targets. "
                       "Raw functional evidence and complete checkout Java-tree qualification are separate."}
    processes = {}

    def save():
        temporary = target.with_suffix(".json.pending")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(target)

    def request(server, command):
        event = {"server": server, "command": command, "start": time.monotonic(), "utc": utc()}
        report["lifecycle"].append(event)
        try:
            event["reply"] = rcon.command(PORTS[server], command, timeout=5)
            return event["reply"]
        except Exception as error:
            event["uncertain_no_mutation_replay"] = type(error).__name__ + ": " + str(error)
            raise
        finally:
            event["end"] = time.monotonic()

    try:
        if target.exists():
            raise ValueError("Never overwrite evidence")
        save()
        report["source_before"] = source_point(expected)
        if not report["source_before"]["matches_expected"]:
            raise ValueError("Main Java source differs from final freeze; no JVM start")
        keys = dict(DEFAULTS)
        if args.variant == "notification1000":
            keys["transfer.notificationMillis"] = "1000"
        elif args.variant == "active200":
            keys["transfer.activeWakeMillis"] = "200"
        handles = []
        try:
            for server in PORTS:
                handle = (ROOT / "scratch" / ("server-" + server + ".launch.lock")).open("a")
                handles.append(handle)
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if preparation.running(server):
                    raise ValueError("Selected JVM still running; no config changes")
                for port in (PORTS[server], PORTS[server] - 10):
                    with socket.socket() as check:
                        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        check.bind(("127.0.0.1", port))
                        check.listen(1)
            command = ["python3", "scripts/configure-optimization.py", "--label", args.label, "--mode", args.mode]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            report["fixture_preparation"] = {"argv": command, "exit": result.returncode,
                                               "stdout": result.stdout, "stderr": result.stderr}
            if result.returncode:
                raise ValueError("Fresh isolated fixture preparation rejected")
            report["effective_test_keys"] = keys
            report["fixture_configs"] = {}
            for server in PORTS:
                path = ROOT / ("run-" + server) / "cross-tesseract.properties"
                preparation.update(path, keys)
                values = preparation.properties(path)
                if any(values.get(key) != value for key, value in keys.items()):
                    raise ValueError("Stopped fixture parameter mismatch")
                report["fixture_configs"][server] = {"config_sha256": sha(path), "server_id": values["server.id"],
                                                       "world": "world-opt-" + args.label + "-" + server}
        finally:
            for handle in handles:
                handle.close()
        save()
        for server in PORTS:
            entry = seal["launches"][server]
            for key, expected_key in (("launcher", "launcher_sha256"), ("vm_args", "vm_args_sha256")):
                if sha(Path(entry[key])) != entry[expected_key]:
                    raise ValueError("Frozen launcher/VM args changed")
            for kind in ("classes", "resources"):
                wanted = {row["relative_path"]: row["sha256"] for row in seal["artifacts"][kind]["files"]}
                if contents(Path(entry["launcher"]).parent / kind) != wanted:
                    raise ValueError("Frozen launch " + kind + " changed")
            log = ROOT / "logs" / (args.label + "-" + stamp + "-" + server + ".log")
            with log.open("x") as stream:
                process = subprocess.Popen(["bash", "scripts/start-frozen-dev.sh", server, entry["launcher"]], cwd=ROOT,
                                           stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            processes[server] = process
            report["lifecycle"].append({"action": "start_frozen_once", "server": server, "PID": process.pid,
                                         "launcher": entry["launcher"], "launcher_sha256": entry["launcher_sha256"],
                                         "vm_args": entry["vm_args"], "vm_args_sha256": entry["vm_args_sha256"],
                                         "log": str(log.relative_to(ROOT)), "utc": utc()})
            save()
        deadline = time.monotonic() + 120
        ready = set()
        while time.monotonic() < deadline and ready != set(PORTS):
            for server, process in processes.items():
                if process.poll() is not None:
                    raise RuntimeError("Frozen launcher exited before workload " + server)
                if server not in ready:
                    try:
                        if "STATUS online" in request(server, "ct_test status"):
                            ready.add(server)
                    except OSError:
                        pass
            if ready != set(PORTS):
                time.sleep(.5)
        if ready != set(PORTS):
            raise RuntimeError("Startup deadline; no repeated start")
        script = "scripts/rc-probe-mix.py" if args.phase == "mix" else "scripts/rc-probe-benchmark.py"
        seconds, probes = (60, 10) if args.phase == "ablation" else (120, 40)
        command = ["python3", script, "--execute", "--probe-manifest", str(manifest_path), "--label", args.label,
                   "--operator-revision", seal["source_revision"], "--warmup", "30", "--seconds", str(seconds), "--repeats", "1"]
        if args.phase != "mix":
            command += ["--probes", str(probes), "--scenarios", "mixed" if args.phase == "ablation" else "same,cross,mixed"]
        prefix = "optimization-rc-probe-mix-" if args.phase == "mix" else "optimization-rc-probe-"
        pattern = prefix + args.label + "-*.json"
        prior = set((ROOT / "reports").glob(pattern))
        if prior:
            raise ValueError("Same-label evidence exists; no replay/overwrite")
        log = ROOT / "logs" / (args.label + "-" + stamp + "-driver.log")
        report.update(state="WORKLOAD_RUNNING", command=command, workload_utc_start=utc(),
                      driver=meta(ROOT / script), driver_log=str(log.relative_to(ROOT)))
        save()
        with log.open("x") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        report.update(workload_exit=result.returncode, workload_utc_end=utc())
        report["source_after_workload"] = source_point(expected)
        added = set((ROOT / "reports").glob(pattern)) - prior
        if len(added) != 1:
            raise ValueError("Expected exactly one new raw report")
        raw = added.pop()
        data = json.loads(raw.read_text())
        report.update(raw_report=meta(raw), raw_passed=data.get("passed"), samples=len(data.get("samples", [])))
        expected_samples = 3 if args.phase == "fe" else 1
        report["functional_passed"] = result.returncode == 0 and data.get("passed") is True and report["samples"] == expected_samples
        if not report["functional_passed"]:
            raise ValueError("Native functional workload incomplete/failed; retain assets and raw")
        if not report["source_after_workload"]["matches_expected"]:
            raise ValueError("Checkout Java changed during workload; actual frozen-byte guard remains separate")
    except BaseException as error:
        report["failures"].append(type(error).__name__ + ": " + str(error))
    finally:
        for server, process in processes.items():
            if process.poll() is None:
                try:
                    request(server, "stop")
                except Exception:
                    pass  # Uncertain stop is recorded; never replay it or force kill.
        deadline = time.monotonic() + 120
        while any(process.poll() is None for process in processes.values()) and time.monotonic() < deadline:
            time.sleep(.5)
        alive = [server for server, process in processes.items() if process.poll() is None]
        report["own_launcher_exits"] = {server: {"exit_code": process.poll(), "launcher": seal["launches"][server]["launcher"],
            "launcher_sha256": seal["launches"][server]["launcher_sha256"]} for server, process in processes.items()}
        failed_exit = {server: process.poll() for server, process in processes.items() if process.poll() not in (None, 0)}
        if failed_exit:
            report["failures"].append("Own launcher normal-stop exit was nonzero: " + str(failed_exit))
        if alive:
            report["failures"].append("Normal-stop deadline; no force kill: " + ",".join(alive))
        else:
            handles = []
            try:
                for server in processes:
                    handle = (ROOT / "scratch" / ("server-" + server + ".launch.lock")).open("a")
                    handles.append(handle)
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                report["all_own_launchers_exited_and_locks_free"] = True
            except BlockingIOError:
                report["failures"].append("A selected launch lock remains held")
            finally:
                for handle in handles:
                    handle.close()
        report["source_after_stop"] = source_point(expected)
        report["qualified_passed"] = report["functional_passed"] and all(report.get(key, {}).get("matches_expected") is True
            for key in ("source_before", "source_after_workload", "source_after_stop")) and not report["failures"]
        report.update(utc_end=utc(), passed=report["qualified_passed"], state="COMPLETE" if report["qualified_passed"] else "FAILED_RETAINED")
        save()
    print(json.dumps({"controller": meta(target), "passed": report["passed"], "raw_report": report.get("raw_report")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
