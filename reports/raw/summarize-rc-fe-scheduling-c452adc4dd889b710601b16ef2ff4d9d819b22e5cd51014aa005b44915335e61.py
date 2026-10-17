#!/usr/bin/env python3
"""Offline scheduling evidence from explicitly CLOSED, bound RC FE controllers.

Repeated --controller selects archived runs. Missing scheduling counters remain
UNMEASURED, including older f3 runtimes. No native, SQL, RCON or JDK is invoked.
JSON/CSV outputs use exclusive-create UUID names and never overwrite evidence.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest
from uuid import uuid4

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts/analysis/summarize-rc-mix.py'
spec = importlib.util.spec_from_file_location('rc_fe_scheduling_offline_archive', HELPER)
archive_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive_helpers)
REASONS = ('input', 'rx_consumed', 'local_hint', 'remote_hint', 'demand', 'poll', 'recovery')
COUNTERS = tuple('schedule_' + reason + '_' + phase for reason in REASONS
                 for phase in ('signals', 'captured', 'effective'))
STAGES = {
    'capture': ('dev/crosstesseract/runtime/RuntimeService', 'capture',
                'One endpoint argument per invocation, including a capture attempt returning null; successful requests/unique devices are not counted by this histogram.'),
    'notification_fanout': ('dev/crosstesseract/runtime/RuntimeService', 'wakeChannel',
                            'Channel wake scheduling probe only; does not measure all Redis/notification worker activity or count scanned/selected endpoints.'),
    'prepare_publication': ('dev/crosstesseract/runtime/RuntimeService', 'preparePublication',
                            'Publication preparation invocation; request/result list sizes are not recorded by the timing hook.'),
    'finish': ('dev/crosstesseract/runtime/RuntimeService', 'finish',
               'One Prepared endpoint argument per invocation; may return before doing work. Completed/unique device count is not recorded.'),
    'wal_write': ('dev/crosstesseract/backend/LocalJournal', 'write',
                  'All selected LocalJournal.write invocations, including identical-snapshot returns; not a count or duration of independent file/directory fsyncs.'),
    'channel_SQL': ('dev/crosstesseract/backend/Authority', 'channelBatch',
                    'Authority channelBatch invocation; request list length is not recorded by this timing hook.'),
    'publish_SQL': ('dev/crosstesseract/backend/Authority', 'publishBatch',
                    'Authority publishBatch invocation; publication list length is not recorded by this timing hook.'),
    'SQL_transaction': ('dev/crosstesseract/backend/Sql', 'transaction',
                        'Java transaction helper wall duration/call count, including retry/wait scope; not SQL statement or physical commit count.'),
}
FIELDS = ('controller', 'runtime_revision', 'scenario', 'repeat', 'scope', 'server',
          'row_kind', 'metric', 'status', 'before', 'after', 'delta', 'known_delta_sum',
          'count', 'inclusive_sum_ns', 'exclusive_sum_ns', 'exceptional_returns', 'detail')


def counter_delta(before, after, key):
    a, z = before.get(key), after.get(key)
    if a is None or z is None:
        return {'status': 'UNMEASURED', 'before': a, 'after': z, 'delta': None,
                'reason': 'Counter absent from one/both archived observations; no zero imputation or unsupported-version inference'}
    if type(a) is not int or type(z) is not int or not 0 <= a <= z:
        raise ValueError('Noninteger, negative or reset scheduling counter: ' + key)
    return {'status': 'MEASURED', 'before': a, 'after': z, 'delta': z - a}


def aggregate(values):
    measured = [value['delta'] for value in values.values() if value['status'] == 'MEASURED']
    return {'status': 'MEASURED' if len(measured) == 3 else ('PARTIAL' if measured else 'UNMEASURED'),
            'delta': sum(measured) if len(measured) == 3 else None,
            'known_delta_sum': sum(measured) if measured else None,
            'measured_servers': [server for server, value in values.items() if value['status'] == 'MEASURED'],
            'unmeasured_servers': [server for server, value in values.items() if value['status'] != 'MEASURED'],
            'scope': 'Known-server sum only when partial; never a measured three-JVM total or a business attribution ratio.'}


def load_run(archive, filename):
    controller_ref, controller = archive.read(filename)
    if (controller.get('state') != 'COMPLETE' or not controller.get('utc_end')
            or controller.get('phase') != 'fe' or controller.get('mode') != 'fast'
            or controller.get('variant') != 'default' or controller.get('workload_exit') != 0
            or any(controller.get(key) is not True for key in
                   ('passed', 'qualified_passed', 'functional_passed', 'raw_passed',
                    'all_own_launchers_exited_and_locks_free')) or controller.get('failures')
            or not all(controller.get(key, {}).get('matches_expected') is True for key in
                       ('source_before', 'source_after_workload', 'source_after_stop'))):
        raise ValueError('A completed qualified FE/fast/default controller is required')
    raw_ref, raw = archive.reference(controller['raw_report'])
    runtime_ref, runtime = archive.reference(controller['runtime_manifest'])
    if (raw.get('passed') is not True or raw.get('failures')
            or raw['operator_runtime_revision'] != controller['runtime_revision']
            or raw['probe_manifest'] != controller['runtime_manifest']
            or raw['probe_configuration'] != runtime):
        raise ValueError('Controller/raw/runtime binding differs')
    samples = [(sample['scenario'], sample['repeat']) for sample in raw['samples']]
    if len(samples) != len(set(samples)) or not 1 <= len(samples) <= 16:
        raise ValueError('Distinct bounded sample set required')
    return {'controller': controller_ref, 'raw': raw_ref, 'runtime_manifest': runtime_ref,
            'runtime_revision': controller['runtime_revision'],
            'source_guard_expected_revision': controller['source_guard_expected_revision'],
            'conditions': raw['conditions'], 'probe_identity': runtime['probe'],
            'qualified': True, 'samples': [], '_raw': raw}


def evidence(archive, run, keys):
    raw = run.pop('_raw')
    for sample in raw['samples']:
        if sample['passed'] is not True:
            raise ValueError('Unsuccessful sample is not qualified scheduling evidence')
        entry = {'scenario': sample['scenario'], 'repeat': sample['repeat'], 'windows': {}}
        for scope, endpoint, field in (
                ('fixed', 'counter_end', 'probe_fixed_window'),
                ('full', 'counter_after_drain', 'probe_full_lifecycle')):
            windows, _ = archive_helpers.probes(archive, sample, field)
            per_server, stages = {}, {}
            for server in ('A', 'B', 'C'):
                before = sample['counter_start']['servers'][server]['metrics']
                after = sample[endpoint]['servers'][server]['metrics']
                per_server[server] = {key: counter_delta(before, after, key) for key in keys}
                record = sample[field][server]['data']
                stages[server] = {}
                for name, (owner, method, note) in STAGES.items():
                    value = record['spans'].get(name)
                    transformed = record['transformed_classes'].get(owner, {})
                    methods = transformed.get('methods', '')
                    if value is None or method + '(' not in methods:
                        stages[server][name] = {'status': 'UNMEASURED', 'reason': 'Missing method histogram or actual transform metadata'}
                        continue
                    inclusive, exclusive = value['inclusive'], value['exclusive']
                    if inclusive['count'] != exclusive['count']:
                        raise ValueError('Inclusive/exclusive invocation counts disagree')
                    stages[server][name] = {
                        'status': 'MEASURED', 'inclusive': archive_helpers.brief(inclusive),
                        'exclusive': archive_helpers.brief(exclusive),
                        'exceptional_returns': value['exceptional_returns'],
                        'method_owner': owner, 'method': method, 'scope': note,
                        'actual_devices_per_call': {'status': 'UNMEASURED',
                            'reason': 'The archived timing hook does not record device/request-list sizes or per-call endpoint outcomes; timing/counter windows differ, so batch_devices divided by call count is not substituted.'},
                    }
            total = {key: aggregate({server: per_server[server][key] for server in per_server}) for key in keys}
            entry['windows'][scope] = {
                'reason_counters_per_server': per_server, 'reason_counters_aggregate': total,
                'stage_spans_per_server': stages, 'probe_windows': windows,
                'counter_brackets': {'start': {key: sample['counter_start'][key] for key in ('start', 'end')},
                                     'end': {key: sample[endpoint][key] for key in ('start', 'end')}},
                'scope': 'Counters are sequential before/after snapshots; probe prefix/stop is nearby but not identical to those brackets. They are not a shared exact time interval for deriving devices/call or per-reason costs.',
            }
        run['samples'].append(entry)
    return run


def rows(runs):
    result = []
    for run in runs:
        for sample in run['samples']:
            common = {'controller': run['controller']['path'], 'runtime_revision': run['runtime_revision'],
                      'scenario': sample['scenario'], 'repeat': sample['repeat']}
            for scope, window in sample['windows'].items():
                for server, counters in window['reason_counters_per_server'].items():
                    for key, counter in counters.items():
                        result.append(dict(common, scope=scope, server=server, row_kind='reason_counter', metric=key,
                                           **{field: counter.get(field) for field in ('status', 'before', 'after', 'delta')}, detail=counter.get('reason')))
                for key, counter in window['reason_counters_aggregate'].items():
                    result.append(dict(common, scope=scope, server='ABC', row_kind='reason_counter_aggregate', metric=key,
                                       **{field: counter.get(field) for field in ('status', 'delta', 'known_delta_sum')}, detail=counter['scope']))
                for server, stages in window['stage_spans_per_server'].items():
                    for key, value in stages.items():
                        measured = value['status'] == 'MEASURED'
                        result.append(dict(common, scope=scope, server=server, row_kind='method_wall_span', metric=key,
                            status=value['status'], count=value['inclusive']['count'] if measured else None,
                            inclusive_sum_ns=value['inclusive']['sum_ns'] if measured else None,
                            exclusive_sum_ns=value['exclusive']['sum_ns'] if measured else None,
                            exceptional_returns=value['exceptional_returns'] if measured else None,
                            detail=value.get('scope', value.get('reason'))))
    return result


class OfflineTests(unittest.TestCase):
    def test_missing_is_never_zero(self):
        self.assertEqual(counter_delta({}, {}, 'schedule_input_signals')['status'], 'UNMEASURED')
        self.assertIsNone(counter_delta({}, {'key': 3}, 'key')['delta'])

    def test_real_zero_and_increase(self):
        self.assertEqual(counter_delta({'key': 0}, {'key': 0}, 'key')['delta'], 0)
        self.assertEqual(counter_delta({'key': 3}, {'key': 7}, 'key')['delta'], 4)

    def test_reset_is_rejected(self):
        with self.assertRaises(ValueError):
            counter_delta({'key': 7}, {'key': 3}, 'key')

    def test_partial_sum_is_not_total(self):
        known = counter_delta({'key': 3}, {'key': 7}, 'key')
        missing = counter_delta({}, {}, 'key')
        result = aggregate({'A': known, 'B': missing, 'C': missing})
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(result['known_delta_sum'], 4)
        self.assertIsNone(result['delta'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller', action='append', default=[])
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        if args.controller:
            parser.error('Self-tests use synthetic data only')
        outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OfflineTests))
        print(json.dumps({'offline_self_test_passed': outcome.wasSuccessful(), 'native_SQL_RCON_JDK': 'NOT RUN'}))
        return 0 if outcome.wasSuccessful() else 1
    if not 1 <= len(args.controller) <= 8 or len(set(args.controller)) != len(args.controller):
        parser.error('One to eight distinct CLOSED controllers required')
    archive = archive_helpers.Archive()
    runs = [load_run(archive, filename) for filename in args.controller]
    keys = set(COUNTERS)
    for run in runs:
        for sample in run['_raw']['samples']:
            for point in ('counter_start', 'counter_end', 'counter_after_drain'):
                for record in sample[point]['servers'].values():
                    keys.update(key for key in record['metrics'] if re.fullmatch(r'schedule_.+_(signals|captured|effective)', key))
    result = {'kind': 'offline_RC_FE_scheduling_evidence', 'utc': datetime.now(timezone.utc).isoformat(),
              'recipe': {'path': str(Path(__file__).resolve().relative_to(ROOT)), 'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              'offline_helper': {'path': str(HELPER.relative_to(ROOT)), 'sha256': hashlib.sha256(HELPER.read_bytes()).hexdigest()},
              'runs': [evidence(archive, run, sorted(keys)) for run in runs],
              'sources': list(archive.files.values()),
              'limitations': [
                  'Reason labels overlap on an endpoint request. Effective includes dirty checkpoints and any committed/received result, not asset-business-only work.',
                  'Signals, captured reasons and effective reasons are different events. No ratio is interpreted as business share, global fairness, wasted work, or per-reason SQL/WAL time.',
                  'Absent reason fields, especially all f3 fields, remain UNMEASURED. Missing/partial JVM counter sums are never presented as a measured total.',
                  'Histograms are method call wall times across the selected threads, not CPU usage or an E2E critical path. Nested phases overlap; their sums must not be added as total runtime cost.',
                  'No per-call device/request size hook exists in this FE archive; those values stay UNMEASURED. One endpoint argument is not proof that an invocation completed useful work.',
                  'wal_write includes identical-snapshot returns; SQL_transaction counts Java helper calls, not physical transactions. Notification_fanout names wakeChannel only.',
                  'Probe and counter boundaries differ slightly. Fixed precedes drain; full includes actual drain/quiet. Every layout/JVM and both scopes are preserved.',
                  'n1 layouts and instrumented-root quantiles do not prove general production tails, uninstrumented work or performance acceptance.',
              ], 'performance_acceptance_assessed': False}
    payload = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if len(payload.encode()) > archive_helpers.MAX_FILE_BYTES:
        raise ValueError('Bounded scheduling summary exceeded')
    target = ROOT / 'reports/rc-20261017' / ('fe-scheduling-summary-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:12])
    with target.with_suffix('.json').open('x') as stream:
        stream.write(payload)
    with target.with_suffix('.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows(result['runs']))
    print(json.dumps({'report': str(target.with_suffix('.json').relative_to(ROOT)),
                      'csv': str(target.with_suffix('.csv').relative_to(ROOT)), 'native_SQL_RCON_JDK': 'NOT RUN'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
