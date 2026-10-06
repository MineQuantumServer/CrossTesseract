#!/usr/bin/env bash
# Reuse an existing immutable development launch; never create a new freeze.
set -euo pipefail

ct_usage() {
  cat <<'EOF'
Usage: scripts/start-frozen-dev.sh [--check] A|B|C|perf scratch/dev-launch/UUID/runServerX.sh

The launcher must be a regular, already-frozen repository file with the exact
server name (runServerA/B/C/Perf.sh) and matching frozen VM/program/classpath files.
Existing accepted EULA, dev_three_v1 (A/B/C) or dev_perf_v1 (perf), loopback backend
and RCON configuration are required. The requested server's launch lock and JVM
guard prevent overlapping managed processes. Proxy/CA setup matches start-dev.sh.

--check   Inspect files/config/hash provenance only: no /proc, locks, JVM or network.
--help    Show this text.

No build, class freeze, EULA acceptance, config change, world reset or process stop.
Select fresh test worlds/server IDs separately before running a workload.
EOF
}

case "${1:-}" in -h|--help) ct_usage; exit 0;; esac
ct_check=0
if [[ "${1:-}" == --check ]]; then ct_check=1; shift; fi
if [[ $# != 2 ]]; then ct_usage >&2; exit 2; fi
case "$1" in A|B|C|perf) ct_run="$1";; *) ct_usage >&2; exit 2;; esac
ct_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ct_root"
ct_launcher="$2"

# This first pass is also the complete --check path. It performs local file reads
# only, and never imports a workload/RCON helper or executes the frozen shell.
ct_validate() {
  python3 -B - "$ct_root" "$ct_run" "$ct_launcher" "$1" <<'PY'
import hashlib,json,os,re,shlex,sys
from pathlib import Path
from urllib.parse import urlsplit

root=Path(sys.argv[1]).resolve(); mode=sys.argv[2]; supplied=Path(sys.argv[3]); live=sys.argv[4]=='live'
title='Perf' if mode=='perf' else mode
requested=supplied if supplied.is_absolute() else root/supplied
launch=requested.resolve(strict=True)
freeze_root=root/'scratch/dev-launch'
if (not launch.is_relative_to(freeze_root) or launch.parent.parent!=freeze_root
        or not re.fullmatch(r'[0-9a-f]{32}',launch.parent.name)
        or launch.name!='runServer'+title+'.sh' or not launch.is_file()):
    raise ValueError('Expected this server\'s scratch/dev-launch/32-hex-UUID/runServer'+title+'.sh')
for part in (requested,*requested.parents):
    if part==root.parent:break
    if part.is_symlink():raise ValueError('Frozen launcher path must not contain symlinks')
directory=launch.parent; run=root/('run-'+mode)
if not run.is_dir() or run.is_symlink():raise ValueError('Existing local run directory required')

def regular(path,limit=262144):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:
        raise ValueError('Expected bounded regular local file: '+str(path))
    return path.read_text()

def properties(path):
    result={}
    for line in regular(path).splitlines():
        line=line.strip()
        if line and not line.startswith(('#','!')) and '=' in line:
            key,value=line.split('=',1);key=key.strip()
            if key in result:raise ValueError('Duplicate config key: '+key)
            result[key]=value.strip()
    return result

text=regular(launch)
lex=shlex.shlex(text,posix=True,punctuation_chars=True);lex.whitespace_split=True;lex.commenters=''
tokens=list(lex)
if len(tokens)!=12 or tokens[:2]!=['(','cd'] or tokens[2]!=str(run) or tokens[3:5]!=[';','exec'] or tokens[-1]!=')':
    raise ValueError('Unrecognized frozen launch: expected one cd/exec subshell')
java=Path(tokens[5]).resolve(strict=True)
if java.name!='java' or not java.is_relative_to(root/'scratch/jdk') or not java.is_file() or not os.access(java,os.X_OK):
    raise ValueError('Expected existing Java executable under repository scratch/jdk')
release=properties(java.parent.parent/'release')
if not re.match(r'^21(?:\.|\")',release.get('JAVA_VERSION','').lstrip('"')):
    raise ValueError('Frozen fixture requires Java 21')
args={suffix:directory/('server'+title+suffix+'.txt') for suffix in ('RunClasspath','RunVmArgs','RunProgramArgs')}
selected='-Dfml.modFolders=cross_tesseract%%'+str(directory/'classes')+':cross_tesseract%%'+str(directory/'resources')
if tokens[6:11]!=['@'+str(args['RunClasspath']),'@'+str(args['RunVmArgs']),selected,'net.neoforged.devlaunch.Main','@'+str(args['RunProgramArgs'])]:
    raise ValueError('Launcher must select its own frozen argument files/classes/resources')
for path in args.values():regular(path,1048576)
vm=shlex.split(regular(args['RunVmArgs']),comments=True,posix=True)
system={value[2:].split('=',1)[0]:value.split('=',1)[1] for value in vm if value.startswith('-D') and '=' in value}
cfg=run/'cross-tesseract.properties'
if system.get('cross_tesseract.testHarness')!='true' or system.get('cross_tesseract.config')!=str(cfg):
    raise ValueError('Frozen VM args must use the requested fixture config and enabled test harness')
if any(key in os.environ for key in ('CT_MYSQL_URL','CT_MYSQL_USER','CT_MYSQL_PASSWORD','CT_REDIS_URI')):
    raise ValueError('Backend override environment variables are not accepted')
config=properties(cfg); vanilla=properties(run/'server.properties'); eula=properties(run/'eula.txt')
cluster='dev_perf_v1' if mode=='perf' else 'dev_three_v1'
mysql=urlsplit(config.get('mysql.url','').removeprefix('jdbc:'))
port={'A':'25575','B':'25576','C':'25577','perf':'25578'}[mode]
if not (eula.get('eula')=='true' and config.get('backend.enabled')=='true'
        and config.get('cluster.id')==cluster and config.get('mysql.user')=='ct_dev'
        and mysql.scheme=='mysql' and mysql.hostname=='127.0.0.1' and mysql.port==13306
        and mysql.path=='/cross_tesseract' and mysql.username is None and mysql.password is None
        and config.get('redis.uri')=='redis://127.0.0.1:16379'
        and vanilla.get('server-ip')=='127.0.0.1' and vanilla.get('enable-rcon')=='true'
        and vanilla.get('rcon.port')==port and config.get('server.id')):
    raise ValueError('Existing accepted EULA and isolated loopback fixture configuration required')
if not re.fullmatch(r'world(?:-opt-[A-Za-z0-9_-]{1,80})?',vanilla.get('level-name','')):
    raise ValueError('Expected existing fixture world name, never an arbitrary world path')

def tree_hash(path):
    if path.is_symlink() or not path.is_dir():raise ValueError('Frozen classes/resources directory required')
    files=sorted(path.rglob('*')); digest=hashlib.sha256(); count=0; total=0
    if len(files)>8192:raise ValueError('Frozen directory exceeds bounded manifest')
    for file in files:
        if file.is_symlink():raise ValueError('Frozen files must not reference live build outputs')
        if not file.is_file():continue
        size=file.stat().st_size;total+=size;count+=1
        if size>33554432 or total>67108864:raise ValueError('Frozen directory exceeds bounded size')
        name=file.relative_to(path).as_posix()
        digest.update((name+'\0'+hashlib.sha256(file.read_bytes()).hexdigest()+'\n').encode())
    return {'path':str(path),'files':count,'bytes':total,'manifest_sha256':digest.hexdigest(),
        'manifest_format':'sorted relative path + NUL + content SHA256 + LF'}
if not (directory/'classes/dev/crosstesseract/test/ThreeServerHarness.class').is_file():
    raise ValueError('Frozen test-harness class missing')
classes=tree_hash(directory/'classes');resources=tree_hash(directory/'resources')
if live:
    expected='server'+title+'RunVmArgs.txt'
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            argv=[arg.decode(errors='replace') for arg in (proc/'cmdline').read_bytes().split(b'\0') if arg]
            if not argv or Path(argv[0]).name!='java':continue
            same_args=any(Path(arg.removeprefix('@')).name==expected for arg in argv)
            # Packaged NeoForge launches use unix_args.txt rather than devlaunch
            # Main. Their run directory still identifies the same fixture.
            same_cwd=(proc/'cwd').resolve()==run
            if same_args or same_cwd:raise RuntimeError('Previous managed '+mode+' JVM still running (PID '+proc.name+'); wait for complete shutdown')
        except (FileNotFoundError,PermissionError):continue
print(json.dumps({'mode':mode,'validation':'live process guard + local files' if live else 'OFFLINE files only; process/lock availability UNCHECKED',
    'launch':str(launch),'launch_sha256':hashlib.sha256(text.encode()).hexdigest(),'java':str(java),
    'cluster':cluster,'server_id':config['server.id'],'level_name':vanilla['level-name'],'rcon_port':int(port),
    'classes':classes,'resources':resources,'vm_args_sha256':hashlib.sha256(args['RunVmArgs'].read_bytes()).hexdigest()}))
PY
}

ct_validate offline
if [[ "$ct_check" == 1 ]]; then exit 0; fi

if [[ -n "${HTTPS_PROXY:-}" ]]; then
  read -r ct_proxy_host ct_proxy_port < <(python3 -c 'import os,urllib.parse; u=urllib.parse.urlparse(os.environ["HTTPS_PROXY"]);print(u.hostname,u.port or 80)')
  export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Dhttps.proxyHost=$ct_proxy_host -Dhttps.proxyPort=$ct_proxy_port -Dhttp.proxyHost=$ct_proxy_host -Dhttp.proxyPort=$ct_proxy_port -Dhttp.nonProxyHosts=localhost|127.*"
fi
if [[ -f /etc/ssl/certs/java/cacerts ]]; then export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts"; fi
exec 9>"scratch/server-$ct_run.launch.lock"
flock -n 9 || { echo "A supervised $ct_run process is already running; wait for its complete shutdown." >&2; exit 1; }
ct_validate live
# Canonical path was validated above; bash receives a path, never eval'd shell text.
ct_launcher="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$ct_launcher")"
exec bash "$ct_launcher"
