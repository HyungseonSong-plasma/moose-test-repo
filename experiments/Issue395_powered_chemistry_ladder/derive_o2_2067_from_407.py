#!/usr/bin/env python3
"""Locally derive O2(a1Delta_g) 2067 superelastic sigma from validated 407 sigma.

No original cross-section numeric values are bundled or published. This model
requires an independently sourced 407 electron-energy/cross-section CSV.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path

DELTA_EV = 0.977
DEGENERACY_RATIO = 3.0 / 2.0
HEADERS = ("electron_energy_eV", "cross_section_m2")


def read_407(path: Path) -> list[tuple[float, float]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(HEADERS):
            raise ValueError(f"Expected CSV columns {HEADERS}")
        rows = [(float(r[HEADERS[0]]), float(r[HEADERS[1]])) for r in reader]
    if len(rows) != 26:
        raise ValueError("Phelps O2 SING DELTA is expected to contain 26 points")
    if rows[0] != (0.0, 0.0) or not math.isclose(rows[1][0], DELTA_EV, abs_tol=1e-7) or rows[1][1] != 0.0:
        raise ValueError("407 zero-energy and 0.977-eV threshold anchors must match original")
    for i, (energy, sigma) in enumerate(rows):
        if not math.isfinite(energy) or not math.isfinite(sigma) or energy < 0 or sigma < 0:
            raise ValueError("Invalid/nonfinite forward cross-section data")
        if i and energy <= rows[i - 1][0]:
            raise ValueError("Electron energies must increase strictly")
    return rows


def detailed_balance_inverse(rows: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return positive-energy reverse grid and an explicit interpolant-based E=0 limit.

    For E=0, use the first above-threshold LINEAR segment of the forward
    cross-section. The limit is an interpolation convention, not measurement.
    """
    if len(rows) < 3:
        raise ValueError("Need at least three forward points")
    threshold, next_point = rows[1], rows[2]
    if not math.isclose(threshold[0], DELTA_EV, abs_tol=1e-7) or threshold[1] != 0.:
        raise ValueError("Incorrect 407 threshold pair")
    slope = next_point[1] / (next_point[0] - threshold[0])
    result = [(0.0, DEGENERACY_RATIO * DELTA_EV * slope)]
    for en, sigma in rows[2:]:
        reverse_energy = en - DELTA_EV
        if reverse_energy <= 0:
            raise ValueError("Above-threshold forward energies must exceed DELTA_EV")
        inverse_sigma = DEGENERACY_RATIO * en / reverse_energy * sigma
        if not math.isfinite(inverse_sigma) or inverse_sigma < 0:
            raise ValueError("Invalid inverse sigma")
        result.append((reverse_energy, inverse_sigma))
    return result


def emit_local(source: Path, output: Path, manifest: Path) -> dict:
    source = source.resolve(strict=True)
    output = output.resolve()
    manifest = manifest.resolve()
    if len({source, output, manifest}) != 3:
        raise ValueError("Source, output and manifest must be separate paths")
    if output.exists() or manifest.exists():
        raise FileExistsError("Output already exists; no silent overwrite")
    rows = detailed_balance_inverse(read_407(source))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADERS)
    for energy, sigma in rows:
        writer.writerow([f"{energy:.17g}", f"{sigma:.17g}"])
    raw = buffer.getvalue().encode("utf-8")
    meta = {
        "reaction_id": 2067,
        "parent_reaction_id": 407,
        "status": "DERIVED_CROSS_SECTION_ONLY_NO_BOLTZMANN_RATE_OR_RUNTIME_ACCEPTANCE",
        "energy_gain_eV": DELTA_EV,
        "forward_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "derived_sha256": hashlib.sha256(raw).hexdigest(),
        "source_npoints": 26,
        "derived_npoints": len(rows),
        "units": {"energy": "eV", "cross_section": "m2"},
        "method": "detailed_balance_inverse_407_gX_3_ga_2",
        "zero_energy_note": "linear-interpolant limiting value; not a measured point",
        "formula_benchmark": "2.06e-15*exp(-1.163/Te) m3/s, Maxwellian only, Kim 2006",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    manifest.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-407", type=Path, required=True)
    p.add_argument("--output-2067", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    opts = p.parse_args()
    meta = emit_local(opts.source_407, opts.output_2067, opts.manifest)
    print(f"O2_2067_DERIVED_SIGMA_READY_NOT_RATE n={meta['derived_npoints']}")


if __name__ == "__main__":
    main()
