#!/usr/bin/env python3
"""Fresh perf-world native v2 recorder check; no workload assets; offline by default."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, fcntl, hashlib, importlib.util, json, subprocess, sys, time, uuid
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--manifest',type=Path);a=p.parse_args()
if not a.execute:print(json.dumps({'execution':'NOT_RUN','requires':'--execute --manifest final v2; released native window'}));raise SystemExit(0)
if a.manifest is None:p.error('--manifest required')
manifest=a.manifest.resolve(strict=True);seal=json.loads(manifest.read_text());entry=seal['launches']['perf'];token=uuid.uuid4().hex
target=ROOT/'reports/rc-20261017'/('probe-v2-native-validation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+token[:8]+'.json')
report={'passed':False,'utc_start':utc(),'manifest':str(manifest.relative_to(ROOT)),'manifest_sha256':sha(manifest),'commands':[],'failures':[],
 'scope':'Fresh isolated perf world, one empty unbound BE, actual saveAdditional via vanilla data-get call. No FE/item/fluid input or consumption; not a world-save or performance sample.'}
def save():
 temp=target.with_suffix('.json.pending');temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(target)
cfg=load('rc_v2_check_config',ROOT/'scripts/configure-optimization.py');probe=load('rc_v2_check_probe',ROOT/'scripts/rc-probe-benchmark.py');rcon=load('rc_v2_check_rcon',ROOT/'scripts/rcon.py')
expected={r['relative_path'][5:]:r['sha256'] for r in seal['artifacts']['source_main']['files'] if r['relative_path'].startswith('java/')}
stage=load('rc_v2_check_source_guard',ROOT/'scripts/analysis/run-rc-v2-stage.py');process=None;windows=None
def request(command):
 event={'command':command,'start':time.monotonic(),'utc':utc()};report['commands'].append(event)
 try:event['reply']=rcon.command(25578,command,timeout=5);return event['reply']
 except Exception as e:event['uncertain_no_mutation_replay']=type(e).__name__+': '+str(e);raise
 finally:event['end']=time.monotonic();save()
try:
 save();report['source_before']=stage.source_point(expected);assert report['source_before']['matches_expected']
 lock=(ROOT/'scratch/server-perf.launch.lock').open('a')
 try:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert not cfg.running('perf')
  label='rc-v2-check-'+token[:8];command=['python3','scripts/configure-optimization.py','--servers','perf','--label',label,'--mode','fast']
  result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True);report['preparation']={'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr};assert result.returncode==0
 finally:lock.close()
 assert sha(Path(entry['launcher']))==entry['launcher_sha256'] and sha(Path(entry['vm_args']))==entry['vm_args_sha256']
 log=ROOT/'logs'/('rc-probe-v2-native-'+token+'.log')
 with log.open('x') as stream:process=subprocess.Popen(['bash','scripts/start-frozen-dev.sh','perf',entry['launcher']],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
 report.update(controller_launcher_PID=process.pid,log=str(log.relative_to(ROOT)));save();deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  if process.poll() is not None:raise RuntimeError('Probe JVM exited before ready')
  try:
   if 'STATUS online' in request('ct_test status'):break
  except OSError:pass
  time.sleep(.5)
 else:raise RuntimeError('Probe startup timeout')
 x,z=20160,20160;owner=str(uuid.uuid4());request(f'forceload add {x} {z}')
 spawn=request(f'ct_test spawn {x} {z} {owner}');assert 'SPAWN ' in spawn
 deadline=time.monotonic()+60
 while True:
  inspected=request(f'ct_test inspect {x} {z}')
  if 'registered=true' in inspected:break
  if time.monotonic()>deadline:raise RuntimeError('Empty fixture registration timeout')
  time.sleep(.1)
 windows=probe.ProbeWindows(manifest,servers=('perf',));report['start']=windows.start();save()
 request(f'data get block {x} 64 {z}')
 time.sleep(5);report['fixed']=windows.fixed();report['full']=windows.stop();save()
 data=report['full']['perf']['data'];assert data['ticks']>=50 and data['spans']['save_additional']['inclusive']['count']>=1
 assert data['mod_roots']['valid'] and data['mod_roots']['per_complete_logical_tick_cycle']['count']==data['ticks']
 assert report['fixed']['perf']['data']['mod_roots']['per_complete_logical_tick_cycle']['count']==report['fixed']['perf']['data']['ticks']-1
 identity={}
 for name,record in data['transformed_classes'].items():
  if name.startswith('dev/crosstesseract/'):
   path=Path(entry['launcher']).parent/'classes'/(name+'.class');assert sha(path)==record['original_class_sha256'];identity[name]=sha(path)
 report['actual_transform_input_matches_frozen_classes']=identity;report['functional_probe_pass']=True
except BaseException as error:report['failures'].append(type(error).__name__+': '+str(error))
finally:
 if windows is not None and windows.token is not None:
  try:report['incomplete_probe']=windows.stop()
  except Exception as error:report['failures'].append('Incomplete probe stop: '+repr(error))
 if process is not None and process.poll() is None:
  try:request('stop')
  except Exception:pass
  try:process.wait(timeout=120)
  except subprocess.TimeoutExpired:report['failures'].append('Normal-stop timeout; no force kill')
 report['source_after_stop']=stage.source_point(expected)
 if not report['source_after_stop']['matches_expected']:report['failures'].append('Main Java source changed')
 report.update(launcher_exit=process.poll() if process is not None else None,utc_end=utc(),passed=bool(report.get('functional_probe_pass')) and not report['failures']);save()
print(json.dumps({'report':str(target.relative_to(ROOT)),'sha256':sha(target),'passed':report['passed'],'failures':report['failures']}));raise SystemExit(0 if report['passed'] else 1)
