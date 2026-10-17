from pathlib import Path
from datetime import datetime, timezone
import argparse, fcntl, hashlib, json, shutil, uuid, zipfile

ROOT=Path(__file__).resolve().parents[2]
EXPECTED_JAR='1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f'
MATRIX=ROOT/'reports/rc-20261017/native-matrix-final-3647ded-r2-20261017T113417Z-7d0c0d98c45b.json'
F3=ROOT/'scratch/rc-baseline-env-20261017T095358Z-a75d6375/frozen-f3-baseline'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def meta(p):return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def tree(p):
 files=[]
 for f in sorted(p.rglob('*')):
  if f.is_symlink():raise ValueError('No symbolic frozen inputs')
  if f.is_file():files.append(dict(meta(f),relative_path=f.relative_to(p).as_posix()))
 return {'path':str(p),'files':files,'manifest_sha256':hashlib.sha256(json.dumps([{k:v for k,v in f.items() if k!='path'} for f in files],sort_keys=True,separators=(',',':')).encode()).hexdigest()}
def values(t):return {r['relative_path']:r['sha256'] for r in t['files']}
p=argparse.ArgumentParser();p.add_argument('--profile',choices=('f3','final'),required=True);p.add_argument('--agent-manifest',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
if not a.execute:print(json.dumps({'execution':'NOT_RUN','profile':a.profile,'requires':'--execute; released build/native window'}));raise SystemExit(0)
lock=(ROOT/'scratch/dev-build.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
matrix=json.loads(MATRIX.read_text());assert matrix['passed'] and matrix['full_matrix_gate'] and matrix['source_and_locks_unchanged'] and matrix['actual_required_tests_passed']==156
source_proof=Path(matrix['source_manifest']['path']);source_proof=source_proof if source_proof.is_absolute() else ROOT/source_proof
assert sha(source_proof)==matrix['source_manifest']['sha256']
expected_source={r['path'][9:]:r['sha256'] for r in json.loads(source_proof.read_text())['files'] if r['path'].startswith('src/main/')}
current_source=tree(ROOT/'src/main');assert values(current_source)==expected_source,'Main source differs from successful final native matrix'
current_jar=ROOT/'build/libs/cross_tesseract-0.1.0-dev.jar';assert sha(current_jar)==EXPECTED_JAR
agent_manifest=a.agent_manifest.resolve(strict=True);agent=json.loads(agent_manifest.read_text());assert agent['recorder_revision']=='v2_mod_roots'
for row in agent['artifacts']:assert sha(Path(row['path']))==row['sha256']
agent_jar=next(Path(r['path']) for r in agent['artifacts'] if Path(r['path']).name=='rc-probe-agent.jar')
if a.profile=='final':
 source=ROOT/'src/main';classes=ROOT/'build/classes/java/main';resources=ROOT/'build/resources/main';jar=current_jar;revision=matrix['workspace_git_HEAD']
else:
 source=F3/'source-main';classes=F3/'classes';resources=F3/'resources';jar=F3/'artifacts/cross_tesseract-0.1.0-dev.jar';revision='f3c59b772dcbd343596174c73093b2fef536f19c'
before_classes=tree(classes);before_resources=tree(resources)
with zipfile.ZipFile(jar) as archive:
 for manifest in (before_classes,before_resources):
  for row in manifest['files']:assert hashlib.sha256(archive.read(row['relative_path'])).hexdigest()==row['sha256'],row['relative_path']
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
folder=ROOT/'scratch'/('rc-v2-'+a.profile+'-freeze-'+stamp);folder.mkdir()
shutil.copytree(classes,folder/'classes');shutil.copytree(resources,folder/'resources');shutil.copytree(source,folder/'source-main');shutil.copyfile(jar,folder/jar.name)
record={'utc':datetime.now(timezone.utc).isoformat(),'freeze_helper':meta(Path(__file__).resolve()),'source_revision':revision,'profile':a.profile,'probe_manifest':str(agent_manifest),'probe_manifest_sha256':sha(agent_manifest),'probe':agent,
 'final_native_matrix':meta(MATRIX),'final_native_source_manifest':meta(source_proof),'artifacts':{'JAR':meta(folder/jar.name),'classes':tree(folder/'classes'),'resources':tree(folder/'resources'),'source_main':tree(folder/'source-main')},'launches':{},'base_arg_provenance':{},
 'scope':'New v2 opt-in agent; actual frozen original f3 or final classes/resources/JAR. Both profiles use the same newly generated final base VM/program/classpath arguments without optional mods. Existing v1 and all original launch directories are preserved. Runtime source is separate from the final checkout source-tree guard. No build/backend/JVM here. Sources JAR is not a runtime input.'}
base=ROOT/'build/moddev'
for server,title in (('A','A'),('B','B'),('C','C'),('perf','Perf')):
 new=ROOT/'scratch/dev-launch'/uuid.uuid4().hex;new.mkdir();shutil.copytree(folder/'classes',new/'classes');shutil.copytree(folder/'resources',new/'resources')
 original=list(sorted(f for f in base.iterdir() if f.is_file() and f.name.startswith('server'+title) and f.suffix in ('.txt','.xml')))+[base/('runServer'+title+'.sh')]
 record['base_arg_provenance'][server]=[meta(f) for f in original]
 for f in original:
  text=f.read_text().replace(str(base),str(new)).replace(str(ROOT/'build/classes/java/main'),str(new/'classes')).replace(str(ROOT/'build/resources/main'),str(new/'resources'))
  (new/f.name).write_text(text)
 control=new/'probe-control.txt';out=ROOT/'reports/rc-20261017'/('probe-v2-'+a.profile+'-'+stamp+'-'+server)
 vm=new/('server'+title+'RunVmArgs.txt');text=vm.read_text();assert '-javaagent:' not in text
 vm.write_text(text+'\n-javaagent:'+str(agent_jar)+'='+str(control)+';'+str(out)+'\n')
 launcher=new/('runServer'+title+'.sh')
 assert values(tree(new/'classes'))==values(record['artifacts']['classes']) and values(tree(new/'resources'))==values(record['artifacts']['resources'])
 record['launches'][server]={'launcher':str(launcher),'launcher_sha256':sha(launcher),'vm_args':str(vm),'vm_args_sha256':sha(vm),'control':str(control),'output':str(out),'base_launcher':str(base/launcher.name)}
assert values(tree(ROOT/'src/main'))==values(current_source) and sha(current_jar)==EXPECTED_JAR
assert values(tree(classes))==values(before_classes) and values(tree(resources))==values(before_resources)
target=ROOT/'reports/rc-20261017'/('probe-launches-v2-'+a.profile+'-'+stamp+'.json')
with target.open('x') as stream:json.dump(record,stream,indent=2);stream.write('\n')
(ROOT/'scratch'/('rc-v2-'+a.profile+'-manifest-active.txt')).write_text(str(target)+'\n')
print(json.dumps({'manifest':str(target.relative_to(ROOT)),'sha256':sha(target),'JAR_sha256':record['artifacts']['JAR']['sha256'],'source_revision':revision,'bytes':target.stat().st_size}),flush=True)
