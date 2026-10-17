#!/usr/bin/env python3
"""Optional real ENOSPC on a NON-AUTHORIZED COPY of this round's native32FE WAL.

Default is NOT RUN. --preflight is offline/read-only for the original fixture.
--execute is only for an explicit release after full soak, the extra f3Fast mix,
and normal fallback have all finished. It uses an already-local pinned image,
no network, a private1MiB tmpfs and a copied seed; never mounts the source world.
No source WAL/SQL/chunk is modified, consumed, replayed, refunded or imported.
This tests the production LocalJournal on a native-origin filesystem copy, not
Minecraft Runtime ENOSPC, live SQL recovery, hardware IO failure or power loss.
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
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'scratch/rc-native/fault-4dc94971b6d8'
RESULT_SHA = '7e74f15160d35b7561ce9f1a246b11447e795ca3fbdab73ec5e0edd46628fd25'
MAIN_SHA = '998b3fc31ae9fd813f5f916a345240451d476283a9b05672b1bcc6c80cf89504'
JAR_SHA = '1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f'
GROUP_SOURCE = 'src/main/java/dev/crosstesseract/test/RcGroupGameTests.java'
GROUP_SOURCE_SHA = '7ce04044a4197223d5195309adf6eebe6082a3dcfe2ad5e8e369259e9f84d49d'
HELPERS = {
    'scripts/rc_enospc_test.py': 'b5d997d4612b6df7e28c7880da02ae14cd45e4e62f65f6ffd7812f949f4dcd90',
    'scripts/optimization-restart-fallback-test.py': '61c0e399c3f8b2c0c0f6dba09def173374f13943cad343a8e54f2873aee4259c',
}
SOURCES = (
    'src/main/java/dev/crosstesseract/backend/LocalJournal.java',
    'src/main/java/dev/crosstesseract/core/DomainException.java',
    'src/main/java/dev/crosstesseract/core/LocalSnapshot.java',
    'src/main/java/dev/crosstesseract/core/Resource.java',
    'src/main/java/dev/crosstesseract/core/ThermalBuffer.java',
    'src/main/java/dev/crosstesseract/core/Protocol.java',
    'src/main/java/dev/crosstesseract/core/Metrics.java',
    'scripts/rc_native_enospc_probe.java',
)
MARKER = re.compile(r'CT_RC_GROUP_PASS endpoints=\[([^\]\r\n]+)\] initial_native_input=384 actual_native_output=256 retained_TX=128 actual_groups=3\+1 first_LOCAL=3 first_RESERVED=1 original_TX_ids_preserved=true')
DOCKER_SOCKET = 'unix:///var/run/docker.sock'
DOCKER_ENV_OVERRIDES = ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def docker_command(*arguments):
    return ['docker', '--host=' + DOCKER_SOCKET, *arguments]


def docker_environment(environment=None):
    cleaned = dict(os.environ if environment is None else environment)
    for key in DOCKER_ENV_OVERRIDES:
        cleaned.pop(key, None)
    return cleaned


def run_docker(command, **kwargs):
    if command[:2] != docker_command() or 'env' in kwargs:
        raise ValueError('Every Docker call must use the fixed local socket and sanitized environment')
    return subprocess.run(command, env=docker_environment(), **kwargs)


def read(path, limit):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    if '..' in path.parts or not path.is_relative_to(ROOT):
        raise ValueError('Only exact repository paths permitted')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('Symlink input refused')
        if part == ROOT:
            break
    if not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Bounded regular input required: ' + str(path))
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError('Input grew beyond bound')
    return data


def meta(path, data=None):
    data = read(path, 2 * 1024 * 1024) if data is None else data
    return {'path': str(Path(path).relative_to(ROOT)), 'sha256': digest(data), 'bytes': len(data)}


def load_helpers():
    modules = []
    for index, (filename, expected) in enumerate(HELPERS.items()):
        if digest(read(ROOT / filename, 262144)) != expected:
            raise ValueError('Reviewed offline helper changed: ' + filename)
        spec = importlib.util.spec_from_file_location('rc_native_enospc_offline_' + str(index), ROOT / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def group_endpoints(text):
    matches = MARKER.findall(text)
    if len(matches) != 1:
        raise ValueError('Exactly one fully qualified native group PASS marker required')
    endpoints = [str(UUID(value.strip())) for value in matches[0].split(',')]
    if len(endpoints) != 4 or len(set(endpoints)) != 4:
        raise ValueError('Four unique marker endpoint IDs required')
    return endpoints


def validate_snapshot(snapshot, selected, world):
    if snapshot.get('format') != 2 or snapshot['endpoint'] != selected or snapshot['world'] != world:
        raise ValueError('Selected actual endpoint/world mismatch')
    deposits = snapshot['deposits']
    if (len(deposits) != 32 or any(value['amount'] != 1 for value in deposits)
            or len({value['transaction'] for value in deposits}) != 32
            or len({value['channel'] for value in deposits}) != 1
            or any(value['remaining'] != 0 for value in snapshot['credits'])
            or not 0 <= snapshot['revision'] < 2**63 - 1):
        raise ValueError('Only the original32 pending native FE with no positive RX may be copied')
    return {'endpoint': selected, 'world': world, 'generation': snapshot['generation'],
            'original_revision': snapshot['revision'], 'attempted_revision': snapshot['revision'] + 1,
            'channel': deposits[0]['channel'], 'TX_FE': 32, 'deposit_count': 32,
            'business_IDs': [value['transaction'] for value in deposits],
            'credit_tombstone_count': len(snapshot['credits']), 'positive_RX': 0,
            'scope': 'Current source WAL decode plus closed native assertions. No current SQL query or new asset is implied.'}


def preflight(endpoint, expected_sha=None):
    if not endpoint or str(UUID(endpoint)) != endpoint:
        raise ValueError('Explicit canonical --source-endpoint required; no automatic file selection')
    result_path = FIXTURE / 'result.json'
    result_raw = read(result_path, 16384)
    if digest(result_raw) != RESULT_SHA:
        raise ValueError('The selected original native result identity changed')
    result = json.loads(result_raw)
    if (result['fixture'] != 'fault-4dc94971b6d8'
            or result['cluster'] != 'test_rcnative_fault_4dc94971b6d8'
            or result['passed'] is not True or result['native_exit'] != 0
            or result['required_native_tests'] != 7 or result['source_unchanged'] is not True
            or result['actual_split_positive_pass_marker'] is not True
            or result['source_manifest_sha256'] != MAIN_SHA or result['JAR_sha256'] != JAR_SHA):
        raise ValueError('Original native/source/JAR qualification failed')
    log_path = FIXTURE / 'native.log'
    log = read(log_path, 2 * 1024 * 1024)
    if digest(log) != result['logs']['native.log']:
        raise ValueError('Original native log SHA mismatch')
    text = log.decode('utf-8')
    endpoints = group_endpoints(text)
    if endpoint not in endpoints or 'All 7 required tests passed' not in text or 'Stopping server' not in text:
        raise ValueError('Explicit endpoint is not in the completed native group fixture')
    sources = sorted((ROOT / 'src/main/java').rglob('*.java'))
    if not sources or len(sources) > 1024:
        raise ValueError('Bounded native-source manifest required')
    canonical = b''
    total = 0
    for path in sources:
        data = read(path, 262144)
        total += len(data)
        if total > 8 * 1024 * 1024:
            raise ValueError('Native-source byte bound')
        canonical += str(path.relative_to(ROOT)).encode() + b'\0' + hashlib.sha256(data).digest()
    if digest(canonical) != MAIN_SHA or digest(read(ROOT / GROUP_SOURCE, 262144)) != GROUP_SOURCE_SHA:
        raise ValueError('Current reviewed sources no longer match the passed native source manifest')
    _, pure = load_helpers()
    world_path = FIXTURE / 'game/world/cross_tesseract/world-id'
    world_bytes = read(world_path, 128)
    world = str(UUID(world_bytes.decode().strip()))
    wal = FIXTURE / ('game/world/cross_tesseract/journal/' + endpoint + '.ctj')
    seed = read(wal, 16384)
    sha = digest(seed)
    if expected_sha is not None and (not re.fullmatch('[0-9a-f]{64}', expected_sha) or sha != expected_sha):
        raise ValueError('Source WAL changed since the reviewed preflight SHA')
    snapshot = pure.decode_fe_wal(seed)
    asset = validate_snapshot(snapshot, endpoint, world)
    if digest(read(wal, 16384)) != sha:
        raise ValueError('Source WAL changed during read-only preflight')
    return {'native_result': meta(result_path, result_raw), 'native_log': meta(log_path, log),
            'native_marker': MARKER.search(text).group(0), 'marker_endpoint_IDs': endpoints,
            'native_source_manifest_sha256': MAIN_SHA, 'native_JAR_sha256': JAR_SHA,
            'group_test_source': meta(ROOT / GROUP_SOURCE), 'original_world_id_file': meta(world_path, world_bytes),
            'source_WAL_before': meta(wal, seed), 'source_WAL_after_preflight': meta(wal, seed),
            'snapshot': asset,
            'native_lineage': 'The SHA-bound native test proves384 actual FE input,256 actual native output, and four independently retained32FE TX sets with preserved IDs. The selected current WAL supplies its exact32 IDs; per-input business IDs were not separately logged at capability entry.',
            'current_SQL_state': 'UNMEASURED_NO_QUERY', 'source_mutations': False,
            'copy_scope': 'A later private copy has no database authorization and is never a second spendable asset, imported, replayed or refunded.'}, seed


def create_command(image_id, frozen, token, endpoint, seed_sha, jdk=None):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id) or str(UUID(endpoint)) != endpoint or not re.fullmatch('[0-9a-f]{64}', seed_sha):
        raise ValueError('Exact image/endpoint/seed identities required')
    compiler, java = ('/jdk/bin/javac', '/jdk/bin/java') if jdk else ('javac', 'java')
    script = compiler + ' -Xmaxerrs 10 -d /tmp ' + ' '.join('/source/' + filename for filename in SOURCES)
    script += '\nexec ' + java + ' -cp /tmp rc_native_enospc_probe /wal /source/seed/' + endpoint + '.ctj ' + seed_sha
    uid, gid = os.getuid(), os.getgid()
    command = docker_command('create', '--name', 'ct-rc-native-enospc-' + token,
               '--label', 'ct.rc_native_enospc_token=' + token, '--pull=never',
               '--network', 'none', '--read-only', '--cap-drop=ALL', '--user', str(uid) + ':' + str(gid),
               '--security-opt=no-new-privileges', '--memory=384m', '--memory-swap=384m',
               '--cpus=0.25', '--pids-limit=64', '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m,mode=1777',
               '--tmpfs', '/wal:rw,nosuid,nodev,size=1m,mode=0700,uid=' + str(uid) + ',gid=' + str(gid),
               '--mount', 'type=bind,src=' + str(frozen) + ',dst=/source,readonly',
               '--env', 'LC_ALL=C', '--env', 'JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=1 -Xms16m -Xmx128m',
               '--entrypoint', '/bin/sh')
    if jdk:
        command += ['--mount', 'type=bind,src=' + str(jdk) + ',dst=/jdk,readonly']
    return command + [image_id, '-eu', '-c', script]


def ensure_stopped():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if args and Path(os.fsdecode(args[0])).name == 'java' and any(re.search(
                    rb'(server[ABC]|serverPerf|gameTestServer)RunVmArgs\.txt|net\.minecraft\.server\.Main|forgeserverdev', value) for value in args):
                raise ValueError('Native JVM still running; wait for the explicit full/f3Fast/fallback release')
        except (FileNotFoundError, PermissionError):
            continue


def private_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('xb') as output:
        os.chmod(path, 0o600)
        output.write(data)


def execute(args):
    if not args.expected_source_wal_sha256:
        raise ValueError('Execution requires the exact independently reviewed --expected-source-wal-sha256')
    proof, seed = preflight(args.source_endpoint, args.expected_source_wal_sha256)
    ensure_stopped()
    filesystem, _ = load_helpers()
    if not args.image or not filesystem.PINNED.fullmatch(args.image):
        raise ValueError('Already-local immutable --image required; no pull/build allowed')
    inspected = run_docker(docker_command('image', 'inspect', '--format', '{{.Id}}', args.image),
                               capture_output=True, text=True, check=True, timeout=10)
    image_id = inspected.stdout.strip()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('Invalid inspected local image ID')
    jdk, jdk_proof = filesystem.jdk_evidence(args.jdk, args.jdk_archive) if args.jdk else (None, 'IMAGE_JDK_RECORDED_BY_EXECUTED_PROBE_ONLY')
    if args.jdk_archive and not args.jdk:
        raise ValueError('--jdk-archive requires --jdk')
    token = uuid4().hex
    scratch = ROOT / 'scratch'
    if scratch.is_symlink():
        raise ValueError('No symlink scratch root')
    directory = scratch / ('rc-native-enospc-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + token)
    directory.mkdir(mode=0o700)
    frozen = directory / 'source'
    frozen.mkdir(mode=0o700)
    copied = []
    for filename in SOURCES:
        data = read(ROOT / filename, 262144)
        private_write(frozen / filename, data)
        copied.append({'path': filename, 'sha256': digest(data), 'bytes': len(data)})
    private_write(frozen / ('seed/' + args.source_endpoint + '.ctj'), seed)
    result = {'utc_start': utc(), 'passed': False, 'source_proof': proof,
              'recipe': meta(Path(__file__).resolve()), 'helpers': HELPERS,
              'frozen_sources': copied, 'local_image_requested': args.image, 'local_image_id': image_id,
              'host_JDK_readonly': jdk_proof, 'container_network': 'none', 'private_WAL_tmpfs_bytes': 1048576,
              'Docker_transport': {'host': DOCKER_SOCKET, 'cleared_environment_keys': list(DOCKER_ENV_OVERRIDES),
                                   'scope': 'Every image inspect/create/start/state inspect/remove call; no default or remote context'},
              'container_identity': {'uid': os.getuid(), 'gid': os.getgid(),
                                     'docker_user': str(os.getuid()) + ':' + str(os.getgid()),
                                     'uid_zero': os.getuid() == 0,
                                     'scope': 'Actual executing process UID/GID, possibly0; never a fixed UID1000/non-root guarantee. ALL capabilities dropped, readonly root and network none remain independent constraints.'},
              'source_world_mounted': False, 'source_SQL_modified_or_queried': False,
              'seed_copy_authorized_by_SQL': False, 'copy_imported_consumed_replayed_refunded': False,
              'native_Runtime_ENOSPC_SQL_recovery_hardware_power_loss': 'NOT_RUN'}
    container = None
    started = time.monotonic()
    try:
        command = create_command(image_id, frozen, token, args.source_endpoint, args.expected_source_wal_sha256, jdk)
        result['create_command'] = command
        created = run_docker(command, capture_output=True, text=True, check=True, timeout=15)
        container = created.stdout.strip()
        if not re.fullmatch('[0-9a-f]{64}', container):
            raise ValueError('Invalid owned container ID')
        result['owned_container_id'] = container
        for filename in ('stdout.log', 'stderr.log'):
            private_write(directory / filename, b'')
        with (directory / 'stdout.log').open('ab') as output, (directory / 'stderr.log').open('ab') as errors:
            attached = run_docker(docker_command('start', '--attach', container), stdout=output, stderr=errors,
                                      check=False, timeout=args.timeout)
        result['docker_attach_exit_code'] = attached.returncode
        inspected = run_docker(docker_command('inspect', '--format', '{{.State.ExitCode}}', container),
                                   capture_output=True, text=True, check=True, timeout=10)
        result['container_exit_code'] = int(inspected.stdout.strip())
        if any((directory / filename).stat().st_size > 262144 for filename in ('stdout.log', 'stderr.log')):
            raise ValueError('Bounded probe output exceeded')
        probe = json.loads((directory / 'stdout.log').read_text())
        result['probe'] = probe
        result['passed'] = (attached.returncode == result['container_exit_code'] == 0
                            and probe.get('passed') is True and probe.get('file_store_type') == 'tmpfs'
                            and probe.get('controlled_IOException_injection') is False
                            and probe.get('WAL_actual_exception', {}).get('ENOSPC_message_observed') is True
                            and probe.get('old32FE_copy_and_business_IDs_preserved_after_failure') is True
                            and probe.get('retry_same_IDs_and_quantities') is True
                            and probe.get('durable_TX_after_failure_FE') == probe.get('durable_TX_after_retry_FE') == 32
                            and probe.get('original_business_IDs') == proof['snapshot']['business_IDs']
                            and probe.get('original_revision') == proof['snapshot']['original_revision']
                            and probe.get('retry_revision') == proof['snapshot']['attempted_revision']
                            and probe.get('readonly_seed_after_sha256') == args.expected_source_wal_sha256)
    except Exception as error:
        result['failure_class'] = type(error).__name__
        result['failure'] = str(error)[:2048]
    finally:
        if container is not None:
            try:
                removed = run_docker(docker_command('rm', '--force', '--volumes', container), capture_output=True, timeout=15)
                result['owned_copy_container_remove_exit_code'] = removed.returncode
                if removed.returncode:
                    result['passed'] = False
            except Exception as error:
                result['passed'] = False
                result['container_cleanup_failure_class'] = type(error).__name__
        try:
            after, _ = preflight(args.source_endpoint, args.expected_source_wal_sha256)
            result['source_WAL_after'] = after['source_WAL_before']
            result['original_source_WAL_and_native_evidence_unchanged'] = after == proof
            if after != proof:
                result['passed'] = False
        except Exception as error:
            result['passed'] = False
            result['source_after_failure'] = type(error).__name__ + ': ' + str(error)[:1024]
        result['utc_end'] = utc()
        result['elapsed_seconds'] = time.monotonic() - started
        for filename in ('stdout.log', 'stderr.log'):
            if (directory / filename).is_file():
                result[filename] = meta(directory / filename)
        target = directory / 'result.json'
        private_write(target, (json.dumps(result, indent=2, allow_nan=False) + '\n').encode())
        print(json.dumps({'passed': result['passed'], 'report': str(target.relative_to(ROOT)),
                          'source_world_or_SQL_modified': False, 'native_Runtime_ENOSPC': 'NOT_RUN'}))
    return 0 if result['passed'] else 1


class OfflineTests(unittest.TestCase):
    def test_marker_requires_exact_source_and_four_unique_endpoints(self):
        ids = [str(uuid4()) for _ in range(4)]
        text = 'CT_RC_GROUP_PASS endpoints=[' + ', '.join(ids) + '] initial_native_input=384 actual_native_output=256 retained_TX=128 actual_groups=3+1 first_LOCAL=3 first_RESERVED=1 original_TX_ids_preserved=true'
        self.assertEqual(group_endpoints(text), ids)
        with self.assertRaises(ValueError):
            group_endpoints(text + '\n' + text)
        with self.assertRaises(ValueError):
            group_endpoints(text.replace('retained_TX=128', 'retained_TX=0'))

    def test_snapshot_requires_real32_shape_and_rejects_positive_RX(self):
        endpoint, world, channel = (str(uuid4()) for _ in range(3))
        snapshot = {'format': 2, 'endpoint': endpoint, 'world': world, 'generation': 1, 'revision': 20,
                    'deposits': [{'transaction': str(uuid4()), 'channel': channel, 'amount': 1} for _ in range(32)], 'credits': []}
        self.assertEqual(validate_snapshot(snapshot, endpoint, world)['TX_FE'], 32)
        for changed in (dict(snapshot, deposits=snapshot['deposits'][:-1]),
                        dict(snapshot, credits=[{'remaining': 1}]), dict(snapshot, revision=2**63 - 1),
                        dict(snapshot, format=1)):
            with self.assertRaises(ValueError):
                validate_snapshot(changed, endpoint, world)
        with self.assertRaises(ValueError):
            validate_snapshot(snapshot, str(uuid4()), world)

    def test_private_container_never_mounts_original_world(self):
        endpoint = str(uuid4())
        command = create_command('sha256:' + 'a' * 64, Path('/private/only-frozen-copy'), 'test', endpoint, 'b' * 64)
        self.assertEqual(command[command.index('--network') + 1], 'none')
        self.assertIn('--read-only', command)
        self.assertIn('--cap-drop=ALL', command)
        self.assertIn('--pull=never', command)
        self.assertEqual(command[:2], docker_command())
        self.assertEqual(command[command.index('--user') + 1], str(os.getuid()) + ':' + str(os.getgid()))
        self.assertFalse(any(str(FIXTURE) in value or '/dev/shm' in value for value in command))
        mounts = [command[index + 1] for index, value in enumerate(command) if value == '--mount']
        self.assertFalse(any('docker.sock' in value for value in mounts))
        self.assertTrue(any(value.endswith('dst=/source,readonly') for value in command))
        self.assertIn('/source/seed/' + endpoint + '.ctj', command[-1])
        self.assertNotIn('rc_enospc_probe ', command[-1])

    def test_all_Docker_calls_pin_local_socket_and_remove_remote_environment(self):
        remote = {key: 'untrusted-remote-setting' for key in DOCKER_ENV_OVERRIDES}
        remote['RC_NATIVE_TEST_SAFE_SENTINEL'] = 'preserved'
        commands = [docker_command('image', 'inspect', 'sha256:' + 'a' * 64),
                    create_command('sha256:' + 'a' * 64, Path('/private/frozen'), 'test', str(uuid4()), 'b' * 64),
                    docker_command('start', '--attach', 'own-container'),
                    docker_command('inspect', '--format', '{{.State.ExitCode}}', 'own-container'),
                    docker_command('rm', '--force', '--volumes', 'own-container')]
        with patch.dict(os.environ, remote), patch('subprocess.run') as process:
            for command in commands:
                run_docker(command, timeout=1)
            self.assertEqual(process.call_count, 5)
            for call in process.call_args_list:
                self.assertEqual(call.args[0][:2], ['docker', '--host=unix:///var/run/docker.sock'])
                self.assertTrue(all(key not in call.kwargs['env'] for key in DOCKER_ENV_OVERRIDES))
                self.assertEqual(call.kwargs['env']['RC_NATIVE_TEST_SAFE_SENTINEL'], 'preserved')
        with self.assertRaises(ValueError):
            run_docker(['docker', 'inspect', 'other-context'])
        with self.assertRaises(ValueError):
            run_docker(docker_command('inspect', 'own'), env={})

    def test_bad_seed_image_and_external_source_paths_rejected(self):
        with self.assertRaises(ValueError):
            create_command('redis:7.4.6', Path('/copy'), 'test', str(uuid4()), 'a' * 64)
        with self.assertRaises(ValueError):
            create_command('sha256:' + 'a' * 64, Path('/copy'), 'test', str(uuid4()), 'short')
        with self.assertRaises(ValueError):
            read('/tmp/other-world.ctj', 16384)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--preflight', action='store_true', help='Read only the exact new native fixture; no Docker/JDK/SQL/process execution or seed copy')
    modes.add_argument('--self-test', action='store_true')
    parser.add_argument('--source-endpoint')
    parser.add_argument('--expected-source-wal-sha256')
    parser.add_argument('--image', help='Already-local immutable image digest, never pulled/built')
    parser.add_argument('--jdk', help='Optional exact scratch/jdk/jdk-21.0.8+9 readonly bind')
    parser.add_argument('--jdk-archive')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    if args.self_test:
        outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OfflineTests))
        print(json.dumps({'offline_self_test_passed': outcome.wasSuccessful(), 'Docker_JDK_SQL_native_ENOSPC': 'NOT_RUN'}))
        return 0 if outcome.wasSuccessful() else 1
    if not args.execute and not args.preflight:
        print(json.dumps({'execution': 'NOT_RUN', 'requires': 'Explicit release after full/f3Fast/normal-fallback completion, then --execute with reviewed endpoint/source SHA/local image; --preflight is read-only'}))
        return 0
    if not args.source_endpoint or not 1 <= args.timeout <= 180:
        parser.error('Explicit --source-endpoint and timeout1..180 required')
    if args.preflight:
        proof, _ = preflight(args.source_endpoint, args.expected_source_wal_sha256)
        report = {'execution': 'OFFLINE_READ_ONLY_PREFLIGHT', 'utc': utc(), 'source_proof': proof,
                  'recipe': meta(Path(__file__).resolve()),
                  'proposed_java_probe': meta(ROOT / 'scripts/rc_native_enospc_probe.java'),
                  'helpers': HELPERS, 'Docker_JDK_SQL_native_ENOSPC': 'NOT_RUN'}
        target = ROOT / 'reports/rc-20261017' / ('native-origin-enospc-preflight-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:12] + '.json')
        private_write(target, (json.dumps(report, indent=2, allow_nan=False) + '\n').encode())
        print(json.dumps({'execution': report['execution'], 'report': str(target.relative_to(ROOT)),
                          'source_endpoint': args.source_endpoint,
                          'source_WAL_sha256': proof['source_WAL_before']['sha256'],
                          'Docker_JDK_SQL_native_ENOSPC': 'NOT_RUN'}))
        return 0
    return execute(args)


if __name__ == '__main__':
    sys.exit(main())
