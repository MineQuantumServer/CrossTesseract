from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,shutil,subprocess,sys,tempfile,uuid
root=Path.cwd().resolve()
original=root/'reports/rc-20261017/fe-final-gates-20261017T173453Z-7e770cf1.json'
result=json.loads(original.read_text())
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
out=root/'reports/rc-20261017'/('archive-portability-0113-fe-'+stamp)
out.mkdir()
work=Path(tempfile.mkdtemp(prefix='ct-rc0113-public-'))
files={Path('scripts/analysis/compare-rc-fe.py'),Path(result['targets']['path']),Path(result['measurement_amendment']['path']),Path(result['frozen_v1']['path'])}
for ref in result['sources'].values():files.add(Path(ref['path']))
for key in ('baseline_controller','candidate_controller'):
 controller=json.loads((root/result['sources'][key]['path']).read_text())
 files.add(Path(controller['runtime_manifest']['path']))
 raw=json.loads((root/controller['raw_report']['path']).read_text())
 for sample in raw['samples']:
  for name in ('probe_fixed_window','probe_full_lifecycle'):
   for frame in sample[name].values():files.add(Path(frame['source']['path']))
inputs=[]
for name in sorted(files):
 source=root/name
 assert name.parts[0] in ('reports','scripts','docs') and not source.is_symlink() and source.is_file()
 target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
 inputs.append({'path':str(name),'bytes':source.stat().st_size,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
guard=root/'reports/rc-20261017/archive-portability-20261017T154941Z-107a484f/offline_guard.py'
shutil.copyfile(guard,out/'offline_guard.py')
command=[sys.executable,'-I',str(out/'offline_guard.py'),str(root),str(work),str(work/'scripts/analysis/compare-rc-fe.py')]
for key in ('baseline','candidate','baseline_controller','candidate_controller'):command.extend(['--'+key.replace('_','-'),result['sources'][key]['path']])
run=subprocess.run(command,cwd=work,capture_output=True,text=True,timeout=45)
(out/'stdout.log').write_text(run.stdout);(out/'stderr.log').write_text(run.stderr)
outputs=list((work/'reports/rc-20261017').glob('fe-final-gates-*.json'))
assert len(outputs)==1
current=json.loads(outputs[0].read_text())
keys=('recipe','sources','frozen_v1','targets','measurement_amendment','source_and_runtime_qualified','samples','limits','all_small_FE_gates_passed')
equal={key:result[key]==current[key] for key in keys}
proof={'kind':'archive_only_current_0113_FE_reproduction','utc':datetime.now(timezone.utc).isoformat(),'original':{'path':str(original.relative_to(root)),'sha256':hashlib.sha256(original.read_bytes()).hexdigest()},'command':command,'temporary_root':str(work),'inputs':inputs,'input_bytes':sum(row['bytes'] for row in inputs),'input_count':len(inputs),'actual_exit':run.returncode,'all_values_equal':equal,'passed':run.returncode==2 and all(equal.values()),'scope':'Only public reports, recipe and frozen docs copied; no source/build/.git/scratch; Python -I and audit hook reject original repository, network, subprocess. Reader restriction, not an OS sandbox; EXIT2 preserves performance FAIL.'}
shutil.copyfile(outputs[0],out/'recomputed.json');shutil.copyfile(outputs[0].with_suffix('.csv'),out/'recomputed.csv');shutil.copyfile(Path(__file__),out/'verify.py')
(out/'verification.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'output':str(out.relative_to(root)),'passed':proof['passed'],'exit':run.returncode,'files':len(files),'bytes':proof['input_bytes'],'equal':equal}))
raise SystemExit(0 if proof['passed'] else 1)
