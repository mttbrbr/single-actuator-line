#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"

if [[ "${1:-}" == "--resume" ]]; then
    for rank in {0..11}; do
        if [[ ! -d "$case_dir/processor$rank" ]]; then
            echo "ERROR: missing processor$rank; there is no 12-rank run to resume." >&2
            exit 2
        fi
    done
    cd "$case_dir"
    foamDictionary -disableFunctionEntries system/controlDict -entry startFrom -set latestTime
    mpirun -np 12 pimpleFoam -parallel 2>&1 | tee -a log.pimpleFoam
    exit 0
fi
if [[ $# -ne 0 ]]; then
    echo "Usage: $0 [--resume]" >&2
    exit 2
fi
if [[ -d "$case_dir/processor0" ]]; then
    echo "ERROR: existing production checkpoints detected. Use make resume; refusing to overwrite." >&2
    exit 2
fi

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
