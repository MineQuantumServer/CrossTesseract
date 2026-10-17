#!/usr/bin/env python3
"""Fresh, explicit, isolated native RC faults. No existing world/ledger is reset.
Requires existing operator-accepted EULA AND --accept-eula; the flag is an operator assertion.
No execution without --execute. Failure logs and positive retained assets are preserved.
"""
import argparse,hashlib,json,re,signal,subprocess,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def sources():return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest() for p in sorted((ROOT/'src/main/java').rglob('*.java')))).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--accept-eula',action='store_true');args=p.parse_args()
 if not args.execute:print('NOT_RUN: requires --execute --accept-eula; only new isolated fixtures');return 0
 if not args.accept_eula:raise ValueError('operator must first accept https://www.minecraft.net/eula')
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   argv=(proc/'cmdline').read_bytes().split(b'\0')
   if argv and argv[0].endswith(b'/java') and any(re.search(rb'(server[ABC]|gameTestServer)RunVmArgs\.txt',a) for a in argv):raise RuntimeError('normally stop native test JVMs before starting this separate fault run')
  except (FileNotFoundError,PermissionError):pass
 original=(ROOT/'config/gametest.properties').read_text();values=dict(line.split('=',1) for line in original.splitlines() if '=' in line and not line.lstrip().startswith('#'))
 if not(values.get('cluster.id','').startswith('test_') and values.get('mysql.user')=='ct_dev' and values.get('mysql.url','').startswith('jdbc:mysql://127.0.0.1:13306/cross_tesseract?') and values.get('redis.uri')=='redis://127.0.0.1:16379'):raise ValueError('isolated test backend required')
 token='fault-'+uuid.uuid4().hex[:12];out=ROOT/'scratch/rc-native'/token;out.mkdir(parents=True);game=out/'game';game.mkdir()
 lines=[line for line in original.splitlines() if not line.startswith(('cluster.id=','server.id=','transfer.channelBatches=','transfer.localFastPath=','transfer.maxBatchRecords=','transfer.maxBatchDevices='))]
 lines+=['cluster.id=test_rcnative_'+token.replace('-','_'),'server.id='+token,'transfer.channelBatches=true','transfer.localFastPath=true','transfer.maxBatchRecords=192','transfer.maxBatchDevices=8']
 (out/'backend.properties').write_text('\n'.join(lines)+'\n');(game/'eula.txt').write_text('eula=true\n');(game/'server.properties').write_text('server-ip=127.0.0.1\nonline-mode=false\nenable-rcon=false\n')
 report={'fixture':token,'cluster':'test_rcnative_'+token.replace('-','_'),'source_manifest_sha256':sources(),'utc_start':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'passed':False,'operator_asserted_EULA':True,'scope':'real Minecraft/Authority/WAL; capacity exhaustion and controlled worker interruption after first actual publication group; not power loss or COMMIT ACK loss'}
 build=['scripts/gradle-dev.sh','--no-daemon','--max-workers=2','classes','jar','createGameTestServerLaunchScript','-PrcFaultTests','-PrcFixture='+token];report['build_command']=build
 try:
  with (out/'build.log').open('x') as stream:built=subprocess.run(build,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
  report['build_exit']=built.returncode
  if built.returncode:raise RuntimeError('native fault build failed; no Minecraft launched')
  jar=ROOT/'build/libs/cross_tesseract-0.1.0-dev.jar';report['JAR_sha256']=digest(jar)
  if sources()!=report['source_manifest_sha256']:raise RuntimeError('source changed during build')
  # Use immutable classes/resources/argument copies, as the three-server launcher does.
  frozen=subprocess.check_output(['flock','-s','scratch/dev-build.lock','python3','scripts/freeze-dev-launch.py','build/moddev/runGameTestServer.sh'],cwd=ROOT,text=True,timeout=30).strip()
  launcher=Path(frozen);expected=ROOT/'scratch/dev-launch'
  if launcher.parent.parent!=expected or not re.fullmatch('[a-f0-9]{32}',launcher.parent.name) or launcher.name!='runGameTestServer.sh':raise RuntimeError('unexpected immutable GameTest launcher')
  report['frozen_launcher']=str(launcher.relative_to(ROOT));report['frozen_launcher_sha256']=digest(launcher)
  with (out/'native.log').open('x') as stream:
   proc=subprocess.Popen(['bash',str(launcher)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
   report['pid']=proc.pid
   try:report['native_exit']=proc.wait(timeout=120)
   except subprocess.TimeoutExpired:
    report['native_timeout']=True;proc.send_signal(signal.SIGTERM)
    try:report['SIGTERM_exit']=proc.wait(timeout=30)
    except subprocess.TimeoutExpired:report['owned_process_still_running']=True
    raise RuntimeError('native timeout; SIGTERM requested, no hard kill/refund/replay')
  text=(out/'native.log').read_text();report['capacity_positive_pass_marker']='CT_RC_CAPACITY_PASS' in text;report['actual_split_positive_pass_marker']='CT_RC_GROUP_PASS' in text
  report['passed']=report['native_exit']==0 and all(report[k] for k in ('capacity_positive_pass_marker','actual_split_positive_pass_marker')) and 'required tests passed' in text and ' failed at ' not in text
 except Exception as failure:report['failure']=type(failure).__name__+': '+str(failure)
 finally:
  report['utc_end']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());report['source_unchanged']=sources()==report['source_manifest_sha256'];report['passed']=report['passed'] and report['source_unchanged'];report['logs']={f.name:digest(f) for f in out.glob('*.log')}
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':report['passed'],'report':str((out/'result.json').relative_to(ROOT))}))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
