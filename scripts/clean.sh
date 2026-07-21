#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"

find "$case_dir" -maxdepth 1 -type d -name 'processor*' -exec rm -rf {} +
find "$case_dir" -maxdepth 1 -type d -regex '.*/[0-9]+\(\.[0-9]+\)?' -exec rm -rf {} +
rm -rf "$case_dir/constant/polyMesh" "$case_dir/postProcessing" "$case_dir/0"
rm -f "$case_dir"/log.* "$case_dir"/*.foam
echo "Removed generated mesh, time directories and logs; Mann boundaryData was retained."

