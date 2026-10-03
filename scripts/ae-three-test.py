#!/usr/bin/env python3
"""Three actual AE-enabled Minecraft JVMs: native storage plus experimental shadow nodes.
Requires AE prototype launch configs; reports proxy semantics, never claims native JVM grids merge.
"""
from pathlib import Path
import json,re,time,uuid
from importlib.util import spec_from_file_location,module_from_spec
from rcon import command
ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('three',ROOT/'scripts/three-server-test.py');t=module_from_spec(spec);spec.loader.exec_module(t)
def ae(server,x,z,action,*args):return t.issue(server,f'ae-test {x} {z} {action} '+ ' '.join(map(str,args)))
def state(server,x,z):
    try:return json.loads(re.search(r'AE_TEST (\{.*\})',ae(server,x,z,'state'))[1])
    except AssertionError as e:
        if 'ae_peer_unconfirmed' not in str(e):raise
        return {'state':'starting','grid':None,'shadows':-1,'activeShadows':-1,'active':False}
def amount(server,x,z,action,resource,n):return int(re.search(r'AE_TEST (\d+)',ae(server,x,z,action,resource,n))[1])
def run():
    def ready(i):
        try:return t.issue(i,'status')
        except OSError:return 'starting'
    for i in range(3):t.poll(lambda:ready(i),lambda s:'STATUS online' in s,seconds=60)
    capabilities=t.sql(f"SELECT server_id,capabilities FROM ct_servers WHERE cluster_id='{t.CLUSTER}' AND server_id IN ('dev-A','dev-B','dev-C') ORDER BY server_id");assert len(capabilities)==3 and all('ae_proxy_v1' in r[1] for r in capabilities),capabilities
    owner=str(uuid.uuid4());member=str(uuid.uuid4());name='ae_three_'+uuid.uuid4().hex[:8];t.issue(0,f'create {owner} {name}');channel=t.poll(lambda:t.sql(f"SELECT channel_id FROM ct_channels WHERE cluster_id='{t.CLUSTER}' AND name='{name}'"),bool)[0][0]
    t.issue(0,f'invite {owner} {channel} {member}');inv=t.poll(lambda:t.sql(f"SELECT invite_id FROM ct_invites WHERE cluster_id='{t.CLUSTER}' AND channel_id='{channel}'"),bool)[0][0];t.issue(1,f'accept {member} {inv}')
    x=65000+int(time.time())%1000;z=96;devices=[]
    for i in range(3):
        command(t.PORTS[i],f'forceload add {x-16} {z-16} {x+16} {z+16}');t.issue(i,f'spawn {x} {z} {member if i==1 else owner}');d=t.poll(lambda:t.device(i,x,z),lambda d:d['registered']);devices.append(d['id']);t.issue(i,f'bind {x} {z} {channel}');t.poll(lambda:t.device(i,x,z),lambda d:d['channel']==channel and not d['pause']);t.issue(i,f'mode {x} {z} cross_tesseract:item {"SEND" if i==0 else "RECEIVE"}');t.issue(i,f'mode {x} {z} cross_tesseract:fe {"SEND" if i==0 else "RECEIVE"}');t.issue(i,f'sides {x} {z} cross_tesseract:fe 2');command(t.PORTS[i],f'setblock {x-1} 64 {z} ae2:creative_energy_cell');t.issue(i,f'ae {x} {z} true')
    native=t.poll(lambda:[state(i,x,z) for i in range(3)],lambda states:all(s['state']=='ae_proxy_experimental' and s['shadows']==2 and s['activeShadows']==2 and s['active'] for s in states),seconds=35)
    checks=['three JVMs advertise real native grid identities; each installs two real remote channel consumers and requires local power']
    assert amount(1,x,z,'extract','minecraft:diamond',5)==0 and amount(2,x,z,'extract','minecraft:diamond',5)==0,'native misses must return immediately, without exposing remote inventory'
    pending=t.poll(lambda:t.sql(f"SELECT endpoint_id,amount,remaining,state FROM ct_stock_requests WHERE cluster_id='{t.CLUSTER}' AND channel_id='{channel}' ORDER BY endpoint_id"),lambda rows:len(rows)==2)
    assert all(row[1:]==['5','5','PENDING'] for row in pending),pending
    checks.append('B/C native misses immediately return zero and persist separate authorized directed requests; no balance is created by intent')
    accepted=t.poll(lambda:amount(0,x,z,'insert','minecraft:diamond',24),lambda n:n==24)
    t.poll(lambda:[t.device(i,x,z) for i in range(3)],lambda ds:sum(d['rxItem'] for d in ds)==24 and ds[0]['txItem']==0)
    extracted=sum(amount(i,x,z,'extract','minecraft:diamond',24) for i in (1,2));assert extracted==accepted==24,extracted
    t.poll(lambda:t.issue(0,f'push-fe {x} {z} 12345'),lambda s:'ACCEPTED 12345' in s);t.poll(lambda:[t.device(i,x,z) for i in range(3)],lambda ds:sum(d['rxFE'] for d in ds)==12345 and ds[0]['txFE']==0)
    checks.append('native synchronous AE insertion -> actual SQL/WAL allocations -> two remote AE extraction interfaces: total 24 diamonds; FE remains usable across differing optional mod combinations')
    # A second bridge shares the same actual native grid and must not become another remote grid.
    t.issue(0,f'spawn {x+1} {z} {owner}');t.poll(lambda:t.device(0,x+1,z),lambda d:d['registered']);t.issue(0,f'bind {x+1} {z} {channel}');t.poll(lambda:t.device(0,x+1,z),lambda d:d['channel']==channel and not d['pause']);t.issue(0,f'ae {x+1} {z} true');
    t.poll(lambda:[state(0,x,z),state(0,x+1,z)],lambda ss:ss[0]['grid']==ss[1]['grid'],seconds=20);time.sleep(8)
    advertised=t.sql(f"SELECT server_id,COUNT(DISTINCT network_id) FROM ct_ae_networks WHERE cluster_id='{t.CLUSTER}' AND channel_id='{channel}' AND lease_until>CURRENT_TIMESTAMP(6) GROUP BY server_id ORDER BY server_id");assert advertised==[['dev-A','1'],['dev-B','1'],['dev-C','1']],advertised
    t.poll(lambda:[state(i,x,z) for i in (1,2)],lambda ss:all(s['shadows']==3 and s['activeShadows']==3 for s in ss),seconds=25)
    checks.append('two bridges on the same actual A grid advertise one grid; B/C account for two A consumers without recursively multiplying shadows')
    command(t.PORTS[1],f'setblock {x-1} 64 {z} air');t.poll(lambda:[state(i,x,z) for i in (0,2)],lambda ss:all(s['shadows']==0 for s in ss),seconds=15);assert amount(1,x,z,'extract','minecraft:diamond',1)==0
    checks.append('native B power loss withdraws experimental proxy admission on A/C and blocks B synchronous storage')
    command(t.PORTS[1],f'setblock {x-1} 64 {z} ae2:creative_energy_cell');t.poll(lambda:[state(i,x,z) for i in (1,2)],lambda ss:all(s['state']=='ae_proxy_experimental' for s in ss),seconds=25)
    t.issue(0,f'remove-member {owner} {channel} {member}');t.poll(lambda:t.device(1,x,z),lambda d:d['pause']=='forbidden');t.poll(lambda:state(1,x,z),lambda s:s['shadows']==0);assert amount(1,x,z,'insert','minecraft:stone',1)==0
    checks.append('member removal suspends B native proxy nodes and storage; surviving authorized grids continue independently')
    report={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cluster':t.CLUSTER,'channel':channel,'endpoints':devices,'server_capabilities':capabilities,'initial_native_states':native,'checks':checks,'ae_level1':'actual cross-JVM material bridge verified','ae_level2':'experimental real-node proxy verified; native IGrid/controller/power/security/crafting/request merge NOT implemented'}
    (ROOT/'reports/ae-three.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':run()
