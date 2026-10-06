#!/usr/bin/env python3
"""100/500/1000 real loaded endpoints with matched loaded-chunk OFF/active baselines.
Only isolated dev_perf_v1 and local console fixtures; no estimated performance values.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
from rcon import command
from importlib.util import spec_from_file_location,module_from_spec

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('three',ROOT/'scripts/three-server-test.py');three=module_from_spec(spec);spec.loader.exec_module(three)
sql,poll=three.sql,three.poll
PORT=25578;CLUSTER='dev_perf_v1'
def issue(value):
    text=command(PORT,'ct_test '+value)
    if 'ERROR ' in text:raise AssertionError(text)
    return text
def bulk():
    result=dict(re.findall(r'(\w+)=([\d.]+)',issue('bulk-status')))
    return {k:float(v) if '.' in v else int(v) for k,v in result.items()}
def numeric_metrics(text):
    values=re.findall(r'(\w+)=(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?=[, }\r\n]|$)',text)
    return {k:float(v) if any(marker in v for marker in '.eE') else int(v) for k,v in values}
def metrics():
    return numeric_metrics(issue('status'))

def validation_failures(report):
    failures=[]
    if [s['count'] for s in report['scenarios']]!=[100,500,1000]:failures.append('incomplete endpoint scale sequence')
    for scenario in report['scenarios']:
        count=scenario['count']
        if [s['active'] for s in scenario['samples']]!=[False,True]:failures.append(f'{count}: incomplete OFF/ACTIVE windows')
        for sample in scenario['samples']:
            label=f"{count}/{'ACTIVE' if sample['active'] else 'OFF'}"
            if sample['worker_errors'] or sample['queue_rejections']:failures.append(label+': worker errors or queue rejection')
            if sample['registered_endpoints']!=count or sample['loaded_endpoints']!=count:failures.append(label+': endpoint count differs from planned workload')
            if sample['active_endpoints']!=(count if sample['active'] else 0):failures.append(label+': active endpoint count differs at final observation')
            first=sample.get('first_metrics',{});last=sample['metrics']
            if last.get('quarantined',0)-first.get('quarantined',0):failures.append(label+': new quarantines')
    return failures

def self_test():
    assert numeric_metrics('{tiny=9.72E-4, scientific=9E-4, integer=9007199254740993, negative=-1, bad=12abc}')=={'tiny':.000972,'scientific':.0009,'integer':9007199254740993,'negative':-1}
    def sample(n,active):return dict(active=active,worker_errors=0,queue_rejections=0,registered_endpoints=n,loaded_endpoints=n,active_endpoints=n if active else 0,first_metrics={'quarantined':0},metrics={'quarantined':0})
    report={'scenarios':[{'count':n,'samples':[sample(n,False),sample(n,True)]} for n in (100,500,1000)]}
    assert not validation_failures(report)
    report['scenarios'][1]['samples'][1]['worker_errors']=50
    assert any('worker errors' in f for f in validation_failures(report))
    report['scenarios'][1]['samples'][1]['worker_errors']=0;report['scenarios'][2]['samples'][1]['active_endpoints']=984
    assert any('active endpoint count' in f for f in validation_failures(report))
    report['scenarios'].pop();assert 'incomplete endpoint scale sequence' in validation_failures(report)
    print('Offline scale acceptance checks passed; no JVM/backend accessed.')

def run():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--label',default='before');parser.add_argument('--seconds',type=int,default=20)
    parser.add_argument('--origin-x',type=int,help='Explicit isolated fixture coordinate for matching the recorded loaded-chunk footprint; default preserves the original time-derived coordinate')
    parser.add_argument('--observer-ready-file',type=Path,help='Optional one-time startup signal under scratch/optimization; adds no RCON query and is written before the first timed window')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:self_test();return
    if not re.fullmatch(r'[a-z0-9_-]+',args.label) or not 5<=args.seconds<=120:raise ValueError('invalid benchmark parameters')
    if args.origin_x is not None and not 30000<=args.origin_x<=34000:raise ValueError('fixture origin must remain within the isolated performance area')
    if args.observer_ready_file is not None:
        args.observer_ready_file=args.observer_ready_file.resolve()
        if args.observer_ready_file.parent!=(ROOT/'scratch/optimization').resolve() or not re.fullmatch(r'[a-z0-9_-]+\.json',args.observer_ready_file.name):raise ValueError('invalid observer startup signal path')
        if args.observer_ready_file.exists():raise ValueError('refusing existing observer startup signal')
    def ready():
        try:return issue('status')
        except OSError:return 'starting'
    poll(ready,lambda t:'STATUS online' in t,seconds=60)
    owner=str(uuid.uuid4());x=args.origin_x if args.origin_x is not None else 30000+int(time.time())%4000;z=0;channels=[]
    for i in range(4):
        name='perf_'+args.label+'_'+uuid.uuid4().hex[:8];issue(f'create {owner} {name}')
        channel=poll(lambda:sql(f"SELECT channel_id FROM ct_channels WHERE cluster_id='{CLUSTER}' AND name='{name}'"),bool)[0][0];channels.append(channel)
    command(PORT,f'forceload add {x} 0 {x+31} 31')
    report={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'label':args.label,'cluster':CLUSTER,'hardware':{'cpu':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown'),'logical_cpus':os.cpu_count(),'memory':Path('/proc/meminfo').read_text().splitlines()[0]},'jvm':'Temurin 21.0.8+9 -Xmx2G','minecraft':'1.21.1','neoforge':'21.1.252','mod':'0.1.0-dev','backend':'MySQL 8.4.7 defaults + Redis 7.4.6; local Docker loopback; no injected network latency','method':'one real Minecraft JVM; shared real SQL/Redis path even for local endpoints; 4 channels, half SEND/half RECEIVE; test fixtures use vanilla load tickets, separate from mod quota tickets; no other factory machines','scenarios':[]}
    report['fixture']={'origin_x':x,'origin_z':z,'y':64,'width':32,'depth':32,'owner_uuid':owner,'channels':channels,
        'explicit_origin':args.origin_x is not None,'loaded_chunk_columns':(x+31)//16-x//16+1,
        'loaded_chunk_rows':(z+31)//16-z//16+1,'warmup_seconds':5,'repeats':1}
    config=(ROOT/'run-perf/cross-tesseract.properties').read_text().splitlines()
    report['transfer_flags']={line.split('=',1)[0]:line.split('=',1)[1] for line in config if line.startswith(('transfer.channelBatches=','transfer.localFastPath='))}
    report['DB_window_definition']='Counter snapshots bracket the nominal steady interval; rates using nominal seconds include uncounted tail RCON time. Capture bounds are recorded separately, without changing the original query schedule.'
    pid=int(re.search(r'PID (\d+)',issue('pid'))[1]);jcmd=ROOT/'scratch/jdk/jdk-21.0.8+9/bin/jcmd'
    raw=ROOT/'reports/raw';raw.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(jcmd),str(pid),'JFR.start','name=ct_perf','settings=profile',f'filename={raw / (args.label+".jfr")}','maxsize=64m'],check=True,capture_output=True,text=True)
    report['passed']=False
    try:
        for count in (100,500,1000):
            if count>100:issue('bulk-active false')
            issue(f'bulk {x} {z} {count} {owner} '+','.join(channels))
            initialized=poll(bulk,lambda r:r.get('registered')==count and r.get('bound')==count,seconds=300)
            if count==100 and args.observer_ready_file is not None:
                signal={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'monotonic':time.monotonic(),'bulk':initialized,'stage':'before first warmup; no assets acknowledged by this signal'}
                temporary=args.observer_ready_file.with_suffix('.tmp')
                temporary.write_text(json.dumps(signal)+'\n');os.replace(temporary,args.observer_ready_file)
            samples=[]
            for active in (False,True):
                issue('bulk-active '+str(active).lower());time.sleep(5);issue('reset-metrics')
                first=bulk();first_status_start=time.monotonic();first_metrics=metrics();first_status_end=time.monotonic();start=time.monotonic()
                while time.monotonic()-start<args.seconds:time.sleep(min(1,args.seconds-(time.monotonic()-start)))
                duration=time.monotonic()-start;last=bulk();last_status_start=time.monotonic();last_metrics=metrics();last_status_end=time.monotonic()
                accepted=last['accepted']-first['accepted'];extracted=last['extracted']-first['extracted']
                samples.append({'active':active,'seconds':duration,'registered_endpoints':last['registered'],'loaded_endpoints':last_metrics['registered_loaded_endpoints'],'active_endpoints':last_metrics['active_endpoints'],'channels':4,'accepted_FE':accepted,'extracted_FE':extracted,'extracted_FE_per_second':extracted/duration,'worker_transactions_per_second':(last_metrics['transactions']-first_metrics['transactions'])/duration,'queue_rejections':last_metrics['queue_rejected']-first_metrics['queue_rejected'],'worker_errors':last_metrics['errors']-first_metrics['errors'],'fixture_ms_per_tick':(last['fixture_ms_total']-first['fixture_ms_total'])/max(1,last['fixture_ticks']-first['fixture_ticks']),'metrics':last_metrics,
                    'first_metrics':first_metrics,'first_bulk':first,'last_bulk':last,
                    'DB_transactions_window':last_metrics['db_transactions']-first_metrics['db_transactions'],
                    'DB_transactions_per_second':(last_metrics['db_transactions']-first_metrics['db_transactions'])/duration,
                    'counter_capture_seconds_bounds':{'lower':last_status_start-first_status_end,'upper':last_status_end-first_status_start},
                    'DB_transactions_per_capture_second_bounds':{
                        'lower':(last_metrics['db_transactions']-first_metrics['db_transactions'])/(last_status_end-first_status_start),
                        'upper':(last_metrics['db_transactions']-first_metrics['db_transactions'])/(last_status_start-first_status_end)}})
            report['scenarios'].append({'count':count,'channel_distribution':[min(256,max(0,count-i*256)) for i in range(4)],'samples':samples})
            (ROOT/f'reports/performance-{args.label}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(report['scenarios'][-1],ensure_ascii=False),flush=True)
        report['completed']=True
        report['validation_failures']=validation_failures(report)
        report['passed']=not report['validation_failures']
    except Exception as e:
        report['failure']=type(e).__name__+': '+str(e)
        raise
    finally:
        try:issue('bulk-active false')
        except Exception as e:report['cleanup_failure']=type(e).__name__;report['passed']=False
        stopped=subprocess.run([str(jcmd),str(pid),'JFR.stop','name=ct_perf'],capture_output=True,text=True)
        report['jfr_stop_exit']=stopped.returncode
        if stopped.returncode:report['passed']=False
        (ROOT/f'reports/performance-{args.label}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if not report['passed']:raise AssertionError('Benchmark validation or cleanup failed; see the saved report')
    print('Saved '+str(ROOT/f'reports/performance-{args.label}.json'))

if __name__=='__main__':run()
