#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"

python3 "$root/tools/generate_case.py" --profile production
if [[ ! -f "$case_dir/constant/boundaryData/manifest.json" ]]; then
    echo "ERROR: Mann boundaryData is missing. Run tools/generate_mann_inflow.py." >&2
    exit 2
fi
if [[ ! -d "$case_dir/constant/polyMesh" ]]; then
    "$root/scripts/mesh.sh" production
else
    "$root/scripts/check_mesh.sh"
    (
        cd "$case_dir"
        topoSet 2>&1 | tee log.topoSet
    )
fi
"$root/scripts/prepare_initial_conditions.sh" mann

cd "$case_dir"
decomposePar -force 2>&1 | tee log.decomposePar
mpirun -np 12 pimpleFoam -parallel 2>&1 | tee log.pimpleFoam

