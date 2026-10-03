#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || { echo 'This pinned helper is for Linux x86_64. Install a Java 21 JDK for your platform.' >&2; exit 1; }
ct_jdk=scratch/jdk/jdk-21.0.8+9
if [[ -x "$ct_jdk/bin/javac" ]]; then "$ct_jdk/bin/javac" -version;exit 0;fi
[[ ! -e "$ct_jdk" ]] || { echo 'Existing JDK directory is incomplete; refusing to overwrite.' >&2;exit 1; }
mkdir -p scratch/jdk
ct_archive=$(mktemp /tmp/ct-jdk.XXXXXX.tar.gz)
trap 'rm -- "$ct_archive"' EXIT
curl -fL --retry 3 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.8%2B9/OpenJDK21U-jdk_x64_linux_hotspot_21.0.8_9.tar.gz' -o "$ct_archive"
printf '%s  %s\n' f2dc5418092c43003db8f9005c4a286e1c0104fea96ccdd49e8ebd037cac9219 "$ct_archive" | sha256sum -c -
tar -xzf "$ct_archive" -C scratch/jdk
"$ct_jdk/bin/javac" -version
