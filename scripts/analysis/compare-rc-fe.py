#!/usr/bin/env python3
"""Offline RC gate evaluation. Reads immutable reports; never contacts Minecraft/SQL.

Both same-agent v2 comparisons and the pre-existing v1 numerical limits apply.
Output is exclusive-create, so failed or superseded runs cannot be overwritten.
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / 'reports/optimization-rc-probe-rc-fe-baseline-fast2-20261017T103942Z-d8e7ca.json'
V1_SHA = '9afa0a4af733f526a530e610ebefc73e918f91a372c39e8c9e6f5775e49b2d2e'



# Explicit reviewed runtime identities; the fixed v1 limits and f3 baseline do
# not change when a later candidate is evaluated. No inferred checkout HEAD.
REVIEWED_CANDIDATES = {
    '3647dede64cfc23e054dfa962fd127787cae14ec': '1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f',
    '0113ef30f2269f9ea51e7c15e585792828fd2a51': '70a02e49900dee34fc996bfcf95360689ea9e42c35996c581c52df2ee6fdb07c',
}

def reviewed_runtime(role, revision, jar):
    allowed = ({'f3c59b772dcbd343596174c73093b2fef536f19c': '7924ab808667c69aabbbe71c2c92f1294437a7cc8bb19e409c366af1f682553a'}
               if role == 'baseline' else REVIEWED_CANDIDATES if role == 'candidate' else {})
    if revision not in allowed or allowed[revision] != jar:
        raise ValueError('Exact reviewed source/JAR runtime pair required for ' + role)
    return revision


def source(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT / 'reports') or not path.is_file():
        raise ValueError('Only existing repository reports may be read: ' + str(path))
    return path, json.loads(path.read_text())


def identity(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def change(before, after):
    return 100 * (after / before - 1) if before else None


def brief(value):
    return {key: item for key, item in value.items() if key != 'histogram_upper_ns_count'}


def bound_reference(reference, expected_path=None):
    selected, body = source(reference['path'])
    if identity(selected)['sha256'] != reference['sha256'] or expected_path is not None and selected != expected_path:
        raise ValueError('Report reference does not identify the actual input: ' + str(selected))
    return body


def window(sample, field):
    if set(sample[field]) != {'A', 'B', 'C'}:
        raise ValueError('Exactly A/B/C full-window probes are required')
    servers = {}
    for server, record in sample[field].items():
        data = record['data']
        if bound_reference(record['source']) != data:
            raise ValueError('Embedded probe differs from its immutable raw file')
        roots = data['mod_roots']
        logical = roots['per_complete_logical_tick_cycle']
        ticks = data['ticks']
        closed = field == 'probe_full_lifecycle'
        if (data['probe_revision'] != 'v2_mod_roots' or ticks <= 1 or data['window_closed'] is not closed
                or roots['per_complete_tick']['count'] != ticks
                or data['spans']['server_tick']['inclusive']['count'] != ticks
                or logical['count'] != ticks - (0 if closed else 1)):
            raise ValueError('Incomplete v2 frame/cycle accounting')
        needed = {'dev/crosstesseract/runtime/RuntimeService', 'dev/crosstesseract/block/Ports$EnergyPort',
                  'dev/crosstesseract/block/TesseractBlockEntity', 'dev/crosstesseract/core/LocalBuffer',
                  'net/minecraft/server/MinecraftServer'}
        valid = bool(roots['valid']) and not any((data['trace_errors'], data['frame_depth_mismatches'],
            data['frame_overflow_calls'], roots['invalid_ticks'], roots['invalid_cycles'], data['transform_failures']))
        valid = valid and needed <= data['transformed_classes'].keys()
        servers[server] = {
            'raw': record['source'], 'valid': valid, 'ticks': data['ticks'],
            'actual_tps': data['actual_tps'], 'window_closed': data['window_closed'],
            'logical_cycle': brief(logical), 'frame': brief(roots['per_complete_tick']),
            'outside_main': brief(roots['outside_tick_main_thread_roots']),
            'worker': brief(roots['non_main_thread_roots']),
            'MC_tick': brief(data['spans']['server_tick']['inclusive']),
            'generator': brief(data['spans']['generator']['inclusive']),
            'method_spans': {key: brief(value['inclusive']) for key, value in data['spans'].items()},
            'coverage_limits': roots['coverage_limits'],
            'mod_p99_2ms_passed': valid and logical.get('p99_ns_upper', float('inf')) <= 2_000_000,
            'MC_p95_50ms_passed': valid and data['spans']['server_tick']['inclusive'].get('p95_ns_upper', float('inf')) <= 50_000_000,
            'TPS_19_5_passed': valid and data['actual_tps'] >= 19.5,
        }
    return servers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--baseline-controller', required=True)
    parser.add_argument('--candidate-controller', required=True)
    args = parser.parse_args()
    paths, bodies = {}, {}
    for key, value in vars(args).items():
        paths[key], bodies[key] = source(value)
    if identity(V1)['sha256'] != V1_SHA:
        raise ValueError('The frozen v1 baseline has changed')
    legacy = json.loads(V1.read_text())
    base, candidate = bodies['baseline'], bodies['candidate']
    for key in ('baseline', 'candidate'):
        controller = bodies[key + '_controller']
        if bound_reference(controller['raw_report'], paths[key]) != bodies[key]:
            raise ValueError('Controller/raw mismatch')
        if controller['runtime_manifest'] != bodies[key]['probe_manifest']:
            raise ValueError('Controller and raw have different runtime manifests')
        seal = bound_reference(controller['runtime_manifest'])
        revision = reviewed_runtime(key, seal.get('source_revision'), seal.get('artifacts', {}).get('JAR', {}).get('sha256'))
        if (controller['state'] != 'COMPLETE' or not controller.get('utc_end') or controller['workload_exit'] != 0
                or controller['phase'] != 'fe' or controller['mode'] != 'fast' or controller['variant'] != 'default'
                or controller['runtime_revision'] != revision or controller['failures']
                or not controller['all_own_launchers_exited_and_locks_free']
                or not all(controller[point]['matches_expected'] for point in ('source_before', 'source_after_workload', 'source_after_stop'))):
            raise ValueError('A complete correctly bound FE/fast/default controller is required')
        scenarios = [s['scenario'] for s in bodies[key]['samples']]
        if sorted(scenarios) != ['cross', 'mixed', 'same'] or any(s['repeat'] != 1 for s in bodies[key]['samples']):
            raise ValueError('This n1 comparison never silently drops repeated, missing or extra windows')
    if base['conditions'] != candidate['conditions']:
        raise ValueError('Measured input and observation conditions differ')
    if (base['probe_configuration']['probe_manifest_sha256'] != candidate['probe_configuration']['probe_manifest_sha256']
            or base['probe_configuration']['probe']['recorder_revision'] != 'v2_mod_roots'
            or base['probe_configuration']['probe'] != candidate['probe_configuration']['probe']):
        raise ValueError('Both runtimes must use the exact same v2 agent')
    qualified = all(bodies[key].get('qualified_passed') is True for key in ('baseline_controller', 'candidate_controller'))
    result = {
        'utc': datetime.now(timezone.utc).isoformat(), 'recipe': identity(Path(__file__).resolve()),
        'sources': {key: identity(path) for key, path in paths.items()}, 'frozen_v1': identity(V1),
        'targets': identity(ROOT / 'docs/RC_20261017_TARGETS.md'),
        'measurement_amendment': identity(ROOT / 'docs/RC_20261017_MEASUREMENT_AMENDMENT.md'),
        'source_and_runtime_qualified': qualified, 'samples': [],
        'limits': [
            'n=1 per layout; 40 low-flow observations do not establish general production p95.',
            'SQL physical transaction/helper statement counters and account statement events are distinct.',
            'Fixed cost precedes final drain; full cost includes actual drain and the quiet observation barrier.',
            'Cost counters cover the measured 240-event steady business through drain, excluding fixture setup, low-flow probes and warmup, which have separate raw records.',
            'Only instrumented mod roots are covered; GUI and uninstrumented entry points remain unverified.',
            'Logical cycles include instrumented main-thread roots between MC tick starts, including calls outside tickServer.',
            'Internal per-JVM nanoTime spans are not subtracted across JVMs. E2E uses one external observer.',
            'No all-path 30% historical target is rewritten; no new v2 baseline can relax the old v1 gates.',
        ],
    }
    rows = []
    for scenario in ('same', 'cross', 'mixed'):
        samples = {key: next(s for s in body['samples'] if s['scenario'] == scenario)
                   for key, body in (('baseline', base), ('candidate', candidate), ('v1', legacy))}
        first, last, old = (samples[key] for key in ('baseline', 'candidate', 'v1'))
        same = all(first['business'][key] == last['business'][key] == old['business'][key]
                   for key in ('input_attempts', 'accepted_input_events', 'fully_accepted_input_events', 'accepted_FE'))
        p95 = {key: s['low_flow']['full_output_upper_ms']['p95'] for key, s in samples.items()}
        gate = min(max(p95['baseline'] * 1.2, p95['baseline'] + 100), max(p95['v1'] * 1.2, p95['v1'] + 100), 800 if scenario == 'same' else 1000)
        entry = {
            'scenario': scenario, 'same_actual_inputs': same,
            'functional_passed': {key: s['passed'] for key, s in samples.items()},
            'latency': {'p95_upper_ms': p95, 'stricter_frozen_limit_ms': gate, 'passed': p95['candidate'] <= gate},
            'low_flow_bounds': {key: s['low_flow'] for key, s in samples.items()}, 'costs': {}, 'windows': {},
            'service': {key: s['sinks'] for key, s in samples.items()},
            'business': {key: s['business'] for key, s in samples.items()},
        }
        for scope, field, probe, end in (('fixed', 'counter_delta', 'probe_fixed_window', 'counter_end'),
                                         ('full', 'lifecycle_counter_delta', 'probe_full_lifecycle', 'counter_after_drain')):
            a, z, v = (samples[key][field] for key in ('baseline', 'candidate', 'v1'))
            # Sequential A/B/C counter reads have brackets, not one atomic time.
            # The outer duration gives a rate lower bound; use the upper rate for admission.
            shortest = last[end]['start'] - last['counter_start']['end']
            longest = last[end]['end'] - last['counter_start']['start']
            if not 0 < shortest <= longest:
                raise ValueError('Nonpositive or inverted counter observation interval')
            costs = {}
            for metric in ('db_transactions', 'db_statements', 'transactions', 'batch_devices', 'batch_records',
                           'wal_writes', 'wal_bytes', 'db_deadlock_retries', 'errors', 'queue_rejected', 'quarantined'):
                costs[metric] = {'baseline': a.get(metric), 'candidate': z.get(metric), 'v1': v.get(metric),
                                 'change_percent_v2': change(a[metric], z[metric]) if a.get(metric) is not None and z.get(metric) is not None else None}
                if metric in ('db_transactions', 'db_statements'):
                    threshold = .8 * min(a[metric], v[metric])
                    costs[metric].update({'stricter_20percent_limit': threshold, 'passed': same and z[metric] <= threshold})
            costs['account_statement_events'] = {key: samples[key][field].get('statements') for key in samples}
            costs['transactions_per_second_bounds'] = {'lower': z['db_transactions'] / longest, 'upper': z['db_transactions'] / shortest}
            costs['transactions_40_per_second_passed'] = costs['transactions_per_second_bounds']['upper'] <= 40
            costs['observation_seconds_bounds'] = {'lower': shortest, 'upper': longest}
            costs['no_errors_rejections_quarantine'] = all(z[metric] == 0 for metric in ('errors', 'queue_rejected', 'quarantined'))
            costs['per_accepted_input_event'] = {key: z[key] / last['business']['accepted_input_events'] for key in ('db_transactions', 'db_statements', 'wal_writes')}
            entry['costs'][scope] = costs
            entry['windows'][scope] = {key: window(samples[key], probe) for key in ('baseline', 'candidate')}
            row = {'scenario': scenario, 'scope': scope, 'qualified': qualified, 'same_actual_inputs': same,
                   'baseline_p95_ms': p95['baseline'], 'candidate_p95_ms': p95['candidate'], 'latency_limit_ms': gate,
                   'latency_passed': entry['latency']['passed'], 'candidate_tx_per_second_upper': costs['transactions_per_second_bounds']['upper']}
            for metric in ('db_transactions', 'db_statements', 'wal_writes', 'wal_bytes'):
                for key, val in costs[metric].items():
                    row[metric + '_' + key] = val
            rows.append(row)
        proof = last['conservation']
        entry['conservation_and_quiet_passed'] = (proof['accepted_FE'] == proof['extracted_FE']
            and proof['quiet_barrier']['passed'] is True
            and proof['residue']['sql_pool_FE'] == proof['residue']['sql_allocation_remaining_FE'] == 0
            and all(all(value[field] == 0 for field in ('txFE', 'rxFE', 'txItem', 'rxItem', 'txFluid', 'rxFluid'))
                    for value in proof['residue']['local_buffers'].values()))
        result['samples'].append(entry)
    result['all_small_FE_gates_passed'] = qualified and all(
        sample['same_actual_inputs'] and all(sample['functional_passed'].values()) and sample['latency']['passed'] and sample['conservation_and_quiet_passed']
        and all(cost['db_transactions']['passed'] and cost['db_statements']['passed'] and cost['transactions_40_per_second_passed'] and cost['no_errors_rejections_quarantine']
                for cost in sample['costs'].values())
        and all(server['mod_p99_2ms_passed'] and server['MC_p95_50ms_passed'] and server['TPS_19_5_passed']
                for modes in sample['windows'].values() for server in modes['candidate'].values())
        for sample in result['samples'])
    prefix = ROOT / 'reports/rc-20261017' / ('fe-final-gates-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
    with prefix.with_suffix('.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    with prefix.with_suffix('.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({'report': str(prefix.with_suffix('.json').relative_to(ROOT)),
                      'csv': str(prefix.with_suffix('.csv').relative_to(ROOT)),
                      'all_small_FE_gates_passed': result['all_small_FE_gates_passed']}))
    return 0 if result['all_small_FE_gates_passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
