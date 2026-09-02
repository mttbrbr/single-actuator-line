#!/usr/bin/env python3
"""Render OpenFOAM dictionaries from the single YAML source of truth."""

from __future__ import annotations

import argparse
import difflib
import json
import math
import sys
from pathlib import Path

from case_config import (
    DEFAULT_CONFIG,
    ROOT,
    foam_header,
    foam_vector,
    friction_velocity,
    load_config,
    read_blade,
    tip_speed_ratio,
    turbine_positions,
)

CASE = ROOT / "case"


def render_block_mesh(cfg: dict, profile: str) -> str:
    diameter = float(cfg["turbine"]["diameter"])
    breaks = {
        axis: [float(value) * diameter for value in cfg["mesh"][axis]["breaks_D"]]
        for axis in ("x", "y", "z")
    }
    cells = {
        axis: [
            int(value)
            for value in (
                cfg["mesh"][axis]["cells"]
                if profile == "production"
                else cfg["smoke"]["cells"][axis]
            )
        ]
        for axis in ("x", "y", "z")
    }
    grading = {
        axis: [float(value) for value in cfg["mesh"][axis]["grading"]]
        for axis in ("x", "y", "z")
    }

    nx, ny, nz = (len(breaks[axis]) for axis in ("x", "y", "z"))

    def vertex(ix: int, iy: int, iz: int) -> int:
        return (iz * ny + iy) * nx + ix

    vertices = []
    for z in breaks["z"]:
        for y in breaks["y"]:
            for x in breaks["x"]:
                vertices.append(f"    ({x:.9g} {y:.9g} {z:.9g})")

    blocks = []
    inlet_faces = []
    outlet_faces = []
    ground_faces = []
    top_faces = []
    side_faces = []
    for iz in range(nz - 1):
        for iy in range(ny - 1):
            for ix in range(nx - 1):
                v000 = vertex(ix, iy, iz)
                v100 = vertex(ix + 1, iy, iz)
                v110 = vertex(ix + 1, iy + 1, iz)
                v010 = vertex(ix, iy + 1, iz)
                v001 = vertex(ix, iy, iz + 1)
                v101 = vertex(ix + 1, iy, iz + 1)
                v111 = vertex(ix + 1, iy + 1, iz + 1)
                v011 = vertex(ix, iy + 1, iz + 1)
                blocks.append(
                    "    hex "
                    f"({v000} {v100} {v110} {v010} {v001} {v101} {v111} {v011}) "
                    f"({cells['x'][ix]} {cells['y'][iy]} {cells['z'][iz]}) "
                    f"simpleGrading ({grading['x'][ix]:.9g} "
                    f"{grading['y'][iy]:.9g} {grading['z'][iz]:.9g})"
                )
                if ix == 0:
                    inlet_faces.append(f"            ({v000} {v001} {v011} {v010})")
                if ix == nx - 2:
                    outlet_faces.append(f"            ({v100} {v110} {v111} {v101})")
                if iz == 0:
                    ground_faces.append(f"            ({v000} {v010} {v110} {v100})")
                if iz == nz - 2:
                    top_faces.append(f"            ({v001} {v101} {v111} {v011})")
                if iy == 0:
                    side_faces.append(f"            ({v000} {v100} {v101} {v001})")
                if iy == ny - 2:
                    side_faces.append(f"            ({v010} {v011} {v111} {v110})")

    def patch(name: str, patch_type: str, faces: list[str]) -> str:
        return (
            f"    {name}\n"
            "    {\n"
            f"        type {patch_type};\n"
            "        faces\n"
            "        (\n"
            + "\n".join(faces)
            + "\n        );\n"
            "    }"
        )

    return (
        foam_header("blockMeshDict")
        + "scale 1;\n\nvertices\n(\n"
        + "\n".join(vertices)
        + "\n);\n\nblocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\nedges ();\n\nboundary\n(\n"
        + "\n".join(
            (
                patch("inlet", "patch", inlet_faces),
                patch("outlet", "patch", outlet_faces),
                patch("ground", "wall", ground_faces),
                patch("top", "patch", top_faces),
                patch("sides", "symmetry", side_faces),
            )
        )
        + "\n);\n\nmergePatchPairs ();\n"
    )


def render_toposet(cfg: dict) -> str:
    diameter = float(cfg["turbine"]["diameter"])
    turbine = turbine_positions(cfg)[0]
    minimum = (
        float(turbine["x"]) - 0.5 * diameter,
        float(turbine["y"]) - 1.0 * diameter,
        0.0,
    )
    maximum = (
        float(turbine["x"]) + 0.5 * diameter,
        float(turbine["y"]) + 1.0 * diameter,
        2.25 * diameter,
    )
    return foam_header("topoSetDict") + f"""actions
(
    {{
        name T1;
        type cellSet;
        action new;
        source boxToCell;
        box {foam_vector(minimum)} {foam_vector(maximum)};
    }}
);
"""


def blade_element_data(cfg: dict) -> str:
    pitch = float(cfg["turbine"]["pitch_deg"])
    blade = read_blade()
    n_segments = len(blade) - 1
    if int(cfg["turbine"]["n_elements"]) % n_segments:
        raise ValueError(
            "turbine.n_elements must be a multiple of the blade geometry "
            f"segment count ({n_segments})"
        )
    lines = []
    for row in blade:
        # NREL defines positive twist/pitch towards feather, whereas
        # turbinesFoam's axial-flow element convention has the opposite sign.
        turbine_pitch = -(row["twist"] + pitch)
        lines.append(
            "                    "
            f"(0 {row['radius']:.6g} 0 {row['chord']:.6g} "
            f"{row['mount']:.6g} {turbine_pitch:.6g})"
        )
    return "\n".join(lines)


def render_turbine_option(cfg: dict, turbine: dict, index: int) -> str:
    tcfg = cfg["turbine"]
    velocity = float(cfg["abl"]["hub_velocity"])
    n_elements = int(tcfg["n_elements"])
    n_root = max(1, round(n_elements * (1.2575 - 0.5083) / (float(tcfg["radius"]) - 0.5083)))
    profiles = " ".join(["cylinder"] * n_root + ["S809"] * (n_elements - n_root))
    dynamic = "on" if tcfg["dynamic_stall"] else "off"
    write_elements = "true" if index == 0 else "false"
    return f"""{turbine['name']}
{{
    type axialFlowTurbineALSource;
    active on;

    axialFlowTurbineALSourceCoeffs
    {{
        fieldNames (U);
        selectionMode cellSet;
        cellSet {turbine['name']};
        origin ({turbine['x']:.8g} {turbine['y']:.8g} {turbine['z']:.8g});
        axis {foam_vector(tcfg['axis'])};
        verticalDirection {foam_vector(tcfg['vertical_direction'])};
        freeStreamVelocity ({velocity:.8g} 0 0);
        tipSpeedRatio {tip_speed_ratio(cfg):.8g};
        rotorRadius {float(tcfg['radius']):.8g};
        azimuthalOffset {index * 17.0:.8g};

        dynamicStall
        {{
            active {dynamic};
            dynamicStallModel LeishmanBeddoes;
        }}

        endEffects
        {{
            active on;
            endEffectsModel Glauert;
            GlauertCoeffs {{ tipEffects on; rootEffects on; }}
        }}

        blades
        {{
            blade1
            {{
                writePerf true;
                writeElementPerf {write_elements};
                nElements {n_elements};
                elementProfiles ({profiles});
                elementData
                (
{blade_element_data(cfg)}
                );
            }}
            blade2
            {{
                $blade1;
                writePerf false;
                writeElementPerf false;
                azimuthalOffset 180.0;
            }}
        }}

        tower
        {{
            includeInTotalDrag false;
            nElements 12;
            elementProfiles (cylinder);
            elementData
            (
                (-1.401 -12.192 0.50)
                (-1.401  -8.000 0.46)
                (-1.401  -4.000 0.42)
                (-1.401   0.000 0.38)
            );
        }}

        hub
        {{
            nElements 4;
            elementProfiles (cylinder);
            elementData ((0 0.50 0.50) (0 -0.50 0.50));
        }}

        profileData
        {{
            S809
            {{
                Re 1e6;
                GaussianCoeffs
                {{
                    chordFactor 0.25;
                    dragFactor 1.0;
                    meshFactor {float(tcfg['gaussian_mesh_factor']):.8g};
                }}
                data (#include "../../data/airfoils/S809_Re1M_extended");
            }}
            cylinder {{ data ((-180 0 1.1 0) (180 0 1.1 0)); }}
        }}
    }}
}}
"""


def render_fvoptions(cfg: dict) -> str:
    sections = [
        render_turbine_option(cfg, turbine, index)
        for index, turbine in enumerate(turbine_positions(cfg))
    ]
    return foam_header("fvOptions") + "\n".join(sections)


def render_functions(cfg: dict) -> str:
    diameter = float(cfg["turbine"]["diameter"])
    positions = turbine_positions(cfg)
    probes = []
    planes = []
    for turbine in positions:
        for downstream in (1, 2, 4, 6, 8):
            x = float(turbine["x"]) + downstream * diameter
            if x < float(cfg["domain_D"]["x"][1]) * diameter:
                probes.append((x, float(turbine["y"]), float(turbine["z"])))
                planes.append((f"{turbine['name']}_{downstream}D", (x, 0.0, 0.0)))
    probe_lines = "\n".join(f"            {foam_vector(point)}" for point in probes)
    plane_lines = "\n".join(
        f"""        {name}
        {{
            type cuttingPlane;
            planeType pointAndNormal;
            pointAndNormalDict
            {{
                point {foam_vector(point)};
                normal (1 0 0);
            }}
            interpolate true;
        }}"""
        for name, point in planes
    )
    start = float(cfg["run"]["statistics_start"])
    return f"""QCriterion
{{
    type Q;
    libs (fieldFunctionObjects);
    field U;
    executeControl writeTime;
    writeControl writeTime;
}}

fieldAverage
{{
    type fieldAverage;
    libs ("libfieldFunctionObjects.so");
    executeControl timeStep;
    executeInterval 1;
    writeControl writeTime;
    timeStart {start:.8g};
    fields
    (
        U {{ mean on; prime2Mean on; base time; }}
        p {{ mean on; prime2Mean off; base time; }}
    );
}}

wakeCentrelineProbes
{{
    type probes;
    libs ("libsampling.so");
    fields (U p);
    writeControl timeStep;
    writeInterval 10;
    probeLocations
    (
{probe_lines}
    );
}}

wakePlanes
{{
    type surfaces;
    libs ("libsampling.so");
    writeControl writeTime;
    timeStart {start:.8g};
    surfaceFormat vtk;
    fields (U UMean UPrime2Mean p);
    surfaces
    (
{plane_lines}
    );
}}
"""


def render_control_dict(cfg: dict, profile: str) -> str:
    smoke = profile == "smoke"
    run = cfg["smoke"] if smoke else cfg["run"]
    functions = (
        "functions {};"
        if smoke
        else 'functions\n{\n    #include "include/generatedFunctions.dict"\n}'
    )
    libraries = (
        '("libturbinesFoam.so");'
        if smoke
        else """(
    "libturbinesFoam.so"
    "libfieldFunctionObjects.so"
    "libsampling.so"
);"""
    )
    return foam_header("controlDict") + f"""application pimpleFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {float(run['end_time']):.8g};
deltaT {float(cfg['run']['initial_delta_t']):.8g};
writeControl adjustableRunTime;
writeInterval {float(cfg['run']['write_interval'] if not smoke else run['end_time']):.8g};
purgeWrite {int(cfg['run'].get('purge_write', 0) if not smoke else 0)};
writeFormat binary;
writePrecision 10;
writeCompression off;
timeFormat general;
timePrecision 8;
runTimeModifiable true;
adjustTimeStep true;
maxCo {float(run['max_courant']):.8g};
maxDeltaT {float(cfg['run']['max_delta_t']):.8g};

libs {libraries}
{functions}
"""


def render_decompose(cfg: dict, profile: str) -> str:
    nproc = int(
        cfg["run"]["n_processors"]
        if profile == "production"
        else cfg["smoke"]["n_processors"]
    )
    return foam_header("decomposeParDict") + f"numberOfSubdomains {nproc};\nmethod scotch;\n"


def render_metadata(cfg: dict, profile: str) -> str:
    return json.dumps(
        {
            "profile": profile,
            "turbines": turbine_positions(cfg),
            "mesh_cells": math.prod(
                sum(
                    cfg["mesh"][axis]["cells"]
                    if profile == "production"
                    else cfg["smoke"]["cells"][axis]
                )
                for axis in ("x", "y", "z")
            ),
            "tip_speed_ratio_computed": tip_speed_ratio(cfg),
            "friction_velocity": friction_velocity(cfg),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def outputs(cfg: dict, profile: str) -> dict[Path, str]:
    return {
        CASE / "system" / "blockMeshDict": render_block_mesh(cfg, profile),
        CASE / "system" / "topoSetDict": render_toposet(cfg),
        CASE / "system" / "fvOptions": render_fvoptions(cfg),
        CASE / "system" / "include" / "generatedFunctions.dict": render_functions(cfg),
        CASE / "system" / "include" / "generatedMetadata.json": render_metadata(cfg, profile),
        CASE / "system" / "controlDict": render_control_dict(cfg, profile),
        CASE / "system" / "decomposeParDict": render_decompose(cfg, profile),
    }


def check_outputs(rendered: dict[Path, str]) -> bool:
    clean = True
    for path, expected in rendered.items():
        if not path.exists():
            print(f"missing generated file: {path.relative_to(ROOT)}", file=sys.stderr)
            clean = False
            continue
        current = path.read_text(encoding="utf-8")
        if current != expected:
            print(f"stale generated file: {path.relative_to(ROOT)}", file=sys.stderr)
            diff = difflib.unified_diff(
                current.splitlines(), expected.splitlines(), fromfile="current", tofile="expected", n=2
            )
            print("\n".join(list(diff)[:40]), file=sys.stderr)
            clean = False
    return clean


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--profile", choices=("production", "smoke"), default="production")
    parser.add_argument("--check", action="store_true", help="fail if generated files are absent or stale")
    args = parser.parse_args()

    cfg = load_config(args.config)
    rendered = outputs(cfg, args.profile)
    if args.check:
        return 0 if check_outputs(rendered) else 1
    for path, content in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
