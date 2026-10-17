#!/usr/bin/env python3
"""Private-container, real ENOSPC micro-test for the actual production LocalJournal.

Default mode is offline. --execute additionally requires an ALREADY LOCAL pinned
JDK21 image (repository@sha256:... or sha256:...), or --jdk pointing exactly to
the repository's scratch/jdk/jdk-21.0.8+9 with an already-local Debian/glibc image.
The explicit host JDK is read-only mounted at /jdk; no image entrypoint/service
is started. No image pull/build, Gradle,
Minecraft, SQL, host filler or shared /dev/shm is used. The only writable WAL is
a private 1MiB container tmpfs, and the container has --network none. Positive
WAL values are standalone filesystem fixtures, not historical/game/SQL assets.

Example after selecting an existing image digest:
  python3 scripts/rc_enospc_test.py --execute --image sha256:<64 hex>
Reports, exact frozen source copies and raw output are retained under a NEW
scratch/rc-enospc-<UTC>-<UUID> directory. --self-test does not use Docker/JDK.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "src/main/java/dev/crosstesseract/backend/LocalJournal.java",
    "src/main/java/dev/crosstesseract/core/DomainException.java",
    "src/main/java/dev/crosstesseract/core/LocalSnapshot.java",
    "src/main/java/dev/crosstesseract/core/Resource.java",
    "src/main/java/dev/crosstesseract/core/ThermalBuffer.java",
    "src/main/java/dev/crosstesseract/core/Protocol.java",
    "src/main/java/dev/crosstesseract/core/Metrics.java",
    "scripts/rc_enospc_probe.java",
)
PINNED = re.compile(r"(?:[A-Za-z0-9._/:\-]+@)?sha256:[a-f0-9]{64}")


def utc():
    return datetime.now(timezone.utc).isoformat()


def create_command(image_id, frozen, name, token, jdk=None):
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
        raise ValueError("local immutable image ID required")
    compiler, java = (("/jdk/bin/javac", "/jdk/bin/java") if jdk else ("javac", "java"))
    compile_and_run = compiler + " -Xmaxerrs 10 -d /tmp " + " ".join("/source/" + path for path in SOURCES)
    compile_and_run += "\nexec " + java + " -cp /tmp rc_enospc_probe /wal"
    uid, gid = os.getuid(), os.getgid()
    private_owner = ",uid=" + str(uid) + ",gid=" + str(gid)
    command = ["docker", "create", "--name", name, "--label", "ct.rc_enospc_token=" + token,
            "--pull=never", "--network", "none", "--read-only", "--cap-drop=ALL",
            "--user", str(uid) + ":" + str(gid),
            "--security-opt=no-new-privileges", "--memory=384m", "--memory-swap=384m", "--cpus=0.25",
            "--pids-limit=64", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,mode=1777",
            "--tmpfs", "/wal:rw,nosuid,nodev,size=1m,mode=0700" + private_owner,
            "--tmpfs", "/data:rw,nosuid,nodev,size=1m,mode=0700" + private_owner,
            "--mount", "type=bind,src=" + str(frozen) + ",dst=/source,readonly",
            "--env", "LC_ALL=C", "--env", "JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=1 -Xms16m -Xmx128m",
            "--entrypoint", "/bin/sh"]
    if jdk:
        command += ["--mount", "type=bind,src=" + str(jdk) + ",dst=/jdk,readonly"]
    return command + [image_id, "-eu", "-c", compile_and_run]


def hash_file(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for data in iter(lambda: source.read(1048576), b""):
            value.update(data)
    return value.hexdigest()


def jdk_evidence(argument, archive=None):
    expected = ROOT / "scratch/jdk/jdk-21.0.8+9"
    candidate = Path(argument)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if candidate != expected or ".." in candidate.parts:
        raise ValueError("--jdk is restricted to scratch/jdk/jdk-21.0.8+9")
    for relative in ("scratch", "scratch/jdk", "scratch/jdk/jdk-21.0.8+9"):
        if (ROOT / relative).is_symlink():
            raise ValueError("JDK directory symlink forbidden")
    if not candidate.is_dir() or candidate.resolve(strict=True) != expected:
        raise ValueError("exact real repository JDK directory required")
    for executable in ("java", "javac"):
        binary = candidate / "bin" / executable
        if not binary.is_file() or binary.is_symlink():
            raise ValueError("real JDK21 tool binary required")
    manifest, total = [], 0
    for path in candidate.rglob("*"):
        if len(manifest) >= 4096:
            raise ValueError("JDK manifest file-count limit")
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not target.is_relative_to(expected):
                raise ValueError("JDK symlink escapes read-only JDK root")
            manifest.append({"path": str(path.relative_to(candidate)), "symlink_target": str(target.relative_to(candidate))})
        elif path.is_file():
            size = path.stat().st_size
            total += size
            if size > 268435456 or total > 805306368:
                raise ValueError("JDK manifest byte limit")
            manifest.append({"path": str(path.relative_to(candidate)), "bytes": size, "sha256": hash_file(path)})
    manifest.sort(key=lambda entry: entry["path"])
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    evidence = {"path": str(candidate.relative_to(ROOT)), "directory_manifest": manifest,
                "directory_manifest_sha256": hashlib.sha256(encoded).hexdigest(), "file_bytes": total,
                "archive": "NOT_PROVIDED", "source_URL": "UNVERIFIED_OPERATOR_PROVIDED_REPOSITORY_JDK"}
    if archive:
        source = Path(archive)
        if not source.is_absolute(): source = ROOT / source
        if ".." in source.parts or not source.is_relative_to(ROOT / "scratch") or source.is_symlink() or not source.is_file():
            raise ValueError("JDK archive must be a real file below repository scratch")
        if not source.resolve().is_relative_to(ROOT / "scratch") or source.stat().st_size > 536870912:
            raise ValueError("JDK archive path or size limit")
        evidence["archive"] = {"path": str(source.relative_to(ROOT)), "bytes": source.stat().st_size, "sha256": hash_file(source)}
    return candidate, evidence


def execute(args):
    if not args.image or not PINNED.fullmatch(args.image):
        raise ValueError("--image must be an already-local immutable image digest")
    inspected = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", args.image],
                               text=True, capture_output=True, check=True, timeout=10)
    image_id = inspected.stdout.strip()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
        raise ValueError("invalid local image identity")
    jdk, host_jdk = jdk_evidence(args.jdk, args.jdk_archive) if args.jdk else (None, "IMAGE_JDK_UNTIL_ACTUAL_PROBE_VERSION")
    if args.jdk_archive and not args.jdk:
        raise ValueError("--jdk-archive requires --jdk")
    scratch = ROOT / "scratch"
    if scratch.is_symlink():
        raise ValueError("scratch symlink forbidden")
    scratch.mkdir(exist_ok=True)
    token = uuid.uuid4().hex
    directory = scratch / ("rc-enospc-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + token)
    directory.mkdir(mode=0o700)
    frozen = directory / "source"
    frozen.mkdir()
    manifest = []
    for relative in SOURCES:
        original = ROOT / relative
        if original.is_symlink() or original.stat().st_size > 262144:
            raise ValueError("unsafe or oversized source input")
        destination = frozen / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = original.read_bytes()
        destination.write_bytes(data)
        manifest.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    result = {"utc_start": utc(), "passed": False, "local_image_requested": args.image, "local_image_id": image_id,
              "compiled_source_files": manifest, "source_scope": "exact copied production sources; not a frozen benchmark artifact claim",
              "container_network": "none", "private_WAL_tmpfs_bytes": 1048576, "host_shared_filler": False,
              "native_SQL_hardware_power_loss_tests": "NOT_RUN", "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    result["host_JDK_readonly"] = host_jdk
    container = None
    started = time.monotonic()
    try:
        command = create_command(image_id, frozen, "ct-rc-enospc-" + token, token, jdk)
        result["create_command"] = command
        creation = subprocess.run(command, text=True, capture_output=True, check=True, timeout=15)
        container = creation.stdout.strip()
        if not re.fullmatch(r"[a-f0-9]{64}", container):
            raise ValueError("invalid owned container identity")
        result["owned_container_id"] = container
        with (directory / "stdout.log").open("xb") as output, (directory / "stderr.log").open("xb") as errors:
            completed = subprocess.run(["docker", "start", "--attach", container], stdout=output, stderr=errors,
                                       timeout=args.timeout, check=False)
        result["docker_attach_exit_code"] = completed.returncode
        exit_state = subprocess.run(["docker", "inspect", "--format", "{{.State.ExitCode}}", container],
                                    capture_output=True, text=True, check=True, timeout=10)
        result["container_exit_code"] = int(exit_state.stdout.strip())
        raw = (directory / "stdout.log").read_bytes()
        if len(raw) > 262144 or (directory / "stderr.log").stat().st_size > 262144:
            raise ValueError("raw probe output size limit")
        probe = json.loads(raw)
        result["probe"] = probe
        result["passed"] = (completed.returncode == 0 and result["container_exit_code"] == 0
                            and probe.get("passed") is True and probe.get("file_store_type") == "tmpfs"
                            and probe.get("controlled_IOException_injection") is False
                            and probe.get("WAL_actual_exception", {}).get("ENOSPC_message_observed") is True
                            and probe.get("old_positive_ctj_preserved") is True
                            and probe.get("durable_TX_after_failure_FE") == 128
                            and probe.get("durable_TX_after_retry_FE") == 135)
    except Exception as error:
        # No credentials or SQL are involved in this isolated filesystem driver.
        result["failure_class"] = type(error).__name__
        result["failure"] = str(error)[:2048]
    finally:
        if container is not None:
            try:
                removed = subprocess.run(["docker", "rm", "--force", "--volumes", container], capture_output=True, timeout=15)
                result["owned_container_remove_exit_code"] = removed.returncode
                if removed.returncode != 0:
                    result["passed"] = False
            except Exception as error:
                result["passed"] = False
                result["cleanup_failure_class"] = type(error).__name__
        result["utc_end"] = utc()
        result["elapsed_seconds"] = time.monotonic() - started
        for filename in ("stdout.log", "stderr.log"):
            path = directory / filename
            if path.exists():
                result[filename + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        report = directory / "result.json"
        with report.open("x") as output:
            json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)
            output.write("\n")
        print(json.dumps({"passed": result["passed"], "report": str(report.relative_to(ROOT)),
                          "real_private_tmpfs_probe_executed": container is not None,
                          "native_SQL_hardware_power_loss_tests": "NOT_RUN"}))
    return 0 if result["passed"] else 1


def self_test():
    class Tests(unittest.TestCase):
        def test_container_only_has_private_writable_volumes_and_no_network(self):
            command = create_command("sha256:" + "a" * 64, Path("/tmp/frozen-rc-sources"), "ct-rc-enospc-test", "token")
            self.assertEqual("none", command[command.index("--network") + 1])
            self.assertIn("--read-only", command)
            self.assertIn("--pull=never", command)
            self.assertEqual(str(os.getuid()) + ":" + str(os.getgid()), command[command.index("--user") + 1])
            self.assertIn("/wal:rw,nosuid,nodev,size=1m,mode=0700,uid=" + str(os.getuid()) + ",gid=" + str(os.getgid()), command)
            self.assertIn("--cap-drop=ALL", command)
            self.assertFalse(any("/dev/shm" in entry or "docker.sock" in entry for entry in command))
            self.assertTrue(any(entry.endswith("dst=/source,readonly") for entry in command))
            self.assertIn("javac -Xmaxerrs 10", command[-1])
        def test_unpinned_images_rejected(self):
            for image in ("eclipse-temurin:21-jdk", "sha256:short", "-invalid"):
                self.assertIsNone(PINNED.fullmatch(image))
                with self.assertRaises(ValueError): create_command(image, Path("/tmp/frozen"), "name", "token")
        def test_explicit_repository_jdk_is_readonly_and_service_entrypoint_bypassed(self):
            command = create_command("sha256:" + "b" * 64, Path("/tmp/frozen"), "name", "token", ROOT / "scratch/jdk/jdk-21.0.8+9")
            self.assertEqual("/bin/sh", command[command.index("--entrypoint") + 1])
            self.assertTrue(any(entry.endswith("dst=/jdk,readonly") for entry in command))
            self.assertIn("/jdk/bin/javac", command[-1])
            self.assertIn("exec /jdk/bin/java", command[-1])
            for bad in ("/tmp/another-jdk", "scratch/jdk/../jdk-21.0.8+9"):
                with self.assertRaises(ValueError): jdk_evidence(bad)
        def test_all_production_source_inputs_exist_and_stay_small(self):
            for relative in SOURCES:
                path = ROOT / relative
                self.assertTrue(path.is_file(), relative)
                self.assertLess(path.stat().st_size, 262144)
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    print(json.dumps({"mode": "OFFLINE_SELF_TEST", "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "Docker_JDK_ENOSPC_SQL_native_tests": "NOT_RUN"}))
    return 0 if result.wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    parser.add_argument("--image", help="Already-local pinned image digest; no image pulls.")
    parser.add_argument("--jdk", help="Optional exact real scratch/jdk/jdk-21.0.8+9, readonly bind at /jdk.")
    parser.add_argument("--jdk-archive", help="Optional retained JDK archive below scratch; hash is evidence, no extraction.")
    parser.add_argument("--timeout", type=int, default=90, help="Container attach bound, 1..120 seconds.")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.execute:
        print(json.dumps({"mode": "OFFLINE", "Docker_JDK_ENOSPC_SQL_native_tests": "NOT_RUN"}))
        return 0
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be within 1..120 seconds")
    try:
        return execute(args)
    except Exception as error:
        print(json.dumps({"passed": False, "failure_class": type(error).__name__, "failure": str(error)[:2048]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
