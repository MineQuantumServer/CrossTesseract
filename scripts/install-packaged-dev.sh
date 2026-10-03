#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "${1:-}" == --accept-eula ]] || { echo 'Read the Minecraft EULA, then pass --accept-eula for this isolated test install.' >&2;exit 1; }
ct_jdk="$PWD/scratch/jdk/jdk-21.0.8+9"
[[ -x "$ct_jdk/bin/java" ]] || { echo 'Run scripts/install-jdk.sh first.' >&2;exit 1; }
if [[ -n "${HTTPS_PROXY:-}" ]]; then
  read -r ct_proxy_host ct_proxy_port < <(python3 -c 'import os,urllib.parse; u=urllib.parse.urlparse(os.environ["HTTPS_PROXY"]);print(u.hostname,u.port or 80)')
  export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Dhttps.proxyHost=$ct_proxy_host -Dhttps.proxyPort=$ct_proxy_port -Dhttp.proxyHost=$ct_proxy_host -Dhttp.proxyPort=$ct_proxy_port -Dhttp.nonProxyHosts=localhost|127.*"
fi
ct_installer=scratch/packaged/neoforge-21.1.252-installer.jar
mkdir -p scratch/packaged/server
if [[ ! -f "$ct_installer" ]]; then
  curl -fL --retry 3 https://maven.neoforged.net/releases/net/neoforged/neoforge/21.1.252/neoforge-21.1.252-installer.jar -o "$ct_installer"
fi
printf '%s  %s\n' d0345e2a104ce4633065f572310ba6e0dd428bb6a73364cf0c2443ed9f8950ad "$ct_installer" | sha256sum -c -
if [[ ! -f scratch/packaged/server/libraries/net/neoforged/neoforge/21.1.252/unix_args.txt ]]; then
  "$ct_jdk/bin/java" -Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts -jar "$ct_installer" --installServer scratch/packaged/server
fi
python3 - <<'PY'
from pathlib import Path
import shutil
root=Path('scratch/packaged/server');(root/'config').mkdir(exist_ok=True);(root/'mods').mkdir(exist_ok=True)
def create(p,text):
    if not p.exists():p.write_text(text)
create(root/'eula.txt','eula=true\n')
create(root/'config/cross-tesseract.properties','''backend.enabled=true
cluster.id=dev_packaged_v1
server.id=dev-packaged
mysql.url=jdbc:mysql://127.0.0.1:13306/cross_tesseract?sslMode=DISABLED&allowPublicKeyRetrieval=true&connectTimeout=1500&socketTimeout=3000
mysql.user=ct_dev
mysql.password=ct_dev_only
redis.uri=redis://127.0.0.1:16379
chunkLoading.maxPerPlayer=2
''')
create(root/'server.properties','''server-port=25569
server-ip=127.0.0.1
online-mode=true
enable-rcon=true
rcon.port=25579
rcon.password=ct_dev_rcon_only
level-type=minecraft:flat
generator-settings={"biome":"minecraft:plains","layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}]}
view-distance=3
simulation-distance=3
spawn-chunk-radius=0
max-players=4
''')
jar=Path('build/libs/cross_tesseract-0.1.0-dev.jar')
if not jar.exists():raise SystemExit('Build the mod first: scripts/gradle-dev.sh build')
shutil.copy2(jar,root/'mods'/jar.name)
print('Isolated official NeoForge install ready: scratch/packaged/server')
PY
