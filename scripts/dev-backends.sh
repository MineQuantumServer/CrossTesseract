#!/usr/bin/env bash
set -euo pipefail
# Only the isolated local Docker socket and loopback ports are used.
ct_docker() { env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock "$@"; }
start_container() {
  local name="$1" image="$2" port="$3" inner="$4"; shift 4
  if ct_docker inspect "$name" >/dev/null 2>&1; then
    local actual
    actual=$(ct_docker inspect --format '{{.Config.Image}}' "$name")
    case "$actual" in mysql:8.4.7|"$image") ;; *) echo "Refusing to reuse unrelated container $name" >&2; exit 1;; esac
    ct_docker start "$name" >/dev/null
  else
    ct_docker run -d --name "$name" --label cross_tesseract.environment=isolated-test -p "127.0.0.1:$port:$inner" "$@" "$image" >/dev/null
  fi
}
start_container ct-dev-mysql mysql@sha256:0426ec38c7a10aa45ba383887df7878f74ee70e2fd589c7b69207f3577901903 13306 3306 \
  -e MYSQL_DATABASE=cross_tesseract -e MYSQL_USER=ct_dev -e MYSQL_PASSWORD=ct_dev_only -e MYSQL_ROOT_PASSWORD=ct_dev_root_only
if ct_docker inspect ct-dev-redis >/dev/null 2>&1; then
  ct_actual=$(ct_docker inspect --format '{{.Config.Image}}' ct-dev-redis)
  case "$ct_actual" in redis:7.4.6|redis@sha256:a9cc41d6d01da2aa26c219e4f99ecbeead955a7b656c1c499cce8922311b2514) ;; *) echo 'Refusing to reuse unrelated ct-dev-redis container' >&2;exit 1;; esac
  ct_docker start ct-dev-redis >/dev/null
else
  ct_docker run -d --name ct-dev-redis --label cross_tesseract.environment=isolated-test -p 127.0.0.1:16379:6379 \
    redis@sha256:a9cc41d6d01da2aa26c219e4f99ecbeead955a7b656c1c499cce8922311b2514 redis-server --appendonly yes >/dev/null
fi
echo 'Isolated MySQL 127.0.0.1:13306 and Redis 127.0.0.1:16379 started. Test credentials only.'
