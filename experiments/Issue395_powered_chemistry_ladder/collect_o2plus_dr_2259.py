#!/usr/bin/env python3
"""Reaction 2259: prepare author-supplied O2+ dissociative-recombination cross sections.

Source: Peverall et al., J. Chem. Phys. 114, 6679-6689 (2001),
DOI 10.1063/1.1349079. The experiment covers 1 meV to 3 eV electron-ion
collision energy; this program NEVER invents points or downloads a dataset.
Only ingest a locally obtained, source-matched digitization/author data file.

Input CSV: collision_energy_eV,cross_section_cm2
Output CSV: collision_energy_eV,cross_section_m2
Input must be the *total dissociative recombination* cross section of
O2+(X 2Pi_g, v=0) + e, not electron-impact ionization of O2/O2+,
dissociative excitation, or a product-branch-specific partial cross section.
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

DOI = "10.1063/1.1349079"
SOURCE_URL = "https://doi.org/" + DOI
SOURCE_TYPE = "measured_absolute_dissociative_recombination"
ION_STATE = "O2+(X2Pi_g,v=0)"
SCALE_CM2_TO_M2 = 1e-4
OUTPUT_CSV = "o2plus_dr_2259_sigma.csv"
OUTPUT_MANIFEST = "o2plus_dr_2259_provenance.json"
EXPECTED_HEADERS = ["collision_energy_eV", "cross_section_cm2"]


def parse_author_data(content: str) -> list[tuple[float, float]]:
    """Input is original source-linked energy/sigma data, never a formula substitute."""
    reader = csv.DictReader(io.StringIO(content, newline=""))
    if reader.fieldnames != EXPECTED_HEADERS:
        raise ValueError(f"Require exact input CSV headers: {EXPECTED_HEADERS}")
    rows: list[tuple[float, float]] = []
    for raw in reader:
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError("Malformed or incomplete source row")
        try:
            energy = float(raw["collision_energy_eV"])
            sigma_cm2 = float(raw["cross_section_cm2"])
        except (TypeError, ValueError) as e:
            raise ValueError("Cross-section points must be numeric") from e
        if not math.isfinite(energy) or energy <= 0:
            raise ValueError("DR collision energies must be positive finite eV, no 0-eV anchor")
        if not math.isfinite(sigma_cm2) or sigma_cm2 <= 0:
            raise ValueError("DR cross sections must be positive finite cm2")
        if rows and energy <= rows[-1][0]:
            raise ValueError("DR collision energies must strictly increase")
        rows.append((energy, sigma_cm2 * SCALE_CM2_TO_M2))
    if len(rows) < 8:
        raise ValueError("Need at least eight independently sourced numeric points")
    if rows[0][0] > .005 or rows[-1][0] < 2.0:
        raise ValueError("Source data must include low/high energy coverage approaching 0.001-3 eV")
    return rows


def prepare(source: Path, output_dir: Path, retrieved_on: str, *, replace: bool = False) -> dict:
    date = dt.date.fromisoformat(retrieved_on)
    if date > dt.date.today():
        raise ValueError("Future retrieval date is not allowed")
    source = source.resolve(strict=True)
    output_dir = output_dir.resolve()
    if source.suffix.lower() != ".csv":
        raise ValueError("Use a locally obtained, source-matched .csv digitization")
    if source == output_dir or output_dir in source.parents:
        raise ValueError("Keep original source outside generated output")
    source_bytes = source.read_bytes()
    points = parse_author_data(source_bytes.decode("utf-8-sig"))
    csv_out = output_dir / OUTPUT_CSV
    manifest_out = output_dir / OUTPUT_MANIFEST
    if not replace and (csv_out.exists() or manifest_out.exists()):
        raise FileExistsError("Existing outputs: explicit --replace required")
    output_dir.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(("collision_energy_eV", "cross_section_m2"))
    for energy, sigma_m2 in points:
        writer.writerow((f"{energy:.17g}", f"{sigma_m2:.17g}"))
    output_bytes = buf.getvalue().encode("utf-8")
    csv_out.write_bytes(output_bytes)
    manifest = {
        "reaction_id": 2259,
        "registry_issue": 419,
        "process": "e + O2+ -> O + O",
        "process_kind": SOURCE_TYPE,
        "initial_ion_state": ION_STATE,
        "source_doi": DOI,
        "source_url": SOURCE_URL,
        "source_citation": "Peverall et al., J. Chem. Phys. 114, 6679-6689 (2001)",
        "source_data_type": "user-provided original/digitized numeric data; unverified by code",
        "retrieved_on": date.isoformat(),
        "source_filename": source.name,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "input_energy_unit": "eV center-of-mass electron-ion collision energy",
        "input_cross_section_unit": "cm2",
        "cross_section_to_m2": SCALE_CM2_TO_M2,
        "output_energy_unit": "eV",
        "output_cross_section_unit": "m2",
        "output_filename": OUTPUT_CSV,
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "point_count": len(points),
        "measured_range_eV": [0.001, 3.0],
        "coverage_available_eV": [points[0][0], points[-1][0]],
        "interpolation_recommendation": "log-log, only between measured positive pairs; never extrapolate",
        "reaction_rate_table_created": False,
        "species_branching_verified": False,
        "electron_energy_loss_eV": None,
        "physics_runtime_activated": False,
        "warning": "Do not assume both products O(3P), fixed electron energy loss, or neutral-target Phelps cross sections.",
    }
    manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    return manifest


def benchmark_k(te_kelvin: float) -> float:
    """Peverall's thermal rate comparison only; NOT an xsec generator."""
    if not math.isfinite(te_kelvin) or te_kelvin <= 200.0:
        raise ValueError("Peverall thermal benchmark is only stated for Te > 200 K")
    return 2.4e-13 * (300.0 / te_kelvin)**0.70


def compare_boltzmann_rates(records: list[dict[str, str]]) -> list[dict]:
    """Compare user-produced thermal k(Te) to Peverall benchmark (not scientific acceptance)."""
    out = []
    seen = set()
    for row in records:
        if set(row) != {"Te_K", "k_lookup_m3_s"}:
            raise ValueError("Required columns: Te_K,k_lookup_m3_s")
        try:
            te, k = float(row["Te_K"]), float(row["k_lookup_m3_s"])
        except (ValueError, TypeError) as exc:
            raise ValueError("Non-numeric thermal rate") from exc
        ref = benchmark_k(te)
        if not math.isfinite(k) or k < 0:
            raise ValueError("Lookup rate must be finite and nonnegative")
        if te in seen:
            raise ValueError("Duplicate Te point")
        seen.add(te)
        out.append({"Te_K": te, "k_lookup_m3_s": k, "k_reference_m3_s": ref,
                    "relative_deviation": (k - ref)/ref,
                    "acceptance": "numerical comparison only"})
    if not out:
        raise ValueError("No Boltzmann lookup rates to compare")
    return sorted(out, key=lambda item: item["Te_K"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract", help="Prepare authorized original cross section CSV locally")
    extract.add_argument("--source-csv", type=Path, required=True)
    extract.add_argument("--output-dir", type=Path, required=True)
    extract.add_argument("--retrieved-on", required=True)
    extract.add_argument("--replace", action="store_true")
    benchmark = sub.add_parser("compare", help="Compare *future* lookup against thermal formula")
    benchmark.add_argument("--boltzmann-rates-csv", type=Path, required=True)
    benchmark.add_argument("--report-json", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "extract":
        result = prepare(args.source_csv, args.output_dir, args.retrieved_on,
                         replace=args.replace)
        print("O2PLUS_DR_2259_SOURCE_PREPARATION_PASS_NOT_PHYSICS_ACCEPTANCE")
        print(f"source_sha256={result['source_sha256']} points={result['point_count']}")
    else:
        with args.boltzmann_rates_csv.open(newline="", encoding="utf-8") as stream:
            result = compare_boltzmann_rates(list(csv.DictReader(stream)))
        args.report_json.write_text(json.dumps({
            "status": "REFERENCE_COMPARISON_ONLY",
            "source_doi": DOI,
            "not_chemistry_or_runtime_acceptance": True,
            "points": result,
        }, indent=2)+"\n", encoding="utf-8")
        print("O2PLUS_DR_2259_BENCHMARK_COMPARISON_COMPLETE_NOT_SCIENTIFIC_PASS")


if __name__ == "__main__":
    main()
