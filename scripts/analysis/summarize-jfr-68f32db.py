#!/usr/bin/env python3
"""Fixed archived-dataset recipe for the parsed 68f32db JFR evidence.

Reads already-parsed JFR JSON and the saved scale comparison; looks up selected
source lines in frozen git history. Writes the named summary JSON/Markdown.
Requires the 68f32db comparison. Never opens JFR recordings or invokes Java.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PATHS = {
    'reference_753': 'reports/optimization-jfr-75392af.json',
    'reference_9258': 'reports/optimization-jfr-9258a6a.json',
    'current_68': 'reports/optimization-jfr-68f32db.json',
    'scale_comparison': 'reports/optimization-scale-comparison-68f32db.json',
}
documents,inputs = {},{}
for key,path in PATHS.items():
    data=(ROOT/path).read_bytes()
    assert len(data) <= 8*1024*1024,path
    documents[key]=json.loads(data)
    inputs[key]=dict(path=path,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
current=documents['current_68']
assert current['analysis_executed']
assert current['recordings']['current']['source_revision'] == '68f32db439f445b8f72faf92dc62fbc5b9dce738'
assert current['recordings']['current']['source_revision'] == documents['scale_comparison']['source_revisions']['current_68']

def walk(value):
    if isinstance(value,dict):
        yield value
        for nested in value.values():yield from walk(nested)
    elif isinstance(value,list):
        for nested in value:yield from walk(nested)

def utc_ns(value):
    assert value.endswith('Z'),value
    seconds=datetime.fromisoformat(value[:19]).replace(tzinfo=timezone.utc)
    fraction=value[20:-1] if value[19:20]=='.' else ''
    return int(seconds.timestamp())*1000000000+int((fraction+'000000000')[:9])

validation=dict(four_current_plan_windows_match_reader=True,all_scanned_totals_match_event_counts=True,
    sampling_bucket_totals_match_started_event_counts=True,retained_example_times_inside_selected_windows=True,
    mod_source_labels_match_declared_recording_revision=True,recorded_event_ranges_cover_selected_windows=True,raw_JFR_reopened=False)
for run,recording in current['recordings'].items():
    plan=current['plans'][run]
    assert recording['scanned_events'] == sum(recording['all_recording_event_counts'].values())
    assert recording['monitor_pid_match']
    assert [w['name'] for w in plan['windows']] == [w['name'] for w in recording['windows']] == ['OFF','ACTIVE']
    for p,w in zip(plan['windows'],recording['windows']):
        assert p['start_utc_inclusive'] == w['start_utc'] and p['end_utc_exclusive'] == w['end_utc']
        assert p['inner_utc_seconds'] == w['seconds'] and p['endpoints'] == 1000 and p['monitor_samples'] == 60
        assert utc_ns(recording['event_range_first_utc']) <= utc_ns(w['start_utc']) < utc_ns(w['end_utc']) <= utc_ns(recording['event_range_last_utc'])
        for kind in ('jdk.ExecutionSample','jdk.NativeMethodSample'):
            assert sum(v['samples'] for k,v in w['sampling'].items() if k.startswith(kind+':')) == w['started_event_counts'].get(kind,0)
        for node in walk(w):
            if 'first_sample_utc' in node:
                assert utc_ns(w['start_utc']) <= utc_ns(node['first_sample_utc']) < utc_ns(w['end_utc'])
            if node.get('class','').startswith('dev.crosstesseract.'):
                assert node['source_revision'] == recording['source_revision']
                assert node['source_path'].startswith('src/main/java/dev/crosstesseract/')
                assert '..' not in node['source_path']
for run in ('reference_753','reference_9258'):
    baseline=documents[run]['recordings']['baseline']
    assert baseline['source_revision'] == current['recordings']['baseline']['source_revision']
    assert baseline['input'] == current['recordings']['baseline']['input']
    for old,new in zip(baseline['windows'],current['recordings']['baseline']['windows']):
        assert old['start_utc'] == new['start_utc'] and old['end_utc'] == new['end_utc']
        assert old['sampling']['jdk.ExecutionSample:MAIN']['samples'] == new['sampling']['jdk.ExecutionSample:MAIN']['samples']
validation['historical_comparisons_use_identical_baseline_recording_and_windows']=True

def compact_duration(record):
    return {k:deepcopy(v) for k,v in record.items() if k!='first_recorded_events'}

def compact_window(window):
    out={k:deepcopy(window[k]) for k in ('name','start_utc','end_utc','seconds','started_event_counts',
        'sampled_thread_counts','excluded_cross_boundary_duration_events','periodic_cpu_load_fractions','allocation_sampling','data_loss_events')}
    out['duration_events']={k:compact_duration(v) for k,v in window['duration_events'].items()}
    out['main_execution_sampling']=deepcopy(window['sampling'].get('jdk.ExecutionSample:MAIN',{}))
    out['main_native_sampling']=deepcopy(window['sampling'].get('jdk.NativeMethodSample:MAIN',{}))
    out['main_execution_sampling']['top_stacks']=out['main_execution_sampling'].get('top_stacks',[])[:5]
    out['main_execution_sampling']['top_runtime_tick_stacks']=out['main_execution_sampling'].get('top_runtime_tick_stacks',[])[:8]
    out['main_native_sampling']['top_stacks']=out['main_native_sampling'].get('top_stacks',[])[:2]
    return out

recordings={}
for run,recording in current['recordings'].items():
    plan=current['plans'][run]
    monitor_path=plan['monitor']['path'];data=(ROOT/monitor_path).read_bytes()
    assert len(data) <= 4*1024*1024
    monitor=json.loads(data)
    assert monitor['identity']['pid'] == plan['monitor_identity']['pid']
    recordings[run]=dict(declared_source_revision=recording['source_revision'],
        raw_jfr_evidence_from_reader=recording['input'],raw_jfr_hash_inherited_from_reader_not_rehashed=True,
        reader_source=recording['reader_source'],reader_generated_utc=current['generated_utc'],
        jvm_pid_matches_monitor=recording['monitor_pid_match'],event_range_first_utc=recording['event_range_first_utc'],
        event_range_last_utc=recording['event_range_last_utc'],scanned_events=recording['scanned_events'],
        recorded_data_loss_events=recording['all_recording_event_counts'].get('jdk.DataLoss',0),
        coverage_concerns=recording['coverage_concerns'],observed_active_settings=recording['observed_active_settings'],
        monitor_input=dict(path=monitor_path,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()),
        selected_window_plans=deepcopy(plan['windows']),windows=[compact_window(w) for w in recording['windows']])

# Only lookup selected positive line-table positions in frozen git text. These are
# source lookups, not independent class-loader or artifact-origin attestations.
source_checks=[]
for run,recording in current['recordings'].items():
    selected={}
    for w in recording['windows']:
        m=w['sampling'].get('jdk.ExecutionSample:MAIN',{})
        for stack in m.get('top_runtime_tick_stacks',[])[:5]:
            for frame in stack['frames_leaf_to_root']:
                if frame.get('source_revision') and frame['line']>0 and '$$Lambda' not in frame['class']:
                    selected.setdefault(frame['source_path'],set()).add(frame['line'])
    for path,lines in sorted(selected.items()):
        source=subprocess.run(['git','show',recording['source_revision']+':'+path],cwd=ROOT,check=True,capture_output=True,timeout=3).stdout
        assert len(source)<=256*1024
        texts=source.decode().splitlines()
        assert all(1<=line<=len(texts) for line in lines)
        source_checks.append(dict(recording=run,declared_source_revision=recording['source_revision'],path=path,
            git_source_sha256=hashlib.sha256(source).hexdigest(),
            recorded_lines_checked=[dict(line=line,source_text=texts[line-1]) for line in sorted(lines)],
            scope='Selected actual positive line-table source lookups in declared frozen git revision. Hidden lambda classes/negative lines and class-loader origin are not independently attested.'))

def active_row(label,doc,run):
    record=doc['recordings'][run];w=next(w for w in record['windows'] if w['name']=='ACTIVE')
    main=w['sampling']['jdk.ExecutionSample:MAIN'];native=w['sampling'].get('jdk.NativeMethodSample:MAIN',{})
    wakes=[m for m in main['top_inclusive_methods'] if '.RuntimeService.wakeChannel(' in m['identity']]
    assert len(wakes)<=1
    allocation=w['allocation_sampling'];gc=w['duration_events']['jdk.GCPhasePause:GLOBAL']
    return dict(run=label,declared_source_revision=record['source_revision'],window_seconds=w['seconds'],start_utc=w['start_utc'],end_utc=w['end_utc'],
        main_execution_samples=main['samples'],runtime_tick_inclusive_samples=main['runtime_tick_inclusive_samples'],
        runtime_fraction_of_main_execution_samples=main['runtime_tick_inclusive_samples']/main['samples'],
        wakeChannel_inclusive_samples=wakes[0]['count'] if wakes else None,
        wakeChannel_fraction_of_runtime_samples=wakes[0]['count']/main['runtime_tick_inclusive_samples'] if wakes else None,
        wakeChannel_coverage='Count from retained ranked inclusive method entry; a missing entry is unknown, not zero.',
        main_native_samples=native.get('samples',0),native_runtime_samples=native.get('runtime_tick_inclusive_samples',0),
        runtime_estimated_allocation_weight_bytes=allocation['main_runtime_estimated_weight_bytes'],
        runtime_allocation_sample_events=allocation['main_runtime_sample_events'],
        global_estimated_allocation_weight_bytes=allocation['estimated_weight_bytes'],
        recorded_top_level_gc_pause_events=gc['recorded_events'],recorded_top_level_gc_pause_sum_ms=gc['duration_sum_ms'],recorded_top_level_gc_pause_max_ms=gc['max_ms'],
        comparisons_descriptive_not_causal=True)
rows=[active_row('original_87',current,'baseline'),active_row('reference_753',documents['reference_753'],'current'),
    active_row('reference_9258',documents['reference_9258'],'current'),active_row('current_68',current,'current')]
def change(old,new):return (new/old-1)*100 if old else None
active_changes={field:change(rows[0][field],rows[-1][field]) for field in ('runtime_estimated_allocation_weight_bytes','global_estimated_allocation_weight_bytes','recorded_top_level_gc_pause_sum_ms')}
report=dict(schema_version=1,report_kind='parsed_JFR_only_68f32db_summary',derived_from_parsed_json_only=True,
    generated_utc=datetime.now(timezone.utc).isoformat(),inputs=inputs,reader_generated_utc=current['generated_utc'],
    limitations=current['limitations'],validation=validation,recordings=recordings,source_checks=source_checks,
    historical_active_sampling_comparison=rows,descriptive_active_change_original_to_current_percent=active_changes,
    main_p95_causal_attribution_established=False,full_wall_MSPT_or_actual_TPS_measured=False)
stem=ROOT/'reports/optimization-jfr-68f32db'
stem.with_name(stem.name+'-summary').with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

lines=['# 68f32db JFR离线采样证据','',
    '仅从已经解析的JSON生成本摘要，没有重新打开JFR或运行JDK。68的ACTIVE窗口主线程执行样本169个、含Runtime.tick的样本72个、含wakeChannel的样本35个；753/9258相应观察数更高，但这些采样计数不能换算CPU毫秒或认定为主线程p95变化的因果解释。', '',
    '主输入 [已解析JSON](optimization-jfr-68f32db.json)，执行解析时间 `'+current['generated_utc']+'`；其SHA-256为 `'+inputs['current_68']['sha256']+'`。四窗口、事件统计、实际栈、冻结源码行、历史解析输入SHA见 [摘要JSON](optimization-jfr-68f32db-summary.json)。原始JFR的文件摘要仅继承读取器证据，本次没有重读原始文件。', '',
    '## 时钟与四个实际窗口','',
    '只选择1000端点reset后60点的保守内区间：[首status回复结束，末status请求开始)。每段约118秒，不是名义120秒。JFR Instant与同机观察器UTC对齐；没有相减跨JVM单调钟、插值或将建立/预热混入。记录中的JVM PID均与监测器一致，所选四窗覆盖完整，没有记录DataLoss事件；这不证明每次执行或每次分配都被采到。','',
    '| 来源/模式 | 真实UTC区间（2026-10-06） | 内区间秒 | 全线程Execution / Native事件 | 主线程Execution / Runtime样本 |',
    '| --- | --- | --- | --- | --- |']
for run,recording in current['recordings'].items():
    for w in recording['windows']:
        m=w['sampling'].get('jdk.ExecutionSample:MAIN',{})
        events=w['started_event_counts']
        lines.append(f"| {'原版87' if run=='baseline' else '68'} {w['name']} | {w['start_utc']}–{w['end_utc']} | {w['seconds']:.6f} | {events.get('jdk.ExecutionSample',0)} / {events.get('jdk.NativeMethodSample',0)} | {m.get('samples',0)} / {m.get('runtime_tick_inclusive_samples',0)} |")
lines += ['', 'ExecutionSample、NativeMethodSample分别统计；当前主线程Native样本90/116均在Thread.yield0路径且无Runtime.tick栈，不能与执行样本合并成Runtime耗时。当前OFF仅27个Runtime样本，稳定热点排序或p95归因证据不足。设置是全记录观察值：执行采样10ms、native20ms、分配节流300/s；采样时长/事件阈值不能用于反推精确CPU耗时。', '',
    '## 1000 ACTIVE历史采样比较','',
    '| 冻结来源 | MAIN Execution | Runtime inclusive /MAIN | wakeChannel inclusive /Runtime | Runtime分配权重MiB（事件） | 全JVM分配权重MiB | 顶层GC暂停次数 /总ms /最大ms |',
    '| --- | --- | --- | --- | --- | --- | --- |']
for r in rows:
    wake='—' if r['wakeChannel_inclusive_samples'] is None else f"{r['wakeChannel_inclusive_samples']} / {r['wakeChannel_fraction_of_runtime_samples']*100:.2f}%"
    lines.append(f"| {r['declared_source_revision'][:7]} | {r['main_execution_samples']} | {r['runtime_tick_inclusive_samples']} / {r['runtime_fraction_of_main_execution_samples']*100:.2f}% | {wake} | {r['runtime_estimated_allocation_weight_bytes']/1048576:.2f} ({r['runtime_allocation_sample_events']}) | {r['global_estimated_allocation_weight_bytes']/1048576:.2f} | {r['recorded_top_level_gc_pause_events']} / {r['recorded_top_level_gc_pause_sum_ms']:.6f} / {r['recorded_top_level_gc_pause_max_ms']:.6f} |")
lines += ['', 'inclusive方法计数彼此可重叠，不能相加；wake计数来自保存的排名项，未出现的项不补为零。分配weight是JFR统计估计，不是精确bytes/对象数、保留堆或某方法独占分配。68 Runtime ACTIVE估计权重相对原版 '+f"{active_changes['runtime_estimated_allocation_weight_bytes']:+.2f}%"+'，全JVM '+f"{active_changes['global_estimated_allocation_weight_bytes']:+.2f}%"+'；样本数量和权重会有抽样变化，不能据此认定资产路径或CPU成本降低了相同比例。', '',
    '## 实际保存的68调用栈','',
    '当前ACTIVE最常见Runtime栈之一为 `ConcurrentHashMap.get → RuntimeService.wakeChannel:298 → tick:327`（9样本）；直接leaf在wakeChannel:299的一栈4样本；`HashMap.getNode → ChannelCoordinator.hasPendingSignal:63 → wakeChannel:302 → tick:328`的一栈3样本。这些栈支持剩余探测包含端点lookup、状态判定和已有ready信号查询；没有证明某个方法独占全部开销。', '',
    '当前MAIN含Runtime栈的leaf中，ConcurrentHashMap.get14、HashMap.getNode12、wakeChannel9、HashMap.getOrDefault6样本。MAIN整体leaf仍包含ChunkHolder.getTickingChunk41、ChunkMap.processUnloads15，不能把主线程全栈活动归到模组。回调派发lambda$submit$10的inclusive排名13样本也保留；没有把所有lookup或回调都自动归到wakeChannel。', '',
    '所列方法/行均按冻结 `68f32db` 的记录line table和git文本核对，具体源码摘要/行文本见summary的source_checks。历史栈仅对应各自87/753/9258冻结源；隐藏lambda类与负行号不当作独立声明行。启动归档、源码/类摘要和PID不是class-loader CodeSource证明。', '',
    '## GC与归因边界','',
    '68 ACTIVE顶层GC暂停42次、总138.914355ms、最大7.861690ms；原版35次、总90.085517ms、最大6.997081ms。这里仅累加同一顶层GCPhasePause事件，不相加嵌套阶段。GarbageCollection总2977.388473ms包含并发生命周期，不能称为主线程暂停；边界跨越的duration事件已排除。OFF顶层暂停8.848002ms对原版10.357265ms，样本少，不能当作稳定GC优化。', '',
    '记录显示采样栈分布、分配权重和GC活动不同，但没有每tick时间与样本/GC对齐的因果数据。规模报告中68主线程p95仍相对原版升38.42%/36.56%/102.46%；本JFR不把采样减少解释成精确p95收益，也不能断言GC造成或解释该回归。已有Runtime滚动分位和Minecraft记录工作平均都不是完整wall MSPT/实际TPS；一次固定供给、单JVM和一次重复不证明工厂容量或三服性能。', '',
    '9258的首100旁路监测缺口和原版完整窗DB初值缺失仍保留在 [四版本规模比较](optimization-scale-comparison-68f32db.md)，不影响本页仅选双方都有真实记录的1000 OFF/ACTIVE内区间。没有在线SQL/RCON、运行MC、修改Java或增加现场负载。']
stem.with_suffix('.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(paths=[str(stem.with_name(stem.name+'-summary').with_suffix('.json')),str(stem.with_suffix('.md'))],
    validation=validation,source_files_checked=len(source_checks),active_rows=rows),ensure_ascii=False))
