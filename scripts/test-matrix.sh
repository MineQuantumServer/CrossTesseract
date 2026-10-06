#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs reports
ct_failed=0
for ct_mods in '' mekanism ae2 ae2,mekanism gregtech gregtech,mekanism ae2,gregtech ae2,gregtech,mekanism; do
  ct_label=$(printf '%s' "$ct_mods" | tr ',' '-');ct_label=${ct_label:-base}
  if [[ "$ct_mods" == *gregtech* && ! -f scratch/upstream/gregtech/build/libs/gtceu-1.21.1-8.0.0.jar ]]; then
    echo 'BLOCKED: build the real FortyTwoCn GregTech runtime as described in docs/COMPATIBILITY.md.' > "logs/matrix-$ct_label.log"
    echo "BLOCKED $ct_label (missing actual GT runtime)";ct_failed=1;continue
  fi
  ct_args=(runGameTestServer -PgameTestBackend "-PtestMods=$ct_mods")
  if [[ "$ct_label" != base && ! -f "gradle/locks/$ct_label.lockfile" ]]; then ct_args+=(--write-locks); fi
  echo "Running native GameTests: $ct_label"
  if timeout 300 scripts/gradle-dev.sh "${ct_args[@]}" > "logs/matrix-$ct_label.log" 2>&1; then
    echo "PASS $ct_label"
  else
    echo "FAIL $ct_label (see logs/matrix-$ct_label.log)";ct_failed=1
  fi
done
python3 - <<'PY'
import json,re,time
from pathlib import Path
rows=[]
for label in ('base','mekanism','ae2','ae2-mekanism','gregtech','gregtech-mekanism','ae2-gregtech','ae2-gregtech-mekanism'):
    path=Path('logs')/f'matrix-{label}.log';s=path.read_text();match=re.search(r'All (\d+) required tests passed',s)
    mods={'mekanism':'(mekanism)','ae2':'(ae2)','gregtech':'(gtceu)'}
    expected=10+sum((3 if m=='ae2' else 2) for m in mods if m in label.split('-'))
    present=all(token in s for m,token in mods.items() if m in label.split('-'))
    rows.append({'combination':label,'passed':bool(match) and int(match[1])>=expected and present and 'BUILD SUCCESSFUL' in s,'required_native_tests':int(match[1]) if match else None,'minimum_expected_tests':expected,'optional_mods_present':present,'log':str(path)})
Path('reports/compat-matrix.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'Real NeoForge GameTest JVMs with real MySQL/Redis; GT is exact FortyTwoCn source plus disclosed local ModularUI 3.3.1 alternative.','combinations':rows},indent=2)+'\n')
if not all(r['passed'] for r in rows):raise SystemExit(1)
PY
exit "$ct_failed"
