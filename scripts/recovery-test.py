#!/usr/bin/env python3
"""Isolated real-server restart, Redis loss and hard-crash recovery tests.

Only local dev fixture servers and named dev Docker containers are affected.
"""
import json
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid
from rcon import command
from importlib.util import spec_from_file_location,module_from_spec

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('three',ROOT/'scripts/three-server-test.py');three=module_from_spec(spec);spec.loader.exec_module(three)
sql,poll=three.sql,three.poll
CLUSTER=three.CLUSTER

def status():
    try:return command(25575,'ct_test status')
    except OSError:return 'starting'

def launch():
    log=(ROOT/'logs/recovery-server-A.log').open('a')
    process=subprocess.Popen(['bash','scripts/start-dev.sh','A'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    poll(status,lambda t:'STATUS online' in t,seconds=60)
    return process

def wait_stopped():
    # Do not issue RCON commands while vanilla is shutting down. A queued command can deadlock
    # RconClient.executeBlocking against GenericThread.stop; observe process exit instead.
    poll(launcher_stopped,bool,seconds=30)

def launcher_stopped():
    if jvms():return False
    with (ROOT/'scratch/server-A.launch.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
        except BlockingIOError:return False

def jvms():
    matching=[]
    for proc in Path('/proc').iterdir():
        if proc.name.isdigit():
            try:
                args=(proc/'cmdline').read_bytes().split(b'\0')
                if args and args[0].endswith(b'/java') and any(b'serverARunVmArgs.txt' in a for a in args):matching.append(int(proc.name))
            except (FileNotFoundError,PermissionError):pass
    return matching

def docker(*args):
    env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    return subprocess.run(['docker','--host=unix:///var/run/docker.sock',*args],env=env,capture_output=True,text=True,check=True).stdout

def run():
    checks=[];initial=poll(status,lambda t:'STATUS online' in t,seconds=60)
    import re
    owner=str(uuid.uuid4());x=int(time.time())%2000+20000;z=48
    command(25575,f'forceload add {x} {z}')
    three.issue(0,f'spawn {x} {z} {owner}')
    be=poll(lambda:three.device(0,x,z),lambda r:r['registered']);eid=be['id']
    three.issue(0,f'chunk-on {x} {z}')
    poll(lambda:sql(f"SELECT state FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND endpoint_id='{eid}'"),lambda r:r==[['ACTIVE']])
    # A restored server can become online before its bounded ticket work finishes.
    # Count authoritative eligible grants, rather than sampling a partial startup count.
    expected_tickets=int(sql(f"SELECT COUNT(*) FROM ct_chunk_grants g JOIN ct_endpoints e ON e.cluster_id=g.cluster_id AND e.endpoint_id=g.endpoint_id WHERE g.cluster_id='{CLUSTER}' AND e.server_id='dev-A' AND e.state='ACTIVE' AND g.desired=TRUE")[0][0])
    command(25575,f'forceload remove {x} {z}')
    command(25575,'save-all flush')
    command(25575,'stop');wait_stopped();launch()
    poll(status,lambda t:f'tickets={expected_tickets} ' in t,seconds=20)
    assert three.device(0,x,z)['id']==eid
    assert sql(f"SELECT COUNT(*) FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'")==[['1']]
    checks.append('clean restart restores authorized ticking ticket without prior block ticking/player login; quota stays one')
    docker('stop','ct-dev-redis')
    poll(status,lambda t:'STATUS online' not in t and 'tickets=0 ' in t,seconds=8)
    assert sql(f"SELECT COUNT(*) FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'")==[['1']]
    checks.append('Redis unavailable removes actual mod ticket and preserves persistent quota')
    docker('start','ct-dev-redis');poll(status,lambda t:'STATUS online' in t and f'tickets={expected_tickets} ' in t,seconds=20)
    docker('exec','ct-dev-redis','redis-cli','FLUSHDB')
    poll(status,lambda t:'STATUS online' in t,seconds=10)
    assert sql(f"SELECT COUNT(*) FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'")==[['1']]
    checks.append('Redis restart and complete hint/cache deletion do not remove authoritative quota')
    # Kill only this fixture's exact local launch JVM.
    matching=jvms()
    assert len(matching)==1,matching
    os.kill(matching[0],signal.SIGKILL);wait_stopped()
    poll(lambda:sql(f"SELECT lease_until<CURRENT_TIMESTAMP(6) FROM ct_servers WHERE cluster_id='{CLUSTER}' AND server_id='dev-A'"),lambda r:r==[['1']],seconds=20)
    launch()
    assert sql(f"SELECT state FROM ct_endpoints WHERE cluster_id='{CLUSTER}' AND endpoint_id='{eid}'")==[['QUARANTINED']]
    assert sql(f"SELECT COUNT(*) FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'")==[['1']]
    assert 'tickets=0 ' in status()
    checks.append('hard-killed Minecraft JVM rejoins with fenced epoch, quarantines external-save uncertainty and retains quota without restoring ticket')
    # Remote close can be acknowledged after the inactive endpoint registers its current fenced epoch.
    command(25575,f'forceload add {x} {z}')
    poll(lambda:three.device(0,x,z),lambda r:r['registered'])
    three.issue(0,f'chunk-off {x} {z}')
    poll(lambda:sql(f"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND endpoint_id='{eid}'"),lambda r:not r)
    command(25575,f'forceload remove {x} {z}')
    report={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cluster':CLUSTER,'endpoint':eid,'checks':checks,'final_status':status(),'scope':'actual Minecraft JVM, real Redis/MySQL; arbitrary external chest rollback is not made atomic'}
    (ROOT/'reports/recovery.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':run()
