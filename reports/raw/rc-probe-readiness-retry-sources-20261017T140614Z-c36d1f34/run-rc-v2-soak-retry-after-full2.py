#!/usr/bin/env python3
"""Fresh smoke3/full3 after the closed, audited full2 observer-read failure.

No old workload replay, consumption, refund or failed-evidence rewrites. Child
controllers prepare new worlds and perform their own normal start/stop. Default
is offline; all referenced failed parents and terminal audit bytes are bound.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]

def utc():return datetime.now(timezone.utc).isoformat()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def meta(path):return {'path':str(path.relative_to(ROOT)),'sha256':sha(path)}
def read_ref(ref):
    path=Path(ref['path']);path=path if path.is_absolute() else ROOT/path
    if path.is_symlink():raise ValueError('No symlink evidence')
    path=path.resolve(strict=True)
    if not path.is_relative_to(ROOT) or sha(path)!=ref['sha256']:raise ValueError('Closed evidence SHA/path mismatch')
    return path,json.loads(path.read_text())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--failed-continuation',type=Path);p.add_argument('--asset-audit',type=Path);p.add_argument('--export-audit',type=Path);a=p.parse_args()
    if not a.execute:
        print(json.dumps({'execution':'NOT_RUN','order':['fresh_smoke3_60s','fresh_full3_3600s'],'retained':'original smoke1 and full2 failed raw/worlds/assets unchanged'}));return 0
    if any(v is None for v in (a.failed_continuation,a.asset_audit,a.export_audit)):p.error('All three explicit closed references required')
    if any(k in os.environ for k in ('CT_MYSQL_URL','CT_MYSQL_USER','CT_MYSQL_PASSWORD','CT_REDIS_URI')):raise ValueError('Backend override forbidden')
    refs=[]
    for path in (a.failed_continuation,a.asset_audit,a.export_audit):
        path=path.resolve(strict=True)
        if not path.is_relative_to(ROOT) or path.is_symlink():raise ValueError('Repository regular evidence only')
        refs.append((path,json.loads(path.read_text())))
    (prior_path,prior),(asset_path,asset),(export_path,export)=refs
    if prior.get('passed') is not False or prior.get('state')!='FAILED_RETAINED' or not prior.get('utc_end'):raise ValueError('Closed failed second parent required')
    runs={r['name']:r for r in prior['runs']}
    if runs['smoke60']['state']!='PASS' or runs['full3600']['state']!='FAILED_RETAINED':raise ValueError('Exact smoke2-pass/full2-failure chain required')
    smoke_path,smoke=read_ref(runs['smoke60']['child_controller'])
    if not smoke.get('qualified_passed') or not smoke.get('all_own_launchers_exited_and_locks_free'):raise ValueError('Closed smoke2 pass absent')
    full_path,full=read_ref(runs['full3600']['child_controller']);raw_path,raw=read_ref(full['raw_report'])
    if (full.get('passed') is not False or full.get('sixty_minute_gate') is not False or full.get('all_own_launchers_exited_and_locks_free') is not True
            or any(x['exit_code']!=0 for x in full['own_launcher_exits'].values())
            or raw.get('failures')!=["JSONDecodeError: Expecting ',' delimiter: line 1 column 106497 (char 106496)"]
            or 'final_drain' in raw or raw.get('60min_gate') is not False):raise ValueError('Different full2 failure; do not automatically continue')
    if (asset.get('audit_passed') is not True or asset.get('original_sixty_minute_gate') is not False
            or asset['raw']['sha256']!=sha(raw_path) or asset['controller']['sha256']!=sha(full_path)
            or asset.get('positive_WAL_SQL_credit_identity_match') is not True or asset.get('all_source_WAL_deposits_empty') is not True):raise ValueError('Failed-window terminal asset audit missing')
    if export.get('original_failed_raw_sha256')!=sha(raw_path) or export.get('business_mutation_commands_after_observation_end')!=[]:raise ValueError('Post-failure command boundary audit mismatch')
    if export['asset_audit']['sha256']!=sha(asset_path):raise ValueError('Export/asset audit chain mismatch')
    for row in export['exports']:
        for key in ('source','archive'):
            path=ROOT/row[key]
            if sha(path)!=row['sha256']:raise ValueError('Late-read export bytes changed')
    original_path,original=read_ref(prior['continuation_of_failed_sequence'])
    if original.get('passed') is not False or original.get('state')!='FAILED_RETAINED':raise ValueError('Original first failed parent must remain failed')
    for ref in prior['prior_closed_children'].values():
        _,child=read_ref(ref)
        if not child.get('qualified_passed') or not child.get('functional_passed') or not child.get('all_own_launchers_exited_and_locks_free'):raise ValueError('Original closed primary child invalid')
        read_ref(child['raw_report'])
    final_path,_=read_ref(prior['final_manifest']);read_ref(prior['f3_manifest'])
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    target=ROOT/'reports/rc-20261017'/('v2-soak-full2-retry-'+stamp+'.json')
    archive=ROOT/'reports/raw'/('rc-probe-readiness-retry-sources-'+stamp);archive.mkdir(parents=True,exist_ok=False)
    sources=[]
    for source in (Path(__file__).resolve(),ROOT/'scripts/rc-probe-benchmark.py',ROOT/'scripts/rc-soak.py',ROOT/'scripts/analysis/run-rc-v2-soak.py',ROOT/'scripts/analysis/test-rc-probe-file-readiness.py'):
        dest=archive/source.name
        with dest.open('xb') as out:out.write(source.read_bytes())
        sources.append({'source':meta(source),'archive':meta(dest)})
    helper='scripts/analysis/run-rc-v2-soak.py'
    report={'schema':1,'passed':False,'state':'STARTING','utc_start':utc(),'controller':meta(Path(__file__).resolve()),
            'continuation_of_failed_sequence':meta(original_path),'failed_second_continuation':meta(prior_path),
            'failed_full2_controller':meta(full_path),'failed_full2_raw':meta(raw_path),'successful_smoke2_controller':meta(smoke_path),
            'first_smoke_failure_audit':prior['first_smoke_failure_audit'],'failed_first_smoke_controller':prior['failed_first_smoke_controller'],
            'full2_failure_asset_audit':meta(asset_path),'full2_export_late_read_audit':meta(export_path),
            'prior_closed_children':prior['prior_closed_children'],'f3_manifest':prior['f3_manifest'],'final_manifest':prior['final_manifest'],
            'archived_observer_sources':sources,'failures':[],
            'scope':'Fresh smoke3/full3, same frozen3647/v2 agent/input conditions. Only Python readiness reader changed. Old smoke1/full2 failed gates, worlds, IDs and retained assets remain unchanged. No replay, repair, refund or consumption of old assets.',
            'runs':[{'name':name,'state':'NOT_RUN','command':['python3',helper,'--execute','--manifest',str(final_path),'--kind',kind,'--label',label]} for name,kind,label in (('smoke60','smoke','rc-soak-v2-3647-smoke3'),('full3600','full','rc-soak-v2-3647-full3'))]}
    def save():
        pending=target.with_suffix('.json.pending');pending.write_text(json.dumps(report,indent=2)+'\n');pending.replace(target)
    try:
        if target.exists():raise ValueError('Never overwrite evidence')
        save()
        for run in report['runs']:
            run.update(state='RUNNING',utc_start=utc(),observer_start=time.monotonic(),helper=meta(ROOT/helper));report['state']='RUNNING_'+run['name']
            log=ROOT/'logs'/('rc-v2-full2-retry-'+run['name']+'-'+stamp+'.log');run['log']=str(log.relative_to(ROOT));save()
            print('RC_V2_FULL2_RETRY_STAGE_START '+run['name'],flush=True)
            with log.open('x') as out:child=subprocess.run(run['command'],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
            run.update(exit_code=child.returncode,utc_end=utc(),observer_end=time.monotonic())
            completion=json.loads(log.read_text().splitlines()[-1]);run['completion']=completion;path,data=read_ref(completion['controller']);run['child_controller']=meta(path)
            run['state']='PASS' if child.returncode==0 and completion.get('passed') is True and data.get('passed') is True else 'FAILED_RETAINED'
            save();print('RC_V2_FULL2_RETRY_STAGE_END '+run['name']+' '+run['state'],flush=True)
            if run['state']!='PASS':raise ValueError('Fresh child failed; retain assets/configs and later stages NOT_RUN')
        report.update(state='COMPLETE',passed=True)
    except BaseException as error:
        report['state']='FAILED_RETAINED';report['failures'].append(type(error).__name__+': '+str(error))
    finally:report['utc_end']=utc();save()
    print(json.dumps({'sequence':meta(target),'passed':report['passed'],'state':report['state']}),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
