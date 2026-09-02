#!/usr/bin/env python3
"""Shared configuration and validation helpers for the LES case."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "case.yaml"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    source = Path(path).resolve()
    with source.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    parent = data.pop("extends", None)
    if parent:
        parent_path = (source.parent / parent).resolve()
        with parent_path.open(encoding="utf-8") as stream:
            data = deep_merge(yaml.safe_load(stream), data)
    validate_config(data)
    return data


def validate_config(cfg: dict[str, Any]) -> None:
    turbine = cfg["turbine"]
    diameter = float(turbine["diameter"])
    radius = float(turbine["radius"])
    if not math.isclose(diameter, 2.0 * radius, rel_tol=0, abs_tol=1e-9):
        raise ValueError("turbine.diameter must be exactly twice turbine.radius")

    xlim = cfg["domain_D"]["x"]
    ylim = cfg["domain_D"]["y"]
    zlim = cfg["domain_D"]["z"]
    hub_D = float(turbine["hub_height"]) / diameter
    position = turbine["position_D"]
    if not (xlim[0] + 0.5 < position[0] < xlim[1] - 0.5):
        raise ValueError("T1 rotor is outside the x-domain")
    if not (ylim[0] + 0.5 < position[1] < ylim[1] - 0.5):
        raise ValueError("T1 rotor is outside the y-domain")
    if hub_D - 0.5 <= zlim[0] or hub_D + 0.5 >= zlim[1]:
        raise ValueError("rotor disk intersects the ground or top boundary")

    for axis in ("x", "y", "z"):
        mesh_axis = cfg["mesh"][axis]
        breaks = [float(value) for value in mesh_axis["breaks_D"]]
        cells = [int(value) for value in mesh_axis["cells"]]
        grading = [float(value) for value in mesh_axis["grading"]]
        if len(breaks) != len(cells) + 1 or len(cells) != len(grading):
            raise ValueError(f"mesh.{axis} entries have inconsistent lengths")
        if any(b <= a for a, b in zip(breaks, breaks[1:])):
            raise ValueError(f"mesh.{axis}.breaks_D must be strictly increasing")
        if any(value <= 0 for value in cells + grading):
            raise ValueError(f"mesh.{axis} cells and grading must be positive")
        if (
            not math.isclose(breaks[0], float(cfg["domain_D"][axis][0]))
            or not math.isclose(breaks[-1], float(cfg["domain_D"][axis][1]))
        ):
            raise ValueError(f"mesh.{axis} must span the complete domain")

    if float(cfg["run"]["statistics_start"]) >= float(cfg["run"]["end_time"]):
        raise ValueError("statistics_start must precede end_time")
    if float(cfg["mann"]["duration"]) < float(cfg["run"]["end_time"]):
        raise ValueError("Mann duration must cover the complete production run")


def rotor_speed_rad_s(cfg: dict[str, Any]) -> float:
    return float(cfg["turbine"]["rotor_speed_rpm"]) * 2.0 * math.pi / 60.0


def tip_speed_ratio(cfg: dict[str, Any]) -> float:
    return (
        rotor_speed_rad_s(cfg)
        * float(cfg["turbine"]["radius"])
        / float(cfg["abl"]["hub_velocity"])
    )


def friction_velocity(cfg: dict[str, Any]) -> float:
    abl = cfg["abl"]
    return (
        float(abl["von_karman"])
        * float(abl["hub_velocity"])
        / math.log(
            (float(cfg["turbine"]["hub_height"]) + float(abl["roughness_length"]))
            / float(abl["roughness_length"])
        )
    )


def mean_velocity(cfg: dict[str, Any], z: float) -> float:
    """Neutral log-law velocity, regularised below the roughness length."""
    z0 = float(cfg["abl"]["roughness_length"])
    kappa = float(cfg["abl"]["von_karman"])
    return friction_velocity(cfg) / kappa * math.log((max(z, 0.0) + z0) / z0)


def turbine_positions(cfg: dict[str, Any]) -> list[dict[str, float | str]]:
    diameter = float(cfg["turbine"]["diameter"])
    hub = float(cfg["turbine"]["hub_height"])
    position = cfg["turbine"]["position_D"]
    return [
        {
            "name": "T1",
            "x": float(position[0]) * diameter,
            "y": float(position[1]) * diameter,
            "z": hub,
        }
    ]


def read_blade(path: Path | None = None) -> list[dict[str, float]]:
    source = path or ROOT / "data" / "turbines" / "phaseVI_blade.csv"
    rows: list[dict[str, float]] = []
    with source.open(encoding="utf-8") as stream:
        reader = csv.reader(line for line in stream if not line.startswith("#"))
        for row in reader:
            if not row:
                continue
            rows.append(
                {
                    "radius": float(row[0]),
                    "chord": float(row[1]),
                    "twist": float(row[2]),
                    "mount": float(row[3]),
                }
            )
    if len(rows) < 2 or any(
        b["radius"] <= a["radius"] for a, b in zip(rows, rows[1:])
    ):
        raise ValueError("blade radial stations must be strictly increasing")
    return rows


def foam_header(object_name: str, klass: str = "dictionary") -> str:
    return f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2412                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {klass};
    object      {object_name};
}}
// Generated from config/case.yaml. Do not edit by hand.

"""


def foam_vector(values: list[float] | tuple[float, ...]) -> str:
    return "(" + " ".join(f"{float(value):.9g}" for value in values) + ")"

