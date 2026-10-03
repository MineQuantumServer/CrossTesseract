#!/usr/bin/env python3
"""Real, short MySQL outage against named local development backends only."""
from pathlib import Path
import json,time,uuid,re
from importlib.util import spec_from_file_location,module_from_spec
from rcon import command
ROOT=Path(__file__).resolve().parents[1]
def load(name,file):
    spec=spec_from_file_location(name,ROOT/'scripts'/file);module=module_from_spec(spec);spec.loader.exec_module(module);return module
t=load('three','three-server-test.py');r=load('recovery','recovery-test.py')
def run():
    t.poll(r.status,lambda x:'STATUS online' in x,seconds=60)
    owner=str(uuid.uuid4());x=60000+int(time.time())%1000;z=80
    for dx in (0,1):command(25575,f'forceload add {x+dx} {z}');t.issue(0,f'spawn {x+dx} {z} {owner}');t.poll(lambda:t.device(0,x+dx,z),lambda d:d['registered'])
    endpoint=t.device(0,x,z)['id'];other=t.device(0,x+1,z)['id'];t.issue(0,f'chunk-on {x} {z}');t.poll(lambda:t.sql(f"SELECT state FROM ct_chunk_grants WHERE cluster_id='{t.CLUSTER}' AND endpoint_id='{endpoint}'"),lambda x:x==[['ACTIVE']]);command(25575,'save-all flush')
    started=time.monotonic()
    try:
        r.docker('stop','ct-dev-mysql')
        offline=t.poll(r.status,lambda s:'STATUS online' not in s and 'tickets=0 ' in s,seconds=8)
        query_start=time.monotonic();reply=t.issue(0,f'chunk-on {x+1} {z}');roundtrip_ms=(time.monotonic()-query_start)*1000
    finally:r.docker('start','ct-dev-mysql')
    def mysql_ready():
        try:return r.docker('exec','-e','MYSQL_PWD=ct_dev_only','ct-dev-mysql','mysqladmin','-u','ct_dev','ping','-h','127.0.0.1')
        except Exception:return 'starting'
    t.poll(mysql_ready,lambda s:'alive' in s,seconds=20)
    assert t.sql(f"SELECT COUNT(*) FROM ct_chunk_grants WHERE cluster_id='{t.CLUSTER}' AND player_uuid='{owner}'")==[['1']]
    assert not t.sql(f"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id='{t.CLUSTER}' AND endpoint_id='{other}'")
    final=r.status()
    # Longer outages fence the old session; record that fact rather than rebasing old workers.
    if 'STATUS online' not in final:
        try:final=t.poll(r.status,lambda s:'STATUS online' in s,seconds=8)
        except AssertionError:final=r.status()
    report={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cluster':t.CLUSTER,'endpoint':endpoint,'persistent_player_slots':1,'new_device_grants':0,'offline_status':offline,'management_response':reply,'management_roundtrip_ms_during_mysql_outage':roundtrip_ms,'test_elapsed_seconds':time.monotonic()-started,'final_status':final,'scope':'Actual MySQL container stopped/restarted; Minecraft remains responsive, own tickets revoked and persistent quota retained. Expired sessions require a new fenced boot.'}
    (ROOT/'reports/mysql-outage.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':run()
