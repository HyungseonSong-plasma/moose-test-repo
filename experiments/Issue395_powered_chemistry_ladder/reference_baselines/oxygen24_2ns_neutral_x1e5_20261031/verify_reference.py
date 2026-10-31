#!/usr/bin/env python3
"""Read-only verifier for the pinned Oxygen24 400/1000W 2ns candidate reference."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
MANIFEST = BASE / "manifest.json"
N_A = 6.02214076e23


def close(actual: float, expected: float, name: str, rtol: float = 1e-11):
    if not math.isfinite(actual) or not math.isclose(
        actual, expected, rel_tol=rtol, abs_tol=1e-15
    ):
        raise ValueError(f"{name}: {actual!r} != {expected!r}")


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(m: dict) -> None:
    assert m["status"] == "BOUNDED_2NS_REFERENCE_CANDIDATE_NOT_CANONICAL_SCIENTIFIC_BASELINE"
    assert len(m["exact_executed_source_sha"]) == 40
    assert m["reconstruction"]["time_grid_s"] == [0, 1e-9, 2e-9]
    assert m["reconstruction"]["private_19_numeric_rate_tables_required"]
    assert m["chemistry"]["activated_count"] == 24
    assert set(m["cases"]) == {"400W", "1000W"}
    inlet = m["inlet"]
    x = inlet["mole_fractions"]
    mw = inlet["molar_masses_kg_mol"]
    close(sum(x.values()), 1.0, "inlet sum")
    mean_m = sum(x[k] * mw[k] for k in x)
    for name, target in inlet["mass_fractions"].items():
        close(x[name] * mw[name] / mean_m, target, f"inlet Y({name})")
    receiver = inlet["receiver_defaults_kg_s"]
    total = receiver["neutral_inlet_mdot"]
    close(sum(v for k, v in receiver.items() if k != "neutral_inlet_mdot"),
          total, "receiver mass flow closure")
    close(total, inlet["total_mass_flow_kg_s"], "total inlet flow")
    for species in ("O2_a1Delta", "O_3P", "O_1D"):
        close(x[species], 1e-5, f"mole fraction {species}")
    neutral_y = m["initial_state"]["neutral_mass_fractions"]
    close(sum(neutral_y.values()) + inlet["mass_fractions"]["O2_X"],
          1.0, "neutral mass fraction closure")
    for name, case in m["cases"].items():
        assert case["rf_target_w"] == int(name[:-1])
        assert case["reference_input_sha256"] == m["common_generated_main_input_sha256"]
        assert all(case[f"p{i}"] == "PASS" for i in range(5))
        close(case["actual_final_time_s"], 2e-9, f"{name} end time")


def unique_body(text: str, name: str) -> str:
    pattern = r"(?ms)^  \[" + re.escape(name) + r"\]\s*\n(.*?)^  \[\]\s*$"
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise ValueError(f"missing/duplicated block {name}")
    return matches[0]


def unique_numeric(body: str, name: str) -> float:
    values = re.findall(r"(?m)^\s*" + re.escape(name) +
                        r"\s*=\s*([^#\n]+)", body)
    if len(values) != 1:
        raise ValueError(f"missing/ambiguous {name}")
    return float(values[0].strip())


def verify_input(m: dict, case_name: str, path: Path) -> None:
    case = m["cases"][case_name]
    if hash_file(path) != case["reference_input_sha256"]:
        raise ValueError(f"{case_name}: generated main input SHA-256 differs from reference")
    text = path.read_text(encoding="utf-8")
    for name, value in m["initial_state"]["neutral_mass_fractions"].items():
        close(unique_numeric(unique_body(text, name), "initial_condition"),
              value, f"{name} IC")
    for name, value in m["inlet"]["receiver_defaults_kg_s"].items():
        close(unique_numeric(unique_body(text, name), "default"),
              value, f"{name} Receiver")
    em = re.findall(r"(?ms)^\[Executioner\]\s*\n(.*?)^\[\]\s*$", text)
    if len(em) != 1:
        raise ValueError("missing or multiple Executioner blocks")
    close(unique_numeric(em[0], "end_time"), 2e-9, "end_time")
    sequences = re.findall(r"(?m)^\s*time_sequence\s*=\s*'([^']+)'", em[0])
    if len(sequences) != 1:
        raise ValueError("missing or duplicated time_sequence")
    grid = [float(s) for s in sequences[0].split()]
    if len(grid) != 3:
        raise ValueError(f"expected 3 time points, got {len(grid)}")
    for i, value in enumerate([0.0, 1e-9, 2e-9]):
        close(grid[i], value, f"time[{i}]", rtol=1e-12)


def verify_csv(m: dict, case_name: str, path: Path) -> None:
    case = m["cases"][case_name]
    if hash_file(path) != case["output_csv_sha256"]:
        raise ValueError(f"{case_name}: CSV SHA-256 differs from archived evidence")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 3:
        raise ValueError(f"expected 3 CSV observations, got {len(rows)}")
    for idx, time in enumerate([0.0, 1e-9, 2e-9]):
        close(float(rows[idx]["time"]), time, f"CSV time[{idx}]")
    initial = rows[0]
    for species, column in (
        ("O2_X", "n_O2_X_avg"), ("O2_a1Delta", "n_O2_a_avg"),
        ("O_3P", "n_O_3P_avg"), ("O_1D", "n_O_1D_avg")
    ):
        close(float(initial[column]),
              m["initial_state"]["observed_initial_number_density_m3"][species],
              f"CSV initial {column}", rtol=1e-10)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case", choices=["400W", "1000W"])
    p.add_argument("--input", type=Path)
    p.add_argument("--csv", type=Path)
    p.add_argument("--manifest-only", action="store_true")
    args = p.parse_args()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    verify_manifest(m)
    if args.manifest_only:
        print("OXYGEN24_REFERENCE_MANIFEST_PASS")
        return
    if not args.case or not args.input:
        p.error("--case and --input are required unless --manifest-only")
    verify_input(m, args.case, args.input)
    if args.csv:
        verify_csv(m, args.case, args.csv)
    print(f"OXYGEN24_{args.case}_PINNED_INPUT_REFERENCE_PASS")
    if args.csv:
        print(f"OXYGEN24_{args.case}_PINNED_OUTPUT_REFERENCE_PASS")


if __name__ == "__main__":
    main()
