#!/usr/bin/env python3
"""Issue #376 T3 RF-transfer counterfactual and frozen-state determinism checks."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

ZERO_W = 1.0e-12
ZERO_SOURCE = 1.0e-16
ZERO_ENERGY_DRIFT = 1.0e-13
FIELD_ZERO = 1.0e-12
FIELD_NONZERO = 1.0e-6
DETERMINISTIC_REL = 1.0e-12


def last_csv(path: Path) -> dict[str, float]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty CSV: {path}")
    return {k: float(v) for k, v in rows[-1].items() if k and v not in (None, "")}


def all_rows(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return [{k: float(v) for k, v in row.items() if k and v not in (None, "")} for row in rows]


def decode_names(var) -> list[str]:
    arr = np.asarray(var.data).copy()
    out = []
    for row in arr:
        if row.dtype.kind == "S":
            s = b"".join(row.tolist()).decode(errors="ignore")
        else:
            s = "".join(chr(int(v)) for v in row if int(v) != 0)
        out.append(s.split("\0")[0].strip())
    return out


def exodus_nodal(path: Path, names: tuple[str, ...]) -> dict[str, np.ndarray]:
    with netcdf_file(path, "r", mmap=False) as f:
        var_names = decode_names(f.variables["name_nod_var"])
        out = {}
        for name in names:
            idx = var_names.index(name) + 1
            out[name] = np.asarray(f.variables[f"vals_nod_var{idx}"].data[-1], dtype=float).copy()
    return out


def rel_l2(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1.0e-300))


def energy_drift(rows: list[dict[str, float]]) -> float:
    return rows[-1]["electron_energy_inventory_eV_mol"] - rows[0]["electron_energy_inventory_eV_mol"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-source-csv", type=Path, required=True)
    ap.add_argument("--baseline-source-e", type=Path, required=True)
    ap.add_argument("--baseline-target-csv", type=Path, required=True)
    ap.add_argument("--baseline-target-e", type=Path, required=True)
    ap.add_argument("--repeat-source-csv", type=Path, required=True)
    ap.add_argument("--repeat-source-e", type=Path, required=True)
    ap.add_argument("--repeat-target-csv", type=Path, required=True)
    ap.add_argument("--repeat-target-e", type=Path, required=True)
    ap.add_argument("--field-off-source-csv", type=Path, required=True)
    ap.add_argument("--field-off-target-csv", type=Path, required=True)
    ap.add_argument("--reactive-source-csv", type=Path, required=True)
    ap.add_argument("--reactive-target-csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    failures: list[str] = []

    bsrc = last_csv(args.baseline_source_csv)
    btar_rows = all_rows(args.baseline_target_csv)
    btar = btar_rows[-1]
    rsrc = last_csv(args.repeat_source_csv)
    rtar = last_csv(args.repeat_target_csv)
    fsrc = last_csv(args.field_off_source_csv)
    ftar_rows = all_rows(args.field_off_target_csv)
    ftar = ftar_rows[-1]
    xsrc = last_csv(args.reactive_source_csv)
    xtar_rows = all_rows(args.reactive_target_csv)
    xtar = xtar_rows[-1]

    # Transfer disabled: baseline Maxwell must remain active while target RF source is exactly off.
    baseline_field = math.hypot(bsrc["E_real_l2"], bsrc["E_imag_l2"])
    transfer_off_drift = energy_drift(btar_rows)
    if not (bsrc["P_abs"] > 0.0 and baseline_field > FIELD_NONZERO):
        failures.append("transfer-off discriminator lost the active Maxwell baseline")
    if abs(btar["S_rf_eV_mol_s"]) > ZERO_SOURCE:
        failures.append(f"transfer-off RF energy source nonzero: {btar['S_rf_eV_mol_s']:.6e}")
    if abs(transfer_off_drift) > ZERO_ENERGY_DRIFT:
        failures.append(f"transfer-off energy inventory drift {transfer_off_drift:.6e}")
    if not (btar["P_rf_raw_W"] > 0.0):
        failures.append("transfer-off target no longer sees the nonzero Maxwell field")

    # RF field/source off.
    field_off_norm = math.hypot(fsrc["E_real_l2"], fsrc["E_imag_l2"])
    field_off_drift = energy_drift(ftar_rows)
    if field_off_norm > FIELD_ZERO or abs(fsrc["P_abs"]) > ZERO_W:
        failures.append("RF-source-off Maxwell field/power is not zero")
    for key in ("P_rf_raw_W", "P_rf_scaled_W"):
        if abs(ftar[key]) > ZERO_W:
            failures.append(f"RF-source-off target {key} nonzero: {ftar[key]:.6e}")
    if abs(ftar["S_rf_eV_mol_s"]) > ZERO_SOURCE:
        failures.append("RF-source-off target electron-energy source is nonzero")
    if abs(field_off_drift) > ZERO_ENERGY_DRIFT:
        failures.append(f"RF-source-off energy inventory drift {field_off_drift:.6e}")

    # sigma_R -> 0 with reactive sigma_I retained: field must remain nonzero while dissipation vanishes.
    reactive_field = math.hypot(xsrc["E_real_l2"], xsrc["E_imag_l2"])
    reactive_drift = energy_drift(xtar_rows)
    if reactive_field <= FIELD_NONZERO:
        failures.append("reactive-only Maxwell field unexpectedly vanished")
    if abs(xsrc["P_abs"]) > ZERO_W:
        failures.append(f"reactive-only source P_abs nonzero: {xsrc['P_abs']:.6e}")
    for key in ("P_rf_raw_W", "P_rf_scaled_W"):
        if abs(xtar[key]) > ZERO_W:
            failures.append(f"reactive-only target {key} nonzero: {xtar[key]:.6e}")
    if abs(xtar["S_rf_eV_mol_s"]) > ZERO_SOURCE:
        failures.append("reactive-only target electron-energy source is nonzero")
    if abs(reactive_drift) > ZERO_ENERGY_DRIFT:
        failures.append(f"reactive-only energy inventory drift {reactive_drift:.6e}")

    # Frozen-state determinism: prescribed sigma/source state repeated exactly through Maxwell and mapping.
    bsrc_e = exodus_nodal(args.baseline_source_e, ("E_real", "E_imag"))
    rsrc_e = exodus_nodal(args.repeat_source_e, ("E_real", "E_imag"))
    btar_e = exodus_nodal(args.baseline_target_e, ("E_real_rf", "E_imag_rf"))
    rtar_e = exodus_nodal(args.repeat_target_e, ("E_real_rf", "E_imag_rf"))
    source_real_rel = rel_l2(rsrc_e["E_real"], bsrc_e["E_real"])
    source_imag_rel = rel_l2(rsrc_e["E_imag"], bsrc_e["E_imag"])
    target_real_rel = rel_l2(rtar_e["E_real_rf"], btar_e["E_real_rf"])
    target_imag_rel = rel_l2(rtar_e["E_imag_rf"], btar_e["E_imag_rf"])
    source_power_rel = abs(rsrc["P_abs"] - bsrc["P_abs"]) / max(abs(bsrc["P_abs"]), 1.0e-300)
    target_power_rel = abs(rtar["P_rf_raw_W"] - btar["P_rf_raw_W"]) / max(abs(btar["P_rf_raw_W"]), 1.0e-300)
    det_metrics = [source_real_rel, source_imag_rel, target_real_rel, target_imag_rel, source_power_rel, target_power_rel]
    if max(det_metrics) > DETERMINISTIC_REL:
        failures.append(f"frozen-state deterministic mismatch {max(det_metrics):.6e} > {DETERMINISTIC_REL:.6e}")

    report = {
        "issue": 376,
        "gate": "T3 RF-transfer counterfactuals and frozen-state determinism",
        "status": "FAIL" if failures else "PASS",
        "scientific_acceptance": {"T3_counterfactuals": not failures, "issue_376_complete": False},
        "transfer_disabled": {
            "maxwell_P_abs_W": bsrc["P_abs"],
            "maxwell_field_l2": baseline_field,
            "target_raw_power_W": btar["P_rf_raw_W"],
            "target_RF_source_eV_mol_s": btar["S_rf_eV_mol_s"],
            "energy_inventory_drift_eV_mol": transfer_off_drift,
        },
        "rf_source_off": {
            "maxwell_field_l2": field_off_norm,
            "maxwell_P_abs_W": fsrc["P_abs"],
            "target_raw_power_W": ftar["P_rf_raw_W"],
            "target_RF_source_eV_mol_s": ftar["S_rf_eV_mol_s"],
            "energy_inventory_drift_eV_mol": field_off_drift,
        },
        "sigma_R_zero_reactive_only": {
            "maxwell_field_l2": reactive_field,
            "maxwell_P_abs_W": xsrc["P_abs"],
            "target_raw_power_W": xtar["P_rf_raw_W"],
            "target_RF_source_eV_mol_s": xtar["S_rf_eV_mol_s"],
            "energy_inventory_drift_eV_mol": reactive_drift,
        },
        "frozen_state_determinism": {
            "source_E_real_relative_l2": source_real_rel,
            "source_E_imag_relative_l2": source_imag_rel,
            "target_E_real_relative_l2": target_real_rel,
            "target_E_imag_relative_l2": target_imag_rel,
            "source_P_abs_relative_difference": source_power_rel,
            "target_raw_power_relative_difference": target_power_rel,
            "max_metric": max(det_metrics),
        },
        "tolerances": {
            "zero_power_W": ZERO_W,
            "zero_source_eV_mol_s": ZERO_SOURCE,
            "zero_energy_drift_eV_mol": ZERO_ENERGY_DRIFT,
            "field_zero_l2": FIELD_ZERO,
            "field_nonzero_l2": FIELD_NONZERO,
            "frozen_deterministic_relative": DETERMINISTIC_REL,
        },
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
