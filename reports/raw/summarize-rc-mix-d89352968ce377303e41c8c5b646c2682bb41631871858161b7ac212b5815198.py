#!/usr/bin/env python3
"""Summarize CLOSED RC mixed-resource archives without contacting any server.

Use repeated --controller arguments. All input references are checked against
repository reports and their SHA-256. Output JSON/CSV names are unique and are
created exclusively. --self-test uses synthetic data only. This is an offline
descriptive summary, not a performance or production-safety acceptance gate.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import unittest
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_CONTROLLERS = 8
MAX_EVENTS = 49152
ITEM = 'cross_tesseract:item'
HEX64 = re.compile(r'[0-9a-f]{64}')
CSV_FIELDS = ('controller', 'runtime_revision', 'mode', 'scenario', 'repeat',
              'batch_sequence', 'variant', 'row_kind', 'scope', 'server',
              'endpoint', 'operation', 'metric', 'status', 'value', 'lower_ms',
              'upper_ms', 'unit', 'detail')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(raw):
    def invalid(value):
        raise ValueError('Nonfinite JSON number: ' + value)
    return json.loads(raw, object_pairs_hook=unique_keys, parse_constant=invalid)


def uuid(value):
    result = str(UUID(value))
    if result != value:
        raise ValueError('Canonical UUID required')
    return result


class Archive:
    def __init__(self, root=ROOT):
        self.root = root.resolve()
        self.files = {}
        self.bodies = {}

    def read(self, value, expected_sha=None):
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root / 'reports') or not path.is_file():
            raise ValueError('Only existing repository reports may be read: ' + str(path))
        key = str(path.relative_to(self.root))
        if key not in self.files:
            if len(self.files) >= 512 or not 0 < path.stat().st_size <= MAX_FILE_BYTES:
                raise ValueError('Archive input count/size limit')
            raw = path.read_bytes()
            if len(raw) > MAX_FILE_BYTES:
                raise ValueError('Archive grew beyond limit')
            self.files[key] = {'path': key, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            self.bodies[key] = decode(raw)
        if expected_sha is not None and (not HEX64.fullmatch(expected_sha)
                or self.files[key]['sha256'] != expected_sha):
            raise ValueError('Archive SHA mismatch: ' + key)
        return self.files[key], self.bodies[key]

    def reference(self, reference):
        return self.read(reference['path'], reference['sha256'])


def completed(controller):
    if (controller.get('state') != 'COMPLETE' or not controller.get('utc_end')
            or controller.get('phase') != 'mix' or controller.get('mode') not in ('batch', 'fast')
            or controller.get('variant') != 'default' or controller.get('workload_exit') != 0
            or any(controller.get(key) is not True for key in
                   ('passed', 'functional_passed', 'qualified_passed', 'raw_passed',
                    'all_own_launchers_exited_and_locks_free'))
            or controller.get('failures')):
        raise ValueError('A completed, qualified, successful mix controller is required')
    for point in ('source_before', 'source_after_workload', 'source_after_stop'):
        body = controller[point]
        if body.get('matches_expected') is not True or any(body.get(key) for key in ('added', 'removed', 'changed')):
            raise ValueError('Source guard failed: ' + point)
    if len({controller[key]['canonical_sha256'] for key in
            ('source_before', 'source_after_workload', 'source_after_stop')}) != 1:
        raise ValueError('Source guard hashes disagree')
    if not re.fullmatch(r'[0-9a-f]{40}', controller['runtime_revision']):
        raise ValueError('Exact runtime revision required')


def brief(histogram):
    return {key: value for key, value in histogram.items() if key != 'histogram_upper_ns_count'}


def probes(archive, sample, field):
    records = sample[field]
    if set(records) != {'A', 'B', 'C'}:
        raise ValueError('Exactly A/B/C probe records are required')
    result, events = {}, []
    for server, record in records.items():
        reference, data = archive.reference(record['source'])
        if data != record['data']:
            raise ValueError('Embedded probe differs from its raw file')
        roots = data['mod_roots']
        ticks = data['ticks']
        closed = field == 'probe_full_lifecycle'
        errors = ('trace_errors', 'trace_events_dropped', 'frame_depth_mismatches', 'frame_overflow_calls')
        if (data['probe_revision'] != 'v2_mod_roots' or ticks <= 1
                or data['window_closed'] is not closed or roots['valid'] is not True
                or any(data[key] for key in errors) or data['transform_failures']
                or roots['invalid_ticks'] or roots['invalid_cycles']
                or roots['per_complete_tick']['count'] != ticks
                or roots['per_complete_logical_tick_cycle']['count'] != ticks - (0 if closed else 1)
                or data['spans']['server_tick']['inclusive']['count'] != ticks):
            raise ValueError('Incomplete/invalid v2 probe accounting')
        transformed = data['transformed_classes']
        required = {
            'net/minecraft/server/MinecraftServer': 'tickServer(Ljava/util/function/BooleanSupplier;)V',
            'dev/crosstesseract/block/TesseractBlockEntity': 'saveAdditional(Lnet/minecraft/nbt/CompoundTag;Lnet/minecraft/core/HolderLookup$Provider;)V',
        }
        if any(method not in transformed.get(name, {}).get('methods', '') for name, method in required.items()):
            raise ValueError('Required actual transforms missing')
        result[server] = {
            'source': reference, 'token': data['token'], 'window_closed': closed,
            'ticks': ticks, 'actual_tps': data['actual_tps'], 'clock': data['clock'],
            'logical_cycle': brief(roots['per_complete_logical_tick_cycle']),
            'tick_frame': brief(roots['per_complete_tick']),
            'MC_tick': brief(data['spans']['server_tick']['inclusive']),
            'outside_main': brief(roots['outside_tick_main_thread_roots']),
            'worker': brief(roots['non_main_thread_roots']),
            'generator': brief(data['spans']['generator']['inclusive']),
            'coverage_limits': roots['coverage_limits'],
            'logical_cycle_scope': roots['logical_tick_cycle_scope'],
        }
        for index, event in enumerate(data['item_events']):
            if len(events) >= MAX_EVENTS:
                raise ValueError('Bounded trace count exceeded')
            uuid(event['endpoint'])
            if event['operation']:
                uuid(event['operation'])
            if any(type(event[key]) is not int or event[key] < 0 for key in ('nano_time', 'amount', 'revision')):
                raise ValueError('Invalid trace integer')
            events.append(dict(event, server=server, probe_token=data['token'], event_index=index))
    return result, events


def payload_identity(payload, variants):
    """Strict small ASCII AnyTag reader; no Minecraft or operational imports."""
    if not 1 <= len(payload) <= 4096 or len(variants) != 2 or len(set(variants.values())) != 2:
        raise ValueError('Only the bounded two-component stone workload is supported')
    offset = 0

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(payload):
            raise ValueError('Truncated AnyTag')
        result = payload[offset:offset + size]
        offset += size
        return result

    def text():
        size = int.from_bytes(take(2), 'big')
        if size > 512:
            raise ValueError('AnyTag string bound')
        return take(size).decode('ascii')

    def value(kind, depth):
        if depth > 4:
            raise ValueError('AnyTag depth bound')
        if kind == 3:
            return int.from_bytes(take(4), 'big', signed=True)
        if kind == 8:
            return text()
        if kind != 10:
            raise ValueError('Unexpected AnyTag kind')
        result, keys = {}, []
        while True:
            child = take(1)[0]
            if child == 0:
                if keys != sorted(keys):
                    raise ValueError('Unsorted StackCodec compound')
                return result
            key = text()
            if len(result) >= 8 or key in result:
                raise ValueError('Duplicate/oversized AnyTag compound')
            keys.append(key)
            result[key] = value(child, depth + 1)

    tag = value(take(1)[0], 0)
    if (offset != len(payload) or not isinstance(tag, dict)
            or not set(tag) <= {'id', 'count', 'components'}
            or tag.get('id') != 'minecraft:stone' or type(tag.get('count', 1)) is not int
            or tag.get('count', 1) != 1):
        raise ValueError('Not a normalized controlled stone')
    components = tag.get('components')
    if not isinstance(components, dict) or set(components) != {'minecraft:custom_name'}:
        raise ValueError('Unexpected component patch')
    name = components['minecraft:custom_name']
    if not isinstance(name, str):
        raise ValueError('Expected flat CUSTOM_NAME')
    if name.lstrip().startswith(('"', '{')):
        name = decode(name)
        if isinstance(name, dict) and set(name) == {'text'}:
            name = name['text']
    if not isinstance(name, str) or name not in variants.values():
        raise ValueError('Component is not one of the fixed workload identities')
    return {'variant': next(key for key, val in variants.items() if val == name),
            'CUSTOM_NAME': name, 'item_id': 'minecraft:stone',
            'payload_sha256': hashlib.sha256(payload).hexdigest(),
            'actual_payload_bytes': len(payload)}


def sql_identities(raw, sample, events, endpoints, channel):
    audit = sample.get('trace_resource_identity_after_seal', {})
    traced = {event['operation'] for event in events if event['operation']}
    operations, queries = {}, []
    after = raw['observer_monotonic_start'] + sample['counter_after_drain']['end']
    stop_ends = [value['end'] for command in sample['probe_control_commands']
                 if command['command'].startswith('stop ')
                 for value in command['observer_monotonic_intervals'].values()]
    if not stop_ends:
        raise ValueError('No sealed stop control evidence')
    after = max(after, max(stop_ends))
    for query_index, query in enumerate(audit.get('queries', [])):
        if not after <= query['observer_start'] <= query['observer_end']:
            raise ValueError('SQL identity observation was not after counters and probe seal')
        rows = query.get('raw_rows', [])
        if len(rows) > 128:
            raise ValueError('Bounded SQL identity set exceeded')
        queries.append({'query_index': query_index, 'observer_start': query['observer_start'],
                        'observer_end': query['observer_end'], 'row_count': len(rows),
                        'raw_rows_sha256': hashlib.sha256(canonical(rows)).hexdigest()})
        for row_index, row in enumerate(rows):
            if (len(row) != 12 or row[0] not in traced or row[0] in operations
                    or row[1] not in endpoints or row[2] != channel
                    or row[3] not in ('DEPOSIT', 'ALLOCATE') or row[8] != ITEM
                    or row[9] != '1' or not row[11].startswith('hex:')):
                raise ValueError('Unexpected/duplicate SQL operation identity row')
            payload = bytes.fromhex(row[11][4:])
            identity = payload_identity(payload, raw['conditions']['CUSTOM_NAME'])
            if identity['payload_sha256'] != row[10].lower():
                raise ValueError('Actual SQL resource payload SHA mismatch')
            info = dict(identity, operation=uuid(row[0]), endpoint=uuid(row[1]),
                        endpoint_name=endpoints[row[1]]['name'], server=endpoints[row[1]]['server'],
                        channel=uuid(row[2]), transfer_kind=row[3], state=row[4],
                        amount=int(row[5]), remaining=int(row[6]), resource_id=uuid(row[7]),
                        resource_kind=row[8], format_version=1,
                        SQL_evidence={'query_index': query_index, 'row_index': row_index})
            if info['amount'] < 0 or not 0 <= info['remaining'] <= info['amount']:
                raise ValueError('Invalid SQL amount/remaining')
            claimed = audit.get('operations', {}).get(row[0], {})
            for key in ('variant', 'payload_sha256', 'resource_id', 'transfer_kind', 'amount', 'remaining'):
                if key in claimed and claimed[key] != info[key]:
                    raise ValueError('Derived SQL identity disagrees with recorded audit')
            operations[row[0]] = info
    return operations, {'status_as_recorded': audit.get('status', 'UNKNOWN'),
                        'queries': queries, 'unidentified_business_IDs': sorted(traced - operations.keys()),
                        'scope': 'Post-seal SQL resource payload identity only; no timed-window query cost or per-event component ID.'}


def unmeasured(reason):
    return {'status': 'UNMEASURED', 'reason': reason}


def span(start, end, label, signed_observation=False):
    if start is None or end is None:
        return unmeasured('Missing unambiguous trace marker: ' + label)
    if (start['server'], start['probe_token']) != (end['server'], end['probe_token']):
        return unmeasured('Different JVMs; nanoTime is never subtracted across servers')
    if end['nano_time'] < start['nano_time'] and not signed_observation:
        return unmeasured('Trace markers are not in the required order')
    duration = end['nano_time'] - start['nano_time']
    return {'status': 'MEASURED', 'nanoseconds': duration, 'milliseconds': duration / 1_000_000,
            'server': start['server'], 'start_event': start, 'end_event': end,
            'signed_confirmation_observation_difference': signed_observation,
            'scope': label + '; selected test-hook return/observation times, not exact SQL commit or fsync duration'}


def first(events, phase, after=None):
    candidates = [event for event in events if event['phase'] == phase
                  and (after is None or event['nano_time'] >= after['nano_time'])]
    return min(candidates, key=lambda event: event['nano_time']) if candidates else None


def operation_pipeline(info, events):
    events = sorted(events, key=lambda event: event['nano_time'])
    for event in events:
        if event['endpoint'] != info['endpoint'] or event['server'] != info['server']:
            raise ValueError('Business-ID trace endpoint/JVM contradicts actual SQL identity')
    stages, markers = {}, {}
    if info['transfer_kind'] == 'DEPOSIT':
        capture = first(events, 'capture_deposits')
        sql = first(events, 'sql_deposit_confirmed')
        wal_candidates = [event for event in events if capture and sql
                          and event['phase'] == 'wal_return_deposits'
                          and event['revision'] == capture['revision']
                          and capture['nano_time'] <= event['nano_time'] <= sql['nano_time']]
        wal = wal_candidates[0] if wal_candidates else None
        markers = {'capture': capture, 'source_wal_return': wal, 'sql_deposit_confirmed': sql}
        stages = {'capture_to_source_wal_return': span(capture, wal, 'Capture return to matching-revision source WAL return'),
                  'source_wal_return_to_sql_deposit': span(wal, sql, 'Source WAL return to SQL deposit confirmation'),
                  'capture_to_sql_deposit': span(capture, sql, 'Capture return to SQL deposit confirmation')}
    else:
        reserved = first(events, 'sql_reserved_confirmed')
        local = first(events, 'sql_LOCAL_confirmed')
        candidates = [event for event in events if reserved and local
                      and event['phase'] == 'wal_return_credits' and event['amount'] > 0
                      and event['revision'] == local['revision']
                      and reserved['nano_time'] <= event['nano_time'] <= local['nano_time']]
        wal = candidates[0] if candidates else None
        applied = first(events, 'RX_apply', local) if local else None
        markers = {'sql_reserved_confirmed': reserved, 'destination_wal_return': wal,
                   'sql_LOCAL_confirmed': local, 'RX_apply': applied}
        stages = {'sql_reserved_to_destination_wal_return': span(reserved, wal, 'SQL reservation confirmation to matching-revision destination WAL return'),
                  'destination_wal_return_to_LOCAL': span(wal, local, 'Destination WAL return to SQL LOCAL confirmation'),
                  'LOCAL_to_RX_apply': span(local, applied, 'SQL LOCAL confirmation to main-thread RX apply')}
    return dict(info, events=events, markers=markers, stages=stages,
                marker_selection='First observed confirmation/capture; first matching-revision WAL return preceding confirmation. Every trace event remains listed; no latency-minimizing selection.')


def unique_consumption(info, all_events, identities, external_amount):
    endpoint_events = [event for event in all_events if event['endpoint'] == info['endpoint']]
    allocations = [value for value in identities.values()
                   if value['endpoint'] == info['endpoint'] and value['transfer_kind'] == 'ALLOCATE']
    reserved = [event for event in endpoint_events if event['phase'] == 'sql_reserved_confirmed']
    applied = [event for event in endpoint_events if event['phase'] == 'RX_apply']
    consumed = [event for event in endpoint_events if event['phase'] == 'local_RX_consumed']
    credit_operations = {event['operation'] for event in endpoint_events
                         if event['phase'] in ('sql_reserved_confirmed', 'wal_return_credits',
                                               'capture_credits', 'sql_LOCAL_confirmed', 'RX_apply')}
    if (len(allocations) != 1 or len(reserved) != 1 or len(applied) != 1 or len(consumed) != 1
            or info['amount'] != 32 or external_amount != 32
            or credit_operations != {info['operation']}
            or reserved[0]['amount'] != 32 or applied[0]['amount'] != 32 or consumed[0]['amount'] != 32
            or applied[0]['operation'] != info['operation']
            or reserved[0]['operation'] != info['operation']):
        return unmeasured('Endpoint does not have exactly one complete-window ITEM allocation/apply/consume and 32 externally received items of this variant')
    result = span(applied[0], consumed[0], 'RX apply to unique complete-window local RX consumption')
    result['attribution'] = ('Derived only from one ITEM allocation/apply/consume for this endpoint across the sealed window plus exactly32 external items of its SQL-identified variant; consume hook has no business ID')
    return result


def bounds(source, target):
    if any(not isinstance(point[key], (int, float)) or not math.isfinite(point[key])
           for point in (source, target) for key in ('start', 'end')):
        raise ValueError('Invalid external observation interval')
    if source['start'] > source['end'] or target['start'] > target['end']:
        raise ValueError('Inverted external observation interval')
    return {'lower_ms': max(0, (target['start'] - source['end']) * 1000),
            'upper_ms': max(0, (target['end'] - source['start']) * 1000)}


def external_batch(batch):
    result = {}
    for variant, record in batch['variants'].items():
        item = {key: record.get(key) for key in ('injection', 'source_first_decrement', 'source_empty_interval', 'full_output', 'outputs_by_sink')}
        for metric, start, end in (
                ('input_to_source', 'injection', 'source_first_decrement'),
                ('source_to_full_output', 'source_first_decrement', 'full_output'),
                ('input_to_full_output', 'injection', 'full_output')):
            if record.get(start) is None or record.get(end) is None:
                item[metric] = unmeasured('External physical observation missing')
                continue
            measured = bounds(record[start], record[end])
            original = record[metric + '_bounds']
            if any(not math.isclose(measured[key], original[key], abs_tol=.000001, rel_tol=1e-9) for key in measured):
                raise ValueError('External bounds disagree with retained observations')
            item[metric] = dict(measured, status='MEASURED',
                                scope='One Python observer; source means first physical source-chest decrement, full means all32 external items of this variant')
        result[variant] = item
    return {'sequence': batch['sequence'], 'phase': batch['phase'], 'passed': batch['passed'], 'variants': result}


def costs(sample, field, end):
    delta = sample[field]
    shortest = sample[end]['start'] - sample['counter_start']['end']
    longest = sample[end]['end'] - sample['counter_start']['start']
    if not 0 < shortest <= longest:
        raise ValueError('Invalid cost observation bounds')
    transactions = delta['sum'].get('db_transactions')
    return {'sum': delta['sum'], 'per_server': delta['per_server'],
            'measurement_status': delta['measurement_status'],
            'account_statement_events': delta.get('account_statement_events'),
            'observation_seconds_bounds': {'lower': shortest, 'upper': longest},
            'physical_transactions_per_second_bounds': (
                {'lower': transactions / longest, 'upper': transactions / shortest} if transactions is not None
                else unmeasured('Physical transaction counter unavailable')),
            'scope': 'Aggregate simultaneous FE/water/ITEM workload, not attributable per ITEM variant. Helper SQL counters and account SQL events are different measures; full includes actual drain/quiet. Missing counters are UNMEASURED, never zero.'}


def summarize(archive, controller_path):
    controller_ref, controller = archive.read(controller_path)
    completed(controller)
    raw_ref, raw = archive.reference(controller['raw_report'])
    runtime_ref, runtime = archive.reference(controller['runtime_manifest'])
    archive.reference(controller['checkout_source_guard_manifest'])
    if (raw['probe_manifest'] != controller['runtime_manifest'] or raw['probe_configuration'] != runtime
            or raw['operator_runtime_revision'] != controller['runtime_revision']
            or raw.get('passed') is not True or raw.get('native_executed') is not True
            or not raw.get('utc_end') or raw.get('failures') or raw['cluster'] != 'dev_three_v1'
            or runtime['probe']['recorder_revision'] != 'v2_mod_roots'):
        raise ValueError('Raw/runtime/controller identities or completion differ')
    if not 1 <= len(raw['samples']) <= 16:
        raise ValueError('Bounded completed sample set required')
    endpoints = {uuid(device['id']): device for device in raw['devices']}
    if len(endpoints) != len(raw['devices']):
        raise ValueError('Duplicate endpoint mapping')
    result = {'controller': controller_ref, 'raw': raw_ref, 'runtime_manifest': runtime_ref,
              'runtime_revision': controller['runtime_revision'], 'mode': controller['mode'],
              'controller_variant': controller['variant'], 'source_and_runtime_qualified': True,
              'utc_start': controller['utc_start'], 'utc_end': controller['utc_end'],
              'source_guard_expected_revision': controller['source_guard_expected_revision'],
              'source_points': {key: {field: controller[key][field] for field in ('utc', 'canonical_sha256', 'matches_expected')}
                                for key in ('source_before', 'source_after_workload', 'source_after_stop')},
              'runtime_evidence_scope': 'Bound archived controller/launch manifest and as-run hashes; operator runtime revision and checkout-source guard are distinct. This is not classloader attestation.',
              'probe_identity': {'probe_manifest_sha256': runtime['probe_manifest_sha256'], 'probe': runtime['probe']},
              'conditions': raw['conditions'], 'endpoint_map': endpoints, 'samples': [],
              'as_run_helper_sources': raw.get('helper_sources', {}),
              'as_run_source_evidence': raw.get('source_evidence'),
              'service': {key: raw.get(key) for key in ('receiver_service_scope', 'steady_window_actual_receiver_service', 'steady_plus_tail_actual_receiver_service', 'all_phase_actual_receiver_service')},
              'warnings_as_recorded': raw.get('warnings', [])}
    seen = set()
    for sample_index, sample in enumerate(raw['samples']):
        key = (sample['scenario'], sample['repeat'])
        if key in seen or sample['passed'] is not True:
            raise ValueError('Duplicate or unsuccessful sample')
        seen.add(key)
        fixed, _ = probes(archive, sample, 'probe_fixed_window')
        full, events = probes(archive, sample, 'probe_full_lifecycle')
        fixtures = raw['fixtures'][sample['scenario']]
        if len(fixtures) != 1:
            raise ValueError('Exactly one owned channel per sample is required')
        channel = uuid(fixtures[0]['channel'])
        identities, audit = sql_identities(raw, sample, events, endpoints, channel)
        grouped = defaultdict(list)
        for event in events:
            if event['endpoint'] not in endpoints or endpoints[event['endpoint']]['server'] != event['server']:
                raise ValueError('Trace endpoint/server mapping absent or contradictory')
            if event['operation']:
                grouped[event['operation']].append(event)
        pipelines = {operation: operation_pipeline(info, grouped[operation]) for operation, info in identities.items()}
        batches = [external_batch(batch) for batch in raw['item_batches']
                   if batch['lane'] == sample['scenario'] and batch['repeat'] == sample['repeat'] and batch['phase'] == 'steady']
        for operation, pipeline in pipelines.items():
            if pipeline['transfer_kind'] == 'ALLOCATE':
                external = sum(batch['variants'].get(pipeline['variant'], {}).get('outputs_by_sink', {}).get(pipeline['endpoint_name'], 0) for batch in batches)
                pipeline['stages']['RX_apply_to_unique_RX_consumed'] = unique_consumption(
                    pipeline, events, identities, external)
        flow = {}
        for variant in raw['conditions']['CUSTOM_NAME']:
            deposits = [value for value in pipelines.values() if value['variant'] == variant and value['transfer_kind'] == 'DEPOSIT']
            allocations = [value for value in pipelines.values() if value['variant'] == variant and value['transfer_kind'] == 'ALLOCATE']
            if len(deposits) == len(allocations) == 1 and all(
                    deposits[0][field] == allocations[0][field]
                    for field in ('channel', 'resource_id', 'resource_kind', 'format_version', 'payload_sha256', 'amount')):
                gap = span(deposits[0]['markers']['sql_deposit_confirmed'],
                           allocations[0]['markers']['sql_reserved_confirmed'],
                           'Same-JVM signed deposit-confirmation to reservation-confirmation observation difference; negative values may reflect result-hook ordering in one returned batch, not a negative SQL transition duration',
                           signed_observation=True)
            else:
                gap = unmeasured('Resource pooling or multiple/missing operations prevents a unique source/destination operation pair')
            flow[variant] = {'deposit_operations': [value['operation'] for value in deposits],
                             'allocation_operations': [value['operation'] for value in allocations],
                             'source_SQL_to_destination_reservation': gap}
        guard = sample['conservation']['guard']
        snapshots = guard['snapshots']
        if not snapshots:
            raise ValueError('Conservation requires actual quiet observations')
        residue = snapshots[-1]['residue']
        ledger = sample['steady_and_tail_ledger_change']
        balanced = all(value['accepted'] == value['external_output'] and
                       (not kind.startswith('item_') or value['source_actual_decrement'] == value['accepted'])
                       for kind, value in ledger.items())
        item = {'sample_index': sample_index, 'scenario': sample['scenario'], 'repeat': sample['repeat'],
                'channel': channel, 'external_ITEM_batches': batches,
                'operations': pipelines, 'SQL_identity_audit': audit, 'variant_flows': flow,
                'unassigned_events': [dict(event, attribution=unmeasured(
                    ('local_input has no business ID and is never assigned a variant by time, order or amount'
                     if event['phase'] == 'local_input' else 'Hook has no business ID; any uniquely derived endpoint consumption link is explicitly reported in the allocation stages')
                    if not event['operation'] else 'Business ID has no validated post-seal SQL identity'))
                    for event in events if not event['operation'] or event['operation'] not in identities],
                'trace_phase_counts': dict(Counter(event['phase'] for event in events)),
                'costs': {'fixed': costs(sample, 'counter_delta', 'counter_end'),
                          'full': costs(sample, 'lifecycle_counter_delta', 'counter_after_drain')},
                'windows': {'fixed': fixed, 'full': full},
                'steady_ledger': sample['steady']['ledger_change'], 'full_ledger': ledger,
                'conservation': {'passed_as_recorded': sample['conservation']['passed'],
                                 'per_resource_ledger_balanced': balanced,
                                 'quiet_passed_as_recorded': guard['passed'],
                                 'quiet_seconds': guard['quiet_seconds'],
                                 'all_guard_observations_empty': all(point['empty'] is True for point in snapshots),
                                 'guard_observation_states': [{key: point[key] for key in ('at', 'empty')} for point in snapshots],
                                 'final_residue': residue,
                                 'SQL_and_local_zero_separately': (
                                     all(value['pool'] == value['allocation_remaining'] == 0 for value in residue['resources'])
                                     and all(all(value[field] == 0 for field in ('txFE', 'rxFE', 'txItem', 'rxItem', 'txFluid', 'rxFluid'))
                                             for value in residue['local_buffers'].values())),
                                 'guard': {key: value for key, value in guard.items() if key != 'snapshots'},
                                 'guard_snapshot_count': len(snapshots),
                                 'scope': 'Guard observations include any initial nonempty state and reset before the final continuous quiet suffix; all_guard_observations_empty is not the quiet acceptance predicate.'},
                'service_scope': 'Per resource and receiver; service does not imply equal share or general fairness bounds.'}
        result['samples'].append(item)
    result['sample_count'] = len(result['samples'])
    result['external_ITEM_variant_observations'] = sum(len(batch['variants']) for sample in result['samples'] for batch in sample['external_ITEM_batches'])
    return result


def csv_rows(runs):
    rows = []
    for run in runs:
        for sample in run['samples']:
            base = {'controller': run['controller']['path'], 'runtime_revision': run['runtime_revision'],
                    'mode': run['mode'], 'scenario': sample['scenario'], 'repeat': sample['repeat']}
            def add(**values):
                rows.append(dict(base, **values))
            for batch in sample['external_ITEM_batches']:
                for variant, value in batch['variants'].items():
                    for metric in ('input_to_source', 'source_to_full_output', 'input_to_full_output'):
                        observed = value[metric]
                        add(row_kind='external_ITEM', batch_sequence=batch['sequence'], variant=variant,
                            metric=metric, status=observed['status'], lower_ms=observed.get('lower_ms'),
                            upper_ms=observed.get('upper_ms'), unit='ms', detail=observed.get('reason', observed.get('scope')))
            for operation, value in sample['operations'].items():
                for metric, observed in value['stages'].items():
                    add(row_kind='pipeline', variant=value['variant'], endpoint=value['endpoint'],
                        operation=operation, server=value['server'], metric=metric, status=observed['status'],
                        value=observed.get('milliseconds'), unit='ms', detail=observed.get('reason', observed.get('scope')))
            for variant, value in sample['variant_flows'].items():
                observed = value['source_SQL_to_destination_reservation']
                add(row_kind='pipeline_confirmation_gap', variant=variant,
                    metric='source_SQL_to_destination_reservation', status=observed['status'],
                    value=observed.get('milliseconds'), unit='ms', detail=observed.get('reason', observed.get('scope')))
            for scope, value in sample['costs'].items():
                for metric, count in value['sum'].items():
                    add(row_kind='aggregate_cost', scope=scope, metric=metric, value=count,
                        status=value['measurement_status'].get(metric, 'UNMEASURED'), unit='count_or_bytes_as_named')
                account = value['account_statement_events']
                add(row_kind='account_SQL', scope=scope, metric='account_statement_events',
                    value=account.get('events') if account else None,
                    status='MEASURED' if account else 'UNMEASURED', unit='events')
            for scope, servers in sample['windows'].items():
                for server, value in servers.items():
                    for metric, count in (('logical_cycle_p99_ns_upper', value['logical_cycle']['p99_ns_upper']),
                                          ('MC_tick_p95_ns_upper', value['MC_tick']['p95_ns_upper']),
                                          ('actual_tps', value['actual_tps'])):
                        add(row_kind='complete_window', scope=scope, server=server, metric=metric,
                            value=count, status='MEASURED', unit='TPS' if metric == 'actual_tps' else 'ns')
            for resource, value in sample['full_ledger'].items():
                for endpoint, count in value['output_by_endpoint'].items():
                    add(row_kind='receiver_service', scope='steady_plus_tail', endpoint=endpoint,
                        metric=resource, value=count, status='MEASURED', unit=value['unit'])
            add(row_kind='conservation', scope='steady_plus_tail', metric='per_resource_ledger_balanced',
                value=sample['conservation']['per_resource_ledger_balanced'], status='MEASURED', unit='boolean')
    return rows


class OfflineTests(unittest.TestCase):
    def event(self, phase='RX_apply', server='A', nano=10, operation='x'):
        return {'phase': phase, 'server': server, 'probe_token': 'same', 'nano_time': nano,
                'amount': 32, 'endpoint': 'endpoint', 'operation': operation, 'revision': 1}

    def test_same_jvm_only(self):
        self.assertEqual(span(self.event(), self.event(nano=20), 'test')['nanoseconds'], 10)
        self.assertEqual(span(self.event(), self.event(server='B', nano=20), 'test')['status'], 'UNMEASURED')
        self.assertEqual(span(self.event(nano=20), self.event(), 'test')['status'], 'UNMEASURED')

    def test_signed_confirmation_observation(self):
        self.assertEqual(span(self.event(nano=20), self.event(), 'confirmation order', True)['nanoseconds'], -10)
        self.assertEqual(span(self.event(nano=20), self.event(server='B'), 'confirmation order', True)['status'], 'UNMEASURED')

    def test_unique_consumption_and_ambiguity(self):
        info = {'operation': 'x', 'endpoint': 'endpoint', 'transfer_kind': 'ALLOCATE', 'amount': 32}
        events = [self.event('sql_reserved_confirmed'), self.event(), self.event('local_RX_consumed', nano=30, operation='')]
        self.assertEqual(unique_consumption(info, events, {'x': info}, 32)['status'], 'MEASURED')
        self.assertEqual(unique_consumption(info, events + [self.event('local_RX_consumed', nano=40, operation='')], {'x': info}, 32)['status'], 'UNMEASURED')
        self.assertEqual(unique_consumption(info, events, {'x': info}, 31)['status'], 'UNMEASURED')
        self.assertEqual(unique_consumption(info, events + [self.event('capture_credits', operation='unknown')], {'x': info}, 32)['status'], 'UNMEASURED')

    def test_external_bounds(self):
        self.assertEqual(bounds({'start': 1, 'end': 2}, {'start': 3, 'end': 4}), {'lower_ms': 1000, 'upper_ms': 3000})

    def test_sql_payload_identity(self):
        def text(value):
            raw = value.encode('ascii')
            return len(raw).to_bytes(2, 'big') + raw
        variants = {'A': 'CT mixed A', 'B': 'CT mixed B'}
        for variant in ('B', 'A'):
            payload = (b'\x0a\x0a' + text('components') + b'\x08' + text('minecraft:custom_name')
                       + text(json.dumps(variants[variant])) + b'\x00\x03' + text('count')
                       + (1).to_bytes(4, 'big') + b'\x08' + text('id') + text('minecraft:stone') + b'\x00')
            self.assertEqual(payload_identity(payload, variants)['variant'], variant)
            with self.assertRaises(ValueError):
                payload_identity(payload + b'\x00', variants)

    def test_archive_binding_and_escape(self):
        with tempfile.TemporaryDirectory(prefix='rc-mix-summary-offline-') as directory:
            root = Path(directory)
            (root / 'reports').mkdir()
            path = root / 'reports/test.json'
            path.write_text('{}')
            archive = Archive(root)
            self.assertEqual(archive.reference({'path': 'reports/test.json', 'sha256': hashlib.sha256(b'{}').hexdigest()})[1], {})
            with self.assertRaises(ValueError):
                archive.reference({'path': 'reports/test.json', 'sha256': '0' * 64})
            with self.assertRaises(ValueError):
                archive.read('../outside.json')

    def test_incomplete_controller_rejected(self):
        with self.assertRaises(ValueError):
            completed({'state': 'RUNNING', 'qualified_passed': True})

    def test_matching_revision_wal(self):
        info = {'endpoint': 'endpoint', 'server': 'A', 'transfer_kind': 'DEPOSIT'}
        capture = self.event('capture_deposits')
        wrong = dict(self.event('wal_return_deposits', nano=11), revision=2)
        sql = self.event('sql_deposit_confirmed', nano=20)
        self.assertEqual(operation_pipeline(info, [capture, wrong, sql])['stages']['capture_to_source_wal_return']['status'], 'UNMEASURED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller', action='append', default=[], help='Completed mix controller under repository reports; repeat for multiple runs')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        if args.controller:
            parser.error('--self-test uses synthetic data only')
        outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OfflineTests))
        print(json.dumps({'offline_self_test_passed': outcome.wasSuccessful(), 'native_SQL_RCON': 'NOT RUN'}))
        return 0 if outcome.wasSuccessful() else 1
    if not 1 <= len(args.controller) <= MAX_CONTROLLERS or len(set(args.controller)) != len(args.controller):
        parser.error('Provide one to eight distinct closed --controller reports')
    archive = Archive()
    runs = [summarize(archive, path) for path in args.controller]
    if len({run['controller']['path'] for run in runs}) != len(runs):
        raise ValueError('Duplicate resolved controller path')
    recipe_path = Path(__file__).resolve()
    report = {'kind': 'offline_RC_mix_archive_summary', 'utc': datetime.now(timezone.utc).isoformat(),
              'recipe': {'path': str(recipe_path.relative_to(ROOT)), 'sha256': hashlib.sha256(recipe_path.read_bytes()).hexdigest()},
              'sources': list(archive.files.values()), 'runs': runs,
              'limitations': [
                  'Descriptive observations only: n1 windows and two fixed ITEM variants do not establish a population p95, significance or general capacity.',
                  'External bounds use one observer. No local_input event is assigned a variant by time, order or amount.',
                  'Trace identity comes only from post-seal actual SQL resource payloads joined by business UUID; deposit/allocation assets are not added to WAL/local mirrors.',
                  'Only same-JVM nanoTime differences are measured. Cross-server source SQL to destination reservation remains UNMEASURED; same-JVM values are confirmation observations, not exact SQL transition times.',
                  'wal_return is a successful LocalJournal.write return, including possible identical-snapshot skips. It is not an independent file/directory fsync, power-loss durability measurement, or device latency.',
                  'RX consumption hooks have no business ID. Attribution is permitted only for one allocation/apply/consume and exactly32 external variant items for that endpoint across the complete sealed window.',
                  'Main-thread quantiles are the validated deduplicated selected-root logical-cycle histograms. Method p99 is not whole-mod p99; uncovered entry points and worker costs are distinct.',
                  'Fixed counters precede final drain. Full cost includes actual drain/quiet; aggregate mixed-resource cost cannot be apportioned to an ITEM variant.',
                  'No live SQL, RCON, Minecraft, JDK/JFR parser, workload, lifecycle or fallback action is performed by this tool.',
              ], 'performance_acceptance_assessed': False}
    payload = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if len(payload.encode()) > MAX_FILE_BYTES:
        raise ValueError('Bounded derived report size exceeded')
    prefix = ROOT / 'reports/rc-20261017' / ('mix-summary-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:12])
    with prefix.with_suffix('.json').open('x') as stream:
        stream.write(payload)
    with prefix.with_suffix('.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_rows(runs))
    print(json.dumps({'report': str(prefix.with_suffix('.json').relative_to(ROOT)),
                      'csv': str(prefix.with_suffix('.csv').relative_to(ROOT)),
                      'runs': len(runs), 'performance_acceptance_assessed': False, 'native_SQL_RCON': 'NOT RUN'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
