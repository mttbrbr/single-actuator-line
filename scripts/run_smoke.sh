#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
smoke_root="$(mktemp -d /tmp/single-actuator-line-smoke.XXXXXXXX)"
echo "Smoke case: $smoke_root"
if ! (cd "$root" && git ls-files -z | tar --null -T - -cf - | tar -xf - -C "$smoke_root"); then
    echo "ERROR: could not copy tracked case files; retained $smoke_root" >&2
    exit 2
fi
case_dir="$smoke_root/case"

python3 "$smoke_root/tools/generate_case.py" --profile smoke
"$smoke_root/scripts/prepare_initial_conditions.sh" uniform
"$smoke_root/scripts/mesh.sh" smoke

cd "$case_dir"
decomposePar -force 2>&1 | tee log.decomposePar
mpirun -np 4 pimpleFoam -parallel 2>&1 | tee log.pimpleFoam.smoke
grep -q "End" log.pimpleFoam.smoke
echo "Smoke test completed in $smoke_root. The production case was not modified."
