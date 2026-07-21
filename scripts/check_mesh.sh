#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
case_dir="$root/case"
log="$case_dir/log.checkMesh"

if [[ "${1:-}" != "--reuse-log" ]]; then
    (cd "$case_dir" && checkMesh 2>&1 | tee log.checkMesh)
fi

grep -q "Mesh OK" "$log" || { echo "ERROR: checkMesh did not report Mesh OK" >&2; exit 3; }
cells="$(awk '/cells:/ {print $2; exit}' "$log")"
if [[ -z "$cells" ]]; then
    echo "ERROR: could not read cell count from $log" >&2
    exit 3
fi
if (( cells < 4500000 || cells > 5500000 )); then
    echo "ERROR: $cells cells is outside the 4.5M--5.5M acceptance band." >&2
    exit 3
fi
echo "Mesh accepted: $cells cells."

