#!/usr/bin/env python3
"""Serial, fresh-world validation of the explicitly approved discovery fix.

Offline by default. Execute only after ROOT has released the native/build window.
Historical f3/3647 evidence and retained worlds are references, never replayed.
Functional/provenance gates here do not replace the frozen performance targets.
"""
from datetime import datetime, timezone
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rc_runtime_identity import approved_pair, manifest_identity

REVISION = "0113ef30f2269f9ea51e7c15e585792828fd2a51"
JAR = "70a02e49900dee34fc996bfcf95360689ea9e42c35996c581c52df2ee6fdb07c"
AGENT_ARTIFACTS = {
    "asm-9.8.jar": "876eab6a83daecad5ca67eb9fcabb063c97b5aeb8cf1fca7a989ecde17522051",
    "rc-probe-agent.jar": "45c3fb29362eeda302051ec1f32641c5e6fabd79e395979dd9b999c9217cdebb",
    "rc-probe-stats.jar": "ca2e9a074dfe0ef276fcffca19e44cd001cd43a8df192ece7ba91d9658f514ee",
}
STAGES = ("freeze", "native_v2", "fe3", "resource_batch", "resource_fast",
          "smoke60", "full3600", "history_post_stop", "offline_summary")
SOURCE_NAMES = (
    "scripts/analysis/run-rc-discovery-followup.py",
    "scripts/analysis/rc_runtime_identity.py",
    "scripts/analysis/freeze-rc-v2-probe.py",
    "scripts/analysis/validate-rc-probe-v2.py",
    "scripts/analysis/run-rc-v2-stage.py",
    "scripts/analysis/run-rc-v2-soak.py",
    "scripts/analysis/rc-soak-history-audit.py",
    "scripts/analysis/run-rc-f3-fast-resource-after-soak.py",
    "scripts/analysis/summarize-rc-soak.py",
    "scripts/rc-probe-benchmark.py", "scripts/rc-probe-mix.py", "scripts/rc-soak.py",
    "scripts/optimization-benchmark.py", "scripts/optimization-resource-mix.py",
    "scripts/optimization-container-benchmark.py", "scripts/optimization-monitor.py",
    "scripts/rcon.py", "scripts/configure-optimization.py", "scripts/start-frozen-dev.sh",
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def meta(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def evidence_path(value):
    path = Path(value)
    path = path if path.is_absolute() else ROOT / path
    if path.is_symlink():
        raise ValueError("No symlink evidence")
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError("Repository regular evidence required")
    return path


def read_ref(ref):
    path = evidence_path(ref["path"])
    if sha(path) != ref["sha256"]:
        raise ValueError("Closed evidence SHA mismatch")
    return path, json.loads(path.read_text())


def expected_flags():
    return ["--expected-revision", REVISION, "--expected-jar-sha256", JAR]


def stage_command(manifest, tag, phase, mode="fast"):
    suffix = ("-b-v2" if mode == "batch" else "-f-v2") if phase == "mix" else ""
    label = ("resource-mix-rc-" if phase == "mix" else "rc-fe-v2-") + tag + suffix
    if len(label) > 32:
        raise ValueError("Bounded unique workload label required")
    return ["python3", "scripts/analysis/run-rc-v2-stage.py", "--execute",
            "--manifest", str(manifest), "--tree-manifest", str(manifest),
            *expected_flags(), "--phase", phase, "--mode", mode, "--label", label]


def soak_command(manifest, tag, kind):
    return ["python3", "scripts/analysis/run-rc-v2-soak.py", "--execute",
            "--manifest", str(manifest), *expected_flags(), "--kind", kind,
            "--label", "rc-soak-v2-" + tag + "-" + kind]


def require_closed_child(data, manifest_ref, *, phase=None, kind=None):
    if (data.get("passed") is not True or data.get("functional_passed") is not True
            or data.get("qualified_passed") is not True or data.get("state") != "COMPLETE"
            or not data.get("utc_end") or data.get("runtime_revision") != REVISION
            or data.get("runtime_manifest") != manifest_ref
            or data.get("all_own_launchers_exited_and_locks_free") is not True
            or set(data.get("own_launcher_exits", {})) != set("ABC")
            or any(row.get("exit_code") != 0 for row in data["own_launcher_exits"].values())
            or any(data.get(key, {}).get("matches_expected") is not True
                   for key in ("source_before", "source_after_workload", "source_after_stop"))):
        raise ValueError("Child functional/source/identity/normal-stop gate failed")
    identity = data.get("expected_runtime_identity", {})
    if identity.get("source_revision") != REVISION or identity.get("JAR_sha256") != JAR:
        raise ValueError("Child omitted the explicitly expected runtime pair")
    if phase is not None and (data.get("phase") != phase or data.get("samples") != (3 if phase == "fe" else 1)):
        raise ValueError("Complete n1 FE3/resource sample count required")
    if kind is not None and (data.get("kind") != kind or data.get("sixty_minute_gate") is not (kind == "full")):
        raise ValueError("Smoke/full actual-duration gate mismatch")


def stopped_gate():
    """No backend or RCON requests: locks, selected /proc identity, loopback ports."""
    path = ROOT / "scripts/configure-optimization.py"
    spec = importlib.util.spec_from_file_location("rc_discovery_stopped_gate", path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    handles = []
    try:
        for server, port in (("A", 25575), ("B", 25576), ("C", 25577), ("perf", 25578)):
            handle = (ROOT / "scratch" / ("server-" + server + ".launch.lock")).open("a")
            handles.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if config.running(server):
                raise ValueError("Selected supervised JVM active; do not continue")
            for selected in (port, port - 10):
                with socket.socket() as check:
                    check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    check.bind(("127.0.0.1", selected))
                    check.listen(1)
        return {"utc": utc(), "selected": ["A", "B", "C", "perf"],
                "all_launch_locks_free_no_selected_JVM_and_ports_free": True}
    finally:
        for handle in handles:
            handle.close()


def self_test():
    approved_pair(REVISION, JAR)
    manifest = {"path": "reports/fake-manifest.json", "sha256": "a" * 64}
    sample = {"passed": True, "functional_passed": True, "qualified_passed": True,
              "state": "COMPLETE", "utc_end": "closed", "runtime_revision": REVISION,
              "runtime_manifest": manifest, "all_own_launchers_exited_and_locks_free": True,
              "own_launcher_exits": {server: {"exit_code": 0} for server in "ABC"},
              "expected_runtime_identity": {"source_revision": REVISION, "JAR_sha256": JAR},
              "phase": "fe", "samples": 3,
              **{key: {"matches_expected": True} for key in ("source_before", "source_after_workload", "source_after_stop")}}
    require_closed_child(sample, manifest, phase="fe")
    for key, wrong in (("passed", False), ("runtime_revision", "0" * 40), ("samples", 2),
                       ("all_own_launchers_exited_and_locks_free", False),
                       ("own_launcher_exits", {"A": {"exit_code": 0}})):
        changed = dict(sample, **{key: wrong})
        try:
            require_closed_child(changed, manifest, phase="fe")
        except ValueError:
            pass
        else:
            raise AssertionError("Bad closed child accepted: " + key)
    commands = [stage_command(Path("manifest"), "0113ef3", "fe"),
                stage_command(Path("manifest"), "0113ef3", "mix", "batch"),
                stage_command(Path("manifest"), "0113ef3", "mix"),
                soak_command(Path("manifest"), "0113ef3", "smoke"),
                soak_command(Path("manifest"), "0113ef3", "full")]
    for argv in commands:
        assert argv[argv.index("--expected-revision") + 1] == REVISION
        assert argv[argv.index("--expected-jar-sha256") + 1] == JAR
    assert all(len(argv[argv.index("--label") + 1]) <= 32 for argv in commands)
    print("PASS: offline exact pair, command composition, complete-child and stop/source boundaries")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--native-matrix", type=Path)
    parser.add_argument("--agent-manifest", type=Path)
    parser.add_argument("--expected-revision")
    parser.add_argument("--expected-jar-sha256")
    parser.add_argument("--run-tag", default="0113ef3")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.execute:
        print(json.dumps({"execution": "NOT_RUN", "order": STAGES,
                          "required_runtime": approved_pair(REVISION, JAR),
                          "requires": "explicit expected pair, closed native matrix164, same v2 agent, ROOT live-window release"}))
        return 0
    if (args.native_matrix is None or args.agent_manifest is None
            or (args.expected_revision, args.expected_jar_sha256) != (REVISION, JAR)
            or not re.fullmatch(r"0113ef3(?:-[a-z0-9]{1,3})?", args.run_tag)):
        parser.error("Explicit0113/70a pair, matrix164, v2 manifest and bounded fresh run-tag required")
    if any(key in os.environ for key in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI")):
        raise ValueError("Backend override forbidden")
    matrix_path = evidence_path(args.native_matrix)
    agent_path = evidence_path(args.agent_manifest)
    matrix = json.loads(matrix_path.read_text())
    if not (matrix.get("passed") is True and matrix.get("full_matrix_gate") is True
            and matrix.get("source_and_locks_unchanged") is True and matrix.get("actual_required_tests_passed") == 164):
        raise ValueError("Closed qualifying native matrix164 required before freeze")
    if not matrix.get("combinations") or any(row.get("mod_JAR", {}).get("sha256") != JAR for row in matrix["combinations"]):
        raise ValueError("Native matrix artifact is not the approved0113 build")
    agent = json.loads(agent_path.read_text())
    if (agent.get("recorder_revision") != "v2_mod_roots"
            or {Path(row["path"]).name: row["sha256"] for row in agent.get("artifacts", [])} != AGENT_ARTIFACTS):
        raise ValueError("Existing unchanged v2 agent required")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    target = ROOT / "reports/rc-20261017" / ("discovery-followup-" + args.run_tag + "-" + stamp + ".json")
    archive = ROOT / "reports/raw" / ("discovery-followup-tools-" + stamp)
    archive.mkdir(parents=True, exist_ok=False)
    sources = []
    for name in SOURCE_NAMES:
        source = ROOT / name
        dest = archive / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        if sha(source) != sha(dest):
            raise ValueError("As-run source archive mismatch")
        sources.append({"source": meta(source), "archive": meta(dest)})
    report = {"schema": 1, "passed": False, "state": "STARTING", "utc_start": utc(),
              "controller": meta(Path(__file__).resolve()), "expected_runtime_identity": approved_pair(REVISION, JAR),
              "native_matrix": meta(matrix_path), "agent_manifest": meta(agent_path),
              "run_tag": args.run_tag, "archived_tool_sources": sources, "failures": [],
              "runs": [{"name": name, "state": "NOT_RUN"} for name in STAGES],
              "scope": ["New0113 candidate; original f3 and3647/1ae raw values and retained assets are unchanged.",
                        "n1 FE40probes/30warm/120steady in each of3 layouts; resource B/FAST each n1 with unchanged inputs.",
                        "Fresh smoke60 never satisfies60min; fresh full requires3600s actual input, separate drain and normal stop.",
                        "Functional/provenance completion is separate from the unchanged frozen SQL/latency/main-thread performance goals.",
                        "No concurrent extra RCON/SQL observers or build. History only after full normal stop; offline summary last."]}

    def save():
        pending = target.with_suffix(".json.pending")
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.replace(target)

    def unchanged_tools():
        for row in sources:
            if sha(ROOT / row["source"]["path"]) != row["source"]["sha256"]:
                raise ValueError("As-run controller/workload helper changed; no later start")

    manifest_path = None
    full_controller = None
    history_path = None
    try:
        if target.exists():
            raise ValueError("Never overwrite evidence")
        save()
        for run in report["runs"]:
            name = run["name"]
            unchanged_tools()
            run["pre_stage_stopped_gate"] = stopped_gate()
            if name == "freeze":
                argv = ["python3", "scripts/analysis/freeze-rc-v2-probe.py", "--execute", "--profile", "final",
                        "--agent-manifest", str(agent_path), "--native-matrix", str(matrix_path),
                        "--expected-required-tests", "164", *expected_flags()]
            elif name == "native_v2":
                argv = ["python3", "scripts/analysis/validate-rc-probe-v2.py", "--execute", "--manifest", str(manifest_path)]
            elif name in ("fe3", "resource_batch", "resource_fast"):
                argv = stage_command(manifest_path, args.run_tag, "fe" if name == "fe3" else "mix",
                                     "batch" if name == "resource_batch" else "fast")
            elif name in ("smoke60", "full3600"):
                argv = soak_command(manifest_path, args.run_tag, "smoke" if name == "smoke60" else "full")
            elif name == "history_post_stop":
                argv = ["python3", "scripts/analysis/rc-soak-history-audit.py", "--execute",
                        "--soak-controller", str(full_controller), *expected_flags()]
            else:
                prefix = ROOT / "reports/rc-20261017" / ("soak-final-" + args.run_tag + "-v2-" + stamp)
                argv = ["python3", "scripts/analysis/summarize-rc-soak.py", "--controller", str(full_controller),
                        "--history-report", str(history_path), "--output-prefix", str(prefix)]
            log = ROOT / "logs" / ("rc-discovery-" + args.run_tag + "-" + name + "-" + stamp + ".log")
            run.update(state="RUNNING", command=argv, utc_start=utc(), observer_start=time.monotonic(), log=str(log.relative_to(ROOT)))
            report["state"] = "RUNNING_" + name
            save()
            print("RC_DISCOVERY_STAGE_START " + name, flush=True)
            with log.open("x") as output:
                child = subprocess.run(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
            run.update(exit_code=child.returncode, utc_end=utc(), observer_end=time.monotonic())
            save()
            try:
                completion = json.loads(log.read_text().splitlines()[-1])
            except (IndexError, json.JSONDecodeError) as error:
                run["completion_decode_error"] = type(error).__name__ + ": " + str(error)
                raise ValueError("Child completion absent/invalid; later stages NOT_RUN: " + name) from error
            run["completion"] = completion
            if child.returncode != 0:
                # Capture any closed failure refs without promoting their gates.
                for key in ("controller", "report"):
                    ref = completion.get(key)
                    if isinstance(ref, dict) and "path" in ref and "sha256" in ref:
                        path, _ = read_ref(ref)
                        run["failed_" + key] = meta(path)
                save()
                raise ValueError("Child exited nonzero; retain evidence and later NOT_RUN: " + name)
            if name == "freeze":
                manifest_path, seal = read_ref({"path": completion["manifest"], "sha256": completion["sha256"]})
                manifest_identity(seal, REVISION, JAR)
                frozen_matrix_path, _ = read_ref(seal["final_native_matrix"])
                if frozen_matrix_path != matrix_path:
                    raise ValueError("Freeze used another matrix")
                report["runtime_manifest"] = meta(manifest_path)
            elif name == "native_v2":
                probe_path, data = read_ref({"path": completion["report"], "sha256": completion["sha256"]})
                if (completion.get("passed") is not True or data.get("passed") is not True
                        or data.get("launcher_exit") != 0 or data.get("manifest_sha256") != sha(manifest_path)
                        or any(data.get(key, {}).get("matches_expected") is not True for key in ("source_before", "source_after_stop"))):
                    raise ValueError("Native v2 transform/source/normal-stop proof failed")
                run["validation_report"] = meta(probe_path)
            elif name in ("fe3", "resource_batch", "resource_fast", "smoke60", "full3600"):
                path, data = read_ref(completion["controller"])
                require_closed_child(data, meta(manifest_path),
                                     phase="fe" if name == "fe3" else "mix" if name.startswith("resource_") else None,
                                     kind="smoke" if name == "smoke60" else "full" if name == "full3600" else None)
                raw_path, raw = read_ref(data["raw_report"])
                if completion.get("passed") is not True or raw.get("passed") is not True:
                    raise ValueError("Raw functional workload failed")
                run.update(child_controller=meta(path), raw_report=meta(raw_path))
                if name == "full3600":
                    full_controller = path
            elif name == "history_post_stop":
                history_path, data = read_ref(completion["report"])
                if completion.get("passed") is not True or data.get("passed") is not True or data.get("controller") != meta(full_controller):
                    raise ValueError("Closed full-cohort history audit failed")
                run["history_report"] = meta(history_path)
            else:
                outputs = [prefix.with_suffix(extension) for extension in (".json", ".csv", ".md")]
                if any(not path.is_file() for path in outputs):
                    raise ValueError("Expected all three offline summary artifacts")
                run["artifacts"] = [meta(path) for path in outputs]
            unchanged_tools()
            run["post_stage_stopped_gate"] = stopped_gate()
            run["state"] = "PASS"
            save()
            print("RC_DISCOVERY_STAGE_END " + name + " PASS", flush=True)
        report.update(state="COMPLETE", passed=True)
    except BaseException as error:
        report["failures"].append(type(error).__name__ + ": " + str(error))
        report["state"] = "FAILED_RETAINED"
        running = next((run for run in report["runs"] if run["state"] == "RUNNING"), None)
        if running is not None:
            running["state"] = "FAILED_RETAINED"
        try:
            report["failure_stopped_gate"] = stopped_gate()
        except Exception as guard_error:
            report["failure_stopped_gate"] = {"passed": False, "error": type(guard_error).__name__ + ": " + str(guard_error),
                                              "instruction": "Stop; operator review required. No forcekill/config restore/asset replay."}
        print("RC_DISCOVERY_FAILED_RETAINED " + str(error), flush=True)
    finally:
        report["utc_end"] = utc()
        save()
    print(json.dumps({"sequence": meta(target), "passed": report["passed"], "state": report["state"]}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
