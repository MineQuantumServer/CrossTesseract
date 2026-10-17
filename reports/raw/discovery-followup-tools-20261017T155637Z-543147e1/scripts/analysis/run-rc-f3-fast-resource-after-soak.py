#!/usr/bin/env python3
"""Append one matched f3 FAST resource window after the closed RC/v2 soak.

Offline by default. Preserve the original sequence and soak bytes. Back up the
stopped full-soak ABC configs, run the existing fresh-world stage once, then
restore those exact config bytes only under all three launch locks, with no
selected JVM, and with the expected added-stage configs still present. Worlds,
SQL and WAL are never restored, copied, deleted or reset by this controller.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SERVERS = ("A", "B", "C")
LABEL = "resource-mix-rc-f3f-v2"


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def meta(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def read_ref(ref):
    path = Path(ref["path"])
    if not path.is_absolute():
        path = ROOT / path
    if path.is_symlink():
        raise ValueError("Symlink evidence forbidden")
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT) or sha(path) != ref["sha256"]:
        raise ValueError("Closed evidence path/SHA mismatch")
    return path, json.loads(path.read_text())


def parse_properties(data):
    # Matches the existing isolated fixture helper, never prints any values.
    return dict(line.split("=", 1) for line in data.decode().splitlines()
                if "=" in line and not line.lstrip().startswith(("#", "!")))


def closed_controller(data):
    for key in ("passed", "functional_passed", "qualified_passed", "all_own_launchers_exited_and_locks_free"):
        if data.get(key) is not True:
            raise ValueError("Closed controller gate absent: " + key)
    if set(data.get("own_launcher_exits", {})) != set(SERVERS):
        raise ValueError("All three launcher exits required")
    if any(entry["exit_code"] != 0 for entry in data["own_launcher_exits"].values()):
        raise ValueError("Nonzero own launcher exit")


def load_preparation():
    path = ROOT / "scripts/configure-optimization.py"
    spec = importlib.util.spec_from_file_location("rc_post_soak_fixture_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def stopped_locks(preparation):
    handles = []
    try:
        for index, server in enumerate(SERVERS):
            handle = (ROOT / "scratch" / ("server-" + server + ".launch.lock")).open("a")
            handles.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if preparation.running(server):
                raise ValueError("Selected JVM running; no config copy/restore")
            for port in (25575 + index, 25565 + index):
                with socket.socket() as check:
                    check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    check.bind(("127.0.0.1", port))
                    check.listen(1)
        yield
    finally:
        for handle in handles:
            handle.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--sequence", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        a = b"#Minecraft server properties\n#date one\nlevel-name=one\npassword=x=y\n"
        b = a.replace(b"date one", b"date two")
        assert parse_properties(a) == parse_properties(b)
        assert parse_properties(a) != parse_properties(a.replace(b"level-name=one", b"level-name=two"))
        assert hashlib.sha256(a).digest() != hashlib.sha256(b).digest()
        print("PASS: date comments differ in raw bytes, real property changes differ semantically; offline only")
        return 0
    if not args.execute:
        print(json.dumps({"execution": "NOT_RUN", "order": "completed original full3600/normal stop -> fresh f3 FAST mixed n1 -> normal stop -> exact original stopped config restore", "requires": "--execute --sequence CLOSED_PASS"}))
        return 0
    if args.sequence is None:
        parser.error("Explicit closed sequence required")
    if any(key in os.environ for key in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI")):
        raise ValueError("Backend overrides forbidden")
    sequence_path = args.sequence.resolve(strict=True)
    if not sequence_path.is_relative_to(ROOT) or sequence_path.is_symlink():
        raise ValueError("Repository closed sequence required")
    sequence = json.loads(sequence_path.read_text())
    if sequence.get("passed") is not True or sequence.get("state") != "COMPLETE":
        raise ValueError("Original sequence must finish completely before this append")
    failed_parent = None
    if "continuation_of_failed_sequence" in sequence:
        failed_parent_path, failed_parent = read_ref(sequence["continuation_of_failed_sequence"])
        failed_runs = {run["name"]: run for run in failed_parent["runs"]}
        if (failed_parent.get("passed") is not False or failed_parent.get("state") != "FAILED_RETAINED"
                or failed_runs["smoke60"]["state"] != "FAILED_RETAINED"
                or failed_runs["full3600"]["state"] != "NOT_RUN"
                or sequence["f3_manifest"] != failed_parent["f3_manifest"]
                or sequence["final_manifest"] != failed_parent["final_manifest"]):
            raise ValueError("Different continuation evidence chain")
        for name, ref in sequence["prior_closed_children"].items():
            if ref != failed_runs[name]["child_controller"] or failed_runs[name]["state"] != "PASS":
                raise ValueError("Prior closed child reference changed")
            read_ref(ref)
    runs = {run["name"]: run for run in sequence["runs"]}
    if any(run["state"] != "PASS" or run.get("exit_code") != 0 for run in runs.values()):
        raise ValueError("Original children must all have completed EXIT0")
    full_path, full = read_ref(runs["full3600"]["child_controller"])
    closed_controller(full)
    if full.get("sixty_minute_gate") is not True:
        raise ValueError("Real completed 3600s gate required")
    full_raw_path, full_raw = read_ref(full["raw_report"])
    if not full_raw.get("passed") or full_raw.get("60min_gate") is not True:
        raise ValueError("Full soak raw evidence must pass")
    f3_path, f3 = read_ref(sequence["f3_manifest"])
    final_path, final = read_ref(sequence["final_manifest"])
    if f3["source_revision"] != "f3c59b772dcbd343596174c73093b2fef536f19c" or final["source_revision"] != "3647dede64cfc23e054dfa962fd127787cae14ec":
        raise ValueError("Exact actual frozen f3/final runtime revisions required")
    preparation = load_preparation()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    target = ROOT / "reports/rc-20261017" / ("post-soak-f3-fast-resource-" + stamp + ".json")
    # Configs contain local passwords. Preserve original bytes privately; only
    # paths/SHA and non-sensitive identity gates belong in public reports/Git.
    archive = ROOT / "scratch" / ("rc-private-post-soak-configs-" + stamp)
    archive.mkdir(mode=0o700, exist_ok=False)
    report = {"utc_start": utc(), "passed": False, "state": "STARTING", "controller": meta(Path(__file__).resolve()),
              "original_sequence": meta(sequence_path), "closed_full_soak_controller": meta(full_path),
              "closed_full_soak_raw": meta(full_raw_path), "f3_manifest": meta(f3_path), "final_manifest": meta(final_path),
              "actual_append_point": "After original full3600, full drain and normal ABC EXIT0; not part of the original in-memory plan.",
              "failures": [], "scope": "One extra same-v2 f3 FAST resource baseline. Original raw reports/worlds/SQL/WAL unchanged; only exact stopped config byte restoration after the fresh stage."}
    if failed_parent is not None:
        report["preserved_failed_parent"] = meta(failed_parent_path)

    def save():
        pending = target.with_suffix(".json.pending")
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.replace(target)

    backups = {}
    try:
        save()
        with stopped_locks(preparation):
            for server in SERVERS:
                for name in ("server.properties", "cross-tesseract.properties"):
                    path = ROOT / ("run-" + server) / name
                    if path.is_symlink():
                        raise ValueError("Regular isolated config files required")
                    data = path.read_bytes()
                    props = parse_properties(data)
                    expected = full_raw["identity"][server]
                    if name == "server.properties":
                        if props.get("level-name") != expected["level_name"] or props.get("server-ip") != "127.0.0.1":
                            raise ValueError("Current stopped world differs from closed full soak")
                    elif (props.get("server.id") != expected["server_id"] or props.get("cluster.id") != "dev_three_v1"
                          or props.get("transfer.channelBatches") != "true" or props.get("transfer.localFastPath") != "true"
                          or (expected.get("config_file_end_sha256") is not None
                              and expected["config_file_start_sha256"] != expected["config_file_end_sha256"])
                          or sha(path) != expected["config_file_start_sha256"]):
                        raise ValueError("Current stopped backend config differs from closed full soak")
                    backup = archive / (server + "-full-" + name)
                    with backup.open("xb") as output:
                        output.write(data)
                    os.chmod(backup, 0o600)
                    backups[(server, name)] = (path, data, backup)
            report["full_soak_config_backups"] = [meta(entry[2]) for entry in backups.values()]
            report["full_soak_stopped_config_hash_scope"] = (
                "Actual stopped bytes match each raw identity config_file_start_sha256. "
                "A raw end hash is checked when present; absent raw end hashes remain UNMEASURED, "
                "not synthesized into the original soak report. This controller measures the stopped pre-append hash.")
            report["pre_append_all_launch_locks_held_no_selected_JVM"] = True
            save()
        command = ["python3", "scripts/analysis/run-rc-v2-stage.py", "--execute", "--manifest", str(f3_path),
                   "--tree-manifest", str(final_path), "--phase", "mix", "--mode", "fast", "--variant", "default", "--label", LABEL]
        report.update(state="RUNNING_EXTRA_F3_FAST", command=command, helper=meta(ROOT / command[1]))
        log = ROOT / "logs" / (target.stem + ".log")
        report["log"] = str(log.relative_to(ROOT)); save()
        with log.open("x") as stream:
            child = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        report["child_exit_code"] = child.returncode
        completion = json.loads(log.read_text().splitlines()[-1])
        child_path, child_data = read_ref(completion["controller"])
        report["extra_controller"] = meta(child_path)
        closed_controller(child_data)
        if child.returncode != 0 or completion.get("passed") is not True:
            raise ValueError("Added stage failed; preserve its current configs/assets, no automatic restore")
        extra_raw_path, extra_raw = read_ref(child_data["raw_report"])
        if not extra_raw.get("passed") or len(extra_raw.get("samples", [])) != 1:
            raise ValueError("Added raw window did not complete")
        report["extra_raw"] = meta(extra_raw_path)
        report["own_launcher_exits"] = child_data["own_launcher_exits"]
        report.update(state="RESTORE_PENDING"); save()
        with stopped_locks(preparation):
            current = {}
            for (server, name), (path, original, backup) in backups.items():
                data = path.read_bytes()
                expected = parse_properties(original)
                observed = parse_properties(data)
                if name == "server.properties":
                    expected["level-name"] = "world-opt-" + LABEL + "-" + server
                    if observed != expected:
                        raise ValueError("Added server properties differ beyond its new world/date comments; no restore")
                elif sha(path) != child_data["fixture_configs"][server]["config_sha256"]:
                    raise ValueError("Added backend config changed externally; no restore")
                added_backup = archive / (server + "-added-f3f-" + name)
                with added_backup.open("xb") as output:
                    output.write(data)
                os.chmod(added_backup, 0o600)
                current[(server, name)] = data
            report["pre_restore_configs"] = [meta(archive / (server + "-added-f3f-" + name)) for server, name in backups]
            report["restore_all_launch_locks_held_no_selected_JVM"] = True
            save()
            # Validate every file before the first mutation, and again immediately
            # before its own replace. Never overwrite a differing external edit.
            for key, (path, original, backup) in backups.items():
                if path.read_bytes() != current[key] or backup.read_bytes() != original:
                    raise ValueError("Exact config/backup changed before restore")
            report["restored_configs"] = []
            for key, (path, original, backup) in backups.items():
                if path.read_bytes() != current[key]:
                    raise ValueError("Config changed during stopped restoration")
                pending = path.with_name(path.name + ".rc-post-soak-" + stamp + ".pending")
                with pending.open("xb") as stream:
                    stream.write(original)
                pending.replace(path)
                if path.read_bytes() != original:
                    raise ValueError("Restored config hash mismatch")
                report["restored_configs"].append({"current": meta(path), "full_backup": meta(backup),
                                                    "previous_added_sha256": hashlib.sha256(current[key]).hexdigest()})
                save()
            report["all_full_soak_config_bytes_restored"] = True
            report["all_selected_JVMs_stopped_and_launch_locks_free_after_restore"] = True
        report.update(passed=True, state="COMPLETE")
    except BaseException as error:
        report["failures"].append(type(error).__name__ + ": " + str(error))
        report["state"] = "FAILED_RETAINED_NO_BLIND_CONFIG_RESTORE"
    finally:
        report["utc_end"] = utc(); save()
    print(json.dumps({"controller": meta(target), "passed": report["passed"], "state": report["state"]}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
