#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"

python3 "$root/tools/generate_case.py" --config "$root/config/single_turbine.yaml"
"$root/scripts/prepare_initial_conditions.sh" uniform

cd "$case_dir"
blockMesh 2>&1 | tee log.blockMesh.validation
snappyHexMesh -overwrite 2>&1 | tee log.snappyHexMesh.validation
topoSet 2>&1 | tee log.topoSet.validation
checkMesh 2>&1 | tee log.checkMesh.validation
checkMesh -allGeometry -allTopology 2>&1 | tee log.checkMesh.validation.detailed || true
decomposePar -force 2>&1 | tee log.decomposePar.validation
mpirun -np 12 pimpleFoam -parallel 2>&1 | tee log.pimpleFoam.validation

echo "Validation run complete. Compare T1 mean Cp/Ct over 10--30 s with Phase VI data."
echo "Restore farm dictionaries with: python3 tools/generate_case.py"

