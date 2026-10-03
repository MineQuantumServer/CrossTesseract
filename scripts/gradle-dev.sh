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
mkdir -p scratch
# Serialize Gradle output mutations and protect start-dev's immutable snapshot capture.
exec flock -x scratch/dev-build.lock ./gradlew "$@"
