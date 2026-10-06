#!/usr/bin/env python3
"""Run serial three-JVM container, pressure and A/B/C performance comparisons in fresh isolated fixtures.
Requires prebuilt launch profiles, real dev backends, existing EULA acceptance and --execute.
"""
from pathlib import Path
import sys, subprocess, time, json, hashlib, fcntl, argparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rcon import command
from optimization_sequence_input import select_original

PORTS={'A':25575,'B':25576,'C':25577}
OLD='87bf217fcaffcceb2629c36bb54d5158b9f461e8'
NEW='68f32db439f445b8f72faf92dc62fbc5b9dce738'
BASELINE='reports/optimization-baseline-87bf217-20261006T090251Z-7859e9.json'
FROZEN={
 'A':'scratch/dev-launch/461a2a5e6d514b3d8dee60815d06907f/runServerA.sh',
 'B':'scratch/dev-launch/6abe4cc458594e518651384c893118dd/runServerB.sh',
 'C':'scratch/dev-launch/3ebbae306b2a47d1b42860767294a5de/runServerC.sh'}

def live(server):
    marker=('server'+server+'RunVmArgs.txt').encode(); result=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            args=(p/'cmdline').read_bytes().split(b'\0')
            if args and args[0].endswith(b'/java') and any(marker in a for a in args):result.append(int(p.name))
        except (FileNotFoundError,PermissionError):pass
    return result

def stopped(server):
    if live(server):return False
    with (ROOT/f'scratch/server-{server}.launch.lock').open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
        except BlockingIOError:return False

def stop():
    for server,port in PORTS.items():
        if live(server):
            try:command(port,'stop')
            except OSError:pass
    deadline=time.monotonic()+90
    while not all(stopped(s) for s in PORTS):
        if time.monotonic()>deadline:raise RuntimeError('Clean stop timeout; no automatic force kill')
        time.sleep(.5)

def start(label,old):
    for server in PORTS:
        args=['bash','scripts/start-frozen-dev.sh',server,FROZEN[server]] if old else ['bash','scripts/start-dev.sh',server]
        with (ROOT/f'logs/optimization-{label}-{server}.log').open('w') as log:
            subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+120
    for server,port in PORTS.items():
        while True:
            try:
                if 'STATUS online' in command(port,'ct_test status',timeout=5):break
            except OSError:pass
            if time.monotonic()>deadline:raise RuntimeError('Startup timeout '+server)
            time.sleep(1)

def configure(label,mode,old=False):
    stop()
    subprocess.run(['python3','scripts/configure-optimization.py','--label',label,'--mode',mode],cwd=ROOT,check=True)
    start(label,old)

def measure(kind,label,args,revision):
    pattern='optimization-container-'+label+'-*.json' if kind=='container' else 'optimization-'+label+'-*.json'
    before=set((ROOT/'reports').glob(pattern))
    script='optimization-container-benchmark.py' if kind=='container' else 'optimization-benchmark.py'
    cmd=['python3','scripts/'+script,'--label',label]+args
    entry={'command':cmd,'loaded_source_revision_declared':revision,'utc_start':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'log':f'logs/optimization-{label}.log'}
    report['runs'].append(entry);save()
    print('START',label,entry['utc_start'],flush=True)
    with (ROOT/entry['log']).open('w') as log:result=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    files=set((ROOT/'reports').glob(pattern))-before
    if len(files)!=1:raise RuntimeError('Missing/ambiguous report '+label)
    path=next(iter(files));body=json.loads(path.read_text())
    entry.update(report=str(path.relative_to(ROOT)),exit_code=result.returncode,utc_end=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),failures=body.get('failures',[]),regressions=body.get('regressions',[]),report_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    save();print('END',label,'exit',result.returncode,'failures',entry['failures'],flush=True)
    if entry['failures'] or not body.get('passed',False):
        # The primary driver can return nonzero for a recorded performance regression.
        if kind=='container' or entry['failures']:raise RuntimeError('Functional failure, retained report '+str(path))
    return str(path.relative_to(ROOT))

def save():
    target=ROOT/f'reports/optimization-final-sequence-{stage}-68f32db.json'
    target.write_text(json.dumps(report,indent=2)+'\n')

parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['original','current'],required=True);parser.add_argument('--container-suffix',default='');parser.add_argument('--execute',action='store_true');parser.add_argument('--original-launch-manifest',type=Path,help='JSON map A/B/C to pre-frozen original launch scripts; required only for --stage original');parser.add_argument('--original-sequence-report',type=Path,help='Required for current: explicit completed original sequence JSON, including its child SHA-256 values')
args=parser.parse_args();stage=args.stage
if not args.execute:raise SystemExit('Requires --execute; isolated development only')
if (ROOT/f'reports/optimization-final-sequence-{stage}-68f32db.json').exists():raise SystemExit('Refusing existing evidence; archive explicitly before a new run')
if any(live(s) for s in (*PORTS,'Perf')):raise SystemExit('Normally stop all selected test JVMs first')
if stage=='original':
    if args.original_launch_manifest is None:raise SystemExit('Original source launch manifest is required; do not label current classes as baseline')
    if args.original_launch_manifest.stat().st_size>8192:raise SystemExit('Oversized launch manifest')
    FROZEN=json.loads(args.original_launch_manifest.read_text())
    if set(FROZEN)!=set(PORTS):raise SystemExit('Original launch manifest must contain exactly A/B/C')
report={'stage':stage,'loaded_source_revision_declared':OLD if stage=='original' else NEW,'runs':[],
        'source_manifest_sha256':hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest() for p in sorted((ROOT/'src/main/java').rglob('*.java')))).hexdigest(),
        'jar_sha256':hashlib.sha256((ROOT/'build/libs/cross_tesseract-0.1.0-dev.jar').read_bytes()).hexdigest(),
        'workspace_artifact_scope':'These hashes describe this checked-out workspace and built JAR. Original stage actually starts the supplied frozen classes/resources; its loaded revision remains operator-declared and is documented by child launch manifests, not by the current workspace JAR hash.',
        'observers':'Single RCON workload observer only; no concurrent RCON/tick/SQL/JFR sidecars. Current per-run scripts retain their own fixed monitoring reads.',
        'passed_definition':'All requested procedures and functional gates completed; performance regressions remain separately recorded in every run and are not erased.',
        'procedure_completed':False,'performance_regressions':[], 'passed':False}
if stage=='current':
    if args.original_sequence_report is None:raise SystemExit('Current stage requires --original-sequence-report; no implicit historical baseline')
    report['original_evidence']=select_original(ROOT,args.original_sequence_report,OLD)
    expected=json.loads((ROOT/'reports/optimization-artifact-ready-final.json').read_text())
    binary=next(item for item in expected['artifacts'] if item['path']=='build/libs/cross_tesseract-0.1.0-dev.jar')
    if report['source_manifest_sha256']!=expected['source_manifest_sha256'] or report['jar_sha256']!=binary['sha256']:raise SystemExit('Core source/JAR does not match the declared performance revision')
else:
    report['original_launch_manifest']={'path':str(args.original_launch_manifest),'sha256':hashlib.sha256(args.original_launch_manifest.read_bytes()).hexdigest(),'launches':FROZEN}
save()
try:
    old=stage=='original';revision=OLD if old else NEW;tag='original' if old else 'current'
    container_label='container-'+tag+args.container_suffix+('' if old else '-'+revision[:7])
    configure(container_label,'legacy' if old else 'fast',old)
    measure('container',container_label+'-'+revision[:7],[
        '--operator-revision',revision,'--scenarios','same,cross,mixed','--probes','2','--timeout','420','--idle','2.2','--poll','.1','--execute'],revision)
    # Successful container cleanup proves empty buffers/allocations/chests before removal.
    pressure_args=['--scenarios','backpressure,hotspot','--warmup','30','--seconds','120','--repeats','3','--probes','0']
    if not old:
        original_pressure=report['original_evidence']['stages']['pressure']['report']
        pressure_args+=['--baseline',original_pressure]
    measure('primary',tag+'-pressure-'+revision[:7],pressure_args,revision)
    primary_args=['--scenarios','same,cross,mixed','--warmup','30','--seconds','120','--repeats','3','--probes','40']
    if old:
        configure('original-final','legacy',True)
        measure('primary','original-final-'+revision[:7],primary_args,revision)
    else:
        final_baseline=report['original_evidence']['stages']['primary']['report']
        configure('batch-final-'+revision[:7],'batch')
        measure('primary','batch-final-'+revision[:7],primary_args+['--baseline',final_baseline],revision)
        configure('fast-final-'+revision[:7],'fast')
        measure('primary','fast-final-'+revision[:7],primary_args+['--baseline',final_baseline],revision)
    report['procedure_completed']=True
    report['performance_regressions']=[{'report':entry['report'],'regressions':entry['regressions']} for entry in report['runs'] if entry.get('regressions')]
    report['passed']=True
except BaseException as error:
    report['failure']=type(error).__name__+': '+str(error);raise
finally:
    try:stop()
    except Exception as error:report['stop_failure']=type(error).__name__+': '+str(error);report['passed']=False
    report['utc_end']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());save()
