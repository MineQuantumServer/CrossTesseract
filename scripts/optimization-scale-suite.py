#!/usr/bin/env python3
"""Repeat the fixed six-chunk scale workload and read-only sidecar with serialized startup.
The declared Java core must match the ready-final artifact manifest. --execute and
an existing stopped isolated perf fixture/EULA are required. No worlds are deleted.
"""
from pathlib import Path
import argparse,subprocess,time,sys,json,hashlib,fcntl,signal,importlib.util,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'));from rcon import command
CORE='68f32db439f445b8f72faf92dc62fbc5b9dce738';PORT=25578
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
if not args.execute:raise SystemExit('Requires --execute; existing isolated perf setup only')
TOKEN=uuid.uuid4().hex[:8];LABEL='fast-scale-'+TOKEN;BENCH='opt-fast-68f32db-'+TOKEN
report={'source_commit':CORE,'label':LABEL,'passed':False,'completed':False,'comparison':'Original x30357/z0/y64 six-chunk footprint; 100/500/1000, four channels capped256; 5s warmup,120s OFF/ACTIVE,one repeat. Same2s scale monitor/jstat10s/JFR profile; a one-time file signal from the unchanged bulk registration poll starts sampling before the first warmup; no ABC JVMs or heavy offline tools running. This is distinct from single-observer three-JVM primary runs.'}
target=ROOT/f'reports/optimization-conditions-{LABEL}-68f32db.json'
def save():target.write_text(json.dumps(report,indent=2)+'\n')
def live(suffix):
 marker=('server'+suffix+'RunVmArgs.txt').encode();result=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   argv=(p/'cmdline').read_bytes().split(b'\0')
   if argv and argv[0].endswith(b'/java') and any(marker in arg for arg in argv):result.append(int(p.name))
  except (FileNotFoundError,PermissionError):pass
 return result
if any(live(s) for s in ['A','B','C','Perf']):raise SystemExit('Normal-stop all selected game JVMs first')
if target.exists():raise SystemExit('Refusing saved evidence overwrite')
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();report['repository_HEAD']=head
artifact=json.loads((ROOT/'reports/optimization-artifact-ready-final.json').read_text())
source_hash=hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest() for p in sorted((ROOT/'src/main/java').rglob('*.java')))).hexdigest()
if source_hash!=artifact['source_manifest_sha256']:raise SystemExit('Core source does not match declared performance revision')
report['java_source_tree_sha256']=artifact['source_manifest_sha256'];report['jar_sha256']=hashlib.sha256((ROOT/'build/libs/cross_tesseract-0.1.0-dev.jar').read_bytes()).hexdigest();save()
binary=next(item for item in artifact['artifacts'] if item['path']=='build/libs/cross_tesseract-0.1.0-dev.jar')
if report['jar_sha256']!=binary['sha256']:raise SystemExit('JAR does not match declared performance revision')
monitor=None
try:
 subprocess.run(['python3','scripts/configure-optimization.py','--label',LABEL,'--mode','fast','--servers','perf'],cwd=ROOT,check=True)
 with (ROOT/f'logs/optimization-{LABEL}-68f32db-startup.log').open('w') as log:subprocess.Popen(['bash','scripts/start-dev.sh','perf'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 deadline=time.monotonic()+120
 while True:
  try:
   if 'STATUS online' in command(PORT,'ct_test status',timeout=5):break
  except OSError:pass
  if time.monotonic()>deadline:raise RuntimeError('Perf startup timeout')
  time.sleep(1)
 pids=live('Perf');assert len(pids)==1;pid=pids[0];argv=(Path('/proc')/str(pid)/'cmdline').read_bytes();arguments=argv.split(b'\0');vm=next(Path(a[1:].decode()) for a in arguments if a.startswith(b'@') and a.endswith(b'serverPerfRunVmArgs.txt'))
 frozen=vm.parent;report['selected_launch']={'pid':pid,'argv_sha256':hashlib.sha256(argv).hexdigest(),'vm_args':str(vm),'vm_args_sha256':hashlib.sha256(vm.read_bytes()).hexdigest(),'folder':str(frozen),'classes_sha256':hashlib.sha256(b''.join(str(p.relative_to(frozen/'classes')).encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest() for p in sorted((frozen/'classes').rglob('*.class')))).hexdigest()}
 report['config']={s.split('=',1)[0]:s.split('=',1)[1] for s in (ROOT/'run-perf/cross-tesseract.properties').read_text().splitlines() if s.startswith(('transfer.','limits.'))}
 report['utc_start']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());save()
 before=set((ROOT/'reports').glob(f'optimization-scale-{LABEL}-68f32db-*.json'))
 ready_file=ROOT/f'scratch/optimization/scale-ready-68f32db-{TOKEN}.json';assert not ready_file.exists()
 cmd=['python3','scripts/performance-test.py','--label',BENCH,'--seconds','120','--origin-x','30357','--observer-ready-file',str(ready_file)];report['command']=cmd;save()
 with (ROOT/f'logs/optimization-{LABEL}-68f32db.log').open('w') as log:
  bench=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  # Startup is signalled by the driver's existing serialized registration poll.
  # Never race additional RCON reads against its channel/PID/bootstrap requests.
  deadline=time.monotonic()+300
  while not ready_file.exists():
   if bench.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Driver failed before initialized100 fixture; raw log retained')
   time.sleep(.2)
  report['monitor_startup_signal']=json.loads(ready_file.read_text());save()
  with (ROOT/f'logs/optimization-{LABEL}-68f32db-monitor.log').open('w') as output:
   monitor=subprocess.Popen(['python3','scripts/optimization-scale-monitor.py','--label',LABEL+'-68f32db','--seconds','1800','--interval','2','--jstat-every','10','--coverage-note','Starts after driver signals actual100 registration, before nominal first window; no concurrent startup RCON probes. Original late monitor remains partial; no additional timed observation cadence.'],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
  result=bench.wait()
 report['benchmark_exit_code']=result;report['performance_report']='reports/performance-'+BENCH+'.json'
 body=json.loads((ROOT/report['performance_report']).read_text());report['completed']=body.get('completed',False);report['passed']=body.get('passed',False) and result==0;report['validation_failures']=body.get('validation_failures',[])
 if not report['passed']:raise RuntimeError('Scale validation failed; saved data retained')
finally:
 if monitor is not None:
  if monitor.poll() is None:monitor.send_signal(signal.SIGINT)
  report['monitor_exit_code']=monitor.wait(timeout=20)
  files=set((ROOT/'reports').glob(f'optimization-scale-{LABEL}-68f32db-*.json'))
  if len(files)==1:report['monitor_report']=str(next(iter(files)).relative_to(ROOT))
 if live('Perf'):
  try:report['stop_reply']=command(PORT,'stop')
  except OSError as error:report['stop_reply_error']=type(error).__name__
 deadline=time.monotonic()+90
 while live('Perf'):
  if time.monotonic()>deadline:report['stop_failure']='Normal shutdown timeout; no force kill';report['passed']=False;break
  time.sleep(.5)
 report['remaining_jvm_pids']=live('Perf');report['utc_end']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());save();print(json.dumps(report,indent=2),flush=True)
