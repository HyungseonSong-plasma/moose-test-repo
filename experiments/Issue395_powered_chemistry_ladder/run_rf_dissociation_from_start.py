#!/usr/bin/env python3
"""Issue #395 fresh RF-ON + O2 dissociation trajectory from t=0 to 110 ns.

Production semantics:
- no restart/recover is used in the production trajectory;
- RF heating is enabled at t=0;
- the source-backed O2 dissociation overlay is present and active at t=0;
- the accepted RF-only 110 ns drive/deposition scales are reused;
- a separate chemistry-free 100 ns trajectory is used only to regenerate the
  accepted fixed Maxwell field map.  Its state is never used to initialize the
  production trajectory.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
T6_DIR = ROOT / "experiments" / "Issue376_maxwell_plasma_rf_transfer"
sys.path.insert(0, str(T6_DIR))
import run_t6_representative_icp as base  # noqa: E402

TARGET_W = 1000.0
DRIVE_SOURCE_SCALE = 7.49559809637885
RF_DEPOSITION_SCALE = 0.9997443712965226
FINAL_TIME_S = 1.10e-7
TIME_TOL = 5.0e-15
TABLE_LO = 1.40991
TABLE_HI = 22.1378
SOURCE_CLOSURE_GATE = 1.0e-10
INITIAL_W_O = 0.10309278350515465


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--physics", required=True)
    p.add_argument("--plasma-input-100ns", type=Path, required=True)
    p.add_argument("--plasma-input-110ns", type=Path, required=True)
    p.add_argument("--rf-plasma-overlay", type=Path, required=True)
    p.add_argument("--dissociation-overlay", type=Path, required=True)
    p.add_argument("--maxwell-input", type=Path, required=True)
    p.add_argument("--maxwell-overlay", type=Path, required=True)
    p.add_argument("--transport-table", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    return p.parse_args()


def finite_state(s: dict[str, np.ndarray]) -> bool:
    return all(np.all(np.isfinite(v)) for v in s.values())


def state_fields(path: Path) -> dict[str, np.ndarray]:
    st = base.exodus(path)
    plasma_nodes = np.unique(st["blocks"]["plasma"].reshape(-1))
    log_ne = st["nodal"]["log_ne"][-1][plasma_nodes]
    log_energy = st["nodal"]["log_energy"][-1][plasma_nodes]
    return {
        "ne_mol": np.exp(log_ne),
        "mean_en_eV": np.exp(log_energy - log_ne),
        "o2p_mol": np.exp(st["elem"]["plasma"]["log_ni"][-1]),
        "p_Pa": st["elem"]["plasma"]["p"][-1],
        "w_O": st["elem"]["plasma"]["w_O"][-1],
    }


def read_csv_rows(path: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            row: dict[str, float] = {}
            for key, value in raw.items():
                if key is None or value is None or value == "":
                    continue
                try:
                    row[key] = float(value)
                except ValueError:
                    pass
            if row:
                rows.append(row)
    return rows


def first_row_with(rows: list[dict[str, float]], keys: tuple[str, ...]) -> dict[str, float]:
    for row in rows:
        if all(key in row and math.isfinite(row[key]) for key in keys):
            return row
    raise RuntimeError(f"no CSV row contains finite keys {keys}")


def main() -> int:
    a = args()
    out = a.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    analysis = a.analysis.resolve()
    report: dict = {
        "issue": 395,
        "gate": "RF-ON plus source-backed O2 dissociation from t=0 to 110 ns",
        "status": "ERROR",
        "failures": [],
    }

    try:
        physics = str(Path(a.physics).resolve())
        pin100 = str(a.plasma_input_100ns.resolve())
        pin110 = str(a.plasma_input_110ns.resolve())
        rfov = str(a.rf_plasma_overlay.resolve())
        dissov = str(a.dissociation_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())
        tx, tm = base.table(a.transport_table)

        # Regenerate the accepted fixed Maxwell map.  This reference trajectory
        # is calibration-only; it is never used as a production restart state.
        seed = out / "reference_map" / "seed" / "maxwell"
        base.run([physics, "-i", minp, f"Outputs/file_base={seed}"], out / "reference_map" / "seed" / "maxwell.log")
        seed_e = seed.with_suffix(".e")

        pbase = out / "reference_map" / "plasma100" / "plasma"
        base.run(
            [
                physics,
                "-i",
                pin100,
                rfov,
                f"maxwell_solution_file_t6={seed_e}",
                "source_enable_t6=0",
                "rf_scale_t6=1",
                f"Outputs/file_base={pbase}",
            ],
            out / "reference_map" / "plasma100" / "run.log",
        )
        state100 = pbase.with_suffix(".e")

        m1 = out / "reference_map" / "maxwell1000W" / "maxwell"
        base.run(
            [
                physics,
                "-i",
                minp,
                mov,
                f"plasma_solution_file_t6={state100}",
                f"source_scale={DRIVE_SOURCE_SCALE:.17g}",
                f"Outputs/file_base={m1}",
            ],
            out / "reference_map" / "maxwell1000W" / "run.log",
        )
        m1e = m1.with_suffix(".e")
        pabs_ref = base.csv_last(m1.with_suffix(".csv"))["P_abs"]
        independent_raw, state100_stats = base.mapped_raw_power(state100, m1e, tx, tm)

        # Production: fresh trajectory.  No checkpoint restore and no --recover.
        # The RF kernel is not wrapped in a delayed TimePeriod control, and the
        # dissociation overlay is present in the input from INITIAL onward.
        prod = out / "production" / "plasma"
        base.run(
            [
                physics,
                "-i",
                pin110,
                rfov,
                dissov,
                f"maxwell_solution_file_t6={m1e}",
                "source_enable_t6=1",
                f"rf_scale_t6={RF_DEPOSITION_SCALE:.17g}",
                f"Executioner/end_time={FINAL_TIME_S:.17g}",
                f"Outputs/file_base={prod}",
            ],
            out / "production" / "run.log",
        )

        prode = prod.with_suffix(".e")
        prodcsv = prod.with_suffix(".csv")
        ex = base.exodus(prode)
        times = np.asarray(ex["times"], dtype=float)
        if len(times) < 2:
            raise RuntimeError("production Exodus has fewer than two time points")
        state = state_fields(prode)
        rows = read_csv_rows(prodcsv)
        first = first_row_with(rows, ("P_rf_scaled_W_t6", "diss_R_max", "diss_energy_source_integral"))
        last = rows[-1]

        metrics = {
            "final_time_s": float(times[-1]),
            "time_points": int(len(times)),
            "first_positive_dt_s": float(times[1] - times[0]),
            "reference_1000W_power_error": base.rel(pabs_ref, TARGET_W),
            "reference_raw_remesh_defect": base.rel(independent_raw, pabs_ref),
            "rf_power_first_reported_W": first["P_rf_scaled_W_t6"],
            "diss_R_max_first_reported_mol_m3_s": first["diss_R_max"],
            "diss_energy_first_reported_eV_mol_s": first["diss_energy_source_integral"],
            "rf_power_final_W": last["P_rf_scaled_W_t6"],
            "rf_source_unit_closure_final": base.rel(
                last["S_rf_eV_mol_s_t6"] * base.FARADAY,
                last["P_rf_scaled_W_t6"],
            ),
            "diss_R_min_final_mol_m3_s": last["diss_R_min"],
            "diss_R_max_final_mol_m3_s": last["diss_R_max"],
            "diss_R_integral_final_mol_s": last["diss_R_integral"],
            "diss_energy_source_final_eV_mol_s": last["diss_energy_source_integral"],
            "diss_O_mass_source_final_kg_s": last["diss_O_mass_source_integral"],
            "diss_heavy_mass_closure_final_kg_s": last["diss_heavy_mass_closure_integral"],
            "mean_energy_final_min_eV": float(np.min(state["mean_en_eV"])),
            "mean_energy_final_max_eV": float(np.max(state["mean_en_eV"])),
            "ne_final_min_mol_m3": float(np.min(state["ne_mol"])),
            "pressure_final_min_Pa": float(np.min(state["p_Pa"])),
            "w_O_final_min": float(np.min(state["w_O"])),
            "w_O_final_max": float(np.max(state["w_O"])),
            "w_O_final_mean": float(np.mean(state["w_O"])),
            "w_O_initial": INITIAL_W_O,
        }

        failures: list[str] = []
        if abs(metrics["final_time_s"] - FINAL_TIME_S) > TIME_TOL:
            failures.append("did not reach 110 ns")
        if metrics["reference_1000W_power_error"] > 1.0e-8:
            failures.append("accepted RF drive no longer reproduces 1000 W reference")
        if metrics["reference_raw_remesh_defect"] > base.RAW_GATE:
            failures.append("RF reference remesh defect")
        if metrics["rf_power_first_reported_W"] <= 0.0:
            failures.append("RF source is not active from the first reported state")
        if metrics["diss_R_max_first_reported_mol_m3_s"] <= 0.0:
            failures.append("dissociation progress is not active from the first reported state")
        if metrics["diss_energy_first_reported_eV_mol_s"] >= 0.0:
            failures.append("initial dissociation electron-energy source is not a sink")
        if metrics["rf_source_unit_closure_final"] > base.SOURCE_UNIT_GATE:
            failures.append("RF source-unit closure")
        if metrics["diss_R_max_final_mol_m3_s"] <= 0.0 or metrics["diss_R_integral_final_mol_s"] <= 0.0:
            failures.append("final dissociation progress is not positive")
        if metrics["diss_energy_source_final_eV_mol_s"] >= 0.0:
            failures.append("final dissociation electron-energy source is not a sink")
        if metrics["diss_O_mass_source_final_kg_s"] <= 0.0:
            failures.append("atomic-O production source is not positive")
        if abs(metrics["diss_heavy_mass_closure_final_kg_s"]) > SOURCE_CLOSURE_GATE:
            failures.append("dissociation heavy-mass source closure")
        if not finite_state(state):
            failures.append("non-finite final plasma state")
        if metrics["ne_final_min_mol_m3"] <= 0.0 or metrics["pressure_final_min_Pa"] <= 0.0:
            failures.append("final plasma positivity")
        if metrics["w_O_final_min"] < 0.0 or metrics["w_O_final_max"] >= 1.0:
            failures.append("atomic-O mass fraction bounds")
        if not (
            TABLE_LO
            <= metrics["mean_energy_final_min_eV"]
            <= metrics["mean_energy_final_max_eV"]
            <= TABLE_HI
        ):
            failures.append("final RF transport mean-energy range")

        report = {
            "issue": 395,
            "gate": "RF-ON plus source-backed O2 dissociation from t=0 to 110 ns",
            "status": "PASS" if not failures else "FAIL",
            "classification": (
                "ISSUE395_RF_DISSOCIATION_FROM_START_110NS_PASS"
                if not failures
                else "ISSUE395_RF_DISSOCIATION_FROM_START_110NS_FAIL"
            ),
            "scope": (
                "fresh continuous 0-to-110 ns production trajectory; RF heating active from INITIAL; "
                "source-backed e+O2->e+2O dissociation active from INITIAL; no production restart/recover"
            ),
            "production_restart_recover": False,
            "rf_activation": "t=0 / INITIAL",
            "dissociation_activation": "t=0 / INITIAL",
            "dissociation_rate_law": "1.41e-15*Te_eV^0.22*exp(-12.62/Te_eV) m3/s; Te=(2/3)*mean_en_solved",
            "dissociation_energy_loss_eV": 12.62,
            "historical_csv_used": False,
            "reference_rf_drive": {
                "source_scale": DRIVE_SOURCE_SCALE,
                "rf_deposition_scale": RF_DEPOSITION_SCALE,
                "effective_peak_coil_current_A": 10.0 * DRIVE_SOURCE_SCALE,
                "P_abs_reference_W": pabs_ref,
                "state100ns": state100_stats,
                "purpose": "fixed Maxwell map regeneration only; not a production restart state",
            },
            "metrics": metrics,
            "failures": failures,
        }
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not failures else 2

    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
