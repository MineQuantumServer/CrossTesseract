#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -d scratch/jdk/jdk-21.0.8+9 ]]; then export JAVA_HOME="$PWD/scratch/jdk/jdk-21.0.8+9"; fi
# Apply the cloud session proxy without dumping its environment or credentials.
if [[ -n "${HTTPS_PROXY:-}" ]]; then
  read -r ct_proxy_host ct_proxy_port < <(python3 -c 'import os,urllib.parse; u=urllib.parse.urlparse(os.environ["HTTPS_PROXY"]);print(u.hostname,u.port or 80)')
  export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Dhttps.proxyHost=$ct_proxy_host -Dhttps.proxyPort=$ct_proxy_port -Dhttp.proxyHost=$ct_proxy_host -Dhttp.proxyPort=$ct_proxy_port -Dhttp.nonProxyHosts=localhost|127.*"
fi
if [[ -f /etc/ssl/certs/java/cacerts ]]; then export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts"; fi
case "${1:-}" in gregtech|modularui-modern) ct_reference="$1";; *) echo 'Usage: scripts/build-reference.sh gregtech|modularui-modern [Gradle arguments]' >&2; exit 1;; esac
shift
cd "scratch/upstream/$ct_reference"
exec ./gradlew --no-daemon --max-workers=2 -Dorg.gradle.jvmargs=-Xmx2G "$@"
