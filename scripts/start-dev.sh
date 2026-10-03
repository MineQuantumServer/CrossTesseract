#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in A|B|C|perf) ct_run="$1";; *) echo 'Usage: scripts/start-dev.sh A|B|C|perf' >&2; exit 1;; esac
ct_script="build/moddev/runServer${ct_run}.sh"
if [[ "$ct_run" == perf ]]; then ct_script=build/moddev/runServerPerf.sh; fi
if [[ ! -f "$ct_script" ]]; then echo 'Run the createServer*LaunchScript Gradle tasks first.' >&2; exit 1; fi
if [[ -n "${HTTPS_PROXY:-}" ]]; then
  read -r ct_proxy_host ct_proxy_port < <(python3 -c 'import os,urllib.parse; u=urllib.parse.urlparse(os.environ["HTTPS_PROXY"]);print(u.hostname,u.port or 80)')
  export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Dhttps.proxyHost=$ct_proxy_host -Dhttps.proxyPort=$ct_proxy_port -Dhttp.proxyHost=$ct_proxy_host -Dhttp.proxyPort=$ct_proxy_port -Dhttp.nonProxyHosts=localhost|127.*"
fi
if [[ -f /etc/ssl/certs/java/cacerts ]]; then export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts"; fi
mkdir -p scratch
exec 9>"scratch/server-$ct_run.launch.lock"
flock -n 9 || { echo "A supervised $ct_run process is already running; wait for its complete shutdown." >&2;exit 1; }
ct_frozen=$(flock -s scratch/dev-build.lock python3 scripts/freeze-dev-launch.py "$ct_script")
exec bash "$ct_frozen"
