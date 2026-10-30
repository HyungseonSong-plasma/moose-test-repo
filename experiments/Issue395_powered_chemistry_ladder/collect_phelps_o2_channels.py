#!/usr/bin/env python3
"""Prepare source-verified O2 collision cross sections for #419, without redistribution.

This tool never downloads or publishes Phelps data. Read a user-obtained
original Phelps PDF or faithful text conversion, extract SIX collision
sections mapped to FIVE reaction IDs, and retain source hash/provenance.
These are cross sections, NOT electron-energy rate tables.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess

SOURCE_URL = "https://us.lxcat.net/notes/index.php?download=phelps5"
SCALE_TO_SI = 1e-20  # Phelps printed values: 1E-16 cm2 = 1E-20 m2
NUM = r"(?:[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)"
PAIR = re.compile(rf"^\s*(\d+)\s+({NUM})\s+({NUM})\s*$")
DOUBLE = re.compile(rf"^\s*({NUM})\s+({NUM})\s*$")
ROWS = "ENERGY CROSS SECTION"


@dataclass(frozen=True)
class Section:
    id: str
    reaction_id: int
    heading: str
    n: int
    loss_eV: float | None
    qscale: float | None
    threshold_eV: float | None
    species_mapping: str
    source_kind: str = "indexed"


SECTIONS = (
    Section("401", 401, "O2 TWO-BODY ATTACHMENT", 20, 0., 1.2, 4.4,
            "attachment_e_plus_O2_to_O_plus_Ominus"),
    Section("407", 407, "O2 SING DELTA FROM LINDER-SCHMIDT AND TRAJMAR ET AL",
            26, .977, 1., .977, "O2_a1Delta_excitation"),
    Section("411", 411, "O2 4.5 LOSS", 16, 4.5, 1., 4.5,
            "energy_loss_only_O2_to_2O3P_not_validated"),
    Section("412_loss", 412, "O2 6.0 LOSS", 12, 6., 1., 6.,
            "energy_loss_only_2O3P_not_proven"),
    Section("412_dissociation", 412, "O2 DISSOCIATION - BASED ON TABLE I OF",
            15, None, None, 8., "Cosby_1993_explicit_dissociation",
            "unindexed"),
    Section("413", 413, "O2 8.4 LOSS HAYASHI ABOVE 20EV - CHANTRY BELOW",
            18, 8.4, 1., 8.4, "O2_effective_excitation_loss"),
)


def source_text(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Source not found: {path}")
    if path.suffix.lower() == ".pdf":
        try:
            p = subprocess.run(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
                check=True, capture_output=True, text=True,
            )
        except (OSError, subprocess.CalledProcessError) as e:
            raise ValueError("PDF extraction requires working pdftotext -layout") from e
        return p.stdout
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8")
    raise ValueError("Only .pdf and faithful .txt Phelps sources are accepted")


def section_data(source: str, spec: Section) -> list[tuple[float, float]]:
    heading = re.compile(rf"(?m)^\s*{re.escape(spec.heading)}\s*$")
    hits = list(heading.finditer(source))
    if len(hits) != 1:
        raise ValueError(f"{spec.id}: expected one exact source heading; found {len(hits)}")
    start = hits[0].end()
    stop = source.find(ROWS, start)
    if stop < 0 or stop - start > 1200:
        raise ValueError(f"{spec.id}: no nearby ENERGY CROSS SECTION heading")
    metadata = source[start:stop]
    if spec.loss_eV is not None:
        loss = re.search(rf"ENERGY\s+LOSS\s*=\s*({NUM})", metadata)
        scale = re.search(rf"QSCALE\s*=\s*({NUM})", metadata)
        if not loss or not scale:
            raise ValueError(f"{spec.id}: loss/QSCALE metadata absent")
        if not math.isclose(float(loss.group(1)), spec.loss_eV, abs_tol=1e-7):
            raise ValueError(f"{spec.id}: different physical loss")
        if not math.isclose(float(scale.group(1)), spec.qscale, abs_tol=1e-7):
            raise ValueError(f"{spec.id}: unexpected source QSCALE")
    else:
        if "P. C. Cosby" not in metadata:
            raise ValueError(f"{spec.id}: missing Cosby dissociation attribution")
    tail = source[stop+len(ROWS):]
    points: list[tuple[float, float]] = []
    started = False
    for line in tail.splitlines():
        # pdftotext may preserve the PDF page footer inside a numeric section.
        if re.fullmatch(r"\s*Page\s+\d+\s+of\s+\d+\s*", line):
            continue
        m = (PAIR if spec.source_kind == "indexed" else DOUBLE).fullmatch(line)
        if m:
            if spec.source_kind == "indexed":
                n, e, sigma = m.groups()
                if int(n) != len(points) + 1:
                    raise ValueError(f"{spec.id}: source indices discontinuous")
            else:
                e, sigma = m.groups()
            points.append((float(e), float(sigma) * SCALE_TO_SI))
            started = True
        elif line.strip() and started:
            # Never let a parser silently incorporate a neighboring collision channel.
            if len(points) < spec.n:
                raise ValueError(f"{spec.id}: truncated section with {len(points)} points")
            break
        elif line.strip() and not started:
            raise ValueError(f"{spec.id}: unexpected text before first datum")
        if len(points) == spec.n:
            break
    if len(points) != spec.n:
        raise ValueError(f"{spec.id}: expected {spec.n} points, got {len(points)}")
    if points[0] != (0.0, 0.0):
        raise ValueError(f"{spec.id}: original zero-energy anchor changed")
    for i, (energy, sigma) in enumerate(points):
        if not all(map(math.isfinite, (energy, sigma))) or energy < 0 or sigma < 0:
            raise ValueError(f"{spec.id}: invalid negative/NaN sample")
        if i and energy <= points[i-1][0]:
            raise ValueError(f"{spec.id}: energy sequence not ascending")
    if spec.threshold_eV is not None:
        if points[1][0] != spec.threshold_eV or points[1][1] != 0.0:
            raise ValueError(f"{spec.id}: original threshold anchor altered")
    # Phelps QSCALE indicates previous input-data rescaling; the tabulated
    # points are already the values used in the Boltzmann calculation.
    return points


def collect(source: Path, out: Path, retrieved_on: str, replace: bool = False) -> dict:
    date = dt.date.fromisoformat(retrieved_on)
    if date > dt.date.today():
        raise ValueError("Future retrieval date not allowed")
    source = source.resolve(strict=True)
    out = out.resolve()
    if source == out or out in source.parents:
        raise ValueError("Keep untouched original separate from extracted output")
    text = source_text(source)
    sections = {spec.id: section_data(text, spec) for spec in SECTIONS}
    files = [out / f"o2_{name}_sigma.csv" for name in sections]
    manifest_path = out / "phelps_o2_channels_provenance.json"
    if not replace and any(p.exists() for p in files + [manifest_path]):
        raise FileExistsError("Output already exists; explicit --replace required")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "registry_issue": 419, "source": "A. V. Phelps O2 compilation",
        "source_url": SOURCE_URL, "source_revision": "2008-06-24",
        "retrieved_on": date.isoformat(), "source_filename": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "input_unit_sigma": "1e-16 cm2", "output_unit_sigma": "m2",
        "sigma_to_m2": SCALE_TO_SI,
        "qscale_convention": "already applied in published tabulated values; do not multiply again",
        "interpolation": "linear energy and cross section as specified by Phelps",
        "status": "raw_cross_sections_only; NO rate tables, EEDF or accepted chemistry",
        "channels": {},
    }
    for spec, path in zip(SECTIONS, files):
        buff = io.StringIO(newline="")
        w = csv.writer(buff, lineterminator="\n")
        w.writerow(("electron_energy_eV", "cross_section_m2"))
        for e, sigma in sections[spec.id]:
            w.writerow((f"{e:.17g}", f"{sigma:.17g}"))
        blob = buff.getvalue().encode("utf-8")
        path.write_bytes(blob)
        manifest["channels"][spec.id] = {
            "reaction_id": spec.reaction_id, "original_heading": spec.heading,
            "energy_loss_eV": spec.loss_eV, "printed_qscale": spec.qscale,
            "sample_count": spec.n, "species_mapping": spec.species_mapping,
            "path": path.name, "sha256": hashlib.sha256(blob).hexdigest(),
            "species_source_accepted": spec.id not in {"411", "412_loss", "413"},
            "boltzmann_rate_computed": False,
        }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--retrieved-on", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    r = collect(args.source, args.output_dir, args.retrieved_on, args.replace)
    print("PHELPS_O2_MULTI_CHANNEL_ACQUISITION_PASS")
    for name, channel in r["channels"].items():
        print(f"{name}: {channel['sample_count']} rows -> {channel['path']}")
    print(f"source_sha256={r['source_sha256']}")


if __name__ == "__main__":
    main()
