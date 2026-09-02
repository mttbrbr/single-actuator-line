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
if (( cells < 6600000 || cells > 6800000 )); then
    echo "ERROR: $cells cells is outside the 6.6M--6.8M acceptance band." >&2
    exit 3
fi
hexes="$(awk '/hexahedra:/ {print $2; exit}' "$log")"
polyhedra="$(awk '/polyhedra:/ {print $2; exit}' "$log")"
max_non_ortho="$(awk '/Mesh non-orthogonality Max:/ {print $4; exit}' "$log")"
if [[ -z "$hexes" || -z "$polyhedra" || -z "$max_non_ortho" ]]; then
    echo "ERROR: incomplete cell-type or non-orthogonality data in $log." >&2
    exit 3
fi
if [[ "$hexes" != "$cells" || "$polyhedra" != "0" ]]; then
    echo "ERROR: mesh is not 100% hexahedral ($hexes/$cells hexes, $polyhedra polyhedra)." >&2
    exit 3
fi
awk -v value="$max_non_ortho" 'BEGIN { exit !(value <= 1e-10) }' || {
    echo "ERROR: max non-orthogonality is $max_non_ortho, expected numerical zero." >&2
    exit 3
}
echo "Mesh accepted: $cells orthogonal hexahedral cells."

