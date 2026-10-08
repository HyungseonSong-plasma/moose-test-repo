#!/usr/bin/env python3
"""Analyze Issue #202 RF absorbed-power formula and counterfactuals."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

REL_TOL = 5.0e-3
ZERO_TOL_W = 1.0e-12
FIELD_ZERO_TOL = 1.0e-12
FIELD_NONZERO_TOL = 1.0e-6


def load_csv(path: Path) -> dict[str, float]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty csv: {path}")
    return {k: float(v) for k, v in rows[-1].items() if k and v not in (None, "")}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    names = ["baseline", "lossless", "reactive_only", "field_off"]
    moose = {name: load_csv(args.dir / f"{name}.csv") for name in names}
    refs = {name: load_json(args.dir / f"reference_{name}.json") for name in names}
    failures: list[str] = []

    p_m = moose["baseline"]["P_abs"]
    p_r = float(refs["baseline"]["P_abs_W"])
    rel = abs(p_m - p_r) / max(abs(p_r), 1e-30)
    if not (p_m > 0.0 and p_r > 0.0):
        failures.append("baseline absorbed power is not positive")
    if rel > REL_TOL:
        failures.append(f"baseline MOOSE/reference P_abs relative error {rel:.6e} > {REL_TOL:.6e}")

    for name in ("lossless", "reactive_only"):
        if abs(moose[name]["P_abs"]) > ZERO_TOL_W:
            failures.append(f"{name} MOOSE P_abs is nonzero: {moose[name]['P_abs']:.6e} W")
        if abs(float(refs[name]["P_abs_W"])) > ZERO_TOL_W:
            failures.append(f"{name} reference P_abs is nonzero")
        field = math.hypot(moose[name]["E_real_l2"], moose[name]["E_imag_l2"])
        if field <= FIELD_NONZERO_TOL:
            failures.append(f"{name} field unexpectedly vanished")

    off_field = math.hypot(moose["field_off"]["E_real_l2"], moose["field_off"]["E_imag_l2"])
    if off_field > FIELD_ZERO_TOL:
        failures.append(f"field_off MOOSE field norm is nonzero: {off_field:.6e}")
    if abs(moose["field_off"]["P_abs"]) > ZERO_TOL_W:
        failures.append(f"field_off MOOSE P_abs is nonzero: {moose['field_off']['P_abs']:.6e} W")
    if float(refs["field_off"]["max_abs_E_V_per_m"]) > FIELD_ZERO_TOL:
        failures.append("field_off reference field is nonzero")
    if abs(float(refs["field_off"]["P_abs_W"])) > ZERO_TOL_W:
        failures.append("field_off reference P_abs is nonzero")

    report = {
        "issue": 202,
        "scope": "RF absorbed-power formula and dissipative/reactive counterfactuals",
        "status": "FAIL" if failures else "PASS",
        "scientific_acceptance": False,
        "formula": "Q_RF=0.5*sigma_R*(E_real^2+E_imag^2), peak phasors",
        "baseline": {
            "moose_P_abs_W": p_m,
            "reference_P_abs_W": p_r,
            "relative_error": rel,
        },
        "lossless": {"moose_P_abs_W": moose["lossless"]["P_abs"]},
        "reactive_only": {
            "moose_P_abs_W": moose["reactive_only"]["P_abs"],
            "field_l2": math.hypot(moose["reactive_only"]["E_real_l2"], moose["reactive_only"]["E_imag_l2"]),
        },
        "field_off": {"moose_P_abs_W": moose["field_off"]["P_abs"], "field_l2": off_field},
        "tolerances": {"power_relative": REL_TOL, "zero_W": ZERO_TOL_W},
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
