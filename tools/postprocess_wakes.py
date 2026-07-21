#!/usr/bin/env python3
"""Summarise centreline wake probes over the configured statistics window."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

from case_config import DEFAULT_CONFIG, ROOT, load_config, turbine_positions

NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[Ee][-+]?\d+)?")


def probe_labels(cfg: dict) -> list[dict]:
    diameter = float(cfg["turbine"]["diameter"])
    xmax = float(cfg["domain_D"]["x"][1]) * diameter
    labels = []
    for turbine in turbine_positions(cfg):
        for downstream in (1, 2, 4, 6, 8):
            if float(turbine["x"]) + downstream * diameter < xmax:
                labels.append(
                    {
                        "turbine": turbine["name"],
                        "downstream_D": downstream,
                    }
                )
    return labels


def find_probe_file(case: Path) -> Path:
    candidates = sorted(
        (case / "postProcessing" / "wakeCentrelineProbes").glob("*/U"),
        key=lambda path: float(path.parent.name),
    )
    if not candidates:
        raise FileNotFoundError("no wakeCentrelineProbes/*/U file found")
    return candidates[-1]


def read_probe_file(path: Path, n_probes: int) -> tuple[np.ndarray, np.ndarray]:
    times = []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        numbers = [float(value) for value in NUMBER.findall(line)]
        if len(numbers) != 1 + 3 * n_probes:
            continue
        times.append(numbers[0])
        rows.append(np.asarray(numbers[1:]).reshape(n_probes, 3))
    if not rows:
        raise ValueError(f"no valid samples in {path}")
    return np.asarray(times), np.asarray(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--case", type=Path, default=ROOT / "case")
    parser.add_argument("--output", type=Path, default=ROOT / "case" / "wake_summary.csv")
    args = parser.parse_args()

    cfg = load_config(args.config)
    labels = probe_labels(cfg)
    path = find_probe_file(args.case)
    times, velocity = read_probe_file(path, len(labels))
    mask = times >= float(cfg["run"]["statistics_start"])
    if mask.sum() < 10:
        raise ValueError("fewer than 10 samples in the statistics window")
    samples = velocity[mask]
    uref = float(cfg["abl"]["hub_velocity"])
    records = []
    for index, label in enumerate(labels):
        mean = samples[:, index, :].mean(axis=0)
        std = samples[:, index, :].std(axis=0, ddof=1)
        records.append(
            {
                **label,
                "mean_Ux": mean[0],
                "mean_Uy": mean[1],
                "mean_Uz": mean[2],
                "deficit": 1.0 - mean[0] / uref,
                "TIx": std[0] / max(abs(mean[0]), 1e-12),
                "sample_count": int(mask.sum()),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    metadata = {
        "source": str(path),
        "statistics_start": float(cfg["run"]["statistics_start"]),
        "statistics_end": float(times[mask][-1]),
        "records": len(records),
    }
    args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)

