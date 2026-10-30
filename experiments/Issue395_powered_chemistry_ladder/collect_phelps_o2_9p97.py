#!/usr/bin/env python3
"""Local-only acquisition of Phelps O2 9.97 LOSS with 10.000 eV loss.

No network fetch; do not publish source PDF or extracted numerical CSV.
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
CHANNEL = "O2 9.97 LOSS TRAJMAR"
SCALE_TO_M2 = 1e-20  # Original tabulated sigma is in units of 1e-16 cm^2.
OUTPUT_CSV = "o2_9p97_loss_sigma.csv"
OUTPUT_MANIFEST = "o2_9p97_loss_provenance.json"
CHANNEL_RE = re.compile(r"(?m)^[ \t]*O2[ \t]+9\.97[ \t]+LOSS[ \t]+TRAJMAR[ \t]*$")
BOUNDARY_RE = re.compile(r"(?m)^[ \t]*O2[ \t]+IONIZATION[ \t]*$")
LOSS_RE = re.compile(r"ENERGY[ \t]+LOSS[ \t]*=[ \t]*10\.000\b")
LIMITS_RE = re.compile(
    r"LOWER[ \t]+LIMIT[ \t]*=[ \t]*9\.778[ \t]*,?[ \t]*"
    r"UPPER[ \t]+LIMIT[ \t]*=[ \t]*100\.001\b"
)
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
            completed = subprocess.run(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
                check=True, capture_output=True, text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise ValueError("pdftotext required for Phelps PDF extraction") from exc
        return completed.stdout
    if path.suffix.lower() != ".txt":
        raise ValueError("Expected a Phelps source PDF or pdftotext TXT")
    return path.read_text(encoding="utf-8")


def parse_o2_9p97_source(text: str) -> list[tuple[float, float]]:
    """Return incident energy [eV] and sigma [m^2], not reaction rate."""
    found = list(CHANNEL_RE.finditer(text))
    if len(found) != 1:
        raise ValueError(f"Require exactly one {CHANNEL} section; got {len(found)}")
    segment = text[found[0].end():]
    following = BOUNDARY_RE.search(segment)
    if following is None:
        raise ValueError("Missing O2 IONIZATION boundary; cannot isolate channel")
    segment = segment[:following.start()]
    if not (LOSS_RE.search(segment) and LIMITS_RE.search(segment) and QSCALE_RE.search(segment)):
        raise ValueError("Source energy loss, limits or QSCALE do not match 9.97 channel")
    header = re.search(r"(?m)^[ \t]*ENERGY[ \t]+CROSS[ \t]+SECTION[ \t]*$", segment)
    if header is None:
        raise ValueError("ENERGY CROSS SECTION header missing")
    points: list[tuple[float, float]] = []
    for line in segment[header.end():].splitlines():
        match = PAIR_RE.fullmatch(line)
        if match is None:
            continue
        index, energy_text, sigma_text = match.groups()
        if int(index) != len(points) + 1:
            raise ValueError("Non-sequential source indices")
        points.append((float(energy_text), float(sigma_text) * SCALE_TO_M2))
    if len(points) != 24:
        raise ValueError(f"Expected 24 source points, got {len(points)}")
    for i, (energy, sigma) in enumerate(points):
        if not math.isfinite(energy) or not math.isfinite(sigma) or energy < 0 or sigma < 0:
            raise ValueError("Invalid/non-finite cross-section or energy")
        if i and energy <= points[i - 1][0]:
            raise ValueError("Electron energies are not strictly increasing")
    if points[:2] != [(0.0, 0.0), (10.0, 0.0)]:
        raise ValueError("Incorrect zero/10-eV anchors")
    if points[2][0] != 20.0 or points[2][1] <= 0:
        raise ValueError("Incorrect first post-threshold positive anchor")
    if points[-6:] != [
        (1500.0, 0.0), (2000.0, 0.0), (3000.0, 0.0),
        (5000.0, 0.0), (7000.0, 0.0), (10000.0, 0.0),
    ]:
        raise ValueError("Incorrect high-energy zero-tail anchors")
    return points


def convert(source: Path, out_dir: Path, retrieved_on: str, *, replace: bool = False) -> dict:
    date = dt.date.fromisoformat(retrieved_on)
    if date > dt.date.today():
        raise ValueError("Source retrieval date is in the future")
    source = source.resolve(strict=True)
    out_dir = out_dir.resolve()
    if out_dir in source.parents:
        raise ValueError("Keep original PDF outside the output directory")
    points = parse_o2_9p97_source(extract_source_text(source))
    output, provenance = out_dir / OUTPUT_CSV, out_dir / OUTPUT_MANIFEST
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
        "reaction_id": 414,
        "registry_issue": 419,
        "source": "Phelps electron collision compilation, Trajmar channel",
        "source_url": SOURCE_URL,
        "source_revision": "2008-06-24 (as printed in source)",
        "source_section": CHANNEL,
        "source_channel_label_eV": 9.97,
        "energy_loss_eV": 10.0,
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
        "interpolation": "linear in incident energy and sigma per Phelps",
        "status": "source_extracted_not_boltzmann_rate_or_chemistry_validation",
        "warning": "Effective O2* channel: do not infer physical products or O atom sources.",
        "redistribution": "Do not republish source or extracted numerical dataset without permission",
    }
    provenance.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--retrieved-on", required=True, help="Actual retrieval date YYYY-MM-DD")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    manifest = convert(args.source, args.output_dir, args.retrieved_on, replace=args.replace)
    print(f"PHELPS_O2_9P97_LOCAL_EXTRACTION_PASS points={manifest['point_count']}")
    print(f"source_sha256={manifest['source_sha256']}")
    print(f"csv_sha256={manifest['csv_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
