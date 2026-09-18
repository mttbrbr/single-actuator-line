#!/usr/bin/env python3
"""Export final Pope-resolution and native IDDES-region maps from wake planes."""

from __future__ import annotations

import base64
import math
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIME = "57.5"
SOURCE = ROOT / "case/postProcessing/wakePlanes" / TIME
OUT = ROOT / "artifacts"

D = 10.058
HUB = 12.192
NX, NZ = 52, 34
YMIN, YMAX = -1.5, 1.5
ZMIN, ZMAX = -0.75, 0.75
PLANES = ("1D", "2D", "4D", "6D", "8D")

POPE_COLORS = ("#440154", "#3b528b", "#21918c", "#5ec962", "#bddf26", "#fde725")
REGION_COLORS = ("#d95f59", "#e8d7b7", "#277da1")


def values(element: ET.Element) -> tuple[float, ...]:
    raw = base64.b64decode("".join((element.text or "").split()))
    count = struct.unpack_from("<Q", raw)[0] // 4
    return struct.unpack_from(f"<{count}f", raw, 8)


def arrays(path: Path) -> tuple[tuple[float, ...], dict[str, tuple[float, ...]]]:
    root = ET.parse(path).getroot()
    points = values(root.find(".//Points/DataArray"))
    data = {}
    for name in ("k", "UPrime2Mean", "LESRegion"):
        element = root.find(f".//PointData/DataArray[@Name='{name}']")
        if element is None:
            raise RuntimeError(f"{name} assente in {path}")
        data[name] = values(element)
    return points, data


def binned(path: Path) -> tuple[list[float | None], list[float | None], dict[str, float]]:
    points, data = arrays(path)
    pope_sums = [0.0] * (NX * NZ)
    region_sums = [0.0] * (NX * NZ)
    counts = [0] * (NX * NZ)
    raw_pope: list[float] = []
    raw_region: list[float] = []
    k, uu, region = data["k"], data["UPrime2Mean"], data["LESRegion"]
    for i, modelled in enumerate(k):
        y = points[3 * i + 1] / D
        z = (points[3 * i + 2] - HUB) / D
        if not (YMIN <= y <= YMAX and ZMIN <= z <= ZMAX):
            continue
        resolved = max(0.0, 0.5 * (uu[6*i] + uu[6*i+3] + uu[6*i+5]))
        fraction = resolved / (resolved + max(0.0, modelled) + 1e-30)
        mode = min(1.0, max(0.0, region[i]))
        iy = min(NX - 1, int((y - YMIN) / (YMAX - YMIN) * NX))
        iz = min(NZ - 1, int((z - ZMIN) / (ZMAX - ZMIN) * NZ))
        index = iz * NX + iy
        pope_sums[index] += fraction
        region_sums[index] += mode
        counts[index] += 1
        raw_pope.append(fraction)
        raw_region.append(mode)
    pope = [s / n if n else None for s, n in zip(pope_sums, counts)]
    regions = [s / n if n else None for s, n in zip(region_sums, counts)]
    stats = {
        "pope_mean": sum(raw_pope) / len(raw_pope),
        "pope_80": sum(v >= 0.8 for v in raw_pope) / len(raw_pope),
        "les": sum(raw_region) / len(raw_region),
    }
    return pope, regions, stats


def pope_color(value: float) -> str:
    for index, limit in enumerate((0.1, 0.2, 0.4, 0.6, 0.8)):
        if value < limit:
            return POPE_COLORS[index]
    return POPE_COLORS[-1]


def region_color(value: float) -> str:
    if value < 0.25:
        return REGION_COLORS[0]
    if value < 0.75:
        return REGION_COLORS[1]
    return REGION_COLORS[2]


def svg_document(kind: str, panels: list[tuple[str, list[float | None], dict[str, float]]]) -> str:
    pope = kind == "pope"
    title = ("Frazione di energia turbolenta risolta" if pope else
             "Regione attiva del modello IDDES") + f" — t = {TIME} s"
    subtitle = ("kᵣ = ½ tr(U′U′); quota risolta = kᵣ/(kᵣ+k modellata)" if pope else
                "LESRegion nativo di OpenFOAM: 0 = RANS, 1 = LES; valori intermedi = celle di transizione")
    colors = POPE_COLORS if pope else REGION_COLORS
    labels = (("&lt;10%", "10–20%", "20–40%", "40–60%", "60–80%", "≥80%") if pope else
              ("RANS (&lt;0.25)", "Transizione", "LES (≥0.75)"))
    page_w, page_h = 1500, 930
    plot_x, plot_y, plot_w, plot_h = 66, 48, 370, 240
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{page_w}" height="{page_h}" viewBox="0 0 {page_w} {page_h}">
<rect width="100%" height="100%" fill="#ffffff"/>
<style>text{{font-family:DejaVu Sans,Arial,sans-serif;fill:#172033}} .title{{font-size:26px;font-weight:700}} .subtitle{{font-size:15px}} .panel-title{{font-size:18px;font-weight:700}} .stat{{font-size:14px;font-weight:600}} .tick{{font-size:13px}} .axis{{font-size:15px}} .frame{{fill:none;stroke:#657083;stroke-width:1.2}} .rotor{{stroke:#111827;stroke-width:3;stroke-dasharray:8 6}}</style>
<text class="title" x="40" y="38">{title}</text>
<text class="subtitle" x="40" y="64">{subtitle}</text>''']
    spacing = 205 if pope else 280
    for i, (label, fill) in enumerate(zip(labels, colors)):
        x = 50 + i * spacing
        parts.append(f'<rect x="{x}" y="82" width="30" height="17" fill="{fill}"/><text class="tick" x="{x+38}" y="96">{label}</text>')
    for index, (name, cells, stats) in enumerate(panels):
        ox = 30 + (index % 3) * 490
        oy = 120 + (index // 3) * 375
        statistic = (f"media {stats['pope_mean']:.0%}  ·  area ≥80% {stats['pope_80']:.0%}" if pope else
                     f"quota LES sul piano {stats['les']:.0%}")
        parts.append(f'<g transform="translate({ox} {oy})"><text class="panel-title" x="{plot_x}" y="22">{name} a valle</text><text class="stat" x="{plot_x}" y="42">{statistic}</text>')
        for iz in range(NZ):
            for iy in range(NX):
                value = cells[iz * NX + iy]
                if value is None or not math.isfinite(value):
                    continue
                x = plot_x + iy * plot_w / NX
                y = plot_y + (NZ - iz - 1) * plot_h / NZ
                fill = pope_color(value) if pope else region_color(value)
                parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{plot_w/NX+0.25:.2f}" height="{plot_h/NZ+0.25:.2f}" fill="{fill}"/>')
        parts.append(f'''<rect class="frame" x="{plot_x}" y="{plot_y}" width="{plot_w}" height="{plot_h}"/>
<line class="rotor" x1="{plot_x+plot_w/2}" x2="{plot_x+plot_w/2}" y1="{plot_y+plot_h/6}" y2="{plot_y+5*plot_h/6}"/>
<text class="tick" x="{plot_x}" y="{plot_y+plot_h+20}" text-anchor="middle">−1.5</text><text class="tick" x="{plot_x+plot_w/2}" y="{plot_y+plot_h+20}" text-anchor="middle">0</text><text class="tick" x="{plot_x+plot_w}" y="{plot_y+plot_h+20}" text-anchor="middle">1.5</text>
<text class="axis" x="{plot_x+plot_w/2}" y="{plot_y+plot_h+43}" text-anchor="middle">y / D</text>
<text class="tick" x="{plot_x-9}" y="{plot_y+5}" text-anchor="end">+0.75</text><text class="tick" x="{plot_x-9}" y="{plot_y+plot_h/2+5}" text-anchor="end">0</text><text class="tick" x="{plot_x-9}" y="{plot_y+plot_h+5}" text-anchor="end">−0.75</text>
<text class="axis" transform="translate(15 {plot_y+plot_h/2}) rotate(-90)" text-anchor="middle">(z−H) / D</text></g>''')
    footer = ("Statistiche temporali accumulate nella simulazione fino a t = 57.5 s; linea tratteggiata: diametro del rotore." if pope else
              "Diagnostica istantanea del modello ibrido. La quota globale volumetrica LES a t = 57.5 s è 37.74%.")
    parts.append(f'<text class="subtitle" x="40" y="900">{footer}</text></svg>')
    return "".join(parts)


def main() -> None:
    if not SOURCE.is_dir():
        raise SystemExit(f"Directory assente: {SOURCE}")
    results = []
    for name in PLANES:
        pope, regions, stats = binned(SOURCE / f"T1_{name}.vtp")
        results.append((name, pope, regions, stats))
        print(f"{name}: TKE risolta media={stats['pope_mean']:.2%}, area >=80%={stats['pope_80']:.2%}, LESRegion media={stats['les']:.2%}")
    OUT.mkdir(parents=True, exist_ok=True)
    pope_panels = [(n, p, s) for n, p, _, s in results]
    region_panels = [(n, r, s) for n, _, r, s in results]
    (OUT / "pope-resolution-t57.5.svg").write_text(svg_document("pope", pope_panels))
    (OUT / "iddes-les-region-t57.5.svg").write_text(svg_document("region", region_panels))


if __name__ == "__main__":
    main()
