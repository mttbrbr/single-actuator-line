#!/usr/bin/env python3
"""Generate a Mann box with Hipersim and map it to OpenFOAM boundaryData."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

from case_config import DEFAULT_CONFIG, ROOT, load_config, mean_velocity


def next_power_of_two(value: int) -> int:
    return 1 << (value - 1).bit_length()


def grid_spec(cfg: dict) -> dict:
    diameter = float(cfg["turbine"]["diameter"])
    velocity = float(cfg["abl"]["hub_velocity"])
    dt = float(cfg["mann"]["sample_dt"])
    dx = velocity * dt
    duration = float(cfg["mann"]["duration"])
    requested_nx = math.ceil(duration / dt) + 1
    nx = next_power_of_two(requested_nx)

    width = (cfg["domain_D"]["y"][1] - cfg["domain_D"]["y"][0]) * diameter
    height = (cfg["domain_D"]["z"][1] - cfg["domain_D"]["z"][0]) * diameter
    target_dy = float(cfg["mann"]["dy_D"]) * diameter
    target_dz = float(cfg["mann"]["dz_D"]) * diameter
    ny = max(4, round(width / target_dy))
    nz = max(4, round(height / target_dz))
    dy = width / ny
    dz = height / nz
    n_planes = math.ceil(duration / dt) + 1
    return {
        "Nxyz": (nx, ny, nz),
        "dxyz": (dx, dy, dz),
        "n_planes": n_planes,
        "sample_dt": dt,
        "estimated_boundary_vectors": n_planes * ny * nz,
    }


def foam_list(path: Path, values: list[str], comment: str) -> None:
    with path.open("w", encoding="utf-8") as stream:
        stream.write(f"// {comment}\n{len(values)}\n(\n")
        stream.write("\n".join(values))
        stream.write("\n)\n")


def generate_box(cfg: dict, spec: dict):
    try:
        from hipersim import MannTurbulenceField
        from hipersim.turbgen.spectral_tensor import MannTurbulenceInput
    except ImportError as error:
        raise RuntimeError(
            "Hipersim is not installed. Create a virtual environment and run "
            "`python3 -m pip install -r requirements.txt`."
        ) from error

    mann = cfg["mann"]
    length_scale = float(mann["length_scale_D"]) * float(cfg["turbine"]["diameter"])
    common = {
        "L": length_scale,
        "Gamma": float(mann["gamma"]),
        "Nxyz": spec["Nxyz"],
        "dxyz": spec["dxyz"],
    }
    input_model = MannTurbulenceInput(alphaepsilon=1.0, **common)
    alphaepsilon = float(
        input_model.get_alpha_epsilon(
            TI=float(cfg["abl"]["turbulence_intensity"]),
            U=float(cfg["abl"]["hub_velocity"]),
        )
    )
    field = MannTurbulenceField.generate(
        alphaepsilon=alphaepsilon,
        seed=int(mann["seed"]),
        HighFreqComp=int(mann["high_frequency_compensation"]),
        double_xyz=tuple(bool(v) for v in mann["double_xyz"]),
        n_cpu=int(mann.get("n_cpu", 1)),
        **common,
    )
    return field, alphaepsilon


def write_boundary_data(cfg: dict, spec: dict, uvw: np.ndarray, alphaepsilon: float, output: Path) -> None:
    inlet = output / "inlet"
    if output.exists():
        marker = output / ".wind-farm-mann-data"
        if not marker.exists():
            raise RuntimeError(f"refusing to replace unrecognised directory: {output}")
        shutil.rmtree(output)
    inlet.mkdir(parents=True)
    (output / ".wind-farm-mann-data").write_text("generated\n", encoding="utf-8")

    diameter = float(cfg["turbine"]["diameter"])
    xmin = float(cfg["domain_D"]["x"][0]) * diameter
    ymin = float(cfg["domain_D"]["y"][0]) * diameter
    zmin = float(cfg["domain_D"]["z"][0]) * diameter
    _, ny, nz = spec["Nxyz"]
    _, dy, dz = spec["dxyz"]
    ys = ymin + (np.arange(ny) + 0.5) * dy
    zs = zmin + (np.arange(nz) + 0.5) * dz

    points = [f"({xmin:.9g} {y:.9g} {z:.9g})" for y in ys for z in zs]
    foam_list(inlet / "points", points, "Mann sampling points on inlet cell centres")

    target_ti = float(cfg["abl"]["turbulence_intensity"])
    hub_velocity = float(cfg["abl"]["hub_velocity"])
    realised_u = uvw[: spec["n_planes"], :, :, 0]
    raw_realised_ti = float(np.std(realised_u) / hub_velocity)
    if raw_realised_ti <= 0:
        raise RuntimeError("the generated Mann field has zero longitudinal variance")
    scale_factor = target_ti / raw_realised_ti
    uvw *= scale_factor
    realised_ti = float(np.std(uvw[: spec["n_planes"], :, :, 0]) / hub_velocity)
    for plane in range(spec["n_planes"]):
        time_value = plane * spec["sample_dt"]
        time_name = f"{time_value:.8f}".rstrip("0").rstrip(".")
        time_dir = inlet / time_name
        time_dir.mkdir()
        values = []
        for iy, _ in enumerate(ys):
            for iz, z in enumerate(zs):
                fluctuation = uvw[plane, iy, iz]
                values.append(
                    f"({mean_velocity(cfg, float(z)) + fluctuation[0]:.9g} "
                    f"{fluctuation[1]:.9g} {fluctuation[2]:.9g})"
                )
        foam_list(time_dir / "U", values, f"Mann velocity plane at t={time_name} s")

    manifest = {
        **spec,
        "Nxyz": list(spec["Nxyz"]),
        "dxyz": list(spec["dxyz"]),
        "alphaepsilon": alphaepsilon,
        "effective_alphaepsilon": alphaepsilon * scale_factor**2,
        "raw_realised_homogeneous_u_TI": raw_realised_ti,
        "realisation_scale_factor": scale_factor,
        "realised_homogeneous_u_TI": realised_ti,
        "target_TI": target_ti,
        "seed": int(cfg["mann"]["seed"]),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if not math.isclose(realised_ti, target_ti, rel_tol=1e-6):
        raise RuntimeError(
            f"realised TI {realised_ti:.5f} differs from "
            f"target {manifest['target_TI']:.5f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "case" / "constant" / "boundaryData"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cfg = load_config(args.config)
    spec = grid_spec(cfg)
    printable = {**spec, "Nxyz": list(spec["Nxyz"]), "dxyz": list(spec["dxyz"])}
    print(json.dumps(printable, indent=2))
    if args.dry_run:
        return 0

    field, alphaepsilon = generate_box(cfg, spec)
    # Hipersim stores uvw as (component, x, y, z).
    uvw = np.moveaxis(np.asarray(field.uvw), 0, -1)
    write_boundary_data(cfg, spec, uvw, alphaepsilon, args.output.resolve())
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)

