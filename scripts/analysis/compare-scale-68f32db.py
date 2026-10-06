#!/usr/bin/env python3
"""Fixed archived-dataset recipe for 87bf217/75392af/9258a6a/68f32db.

Reads saved local JSON, verifies archived input hashes, and writes the named
68f32db comparison JSON/CSV/Markdown. Run the 9258a6a recipe first if rebuilding
all derivatives. This performs no live collection or JDK work.
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
PATHS = {
    'prior_9258_comparison': 'reports/optimization-scale-comparison-9258a6a.json',
    'current_68': 'reports/performance-opt-fast-68f32db.json',
    'current_monitor': 'reports/optimization-scale-fast-scale-verified-68f32db-20261006T164948Z-78f406.json',
    'current_conditions': 'reports/optimization-conditions-fast-scale-verified-68f32db.json',
    'current_artifact': 'reports/optimization-artifact-ready-final.json',
}
REVISION = '68f32db439f445b8f72faf92dc62fbc5b9dce738'
COUNTERS = ('db_transactions', 'db_transaction_attempts', 'db_statements', 'db_deadlock_retries',
    'transactions', 'errors', 'queue_rejected', 'quarantined', 'batch_devices', 'batch_records',
    'batch_payload_bytes', 'local_input_units', 'local_output_units', 'wal_writes', 'wal_bytes',
    'wal_identical_skipped')
RING_KEYS = tuple(f'{kind}_ms_{q}' for kind in ('tick','delivery','sql') for q in ('p50','p95','p99','samples'))
GC_KEYS = ('YGC','YGCT','FGC','FGCT','CGC','CGCT','GCT')
documents, sources = {}, {}

def read_source(relative):
    data = (ROOT / relative).read_bytes()
    assert len(data) <= 4 * 1024 * 1024, relative
    return json.loads(data), dict(path=relative, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

for key, path in PATHS.items():
    documents[key], sources[key] = read_source(path)
previous = documents['prior_9258_comparison']
for key, archived in previous['sources'].items():
    _, verified = read_source(archived['path'])
    assert verified == archived, key
    sources['prior_' + key] = archived
conditions, artifact = documents['current_conditions'], documents['current_artifact']
current, monitor = documents['current_68'], documents['current_monitor']
assert conditions['source_commit'] == artifact['source_revision'] == REVISION
assert conditions['java_source_tree_sha256'] == artifact['source_manifest_sha256']
assert conditions['jar_sha256'] in [a['sha256'] for a in artifact['artifacts'] if a['path'].endswith('-dev.jar')]
assert conditions['selected_launch']['pid'] == monitor['identity']['pid']
assert conditions['selected_launch']['argv_sha256'] == monitor['identity']['argv_sha256']
assert conditions['monitor_report'] == PATHS['current_monitor']
assert current['passed'] and current['completed'] and not current['validation_failures']
assert monitor['passed'] and not monitor['failures']
assert conditions['benchmark_exit_code'] == conditions['monitor_exit_code'] == 0
assert not conditions['remaining_jvm_pids']

def delta(first, last, keys):
    values = {key: last[key] - first[key] if key in first and key in last else None for key in keys}
    assert all(value is None or value >= 0 for value in values.values()), values
    return values

def change(old, new):
    return (new / old - 1) * 100 if old is not None and new is not None and old > 0 else None

native = deepcopy(previous['full_nominal_samples'])
windows = deepcopy(previous['observed_windows'])
for row in native:
    if row['run'] == 'current_9258': row['run'] = 'reference_9258'
for row in windows:
    if row['run'] == 'current_monitor':
        row['run'] = 'reference_9258_monitor'
        row['label'] = row['label'].replace('current_9258_', 'reference_9258_', 1)

def window(rounds, name, meaning):
    selected = [monitor['samples'][n] for n in rounds]
    assert [s['round'] for s in selected] == list(rounds)
    assert list(rounds) == list(range(rounds[0], rounds[-1] + 1))
    first, last = selected[0], selected[-1]
    fs, ls = first['status'], last['status']
    count = first['bulk']['metrics']['count']
    assert all(s['bulk']['metrics']['count'] == count for s in selected)
    elapsed = ls['observer_end'] - fs['observer_end']
    low, high = ls['observer_start'] - fs['observer_end'], ls['observer_end'] - fs['observer_start']
    assert 0 < low <= elapsed <= high
    counters = delta(fs['metrics'], ls['metrics'], COUNTERS)
    bulk = delta(first['bulk']['metrics'], last['bulk']['metrics'], ('accepted','extracted','fixture_ms_total','fixture_ticks'))
    active = [s['status']['metrics']['active_endpoints'] for s in selected]
    cpu_delta = last['proc']['cpu_total_seconds'] - first['proc']['cpu_total_seconds']
    cpu_time = last['observer_start'] - first['observer_start']
    cpu_low, cpu_high = last['observer_start'] - first['observer_end'], last['observer_end'] - first['observer_start']
    assert cpu_delta >= 0 and 0 < cpu_low <= cpu_time <= cpu_high
    gc = [s for s in selected if s.get('jstat_gc',{}).get('values') and not s['jstat_gc'].get('error')
        and s['jstat_gc']['observer_start'] >= fs['observer_start'] and s['jstat_gc']['observer_end'] <= ls['observer_end']]
    heap = [s['heap']['heap_used_bytes']/1048576 for s in gc if s.get('heap',{}).get('heap_used_bytes') is not None]
    return dict(label=name, run='current_monitor', source_revision=REVISION,
        source_path=PATHS['current_monitor'], source_sha256=sources['current_monitor']['sha256'],
        meaning=meaning, steady_candidate=True, selected_rounds=list(rounds),
        observed_phase_ids=sorted({s['observed_phase_id'] for s in selected}),
        observed_mode_counts=dict(Counter(s['observed_mode'] for s in selected)), bulk_count=count,
        samples=len(selected), first_reset_observed=first.get('window_reset_observed',False),
        first_status_request_utc=fs['utc_request_start'], first_status_reply_utc=fs['utc_reply_end'],
        last_status_request_utc=ls['utc_request_start'], last_status_reply_utc=ls['utc_reply_end'],
        observer_interval=dict(first_status_request=fs['observer_start'],first_status_reply=fs['observer_end'],
            last_status_request=ls['observer_start'],last_status_reply=ls['observer_end']),
        observed_seconds_reply_to_reply=elapsed,time_seconds_bounds=dict(lower=low,upper=high),
        counter_delta=counters,DB_transactions_per_observed_second=counters['db_transactions']/elapsed,
        DB_transactions_per_capture_second_bounds=dict(lower=counters['db_transactions']/high,upper=counters['db_transactions']/low),
        bulk_counter_delta=bulk,extracted_FE_per_observed_second=bulk['extracted']/elapsed,
        active_first_last_min_max=[active[0],active[-1],min(active),max(active)],
        samples_matching_full_active_count=sum(v == count for v in active),samples_matching_zero_active=sum(v == 0 for v in active),
        zero_worker_activity=counters['transactions'] == 0,
        observed_worker_error_free=all(counters[k] == 0 for k in ('errors','queue_rejected','quarantined')),
        coverage='Actual selected counter spans only; sequential status/bulk snapshots, approximate logical phase matching; no interpolation.',
        cpu=dict(delta_seconds=cpu_delta,elapsed_sample_start_seconds=cpu_time,process_percent_nominal=cpu_delta/cpu_time*100,
            elapsed_seconds_conservative_bounds=dict(lower=cpu_low,upper=cpu_high),
            process_percent_bounds=dict(lower=cpu_delta/cpu_high*100,upper=cpu_delta/cpu_low*100),
            scope='All JVM threads; one logical CPU=100%; coarse process read bounds, not Runtime/main-thread CPU.'),
        rss_MiB=dict(sample_mean=statistics.mean(s['proc']['rss_bytes']/1048576 for s in selected),sample_max=max(s['proc']['rss_bytes']/1048576 for s in selected)),
        heap_gc=dict(samples=len(gc),selected_rounds=[s['round'] for s in gc],
            first_observer_request=gc[0]['jstat_gc']['observer_start'] if gc else None,
            last_observer_reply=gc[-1]['jstat_gc']['observer_end'] if gc else None,
            heap_used_MiB_sample_mean=statistics.mean(heap) if heap else None,heap_used_MiB_sample_max=max(heap) if heap else None,
            GC_counter_delta=delta(gc[0]['jstat_gc']['values'],gc[-1]['jstat_gc']['values'],GC_KEYS) if len(gc)>1 else None,
            coverage='Contained jstat observations only; point heap not live allocation; GCT includes concurrent work and is not STW pause.'))

for phase,count,mode in [(2,100,'off'),(4,100,'active'),(7,500,'off'),(9,500,'active'),(12,1000,'off'),(14,1000,'active')]:
    rounds = [s['round'] for s in monitor['samples'] if s['observed_phase_id'] == phase]
    assert len(rounds) == 60
    w = window(rounds,f'current_68_{count}_{mode}_post_reset','Observed post-reset sixty points; setup/warmup excluded, logical phase boundaries remain approximate.')
    assert w['bulk_count'] == count and w['first_reset_observed']
    assert w['observed_mode_counts'] == {mode.upper() + '_observed':60}
    assert w['observed_worker_error_free']
    windows.append(w)
    if count == 500 and mode == 'active':
        windows.append(window(rounds[-24:],'current_68_500_active_matching_late_24_sample_tail',
            'Last24 post-reset points approximately matched to original500 ACTIVE late tail, not a complete phase.'))
for scenario in current['scenarios']:
    for sample in scenario['samples']:
        fm,lm = sample['first_metrics'],sample['metrics']
        count,active = scenario['count'],scenario['count'] if sample['active'] else 0
        counters = delta(fm,lm,COUNTERS)
        assert counters['db_transactions'] == sample['DB_transactions_window']
        checks = dict(first_loaded=fm['registered_loaded_endpoints'] == count,last_loaded=sample['loaded_endpoints'] == count,
            last_registered=sample['registered_endpoints'] == count,first_active=fm['active_endpoints'] == active,
            last_active=sample['active_endpoints'] == active,worker_error_free=sample['worker_errors'] == 0,
            rejection_free=sample['queue_rejections'] == 0,quarantine_free=counters['quarantined'] == 0)
        assert all(checks.values()),checks
        native.append(dict(run='current_68',source_revision=REVISION,source=sources['current_68'],count=count,active_requested=sample['active'],
            seconds_nominal=sample['seconds'],channel_distribution=scenario['channel_distribution'],registered_final=sample['registered_endpoints'],
            loaded_final=sample['loaded_endpoints'],active_first=fm['active_endpoints'],active_final=sample['active_endpoints'],
            accepted_FE=sample['accepted_FE'],extracted_FE=sample['extracted_FE'],extracted_FE_per_nominal_second=sample['extracted_FE_per_second'],
            worker_transactions_per_nominal_second=sample['worker_transactions_per_second'],worker_errors=sample['worker_errors'],
            queue_rejections=sample['queue_rejections'],fixture_ms_per_tick=sample['fixture_ms_per_tick'],counter_delta=counters,
            DB_transactions_per_nominal_second=sample['DB_transactions_per_second'],counter_capture_seconds_bounds=sample['counter_capture_seconds_bounds'],
            DB_transactions_per_capture_second_bounds=sample['DB_transactions_per_capture_second_bounds'],
            observed_snapshot_checks_passed=True,observed_snapshot_checks=checks,full_window_DB_state='CAPTURED_FIRST_LAST_COUNTERS_WITH_BOUNDS',
            counter_snapshots=dict(first=fm,last=lm),last_metric_ring_snapshot={k:lm.get(k) for k in RING_KEYS},
            native_recorded_tick_avg100_snapshot_ms=lm.get('mc_recorded_tick_ms_avg100'),native_target_ticks_per_second=lm.get('mc_target_ticks_per_second')))
by_native = {(r['run'],r['count'],r['active_requested']):r for r in native}
by_window = {w['label']:w for w in windows}
reference_runs = ('original_87','reference_753','reference_9258')
ring_comparisons,full_DB_comparisons,rate_comparisons,flow_comparisons = [],[],[],[]
for reference in reference_runs:
    for count in (100,500,1000):
        for active in (False,True):
            old,new = by_native[reference,count,active],by_native['current_68',count,active]
            for metric in RING_KEYS:
                if metric.endswith('_samples'):continue
                a,b = old['last_metric_ring_snapshot'].get(metric),new['last_metric_ring_snapshot'].get(metric)
                ring_comparisons.append(dict(reference=reference,current='current_68',count=count,active_requested=active,metric=metric,
                    reference_ms=a,current_ms=b,change_percent=change(a,b),
                    scope='Descriptive final bounded-ring snapshots, not complete120s/time-aligned percentiles or causal effects.'))
            if reference != 'original_87':
                a,b = old['counter_delta']['db_transactions'],new['counter_delta']['db_transactions']
                ar,br = old['DB_transactions_per_nominal_second'],new['DB_transactions_per_nominal_second']
                full_DB_comparisons.append(dict(reference=reference,current='current_68',count=count,active_requested=active,
                    reference_transactions=a,current_transactions=b,count_change_percent=change(a,b),reference_nominal_rate=ar,current_nominal_rate=br,
                    nominal_rate_change_percent=change(ar,br),scope='Captured first/final business-window counters and nominal elapsed seconds; capture-time bounds retained per row.'))
for count,mode in [(500,'active'),(1000,'off'),(1000,'active')]:
    baseline = by_window['baseline_500_active_late_tail' if count == 500 else f'baseline_1000_{mode}_post_reset']
    suffix = '500_active_matching_late_24_sample_tail' if count == 500 else f'1000_{mode}_post_reset'
    for prefix in ('reference_753_','reference_9258_','current_68_'):
        candidate = by_window[prefix + suffix]
        a,b = baseline['DB_transactions_per_observed_second'],candidate['DB_transactions_per_observed_second']
        rate_comparisons.append(dict(reference_window=baseline['label'],candidate_window=candidate['label'],reference_rate=a,candidate_rate=b,
            arithmetic_change_percent=change(a,b),frozen_idle_goal_within_observed_scope=b <= a*.7 if mode == 'off' else None,
            scope='Actual ~118s1000 spans or matched24-point/~46s500 late tails; logical alignment approximate, not complete120s fixed-event comparisons.'))
for count in (100,500,1000):
    rows = [by_native[r,count,True] for r in (*reference_runs,'current_68')]
    flow_comparisons.append(dict(count=count,accepted_FE_by_source={r['run']:r['accepted_FE'] for r in rows},
        output_FE_per_nominal_second_by_source={r['run']:r['extracted_FE_per_nominal_second'] for r in rows},
        same_input_event_ledger=False,independent_final_residue_or_per_receiver_output_audit=False,capacity_claim=False))
method = deepcopy(previous['method'])
method.update(monitor_windows='68 all six post-reset60-point/~118s spans. Retain925100 missingOFF/earlyACTIVE and original100/500OFF gaps;500ACTIVE only original24-point late tail, no interpolation.',
    observer_restart='Historical925 only;68 observer startup uses one-time file signal from existing bulk registration poll before first warmup; no925 failure reassigned to68.',
    source_labels='original_87=87bf217;reference_753=75392af;reference_9258=9258a6a;current_68=68f32db. Primary27ABC4cfff0a and failede405 remain separate.')
report = dict(schema_version=1,report_kind='offline_87_753_9258_68_scale_comparison',utc_generated=datetime.now(timezone.utc).isoformat(),
    offline_file_derivation_only=True,sources=sources,
    source_revisions={**{k.replace('current_9258','reference_9258'):v for k,v in previous['source_revisions'].items()},'current_68':REVISION},
    source_revision_boundary='Each run retains its frozen artifact revision. Archived source/class manifests, PID/argv identities are not class-loader CodeSource attestations.',
    current_operator_provenance=conditions,current_artifact=artifact,
    historical_run_acceptance=previous['run_acceptance'],current_run_acceptance=dict(passed=current['passed'],completed=current['completed'],
        validation_failures=current['validation_failures'],monitor_passed=monitor['passed'],monitor_failures=monitor['failures']),
    historical_9258_observation_gap=previous['observation_gap'],
    current_observation_coverage=dict(startup_signal=conditions['monitor_startup_signal'],all_six_post_reset_windows_observed=True,
        earlier_setup='Not substituted for business windows; collection begins after initial registration.',original_full_DB_windows='UNMEASURED: original first_metrics absent.'),
    conditions={**deepcopy(previous['conditions']),'hardware':current['hardware'],'JVM':current['jvm'],'backend':current['backend'],
        'fixture':current['fixture'],'transfer_flags':current['transfer_flags']},method=method,
    full_nominal_samples=native,observed_windows=windows,observed_rate_comparisons=rate_comparisons,
    captured_full_window_DB_comparisons=full_DB_comparisons,nominal_driver_limited_output_comparisons=flow_comparisons,
    last_ring_comparisons=ring_comparisons,
    descriptive_ring_regression_threshold=dict(percent=10,descriptive_only=True,frozen_acceptance_goal=False),
    all_descriptive_original_to_current_ring_regressions_over10percent=[r for r in ring_comparisons if r['reference']=='original_87' and r['change_percent'] is not None and r['change_percent'] > 10],
    optimization_all_goals_met_claim=False,historical_failed_e405=previous['historical_failed_e405'])
stem = ROOT/'reports/optimization-scale-comparison-68f32db'
stem.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
csv_rows = []
for r in native:
    csv_rows.append(dict(record_type='nominal_business_window',run=r['run'],source_revision=r['source_revision'],count=r['count'],active=r['active_requested'],
        seconds=r['seconds_nominal'],DB_transactions=r['counter_delta'].get('db_transactions'),DB_transactions_per_second=r.get('DB_transactions_per_nominal_second'),
        accepted_FE=r['accepted_FE'],extracted_FE=r['extracted_FE'],output_FE_per_second=r['extracted_FE_per_nominal_second'],
        tick_ms_p95=r['last_metric_ring_snapshot'].get('tick_ms_p95'),tick_ms_p99=r['last_metric_ring_snapshot'].get('tick_ms_p99')))
for w in windows:
    csv_rows.append(dict(record_type='observed_sidecar_window',run=w['run'],source_revision=w['source_revision'],label=w['label'],count=w['bulk_count'],
        seconds=w['observed_seconds_reply_to_reply'],DB_transactions=w['counter_delta']['db_transactions'],DB_transactions_per_second=w['DB_transactions_per_observed_second'],
        steady_candidate=w['steady_candidate'],first_status_request_utc=w['first_status_request_utc'],last_status_reply_utc=w['last_status_reply_utc']))
for r in ring_comparisons:csv_rows.append(dict(record_type='descriptive_last_ring_comparison',**r))
for r in full_DB_comparisons:csv_rows.append(dict(record_type='captured_full_business_window_DB_comparison',**r))
for r in rate_comparisons:csv_rows.append(dict(record_type='observed_DB_rate_comparison',**r))
with stem.with_suffix('.csv').open('w',newline='') as file:
    writer=csv.DictWriter(file,fieldnames=list(dict.fromkeys(k for row in csv_rows for k in row)))
    writer.writeheader();writer.writerows(csv_rows)

lines = ['# 87bf217 / 75392af / 9258a6a / 68f32db规模证据','',
    '68f32db六个业务窗和监测器均实际完成、通过验收并退出0，Minecraft正常停机。worker error、拒绝、新隔离和死锁重试差值为0。ACTIVE主线程p95仍高于原版，本报告不宣称全部性能目标通过。', '',
    '本次单Minecraft JVM，真实MySQL8.4.7/Redis7.4.6，Java21/MC1.21.1/NeoForge21.1.252；x30357/z0/y64六加载区块、100/500/1000端点、最多四频道各上限256、五秒预热、120秒名义业务窗口、各一次重复。固定fixture输入不测真实工厂峰值容量。原版原报告缺坐标、完整窗first_metrics和native平均字段，独立核对的相同六区块范围仍是条件限制。', '',
    '68源码为 `'+REVISION+'`，模组JAR SHA-256为 `'+conditions['jar_sha256']+'`；输入SHA、冻结清单、PID/argv、所有数值和起止界限保存在同名JSON/CSV。没有class-loader级来源证明。历史27次三服计时仍属4cfff0a，e405失败/worker错误证据不改写为当前通过。', '',
    '## Runtime主线程滚动快照','',
    'tick_ms是RuntimeService.tick最多2048样本滚动快照，非完整120秒分位、整服wall MSPT或实际TPS；百分比仅描述单次快照变化，不是因果效应。', '',
    '| ACTIVE端点 | p95 ms 原版 /753 /9258 /68 | 68相对原版 | 68相对753 | 68相对9258 |',
    '| --- | --- | --- | --- | --- |']
for count in (100,500,1000):
    rings=[by_native[r,count,True]['last_metric_ring_snapshot'] for r in (*reference_runs,'current_68')]
    p=[r['tick_ms_p95'] for r in rings]
    lines.append(f"| {count} | {' / '.join(f'{v:.6f}' for v in p)} | {change(p[0],p[3]):+.2f}% | {change(p[1],p[3]):+.2f}% | {change(p[2],p[3]):+.2f}% |")
lines += ['', '| ACTIVE端点 | p99 ms 原版 /753 /9258 /68 |','| --- | --- |']
for count in (100,500,1000):
    p=[by_native[r,count,True]['last_metric_ring_snapshot']['tick_ms_p99'] for r in (*reference_runs,'current_68')]
    lines.append(f"| {count} | {' / '.join(f'{v:.6f}' for v in p)} |")
lines += ['', '三个规模的ACTIVE p95相对原版仍超过10%描述性提示阈值，表明主线程开销仍有回归风险；该阈值不是冻结的性能验收目标。原版→68的tick/delivery/sql各p50/p95/p99所有超过10%描述性回归见JSON。delivery是派发到本地credit，sql_ms是整个后台工作；Minecraft avg100是内部记录平均工作时间，目标20不是实测TPS，不能代替完整wall MSPT。', '',
    '## 捕获首末计数的完整名义业务窗','',
    '完整窗事务仅753/9258/68可相减。原版缺初值，禁止相减相邻阶段末累计值补数。下表是实际first/final DB成功事务数；名义每秒及计数快照请求/回复时间上下界另存JSON。','',
    '| 端点 | OFF ΔDB 753 /9258 /68 | ACTIVE ΔDB 753 /9258 /68 | 68 ACTIVE相对753计数 | 提取FE/s 原版 /753 /9258 /68 |',
    '| --- | --- | --- | --- | --- |']
for count in (100,500,1000):
    off=[by_native[r,count,False]['counter_delta']['db_transactions'] for r in ('reference_753','reference_9258','current_68')]
    active=[by_native[r,count,True]['counter_delta']['db_transactions'] for r in ('reference_753','reference_9258','current_68')]
    flow=[by_native[r,count,True]['extracted_FE_per_nominal_second'] for r in (*reference_runs,'current_68')]
    lines.append(f"| {count} | {' / '.join(str(v) for v in off)} | {' / '.join(str(v) for v in active)} | {change(active[0],active[2]):+.2f}% | {' / '.join(f'{v:.2f}' for v in flow)} |")
lines += ['', '1000 ACTIVE的9970对753的9662增加3.19%，对9258的9915也增加0.55%，没有用原版事务率大幅降低来隐藏后续版本增加。68 OFF三个规模worker-task差值均为0。ACTIVE输入68三档各19,200,000 FE；9258的100档为19,208,000，其他版本/规模均19,200,000。逐输入事件、初始缓冲和快照边界不等同；提取可包含预热/尾段资产。没有逐收端输出账本、独立最终SQL/local资产排空或物理容器保存计时。', '',
    '## 真实旁路事务子窗口','',
    '| 实际窗口 | 原版 ΔDB /秒 /tx/s | 753 ΔDB /秒 /tx/s | 9258 ΔDB /秒 /tx/s | 68 ΔDB /秒 /tx/s | 68相对原版率变化 |',
    '| --- | --- | --- | --- | --- | --- |']
for count,mode in [(500,'active'),(1000,'off'),(1000,'active')]:
    base='baseline_500_active_late_tail' if count == 500 else f'baseline_1000_{mode}_post_reset'
    suffix='500_active_matching_late_24_sample_tail' if count == 500 else f'1000_{mode}_post_reset'
    selected=[by_window[base]]+[by_window[prefix+suffix] for prefix in ('reference_753_','reference_9258_','current_68_')]
    values=[f"{w['counter_delta']['db_transactions']} / {w['observed_seconds_reply_to_reply']:.6f} / {w['DB_transactions_per_observed_second']:.6f}" for w in selected]
    lines.append(f"| {count} {mode.upper()}{' 24点晚尾' if count == 500 else ' 60点'} | {' | '.join(values)} | {change(selected[0]['DB_transactions_per_observed_second'],selected[-1]['DB_transactions_per_observed_second']):+.2f}% |")
lines += ['', '1000 OFF空闲事务目标只按共同~118秒实际子窗口评价；ACTIVE事务减少不替代4cfff0a三服固定业务目标。500 ACTIVE原版仅24点/~46秒晚尾，候选仅按逻辑晚尾近似匹配。原版100/500 OFF旁路未测。没有跨JVM相减monotonic、插值或将子窗口当完整120秒。', '',
    '## 监测边界与历史缺失','',
    '68监测器由既有bulk注册轮询产生的一次文件信号在首段预热前启动；六窗均观察到reset后的60点/~118秒，不将建立/预热点混入。9258首monitor仍是backend_error/exit1，替代monitor仅留下100 ACTIVE末37点/~72秒且未见reset，100 OFF/ACTIVE首段继续缺测；未修补或将历史失败归到68。详见 [9258比较](optimization-scale-comparison-9258a6a.md)。','',
    '| 68子窗口 | rounds | 起点UTC（status请求） | 终点UTC（status回复） | 点数/回复至回复秒 |',
    '| --- | --- | --- | --- | --- |']
for w in windows:
    if w['run']=='current_monitor':
        lines.append(f"| {w['label']} | {w['selected_rounds'][0]}–{w['selected_rounds'][-1]} | {w['first_status_request_utc']} | {w['last_status_reply_utc']} | {w['samples']} / {w['observed_seconds_reply_to_reply']:.6f} |")
lines += ['', '日期均2026-10-06 UTC，持续时间用同一观察器单调钟status回复至回复；真实counter采样在请求/回复区间内，保守界限另存JSON。count/mode依据资格状态推断，reset由滚动样本数下降观察；不是独立模式权威标记。CPU涵盖整个JVM，RSS/堆是点值，jstat GCT含并发阶段，不等于主线程暂停。历史科学记数法tiny字段与共享RCON应答无body nonce的限制继续保留。没有重解析JFR、启动profile、在线查询或构建。']
stem.with_suffix('.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(paths=[str(stem.with_suffix(s)) for s in ('.json','.csv','.md')],native_rows=len(native),observed_windows=len(windows),
    ring_comparisons=len(ring_comparisons),current_1000_DB=by_native['current_68',1000,True]['counter_delta']['db_transactions'],
    full_DB_increase_vs753_percent=change(by_native['reference_753',1000,True]['counter_delta']['db_transactions'],by_native['current_68',1000,True]['counter_delta']['db_transactions']),
    current_observed_rates={w['label']:w['DB_transactions_per_observed_second'] for w in windows if w['run']=='current_monitor'},
    original_ring_regressions_over10=len(report['all_descriptive_original_to_current_ring_regressions_over10percent'])),ensure_ascii=False))
