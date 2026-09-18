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
    visualization = render_visualization_functions(cfg)
    return f"""QCriterion
{{
    type Q;
    libs (fieldFunctionObjects);
    field U;
    executeControl timeStep;
    writeControl writeTime;
}}

vorticityField
{{
    type vorticity;
    libs (fieldFunctionObjects);
    field U;
    result vorticity;
    executeControl timeStep;
    writeControl writeTime;
}}

pressureCoefficient
{{
    type pressure;
    libs (fieldFunctionObjects);
    mode staticCoeff;
    p p;
    U U;
    rho rhoInf;
    rhoInf 1;
    pInf 0;
    UInf {foam_vector((float(cfg['abl']['hub_velocity']), 0.0, 0.0))};
    result Cp;
    executeControl timeStep;
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

DESRegions
{{
    type DESModelRegions;
    libs ("libfieldFunctionObjects.so");
    result LESRegion;
    executeControl timeStep;
    writeControl writeTime;
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
    fields (U UMean UPrime2Mean p k LESRegion);
    surfaces
    (
{plane_lines}
    );
}}
{visualization}
"""


def render_visualization_functions(cfg: dict) -> str:
    settings = cfg.get("visualization", {})
    if not settings.get("enabled", False):
        return ""

    diameter = float(cfg["turbine"]["diameter"])
    hub = float(cfg["turbine"]["hub_height"])
    turbine = turbine_positions(cfg)[0]
    write_control = settings["write_control"]
    write_interval = int(settings["write_interval"])
    fields = settings["fields"]

    def renderer(
        image_name: str,
        function_object: str,
        field_settings: dict,
        image_size: tuple[int, int],
        focal: tuple[float, float, float],
        position: tuple[float, float, float],
        up: tuple[float, float, float],
        clip_min: tuple[float, float, float],
        clip_max: tuple[float, float, float],
        context: str,
        zoom: float,
    ) -> str:
        value_range = foam_vector(tuple(float(v) for v in field_settings["range"]))
        width, height = image_size
        return f"""render_{image_name}
{{
    type runTimePostProcessing;
    libs (\"librunTimePostProcessing.so\");
    parallel false;
    executeControl none;
    writeControl {write_control};
    writeInterval {write_interval};

    output
    {{
        name {image_name};
        width {width};
        height {height};
    }}

    camera
    {{
        parallelProjection yes;
        zoom {zoom:.8g};
        clipBox {foam_vector(clip_min)}{foam_vector(clip_max)};
        focalPoint {foam_vector(focal)};
        up {foam_vector(up)};
        position {foam_vector(position)};
    }}

    colours
    {{
        background (0.025 0.035 0.055);
        background2 (0.075 0.095 0.14);
        text (0.94 0.96 1);
        edge (0.25 0.3 0.4);
        surface (0.5 0.5 0.5);
    }}

    text
    {{
        context
        {{
            string "{context}";
            position (0.025 0.945);
            halign left;
            size 17;
            opacity 0.9;
            bold yes;
            shadow yes;
            visible yes;
        }}
    }}

    surfaces
    {{
        hubHeightPlane
        {{
            type functionObjectSurface;
            functionObject {function_object};
            liveObject true;
            representation surface;
            smooth true;
            visible yes;
            featureEdges none;
            colourBy field;
            field {field_settings['field']};
            colourMap {field_settings['colour_map']};
            range {value_range};
            opacity 1;
            scalarBar
            {{
                visible yes;
                position (0.68 0.865);
                size (0.285 0.055);
                vertical no;
                fontSize 14;
                titleSize 17;
                title \"{field_settings['title']}\";
                labelFormat \"%.2g\";
                numberOfLabels 5;
                bold yes;
                shadow yes;
            }}
        }}
    }}
}}
"""

    horizontal_offsets = [float(value) for value in settings["horizontal_offsets_D"]]
    x_limits = [float(value) * diameter for value in settings["view_D"]["x"]]
    y_limits = [float(value) * diameter for value in settings["view_D"]["y"]]
    horizontal_surfaces = []
    renderers = []
    for offset in horizontal_offsets:
        plane_z = hub + offset * diameter
        if offset == 0:
            plane_name = "hubHeight"
            image_prefix = ""
            label = "hub"
        else:
            direction = "plus" if offset > 0 else "minus"
            magnitude = f"{abs(offset):.2f}".replace(".", "")
            plane_name = f"hub{direction.title()}{magnitude}D"
            image_prefix = f"horizontal_{direction}_{magnitude}D_"
            label = f"hub {offset:+.2f}D"
        horizontal_surfaces.append(
            f"""        {plane_name}
        {{
            type cuttingPlane;
            planeType pointAndNormal;
            pointAndNormalDict
            {{
                point {foam_vector((float(turbine['x']), float(turbine['y']), plane_z))};
                normal (0 0 1);
            }}
            interpolate true;
        }}"""
        )
        focal = (
            0.5 * (x_limits[0] + x_limits[1]) + 0.5 * diameter,
            0.5 * (y_limits[0] + y_limits[1]),
            plane_z,
        )
        position = (focal[0], focal[1], plane_z + 20.0 * diameter)
        clip_min = (x_limits[0], y_limits[0], plane_z - 0.01 * diameter)
        clip_max = (x_limits[1], y_limits[1], plane_z + 0.01 * diameter)
        for field_name, field_settings in fields.items():
            renderers.append(
                renderer(
                    f"{image_prefix}{field_name}",
                    f"horizontalPlanes.{plane_name}",
                    field_settings,
                    tuple(int(value) for value in settings["image_size"]),
                    focal,
                    position,
                    (0.0, 1.0, 0.0),
                    clip_min,
                    clip_max,
                    f"NREL Phase VI  |  horizontal wake  {label}  |  z/D = {plane_z / diameter:.2f}",
                    1.35,
                )
            )

    cross_y = [float(value) * diameter for value in settings["cross_view_D"]["y"]]
    cross_z = [hub + float(value) * diameter for value in settings["cross_view_D"]["z_offset"]]
    cross_sections = [float(value) for value in settings["cross_sections_D"]]
    cross_surfaces = []
    for downstream in cross_sections:
        plane_x = float(turbine["x"]) + downstream * diameter
        distance_name = f"{downstream:g}D".replace(".", "p")
        plane_name = f"wake{distance_name}"
        cross_surfaces.append(
            f"""        {plane_name}
        {{
            type cuttingPlane;
            planeType pointAndNormal;
            pointAndNormalDict
            {{
                point {foam_vector((plane_x, float(turbine['y']), hub))};
                normal (1 0 0);
            }}
            interpolate true;
        }}"""
        )
        focal = (plane_x, 0.5 * (cross_y[0] + cross_y[1]), 0.5 * (cross_z[0] + cross_z[1]))
        position = (plane_x - 20.0 * diameter, focal[1], focal[2])
        clip_min = (plane_x - 0.01 * diameter, cross_y[0], cross_z[0])
        clip_max = (plane_x + 0.01 * diameter, cross_y[1], cross_z[1])
        for field_name in settings["cross_fields"]:
            renderers.append(
                renderer(
                    f"wake_{distance_name}_{field_name}",
                    f"wakeCrossSections.{plane_name}",
                    fields[field_name],
                    tuple(int(value) for value in settings["cross_image_size"]),
                    focal,
                    position,
                    (0.0, 0.0, 1.0),
                    clip_min,
                    clip_max,
                    f"NREL Phase VI  |  rotor-parallel wake section  x/D = {downstream:g}",
                    1.05,
                )
            )

    horizontal_fields = " ".join(str(item["field"]) for item in fields.values())
    cross_fields = " ".join(str(fields[name]["field"]) for name in settings["cross_fields"])
    return f"""
horizontalPlanes
{{
    type surfaces;
    libs (\"libsampling.so\");
    executeControl timeStep;
    executeInterval 1;
    writeControl none;
    surfaceFormat none;
    store true;
    sampleOnExecute true;
    interpolationScheme cellPoint;
    fields ({horizontal_fields});
    surfaces
    {{
{chr(10).join(horizontal_surfaces)}
    }}
}}

wakeCrossSections
{{
    type surfaces;
    libs ("libsampling.so");
    executeControl timeStep;
    executeInterval 1;
    writeControl none;
    surfaceFormat none;
    store true;
    sampleOnExecute true;
    interpolationScheme cellPoint;
    fields ({cross_fields});
    surfaces
    {{
{chr(10).join(cross_surfaces)}
    }}
}}

{"".join(renderers)}"""


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
