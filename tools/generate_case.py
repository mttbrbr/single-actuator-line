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


def scaled_box(box: dict, diameter: float) -> tuple[list[float], list[float]]:
    return (
        [float(value) * diameter for value in box["min"]],
        [float(value) * diameter for value in box["max"]],
    )


def render_block_mesh(cfg: dict, profile: str) -> str:
    diameter = float(cfg["turbine"]["diameter"])
    x0, x1 = (float(v) * diameter for v in cfg["domain_D"]["x"])
    y0, y1 = (float(v) * diameter for v in cfg["domain_D"]["y"])
    z0, z1 = (float(v) * diameter for v in cfg["domain_D"]["z"])
    cells = cfg["mesh"]["base_cells"] if profile == "production" else cfg["smoke"]["base_cells"]
    return foam_header("blockMeshDict") + f"""convertToMeters 1;

vertices
(
    ({x0:.8g} {y0:.8g} {z0:.8g})
    ({x1:.8g} {y0:.8g} {z0:.8g})
    ({x1:.8g} {y1:.8g} {z0:.8g})
    ({x0:.8g} {y1:.8g} {z0:.8g})
    ({x0:.8g} {y0:.8g} {z1:.8g})
    ({x1:.8g} {y0:.8g} {z1:.8g})
    ({x1:.8g} {y1:.8g} {z1:.8g})
    ({x0:.8g} {y1:.8g} {z1:.8g})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({cells[0]} {cells[1]} {cells[2]}) simpleGrading (1 1 1)
);

edges ();

boundary
(
    inlet  {{ type patch; faces ((0 4 7 3)); }}
    outlet {{ type patch; faces ((1 2 6 5)); }}
    ground {{ type wall;  faces ((0 3 2 1)); }}
    top    {{ type patch; faces ((4 5 6 7)); }}
    sides  {{ type symmetry; faces ((0 1 5 4) (3 7 6 2)); }}
);

mergePatchPairs ();
"""


def render_snappy(cfg: dict, profile: str) -> str:
    diameter = float(cfg["turbine"]["diameter"])
    cap = 99 if profile == "production" else int(cfg["smoke"]["refinement_level_cap"])
    boxes = []
    for key, name in (
        ("inlet_slab_D", "inletSlab"),
        ("transition_D", "transition"),
        ("wake_core_D", "wakeCore"),
    ):
        item = cfg["mesh"][key]
        minimum, maximum = scaled_box(item, diameter)
        boxes.append((name, minimum, maximum, min(int(item["level"]), cap)))
    location = [
        float(cfg["domain_D"]["x"][0]) * diameter + 0.123 * diameter,
        0.013 * diameter,
        0.123 * diameter,
    ]
    geometry = "\n".join(
        f"""    {name}
    {{
        type searchableBox;
        min {foam_vector(minimum)};
        max {foam_vector(maximum)};
    }}"""
        for name, minimum, maximum, _ in boxes
    )
    regions = "\n".join(
        f"""        {name}
        {{
            mode inside;
            levels ((1e15 {level}));
        }}"""
        for name, _, _, level in boxes
        if level > 0
    )
    max_cells = int(cfg["mesh"]["max_global_cells"] if profile == "production" else 900000)
    return foam_header("snappyHexMeshDict") + f"""castellatedMesh true;
snap            false;
addLayers       false;

geometry
{{
{geometry}
}}

castellatedMeshControls
{{
    maxLocalCells 800000;
    maxGlobalCells {max_cells};
    minRefinementCells 0;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels {int(cfg['mesh']['n_cells_between_levels'])};
    features ();
    refinementSurfaces {{}}
    resolveFeatureAngle 30;
    refinementRegions
    {{
{regions}
    }}
    locationInMesh {foam_vector(location)};
    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
    nFeatureSnapIter 0;
}}

addLayersControls
{{
    relativeSizes true;
    layers {{}}
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 60;
    nRelaxIter 5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}

meshQualityControls
{{
    #includeEtc "caseDicts/meshQualityDict"
    relaxed {{ maxNonOrtho 75; }}
}}

writeFlags (scalarLevels);
mergeTolerance 1e-6;
"""


def render_toposet(cfg: dict) -> str:
    diameter = float(cfg["turbine"]["diameter"])
    entries = []
    for turbine in turbine_positions(cfg):
        p1 = [float(turbine["x"]) - 0.30 * diameter, float(turbine["y"]), float(turbine["z"])]
        p2 = [float(turbine["x"]) + 0.30 * diameter, float(turbine["y"]), float(turbine["z"])]
        entries.append(
            f"""    {{
        name {turbine['name']};
        type cellSet;
        action new;
        source cylinderToCell;
        point1 {foam_vector(p1)};
        point2 {foam_vector(p2)};
        radius {0.75 * diameter:.8g};
    }}"""
        )
    return foam_header("topoSetDict") + "actions\n(\n" + "\n".join(entries) + "\n);\n"


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
    return f"""fieldAverage
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
purgeWrite 0;
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
            "layout_seed": cfg["layout"]["seed"],
            "turbines": turbine_positions(cfg),
            "tip_speed_ratio_computed": tip_speed_ratio(cfg),
            "friction_velocity": friction_velocity(cfg),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def outputs(cfg: dict, profile: str) -> dict[Path, str]:
    return {
        CASE / "system" / "blockMeshDict": render_block_mesh(cfg, profile),
        CASE / "system" / "snappyHexMeshDict": render_snappy(cfg, profile),
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

