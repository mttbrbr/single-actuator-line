#!/usr/bin/env python3
"""Create videos for every rendered view, grouped by view and field."""

from __future__ import annotations

import argparse
import math
import shutil
import struct
import subprocess
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ("velocity", "vorticity", "pressure_coefficient", "q_criterion")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create combined and per-field MP4 files for every rendered view."
    )
    parser.add_argument("--case", type=Path, default=Path("case"))
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("videos"))
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--start", type=Decimal)
    parser.add_argument("--end", type=Decimal)
    parser.add_argument("--dry-run", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--combined-only", action="store_true")
    group.add_argument("--single-only", action="store_true")
    return parser.parse_args()


def identify(render_dir: Path) -> tuple[str, str] | None:
    name = render_dir.name.removeprefix("render_")
    for field in sorted(FIELDS, key=len, reverse=True):
        if name == field:
            return "hub", field
        suffix = f"_{field}"
        if name.endswith(suffix):
            return name[: -len(suffix)], field
    return None


def sequence(render_dir: Path) -> dict[Decimal, Path]:
    images: dict[Decimal, Path] = {}
    for image in render_dir.glob("*/*.png"):
        try:
            time = Decimal(image.parent.name)
        except InvalidOperation:
            continue
        images[time] = image.resolve()
    return images


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise SystemExit(f"Not a PNG file: {path}")
        stream.read(8)
        return struct.unpack(">II", stream.read(8))


def filtered_times(
    sequences: list[dict[Decimal, Path]], args: argparse.Namespace
) -> list[Decimal]:
    times = sorted(
        time
        for time in set.intersection(*(set(item) for item in sequences))
        if (args.start is None or time >= args.start)
        and (args.end is None or time <= args.end)
    )
    if not times:
        return []
    latest_sizes = [png_size(item[times[-1]]) for item in sequences]
    return [
        time
        for time in times
        if all(
            png_size(item[time]) == expected
            for item, expected in zip(sequences, latest_sizes, strict=True)
        )
    ]


def stage_sequence(directory: Path, images: dict[Decimal, Path], times: list[Decimal]) -> None:
    directory.mkdir(parents=True)
    for index, time in enumerate(times):
        (directory / f"{index:06d}.png").symlink_to(images[time])


def encoding(args: argparse.Namespace) -> list[str]:
    return [
        "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf),
        "-movflags", "+faststart", "-r", str(args.fps),
    ]


def encode_single(ffmpeg: str, source: Path, output: Path, args: argparse.Namespace) -> None:
    height = args.width * 3 // 8
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-hide_banner", "-y", "-framerate", str(args.fps),
        "-i", str(source / "%06d.png"), "-vf",
        f"scale={args.width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={args.width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101522,"
        "format=yuv420p", *encoding(args), str(output),
    ]
    subprocess.run(command, check=True)


def encode_combined(
    ffmpeg: str, sources: list[Path], output: Path, args: argparse.Namespace
) -> None:
    count = len(sources)
    columns = 2 if count > 1 else 1
    cell_width = args.width // columns
    cell_height = cell_width * 3 // 8
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-hide_banner", "-y"]
    for source in sources:
        command.extend(["-framerate", str(args.fps), "-i", str(source / "%06d.png")])
    filters, layout = [], []
    for index in range(count):
        filters.append(
            f"[{index}:v]scale={cell_width}:{cell_height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:color=0x101522"
            f"[v{index}]"
        )
        layout.append(f"{(index % columns) * cell_width}_{(index // columns) * cell_height}")
    inputs = "".join(f"[v{index}]" for index in range(count))
    filters.append(
        f"{inputs}xstack=inputs={count}:layout={'|'.join(layout)}:"
        "fill=0x101522,format=yuv420p[out]"
    )
    command.extend(
        ["-filter_complex", ";".join(filters), "-map", "[out]", *encoding(args), str(output)]
    )
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    if args.fps <= 0:
        raise SystemExit("--fps must be positive")
    if args.width <= 0 or args.width % 4:
        raise SystemExit("--width must be positive and divisible by four")
    if not 0 <= args.crf <= 51:
        raise SystemExit("--crf must be between 0 and 51")

    post = args.case.resolve() / "postProcessing"
    views: dict[str, dict[str, dict[Decimal, Path]]] = {}
    for render_dir in sorted(post.glob("render_*")):
        identity = identify(render_dir)
        if identity is None:
            continue
        view, field = identity
        images = sequence(render_dir)
        if images:
            views.setdefault(view, {})[field] = images
    if not views:
        raise SystemExit(f"No rendered image sequences found below {post}")

    output_root = args.output_dir.resolve()
    if output_root.suffix.lower() == ".mp4":
        legacy_output = output_root
        output_root = legacy_output.with_name(f"{legacy_output.stem}_videos")
        print(
            f"Note: -o now selects an output directory; using {output_root} "
            f"for legacy argument {legacy_output.name}"
        )
    elif output_root.exists() and not output_root.is_dir():
        raise SystemExit(f"Output path exists and is not a directory: {output_root}")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None and not args.dry_run:
        raise SystemExit("ffmpeg is required but was not found in PATH")

    jobs = 0
    with tempfile.TemporaryDirectory(prefix="sal-video-") as temporary:
        staging_root = Path(temporary)
        for view, fields in sorted(views.items()):
            ordered_fields = [field for field in FIELDS if field in fields]
            times = filtered_times([fields[field] for field in ordered_fields], args)
            if not times:
                print(f"Skipping {view}: no common coherent frames")
                continue
            print(
                f"{view}: {len(times)} frames, t={times[0]}..{times[-1]}, "
                f"fields={','.join(ordered_fields)}"
            )
            staged: dict[str, Path] = {}
            for field in ordered_fields:
                destination = staging_root / view / field
                stage_sequence(destination, fields[field], times)
                staged[field] = destination
                if not args.combined_only:
                    jobs += 1
                    output = output_root / field / f"{view}.mp4"
                    print(f"  -> {output}")
                    if not args.dry_run:
                        encode_single(ffmpeg, destination, output, args)
            if not args.single_only:
                jobs += 1
                output = output_root / "main" / f"{view}.mp4"
                print(f"  -> {output}")
                if not args.dry_run:
                    encode_combined(
                        ffmpeg, [staged[field] for field in ordered_fields], output, args
                    )
    print(f"Planned {jobs} video(s) below {output_root}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"ffmpeg failed with exit status {error.returncode}") from error
