#!/usr/bin/env python3
"""Issue #395 RF-only 100 -> 110 ns discriminator.

Purpose:
- reproduce the common chemistry-free 100 ns plasma state;
- calibrate the Maxwell drive to 1000 W absorbed power at 100 ns;
- reproduce the accepted target-quadrature RF deposition normalization;
- run a fresh continuous 0 -> 110 ns TimeSequenceStepper trajectory with
  chemistry absent and RF heating enabled only for the 100 -> 110 ns step;
- report the converged 110 ns electron-energy response without any chemistry
  lookup owner in the production input.
"""
from __future__ import annotations

import argparse
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
import run_t6_representative_icp_v2 as v2  # noqa: E402

import run_a1_powered as a1  # noqa: E402

TARGET_W = 1000.0
FINAL_TIME_S = 1.10e-7
TIME_TOL = 5.0e-15


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--physics", required=True)
    p.add_argument("--plasma-input-100ns", type=Path, required=True)
    p.add_argument("--plasma-input-15us", type=Path, required=True)
    p.add_argument("--rf-plasma-overlay", type=Path, required=True)
    p.add_argument("--rf-only-control-overlay", type=Path, required=True)
    p.add_argument("--maxwell-input", type=Path, required=True)
    p.add_argument("--maxwell-overlay", type=Path, required=True)
    p.add_argument("--transport-table", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    return p.parse_args()


def finite_state(s: dict[str, np.ndarray]) -> bool:
    return all(np.all(np.isfinite(v)) for v in s.values())


def main() -> int:
    a = args()
    out = a.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    analysis = a.analysis.resolve()
    report: dict = {
        "issue": 395,
        "gate": "RF-only 100 to 110 ns discriminator",
        "status": "ERROR",
        "failures": [],
    }

    try:
        physics = str(Path(a.physics).resolve())
        pin100 = str(a.plasma_input_100ns.resolve())
        pin15 = str(a.plasma_input_15us.resolve())
        rfov = str(a.rf_plasma_overlay.resolve())
        rfctrl = str(a.rf_only_control_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())
        tx, tm = base.table(a.transport_table)

        # Seed RF map for the chemistry-free, RF-off 100 ns calibration state.
        seed = out / "seed" / "maxwell"
        base.run([physics, "-i", minp, f"Outputs/file_base={seed}"], out / "seed" / "maxwell.log")
        seed_e = seed.with_suffix(".e")

        # Separate preparation trajectory: 0 -> 100 ns, no chemistry, no RF heating.
        pbase = out / "calibration_state" / "plasma"
        common100 = [physics, "-i", pin100, rfov]
        base.run(
            common100
            + [
                f"maxwell_solution_file_t6={seed_e}",
                "source_enable_t6=0",
                "rf_scale_t6=1",
                f"Outputs/file_base={pbase}",
            ],
            out / "calibration_state" / "run.log",
        )
        pe, pcsv = pbase.with_suffix(".e"), pbase.with_suffix(".csv")
        state100 = out / "calibration_state" / "state100ns.e"
        csv100 = out / "calibration_state" / "state100ns.csv"
        shutil.copy2(pe, state100)
        shutil.copy2(pcsv, csv100)

        active_cp = Path(str(pbase) + "_cp")
        checkpoint100 = out / "calibration_state" / "checkpoint100ns"
        if not active_cp.is_dir():
            raise RuntimeError("100 ns checkpoint missing")
        shutil.copytree(active_cp, checkpoint100)

        # 1000 W Maxwell calibration at the 100 ns plasma state.
        probe = out / "maxwell_probe" / "maxwell"
        base.run(
            [
                physics,
                "-i",
                minp,
                mov,
                f"plasma_solution_file_t6={state100}",
                "source_scale=1",
                f"Outputs/file_base={probe}",
            ],
            out / "maxwell_probe" / "run.log",
        )
        pprobe = base.csv_last(probe.with_suffix(".csv"))["P_abs"]
        drive = math.sqrt(TARGET_W / pprobe)

        m1 = out / "maxwell1" / "maxwell"
        base.run(
            [
                physics,
                "-i",
                minp,
                mov,
                f"plasma_solution_file_t6={state100}",
                f"source_scale={drive:.17g}",
                f"Outputs/file_base={m1}",
            ],
            out / "maxwell1" / "run.log",
        )
        m1e = m1.with_suffix(".e")
        pabs1 = base.csv_last(m1.with_suffix(".csv"))["P_abs"]
        independent_raw, state100_stats = base.mapped_raw_power(state100, m1e, tx, tm)

        # Accepted target-quadrature deposition normalization. This is a same-topology
        # 100 -> 101 ns probe with RF residual injection still disabled.
        v2.restore_checkpoint(checkpoint100, active_cp)
        shutil.copy2(state100, pe)
        shutil.copy2(csv100, pcsv)
        base.run(
            common100
            + [
                f"maxwell_solution_file_t6={m1e}",
                "source_enable_t6=0",
                "rf_scale_t6=1",
                "Executioner/end_time=1.01e-7",
                "Executioner/num_steps=101",
                f"Outputs/file_base={pbase}",
                "--recover",
            ],
            out / "target_raw_probe.log",
        )
        praw = base.csv_last(pcsv)["P_rf_raw_W_t6"]
        rf_scale = pabs1 / praw

        # Production discriminator: one fresh trajectory, no chemistry overlay at all.
        # TimePeriod in rfctrl keeps RF heating off through 100 ns and enables it for
        # the first staged 100 -> 110 ns step.
        prod = out / "rf_only_110ns" / "plasma"
        base.run(
            [
                physics,
                "-i",
                pin15,
                rfov,
                rfctrl,
                f"maxwell_solution_file_t6={m1e}",
                "source_enable_t6=1",
                f"rf_scale_t6={rf_scale:.17g}",
                f"Executioner/end_time={FINAL_TIME_S:.17g}",
                f"Outputs/file_base={prod}",
            ],
            out / "rf_only_110ns" / "run.log",
        )

        prode = prod.with_suffix(".e")
        prodcsv = prod.with_suffix(".csv")
        ex = base.exodus(prode)
        times = np.asarray(ex["times"], dtype=float)
        if len(times) < 2:
            raise RuntimeError("RF-only production Exodus has fewer than two time points")

        s100 = a1.state_fields(state100)
        s110 = a1.state_fields(prode)
        c110 = base.csv_last(prodcsv)

        i100 = int(np.argmin(np.abs(times - 1.0e-7)))
        first_post_100_dt = (
            float(times[i100 + 1] - times[i100]) if i100 + 1 < len(times) else float("nan")
        )

        metrics = {
            "final_time_s": float(times[-1]),
            "time_points": int(len(times)),
            "time_at_index_100_s": float(times[i100]),
            "first_post_100ns_dt_s": first_post_100_dt,
            "target_power_error": base.rel(pabs1, TARGET_W),
            "raw_remesh_defect_at_100ns": base.rel(independent_raw, pabs1),
            "rf_deposition_scale": rf_scale,
            "rf_power_at_110ns_W": c110["P_rf_scaled_W_t6"],
            "rf_source_unit_closure_at_110ns": base.rel(
                c110["S_rf_eV_mol_s_t6"] * base.FARADAY,
                c110["P_rf_scaled_W_t6"],
            ),
            "energy_response_100_to_110ns": a1.rel_l2(s110["mean_en_eV"], s100["mean_en_eV"]),
            "electron_response_100_to_110ns": a1.rel_l2(s110["ne_mol"], s100["ne_mol"]),
            "mean_energy_100ns_min_eV": float(np.min(s100["mean_en_eV"])),
            "mean_energy_100ns_max_eV": float(np.max(s100["mean_en_eV"])),
            "mean_energy_110ns_min_eV": float(np.min(s110["mean_en_eV"])),
            "mean_energy_110ns_max_eV": float(np.max(s110["mean_en_eV"])),
            "ne_110ns_min_mol_m3": float(np.min(s110["ne_mol"])),
            "pressure_110ns_min_Pa": float(np.min(s110["p_Pa"])),
        }

        failures: list[str] = []
        if abs(metrics["final_time_s"] - FINAL_TIME_S) > TIME_TOL:
            failures.append("did not reach 110 ns")
        if abs(metrics["time_at_index_100_s"] - 1.0e-7) > TIME_TOL:
            failures.append("100 ns grid point missing")
        if abs(metrics["first_post_100ns_dt_s"] - 1.0e-8) > TIME_TOL:
            failures.append("first post-100 ns step is not 10 ns")
        if metrics["target_power_error"] > a1.TARGET_GATE:
            failures.append("1000 W calibration")
        if metrics["raw_remesh_defect_at_100ns"] > base.RAW_GATE:
            failures.append("RF remesh defect")
        if metrics["rf_source_unit_closure_at_110ns"] > base.SOURCE_UNIT_GATE:
            failures.append("RF source-unit closure")
        if not finite_state(s110):
            failures.append("non-finite 110 ns plasma state")
        if metrics["ne_110ns_min_mol_m3"] <= 0 or metrics["pressure_110ns_min_Pa"] <= 0:
            failures.append("110 ns positivity")

        report = {
            "issue": 395,
            "gate": "RF-only 100 to 110 ns discriminator",
            "status": "PASS" if not failures else "FAIL",
            "classification": (
                "ISSUE395_RF_ONLY_110NS_PASS" if not failures else "ISSUE395_RF_ONLY_110NS_FAIL"
            ),
            "scope": (
                "separate 100 ns calibration state; 1000 W Maxwell calibration; fresh continuous "
                "0-to-110 ns TimeSequenceStepper production trajectory with chemistry absent and "
                "RF heating enabled only for the 100-to-110 ns step"
            ),
            "active_chemistry": [],
            "chemistry_overlay_in_production": False,
            "rf_activation": "100-to-110 ns step only after common 100 ns baseline",
            "restart_recover_in_production": False,
            "drive_source_scale": drive,
            "effective_peak_coil_current_A": 10.0 * drive,
            "Maxwell_100ns_P_abs_W": pabs1,
            "state100ns": state100_stats,
            "metrics": metrics,
            "failures": failures,
        }
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not failures else 2

    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
