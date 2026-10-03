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
def metrics():
    text=issue('status');return {k:float(v) if '.' in v else int(v) for k,v in re.findall(r'(\w+)=([\d.]+)',text)}

def run():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--label',default='before');parser.add_argument('--seconds',type=int,default=20);args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9_-]+',args.label) or not 5<=args.seconds<=120:raise ValueError('invalid benchmark parameters')
    def ready():
        try:return issue('status')
        except OSError:return 'starting'
    poll(ready,lambda t:'STATUS online' in t,seconds=60)
    owner=str(uuid.uuid4());x=30000+int(time.time())%4000;z=0;channels=[]
    for i in range(4):
        name='perf_'+args.label+'_'+uuid.uuid4().hex[:8];issue(f'create {owner} {name}')
        channel=poll(lambda:sql(f"SELECT channel_id FROM ct_channels WHERE cluster_id='{CLUSTER}' AND name='{name}'"),bool)[0][0];channels.append(channel)
    command(PORT,f'forceload add {x} 0 {x+31} 31')
    report={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'label':args.label,'cluster':CLUSTER,'hardware':{'cpu':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown'),'logical_cpus':os.cpu_count(),'memory':Path('/proc/meminfo').read_text().splitlines()[0]},'jvm':'Temurin 21.0.8+9 -Xmx2G','minecraft':'1.21.1','neoforge':'21.1.252','mod':'0.1.0-dev','backend':'MySQL 8.4.7 defaults + Redis 7.4.6; local Docker loopback; no injected network latency','method':'one real Minecraft JVM; shared real SQL/Redis path even for local endpoints; 4 channels, half SEND/half RECEIVE; test fixtures use vanilla load tickets, separate from mod quota tickets; no other factory machines','scenarios':[]}
    pid=int(re.search(r'PID (\d+)',issue('pid'))[1]);jcmd=ROOT/'scratch/jdk/jdk-21.0.8+9/bin/jcmd'
    raw=ROOT/'reports/raw';raw.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(jcmd),str(pid),'JFR.start','name=ct_perf','settings=profile',f'filename={raw / (args.label+".jfr")}','maxsize=64m'],check=True,capture_output=True,text=True)
    report['passed']=False
    try:
        for count in (100,500,1000):
            if count>100:issue('bulk-active false')
            issue(f'bulk {x} {z} {count} {owner} '+','.join(channels))
            poll(bulk,lambda r:r.get('registered')==count and r.get('bound')==count,seconds=300)
            samples=[]
            for active in (False,True):
                issue('bulk-active '+str(active).lower());time.sleep(5);issue('reset-metrics')
                first=bulk();first_metrics=metrics();start=time.monotonic()
                while time.monotonic()-start<args.seconds:time.sleep(min(1,args.seconds-(time.monotonic()-start)))
                duration=time.monotonic()-start;last=bulk();last_metrics=metrics()
                accepted=last['accepted']-first['accepted'];extracted=last['extracted']-first['extracted']
                samples.append({'active':active,'seconds':duration,'registered_endpoints':last['registered'],'loaded_endpoints':last_metrics['registered_loaded_endpoints'],'active_endpoints':last_metrics['active_endpoints'],'channels':4,'accepted_FE':accepted,'extracted_FE':extracted,'extracted_FE_per_second':extracted/duration,'worker_transactions_per_second':(last_metrics['transactions']-first_metrics['transactions'])/duration,'queue_rejections':last_metrics['queue_rejected']-first_metrics['queue_rejected'],'worker_errors':last_metrics['errors']-first_metrics['errors'],'fixture_ms_per_tick':(last['fixture_ms_total']-first['fixture_ms_total'])/max(1,last['fixture_ticks']-first['fixture_ticks']),'metrics':last_metrics})
            report['scenarios'].append({'count':count,'channel_distribution':[min(256,max(0,count-i*256)) for i in range(4)],'samples':samples})
            (ROOT/f'reports/performance-{args.label}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(report['scenarios'][-1],ensure_ascii=False),flush=True)
        report['passed']=True
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
    if not report['passed']:raise AssertionError('Benchmark cleanup failed; see the saved report')
    print('Saved '+str(ROOT/f'reports/performance-{args.label}.json'))

if __name__=='__main__':run()
