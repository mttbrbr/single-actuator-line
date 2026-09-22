#!/usr/bin/env python3
"""One headless entry point for checkpoint sampling, videos and LES checks."""

from __future__ import annotations

import argparse
import base64
import csv
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "case"
POST = CASE / "postProcessing" / "videoPlanes"
OUTPUT = ROOT / "postprocessing"
VIEWS = ("horizontal_minus_025D", "hub", "horizontal_plus_025D",
         "wake_1D", "wake_2D", "wake_4D", "wake_6D", "wake_8D")
FIELDS = ("velocity", "vorticity", "pressure_coefficient", "q_criterion")
ARRAYS = {"velocity": "U", "vorticity": "vorticity",
          "pressure_coefficient": "Cp", "q_criterion": "Q"}
RANGES = {"velocity": (4.0, 8.5), "vorticity": (0.0, 2.0),
          "pressure_coefficient": (-0.4, 0.8), "q_criterion": (0.0, 0.5)}
LABELS = {"velocity": "|U| (m/s)", "vorticity": "|ω| (1/s)",
          "pressure_coefficient": "Cp", "q_criterion": "Q (1/s²)"}


def video_size(view: str) -> tuple[int, int]:
    return (3840, 1920) if view.startswith("wake_") else (3840, 1440)


def config() -> dict:
    import yaml
    return yaml.safe_load((ROOT / "config/case.yaml").read_text())


def times_in(directory: Path) -> list[Decimal]:
    times = []
    if directory.is_dir():
        for item in directory.iterdir():
            if item.is_dir():
                try:
                    times.append(Decimal(item.name))
                except InvalidOperation:
                    pass
    return sorted(times)


def checkpoint_times() -> list[Decimal]:
    ranks = sorted(CASE.glob("processor[0-9]*"))
    expected = int(config()["run"]["n_processors"])
    if len(ranks) != expected:
        raise RuntimeError(f"Expected {expected} processor directories, found {len(ranks)}")
    sets = [set(times_in(rank)) for rank in ranks]
    common = sorted(t for t in set.intersection(*sets) if t > 0)
    if not common:
        raise RuntimeError("No complete decomposed checkpoint is available")
    for rank in ranks:
        for time in common:
            for name in ("U", "vorticity", "Cp", "Q"):
                if not (rank / str(time) / name).is_file():
                    raise RuntimeError(f"Incomplete checkpoint: {rank.name}/{time}/{name}")
    return common


def views_spec(cfg: dict) -> dict[str, tuple[tuple[float, float, float], tuple[int, int, int]]]:
    d = float(cfg["turbine"]["diameter"])
    h = float(cfg["turbine"]["hub_height"])
    result = {}
    for name, offset in (("horizontal_minus_025D", -0.25), ("hub", 0),
                         ("horizontal_plus_025D", 0.25)):
        result[name] = ((0, 0, h + offset * d), (0, 0, 1))
    for distance in (1, 2, 4, 6, 8):
        result[f"wake_{distance}D"] = ((distance * d, 0, h), (1, 0, 0))
    return result


def sampling_dictionary(cfg: dict) -> str:
    surfaces = []
    for name, (point, normal) in views_spec(cfg).items():
        p = " ".join(f"{v:.9g}" for v in point)
        n = " ".join(str(v) for v in normal)
        surfaces.append(f"""        {name}
        {{
            type cuttingPlane;
            planeType pointAndNormal;
            pointAndNormalDict {{ point ({p}); normal ({n}); }}
            interpolate true;
        }}""")
    return """FoamFile
{
    version 2.0;
    format ascii;
    class dictionary;
    object controlDict;
}
application postProcess;
startFrom latestTime;
functions
{
    videoPlanes
    {
        type surfaces;
        libs ("libsampling.so");
        writeControl timeStep;
        writeInterval 1;
        surfaceFormat vtk;
        fields (U vorticity Cp Q);
        surfaces
        (
""" + "\n".join(surfaces) + "\n        );\n    }\n}\n"


def sample(args: argparse.Namespace, checkpoints: list[Decimal]) -> None:
    if all((POST / str(t) / f"{view}.vtp").is_file()
           for t in checkpoints for view in VIEWS):
        print("All checkpoint planes are already sampled; skipping.")
        return
    dictionary = CASE / "system/videoPostprocessDict"
    dictionary.write_text(sampling_dictionary(config()))
    if not args.dry_run and (shutil.which("mpirun") is None or shutil.which("postProcess") is None):
        raise RuntimeError("Source OpenFOAM v2412 and make MPI available before sampling")
    command = ["mpirun", "-np", str(config()["run"]["n_processors"]),
               "postProcess", "-parallel", "-case", str(CASE),
               "-dict", str(dictionary), "-fields", "(U vorticity Cp Q)",
               "-time", f"{checkpoints[0]}:{checkpoints[-1]}"]
    print("Sampling checkpoint fields; original solver fields are not modified.", flush=True)
    if args.dry_run:
        print(" ".join(command))
        return
    with (CASE / "log.postprocessVideos").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def decode(element: ET.Element) -> np.ndarray:
    raw = base64.b64decode("".join((element.text or "").split()))
    length = struct.unpack_from("<Q", raw)[0]
    dtype = np.dtype("<f4")
    return np.frombuffer(raw, dtype=dtype, count=length // dtype.itemsize, offset=8)


def vtp(path: Path, field: str) -> tuple[np.ndarray, np.ndarray]:
    root = ET.parse(path).getroot()
    points = decode(root.find(".//Points/DataArray")).reshape(-1, 3)
    element = root.find(f".//PointData/DataArray[@Name='{ARRAYS[field]}']")
    if element is None:
        raise RuntimeError(f"Missing {ARRAYS[field]} in {path}")
    values = decode(element)
    if field in ("velocity", "vorticity"):
        values = np.linalg.norm(values.reshape(-1, 3), axis=1)
    return points, values


def frame(path: Path, view: str, field: str, time: Decimal, cfg: dict) -> np.ndarray:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    points, values = vtp(path, field)
    d = float(cfg["turbine"]["diameter"])
    h = float(cfg["turbine"]["hub_height"])
    if view.startswith("wake_"):
        x = points[:, 1] / d
        y = (points[:, 2] - h) / d
        extent = (-1.5, 1.5, -0.75, 0.75)
    else:
        x = points[:, 0] / d
        y = points[:, 1] / d
        extent = (-0.5, 7.5, -1.5, 1.5)
    # Match the D/48 core mesh; finer bins would leave unsampled stripe artefacts.
    nx, ny = (144, 72) if view.startswith("wake_") else (384, 144)
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    xedges = np.linspace(extent[0], extent[1], nx + 1)
    yedges = np.linspace(extent[2], extent[3], ny + 1)
    total = np.histogram2d(y[valid], x[valid], bins=(yedges, xedges), weights=values[valid])[0]
    count = np.histogram2d(y[valid], x[valid], bins=(yedges, xedges))[0]
    image = np.divide(total, count, out=np.full_like(total, np.nan), where=count > 0)
    # Cutting-plane vertices do not land in every display pixel. Fill display
    # gaps by interpolation; do not alter the sampled values or CFD fields.
    columns = np.arange(nx)
    rows = np.arange(ny)
    for row in image:
        known = np.isfinite(row)
        if known.any():
            row[:] = np.interp(columns, columns[known], row[known])
    for column in image.T:
        known = np.isfinite(column)
        if known.any():
            column[:] = np.interp(rows, rows[known], column[known])
    width, height = video_size(view)
    fig = plt.Figure(figsize=(width / 100, height / 100), dpi=100, facecolor="#f3d0bb")
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    lo, hi = RANGES[field]
    rendered = ax.imshow(image, origin="lower", extent=extent, aspect="auto",
                         cmap="coolwarm" if field != "vorticity" else "inferno",
                         vmin=lo, vmax=hi, interpolation="bicubic")
    ax.set_axis_off()
    ax.text(0.025, 0.972, f"NREL Phase VI  |  {view.replace('_', ' ')}  |  t = {time} s",
            transform=ax.transAxes, color="white", fontsize=16, va="top")
    bar = fig.add_axes((0.68, 0.91, 0.28, 0.018))
    cbar = fig.colorbar(rendered, cax=bar, orientation="horizontal")
    cbar.ax.tick_params(colors="white", labelsize=11, length=0, pad=1)
    cbar.outline.set_visible(False)
    cbar.set_label(LABELS[field], color="white", fontsize=12, labelpad=-2)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba())[:, :, :3].copy()


def video(args: argparse.Namespace, checkpoints: list[Decimal]) -> None:
    cfg = config()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    output = OUTPUT / "videos"
    sampled = times_in(POST)
    available = [t for t in checkpoints if t in sampled]
    if available != checkpoints:
        raise RuntimeError(f"videoPlanes has {len(available)}/{len(checkpoints)} checkpoints. Run sample first; missing {sorted(set(checkpoints)-set(available))[:5]}")
    for view in VIEWS:
        view_fields = FIELDS if not view.startswith("wake_") else FIELDS[:2]
        for field in view_fields:
            destination = output / field / f"{view}.mp4"
            print(f"{view}/{field}: {len(checkpoints)} frames, {checkpoints[0]}..{checkpoints[-1]} -> {destination}", flush=True)
            if args.dry_run:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                       "-pixel_format", "rgb24", "-video_size", "%dx%d" % video_size(view), "-framerate", str(args.fps),
                       "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                       "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)]
            process = subprocess.Popen(command, stdin=subprocess.PIPE)
            try:
                for t in checkpoints:
                    path = POST / str(t) / f"{view}.vtp"
                    if not path.is_file():
                        raise RuntimeError(f"Missing sampled plane: {path}")
                    process.stdin.write(frame(path, view, field, t, cfg).tobytes())
            finally:
                process.stdin.close()
                if process.wait() != 0:
                    raise RuntimeError(f"ffmpeg failed for {destination}")
        main_video = output / "main" / f"{view}.mp4"
        print(f"{view}/main -> {main_video}", flush=True)
        if args.dry_run:
            continue
        main_video.parent.mkdir(parents=True, exist_ok=True)
        inputs = []
        for field in view_fields:
            inputs += ["-i", str(output / field / f"{view}.mp4")]
        n = len(view_fields)
        width, height = (1920, 720) if n == 4 else (1920, 960)
        filters = []
        for i in range(n):
            filters.append(f"[{i}:v]scale={width}:{height}[v{i}]")
        labels = "".join(f"[v{i}]" for i in range(n))
        layout = "|".join(
            f"{(i % 2) * width}_{(i // 2) * height}" for i in range(n)
        )
        filters.append(f"{labels}xstack=inputs={n}:layout={layout}[out]")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
                   "-filter_complex", ";".join(filters), "-map", "[out]",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(main_video)]
        subprocess.run(command, check=True)


def diagnostics() -> None:
    for tool in ("export_final_les_diagnostics.py", "postprocess_wakes.py"):
        subprocess.run([sys.executable, str(ROOT / "tools" / tool)], cwd=ROOT, check=True)
    converter = shutil.which("rsvg-convert")
    if converter:
        for svg in (OUTPUT / "artifacts").glob("*t*.svg"):
            subprocess.run([converter, "-w", "1800", "-o", str(svg.with_suffix(".png")),
                            str(svg)], check=True)


def verify_videos(checkpoints: list[Decimal]) -> None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required to verify the videos")
    expected = sum(2 if view.startswith("wake_") else 4 for view in VIEWS) + len(VIEWS)
    paths = sorted((OUTPUT / "videos").glob("*/*.mp4"))
    if len(paths) != expected:
        raise RuntimeError(f"Expected {expected} videos, found {len(paths)}")
    for path in paths:
        command = [ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
                   "-show_entries", "stream=nb_read_frames",
                   "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
        count = int(subprocess.check_output(command, text=True).strip())
        if count != len(checkpoints):
            raise RuntimeError(f"{path}: {count} frames, expected {len(checkpoints)}")
    print(f"Verified {expected} videos with {len(checkpoints)} frames each, "
          f"t={checkpoints[0]}..{checkpoints[-1]} s")


def images(checkpoints: list[Decimal], args: argparse.Namespace) -> None:
    """Extract the verified 4K video frames, with a time index, as PNGs."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    destination = OUTPUT / "images"
    if args.dry_run:
        print(f"Would export {len(checkpoints)} PNGs from each video to {destination}")
        return
    verify_videos(checkpoints)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "checkpoint_times.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("frame", "time_s"))
        writer.writerows((i, str(t)) for i, t in enumerate(checkpoints))
    for movie in sorted((OUTPUT / "videos").glob("*/*.mp4")):
        target = destination / movie.parent.name / movie.stem
        target.mkdir(parents=True, exist_ok=True)
        print(f"Images: {movie.parent.name}/{movie.stem} -> {target}", flush=True)
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(movie), "-vsync", "0",
                        str(target / "frame_%04d.png")], check=True)
        if len(list(target.glob("frame_*.png"))) != len(checkpoints):
            raise RuntimeError(f"Incomplete PNG export: {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "sample", "videos", "images", "diagnostics", "verify", "all"))
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    checkpoints = checkpoint_times()
    print(f"Case: {len(checkpoints)} complete checkpoints, {checkpoints[0]}..{checkpoints[-1]} s")
    if args.action == "status":
        print(f"Sampled video times: {len(times_in(POST))}")
        return
    if args.action in ("sample", "all"):
        sample(args, checkpoints)
    if args.action in ("videos", "all"):
        video(args, checkpoints)
    if args.action in ("diagnostics", "all"):
        diagnostics()
    if args.action in ("videos", "verify", "all") and not args.dry_run:
        verify_videos(checkpoints)
    if args.action in ("images", "all"):
        images(checkpoints, args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"ERROR: {error}") from error
