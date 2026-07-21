#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"
profile="${1:-production}"

python3 "$root/tools/generate_case.py" --profile "$profile"
cd "$case_dir"

blockMesh 2>&1 | tee log.blockMesh
snappyHexMesh -overwrite 2>&1 | tee log.snappyHexMesh
topoSet 2>&1 | tee log.topoSet
checkMesh 2>&1 | tee log.checkMesh
checkMesh -allGeometry -allTopology 2>&1 | tee log.checkMesh.detailed || true

if [[ "$profile" == "production" ]]; then
    "$root/scripts/check_mesh.sh" --reuse-log
fi

