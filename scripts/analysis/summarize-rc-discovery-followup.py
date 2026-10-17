#!/usr/bin/env python3
"""Offline closed FE/soak comparison; never reads events.jsonl or uses a backend."""
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
OLD = 'reports/rc-20261017/rc-fe-v2-final-controller-20261017T121031Z-b0a6bf0a.json'
NEW = 'reports/rc-20261017/rc-fe-v2-0113ef3-controller-20261017T155659Z-3cd56483.json'
OLD_SOAK = 'reports/rc-20261017/soak-final-3647-v2-full3-20261017.json'
NEW_SOAK = 'reports/rc-20261017/soak-final-0113ef3-v2-20261017T155637Z-543147e1.json'
METRICS = ('db_transactions', 'db_statements', 'transactions', 'batch_devices', 'batch_records',
           'wal_writes', 'wal_bytes', 'errors', 'db_deadlock_retries', 'queue_rejected', 'quarantined')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def meta(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}


def read(value):
    path = Path(value); path = path if path.is_absolute() else ROOT / path
    if path.is_symlink(): raise ValueError('Regular closed evidence required')
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT): raise ValueError('Repository evidence only')
    return path, json.loads(path.read_text())


def reference(ref):
    path, data = read(ref['path'])
    if sha(path) != ref['sha256']: raise ValueError('Closed evidence SHA mismatch')
    return path, data


def run(value, revision, jar):
    path, controller = read(value)
    if (controller.get('runtime_revision') != revision or controller.get('state') != 'COMPLETE'
            or controller.get('workload_exit') != 0 or not controller.get('utc_end')
            or any(controller.get(key) is not True for key in ('passed', 'qualified_passed',
               'functional_passed', 'all_own_launchers_exited_and_locks_free'))
            or any(row['exit_code'] != 0 for row in controller['own_launcher_exits'].values())):
        raise ValueError('Closed qualified exact-version FE run required')
    rp, raw = reference(controller['raw_report']); mp, seal = reference(controller['runtime_manifest'])
    if (seal['source_revision'] != revision or seal['artifacts']['JAR']['sha256'] != jar
            or raw['probe_manifest'] != controller['runtime_manifest']
            or raw['operator_runtime_revision'] != revision or raw['passed'] is not True
            or sorted((s['scenario'], s['repeat']) for s in raw['samples']) != [('cross', 1), ('mixed', 1), ('same', 1)]):
        raise ValueError('Runtime/raw identity or sample-set mismatch')
    return {'controller': meta(path), 'raw': meta(rp), 'manifest': meta(mp)}, raw


def hist(value):
    return {key: value.get(key) for key in ('count', 'sum_ns', 'max_ns', 'p50_ns_upper', 'p95_ns_upper', 'p99_ns_upper')}


def totals(business):
    result = {}
    for lane in business.values():
        for resource, record in lane.items():
            value = result.setdefault(resource, {'unit': record['unit'], 'accepted': 0, 'external_output': 0})
            value['accepted'] += record['accepted']; value['external_output'] += record['external_output']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scheduling-summary', required=True)
    parser.add_argument('--supersedes-derivation')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('rc_offline_fe_windows', ROOT / 'scripts/analysis/compare-rc-fe.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    refs, raw = {}, {}
    refs['3647'], raw['3647'] = run(OLD, '3647dede64cfc23e054dfa962fd127787cae14ec', '1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f')
    refs['0113'], raw['0113'] = run(NEW, '0113ef30f2269f9ea51e7c15e585792828fd2a51', '70a02e49900dee34fc996bfcf95360689ea9e42c35996c581c52df2ee6fdb07c')
    if raw['3647']['conditions'] != raw['0113']['conditions']: raise ValueError('Different FE conditions')
    if raw['3647']['probe_configuration']['probe'] != raw['0113']['probe_configuration']['probe']: raise ValueError('Different v2 agents')
    schp, scheduling = read(args.scheduling_summary)
    rows, samples = [], []
    for layout in ('same', 'cross', 'mixed'):
        selected = {key: next(s for s in body['samples'] if s['scenario'] == layout) for key, body in raw.items()}
        keys = ('input_attempts', 'accepted_input_events', 'fully_accepted_input_events', 'accepted_FE')
        same_inputs = all(selected['3647']['business'][key] == selected['0113']['business'][key] for key in keys)
        same_full_outputs = same_inputs and all(s['conservation']['accepted_FE'] == s['conservation']['extracted_FE'] for s in selected.values())
        entry = {'scenario': layout, 'same_actual_inputs': same_inputs, 'same_full_conserved_output': same_full_outputs,
                 'business': {key: s['business'] for key, s in selected.items()},
                 'asset_conservation_including_probes_warmup': {key: {name: s['conservation'][name] for name in ('accepted_FE', 'extracted_FE')} for key, s in selected.items()}, 'windows': {}}
        for scope, counter, probe in (('fixed', 'counter_delta', 'probe_fixed_window'), ('full', 'lifecycle_counter_delta', 'probe_full_lifecycle')):
            cost = {}
            for metric in METRICS:
                before, after = (selected[key][counter].get(metric) for key in ('3647', '0113'))
                cost[metric] = {'3647': before, '0113': after, 'change_percent': (after / before - 1) * 100 if before and after is not None and same_inputs and same_full_outputs else None}
                rows.append({'scenario': layout, 'scope': scope, 'row_kind': 'cost', 'server': 'ABC', 'metric': metric,
                             'old': before, 'new': after, 'change_percent': cost[metric]['change_percent']})
            windows = {key: helper.window(sample, probe) for key, sample in selected.items()}
            entry['windows'][scope] = {'costs': cost, 'account_statement_events': {key: s[counter].get('statements') for key, s in selected.items()},
                'JVM': {key: {server: {'valid': value['valid'], 'ticks': value['ticks'], 'actual_tps': value['actual_tps'],
                         'logical_main_mod_roots': value['logical_cycle'], 'whole_MC_tick': value['MC_tick']} for server, value in data.items()} for key, data in windows.items()}}
            for server in 'ABC':
                for name, field in (('logical_main_mod_roots', 'logical_cycle'), ('whole_MC_tick', 'MC_tick')):
                    for quantile in ('p50_ns_upper', 'p95_ns_upper', 'p99_ns_upper'):
                        before, after = (windows[key][server][field][quantile] / 1e6 for key in ('3647', '0113'))
                        rows.append({'scenario': layout, 'scope': scope, 'row_kind': 'wall_histogram_ms', 'server': server,
                                     'metric': name + '_' + quantile, 'old': before, 'new': after,
                                     'change_percent': (after / before - 1) * 100 if before else None})
        samples.append(entry)
    osp, oldsoak = read(OLD_SOAK); nsp, newsoak = read(NEW_SOAK)
    actual_vectors = {'3647': totals(oldsoak['observation_and_tail_business_delta']), '0113': totals(newsoak['observation_and_tail_business_delta'])}
    controller_path, newcontroller = reference(newsoak['controller'])
    _, newraw = reference(newcontroller['raw_report'])  # JSON only; never the journal.
    observation = newraw['observation']
    report = {'generated_utc': datetime.now(timezone.utc).isoformat(), 'recipe': meta(Path(__file__).resolve()),
        'offline_only': True, 'events_JSONL_read': False, 'FE_sources': refs, 'FE': samples,
        'FE_reason_method_summary': meta(schp),
        'soak': {'sources': {'3647': meta(osp), '0113': meta(nsp)}, 'actual_accepted_and_output_vectors': actual_vectors,
            'identical_actual_hour_business': actual_vectors['3647'] == actual_vectors['0113'],
            'new_actual_observation_seconds': observation['end'] - observation['start'],
            'new_elapsed_seconds': newraw.get('elapsed_seconds'), 'new_endpoints': newsoak['endpoint_count'], 'new_channels': newsoak['channel_count'],
            'new_ITEM_pairs': len(newsoak['ITEM_batches']), 'new_ITEM_payloads': newsoak['ITEM_payloads'],
            'new_ITEM_descriptive_bounds_ms': newsoak['ITEM_descriptive_bounds_ms_by_variant'], 'new_coverage': newsoak['coverage_checks'],
            'costs_parallel_only': {key: {'fixed': body['fixed_counter_delta']['sum'], 'full': body['lifecycle_counter_delta']['sum']} for key, body in (('3647', oldsoak), ('0113', newsoak))},
            'new_full_window_probe': newsoak['complete_window_probe']['probe_full_lifecycle'],
            'new_process_and_queues': newsoak['process_and_queues'], 'new_recipient_service': newsoak['observation_and_tail_business_delta'],
            'new_service_gaps': newsoak['service_observations'], 'new_history': newsoak['post_stop_history']},
        'scope': ['Frozen gates are unchanged and are NOT reassessed or overridden by this descriptive report.',
            'FE each layout n1, actual240 accepted inputs/7.68MFE; fixed output can differ, and fixed counters precede final drain. Full includes recorded drain/quiet.',
            'Sample conservation totals also include already-drained low-flow probes and warmup; they are not the steady-only7.68M counter input. Equality of those asset ledgers is checked without assigning them as counter-window input.',
            'Whole-MC and selected mod-root histograms are complete-window wall spans, not CPU timers, rolling averages, or uninstrumented GUI cost.',
            'Hour actual accepted vectors differ. Old/new hour costs are parallel values, never a same-business unit-cost improvement.',
            'Hour uses30 pairs, each32 A+32 B, only2 stable payload identities. Inherited base fixed_item_pair_per_observation_window describes pair composition, not total hour count; actual120s schedule/batches govern.',
            'Reason labels overlap and effective includes checkpoints. Actual devices/call and asset-bearing per-reason share remain UNMEASURED.',
            'One Python observer, conservative external bounds; no cross-JVM raw nanoTime subtraction or world-save latency claim.',
            '20EP/6channels is not1000 capacity or peak factory throughput. RSS/GC observations do not prove no leak or pause percentiles.',
            'Shared SQL history was not reset; runs are sequential and n1 comparisons are descriptive, not statistical significance.']}
    if args.supersedes_derivation:
        previous, _ = read(args.supersedes_derivation)
        report['supersedes_derivation'] = {'source': meta(previous), 'reason': 'The earlier descriptive report overstrictly required cumulative probe/warmup/steady conservation to equal steady-only7.68M, producing false flags and null changes. All underlying raw counters remain unchanged.'}
    prefix = ROOT / 'reports/rc-20261017' / ('discovery-offline-summary-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    with prefix.with_suffix('.json').open('x') as out: json.dump(report, out, indent=2); out.write('\n')
    with prefix.with_suffix('.csv').open('x', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    lines = ['Closed0113 follow-up descriptive evidence', '', 'FE old3647 → new0113, fixed/full actual same accepted inputs; frozen acceptance gates unchanged.', '', '|layout|scope|tx old→new|SQL statements old→new|WAL writes old→new|', '|---|---|---:|---:|---:|']
    for sample in samples:
        for scope, window in sample['windows'].items():
            pairs = [str(window['costs'][key]['3647']) + '→' + str(window['costs'][key]['0113']) for key in ('db_transactions', 'db_statements', 'wal_writes')]
            lines.append('|' + '|'.join((sample['scenario'], scope, *pairs)) + '|')
    lines += ['', 'New hour: ' + str(report['soak']['new_actual_observation_seconds']) + 's actual input;20EP/6channels;30 pairs; all coverage gates true.', '',
              'Actual accepted load differs from old hour; costs remain parallel, without normalized improvement claims.', '', *['- ' + note for note in report['scope']], '', 'Scheduling JSON: `' + str(schp.relative_to(ROOT)) + '`', '']
    with prefix.with_suffix('.md').open('x') as out: out.write('\n'.join(lines))
    print(json.dumps({'outputs': [meta(prefix.with_suffix(ext)) for ext in ('.json', '.csv', '.md')], 'native_SQL_RCON_JDK': 'NOT RUN'}))


if __name__ == '__main__': raise SystemExit(main())
