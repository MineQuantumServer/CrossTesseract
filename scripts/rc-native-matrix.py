#!/usr/bin/env python3
"""Independent, isolated RC native compatibility matrix; default is OFFLINE.

--execute --accept-eula asserts the operator accepted Minecraft's EULA. Existing
loopback development MySQL/Redis must already be running, and A/B/C/Perf/GameTest
JVMs must be stopped. This script never starts/stops backend containers, queries
or rewrites SQL/WAL assets, updates lock files, or reuses a test world.

Each selected combination builds classes/JAR/launch with -PgameTestBackend,
-PrcFaultTests and a fresh -PrcFixture; freezes its classes/resources/arguments,
legacy classpath and logging configuration; then launches that frozen JVM once.
Recovery and positive-asset fault GameTests run alongside the actual optional
mod closure. Missing GT JAR/lock is BLOCKED. Failed groups do not hide later
independent groups. Timeout sends normal SIGTERM to this script's own process
group only; surviving JVMs block further admission, never trigger hard kill or
asset replay. Every fixture, remaining positive stock and raw log is retained.

Examples:
  python3 scripts/rc-native-matrix.py --self-test
  python3 scripts/rc-native-matrix.py --execute --accept-eula
  python3 scripts/rc-native-matrix.py --execute --accept-eula --combinations base,ae2

Partial selection can pass its selected-tool smoke, but full_matrix_gate stays
false and every omitted combination is explicitly NOT_RUN. Native stock
LogTestReporter has no per-success test-name/XML output: the evidence is the
frozen source registration list, exact required-test total, real loaded Mod IDs,
positive-asset markers and final native exit0, not invented per-test XML.
"""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[1]
COMBINATIONS = {
    "base": (), "mekanism": ("mekanism",), "ae2": ("ae2",),
    "ae2-mekanism": ("ae2", "mekanism"), "gregtech": ("gregtech",),
    "gregtech-mekanism": ("gregtech", "mekanism"), "ae2-gregtech": ("ae2", "gregtech"),
    "ae2-gregtech-mekanism": ("ae2", "gregtech", "mekanism"),
}
MOD_IDS = {"ae2": "ae2", "mekanism": "mekanism", "gregtech": "gtceu"}
CORE_TESTS = ("test/GameTests.java", "test/CoreBackendGameTests.java", "test/RuntimeDeltaGameTests.java",
    "test/RegistrationRecoveryGameTests.java", "test/RcFaultGameTests.java", "test/RcGroupGameTests.java",
    "test/RcWakeGameTests.java", "test/RcDiscoveryGameTests.java")
COMPAT_TESTS = {"ae2": "compat/ae2/AeGameTests.java", "mekanism": "compat/mekanism/MekGameTests.java",
    "gregtech": "compat/gregtech/GtGameTests.java"}
GT_JAR = ROOT / "scratch/upstream/gregtech/build/libs/gtceu-1.21.1-8.0.0.jar"
MAX_LOG = 64 * 1024 * 1024
MAX_FILE = 96 * 1024 * 1024


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def digest(path, maximum=MAX_FILE):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("unsafe/oversized file: " + str(path))
    result = hashlib.sha256()
    with path.open("rb") as source:
        for part in iter(lambda: source.read(1_048_576), b""):
            result.update(part)
    return result.hexdigest()


def metadata(path, maximum=MAX_FILE):
    return {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "bytes": path.stat().st_size, "sha256": digest(path, maximum)}


def new_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    os.chmod(path, 0o600)


def real_directory(path):
    if not path.is_relative_to(ROOT):
        raise ValueError("output outside repository")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError("output directory symlink rejected")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError("output directory required")


def selection(text):
    labels = list(COMBINATIONS) if text == "all" else text.split(",")
    if not labels or len(labels) != len(set(labels)) or any(label not in COMBINATIONS for label in labels):
        raise ValueError("--combinations requires unique canonical labels or all")
    return labels


def lock_manifest():
    paths = [ROOT / "gradle.lockfile", *sorted((ROOT / "gradle/locks").glob("*.lockfile"))]
    return [metadata(path, 1_048_576) for path in paths if path.exists()]


def source_manifest():
    paths = [*sorted((ROOT / "src/main/java").rglob("*.java")),
        *sorted(path for path in (ROOT / "src/main/resources").rglob("*") if path.is_file())]
    paths += [ROOT / value for value in ("build.gradle", "settings.gradle", "gradle.properties", "gradlew",
        "gradle/wrapper/gradle-wrapper.properties", "gradle/wrapper/gradle-wrapper.jar",
        "config/gametest.properties", "scripts/gradle-dev.sh", "scripts/freeze-dev-launch.py", "scripts/rc-native-matrix.py")
        if (ROOT / value).is_file()]
    for name in ("IEnergyContainer.java", "IEnergyInfoProvider.java"):
        path = ROOT / "scratch/upstream/gregtech/src/main/java/com/gregtechceu/gtceu/api/capability" / name
        if path.is_file():
            paths.append(path)
    if len(paths) > 4096 or sum(path.stat().st_size for path in paths) > 64 * 1024 * 1024:
        raise ValueError("source manifest bound exceeded")
    files = [metadata(path, 8 * 1024 * 1024) for path in sorted(set(paths))]
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"files": files, "sha256": hashlib.sha256(canonical).hexdigest(),
        "scope": "actual source/resources/build/helper/config inputs, not loaded-code attestation; frozen class/JAR manifests recorded separately"}


def expected_tests(mods):
    result = []
    for relative in (*CORE_TESTS, *(COMPAT_TESTS[mod] for mod in mods)):
        path = ROOT / "src/main/java/dev/crosstesseract" / relative
        text = path.read_text()
        methods = re.findall(r"@GameTest\s*\(([^)]*)\)\s*public\s+static\s+void\s+(\w+)\s*\(", text, re.S)
        if not methods or any(re.search(r"\brequired\s*=\s*false\b", annotation) for annotation, _ in methods):
            raise ValueError("expected required GameTest source declaration changed: " + relative)
        for _, method in methods:
            result.append({"source": str(path.relative_to(ROOT)), "class": path.stem, "method": method,
                "native_test_name": path.stem.lower() + "." + method.lower(), "required": True})
    return result


def properties(text):
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "!")):
            continue
        if "=" not in line:
            raise ValueError("only simple development property syntax accepted")
        key, value = (part.strip() for part in line.split("=", 1))
        if key in result:
            raise ValueError("duplicate development property: " + key)
        result[key] = value
    return result


def check_backend(text):
    values = properties(text)
    url = values.get("mysql.url", "")
    parsed = urlparse(url.removeprefix("jdbc:"))
    if not (values.get("backend.enabled") == "true" and values.get("cluster.id", "").startswith("test_")
        and values.get("mysql.user") == "ct_dev" and values.get("mysql.password") == "ct_dev_only"
        and parsed.scheme == "mysql" and parsed.hostname == "127.0.0.1" and parsed.port == 13306
        and parsed.path == "/cross_tesseract" and not parsed.username and not parsed.password
        and values.get("redis.uri") == "redis://127.0.0.1:16379"):
        raise ValueError("existing isolated loopback development backend configuration required")
    return values


def native_processes():
    found = []
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        try:
            raw = (directory / "cmdline").read_bytes()
            if len(raw) > 1_048_576:
                continue
            argv = raw.split(b"\0")
            if not argv or not argv[0].endswith(b"/java"):
                continue
            joined = b" ".join(argv)
            named = re.search(rb"(?:server[ABC]|serverPerf|gameTestServer)RunVmArgs\.txt", joined)
            cwd = (directory / "cwd").resolve()
            official = cwd in tuple(ROOT / name for name in ("run-A", "run-B", "run-C", "run-perf")) and (
                b"neoforg" in joined or b"unix_args.txt" in joined or b"minecraft" in joined)
            generic = cwd.is_relative_to(ROOT) and (b"net.minecraft.server.Main" in joined or b"forgeserverdev" in joined)
            if named or official or generic:
                found.append({"pid": int(directory.name), "argv_sha256": hashlib.sha256(raw).hexdigest(),
                    "cwd": str(cwd), "reason": "named/development/packaged Minecraft JVM"})
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return found


def terminate_owned(proc, row, key):
    if proc.poll() is not None:
        return
    row[key + "_SIGTERM_requested"] = True
    row["SQL_clean_stop"] = "NOT_PROVEN_BY_SIGTERM"
    if os.getpgid(proc.pid) != proc.pid:
        raise RuntimeError("owned subprocess session identity changed; refusing group signal")
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        row[key + "_SIGTERM_exit"] = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        row["owned_process_still_running"] = True


def run_owned(command, log, timeout, row, key, vm_argument=None):
    started = time.monotonic()
    with log.open("x") as stream:
        proc = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
        row[key + "_launcher_pid"] = proc.pid
        row[key + "_command"] = command
        row[key + "_utc_start"] = utc()
        try:
            while True:
                try:
                    code = proc.wait(timeout=.5)
                    row[key + "_exit"] = code
                    return code
                except subprocess.TimeoutExpired:
                    pass
                if vm_argument is not None and "native_JVM_identity" not in row:
                    candidates = []
                    for point in native_processes():
                        try:
                            raw = Path(f"/proc/{point['pid']}/cmdline").read_bytes()
                            if vm_argument.encode() in raw.split(b"\0"):
                                candidates.append(point)
                        except FileNotFoundError:
                            continue
                    if len(candidates) > 1:
                        raise RuntimeError("multiple JVMs for one frozen launch")
                    if candidates:
                        row["native_JVM_identity"] = candidates[0]
                if time.monotonic() - started >= timeout or log.stat().st_size > MAX_LOG:
                    row[key + "_timeout_or_log_bound"] = True
                    terminate_owned(proc, row, key)
                    raise RuntimeError(key + " timeout/log bound; fixture retained, no hard kill or replay")
        except BaseException:
            terminate_owned(proc, row, key)
            raise
        finally:
            row[key + "_elapsed_seconds"] = time.monotonic() - started
            row[key + "_utc_end"] = utc()


def class_manifest(directory):
    files = [metadata(path, 8 * 1024 * 1024) for path in sorted(directory.rglob("*")) if path.is_file()]
    if len(files) > 4096 or sum(point["bytes"] for point in files) > 32 * 1024 * 1024:
        raise ValueError("frozen class/resource manifest bound")
    return files


def classpath_entries(argument):
    if argument.is_symlink() or not argument.is_file() or argument.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("bounded regular frozen classpath argument file required")
    values = shlex.split(argument.read_text(), comments=True)
    if len(values) != 2 or values[0] not in ("-classpath", "-cp", "--class-path"):
        raise ValueError("unexpected generated JVM classpath argument format")
    paths = values[1].split(os.pathsep)
    if not paths or len(paths) > 1024 or any(not value or not Path(value).is_absolute() for value in paths):
        raise ValueError("bounded absolute JVM runtime classpath required")
    return paths


def freeze_classpath(argument, frozen):
    # The shared freezer rewrites fml.modFolders in the launcher. The copied JVM
    # classpath argument must independently stop referring to mutable main output.
    paths = classpath_entries(argument)
    text = argument.read_text()
    for original, target in ((ROOT / "build/classes/java/main", frozen / "classes"),
            (ROOT / "build/resources/main", frozen / "resources")):
        if paths.count(str(original)) != 1 or not target.is_dir():
            raise ValueError("expected one mutable main output and its frozen replacement")
        text = text.replace(str(original), str(target))
    argument.write_text(text)
    result = classpath_entries(argument)
    if any(value in result for value in (str(ROOT / "build/classes/java/main"), str(ROOT / "build/resources/main"))):
        raise ValueError("copied classpath still contains mutable main output")
    return result


def freeze_launch(fixture, expected_config, row):
    lock = ROOT / "scratch/dev-build.lock"
    with lock.open("a+") as guard:
        deadline = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(guard, fcntl.LOCK_SH | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("shared freeze build-lock deadline")
                time.sleep(.1)
        completed = subprocess.run(["python3", "scripts/freeze-dev-launch.py", "build/moddev/runGameTestServer.sh"],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        if completed.returncode:
            row["freeze_failure"] = completed.stderr[-3000:]
            raise RuntimeError("shared immutable launch freezer failed")
        launcher = Path(completed.stdout.strip())
        if launcher.parent.parent != ROOT / "scratch/dev-launch" or not re.fullmatch(r"[a-f0-9]{32}", launcher.parent.name) or launcher.name != "runGameTestServer.sh":
            raise ValueError("unexpected frozen launcher path")
        frozen = launcher.parent
        classpath = frozen / "gameTestServerRunClasspath.txt"
        row["frozen_runtime_classpath_entries"] = freeze_classpath(classpath, frozen)
        vm = frozen / "gameTestServerRunVmArgs.txt"
        text = vm.read_text()
        # The shared freezer copies the three argument files, but these two
        # generated references also change with the next compatibility build.
        extras = []
        for prefix, name in (("-DlegacyClassPath.file=", "gameTestServerLegacyClasspath.txt"),
                ("-Dlog4j2.configurationFile=", "gameTestServerLog4j2.xml")):
            matches = [value[len(prefix):] for value in shlex.split(text, comments=True) if value.startswith(prefix)]
            original = ROOT / "build/moddev" / name
            if matches != [str(original)] or original.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("unexpected generated launch reference: " + name)
            target = frozen / name
            shutil.copy2(original, target)
            text = text.replace(str(original), str(target))
            extras.append(target)
        vm.write_text(text)
        flags = dict(value[2:].split("=", 1) for value in shlex.split(text, comments=True)
            if value.startswith("-D") and "=" in value)
        for key, value in {"cross_tesseract.config": str(expected_config), "cross_tesseract.rcFaultTests": "true",
                "cross_tesseract.compatTests": "true", "neoforge.gameTestServer": "true",
                "neoforge.enabledGameTestNamespaces": "cross_tesseract"}.items():
            if flags.get(key) != value:
                raise ValueError("frozen fixture/required flag mismatch: " + key)
        if str(fixture / "game") not in launcher.read_text() or str(ROOT / "build/classes/java/main") in launcher.read_text():
            raise ValueError("frozen launcher cwd/classes mismatch")
        paths = [launcher, *sorted(frozen.glob("*Run*.txt")), *extras]
        row["frozen_launch_files"] = [metadata(path, 2 * 1024 * 1024) for path in sorted(set(paths))]
        row["frozen_class_resources"] = class_manifest(frozen / "classes") + class_manifest(frozen / "resources")
        row["frozen_launcher"] = str(launcher.relative_to(ROOT))
        row["frozen_backend_config_sha256"] = digest(expected_config, 65536)
        return launcher, frozen / "gameTestServerLegacyClasspath.txt", classpath


def runtime_mod_artifacts(legacy, classpath, mods):
    artifacts, mandatory = [], set()
    # ModDev's localRuntime mods are on the actual JVM -classpath. The separate
    # LegacyClasspath contains additional libraries, not the selected mod set.
    paths = list(dict.fromkeys([*legacy.read_text().splitlines(), *classpath_entries(classpath)]))
    if len(paths) > 1024:
        raise ValueError("legacy runtime classpath bound")
    for value in paths:
        path = Path(value)
        if path.suffix != ".jar" or not re.search(r"(?i)(?:ae2|appliedenergistics|mekanism|gtceu|guideme)", path.name):
            continue
        with zipfile.ZipFile(path) as archive:
            names = [name for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml") if name in archive.namelist()]
            if len(names) != 1 or archive.getinfo(names[0]).file_size > 262144:
                raise ValueError("optional runtime mod declaration missing/ambiguous")
            declaration = tomllib.loads(archive.read(names[0]).decode())
            declared = {row["modId"] for row in declaration.get("mods", [])}
            dependencies = []
            for source_id, points in declaration.get("dependencies", {}).items():
                for point in points:
                    if point.get("side", "BOTH").upper() in ("BOTH", "SERVER") and (point.get("type") == "required" or point.get("mandatory") is True):
                        mandatory.add(point["modId"])
                        dependencies.append({"source_mod": source_id, "required_mod": point["modId"], "version_range": point.get("versionRange")})
            artifacts.append({**metadata(path), "declared_mod_ids": sorted(declared),
                "required_server_dependencies": dependencies,
                "scope": "actual resolved runtime JAR; embedded library/mod closure additionally verified by real loader success and loaded Mod List"})
    loaded_primary = {mod for artifact in artifacts for mod in artifact["declared_mod_ids"] if mod in MOD_IDS.values()}
    if loaded_primary != {MOD_IDS[mod] for mod in mods}:
        raise ValueError("resolved optional runtime primary mod set differs from selected testMods")
    if "ae2" in mods:
        mandatory.add("guideme")
    return artifacts, sorted(mandatory)


def loaded_mods(text):
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    rows, active = {}, False
    for line in text.splitlines():
        if "Mod List:" in line:
            active = True
            continue
        if active and re.match(r"\[\d\d:\d\d:\d\d\]", line):
            break
        if active:
            match = re.fullmatch(r"\s*(.*?)\s+\(([a-z][a-z0-9_]*)\)\s*", line)
            if match:
                if match[2] in rows:
                    raise ValueError("duplicate native Mod List ID")
                rows[match[2]] = match[1]
    return rows


def check_native(text, mods, count, dependencies, exit_code):
    actual = loaded_mods(text)
    required = {"minecraft", "neoforge", "cross_tesseract", *(MOD_IDS[mod] for mod in mods), *dependencies}
    passed_counts = [int(value) for value in re.findall(r"All (\d+) required tests passed", text)]
    complete_counts = [int(value) for value in re.findall(r"={3,}\s*(\d+) GAME TESTS COMPLETE", text)]
    started_counts = [int(value) for value in re.findall(r"(\d+) tests are now running", text)]
    capacity = re.findall(r"CT_RC_CAPACITY_PASS[^\r\n]*", text)
    groups = re.findall(r"CT_RC_GROUP_PASS[^\r\n]*", text)
    wake = re.findall(r"CT_RC_WAKE_PASS[^\r\n]*", text)
    discovery = re.findall(r"CT_RC_DISCOVERY_PASS[^\r\n]*", text)
    wake_values = {"input": "128", "first_batch_RESERVED": "128", "prepublication_RX": "0",
        "external_native_output": "128", "duplicate_output": "0", "final_SQL_pool": "0",
        "final_SQL_remaining": "0", "final_WAL_assets": "0"}
    checks = {"native_exit_zero": exit_code == 0,
        "required_total_exact": passed_counts == [count], "completed_total_exact": complete_counts == [count],
        "started_total_exact": started_counts == [count], "required_mod_ids_loaded": required <= set(actual),
        "optional_primary_set_exact": set(actual) & set(MOD_IDS.values()) == {MOD_IDS[mod] for mod in mods},
        "one_positive_capacity_marker": len(capacity) == 1 and all(value in capacity[0] for value in (
            "input=128", "external_native_output=128", "duplicate_output=0", "rejected_task_executions=0")),
        "one_actual_split_group_marker": len(groups) == 1 and all(value in groups[0] for value in (
            "initial_native_input=384", "actual_native_output=256", "retained_TX=128", "actual_groups=3+1", "original_TX_ids_preserved=true")),
        "one_first_batch_checkpoint_hint_upgrade_marker": len(wake) == 1 and all(
            re.findall(r"(?:^|\s)" + re.escape(key) + r"=([^\s]+)(?=\s|$)", wake[0]) == [value]
            for key, value in wake_values.items()),
        "one_continuous_consumption_discovery_marker": len(discovery) == 1 and all(
            re.findall(r"(?:^|\s)" + re.escape(key) + r"=([^\s]+)(?=\s|$)", discovery[0]) == [value]
            for key, value in {"native_input":"288", "native_output":"288", "pool":"0", "owned":"0", "WAL_mirror":"0", "old_LOCAL_not_exhausted":"true"}.items()),
        "no_expected_negative_discovery": "CT_RC_DISCOVERY_NEGATIVE" not in text,
        "no_required_failure_summary": not re.search(r"\d+ required tests failed| failed at |Game test server crashed", text)}
    return {"checks": checks, "passed": all(checks.values()), "native_loaded_mods": actual,
        "required_mod_ids": sorted(required), "required_tests_passed_summary": passed_counts,
        "native_positive_asset_markers": {"capacity": capacity, "partial_publication": groups, "first_batch_wake": wake, "continuous_discovery": discovery},
        "logged_runtime_pause_lines": [line for line in text.splitlines() if "Tesseract paused:" in line][:32],
        "test_identity_proof": "frozen source registered classes/methods + exact started/completed/all-required-pass count; stock native reporter emits no individual success names/XML",
        "SQL_WAL_worker_counters": "NOT_SEPARATELY_QUERIED; actual native assertions and retained positive markers are the evidence"}


def fixture_config(original, token):
    values = check_backend(original)
    values.update({"cluster.id": "test_rcmatrix_" + token.replace("-", "_"), "server.id": token,
        "transfer.channelBatches": "true", "transfer.localFastPath": "true",
        "transfer.maxBatchRecords": "192", "transfer.maxBatchDevices": "8"})
    return "\n".join(key + "=" + value for key, value in values.items()) + "\n", values["cluster.id"]


class Matrix:
    def __init__(self, args):
        self.args, self.selected = args, selection(args.combinations)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.token = uuid.uuid4().hex[:12]
        self.directory = ROOT / "reports/rc-20261017"
        real_directory(self.directory)
        real_directory(ROOT / "scratch/rc-native")
        self.path = self.directory / ("native-matrix-" + args.label + "-" + stamp + "-" + self.token + ".json")
        self.inputs, self.locks = source_manifest(), lock_manifest()
        new_json(self.path.with_name(self.path.stem + "-sources.json"), self.inputs)
        self.original = (ROOT / "config/gametest.properties").read_text()
        check_backend(self.original)
        self.report = {"schema_version": 1, "report_kind": "isolated_RC_native_matrix" if len(self.selected) == 8 else "isolated_RC_native_matrix_tool_smoke",
            "utc_start": utc(), "passed": False, "full_matrix_gate": False, "selected_combinations_passed": False,
            "operator_asserted_EULA": True, "EULA": "https://www.minecraft.net/eula",
            "source_manifest": metadata(self.path.with_name(self.path.stem + "-sources.json")),
            "source_inputs_sha256": self.inputs["sha256"], "lock_files_at_start": self.locks,
            "selected_combinations": self.selected,
            "scope": "fresh cluster/server/world per closure; real Minecraft+existing loopback MySQL/Redis, normal and RC recovery/fault assertions; not a new full client/third-party uncertainty or hardware power-loss test",
            "existing_assets_reused_or_refunded": False, "lock_files_updated_by_driver": False,
            "dependency_resolution": "normal repository access with fixed versions and existing committed locks; no --write-locks or automatic source/build retry",
            "combinations": [{"combination": label, "testMods": list(mods), "state": "NOT_RUN", "passed": False,
                "reason": "awaiting execution" if label in self.selected else "not selected by --combinations"}
                for label, mods in COMBINATIONS.items()]}
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        self.report.update(workspace_git_HEAD=revision,
            revision_scope="workspace checkout HEAD retained; actual compiled inputs and frozen launch class/JAR hashes prove this run's artifacts, not HEAD alone")
        new_json(self.path, self.report)

    def save(self):
        temporary = self.path.with_suffix(".pending.json")
        temporary.write_text(json.dumps(self.report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        temporary.replace(self.path)

    def unchanged(self):
        return source_manifest()["sha256"] == self.inputs["sha256"] and lock_manifest() == self.locks

    def one(self, row):
        label, mods = row["combination"], tuple(row["testMods"])
        row.update(utc_start=utc(), expected_required_tests=expected_tests(mods))
        row["expected_required_count"] = len(row["expected_required_tests"])
        if not self.unchanged():
            row.update(state="BLOCKED", reason="frozen source/lock inputs changed; do not mix revisions")
            return
        running = native_processes()
        if running:
            row.update(state="BLOCKED", reason="A/B/C/Perf/GameTest JVM already running; no process stopped", conflicting_processes=running)
            return
        if "gregtech" in mods and (not GT_JAR.is_file() or GT_JAR.is_symlink()):
            row.update(state="BLOCKED", reason="actual FortyTwoCn GT runtime JAR unavailable; no stub or download substitution")
            return
        lock = ROOT / ("gradle.lockfile" if label == "base" else "gradle/locks/" + label + ".lockfile")
        if not lock.is_file():
            row.update(state="BLOCKED", reason="required committed dependency lock missing; driver never writes locks")
            return
        token = "matrix-" + label + "-" + uuid.uuid4().hex[:12]
        if len(token) > 48:
            raise ValueError("fixture token limit")
        fixture = ROOT / "scratch/rc-native" / token
        fixture.mkdir(mode=0o700)
        game = fixture / "game"
        game.mkdir(mode=0o700)
        config, cluster = fixture_config(self.original, token)
        backend = fixture / "backend.properties"
        backend.write_text(config)
        os.chmod(backend, 0o600)
        (game / "eula.txt").write_text("eula=true\n")
        (game / "server.properties").write_text("server-ip=127.0.0.1\nonline-mode=false\nenable-rcon=false\n")
        row.update(fixture=str(fixture.relative_to(ROOT)), cluster=cluster, server_id=token,
            state="RUNNING", positive_assets_retained=True, SQL_clean_stop="NOT_SEPARATELY_QUERIED")
        new_json(fixture / "manifest.json", {"fixture": token, "combination": label, "cluster": cluster,
            "created_utc": utc(), "source_inputs_sha256": self.inputs["sha256"],
            "EULA_operator_assertion": "--execute --accept-eula", "config_sha256": digest(backend, 65536)})
        self.save()
        try:
            command = ["scripts/gradle-dev.sh", "--no-daemon", "--max-workers=2", "classes", "jar",
                "createGameTestServerLaunchScript", "-PgameTestBackend", "-PrcFaultTests", "-PrcFixture=" + token,
                "-PtestMods=" + ",".join(mods)]
            if run_owned(command, fixture / "build.log", self.args.build_timeout, row, "build") != 0:
                raise RuntimeError("real locked build failed; native NOT_RUN; failed command/log preserved without replay")
            if not self.unchanged():
                raise RuntimeError("source/locks changed during build")
            row["mod_JAR"] = {**metadata(ROOT / "build/libs/cross_tesseract-0.1.0-dev.jar"),
                "scope": "same-build packaged artifact SHA; this matrix actually launches frozen development classes/resources, not a packaged-JAR cold boot"}
            launcher, legacy, classpath = freeze_launch(fixture, backend, row)
            row["optional_runtime_JARs"], dependencies = runtime_mod_artifacts(legacy, classpath, mods)
            row["optional_required_server_dependencies"] = dependencies
            if native_processes() or not self.unchanged():
                raise RuntimeError("native process/source changed before isolated admission")
            exit_code = run_owned(["bash", str(launcher)], fixture / "native.log", self.args.native_timeout,
                row, "native", "@" + str(launcher.parent / "gameTestServerRunVmArgs.txt"))
            if "native_JVM_identity" not in row:
                raise RuntimeError("actual frozen native JVM identity not observed")
            row["native_validation"] = check_native((fixture / "native.log").read_text(), mods,
                row["expected_required_count"], dependencies, exit_code)
            for point in row["frozen_launch_files"] + row["frozen_class_resources"] + row["optional_runtime_JARs"]:
                path = Path(point["path"])
                if not path.is_absolute():
                    path = ROOT / path
                if digest(path) != point["sha256"]:
                    raise RuntimeError("frozen launch/class/resource/optional artifact changed during native run")
            row["passed"] = row["native_validation"]["passed"] and self.unchanged()
            row["state"] = "PASS" if row["passed"] else "FAIL"
        except Exception as error:
            row.update(state="FAIL", passed=False, failure=type(error).__name__ + ": " + str(error)[:3000])
        finally:
            row["source_and_locks_unchanged"] = self.unchanged()
            if not row["source_and_locks_unchanged"]:
                row.update(state="FAIL", passed=False)
            row["utc_end"] = utc()
            row["logs"] = [metadata(path, MAX_LOG + 1_048_576) for path in sorted(fixture.glob("*.log"))]
            new_json(fixture / "result.json", row)
            row["result"] = metadata(fixture / "result.json")
            self.save()

    def run(self):
        real_directory(ROOT / "scratch")
        with (ROOT / "scratch/rc-native-matrix.lock").open("a+") as guard:
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("another RC matrix controller is active")
            for row in self.report["combinations"]:
                if row["combination"] not in self.selected:
                    continue
                print(json.dumps({"combination": row["combination"], "phase": "START", "report": str(self.path.relative_to(ROOT))}), flush=True)
                try:
                    self.one(row)
                except KeyboardInterrupt:
                    row.update(state="FAIL", passed=False, failure="operator interrupted; assets retained")
                    self.report["operator_interrupted"] = True
                    self.save()
                    break
                except Exception as error:
                    row.update(state="FAIL", passed=False, failure=type(error).__name__ + ": " + str(error)[:3000])
                finally:
                    row.setdefault("utc_end", utc())
                    self.save()
                print(json.dumps({"combination": row["combination"], "state": row["state"],
                    "native_exit": row.get("native_exit"), "reason": row.get("failure", row.get("reason"))}), flush=True)
        self.report["utc_end"] = utc()
        self.report["source_and_locks_unchanged"] = self.unchanged()
        chosen = [row for row in self.report["combinations"] if row["combination"] in self.selected]
        self.report["selected_combinations_passed"] = all(row["state"] == "PASS" for row in chosen) and self.report["source_and_locks_unchanged"]
        self.report["passed"] = self.report["full_matrix_gate"] = all(row["state"] == "PASS" for row in self.report["combinations"]) and self.report["source_and_locks_unchanged"]
        self.report["actual_required_tests_passed"] = sum(row.get("expected_required_count", 0) for row in self.report["combinations"] if row["state"] == "PASS")
        self.save()
        print(json.dumps({"report": str(self.path.relative_to(ROOT)), "full_matrix_gate": self.report["full_matrix_gate"],
            "selected_combinations_passed": self.report["selected_combinations_passed"],
            "actual_required_tests_passed": self.report["actual_required_tests_passed"]}), flush=True)
        return 0 if self.report["selected_combinations_passed"] else 1


def self_test():
    class Tests(unittest.TestCase):
        def test_all_eight_unique_closures_and_current_source_test_counts(self):
            self.assertEqual(len(selection("all")), 8)
            counts = {label: len(expected_tests(mods)) for label, mods in COMBINATIONS.items()}
            self.assertEqual(counts["base"], 17)
            self.assertEqual(counts["ae2-gregtech-mekanism"], 24)
            self.assertEqual(sum(counts.values()), 164)
            for invalid in ("base,base", "ae2,unknown", "", "ae2+gregtech"):
                with self.assertRaises(ValueError): selection(invalid)
        def test_loopback_backend_only_and_new_unique_fixture(self):
            source = (ROOT / "config/gametest.properties").read_text()
            values = check_backend(source)
            config, cluster = fixture_config(source, "matrix-base-abcdef123456")
            self.assertEqual(properties(config)["transfer.maxBatchRecords"], "192")
            self.assertTrue(cluster.startswith("test_rcmatrix_"))
            self.assertNotEqual(cluster, values["cluster.id"])
            for key, value in (("mysql.url", "jdbc:mysql://remote:13306/cross_tesseract"), ("redis.uri", "redis://remote:16379"), ("mysql.user", "root")):
                changed = dict(values, **{key: value})
                with self.assertRaises(ValueError): check_backend("\n".join(k + "=" + v for k, v in changed.items()))
        def log(self, count=16, mods=()):
            ids = ("minecraft", "neoforge", "cross_tesseract", *mods)
            return "Mod List:\nName Version (Mod Id)\n" + "\n".join("Name 1.0 (" + mod + ")" for mod in ids) + "\n[00:00:01] next\n" + f"{count} tests are now running\n========= {count} GAME TESTS COMPLETE IN 2s\nAll {count} required tests passed :)\nCT_RC_CAPACITY_PASS input=128 external_native_output=128 duplicate_output=0 rejected_task_executions=0\nCT_RC_GROUP_PASS initial_native_input=384 actual_native_output=256 retained_TX=128 actual_groups=3+1 original_TX_ids_preserved=true\nCT_RC_WAKE_PASS input=128 first_batch_RESERVED=128 prepublication_RX=0 external_native_output=128 duplicate_output=0 final_SQL_pool=0 final_SQL_remaining=0 final_WAL_assets=0\nCT_RC_DISCOVERY_PASS native_input=288 native_output=288 pool=0 owned=0 WAL_mirror=0 old_LOCAL_not_exhausted=true\n"
        def test_pass_requires_real_loaded_ids_exact_totals_markers_and_exit(self):
            self.assertTrue(check_native(self.log(), (), 16, [], 0)["passed"])
            for text, code in ((self.log(15), 0), (self.log(), 1), (self.log().replace("CT_RC_GROUP_PASS", "NOT_A_MARKER"), 0),
                    (self.log().replace("CT_RC_WAKE_PASS", "NOT_A_MARKER"), 0),
                    (self.log().replace("CT_RC_DISCOVERY_PASS", "NOT_A_MARKER"), 0),
                    (self.log().replace("native_output=288", "native_output=0"), 0),
                    (self.log()+"CT_RC_DISCOVERY_NEGATIVE", 0),
                    (self.log().replace("first_batch_RESERVED=128", "first_batch_RESERVED=0"), 0),
                    (self.log().replace("prepublication_RX=0", "prepublication_RX=128"), 0),
                    (self.log().replace("final_WAL_assets=0", "final_WAL_assets=01"), 0),
                    (self.log() + "CT_RC_WAKE_PASS" + self.log().split("CT_RC_WAKE_PASS", 1)[1], 0),
                    (self.log(mods=("ae2",)), 0), (self.log().replace("(cross_tesseract)", "(other)"), 0),
                    (self.log() + "1 required tests failed", 0)):
                self.assertFalse(check_native(text, (), 16, [], code)["passed"])
            self.assertFalse(check_native(self.log(19, ("ae2",)), ("ae2",), 19, ["guideme"], 0)["passed"])
            self.assertTrue(check_native(self.log(19, ("ae2", "guideme")), ("ae2",), 19, ["guideme"], 0)["passed"])
        def test_default_cannot_launch_processes_or_query_network(self):
            with patch("subprocess.Popen", side_effect=AssertionError("offline process")), patch("socket.socket", side_effect=AssertionError("offline socket")):
                self.assertEqual(main([]), 0)
        def test_smoke_selection_never_implicitly_selects_remaining_groups(self):
            selected = selection("base,ae2-gregtech")
            self.assertEqual(len(selected), 2)
            self.assertEqual([label for label in COMBINATIONS if label not in selected], ["mekanism", "ae2", "ae2-mekanism", "gregtech", "gregtech-mekanism", "ae2-gregtech-mekanism"])
        def test_actual_runtime_classpath_is_frozen_and_optional_mods_are_not_assumed_legacy(self):
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                (directory / "classes").mkdir();(directory / "resources").mkdir()
                argument = directory / "gameTestServerRunClasspath.txt"
                mod = directory / "mekanism-fixed.jar"
                with zipfile.ZipFile(mod, "w") as archive:
                    archive.writestr("META-INF/neoforge.mods.toml", '[[mods]]\nmodId="mekanism"\nversion="fixed"\n')
                argument.write_text("-classpath\n" + os.pathsep.join((str(ROOT / "build/classes/java/main"),
                    str(ROOT / "build/resources/main"), str(mod))) + "\n")
                paths = freeze_classpath(argument, directory)
                self.assertEqual(paths[:2], [str(directory / "classes"), str(directory / "resources")])
                legacy = directory / "gameTestServerLegacyClasspath.txt";legacy.write_text("")
                artifacts, dependencies = runtime_mod_artifacts(legacy, argument, ("mekanism",))
                self.assertEqual([value["declared_mod_ids"] for value in artifacts], [["mekanism"]])
                self.assertEqual(dependencies, [])
                with self.assertRaises(ValueError): runtime_mod_artifacts(legacy, argument, ())
                with self.assertRaises(ValueError): freeze_classpath(argument, directory)
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    print(json.dumps({"mode": "OFFLINE_SELF_TEST", "tests": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "native_Gradle_SQL_matrix": "NOT_RUN"}))
    return 0 if result.wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    parser.add_argument("--accept-eula", action="store_true")
    parser.add_argument("--combinations", default="all", help="all or comma-separated canonical hyphen labels, e.g. base,ae2-gregtech")
    parser.add_argument("--label", default="rc", help="new report label; historical paths never overwritten")
    parser.add_argument("--build-timeout", type=float, default=300)
    parser.add_argument("--native-timeout", type=float, default=300)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        return self_test()
    if not args.execute:
        print(json.dumps({"mode": "OFFLINE", "native_Gradle_SQL_matrix": "NOT_RUN",
            "requires": "--execute --accept-eula after all A/B/C/Perf/GameTest JVMs stopped"}))
        return 0
    try:
        if not args.accept_eula:
            raise ValueError("operator must accept https://www.minecraft.net/eula and pass --accept-eula")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", args.label) or not 60 <= args.build_timeout <= 900 or not 60 <= args.native_timeout <= 900:
            raise ValueError("safe label and60..900s per-stage limits required")
        for key in ("CT_MYSQL_URL", "CT_MYSQL_USER", "CT_MYSQL_PASSWORD", "CT_REDIS_URI"):
            if key in os.environ:
                raise ValueError("backend environment overrides are not accepted")
        if any("-javaagent:" in os.environ.get(key, "") for key in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS")):
            raise ValueError("matrix requires unmodified native launch, no inherited test agent")
        return Matrix(args).run()
    except Exception as error:
        print(json.dumps({"passed": False, "failure": type(error).__name__ + ": " + str(error)[:3000]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
