#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

expected="v2412"
actual="${WM_PROJECT_VERSION:-}"
if [[ "$actual" != "$expected" ]]; then
    echo "ERROR: source OpenFOAM.com $expected first (found '${actual:-unset}')." >&2
    exit 2
fi

for command in blockMesh snappyHexMesh topoSet checkMesh pimpleFoam decomposePar mpirun; do
    command -v "$command" >/dev/null || { echo "ERROR: missing $command" >&2; exit 2; }
done

if [[ -f "${FOAM_USER_LIBBIN}/libturbinesFoam.so" ]]; then
    echo "turbinesFoam library: ${FOAM_USER_LIBBIN}/libturbinesFoam.so"
else
    echo "WARNING: libturbinesFoam.so is not compiled for $expected." >&2
    echo "Run ./scripts/build_turbinesfoam.sh" >&2
fi

python3 tools/generate_case.py --check
echo "Environment and generated dictionaries are consistent."

