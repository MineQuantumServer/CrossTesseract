#!/usr/bin/env python3
"""Recompute original87 /68 physical-container evidence from archived files only.

Uses repository-relative report/helper locations and the exact completed child
paths/SHA256 recorded in the two sequence reports. Selected immutable launch
assets are rehashed as files; saved absolute asset paths are relocated using
the archived repository source prefix. No RCON, SQL, JVM/process observation,
profile parsing or native load runs. Explicit execution overwrites only the
three derived reports/optimization-container-comparison-68f32db files.
"""
import csv
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def completed_child(relative, label):
    sequence_path = ROOT / relative
    encoded = sequence_path.read_bytes()
    sequence = json.loads(encoded)
    matches = []
    for run in sequence.get('runs', []):
        command = run.get('command', [])
        if command.count('--label') == 1:
            index = command.index('--label')
            if index + 1 < len(command) and command[index + 1] == label:
                matches.append(run)
    if len(matches) != 1:
        raise ValueError('Requires exactly one archived completed container child: ' + label)
    run = matches[0]
    relative_report = Path(run.get('report', ''))
    if relative_report.is_absolute() or not relative_report.parts or relative_report.parts[0] != 'reports':
        raise ValueError('Sequence report must be repository-relative under reports')
    path = (ROOT / relative_report).resolve()
    if not path.is_relative_to((ROOT / 'reports').resolve()) or path.suffix != '.json':
        raise ValueError('Sequence report escapes archived reports')
    data = path.read_bytes()
    saved = json.loads(data)
    digest = hashlib.sha256(data).hexdigest()
    if digest != run.get('report_sha256'):
        raise ValueError('Sequence child SHA256 differs from its archived file')
    if run.get('exit_code') != 0 or not run.get('utc_end') or not saved.get('passed') or saved.get('failures'):
        raise ValueError('Container child is not a completed functional pass')
    return path, saved, {'sequence_repo_relative_path': relative,
        'sequence_sha256_at_derivation': hashlib.sha256(encoded).hexdigest(),
        'sequence_snapshot_verbatim': sequence, 'completed_container_child_verbatim': run,
        'actual_child_sha256': digest,
        'scope': 'Completed container child only. Sequence snapshot may contain pending later stages; no claim of completed pressure/primary suite.'}


def archived_asset(saved_path, saved_source):
    source_path = Path(saved_source['path'])
    suffix = Path('src/main/java/dev/crosstesseract/test/ThreeServerHarness.java').parts
    if not source_path.is_absolute() or source_path.parts[-len(suffix):] != suffix:
        raise ValueError('Unexpected archived repository source path')
    archived_root = source_path
    for _ in suffix:
        archived_root = archived_root.parent
    relative = Path(saved_path).relative_to(archived_root)
    actual = (ROOT / relative).resolve(strict=True)
    if not actual.is_relative_to(ROOT.resolve()):
        raise ValueError('Selected immutable archive asset escapes repository')
    return actual


def main():
    container_path = ROOT / 'scripts/optimization-container-benchmark.py'
    compare_path = ROOT / 'scripts/optimization-compare.py'
    c = module('offline_container_helpers', container_path)
    m = module('offline_counter_helpers', compare_path)
    sequence_specs = {
        'original87': ('reports/optimization-final-sequence-original.json', 'container-original2-87bf217'),
        'current68': ('reports/optimization-final-sequence-current-68f32db.json', 'container-current-68f32db-68f32db'),
    }
    inputs = {name: completed_child(relative, label) for name, (relative, label) in sequence_specs.items()}
    paths = {name: point[0] for name, point in inputs.items()}
    raw = {name: point[1] for name, point in inputs.items()}
    initial_path = ROOT / 'reports/optimization-container-container-original-87bf217-20261006T140734Z-bfcb60.json'
    initial = json.loads(initial_path.read_text())
    out = ROOT / 'reports/optimization-container-comparison-68f32db'


    def source(path):
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size_bytes': path.stat().st_size}


    def interval(a, b):
        return {'lower_ms': max(0.0, (b['start'] - a['end']) * 1000),
            'upper_ms': max(0.0, (b['end'] - a['start']) * 1000),
            'earlier_span_ms': (a['end'] - a['start']) * 1000, 'later_span_ms': (b['end'] - b['start']) * 1000}


    def proof(p, index):
        snapshots = p['snapshots']
        zero = lambda s: s['residue']['sql_pool_items'] == s['residue']['sql_allocation_remaining_items'] == 0 and all(
            d['registered'] and not d['pause'] and all(d.get(k, -1) == 0 for k in
                ('txItem', 'rxItem', 'txFE', 'rxFE', 'txFluid', 'rxFluid')) for d in s['residue']['local_buffers'].values())
        return {'raw_proof_index': index, 'lane': p['lane'], 'purpose': p['purpose'], 'passed': p['passed'],
            'start': p['started'], 'end': p.get('end'), 'quiet_seconds': p.get('quiet_seconds'),
            'snapshot_count': len(snapshots), 'all_independent_resource_checks_zero': bool(snapshots) and all(zero(s) for s in snapshots),
            'expected_physical_destination_items': p['physical_destination_stone'],
            'all_physical_counts_match': all(s['frame']['source']['count'] == 0 and
                s['frame']['target_total'] == p['physical_destination_stone'] for s in snapshots)}


    def probe(r, scenario, p):
        injection = p['item_replace_interval']
        source_event = p['source_first_decrease_interval']
        first = p['destination_first_increase_interval']
        full = p['destination_full_32_interval']
        frames = p['frames']
        by_server = {server: sum(n for name, n in p['destination_totals'].items() if r['chests'][name]['server'] == server)
            for server in sorted({r['chests'][name]['server'] for name in p['destination_totals']})}
        result = {'scenario': scenario, 'probe_number': p['index'] + 1, 'passed': p['passed'],
            'item_replace_interval': injection, 'source_decrease_interval': source_event,
            'destination_first_interval': first, 'destination_full32_interval': full,
            'input_command': r['RCON_trace'][p['item_replace_trace_index']],
            'input_to_source': interval(injection, source_event), 'source_to_first': interval(source_event, first),
            'source_to_full': interval(source_event, full), 'input_to_first': interval(injection, first),
            'input_to_full': interval(injection, full), 'actual_destination_items': p['destination_totals'],
            'actual_destination_items_by_server': by_server, 'frame_count': len(frames),
            'first_source_read_count': frames[0]['source']['count'], 'last_source_read_count': frames[-1]['source']['count'],
            'last_destination_total': frames[-1]['target_total'], 'drain_proof_indices': p['drain_proof_refs'],
            'post_empty_proof_to_input_seconds': injection['start'] - p['before_input_empty_proof']['end'],
            'first_and_full_same_observation_interval': first == full,
            'event_frame_indices': {
                'source_decrease': next(i for i, f in enumerate(frames) if f['source']['count'] < 32),
                'destination_first': next(i for i, f in enumerate(frames) if f['target_total'] > 0),
                'destination_full': next(i for i, f in enumerate(frames) if f['target_total'] == 32)}}
        result['recorded_E2E_matches_derivation'] = all(abs(result[key][bound] - p[stored][bound]) < 1e-6
            for key, stored in [('source_to_first', 'first_output_E2E'), ('source_to_full', 'full_32_E2E')]
            for bound in ('lower_ms', 'upper_ms'))
        return result


    cohorts = {}
    for name, r in raw.items():
        manifests = {}
        for server, identity in r['identity'].items():
            rechecks = []
            for saved in identity['launch_mod_artifact_manifests']:
                # This reads small immutable archived files only, never the live JVM.
                asset = archived_asset(saved['path'], r['source_evidence'])
                actual = c.jar_manifest(asset) if 'jar_sha256' in saved else c.class_manifest(asset)
                rechecks.append({'path': saved['path'], 'offline_repo_relative_path': asset.relative_to(ROOT).as_posix(),
                    'offline_actual_path': str(asset), 'source_type': saved['source_type'],
                    'recorded_manifest_sha256': saved['manifest_sha256'], 'offline_manifest_sha256': actual['manifest_sha256'],
                    'manifest_format': saved['manifest_format'], 'file_count': len(saved['files']), 'total_bytes': saved['total_bytes'],
                    'recorded_matches_offline_rehash': saved['manifest_sha256'] == actual['manifest_sha256'] and
                        saved.get('jar_sha256') == actual.get('jar_sha256'),
                    'recorded_jar_sha256': saved.get('jar_sha256'), 'offline_jar_sha256': actual.get('jar_sha256')})
            manifests[server] = rechecks
        proofs = [proof(p, i) for i, p in enumerate(r['drain_proofs'])]
        samples = []
        for s in r['samples']:
            captured = m.snapshot_counters(s)
            captured['scope_notes']['counter_window'] = (
                'Physical container layout counter_end follows both probes and all per-probe drain/clear guards. '
                'Scanner waits and guards are included; final empty cleanup/modeOFF/identity validation are later. '
                'This differs from the primary FE main path whose final conservation drain is outside its cost window.')
            samples.append({'scenario': s['scenario'], 'repeat': s['repeat'], 'passed': s['passed'],
                'probes': [probe(r, s['scenario'], p) for p in s['probes']],
                'actual_items_by_sink': s['actual_chest_items_by_sink'], 'raw_counter_delta': s['counter_delta'],
                'captured_counter_window': captured, 'WAL_barrier_snapshots': m.barrier_snapshots(s),
                'counter_capture_interval': {'start': s['counter_start']['start'], 'end': s['counter_end']['end'],
                    'seconds': s['counter_end']['end'] - s['counter_start']['start']},
                'per_two_probe_layout_cost': captured['summed_cumulative_delta'],
                'counter_scope': 'After layout activation through both physical probes and their successful drain/clear guards; includes scanner waiting and ambient/control work. Final cleanup and modeOFF occur later. No fixed240-input/120s steady or transfer-only cost attribution.'})
        end_pid = {server: next(t for t in reversed(r['RCON_trace']) if t['server'] == server and t['command'] == 'ct_test pid')
            for server in r['identity']}
        audit = {
            'raw_complete_pass': r['passed'] and not r['failures'] and bool(r.get('utc_end')),
            'three_layouts_two_probes': len(samples) == 3 and {s['scenario'] for s in samples} == {'same', 'cross', 'mixed'} and
                all(len(s['probes']) == 2 and all(p['passed'] for p in s['probes']) for s in samples),
            'all_physical_outputs32_source0': all(p['last_destination_total'] == 32 and p['last_source_read_count'] == 0 for s in samples for p in s['probes']),
            'E2E_matches_recorded': all(p['recorded_E2E_matches_derivation'] for s in samples for p in s['probes']),
            'all21_guards_passed': len(proofs) == 21 and all(p['passed'] and p['quiet_seconds'] >= 2.2 and
                p['all_independent_resource_checks_zero'] and p['all_physical_counts_match'] for p in proofs),
            'all_sinks_served_cumulatively': all(n > 0 for s in samples for n in s['actual_items_by_sink'].values()),
            'runtime_and_account_SQL_errors_retries_zero': all(s['raw_counter_delta'][k] == 0 for s in samples
                for k in ('errors', 'queue_rejected', 'quarantined', 'db_deadlock_retries')) and
                all(s['raw_counter_delta']['statements']['errors'] == 0 for s in samples),
            'cumulative_counters_valid': all(not any(s['captured_counter_window']['invalid_keys_by_server'].values()) for s in samples),
            'PID_end_matches_initial': all(end_pid[server]['reply'].strip() == 'PID ' + str(info['pid']) for server, info in r['identity'].items()),
            'frozen_launch_assets_offline_rehash_stable': all(x['recorded_matches_offline_rehash'] for xs in manifests.values() for x in xs),
            'three_servers_selected_same_bytecode': len({v['launch_crosstesseract_bytecode_sha256'] for v in r['identity'].values()}) == 1,
            '192_confirmed_items_cleared_and7_empty_fixtures_removed': r['cleared_confirmed_stone'] == 192 and
                not r['fixture_retained_for_diagnosis'] and len(r['cleanup']) == 7 and
                all(x['empty_chest_removed'] and x['device_removed'] for x in r['cleanup']),
        }
        cohorts[name] = {'source': source(paths[name]), 'utc_start': r['utc_start'], 'utc_end': r['utc_end'],
            'elapsed_seconds': r['elapsed_seconds'], 'conditions': r['conditions'], 'operator_runtime_revision': r['operator_runtime_revision'],
            'checkout_git_head': r['git_head'], 'source_geometry_evidence': r['source_evidence'], 'recorded_base_helper_sha256': r['helper_sha256'],
            'identity': {server: {k: v for k, v in identity.items() if k != 'launch_mod_artifact_manifests'} for server, identity in r['identity'].items()},
            'launch_manifests_and_offline_rehash': manifests, 'end_PID_observations': end_pid,
            'end_session_and_asset_verification': {'driver_completed_verification_before_cleanup': r['passed'] and not r['failures'],
                'source': source(container_path), 'source_method': 'verify_final_identity',
                'scope': 'Driver rechecked PID, SQL world/session/epoch and launch-file hashes before cleanup; raw end PID replies persist, but distinct end SQL rows and manifest hashes were not separately stored. Offline rehash is later file evidence, not JVM CodeSource.'},
            'samples': samples, 'quiet_proofs': proofs, 'quiet_proof_snapshot_count': sum(p['snapshot_count'] for p in proofs),
            'quiet_seconds_range': [min(p['quiet_seconds'] for p in proofs), max(p['quiet_seconds'] for p in proofs)],
            'total_physical_stone_received': sum(sum(s['actual_items_by_sink'].values()) for s in samples),
            'confirmed_stone_cleared': r['cleared_confirmed_stone'], 'cleanup': r['cleanup'], 'audit': audit,
            'audit_passed': all(audit.values()), 'other_live_backend_sessions': r['other_live_backend_sessions']}

    pairs = []
    for old_s in cohorts['original87']['samples']:
        new_s = next(s for s in cohorts['current68']['samples'] if s['scenario'] == old_s['scenario'])
        for old_p, new_p in zip(old_s['probes'], new_s['probes']):
            change = {}
            for key in ('input_to_source', 'source_to_first', 'source_to_full', 'input_to_full'):
                old, new = old_p[key], new_p[key]
                change[key] = {'observed_current_upper_below_original_lower': new['upper_ms'] < old['lower_ms'],
                    'elapsed_change_ms_bounds': [new['lower_ms'] - old['upper_ms'], new['upper_ms'] - old['lower_ms']],
                    'reduction_percent_bounds': [100 * (1 - new['upper_ms'] / old['lower_ms']), 100 * (1 - new['lower_ms'] / old['upper_ms'])]
                        if old['lower_ms'] > 0 else None,
                    'scope': 'Conservative event interval arithmetic for one ordinal pair, not a confidence interval or population estimate.'}
            pairs.append({'scenario': old_s['scenario'], 'repeat': old_s['repeat'], 'probe_number': old_p['probe_number'],
                'original': old_p, 'current': new_p, 'interval_changes': change})
    summary = {'schema_version': 1, 'report_kind': 'offline_physical_container_comparison',
        'generated_utc': datetime.now(timezone.utc).isoformat(), 'offline_file_derivation_only': True,
        'generator': source(Path(__file__)),
        'sequence_child_provenance': {name: point[2] for name, point in inputs.items()}, 'read_only_helpers': [source(container_path), source(compare_path)],
        'conditions_equal': raw['original87']['conditions'] == raw['current68']['conditions'],
        'revision_boundary': {'current_physical_container_revision': raw['current68']['operator_runtime_revision'],
            'current_checkout_git_head': raw['current68']['git_head'],
            'historical753_container_remains_separate': True,
            'primary_goal_assessment': 'NOT_MEASURED_BY_THIS_CONTAINER_SUPPLEMENT',
            'operator_reported_next_stage': 'Core68 pressure began2026-10-06T17:06:30Z; new full B/C primary comparisons are separate pending evidence.',
            'note': 'All current values derive from the completed68f32db raw report, not the earlier753/4cfff0a measurements.'},
        'base_helper_hash_equal': raw['original87']['helper_sha256'] == raw['current68']['helper_sha256'],
        'cohorts': cohorts, 'paired_probes': pairs,
        'initial_failed_original': {'source': source(initial_path), 'status': 'FAILED',
            'conditions': initial['conditions'], 'failures_verbatim': initial['failures'], 'fixture_retained': initial['fixture_retained_for_diagnosis'],
            'first_successful_same_source_to_full32_ms': initial['samples'][0]['probes'][0]['full_32_E2E'],
            'second_same_frames': len(initial['samples'][0]['probes'][1]['frames']),
            'second_same_all_observed_source32_target0': all(f['source']['count'] == 32 and f['target_total'] == 0 for f in initial['samples'][0]['probes'][1]['frames']),
            'second_same_E2E': None, 'second_same_E2E_status': 'UNMEASURED_NO_SOURCE_DECREMENT', 'layouts_not_run': ['cross', 'mixed'],
            'separation': 'Not merged with the matched six probes or relabeled as a120s successful latency/asset-protocol loss.'},
        'method': {
            'physical_events': 'Vanilla chest32 ordinary stone -> SEND BE -> RECEIVE BE -> vanilla chest, actual NeighborPump I/O. No push/pull-item shortcut or trace components.',
            'pairing': 'Ordinal(scenario, repeat, probe) in separate fresh worlds, identical declared conditions. Scanner phase/coordinates/session/initial timing are not synchronized; no matched randomized trial.',
            'clock': 'Within each run use one Python monotonic observer; never subtract absolute clocks between runs/JVMs.',
            'intervals': 'Input inside confirmed item-replace request/reply; source decrease last32 request start->first decrease reply end; target previous aggregate read start->first positive/full32 aggregate reply end. First-read decrease fallback explicitly retained. Elapsed bounds=max(0,b0-a1)..max(0,b1-a0).',
            'uncertainty': 'Bounds include RCON and0.1s polling plus mixed read order, not exact mutation timestamps. Direct input-to-full bounds retain source scan wait; component uncertainties are not added as independent errors.',
            'small_n': 'Two probes per layout; p95/p99 would be the maximum and are not reported as robust tails/capacity. Six ordinal pairs are observations, not statistical confidence guarantees.',
            'counter_scope': 'Two physical probes plus guards and wall-time scanner waits; final empty cleanup/modeOFF/identity validation excluded. Wall times differ; costs are not fixed120s/240 inputs, not transferable to the frozen primary DB30% goal. Layout costs repeated in per-probe CSV rows are contextual, never summed across those rows.',
            'SQL': 'ct_dev account SQL events include attempts and retries; separate root observation account excluded. Saved reports contain no other live backend sessions.',
            'WAL': 'Original counts/bytes/barriers are UNMEASURED; current instrumented counters retained without a before/after WAL reduction claim. Barrier rings are per-JVM snapshots, not full-phase p95.',
            'assets': '192 physical stones per cohort; SQL balances/allocation remaining and local buffers independently zero in guards. Never add mirrored SQL/WAL/local copies to physical output.',
            'local_credit': 'local_credit_publications includes cross delivery and is not a same-server-source fast-hit counter. Actual topology/output ledger identifies recipients.',
            'identity': 'Saved selected FML paths/manifests, argfiles, PID/world/session/epoch and operator revision; source checkout is separate. Driver verified end hashes and this analysis rehashed saved immutable files. Neither is class-loader CodeSource proof.',
            'RCON': 'One business observer without parallel RCON sidecars. Full raw command bodies retained and chest coordinates checked; native shared reply buffer still lacks body nonce. No wrong amount/time demonstrated.',
            'scope': 'Low-flow item supplement only, separate from primary30/120 FE workload, frozen DB30%/samep95-40%/crossp95max20% goals and default10% descriptive flags. No world-save/factory capacity/dimension claim.'}}
    summary['complete_valid_paired_result'] = summary['conditions_equal'] and summary['base_helper_hash_equal'] and all(x['audit_passed'] for x in cohorts.values()) and len(pairs) == 6
    out.with_suffix('.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    flat = []
    for name, cohort in cohorts.items():
        for s in cohort['samples']:
            for p in s['probes']:
                row = {'cohort': name, 'source_report': cohort['source']['path'], 'source_sha256': cohort['source']['sha256'],
                    'scenario': s['scenario'], 'repeat': s['repeat'], 'probe': p['probe_number'], 'passed': p['passed'],
                    'actual_items_by_endpoint_json': json.dumps(p['actual_destination_items']),
                    'actual_items_by_server_json': json.dumps(p['actual_destination_items_by_server']),
                    'frame_count': p['frame_count'], 'guard_indices': json.dumps(p['drain_proof_indices']),
                    'guard_quiet_min_seconds': min(cohort['quiet_proofs'][i]['quiet_seconds'] for i in p['drain_proof_indices']),
                    'two_probe_counter_capture_seconds': s['counter_capture_interval']['seconds'],
                    'two_probe_DBtransactions': s['raw_counter_delta']['db_transactions'],
                    'two_probe_SQL_statement_events': s['raw_counter_delta']['statements']['events'],
                    'counter_scope': s['counter_scope'], 'original_missing_WAL_stays_unmeasured': name == 'original87'}
                for key in ('input_to_source', 'source_to_first', 'source_to_full', 'input_to_full'):
                    for bound in ('lower_ms', 'upper_ms'):
                        row[key + '_' + bound] = p[key][bound]
                for key in ('item_replace_interval', 'source_decrease_interval', 'destination_first_interval', 'destination_full32_interval'):
                    for bound in ('start', 'end'):
                        row[key + '_' + bound + '_seconds'] = p[key][bound]
                row.update({'two_probe_' + k: v for k, v in s['per_two_probe_layout_cost'].items()})
                flat.append(row)
    with out.with_suffix('.csv').open('w', newline='') as fh:
        writer = csv.DictWriter(fh, list(dict.fromkeys(k for row in flat for k in row)))
        writer.writeheader()
        writer.writerows(flat)


    def show(p, key, seconds=False):
        scale = 1000 if seconds else 1
        return f"{p[key]['lower_ms']/scale:.3f}–{p[key]['upper_ms']/scale:.3f}"


    table = '\n'.join(
        f"| {pair['scenario']} / {pair['probe_number']} | {show(pair['original'], 'input_to_source', True)} → {show(pair['current'], 'input_to_source', True)} | {show(pair['original'], 'source_to_first')} → {show(pair['current'], 'source_to_first')} | {show(pair['original'], 'source_to_full')} → {show(pair['current'], 'source_to_full')} | {show(pair['original'], 'input_to_full', True)} → {show(pair['current'], 'input_to_full', True)} |"
        for pair in pairs)
    cost_table = '\n'.join(
        f"| {s['scenario']} | {s['counter_capture_interval']['seconds']:.6f} / {next(x for x in cohorts['current68']['samples'] if x['scenario']==s['scenario'])['counter_capture_interval']['seconds']:.6f} | {s['raw_counter_delta']['db_transactions']} / {next(x for x in cohorts['current68']['samples'] if x['scenario']==s['scenario'])['raw_counter_delta']['db_transactions']} | {s['raw_counter_delta']['statements']['events']} / {next(x for x in cohorts['current68']['samples'] if x['scenario']==s['scenario'])['raw_counter_delta']['statements']['events']} | {s['raw_counter_delta']['transactions']} / {next(x for x in cohorts['current68']['samples'] if x['scenario']==s['scenario'])['raw_counter_delta']['transactions']} |"
        for s in cohorts['original87']['samples'])
    wal_table = '\n'.join(
        f"| {s['scenario']} | {s['per_two_probe_layout_cost']['db_statements']} | {s['per_two_probe_layout_cost']['batch_devices']} / {s['per_two_probe_layout_cost']['batch_records']} | {s['per_two_probe_layout_cost']['wal_writes']} / {s['per_two_probe_layout_cost']['wal_bytes']} |"
        for s in cohorts['current68']['samples'])
    manifest_table = '\n'.join(
        f"| {name} | {cohort['identity']['A']['launch_crosstesseract_bytecode_sha256']} | {next(x['recorded_manifest_sha256'] for x in cohort['launch_manifests_and_offline_rehash']['A'] if x['path'].endswith('/resources'))} | {cohort['audit']['frozen_launch_assets_offline_rehash_stable']} |"
        for name, cohort in cohorts.items())
    receiver_table = '\n'.join(
        f"| {name} / {s['scenario']} / {p['probe_number']} | {json.dumps(p['actual_destination_items_by_server'], sort_keys=True)} | {p['last_destination_total']} / {p['last_source_read_count']} |"
        for name, cohort in cohorts.items() for s in cohort['samples'] for p in s['probes'])
    md = f"""# Original87 /68f32db physical vanilla-chest comparison

    Both complete cohorts passed all six actual vanilla-chest probes:192 ordinary stones received per cohort,21 independent static guards, followed by confirmed output clearing and seven empty fixture removals. Conditions match exactly:two32-stone probes for same/cross/mixed,420s timeout,2.2s idle/quiet,0.1s read-only polling, endpointy64/EAST chest in the same forced chunk with64-block spacing. These are low-flow observations, separate from the30/120 primary FE workload and factory-capacity claims.

    | Source | UTC start → end | Elapsed seconds | Runtime declared / checkout |
    | --- | --- | --- | --- |
    | original87 | {cohorts['original87']['utc_start']} → {cohorts['original87']['utc_end']} | {cohorts['original87']['elapsed_seconds']:.6f} | {cohorts['original87']['operator_runtime_revision']} / {cohorts['original87']['checkout_git_head']} |
    | current68 | {cohorts['current68']['utc_start']} → {cohorts['current68']['utc_end']} | {cohorts['current68']['elapsed_seconds']:.6f} | {cohorts['current68']['operator_runtime_revision']} / {cohorts['current68']['checkout_git_head']} |

    Input is the validated item-replace request/reply interval; source is actual vanilla source chest decrease; output is actual vanilla destination chest acceptance. All bounds are single-observer durations within their own run. Source scan waiting and complete input-to-external-output time remain visible.

    | Layout / ordinal probe | Input → source decrease (s), original →68 | Source → first output (ms), original →68 | Source → full32 (ms), original →68 | Complete input → external chest32 (s), original →68 |
    | --- | --- | --- | --- | --- |
    {table}

    Current source→full upper bounds are below their paired original lower bounds for {sum(p['interval_changes']['source_to_full']['observed_current_upper_below_original_lower'] for p in pairs)}/6 observed pairs; current source→first has {sum(p['interval_changes']['source_to_first']['observed_current_upper_below_original_lower'] for p in pairs)}/6. Current complete input→full conservative bounds span{min(p['current']['input_to_full']['lower_ms'] for p in pairs)/1000:.6f}–{max(p['current']['input_to_full']['upper_ms'] for p in pairs)/1000:.6f}s, including source wait{min(p['current']['input_to_source']['lower_ms'] for p in pairs)/1000:.6f}–{max(p['current']['input_to_source']['upper_ms'] for p in pairs)/1000:.6f}s. Source→full spans{min(p['current']['source_to_full']['lower_ms'] for p in pairs):.6f}–{max(p['current']['source_to_full']['upper_ms'] for p in pairs):.6f}ms. First/full share observation intervals in{sum(p['first_and_full_same_observation_interval'] for x in cohorts.values() for s in x['samples'] for p in s['probes'])}/12 probes:the first positive frame was already32, without proving atomic arrival.

    Only two probes per layout are available. No p95/p99 population tail/capacity guarantee is claimed; those order statistics would simply be the observed maximum. Ordinal pairing uses separate fresh worlds without matching scanner phase, coordinates or initial schedule. Interval differences in JSON are observation arithmetic, not confidence intervals.

    | Cohort / layout / probe | Actual external items by server | Total / final source |
    | --- | --- | --- |
    {receiver_table}

    Each cohort delivered64 to its same/cross receiver and32 to each mixed receiver cumulatively. SQL pool, allocation remaining and all local item/FE/fluid buffers each independently checked zero in every guard; no mirrored SQL/WAL/local copies are summed as assets. Original passed{len(cohorts['original87']['quiet_proofs'])} guards/{cohorts['original87']['quiet_proof_snapshot_count']} snapshots, quiet{cohorts['original87']['quiet_seconds_range'][0]:.6f}–{cohorts['original87']['quiet_seconds_range'][1]:.6f}s;68 passed{len(cohorts['current68']['quiet_proofs'])} guards/{cohorts['current68']['quiet_proof_snapshot_count']} snapshots, quiet{cohorts['current68']['quiet_seconds_range'][0]:.6f}–{cohorts['current68']['quiet_seconds_range'][1]:.6f}s. Guards are sampled observations, not one atomic cross-JVM snapshot.

    Counter windows cover both physical probes, all per-probe drain/clear guards and actual scanner waiting. Final modeOFF/identity validation/empty cleanup occur later. Longer original waits include more ambient/control/heartbeat work:these costs are not transfer-only or fixed120s/240-input primary costs. Layout costs repeat in the two individual-probe CSV rows as context and must not be summed across those rows.

    | Layout | Actual counter capture seconds original /68 | DBtx original /68 | ct_dev account SQL events original /68 | Completed worker tasks original /68 |
    | --- | --- | --- | --- | --- |
    {cost_table}

    |68 layout | Instrumented Sql-helper attempts | Batch device appearances / records | WAL writes / bytes |
    | --- | --- | --- | --- |
    {wal_table}

    Original Sql-helper/batch/WAL counts, bytes and barriers remain UNMEASURED, never0. Current WAL is measured only on68; no baseline WAL reduction is inferred. Per-JVM end-ring barrier/tick metrics have unknown coverage and do not establish phase-wide native MSPT/TPS or percentiles. Account SQL events count attempts/retries, exclude observer root, and both saved reports have no other live backend sessions. Container runtime errors/rejections/quarantines/deadlock retries and account SQL errors were0 in all six layout windows. Credit-publication counters include cross-server delivery and do not establish same-server-source fast hits.

    | Cohort | Selected bytecode manifest SHA256 | Selected resource manifest SHA256 | ABC offline file rehash stable |
    | --- | --- | --- | --- |
    {manifest_table}

    All12 saved selected launch class/resource folders were rehashed offline and match their recorded manifests. Actual FML paths, argfile hashes, classes/resources, PID/server/world/session/epoch and endpoint/chest coordinates are preserved in JSON and raw reports. The driver completed final PID/SQL identity/launch-file checks before empty cleanup; raw end PID replies remain, while distinct final SQL rows/hashes were not separately persisted. Selected launch assets and stable files are evidence, without a legacy class-loader CodeSource attestation. Original checkout HEAD differs from original runtime87; current declared revision and checkout both68f32db. Both recorded base-helper hashes match.

    Original raw source:{paths['original87'].relative_to(ROOT)}, SHA256{cohorts['original87']['source']['sha256']}. Current raw source:{paths['current68'].relative_to(ROOT)}, SHA256{cohorts['current68']['source']['sha256']}. All68 values derive from this completed raw report;753 and4cfff0a results remain historical separate evidence.

    The initial original ten-probe/120s attempt remains failed:{initial_path.relative_to(ROOT)}, SHA256{source(initial_path)['sha256']}. First same probe actually completed32; second preserved{summary['initial_failed_original']['second_same_frames']} frames all source32/target0, without a source decrease. Its E2E is UNMEASURED, not120s. Assets were retained; cross/mixed never ran. The later fresh two-probe420s successes do not erase the earlier failure. Operator source investigation attributed the wait to the original2s one-side/one-slot scanner and nominal324s slot0 revisit; source wait is separate from evidence of protocol asset loss.

    One Python monotonic/RCON observer, no concurrent RCON sidecars, raw replies/coordinate checks and conservative request/read intervals are retained. Polling/read order/RCON overhead remain in bounds. Native shared reply bodies still lack business nonces; no wrong count/time is demonstrated. World-save, crash atomicity and other dimensions were not measured.

    Frozen primary goals remain30% DB reduction per identical240-input same/cross/mixed window,40% same upper-boundp95 reduction,cross upper-boundp95 regression at most20%, with default10% descriptive flags separate. This physical supplement does not assess those goals. Core68 pressure began17:06:30 UTC after this container run; subsequent full primary B/C comparisons are separate evidence.

    [Detailed paired JSON](optimization-container-comparison-68f32db.json) · [All12 probe rows](optimization-container-comparison-68f32db.csv)
    """
    md += '\n\nRecompute from archived files: `python3 scripts/analysis/compare-container-68f32db.py`. No native workload is run.\n'
    out.with_suffix('.md').write_text(md)
    print('written', *(str(out.with_suffix(s)) for s in ('.json', '.csv', '.md')))
    print('complete_valid_paired_result', summary['complete_valid_paired_result'])
    print('audits', {name: {'passed': x['audit_passed'], 'failed': [k for k, v in x['audit'].items() if not v]} for name, x in cohorts.items()})

    return 0 if summary['complete_valid_paired_result'] else 1


if __name__ == '__main__':
    sys.exit(main())
