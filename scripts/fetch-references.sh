#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p scratch/upstream
fetch_ref() {
  local name="$1" repo="$2" sha="$3"
  if [[ ! -d "scratch/upstream/$name/.git" ]]; then git init "scratch/upstream/$name" >/dev/null; git -C "scratch/upstream/$name" remote add origin "$repo"; fi
  local actual
  actual=$(git -C "scratch/upstream/$name" rev-parse HEAD 2>/dev/null || true)
  if [[ "$actual" == "$sha" ]]; then return; fi
  if [[ -n "$actual" && "$actual" != HEAD ]]; then
    echo "Existing reference $name has a different commit; refusing to overwrite it." >&2
    exit 1
  fi
  git -C "scratch/upstream/$name" fetch --depth=1 origin "$sha"
  git -C "scratch/upstream/$name" checkout --detach FETCH_HEAD
  test "$(git -C "scratch/upstream/$name" rev-parse HEAD)" = "$sha"
}
fetch_ref ae2 https://github.com/AppliedEnergistics/Applied-Energistics-2.git db17504a86128fdf3dae31f5fb7a112a646e0b93
fetch_ref gregtech https://github.com/FortyTwoCn/GregTech-Modern.git c72dc16b52795cbb0456b6e15e13cc4a85c0ed1b
fetch_ref mekanism https://github.com/mekanism/Mekanism.git bcd7a8bf594cff9614eb12238fe3776f19da24d9
fetch_ref tesseract https://github.com/SuperMartijn642/Tesseract.git cedf6df38a02d1f204733f2d8723d7f99861d972
if [[ "${1:-}" == --with-gt-runtime ]]; then
  fetch_ref modularui-modern https://github.com/brachy84/ModularUI-Modern.git 8ecb104d0c38b1eb9baab5c837624034db7ca873
fi
