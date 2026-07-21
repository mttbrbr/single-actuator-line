#!/usr/bin/env bash
set -euo pipefail

if [[ "${WM_PROJECT_VERSION:-}" != "v2412" ]]; then
    echo "ERROR: source OpenFOAM.com v2412 before building." >&2
    exit 2
fi

if [[ -n "${TURBINESFOAM_SRC:-}" ]]; then
    source_dir="$TURBINESFOAM_SRC"
elif [[ -d "${WM_PROJECT_USER_DIR}/turbinesFoam" ]]; then
    source_dir="${WM_PROJECT_USER_DIR}/turbinesFoam"
else
    openfoam_root="$(dirname "$WM_PROJECT_USER_DIR")"
    source_dir="${openfoam_root}/mttbrbr-v2512/turbinesFoam"
fi

if [[ ! -x "$source_dir/Allwmake" ]]; then
    echo "ERROR: turbinesFoam source not found at $source_dir" >&2
    echo "Set TURBINESFOAM_SRC to the v0.3.0 checkout." >&2
    exit 2
fi

tag="$(git -C "$source_dir" describe --tags --exact-match 2>/dev/null || true)"
if [[ "$tag" != "v0.3.0" ]]; then
    echo "ERROR: expected turbinesFoam v0.3.0, found '${tag:-untagged}'." >&2
    exit 2
fi

echo "Building $source_dir for ${WM_PROJECT_VERSION} -> ${FOAM_USER_LIBBIN}"
# A checkout built with another OpenFOAM release contains absolute dependency
# paths. Clean these before switching ABI/version.
(cd "$source_dir" && ./Allwclean && ./Allwmake)
test -f "${FOAM_USER_LIBBIN}/libturbinesFoam.so"
echo "Build complete."

