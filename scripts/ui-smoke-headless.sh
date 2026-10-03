#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ct_xvfb=$(command -v Xvfb || true)
ct_xlib=${LD_LIBRARY_PATH:-}
if [[ -z "$ct_xvfb" && -x scratch/ui-tools/usr/bin/Xvfb ]]; then
  ct_xvfb="$PWD/scratch/ui-tools/usr/bin/Xvfb"
  ct_xlib="$PWD/scratch/ui-tools/usr/lib/x86_64-linux-gnu${ct_xlib:+:$ct_xlib}"
fi
[[ -n "$ct_xvfb" ]] || { echo 'Install Xvfb to run the actual headless client smoke test.' >&2;exit 1; }
mkdir -p logs
ct_displayfile=$(mktemp /tmp/ct-x-display.XXXXXX)
exec 3>"$ct_displayfile"
LD_LIBRARY_PATH="$ct_xlib" "$ct_xvfb" -displayfd 3 -screen 0 1280x900x24 -ac -nolisten tcp > logs/ui-xvfb.log 2>&1 &
ct_xpid=$!
trap 'kill "$ct_xpid" 2>/dev/null || true;wait "$ct_xpid" 2>/dev/null || true;rm -- "$ct_displayfile"' EXIT
for ct_try in {1..50}; do
  [[ -s "$ct_displayfile" ]] && break
  kill -0 "$ct_xpid" || { cat logs/ui-xvfb.log >&2;exit 1; }
  sleep .1
done
ct_display=$(cat "$ct_displayfile")
[[ "$ct_display" =~ ^[0-9]+$ ]] || { echo 'Xvfb did not allocate a display.' >&2;exit 1; }
# This directory is exclusively the named UI test fixture. Begin every repeat in English;
# the real client changes to Chinese after its first verified screenshot.
python3 - <<'PY'
from pathlib import Path
p=Path('run-ui/options.txt')
if p.exists():
    lines=p.read_text().splitlines();lines=[line for line in lines if not line.startswith('lang:')]
    lines.append('lang:en_us');p.write_text('\n'.join(lines)+'\n')
PY
DISPLAY=":$ct_display" scripts/gradle-dev.sh runClientSmoke "$@"
