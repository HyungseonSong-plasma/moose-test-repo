#!/usr/bin/env python3
"""Locally extract Phelps O2 4.5-eV LOSS cross sections for later Boltzmann work.

No network fetch; do not redistribute either downloaded source or extracted CSV.
Source: https://us.lxcat.net/notes/index.php?download=phelps5
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess

SOURCE_URL = "https://us.lxcat.net/notes/index.php?download=phelps5"
CHANNEL = "O2 4.5 LOSS"
SCALE_TO_M2 = 1e-20  # Phelps: 1e-16 cm2 = 1e-20 m2.
OUTPUT_CSV = "o2_4p5_loss_sigma.csv"
OUTPUT_MANIFEST = "o2_4p5_loss_provenance.json"
CHANNEL_RE = re.compile(r"(?m)^[ \t]*O2[ \t]+4\.5[ \t]+LOSS[ \t]*$")
LOSS_RE = re.compile(r"ENERGY[ \t]+LOSS[ \t]*=[ \t]*4\.500\b")
QSCALE_RE = re.compile(r"QSCALE[ \t]*=[ \t]*1\.000000\b")
PAIR_RE = re.compile(
    r"^[ \t]*(\d+)[ \t]+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)"
    r"[ \t]+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)[ \t]*$"
)


def extract_source_text(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Source file missing: {path}")
    if path.suffix.lower() == ".pdf":
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
                check=True, capture_output=True, text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise ValueError("pdftotext required for Phelps PDF extraction") from exc
        return result.stdout
    if path.suffix.lower() != ".txt":
        raise ValueError("Expected a Phelps source PDF or pdftotext TXT")
    return path.read_text(encoding="utf-8")


def parse_o2_4p5_source(text: str) -> list[tuple[float, float]]:
    """Return (electron energy [eV], sigma [m2]); no O(3P) branching implied."""
    found = list(CHANNEL_RE.finditer(text))
    if len(found) != 1:
        raise ValueError(f"Require exactly one {CHANNEL} section; got {len(found)}")
    segment = text[found[0].end():]
    following = re.search(r"(?m)^[ \t]*O2[ \t]+6\.0[ \t]+LOSS[ \t]*$", segment)
    if following is None:
        raise ValueError("Missing O2 6.0 LOSS boundary; cannot isolate 4.5 channel")
    segment = segment[:following.start()]
    if not LOSS_RE.search(segment) or not QSCALE_RE.search(segment):
        raise ValueError("Incorrect loss energy or QSCALE in source")
    if not re.search(r"(?m)^[ \t]*ENERGY[ \t]+CROSS[ \t]+SECTION[ \t]*$", segment):
        raise ValueError("ENERGY CROSS SECTION header missing")
    points: list[tuple[float, float]] = []
    for line in segment.splitlines():
        match = PAIR_RE.fullmatch(line)
        if not match:
            continue
        i, energy, sigma = match.groups()
        if int(i) != len(points) + 1:
            raise ValueError("Non-sequential source indices")
        points.append((float(energy), float(sigma) * SCALE_TO_M2))
    if len(points) != 16:
        raise ValueError(f"Expected 16 source points, got {len(points)}")
    for i, (energy, sigma) in enumerate(points):
        if not math.isfinite(energy) or not math.isfinite(sigma) or energy < 0 or sigma < 0:
            raise ValueError("Invalid/non-finite cross-section or energy")
        if i and energy <= points[i - 1][0]:
            raise ValueError("Electron energies are not strictly ascending")
    if points[:2] != [(0.0, 0.0), (4.5, 0.0)]:
        raise ValueError("Incorrect zero/threshold anchors")
    if points[2][0] != 4.8 or points[2][1] <= 0:
        raise ValueError("Incorrect first positive post-threshold point")
    if points[-3:] != [(15.0, 0.0), (50.0, 0.0), (10000.0, 0.0)]:
        raise ValueError("Original high-energy zero-tail anchors changed")
    return points


def convert(source: Path, out_dir: Path, retrieved_on: str, *, replace: bool = False) -> dict:
    date = dt.date.fromisoformat(retrieved_on)
    if date > dt.date.today():
        raise ValueError("Source retrieval date is in the future")
    source = source.resolve(strict=True)
    out_dir = out_dir.resolve()
    if out_dir in source.parents:
        raise ValueError("Keep the original PDF outside the output directory")
    points = parse_o2_4p5_source(extract_source_text(source))
    output = out_dir / OUTPUT_CSV
    provenance = out_dir / OUTPUT_MANIFEST
    if not replace and (output.exists() or provenance.exists()):
        raise FileExistsError("Outputs already exist; use --replace explicitly")
    out_dir.mkdir(parents=True, exist_ok=True)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("electron_energy_eV", "cross_section_m2"))
    for energy, sigma in points:
        writer.writerow((f"{energy:.17g}", f"{sigma:.17g}"))
    csv_bytes = stream.getvalue().encode("utf-8")
    output.write_bytes(csv_bytes)
    manifest = {
        "reaction_id": 411,
        "registry_issue": 419,
        "source": "Phelps electron collision compilation",
        "source_url": SOURCE_URL,
        "source_section": CHANNEL,
        "source_revision": "2008-06-24 (as printed in the source)",
        "retrieved_on": date.isoformat(),
        "source_file": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "csv_file": OUTPUT_CSV,
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "point_count": len(points),
        "energy_unit": "eV",
        "source_sigma_unit": "1e-16 cm^2",
        "output_sigma_unit": "m^2",
        "sigma_scale_to_m2": SCALE_TO_M2,
        "energy_loss_eV": 4.5,
        "interpolation": "linear in incident energy and sigma per Phelps",
        "status": "source_energy_loss_only_not_validated_for_2O3P_production",
        "warning": "Do not infer O(3P) atom branching or activate species sources.",
        "redistribution": "Source/converted dataset must not be published without permission",
    }
    provenance.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--retrieved-on", required=True, help="Actual retrieval YYYY-MM-DD")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    manifest = convert(args.source, args.output_dir, args.retrieved_on, replace=args.replace)
    print(f"PHELPS_O2_4P5_LOCAL_EXTRACTION_PASS points={manifest['point_count']}")
    print(f"source_sha256={manifest['source_sha256']}")
    print(f"csv_sha256={manifest['csv_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
