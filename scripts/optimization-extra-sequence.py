#!/usr/bin/env python3
"""Serial isolated resource-mix and ownership/fallback checks for the frozen core.

May wait for the primary sequence's normal stop without contacting its servers.
Only --execute starts tests. It never accepts EULA, resets worlds or kills game JVMs.
"""
from pathlib import Path
import argparse, fcntl, hashlib, json, subprocess, sys, time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rcon import command
CORE='68f32db439f445b8f72faf92dc62fbc5b9dce738'
OLD='87bf217fcaffcceb2629c36bb54d5158b9f461e8'
PORTS={'A':25575,'B':25576,'C':25577}
FROZEN={'A':'scratch/dev-launch/461a2a5e6d514b3d8dee60815d06907f/runServerA.sh',
 'B':'scratch/dev-launch/6abe4cc458594e518651384c893118dd/runServerB.sh',
 'C':'scratch/dev-launch/3ebbae306b2a47d1b42860767294a5de/runServerC.sh'}

def live(server):
 result=[]; marker=('server'+server+'RunVmArgs.txt').encode()
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   argv=(proc/'cmdline').read_bytes().split(b'\0')
   if argv and argv[0].endswith(b'/java') and any(marker in value for value in argv):result.append(int(proc.name))
  except (FileNotFoundError,PermissionError):pass
 return result

def stopped(server):
 if live(server):return False
 with (ROOT/f'scratch/server-{server}.launch.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
  except BlockingIOError:return False

def stop():
 for server,port in PORTS.items():
  if live(server):
   try:command(port,'stop')
   except OSError:pass
 deadline=time.monotonic()+90
 while not all(stopped(server) for server in PORTS):
  if time.monotonic()>deadline:raise RuntimeError('Normal stop timeout; no automatic force kill')
  time.sleep(.5)

def save():target.write_text(json.dumps(report,indent=2)+'\n')

def start(label,old):
 for server in PORTS:
  argv=['bash','scripts/start-frozen-dev.sh',server,FROZEN[server]] if old else ['bash','scripts/start-dev.sh',server]
  with (ROOT/f'logs/optimization-{label}-{server}.log').open('w') as output:
   subprocess.Popen(argv,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
 deadline=time.monotonic()+120
 for server,port in PORTS.items():
  while True:
   try:
    if 'STATUS online' in command(port,'ct_test status',timeout=5):break
   except OSError:pass
   if time.monotonic()>deadline:raise RuntimeError('Startup timeout '+server)
   time.sleep(1)

def mix(label,mode,old=False,smoke=False):
 stop()
 subprocess.run(['python3','scripts/configure-optimization.py','--label','resource-mix-'+label,'--mode',mode],cwd=ROOT,check=True)
 start('resource-mix-'+label,old)
 pattern='optimization-resource-mix-'+label+'-*.json';before=set((ROOT/'reports').glob(pattern))
 argv=['python3','scripts/optimization-resource-mix.py','--execute','--label',label,
  '--operator-revision',OLD if old else CORE,'--scenarios','mixed','--warmup','0' if smoke else '30',
  '--seconds','1' if smoke else '120','--repeats','1' if smoke else '3','--timeout','120' if smoke else '1200']
 entry={'command':argv,'runtime_revision':OLD if old else CORE,'mode':mode,'smoke_not_performance':smoke,
  'utc_start':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'log':'logs/optimization-resource-mix-'+label+'.log'}
 report['runs'].append(entry);save();print('START',label,flush=True)
 with (ROOT/entry['log']).open('w') as output:result=subprocess.run(argv,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
 files=set((ROOT/'reports').glob(pattern))-before
 entry.update(exit_code=result.returncode,utc_end=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
 if len(files)==1:
  path=next(iter(files));body=json.loads(path.read_text())
  entry.update(report=str(path.relative_to(ROOT)),report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),passed=body.get('passed',False))
 save()
 if result.returncode or len(files)!=1 or not entry.get('passed'):raise RuntimeError('Resource mix failed; raw evidence/assets retained '+label)
 print('END',label,flush=True);stop()

def regress(mode):
 argv=['python3','scripts/optimization-regression-suite.py','--mode',mode,'--execute']
 entry={'command':argv,'runtime_revision':CORE,'utc_start':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'log':f'logs/optimization-final-regressions-{mode}-68f32db.log'}
 report['runs'].append(entry);save();print('START regression',mode,flush=True)
 with (ROOT/entry['log']).open('w') as output:result=subprocess.run(argv,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
 entry.update(exit_code=result.returncode,utc_end=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),report=f'reports/optimization-final-regressions-{mode}-68f32db.json');save()
 if result.returncode:raise RuntimeError('Regression suite failed; evidence retained '+mode)
 print('END regression',mode,flush=True)

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');parser.add_argument('--wait-primary',action='store_true');parser.add_argument('--original-launch-manifest',type=Path,required=True)
args=parser.parse_args()
if not args.execute:raise SystemExit('Requires --execute; fault injection is confined to existing isolated dev fixtures')
if args.original_launch_manifest.stat().st_size>8192:raise SystemExit('Oversized original launch manifest')
FROZEN=json.loads(args.original_launch_manifest.read_text())
if set(FROZEN)!=set(PORTS):raise SystemExit('Expected original launch A/B/C exactly')
target=ROOT/'reports/optimization-extra-sequence-68f32db.json'
if target.exists():raise SystemExit('Refusing existing evidence')
artifact=json.loads((ROOT/'reports/optimization-artifact-ready-final.json').read_text())
source_hash=hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest() for p in sorted((ROOT/'src/main/java').rglob('*.java')))).hexdigest()
if source_hash!=artifact['source_manifest_sha256']:raise SystemExit('Declared core source differs')
report={'source_revision':CORE,'source_manifest_sha256':source_hash,'runs':[],'passed':False,
 'scope':'Real same-channel fixed64 named ITEM plus FE/water, followed by real faults and same-JAR restart fallback; all serial. Smoke is not performance.'}
if args.wait_primary:
 report['state']='waiting_for_primary_normal_stop';save();deadline=time.monotonic()+10800
 while True:
  primary=ROOT/'reports/optimization-final-sequence-current-68f32db.json'
  try:body=json.loads(primary.read_text()) if primary.exists() else {}
  except json.JSONDecodeError:body={}
  if body.get('utc_end'):
   if not body.get('procedure_completed') or not body.get('passed'):raise SystemExit('Primary sequence failed; no dependent tests started')
   if all(stopped(server) for server in PORTS):break
  if time.monotonic()>deadline:raise SystemExit('Primary wait expired; no tests started')
  time.sleep(2)
if live('Perf') or not all(stopped(server) for server in PORTS):raise SystemExit('Normally stop selected test JVMs before executing')
report['state']='running';save()
try:
 mix('smoke68','fast',smoke=True)
 mix('original87','legacy',old=True)
 mix('batch68','batch')
 mix('fast68','fast')
 regress('fast');regress('legacy')
 report['passed']=True;report['state']='completed'
except BaseException as error:
 report['failure']=type(error).__name__+': '+str(error);report['state']='failed';raise
finally:
 try:stop()
 except Exception as error:report['stop_failure']=type(error).__name__+': '+str(error);report['passed']=False
 report['utc_end']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());save()
