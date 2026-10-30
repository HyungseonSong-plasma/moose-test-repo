#!/usr/bin/env python3
"""Prepare model-derived O2(a1Delta_g) sigma(E) for reactions 2072-2074.

Input sigma(E) must come from an independently obtained, source-matched
GROUND-STATE cross section with SHA-256 provenance. The shift by the O2*
internal-state energy (0.977 eV) is the *assumption* in Kim (2006), NOT
a measurement of excited-state cross sections. This script does not download
or synthesize physical cross-section magnitudes or solve the Boltzmann equation.

The optional comparator compares future independently computed rates with
Kim (2006) Maxwellian references; 2074 is *derived*, not independently fitted.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path

STATE_ENERGY_EV = 0.977
ELECTRON_TEMPERATURE_EV_RANGE = (1.0, 7.0)
KIM_SOURCE_URL = "https://www2.eecs.berkeley.edu/Pubs/TechRpts/2006/Archive/EECS-2006-56.pdf"
KIM_SOURCE = "Sungjin Kim (2006), UCB/EECS-2006-56, Table 2.1, Appendix A"
OUTPUT_SCHEMA = ("electron_energy_eV", "cross_section_m2")
RATE_SCHEMA = ("reaction_id", "Te_eV", "k_lookup_m3_s")


@dataclass(frozen=True)
class Reaction:
    id: int
    parent_id: int
    parent_channel: str
    parent_process: str
    label: str
    modeled_loss_eV: float

REACTIONS = {
    2072: Reaction(2072, 415, "415", "e+O2(X)->O2+ + 2e",
                   "ionization_O2s_to_O2plus", 12.06-STATE_ENERGY_EV),
    2073: Reaction(2073, 412, "412_dissociation", "e+O2(X)->O(3P)+O(3P)+e",
                   "dissociation_O2s_to_2O", 6.0-STATE_ENERGY_EV),
    2074: Reaction(2074, 417, "417_Oplus_partial", "e+O2(X)->Oplus+O(3P)+2e",
                   "dissociative_ionization_O2s_to_Oplus", 20.0-STATE_ENERGY_EV),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_ground_sigma(text: str) -> list[tuple[float, float]]:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != list(OUTPUT_SCHEMA):
        raise ValueError(f"Input must have exact columns {OUTPUT_SCHEMA}")
    points: list[tuple[float, float]] = []
    for row in reader:
        if set(row) != set(OUTPUT_SCHEMA) or any(v is None for v in row.values()):
            raise ValueError("Malformed collision-source row")
        try:
            e, sigma = float(row["electron_energy_eV"]), float(row["cross_section_m2"])
        except (ValueError, TypeError) as exc:
            raise ValueError("Non-numeric source collision point") from exc
        if not all(map(math.isfinite, (e, sigma))) or e < 0.0 or sigma < 0.0:
            raise ValueError("Nonfinite or negative cross section/energy")
        if points and e <= points[-1][0]:
            raise ValueError("Electron energies are not strictly increasing")
        points.append((e, sigma))
    if len(points) < 8 or not any(x[1] > 0 for x in points):
        raise ValueError("Insufficient independently sourced collision points")
    return points


def check_parent_provenance(rid: int, source_csv: Path, meta: dict) -> dict:
    """Fail closed on total/partial or parent ground-state cross-section confusion."""
    spec = REACTIONS[rid]
    hash_ = _sha(source_csv)
    if rid in (2072, 2073):
        if meta.get("source") != "A. V. Phelps O2 compilation":
            raise ValueError("Only the original Phelps source accepted for 2072/2073")
        if not isinstance(meta.get("source_sha256"), str) or len(meta["source_sha256"]) != 64:
            raise ValueError("Original Phelps source file SHA-256 absent")
        channel = meta.get("channels", {}).get(spec.parent_channel)
        if not isinstance(channel, dict):
            raise ValueError(f"Exact parent source channel {spec.parent_channel} missing")
        if channel.get("reaction_id") != spec.parent_id:
            raise ValueError("Parent reaction ID does not match")
        if channel.get("path") != source_csv.name or channel.get("sha256") != hash_:
            raise ValueError("Parent data filename/hash mismatch")
        heading = "O2 IONIZATION" if rid == 2072 else "O2 DISSOCIATION - BASED ON TABLE I OF"
        if channel.get("original_heading") != heading:
            raise ValueError("Wrong source reaction (Phelps loss vs physical dissociation)")
        if rid == 2073 and channel.get("species_source_accepted") is not True:
            raise ValueError("Cannot use an energy-loss-only channel for dissociation")
        return {"source_url": meta.get("source_url"), "original_sha256": meta["source_sha256"],
                "source_channel": heading, "source_kind": "source_measured_ground_state"}
    if meta.get("reaction_id") != 417:
        raise ValueError("2074 requires ground-state O+ partial-ionization reaction 417")
    if meta.get("parent_channel") != "Oplus_fragment_partial":
        raise ValueError("2074 cannot use total ionization or O2+ parent ionization")
    if meta.get("original_target_state") != "O2(X3Sigma_g-,v=0)":
        raise ValueError("Original 417 cross section must be ground-state O2")
    if meta.get("original_source_doi") != "10.1016/0168-1176(92)87037-F":
        raise ValueError("Wrong O+ partial cross-section experimental source")
    if meta.get("original_source_sha256") is None or len(meta["original_source_sha256"]) != 64:
        raise ValueError("Original experimental source identity not pinned")
    if meta.get("csv_sha256") != hash_:
        raise ValueError("417 numerical partial-ionization file has wrong SHA-256")
    return {"source_doi": meta["original_source_doi"],
            "original_sha256": meta["original_source_sha256"],
            "source_channel": meta["parent_channel"],
            "source_kind": "Oplus_partial_ground_state"}


def threshold_reduce(points: list[tuple[float, float]], shift_eV: float = STATE_ENERGY_EV
                     ) -> tuple[list[tuple[float, float]], int]:
    """Shift the energy axis; never scale sigma values or extrapolate.

    Discard only exactly zero-sigma points below the new 0-eV origin.
    Positive source sigma at or below the shift is not allowed.
    """
    if shift_eV != STATE_ENERGY_EV:
        raise ValueError("Only 0.977 eV O2(a1Delta_g) initial-state shift supported")
    result: list[tuple[float, float]] = []
    dropped = 0
    for e, sigma in points:
        shifted = e - shift_eV
        if shifted <= 0:
            if sigma != 0:
                raise ValueError("Source cross section positive at/below energy shift")
            dropped += 1
            continue
        if result and shifted <= result[-1][0]:
            raise ValueError("Invalid shifted energy grid")
        result.append((shifted, sigma))
    if len(result) < 2 or not any(s > 0 for _, s in result):
        raise ValueError("Insufficient shifted cross-section coverage")
    return result, dropped


def build(rid: int, source_csv: Path, source_manifest: Path, output_dir: Path,
          date_string: str, *, accept_model: bool = False, replace: bool = False) -> dict:
    if rid not in REACTIONS:
        raise ValueError("Only reactions 2072, 2073 and 2074 supported")
    if not accept_model:
        raise ValueError("Explicit --accept-model-threshold-shift required: NOT measured sigma(O2*)")
    date = dt.date.fromisoformat(date_string)
    if date > dt.date.today():
        raise ValueError("Retrieval date is in the future")
    source_csv = source_csv.resolve(strict=True)
    source_manifest = source_manifest.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir in source_csv.parents or output_dir in source_manifest.parents:
        raise ValueError("Original data/provenance must remain outside output directory")
    source_content = source_csv.read_text(encoding="utf-8")
    metadata = json.loads(source_manifest.read_text(encoding="utf-8"))
    src = check_parent_provenance(rid, source_csv, metadata)
    original = parse_ground_sigma(source_content)
    shifted, dropped = threshold_reduce(original)
    out = output_dir / f"o2s_{rid}_derived_sigma.csv"
    provenance = output_dir / f"o2s_{rid}_derived_provenance.json"
    if not replace and (out.exists() or provenance.exists()):
        raise FileExistsError("Do not overwrite existing derived data without --replace")
    output_dir.mkdir(parents=True, exist_ok=True)
    writer_io = io.StringIO(newline="")
    writer = csv.writer(writer_io, lineterminator="\n")
    writer.writerow(OUTPUT_SCHEMA)
    for e, sigma in shifted:
        writer.writerow((f"{e:.17g}", f"{sigma:.17g}"))
    output = writer_io.getvalue().encode("utf-8")
    out.write_bytes(output)
    reaction = REACTIONS[rid]
    manifest = {
        "reaction_id": rid, "oxygen_chemistry_issue": 419,
        "reaction_label": reaction.label,
        "target_state": "O2(a1Delta_g)", "parent_reaction_id": reaction.parent_id,
        "parent_reaction": reaction.parent_process,
        "source_manifest_sha256": _sha(source_manifest),
        "ground_sigma_sha256": _sha(source_csv), "ground_sigma_file": source_csv.name,
        "source_identity": src, "source_retrieved_on": date.isoformat(),
        "shift_eV": STATE_ENERGY_EV, "shift_method": "energy-axis-only; sigma unchanged",
        "parent_rows": len(original), "discarded_zero_source_rows": dropped,
        "output_rows": len(shifted), "output_file": out.name,
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "energy_unit": "eV", "cross_section_unit": "m2",
        "model_electron_loss_eV_PROVISIONAL": reaction.modeled_loss_eV,
        "energy_loss_model_note": "ground-channel assigned loss minus 0.977 eV; NOT a measured threshold or an accepted energy source",
        "validation_status": "DERIVED_MODEL_ONLY_NOT_EXPERIMENTAL_O2STAR_CROSS_SECTION",
        "boltzmann_rate_computed": False, "physics_source_activated": False,
        "benchmark_source": KIM_SOURCE, "benchmark_url": KIM_SOURCE_URL,
    }
    provenance.write_text(json.dumps(manifest, sort_keys=True, indent=2)+"\n",
                          encoding="utf-8")
    return manifest


def benchmark(rid: int, te: float) -> tuple[float, str]:
    """Maxwellian 1-7eV comparison laws from Kim 2006 Table 2.1."""
    if rid not in REACTIONS:
        raise ValueError("Unknown O2* reaction")
    if not math.isfinite(te) or not 1.0 <= te <= 7.0:
        raise ValueError("Kim 2006 benchmark only valid for 1 <= Te <= 7 eV")
    if rid == 2072:
        return 2.34e-15 * te**1.03 * math.exp(-11.31/te), "Kim2006_Table2.1"
    if rid == 2073:
        return 6.86e-15 * math.exp(-5.31/te), "Kim2006_Table2.1"
    return (1.88e-16 * te**1.699 * math.exp(-(16.81-.977)/te),
            "DERIVED_FROM_417_SHIFT_NOT_INDEPENDENT_EXPERIMENTAL_FORMULA")


def compare_rate_rows(rows: list[dict[str, str]]) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        if tuple(row) != RATE_SCHEMA:
            raise ValueError(f"Expected exact rate CSV columns {RATE_SCHEMA}")
        try:
            rid, te, rate = int(row["reaction_id"]), float(row["Te_eV"]), float(row["k_lookup_m3_s"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("Invalid Boltzmann rate fields") from exc
        fit, status = benchmark(rid, te)
        if not math.isfinite(rate) or rate < 0:
            raise ValueError("Rate must be nonnegative and finite")
        if (rid, te) in seen:
            raise ValueError("Repeated reaction and temperature grid point")
        seen.add((rid, te))
        out.append({
            "reaction_id": rid, "Te_eV": te, "k_lookup_m3_s": rate,
            "k_benchmark_m3_s": fit, "relative_deviation": (rate-fit)/fit,
            "benchmark_basis": status, "scientific_acceptance": False
        })
    if not out:
        raise ValueError("Empty actual Lookup rate file")
    return sorted(out, key=lambda r: (r["reaction_id"], r["Te_eV"]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    model = sub.add_parser("derive", help="Produce provisional O2* model cross sections")
    model.add_argument("--reaction-id", type=int, choices=sorted(REACTIONS), required=True)
    model.add_argument("--ground-sigma-csv", type=Path, required=True)
    model.add_argument("--ground-provenance-json", type=Path, required=True)
    model.add_argument("--output-dir", type=Path, required=True)
    model.add_argument("--retrieved-on", required=True)
    model.add_argument("--accept-model-threshold-shift", action="store_true")
    model.add_argument("--replace", action="store_true")
    comp = sub.add_parser("compare", help="Compare independent Boltzmann tables with Kim fits")
    comp.add_argument("--rates-csv", type=Path, required=True)
    comp.add_argument("--report-json", type=Path, required=True)
    a = p.parse_args()
    if a.command == "derive":
        info = build(a.reaction_id, a.ground_sigma_csv, a.ground_provenance_json,
                     a.output_dir, a.retrieved_on, accept_model=a.accept_model_threshold_shift,
                     replace=a.replace)
        print("O2S_MODEL_DERIVED_SIGMA_READY_NOT_MEASURED_NOT_SCIENTIFIC_PASS")
        print(f"id={info['reaction_id']} rows={info['output_rows']}")
    else:
        with a.rates_csv.open(newline="", encoding="utf-8") as stream:
            rows = compare_rate_rows(list(csv.DictReader(stream)))
        a.report_json.write_text(json.dumps({
            "status": "NUMERICAL_FORMULA_COMPARISON_ONLY",
            "no_scientific_acceptance": True,
            "comparison": rows
        }, indent=2)+"\n", encoding="utf-8")
        print("O2S_FORMULA_BENCHMARK_COMPARISON_ONLY")


if __name__ == "__main__":
    main()
