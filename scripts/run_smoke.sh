#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"

python3 "$root/tools/generate_case.py" --profile smoke
"$root/scripts/prepare_initial_conditions.sh" uniform
"$root/scripts/mesh.sh" smoke

cd "$case_dir"
decomposePar -force 2>&1 | tee log.decomposePar
mpirun -np 4 pimpleFoam -parallel 2>&1 | tee log.pimpleFoam.smoke
grep -q "End" log.pimpleFoam.smoke
echo "Smoke test completed. Regenerate the production profile before production."

