#!/usr/bin/env python3
"""Serial real three-JVM correctness/fault regression and same-JAR restart fallback.
Only existing isolated dev fixtures; destructive fault injection never runs without --execute.
"""
from pathlib import Path
import argparse, subprocess, json, time, sys, fcntl, hashlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rcon import command

PORTS={'A':25575,'B':25576,'C':25577}
CORE='68f32db439f445b8f72faf92dc62fbc5b9dce738'

def live(server):
    marker=('server'+server+'RunVmArgs.txt').encode(); result=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().split(b'\0')
            if argv and argv[0].endswith(b'/java') and any(marker in arg for arg in argv):result.append(int(p.name))
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
        if time.monotonic()>deadline:raise RuntimeError('Clean stop failed; no automatic kill')
        time.sleep(.5)

def save():
    target.write_text(json.dumps(report,indent=2)+'\n')

def start():
    for server in PORTS:
        with (ROOT/f'logs/optimization-regression-{args.mode}-{server}.log').open('w') as log:
            subprocess.Popen(['bash','scripts/start-dev.sh',server],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+120
    for server,port in PORTS.items():
        while True:
            try:
                if 'STATUS online' in command(port,'ct_test status',timeout=5):break
            except OSError:pass
            if time.monotonic()>deadline:raise RuntimeError('Startup timeout '+server)
            time.sleep(1)

def run_case(script,name):
    generic={'three':'three-server.json','faults':'faults.json','recovery':'recovery.json','mysql':'mysql-outage.json'}.get(name)
    archive=ROOT/f'reports/{name}-68f32db-{args.mode}.json' if generic else None
    if archive and archive.exists():raise RuntimeError('Refusing existing evidence '+str(archive))
    pattern='optimization-restart-fallback-68f32db-*.json' if name=='fallback' else 'optimization-topology-final-'+args.mode+'-68f32db-*.json'
    before=set((ROOT/'reports').glob(pattern))
    argv=['python3','scripts/'+script]
    if name=='topology':argv+=['--label','final-'+args.mode+'-68f32db']
    if name=='fallback':argv+=['--execute']
    entry={'command':argv,'utc_start':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'log':f'logs/optimization-regression-{args.mode}-{name}.log'}
    previous_mtime=(ROOT/'reports'/generic).stat().st_mtime_ns if generic and (ROOT/'reports'/generic).exists() else None
    report['runs'].append(entry);save();print('START',name,entry['utc_start'],flush=True)
    with (ROOT/entry['log']).open('w') as log:result=subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    entry.update(exit_code=result.returncode,utc_end=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    if generic:
        generated=ROOT/'reports'/generic
        if not generated.exists() or generated.stat().st_mtime_ns==previous_mtime:
            entry['report_status']='No new report; previous generic result is not relabelled';save();raise RuntimeError('No fresh report for '+name)
        body=json.loads(generated.read_text());body['operator_runtime_revision']=CORE;body['transfer_flags']=report['transfer_flags'];body['loaded_revision_note']='Declared Java core; per-start immutable class selection is retained in launcher logs and source manifest.'
        archive.write_text(json.dumps(body,indent=2)+'\n')
    else:
        added=set((ROOT/'reports').glob(pattern))-before
        if len(added)!=1:raise RuntimeError('Ambiguous '+name+' report')
        archive=next(iter(added));body=json.loads(archive.read_text())
    entry.update(report=str(archive.relative_to(ROOT)),report_sha256=hashlib.sha256(archive.read_bytes()).hexdigest());save()
    if result.returncode or (name in ('topology','fallback') and not body.get('passed')):raise RuntimeError('Failed '+name+'; fresh report and original logs retained')
    print('END',name,entry['utc_end'],flush=True)

parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('fast','legacy'),required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
if not args.execute:raise SystemExit('Requires --execute; only stopped isolated test fixtures')
target=ROOT/f'reports/optimization-final-regressions-{args.mode}-68f32db.json'
if target.exists():raise SystemExit('Refusing existing evidence '+str(target))
if live('Perf') or not all(stopped(server) for server in PORTS):raise SystemExit('Stop all selected test JVMs first')
source=sorted((ROOT/'src/main/java').rglob('*.java'))
source_hash=hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest() for p in source)).hexdigest()
expected=json.loads((ROOT/'reports/optimization-artifact-ready-final.json').read_text())
if source_hash!=expected['source_manifest_sha256']:raise SystemExit('Core source does not match declared regression revision')
report={'operator_runtime_revision':CORE,'mode':args.mode,'source_manifest_sha256':source_hash,'transfer_flags':{'transfer.channelBatches':str(args.mode!='legacy').lower(),'transfer.localFastPath':str(args.mode=='fast').lower()},'runs':[],'passed':False,'scope':'Actual three Minecraft JVMs and isolated MySQL/Redis. Not a timed performance run. Online authentication, GUI and third-party save atomicity are not proved.'}
save()
try:
    subprocess.run(['python3','scripts/configure-optimization.py','--label','regression-68f32db-'+args.mode,'--mode',args.mode],cwd=ROOT,check=True)
    start()
    run_case('three-server-test.py','three')
    run_case('optimization-topology-test.py','topology')
    if args.mode=='fast':
        run_case('fault-test.py','faults')
        run_case('recovery-test.py','recovery')
        run_case('mysql-outage-test.py','mysql')
        run_case('optimization-restart-fallback-test.py','fallback')
    report['passed']=True
except BaseException as error:
    report['failure']=type(error).__name__+': '+str(error);raise
finally:
    try:stop()
    except Exception as error:report['stop_failure']=type(error).__name__+': '+str(error);report['passed']=False
    report['utc_end']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());save()
