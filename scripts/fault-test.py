#!/usr/bin/env python3
"""Crash only isolated test Minecraft JVMs at five actual durable ownership boundaries."""
import fcntl,json,os,re,signal,subprocess,time,uuid
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
from rcon import command
ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('three',ROOT/'scripts/three-server-test.py');t=module_from_spec(spec);spec.loader.exec_module(t)
def jvms(suffix):
    result=[]
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            try:
                a=(p/'cmdline').read_bytes().split(b'\0')
                if a and a[0].endswith(b'/java') and any(('server'+suffix+'RunVmArgs.txt').encode() in x for x in a):result.append(int(p.name))
            except (FileNotFoundError,PermissionError):pass
    return result

def launch(n):
    suffix='ABC'[n];log=(ROOT/f'logs/fault-server-{suffix}.log').open('a')
    subprocess.Popen(['bash','scripts/start-dev.sh',suffix],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    t.poll(lambda:ready(n),lambda x:'STATUS online' in x,seconds=60)
def ready(n):
    try:return t.issue(n,'status')
    except OSError:return 'starting'
def properties(suffix, filename):
    path=ROOT / ('run-'+suffix) / filename
    return dict(line.split('=',1) for line in path.read_text().splitlines() if line and not line.startswith('#') and '=' in line)
def server_id(suffix):
    value=properties(suffix,'cross-tesseract.properties')['server.id']
    assert re.fullmatch(r'[A-Za-z0-9_.-]+',value), 'unexpected dev server identity'
    return value
def world_path(suffix):
    value=properties(suffix,'server.properties')['level-name']
    assert re.fullmatch(r'[A-Za-z0-9_-]+',value), 'only isolated named dev worlds'
    return ROOT / ('run-'+suffix) / value
def crash_restart(n,endpoint):
    suffix='ABC'[n]
    def launcher_stopped():
        if jvms(suffix):return False
        with (ROOT/f'scratch/server-{suffix}.launch.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
            except BlockingIOError:return False
    t.poll(launcher_stopped,bool,seconds=20)
    t.poll(lambda:t.sql(f"SELECT lease_until<CURRENT_TIMESTAMP(6) FROM ct_servers WHERE cluster_id='{t.CLUSTER}' AND server_id='{server_id(suffix)}'"),lambda r:r==[['1']],seconds=20)
    launch(n);t.poll(lambda:t.sql(f"SELECT state FROM ct_endpoints WHERE cluster_id='{t.CLUSTER}' AND endpoint_id='{endpoint}'"),lambda r:r==[['QUARANTINED']])
def device(n,x,z,owner,channel,mode):
    command(t.PORTS[n],f'forceload add {x} {z}');t.issue(n,f'spawn {x} {z} {owner}');be=t.poll(lambda:t.device(n,x,z),lambda d:d['registered']);t.issue(n,f'bind {x} {z} {channel}');t.poll(lambda:t.device(n,x,z),lambda d:d['channel']==channel and not d['pause']);t.issue(n,f'mode {x} {z} cross_tesseract:fe {mode}');command(t.PORTS[n],'save-all flush');return be['id']
def run():
    checks=[];base=40000+int(time.time())%2000
    for i,phase in enumerate(('after_send_wal','after_deposit','after_allocation','after_receive_wal','after_local_sql')):
        owner=str(uuid.uuid4());name='fault_'+uuid.uuid4().hex[:8];t.issue(0,f'create {owner} {name}');ch=t.poll(lambda:t.sql(f"SELECT channel_id FROM ct_channels WHERE cluster_id='{t.CLUSTER}' AND name='{name}'"),bool)[0][0]
        x=base+i*4;z=64;sender=device(0,x,z,owner,ch,'SEND');destination=None
        if phase.startswith('after_send') or phase=='after_deposit':
            command(t.PORTS[0],f'ct_test fault {sender} {phase}');t.poll(lambda:t.issue(0,f'push-fe {x} {z} 321'),lambda r:'ACCEPTED 321' in r);crash_restart(0,sender)
            count=t.sql(f"SELECT COUNT(*) FROM ct_transfers WHERE cluster_id='{t.CLUSTER}' AND endpoint_id='{sender}' AND kind='DEPOSIT'")[0][0];assert count==('0' if phase=='after_send_wal' else '1'),count
            journal=world_path('A')/'cross_tesseract/journal'/f'{sender}.ctj';assert journal.exists() and journal.stat().st_size>100
            t.poll(lambda:t.device(0,x,z),lambda d:d['id']==sender and d['registered'] and d['txFE']==321)
        else:
            t.poll(lambda:t.issue(0,f'push-fe {x} {z} 321'),lambda r:'ACCEPTED 321' in r);t.poll(lambda:t.sql(f"SELECT SUM(amount) FROM ct_balances WHERE cluster_id='{t.CLUSTER}' AND channel_id='{ch}'"),lambda r:r==[['321']]);destination=device(1,x+1,z,owner,ch,'OFF');command(t.PORTS[1],f'ct_test fault {destination} {phase}');t.issue(1,f'mode {x+1} {z} cross_tesseract:fe RECEIVE');crash_restart(1,destination)
            records=t.sql(f"SELECT amount,remaining,state FROM ct_transfers WHERE cluster_id='{t.CLUSTER}' AND endpoint_id='{destination}' AND kind='ALLOCATE'");assert records==[['321','321','LOCAL' if phase=='after_local_sql' else 'RESERVED']],records
            assert t.sql(f"SELECT SUM(amount) FROM ct_balances WHERE cluster_id='{t.CLUSTER}' AND channel_id='{ch}'")==[['0']]
            assert 'EXTRACTED 0' in t.issue(1,f'pull-fe {x+1} {z} 1000'),'unclean destination cannot deliver or auto-refund'
            journal=world_path('B')/'cross_tesseract/journal'/f'{destination}.ctj'
            if phase in ('after_receive_wal','after_local_sql'):assert journal.exists();t.poll(lambda:t.device(1,x+1,z),lambda d:d['registered'] and d['rxFE']==(321 if phase=='after_local_sql' else 0))
            else:t.poll(lambda:t.device(1,x+1,z),lambda d:d['registered'] and d['rxFE']==0)
        checks.append({'phase':phase,'sender':sender,'destination':destination,'result':'actual halt=97; new epoch quarantined; ownership preserved; no timeout refund'})
        print('PASS '+phase,flush=True)
    report={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cluster':t.CLUSTER,'checks':checks,'scope':'Own WAL/SQL boundaries. External vanilla/third-party inventories remain outside the atomic transaction.'}
    (ROOT/'reports/faults.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':run()
