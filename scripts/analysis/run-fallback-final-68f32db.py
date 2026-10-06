#!/usr/bin/env python3
"""Serial final same-world fallback after the two retained validator failures.

This is a version-specific development recipe, not a production recovery tool.
No build, backend stop, force kill, world deletion, old input/pull replay, or
automatic configuration restoration. Requires the ROOT-completed asset gates.
The child uses fresh IDs; the original128FE remains untouched. --execute only.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
import uuid

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print('NOT_RUN: requires --execute and the stopped isolated68 fixture.')
        return 0
    spec = importlib.util.spec_from_file_location('ct_final_fallback_helpers', ROOT / 'scripts/optimization-restart-fallback-test.py')
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    guard = helper.RestartFallback(argparse.Namespace(timeout=120, quiet=2.2, poll=.2))
    guard.environment_gate()
    if any(guard.running().values()):
        raise ValueError('All selected test JVMs must already be stopped')
    locks = guard.acquire_stopped_locks()
    if not locks:
        raise ValueError('Stopped launch locks unavailable')
    evidence = {}
    for name in ('optimization-restart-fallback-after-second-failure-audit.json',
                 'optimization-restart-fallback-second-failure-assets-audit.json',
                 'optimization-restart-fallback-root-flags-restoration.json'):
        path = ROOT / 'reports' / name
        body = json.loads(helper.bounded_file(path, 4 * 1024 * 1024))
        evidence[name] = {'sha256': digest(path), 'body': body}
    first = evidence['optimization-restart-fallback-after-second-failure-audit.json']['body']
    second = evidence['optimization-restart-fallback-second-failure-assets-audit.json']['body']
    restored = evidence['optimization-restart-fallback-root-flags-restoration.json']['body']
    if not first.get('read_only') or first['ownership']['total_effective_asset_FE'] != 128 or \
            not second.get('read_only') or len(second['fixtures']) != 2 or \
            any(f['input_FE'] != 189 or f['actual_output_FE'] != 189 or f['effective_remaining_FE'] != 0 for f in second['fixtures']) or \
            restored.get('passed') is not True or not restored.get('processes_all_stopped'):
        raise ValueError('ROOT asset/clean-stop gates do not match')
    files = guard.files_gate(('true', 'true'))
    for server in 'ABC':
        if files[server] != restored['result_files'][server]:
            raise ValueError('Post-audit configuration/world bytes changed')
    guard.container = helper.module('ct_final_fallback_files', 'optimization-container-benchmark.py')
    guard.source_gate()
    original_path = ROOT / 'reports/optimization-restart-fallback-68f32db-20261006T192436Z-9e30ef6d.json'
    if digest(original_path) != '1e4b7550dafad1382009a3cceb4658cf5d71eccd37c4aaf269ef1a82d30d15f7':
        raise ValueError('Original failed evidence changed')
    original = json.loads(original_path.read_text())
    for server in 'ABC':
        entry = original['identity'][server]['launch_provenance']
        if digest(Path(entry['launcher'])) != entry['launcher_sha256']:
            raise ValueError('Frozen launcher changed')
        subprocess.run(['bash', 'scripts/start-frozen-dev.sh', '--check', server, entry['launcher']],
                       cwd=ROOT, check=True, capture_output=True, timeout=30)
        for manifest in entry['selected_launch_manifests']:
            if guard.container.class_manifest(Path(manifest['path'])) != manifest:
                raise ValueError('Frozen class/resource bytes changed')
    token = uuid.uuid4().hex[:8]
    report_path = ROOT / ('reports/optimization-final-fallback-controller-68f32db-' + token + '.json')
    report = {'utc_start': helper.utc(), 'passed': False, 'state': 'RUNNING', 'root_asset_gates': evidence,
              'source_and_JAR_gate': guard.report['source_evidence'], 'initial_files': files,
              'lifecycle': [], 'script_sha256': digest(Path(__file__)), 'failures': [],
              'scope': 'New IDs only; same frozen68 JVMs/worlds; normal stops; original128 untouched. No performance or world-save atomicity claim.'}
    def save():
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    owned = False
    rcon = helper.module('ct_final_fallback_rcon', 'rcon.py').command
    try:
        for handle in locks.values():
            handle.close()
        locks = {}
        owned = True
        for server in 'ABC':
            launch = original['identity'][server]['launch_provenance']['launcher']
            log = ROOT / ('logs/optimization-final-fallback-' + token + '-' + server + '.log')
            with log.open('x') as stream:
                process = subprocess.Popen(['bash', 'scripts/start-frozen-dev.sh', server, launch],
                                           cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            report['lifecycle'].append({'action': 'start_once', 'server': server, 'launcher_PID': process.pid,
                                        'launcher': launch, 'log': str(log.relative_to(ROOT)), 'utc': helper.utc()})
        save()
        ready, deadline = set(), time.monotonic() + 120
        while ready != set('ABC'):
            if time.monotonic() > deadline:
                raise ValueError('Startup timeout; no repeated start')
            for server in 'ABC':
                if server not in ready:
                    try:
                        if 'STATUS online' in rcon(helper.PORTS[server], 'ct_test status', timeout=5):
                            ready.add(server)
                    except OSError:
                        pass
            time.sleep(.5)
        before = set((ROOT / 'reports').glob('optimization-restart-fallback-68f32db-*.json'))
        log = ROOT / ('logs/optimization-final-fallback-' + token + '-test.log')
        with log.open('x') as stream:
            child = subprocess.run(['python3', '-B', 'scripts/optimization-restart-fallback-test.py', '--execute'],
                                   cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        added = set((ROOT / 'reports').glob('optimization-restart-fallback-68f32db-*.json')) - before
        if len(added) != 1:
            raise ValueError('Expected one unique child report')
        path = next(iter(added))
        result = json.loads(path.read_text())
        report['child'] = {'path': str(path.relative_to(ROOT)), 'sha256': digest(path), 'exit_code': child.returncode,
                           'log': str(log.relative_to(ROOT))}
        if child.returncode or result.get('passed') is not True:
            raise ValueError('New fallback failed; assets/configuration retained')
        if any(event.get('endpoint') in ('ba584569-6a07-4abf-9dca-f6a331c4c558', '9a82dabc-03a9-4c75-a176-6e96b6f34551')
               or event.get('channel') == '57536927-3421-43cd-8fc5-9df4df58e920' for event in result['business_events']):
            raise ValueError('Child touched the retained original128 fixture')
        report.update(passed=True, state='FUNCTIONAL_PASS_PENDING_CLEAN_STOP')
    except BaseException as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
        report.update(passed=False, state='FAILED_RETAINED_ASSETS_CONFIG')
    finally:
        if owned:
            try:
                running = guard.running()
                for server in 'ABC':
                    if len(running[server]) > 1:
                        raise ValueError('Ambiguous test JVM; no unrelated stop')
                    if running[server]:
                        config = helper.properties(helper.bounded_file(ROOT / ('run-' + server) / 'cross-tesseract.properties'))
                        if config.get('server.id') != 'opt-regression-68f32db-fast-' + server:
                            raise ValueError('Test identity changed; do not stop unrelated process')
                        try:
                            rcon(helper.PORTS[server], 'stop', timeout=5)
                        except OSError:
                            pass
                deadline = time.monotonic() + 120
                while True:
                    locks = guard.acquire_stopped_locks()
                    if locks:
                        break
                    if time.monotonic() > deadline:
                        raise ValueError('Clean stop timeout; no force kill')
                    time.sleep(.5)
                report['lifecycle'].append({'action': 'normal_stop_all_ABC_locks_acquired', 'utc': helper.utc()})
            except BaseException as error:
                report['failures'].append('Stop: ' + type(error).__name__ + ': ' + str(error))
                report['passed'] = False
        for handle in (locks or {}).values():
            handle.close()
        report['utc_end'] = helper.utc()
        if report['passed']:
            report['state'] = 'COMPLETED_FUNCTIONAL_PASS_AND_NORMAL_STOP'
        save()
        print(json.dumps({'report': str(report_path.relative_to(ROOT)), 'passed': report['passed'], 'state': report['state']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
