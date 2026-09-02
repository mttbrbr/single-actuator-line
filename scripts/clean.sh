#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"

find "$case_dir" -maxdepth 1 -type d -name 'processor*' -exec rm -rf {} +
find "$case_dir" -maxdepth 1 -type d -regex '.*/[0-9]+\(\.[0-9]+\)?' -exec rm -rf {} +
rm -rf "$case_dir/constant/polyMesh" "$case_dir/postProcessing" "$case_dir/0"
boundary_data="$case_dir/constant/boundaryData"
if [[ -d "$boundary_data" ]]; then
    if [[ -f "$boundary_data/.single-turbine-mann-data" || -f "$boundary_data/.wind-farm-mann-data" ]]; then
        rm -rf "$boundary_data"
    else
        echo "ERROR: refusing to remove unrecognised boundaryData directory." >&2
        exit 2
    fi
fi
rm -f "$case_dir"/log.* "$case_dir"/*.foam "$case_dir/system/snappyHexMeshDict"
echo "Removed generated mesh, times, logs, post-processing and Mann boundaryData."

