#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"

for rank in {0..11}; do
    if [[ ! -d "$case_dir/processor$rank" ]]; then
        echo "ERROR: missing processor$rank; there is no 12-rank run to resume." >&2
        exit 2
    fi
done

cd "$case_dir"
foamDictionary -disableFunctionEntries system/controlDict \
    -entry startFrom -set latestTime
mpirun -np 12 pimpleFoam -parallel 2>&1 | tee -a log.pimpleFoam
