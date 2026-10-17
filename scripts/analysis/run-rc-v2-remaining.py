#!/usr/bin/env python3
"""Serial continuation after a completed f3-v2 FE stage; no online work by default.

Each child owns a fresh world, actual single observer and normal JVM lifecycle.
This sequence does not rebuild, touch old evidence, or treat functional PASS as
performance-goal PASS. A failed child retains assets and prevents later starts.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, subprocess, sys, time, uuid
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def meta(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def utc():return datetime.now(timezone.utc).isoformat()
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--f3-manifest',type=Path);p.add_argument('--final-manifest',type=Path);p.add_argument('--completed-f3-controller',type=Path);a=p.parse_args()
if not a.execute:print(json.dumps({'execution':'NOT_RUN','order':['finalFE3','f3Bmix','finalBmix','finalFastMix','ablationDefault','ablationNotification1000','ablationActive200','smoke60','full3600'],'requires':'completed qualified f3 FE controller + same v2 manifests + --execute'}));raise SystemExit(0)
if not all((a.f3_manifest,a.final_manifest,a.completed_f3_controller)):p.error('Explicit closed f3 evidence/manifests required')
f3=a.f3_manifest.resolve(strict=True);final=a.final_manifest.resolve(strict=True);prior=a.completed_f3_controller.resolve(strict=True)
proof=json.loads(prior.read_text());assert proof['passed'] and proof['qualified_passed'] and proof['all_own_launchers_exited_and_locks_free'] and proof['samples']==3
raw=ROOT/proof['raw_report']['path'];assert sha(raw)==proof['raw_report']['sha256'] and json.loads(raw.read_text())['passed']
assert proof['runtime_manifest']==meta(f3),'Completed f3 stage used another runtime manifest'
stage='scripts/analysis/run-rc-v2-stage.py';soak='scripts/analysis/run-rc-v2-soak.py'
def command(manifest,label,phase='fe',mode='fast',variant='default'):
 return ['python3',stage,'--execute','--manifest',str(manifest),'--tree-manifest',str(final),'--phase',phase,'--mode',mode,'--variant',variant,'--label',label]
plan=[('finalFE3',command(final,'rc-fe-v2-final')),
 ('f3Bmix',command(f3,'resource-mix-rc-f3b-v2','mix','batch')),
 ('finalBmix',command(final,'resource-mix-rc-3647b-v2','mix','batch')),
 ('finalFastMix',command(final,'resource-mix-rc-3647f-v2','mix')),
 ('ablationDefault',command(final,'rc-fe-v2-abl-default','ablation')),
 ('ablationNotification1000',command(final,'rc-fe-v2-abl-notify','ablation',variant='notification1000')),
 ('ablationActive200',command(final,'rc-fe-v2-abl-active','ablation',variant='active200')),
 ('smoke60',['python3',soak,'--execute','--manifest',str(final),'--kind','smoke','--label','rc-soak-v2-3647-smoke']),
 ('full3600',['python3',soak,'--execute','--manifest',str(final),'--kind','full','--label','rc-soak-v2-3647-full'])]
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8];target=ROOT/'reports/rc-20261017'/('v2-remaining-sequence-'+stamp+'.json')
report={'utc_start':utc(),'passed':False,'state':'STARTING','completed_f3_controller':meta(prior),'f3_raw':meta(raw),'f3_manifest':meta(f3),'final_manifest':meta(final),'controller':meta(Path(__file__).resolve()),'runs':[{'name':name,'command':argv,'state':'NOT_RUN'} for name,argv in plan],'failures':[],
 'scope':'n1 primary FE3 and resource profiles, independent short ablations, explicit smoke60 then real3600s. Functional pass is separate from frozen latency/SQL targets. No overlap/heavy work; input drivers unchanged during execution.'}
def save():
 pending=target.with_suffix('.json.pending');pending.write_text(json.dumps(report,indent=2)+'\n');pending.replace(target)
try:
 if target.exists():raise ValueError('Never overwrite evidence')
 save()
 for run in report['runs']:
  name,argv=run['name'],run['command'];run.update(state='RUNNING',utc_start=utc(),observer_start=time.monotonic(),helper=meta(ROOT/argv[1]));report['state']='RUNNING_'+name;save();print('RC_V2_STAGE_START '+name,flush=True)
  log=ROOT/'logs'/('rc-v2-'+name+'-'+stamp+'.log');run['log']=str(log.relative_to(ROOT));save()
  with log.open('x') as output:result=subprocess.run(argv,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
  run.update(exit_code=result.returncode,utc_end=utc(),observer_end=time.monotonic())
  try:
   completion=json.loads(log.read_text().splitlines()[-1]);run['completion']=completion
   ref=completion['controller'];child=ROOT/ref['path'];assert sha(child)==ref['sha256'];child_data=json.loads(child.read_text())
   run['child_controller']=ref;run['child_passed']=child_data.get('passed');assert completion.get('passed') is True and child_data.get('passed') is True
  except Exception as error:run['completion_error']=type(error).__name__+': '+str(error)
  run['state']='PASS' if result.returncode==0 and run.get('child_passed') is True and 'completion_error' not in run else 'FAILED_RETAINED';save();print('RC_V2_STAGE_END '+name+' '+run['state'],flush=True)
  if run['state']!='PASS':raise RuntimeError('Child failed; later stages remain NOT_RUN: '+name)
 report.update(passed=True,state='COMPLETE')
except BaseException as error:report['failures'].append(type(error).__name__+': '+str(error));report['state']='FAILED_RETAINED'
finally:report['utc_end']=utc();save()
print(json.dumps({'sequence':meta(target),'passed':report['passed'],'state':report['state']}),flush=True);raise SystemExit(0 if report['passed'] else 1)
