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

for command in blockMesh topoSet checkMesh pimpleFoam decomposePar mpirun; do
    command -v "$command" >/dev/null || { echo "ERROR: missing $command" >&2; exit 2; }
done

library="${FOAM_USER_LIBBIN:-}/libturbinesFoam.so"
if [[ ! -f "$library" ]]; then
    echo "ERROR: externally compiled libturbinesFoam.so not found in FOAM_USER_LIBBIN." >&2
    exit 2
fi
echo "turbinesFoam library: $library"

python3 tools/generate_case.py --check
echo "Environment and generated dictionaries are consistent."

