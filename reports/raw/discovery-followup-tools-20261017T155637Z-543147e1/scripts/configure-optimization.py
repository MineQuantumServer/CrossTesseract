#!/usr/bin/env python3
"""Select fresh isolated benchmark worlds while all selected launch JVMs are stopped.

Writes existing development property files only. Never accepts the EULA, starts
processes, changes cluster policy, deletes worlds, or touches non-loopback targets.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]

def properties(path):
    if path.stat().st_size>65536:raise ValueError('Oversized development properties')
    return dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line and not line.lstrip().startswith(('#','!')))

def running(suffix):
    marker=('server'+('Perf' if suffix=='perf' else suffix)+'RunVmArgs.txt').encode()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            args=(proc/'cmdline').read_bytes().split(b'\0')
            if args and args[0].endswith(b'/java') and any(marker in arg for arg in args):return True
        except (FileNotFoundError,PermissionError):pass
    return False

def update(path,values):
    lines=path.read_text().splitlines();result=[]
    for line in lines:
        key=line.split('=',1)[0] if '=' in line else ''
        if key not in values:result.append(line)
    result.extend(key+'='+value for key,value in values.items())
    temporary=path.with_suffix(path.suffix+'.optimization-pending')
    temporary.write_text('\n'.join(result)+'\n');temporary.replace(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    parser.add_argument('--mode',choices=('legacy','batch','fast'),required=True)
    parser.add_argument('--servers',choices=('ABC','perf'),default='ABC')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]{1,32}',args.label):parser.error('Safe lowercase development labels only')
    suffixes=('A','B','C') if args.servers=='ABC' else ('perf',)
    planned=[]
    for suffix in suffixes:
        directory=ROOT/('run-'+suffix);backend=directory/'cross-tesseract.properties';world=directory/'server.properties'
        if running(suffix):raise ValueError('Stop the selected JVM before changing its fixture: '+suffix)
        config=properties(backend);server=properties(world);port=25575+('ABC'.index(suffix) if suffix!='perf' else 3)
        cluster='dev_three_v1' if suffix!='perf' else 'dev_perf_v1'
        if (config.get('cluster.id')!=cluster or config.get('backend.enabled')!='true' or config.get('mysql.user')!='ct_dev'
            or not config.get('mysql.url','').startswith('jdbc:mysql://127.0.0.1:13306/cross_tesseract?')
            or config.get('redis.uri')!='redis://127.0.0.1:16379' or server.get('server-ip')!='127.0.0.1' or server.get('rcon.port')!=str(port)):
            raise ValueError('Refusing non-isolated configuration: '+suffix)
        if properties(directory/'eula.txt').get('eula')!='true':raise ValueError('An existing accepted EULA is required; this script does not accept it')
        name='world-opt-'+args.label+'-'+suffix
        if (directory/name).exists():raise ValueError('Refusing reused world; choose a fresh label: '+name)
        planned.append((suffix,backend,world,name))
    backup=ROOT/'scratch/optimization/fixture-configs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True)
    for suffix,backend,world,name in planned:
        shutil.copyfile(backend,backup/(suffix+'-cross-tesseract.properties'));shutil.copyfile(world,backup/(suffix+'-server.properties'))
        update(backend,{'server.id':'opt-'+args.label+'-'+suffix,'transfer.channelBatches':str(args.mode!='legacy').lower(),'transfer.localFastPath':str(args.mode=='fast').lower()})
        update(world,{'level-name':name})
    print('Prepared stopped development fixtures:',','.join(suffixes),'mode='+args.mode,'label='+args.label)
    print('Previous configs preserved at',backup.relative_to(ROOT))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError) as error:print(str(error),file=sys.stderr);raise SystemExit(1)
