#!/usr/bin/env bash
set -euo pipefail

mode="${1:-mann}"
case "$mode" in
    mann|uniform) ;;
    *) echo "Usage: $0 {mann|uniform}" >&2; exit 2 ;;
esac

case_dir="$(cd "$(dirname "$0")/../case" && pwd)"
if [[ -d "$case_dir/0" ]]; then
    rm -rf "$case_dir/0"
fi
cp -a "$case_dir/0.$mode" "$case_dir/0"
echo "Prepared case/0 from 0.$mode"

