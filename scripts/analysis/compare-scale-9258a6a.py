#!/usr/bin/env python3
"""Fixed archived-dataset recipe for 87bf217/75392af/9258a6a scale reports.

Reads saved local JSON, verifies archived input hashes, and writes the named
9258a6a comparison JSON/CSV/Markdown. Requires the saved 75392af comparison.
This derives existing measurements; it performs no live collection or JDK work.
"""
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
REVISIONS = {'original_87': '87bf217fcaffcceb2629c36bb54d5158b9f461e8',
    'reference_753': '75392af252744f240253d134d1da565a49b2cc9f',
    'current_9258': '9258a6ade8c94e863a450a3f5eec95dff9c9ee2b'}
PATHS = {
    'original_87': 'reports/performance-opt-baseline-87bf217.json',
    'reference_753': 'reports/performance-opt-fast-75392af.json',
    'current_9258': 'reports/performance-opt-fast-9258a6a.json',
    'original_monitor': 'reports/optimization-scale-baseline-scale-late-20261006T100021Z-09d5b0.json',
    'reference_monitor': 'reports/optimization-scale-fast-scale-fixed-75392af-20261006T135146Z-3eebad.json',
    'current_monitor': 'reports/optimization-scale-fast-scale-cache-ready-9258a6a-20261006T162235Z-a50f0c.json',
    'initial_failed_monitor': 'reports/optimization-scale-fast-scale-cache-9258a6a-20261006T161935Z-d52650.json',
    'observer_restart': 'reports/optimization-scale-9258a6a-observer-restart.json',
    'current_conditions': 'reports/optimization-conditions-fast-scale-cache-9258a6a.json',
    'current_artifact': 'reports/optimization-artifact-hotspot-final.json',
    'reference_artifact': 'reports/optimization-artifact-savepoint.json',
    'previous_comparison': 'reports/optimization-scale-comparison-75392af.json'}
COUNTERS = ('db_transactions', 'db_transaction_attempts', 'db_statements', 'db_deadlock_retries',
    'transactions', 'errors', 'queue_rejected', 'quarantined', 'batch_devices', 'batch_records',
    'batch_payload_bytes', 'local_input_units', 'local_output_units', 'wal_writes', 'wal_bytes',
    'wal_identical_skipped')
RING_KEYS = tuple(f'{kind}_ms_{q}' for kind in ('tick', 'delivery', 'sql') for q in ('p50', 'p95', 'p99', 'samples'))
GC_KEYS = ('YGC', 'YGCT', 'FGC', 'FGCT', 'CGC', 'CGCT', 'GCT')
documents, sources = {}, {}
for key, relative in PATHS.items():
    data = (ROOT / relative).read_bytes()
    assert len(data) <= 4 * 1024 * 1024, relative
    documents[key] = json.loads(data)
    sources[key] = dict(path=relative, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
previous = documents['previous_comparison']
for key, old in [('original_87', 'original_87'), ('reference_753', 'current_753'),
    ('original_monitor', 'original_monitor'), ('reference_monitor', 'current_monitor')]:
    assert sources[key]['sha256'] == previous['sources'][old]['sha256'], key
assert documents['current_conditions']['source_commit'] == REVISIONS['current_9258']
assert documents['current_artifact']['source_revision'] == REVISIONS['current_9258']
assert sources['current_monitor']['sha256'] == documents['observer_restart']['replacement_report_sha256']
assert documents['current_conditions']['selected_launch']['pid'] == documents['current_monitor']['identity']['pid']

def delta(first, last, keys):
    result = {key: last[key] - first[key] if key in first and key in last else None for key in keys}
    assert all(value is None or value >= 0 for value in result.values()), result
    return result

def change(old, new):
    return (new / old - 1) * 100 if old is not None and new is not None and old > 0 else None

def window(key, rounds, label, meaning, steady=True):
    doc = documents[key]
    indexed = {s['round']: s for s in doc['samples']}
    selected = [indexed[n] for n in rounds]
    assert list(rounds) == list(range(rounds[0], rounds[-1] + 1))
    assert len({s['bulk']['metrics']['count'] for s in selected}) == 1
    first, last = selected[0], selected[-1]
    fs, ls = first['status'], last['status']
    elapsed = ls['observer_end'] - fs['observer_end']
    low, high = ls['observer_start'] - fs['observer_end'], ls['observer_end'] - fs['observer_start']
    assert 0 < low <= elapsed <= high
    counters = delta(fs['metrics'], ls['metrics'], COUNTERS)
    bulk = delta(first['bulk']['metrics'], last['bulk']['metrics'], ('accepted', 'extracted', 'fixture_ms_total', 'fixture_ticks'))
    active = [s['status']['metrics']['active_endpoints'] for s in selected]
    count = first['bulk']['metrics']['count']
    cpu_delta = last['proc']['cpu_total_seconds'] - first['proc']['cpu_total_seconds']
    cpu_time = last['observer_start'] - first['observer_start']
    cpu_low, cpu_high = last['observer_start'] - first['observer_end'], last['observer_end'] - first['observer_start']
    assert cpu_delta >= 0 and 0 < cpu_low <= cpu_time <= cpu_high
    gc = [s for s in selected if s.get('jstat_gc', {}).get('values') and not s['jstat_gc'].get('error')
        and s['jstat_gc']['observer_start'] >= fs['observer_start'] and s['jstat_gc']['observer_end'] <= ls['observer_end']]
    heap = [s['heap']['heap_used_bytes'] / 1048576 for s in gc if s.get('heap', {}).get('heap_used_bytes') is not None]
    return dict(label=label, run=key, source_revision=REVISIONS[{'original_monitor':'original_87',
        'reference_monitor':'reference_753', 'current_monitor':'current_9258'}[key]],
        source_path=sources[key]['path'], source_sha256=sources[key]['sha256'], meaning=meaning,
        steady_candidate=steady, selected_rounds=list(rounds), observed_phase_ids=sorted({s['observed_phase_id'] for s in selected}),
        observed_mode_counts=dict(Counter(s['observed_mode'] for s in selected)), bulk_count=count, samples=len(selected),
        first_reset_observed=first.get('window_reset_observed', False),
        first_status_request_utc=fs['utc_request_start'], first_status_reply_utc=fs['utc_reply_end'],
        last_status_request_utc=ls['utc_request_start'], last_status_reply_utc=ls['utc_reply_end'],
        observer_interval=dict(first_status_request=fs['observer_start'], first_status_reply=fs['observer_end'],
            last_status_request=ls['observer_start'], last_status_reply=ls['observer_end']),
        observed_seconds_reply_to_reply=elapsed, time_seconds_bounds=dict(lower=low, upper=high),
        counter_delta=counters, DB_transactions_per_observed_second=counters['db_transactions']/elapsed,
        DB_transactions_per_capture_second_bounds=dict(lower=counters['db_transactions']/high, upper=counters['db_transactions']/low),
        bulk_counter_delta=bulk, extracted_FE_per_observed_second=bulk['extracted']/elapsed,
        active_first_last_min_max=[active[0], active[-1], min(active), max(active)],
        samples_matching_full_active_count=sum(v == count for v in active), samples_matching_zero_active=sum(v == 0 for v in active),
        zero_worker_activity=counters['transactions'] == 0,
        observed_worker_error_free=all(counters[k] == 0 for k in ('errors','queue_rejected','quarantined')),
        coverage='Only actual selected counter spans; sequential status/bulk snapshots, approximate logical phase matching; no interpolation.',
        cpu=dict(delta_seconds=cpu_delta, elapsed_sample_start_seconds=cpu_time,
            process_percent_nominal=cpu_delta/cpu_time*100,
            elapsed_seconds_conservative_bounds=dict(lower=cpu_low, upper=cpu_high),
            process_percent_bounds=dict(lower=cpu_delta/cpu_high*100, upper=cpu_delta/cpu_low*100),
            scope='All JVM threads; one logical CPU=100%; coarse process read bounds, not Runtime/main-thread CPU.'),
        rss_MiB=dict(sample_mean=statistics.mean(s['proc']['rss_bytes']/1048576 for s in selected),
            sample_max=max(s['proc']['rss_bytes']/1048576 for s in selected)),
        heap_gc=dict(samples=len(gc), selected_rounds=[s['round'] for s in gc],
            first_observer_request=gc[0]['jstat_gc']['observer_start'] if gc else None,
            last_observer_reply=gc[-1]['jstat_gc']['observer_end'] if gc else None,
            heap_used_MiB_sample_mean=statistics.mean(heap) if heap else None, heap_used_MiB_sample_max=max(heap) if heap else None,
            GC_counter_delta=delta(gc[0]['jstat_gc']['values'],gc[-1]['jstat_gc']['values'],GC_KEYS) if len(gc)>1 else None,
            coverage='Contained jstat observations only; point heap not live allocation, GCT includes concurrent work and is not STW pause.'))

windows = []
for old in previous['observed_windows']:
    if old['run'] not in ('original_monitor','current_monitor') or not old['steady_candidate']:
        continue
    key = 'reference_monitor' if old['run'] == 'current_monitor' else 'original_monitor'
    name = old['label'].replace('current_', 'reference_753_', 1) if key == 'reference_monitor' else old['label']
    w = window(key,old['selected_rounds'],name,old['meaning'])
    for counter in COUNTERS:
        assert w['counter_delta'][counter] == old['counter_delta'][counter], (name,counter)
    assert abs(w['observed_seconds_reply_to_reply']-old['observed_seconds_reply_to_reply']) < 1e-8
    windows.append(w)
current = documents['current_monitor']
for phase, name, steady, meaning in [(1,'current_9258_100_active_late_tail',False,'Late observer starts without seeing reset; ACTIVE mode tail only, not a complete steady window.'),
    (4,'current_9258_500_off_post_reset',True,'Observed post-reset OFF; excludes setup/warmup prelude.'),
    (6,'current_9258_500_active_post_reset',True,'Observed post-reset full active count; excludes warmup prelude.'),
    (9,'current_9258_1000_off_post_reset',True,'Observed post-reset OFF; excludes setup/warmup prelude.'),
    (11,'current_9258_1000_active_post_reset',True,'Observed post-reset full active count; excludes warmup prelude.')]:
    rounds=[s['round'] for s in current['samples'] if s.get('observed_phase_id')==phase]
    assert len(rounds)==(37 if phase==1 else 60)
    w=window('current_monitor',rounds,name,meaning,steady)
    assert w['first_reset_observed'] == steady
    windows.append(w)
    if phase==6: windows.append(window('current_monitor',rounds[-24:],'current_9258_500_active_matching_late_24_sample_tail',
        'Last 24 post-reset points, matched approximately to the available original500 ACTIVE late tail.'))
by_window={w['label']:w for w in windows}

native=[]
for run,old_run in [('original_87','original_87'),('reference_753','current_753')]:
    for old in previous['full_nominal_samples']:
        if old['run']==old_run:
            row=deepcopy(old);row['run']=run;row['source_revision']=REVISIONS[run]
            native.append(row)
for scenario in documents['current_9258']['scenarios']:
    for s in scenario['samples']:
        fm,lm=s['first_metrics'],s['metrics'];count=scenario['count'];counters=delta(fm,lm,COUNTERS)
        assert counters['db_transactions']==s['DB_transactions_window']
        active=count if s['active'] else 0
        checks=dict(first_loaded=fm['registered_loaded_endpoints']==count,last_loaded=s['loaded_endpoints']==count,
            last_registered=s['registered_endpoints']==count,first_active=fm['active_endpoints']==active,last_active=s['active_endpoints']==active,
            worker_error_free=s['worker_errors']==0,rejection_free=s['queue_rejections']==0,quarantine_free=counters['quarantined']==0)
        assert all(checks.values()),checks
        native.append(dict(run='current_9258',source_revision=REVISIONS['current_9258'],source=sources['current_9258'],
            count=count,active_requested=s['active'],seconds_nominal=s['seconds'],channel_distribution=scenario['channel_distribution'],
            registered_final=s['registered_endpoints'],loaded_final=s['loaded_endpoints'],active_first=fm['active_endpoints'],active_final=s['active_endpoints'],
            accepted_FE=s['accepted_FE'],extracted_FE=s['extracted_FE'],extracted_FE_per_nominal_second=s['extracted_FE_per_second'],
            worker_transactions_per_nominal_second=s['worker_transactions_per_second'],worker_errors=s['worker_errors'],queue_rejections=s['queue_rejections'],
            fixture_ms_per_tick=s['fixture_ms_per_tick'],counter_delta=counters,DB_transactions_per_nominal_second=s['DB_transactions_per_second'],
            counter_capture_seconds_bounds=s['counter_capture_seconds_bounds'],DB_transactions_per_capture_second_bounds=s['DB_transactions_per_capture_second_bounds'],
            observed_snapshot_checks_passed=all(checks.values()),observed_snapshot_checks=checks,
            full_window_DB_state='CAPTURED_FIRST_LAST_COUNTERS_WITH_BOUNDS',counter_snapshots=dict(first=fm,last=lm),
            last_metric_ring_snapshot={k:lm.get(k) for k in RING_KEYS},
            native_recorded_tick_avg100_snapshot_ms=lm.get('mc_recorded_tick_ms_avg100'),native_target_ticks_per_second=lm.get('mc_target_ticks_per_second')))
by_native={(r['run'],r['count'],r['active_requested']):r for r in native}
ring_comparisons=[]
for reference in ('original_87','reference_753'):
    for count in (100,500,1000):
        for active in (False,True):
            a,b=by_native[reference,count,active],by_native['current_9258',count,active]
            for metric in RING_KEYS:
                if metric.endswith('_samples'):continue
                old,new=a['last_metric_ring_snapshot'].get(metric),b['last_metric_ring_snapshot'].get(metric)
                ring_comparisons.append(dict(reference=reference,current='current_9258',count=count,active_requested=active,
                    metric=metric,reference_ms=old,current_ms=new,change_percent=change(old,new),
                    scope='Descriptive final bounded-ring snapshots, not complete120s/time-aligned percentiles or causal effects.'))
rate_comparisons=[]
for count,mode in [(500,'active'),(1000,'off'),(1000,'active')]:
    suffix='500_active_late_tail' if count==500 else f'1000_{mode}_post_reset'
    baseline=by_window['baseline_'+suffix]
    for prefix in ('reference_753_','current_9258_'):
        suffix2='500_active_matching_late_24_sample_tail' if count==500 else suffix
        candidate=by_window[prefix+suffix2]
        rate_comparisons.append(dict(reference_window=baseline['label'],candidate_window=candidate['label'],
            reference_rate=baseline['DB_transactions_per_observed_second'],candidate_rate=candidate['DB_transactions_per_observed_second'],
            arithmetic_change_percent=change(baseline['DB_transactions_per_observed_second'],candidate['DB_transactions_per_observed_second']),
            frozen_idle_goal_within_observed_scope=(candidate['DB_transactions_per_observed_second']<=baseline['DB_transactions_per_observed_second']*.7) if mode=='off' else None,
            scope='Actual ~118s1000 spans or matched24-point/~46s500 late tails; logical cutoff alignment approximate; not complete120s fixed-event comparisons.'))
flow_comparisons=[]
for count in (100,500,1000):
    a,b,c=[by_native[run,count,True] for run in ('original_87','reference_753','current_9258')]
    flow_comparisons.append(dict(count=count,original_accepted_FE=a['accepted_FE'],reference_753_accepted_FE=b['accepted_FE'],
        current_9258_accepted_FE=c['accepted_FE'],original_output_FE_per_second=a['extracted_FE_per_nominal_second'],
        reference_753_output_FE_per_second=b['extracted_FE_per_nominal_second'],current_9258_output_FE_per_second=c['extracted_FE_per_nominal_second'],
        output_change_original_to_current_percent=change(a['extracted_FE_per_nominal_second'],c['extracted_FE_per_nominal_second']),
        same_input_event_ledger=False,independent_final_residue_or_per_receiver_output_audit=False,capacity_claim=False))

report=dict(schema_version=1,report_kind='offline_87_753_9258_scale_comparison',
    utc_generated=datetime.now(timezone.utc).isoformat(),offline_file_derivation_only=True,sources=sources,source_revisions=REVISIONS,
    source_revision_boundary='9258 measurements predate68f32db; 68 has different class/source manifests and is not measured here. Frozen operator archives/launch identity do not attest class-loader CodeSource.',
    current_operator_provenance=documents['current_conditions'],current_artifact=documents['current_artifact'],
    run_acceptance=dict(original_raw_passed=documents['original_87'].get('passed'),original_scope='Original procedure only; full-window initial counters absent.',
        reference_753_passed=documents['reference_753'].get('passed'),current_9258_passed=documents['current_9258']['passed'],
        current_9258_completed=documents['current_9258']['completed'],current_validation_failures=documents['current_9258']['validation_failures'],
        initial_monitor_passed=documents['initial_failed_monitor']['passed'],replacement_monitor_passed=current['passed']),
    observation_gap=dict(first_monitor_error=documents['initial_failed_monitor']['failures'],restart=documents['observer_restart'],
        current100_OFF='UNMEASURED_BY_SIDECAR',current100_ACTIVE='Only37 late points/~72s; initial reset not seen; not used for a matched full-phase comparison.',
        full_six_business_windows='9258 driver first/final counters retained for all six; do not confuse sidecar gaps with missing driver results.',
        original_full_DB_counter_windows='UNMEASURED: original first_metrics absent; adjacent phase-final cumulative values are not substitutes.'),
    conditions=dict(hardware=documents['current_9258']['hardware'],JVM=documents['current_9258']['jvm'],
        backend=documents['current_9258']['backend'],fixture=documents['current_9258']['fixture'],transfer_flags=documents['current_9258']['transfer_flags'],
        warmup_seconds=5,nominal_seconds=120,repeats=1,Minecraft_JVMs=1,
        original_geometry_scope=previous['conditions']['original_geometry_scope'],
        attempted_input_FE_per_second_if20_ticks=160000,measured_factory_capacity=False),
    method={**{key: deepcopy(value) for key,value in previous['method'].items() if key not in ('e405_selection','untimed_explain')},
        'monitor_windows':'9258 post-reset60 points at500/1000;100 ACTIVE only37 late points without observed reset,100 OFF absent. Baseline100/500 OFF absent;500 ACTIVE only24 late points matched by candidate tails. No interpolation/full120s substitution.',
        'observer_restart':'First bulk-status precedes BULKS initialization; retainbackend_error/exit1. Only parent orchestrator paused; Minecraft and driver uninterrupted. Replacement exits0, observes later phases.',
        'source_labels':'current_9258 is9258a6a, reference_753 is75392af, original_87 is87bf217; primary27ABC4cfff0a and failede405 remain separately archived.'},
    full_nominal_samples=native,observed_windows=windows,observed_rate_comparisons=rate_comparisons,
    nominal_driver_limited_output_comparisons=flow_comparisons,last_ring_comparisons=ring_comparisons,
    all_descriptive_original_to_current_ring_regressions_over10percent=[r for r in ring_comparisons if r['reference']=='original_87' and r['change_percent'] is not None and r['change_percent']>10],
    descriptive_ring_regression_threshold=dict(percent=10,descriptive_only=True,frozen_acceptance_goal=False),
    optimization_all_goals_met_claim=False,historical_failed_e405='Retained without rewriting in reports/optimization-scale-comparison-75392af.json and e405 raw/acceptance reports.')
stem=ROOT/'reports/optimization-scale-comparison-9258a6a'
stem.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
rows=[]
for r in native:
    d=r['counter_delta'];rows.append(dict(record_type='nominal_business_window',run=r['run'],source_revision=r['source_revision'],count=r['count'],active=r['active_requested'],
        seconds=r['seconds_nominal'],DB_transactions=d.get('db_transactions'),DB_transactions_per_second=r.get('DB_transactions_per_nominal_second'),
        accepted_FE=r['accepted_FE'],extracted_FE=r['extracted_FE'],output_FE_per_second=r['extracted_FE_per_nominal_second'],
        errors=r['worker_errors'],queue_rejections=r['queue_rejections'],quarantines=d.get('quarantined'),worker_tasks=d.get('transactions'),
        wal_writes=d.get('wal_writes'),wal_bytes=d.get('wal_bytes'),tick_p95_ms=r['last_metric_ring_snapshot'].get('tick_ms_p95'),
        tick_p99_ms=r['last_metric_ring_snapshot'].get('tick_ms_p99'),source=r['source']['path'],source_sha256=r['source']['sha256']))
for r in windows:
    d=r['counter_delta'];rows.append(dict(record_type='observed_counter_subwindow',run=r['run'],source_revision=r['source_revision'],label=r['label'],
        count=r['bulk_count'],samples=r['samples'],seconds=r['observed_seconds_reply_to_reply'],DB_transactions=d['db_transactions'],
        DB_transactions_per_second=r['DB_transactions_per_observed_second'],errors=d['errors'],queue_rejections=d['queue_rejected'],quarantines=d['quarantined'],
        worker_tasks=d['transactions'],accepted_FE=r['bulk_counter_delta']['accepted'],extracted_FE=r['bulk_counter_delta']['extracted'],
        active_first=r['active_first_last_min_max'][0],active_final=r['active_first_last_min_max'][1],
        active_min=r['active_first_last_min_max'][2],active_max=r['active_first_last_min_max'][3],
        round_first=r['selected_rounds'][0],round_last=r['selected_rounds'][-1],first_utc=r['first_status_request_utc'],last_utc=r['last_status_reply_utc'],
        source=r['source_path'],source_sha256=r['source_sha256']))
rows.extend(dict(record_type='final_ring_comparison',**r) for r in ring_comparisons)
rows.extend(dict(record_type='observed_DB_rate_comparison',**r) for r in rate_comparisons)
with stem.with_suffix('.csv').open('w',newline='') as file:
    writer=csv.DictWriter(file,fieldnames=list(dict.fromkeys(k for row in rows for k in row)));writer.writeheader();writer.writerows(rows)

lines=['# 87bf217 / 75392af / 9258a6a规模证据', '',
    '9258a6a的六个100/500/1000端点OFF/ACTIVE业务窗口已完成，worker error、拒绝、新隔离均为0，首次/末次资格数量符合各自模式。当前程序版本已推进到68f32db；本比较只归入9258的实际产物，不把9258性能结果当作68结果。9258冻结JAR SHA-256为 `'+documents['current_conditions']['jar_sha256']+'`，源码/类文件清单、PID/argv、输入SHA和所有数值见同名JSON/CSV。没有class-loader级来源证明。', '',
    '本次是单个Minecraft JVM，Java21/MC1.21.1/NeoForge21.1.252，真实本机MySQL8.4.7/Redis7.4.6，x30357/z0六个加载区块、最多四个已配置频道、五秒预热、120秒名义稳态、一次重复。原版原始报告未记录坐标，独立核对的相同六区块范围继续保留为条件限制。不是三JVM或真实工厂测试。', '',
    '## 9258旁路监测缺口', '',
    '首监测器在BULKS fixture建立前调用bulk-status，实际返回backend_error并以1退出，失败文件保留。仅编排父进程为重启观察器而暂停，Minecraft和业务驱动没有暂停。替代观察器16:22:35启动、16:32:29停止并退出0；100 OFF和100 ACTIVE早段缺测，只有ACTIVE末37点/约72秒且未观察到该窗口reset。该尾段不会冒称完整120秒或用于完整窗对比。500/1000各模式保留post-reset60点/约118秒，设置与预热前段不纳入这些子窗口。业务驱动的六窗first/final计数仍完整，不能将旁路缺口写成业务窗失败。', '',
    '- 初次失败：[原报告](optimization-scale-fast-scale-cache-9258a6a-20261006T161935Z-d52650.json)。',
    '- 后续替代：[原报告](optimization-scale-fast-scale-cache-ready-9258a6a-20261006T162235Z-a50f0c.json)。',
    '- 父进程暂停/恢复：[记录](optimization-scale-9258a6a-observer-restart.json)。', '',
    '## 名义业务窗口', '',
    'DB计数仅9258/753保存了真实first/final快照；每秒以实际约120秒等待时长为分母，SQL计数快照的请求/回复额外边界保存在JSON。原版缺初值，完整窗DB事务率为未测，禁止相减相邻阶段末累计值。', '',
    '| 端点 | 9258 OFF ΔDB /名义tx/s | 9258 ACTIVE ΔDB /名义tx/s | ACTIVE实际提取FE/s 原版 /753 /9258 |',
    '| --- | --- | --- | --- |']
for count in (100,500,1000):
    off,on=by_native['current_9258',count,False],by_native['current_9258',count,True]
    flows=[by_native[r,count,True]['extracted_FE_per_nominal_second'] for r in ('original_87','reference_753','current_9258')]
    lines.append(f"| {count} | {off['counter_delta']['db_transactions']} / {off['DB_transactions_per_nominal_second']:.6f} | {on['counter_delta']['db_transactions']} / {on['DB_transactions_per_nominal_second']:.6f} | {' / '.join(f'{v:.2f}' for v in flows)} |")
lines += ['', '9258 OFF在三档的worker-task差值均为0。100 ACTIVE输入19,208,000 FE，原版/753为19,200,000；500/1000各版本均为19,200,000。总量一致也不代表逐输入事件、初始缓冲和捕获边界相同。提取可能包含预热/尾段资产；此驱动没有逐收端输出账本、独立最终SQL/local资产排空审核或物理容器保存计时。每Minecraft tick至多16次fixture输入尝试，若运行20ticks/s则名义供给上限160,000 FE/s；固定供给下的输出不是峰值容量或实际TPS测量。', '',
    '## Runtime主线程滚动快照', '',
    'tick_ms是模组RuntimeService.tick最多2048样本的滚动快照，不是完整120秒或整服wall MSPT。百分比是描述性快照变化，单次重复不能证明因果。', '',
    '| ACTIVE端点 | p95 ms 原版 /753 /9258 | 9258相对原版 | 9258相对753 | p99 ms 原版 /753 /9258 |',
    '| --- | --- | --- | --- | --- |']
for count in (100,500,1000):
    rings=[by_native[r,count,True]['last_metric_ring_snapshot'] for r in ('original_87','reference_753','current_9258')]
    p95=[r['tick_ms_p95'] for r in rings];p99=[r['tick_ms_p99'] for r in rings]
    lines.append(f"| {count} | {' / '.join(f'{v:.6f}' for v in p95)} | {change(p95[0],p95[2]):+.2f}% | {change(p95[1],p95[2]):+.2f}% | {' / '.join(f'{v:.6f}' for v in p99)} |")
lines += ['', '9258降低了753的ACTIVE p95，但三档仍高于原版；没有把事务减少或热点采样当成主线程目标通过。所有原版→9258超过10%的tick/delivery/sql三分位回归保留在JSON；delivery是派发到本地credit，sql_ms是整个后台工作而非单条SQL。Minecraft内部avg100记录平均值和目标20不是完整wall MSPT/实际TPS；原版也没有相同native记录字段，不补齐比较。', '',
    '## 实际旁路事务子窗口', '',
    '| 实际窗口 | 原版 ΔDB /秒 /tx/s | 753 ΔDB /秒 /tx/s | 9258 ΔDB /秒 /tx/s | 9258相对原版率变化 |',
    '| --- | --- | --- | --- | --- |']
for count,mode in [(500,'active'),(1000,'off'),(1000,'active')]:
    base='baseline_500_active_late_tail' if count==500 else f'baseline_1000_{mode}_post_reset'
    suffix='500_active_matching_late_24_sample_tail' if count==500 else f'1000_{mode}_post_reset'
    selected=[by_window[base],by_window['reference_753_'+suffix],by_window['current_9258_'+suffix]]
    values=[f"{w['counter_delta']['db_transactions']} / {w['observed_seconds_reply_to_reply']:.6f} / {w['DB_transactions_per_observed_second']:.6f}" for w in selected]
    lines.append(f"| {count} {mode.upper()}{' 24点晚尾' if count==500 else ' 60点'} | {' | '.join(values)} | {change(selected[0]['DB_transactions_per_observed_second'],selected[2]['DB_transactions_per_observed_second']):+.2f}% |")
lines += ['', '1000 OFF降幅仅评价共同约118秒实际子窗口内的30%空闲事务目标；ACTIVE事务降幅不替代先前4cfff0a三服固定业务目标。原版100/500 OFF的旁路与所有完整120秒DB初值仍未测。500 ACTIVE只比较原版现存24点/~46秒晚尾与候选24点晚尾，近似按逻辑尾部匹配，不补首段、插值或跨JVM相减monotonic。', '',
    '| 选定9258子窗口 | rounds | 起点UTC（status请求） | 终点UTC（status回复） | 点数/实际秒 |',
    '| --- | --- | --- | --- | --- |']
for w in windows:
    if w['run']=='current_monitor':
        lines.append(f"| {w['label']} | {w['selected_rounds'][0]}–{w['selected_rounds'][-1]} | {w['first_status_request_utc']} | {w['last_status_reply_utc']} | {w['samples']} / {w['observed_seconds_reply_to_reply']:.6f} |")
lines += ['', '日期均2026-10-06 UTC。秒数以同一观察器status回复到回复计算；counter真实采样时刻位于请求/回复区间内，保守上下界在JSON。端点count/mode由报告资格状态推断，reset由滚动样本数下降观察，不是独立权威模式标记。每段保存所选round、原始输入SHA、计数差与起止边界。已有源码科学记数法解析限制按原753报告保留，历史指数tiny字段不补测。', '',
    'CPU/RSS/堆/GC只从同段内保存的进程与jstat快照派生：CPU涵盖整个JVM，堆含未收集对象，GC GCT含并发阶段而非主线程暂停。没有重新解析JFR、启动新profile、在线查询或运行构建。共享RCON控制台应答没有body nonce的旧限制仍在；未推断任何未经证实的错误body，但也未将协议ID当成body来源证明。', '',
    '旧e405的50/496 worker错误和失败规模证据仍见 [753比较](optimization-scale-comparison-75392af.md)；27次三服计时仍属4cfff0a。9258此次修复的收益属于本次数据；本页不包含68的独立规模结果。']
stem.with_suffix('.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(paths=[str(stem.with_suffix(s)) for s in ('.json','.csv','.md')],
    native_rows=len(native),observed_windows=len(windows),ring_comparisons=len(ring_comparisons),
    current_window_rates={w['label']:w['DB_transactions_per_observed_second'] for w in windows if w['run']=='current_monitor'},
    original_ring_regressions_over10=len(report['all_descriptive_original_to_current_ring_regressions_over10percent'])),ensure_ascii=False))
