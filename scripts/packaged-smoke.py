#!/usr/bin/env python3
"""Cold official dedicated server, final Jar-in-Jar, no Gradle development classpath."""
from pathlib import Path
import hashlib,json,os,re,subprocess,time,uuid
from importlib.util import spec_from_file_location,module_from_spec
from rcon import command
ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('three',ROOT/'scripts/three-server-test.py');t=module_from_spec(spec);spec.loader.exec_module(t)
DIRECTORY=ROOT/'scratch/packaged/server';PORT=25579;CLUSTER='dev_packaged_v1'
def issue(value):
    result=command(PORT,'ct_test '+value)
    if 'ERROR ' in result:raise AssertionError(result)
    return result
def device(x):
    s=issue(f'inspect {x} 0');return {'id':re.search(r'DEVICE ([\w-]+)',s)[1],**dict(re.findall(r'(\w+)=(\S*)',s))}
def run():
    jar=DIRECTORY/'mods/cross_tesseract-0.1.0-dev.jar';assert jar.exists(),'Run install-packaged-dev.sh --accept-eula first'
    assert list((DIRECTORY/'mods').glob('*.jar'))==[jar],'This smoke install must contain only our mod'
    config=(DIRECTORY/'config/cross-tesseract.properties').read_text();assert f'cluster.id={CLUSTER}' in config and '127.0.0.1:13306' in config and '127.0.0.1:16379' in config
    env={k:v for k,v in os.environ.items() if k not in ('CT_MYSQL_URL','CT_MYSQL_USER','CT_MYSQL_PASSWORD','CT_REDIS_URI')}
    log=ROOT/'logs/packaged-smoke.log';log.parent.mkdir(exist_ok=True)
    jvm=ROOT/'scratch/jdk/jdk-21.0.8+9/bin/java';p=None;passed=False
    with log.open('w') as out:
        try:
            p=subprocess.Popen([str(jvm),'-Xmx2G','-Dcross_tesseract.testHarness=true','@user_jvm_args.txt','@libraries/net/neoforged/neoforge/21.1.252/unix_args.txt','--nogui'],cwd=DIRECTORY,env=env,stdout=out,stderr=subprocess.STDOUT)
            def ready():
                if p.poll() is not None:raise AssertionError(f'Cold server exited {p.returncode}; see {log}')
                try:return issue('status')
                except OSError:return 'starting'
            t.poll(ready,lambda s:'STATUS online' in s,seconds=90)
            owner=str(uuid.uuid4());name='packaged_'+uuid.uuid4().hex[:10];issue(f'create {owner} {name}')
            ch=t.poll(lambda:t.sql(f"SELECT channel_id FROM ct_channels WHERE cluster_id='{CLUSTER}' AND name='{name}'"),bool)[0][0]
            # Fresh isolated coordinates; the former time modulo reused sealed locations.
            x=1_000_000+int(uuid.uuid4().hex[:5],16)*16;command(PORT,f'forceload add {x} 0 {x+1} 0')
            for dx,mode in ((0,'SEND'),(1,'RECEIVE')):
                issue(f'spawn {x+dx} 0 {owner}');t.poll(lambda:device(x+dx),lambda d:d['registered']=='true');issue(f'bind {x+dx} 0 {ch}');t.poll(lambda:device(x+dx),lambda d:d['channel']==ch and not d['pause']);issue(f'mode {x+dx} 0 cross_tesseract:fe {mode}')
            t.poll(lambda:issue(f'push-fe {x} 0 1234'),lambda s:'ACCEPTED 1234' in s)
            t.poll(lambda:device(x+1),lambda d:d['rxFE']=='1234');assert 'EXTRACTED 1234' in issue(f'pull-fe {x+1} 0 1234')
            capabilities=t.sql(f"SELECT capabilities FROM ct_servers WHERE cluster_id='{CLUSTER}' AND server_id='dev-packaged'")[0][0]
            assert all(k not in capabilities for k in ('gt_eu','mek_chemical','ae_storage')),capabilities
            command(PORT,'save-all flush');status=issue('status');passed=True
        finally:
            if p is not None and p.poll() is None:
                try:command(PORT,'stop')
                except OSError:pass
                try:p.wait(timeout=30)
                except subprocess.TimeoutExpired:p.kill();p.wait();raise AssertionError('Cold server shutdown timed out; marked unclean')
    assert passed and p.returncode==0, f'Cold server shutdown exit {p.returncode}'
    report={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'passed':True,'scope':'official NeoForge installer, actual packaged mod Jar-in-Jar only; no optional mods; real MySQL/Redis, two native FE capabilities and SQL/WAL delivery, clean stop','jar':str(jar.relative_to(ROOT)),'sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),'minecraft':'1.21.1','neoforge':'21.1.252','capabilities':capabilities,'status':status,'log':str(log.relative_to(ROOT)),'java_exit_code':p.returncode,'fixture':{'source_x':x,'sink_x':x+1,'z':0,'owner_uuid':owner,'channel_id':ch,'FE_accepted_and_extracted':1234}}
    (ROOT/'reports/packaged-smoke.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':run()
