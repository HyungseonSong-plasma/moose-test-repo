#!/usr/bin/env python3
"""Issue #395 A1 long-horizon powered chemistry stability screen.

This is a direct extension of the accepted A1 one-step discriminator:
- bootstrap chemistry-OFF to 100 ns with the same chemistry/RF object topology;
- calibrate the Maxwell drive to 1000 W absorbed power at the 100 ns state;
- compute the same target-quadrature RF transfer scale used by the short A1 gate;
- recover from 100 ns and evolve EI02+EI16 to 15 us on the accepted staged time grid;
- keep the calibrated Maxwell field frozen during the 100 ns -> 15 us plasma evolution;
- solve Maxwell once at 15 us with the same fixed drive to quantify accumulated feedback.

The frozen-field choice makes this an exploratory long-horizon stability screen, not a
fully segregated long-time Maxwell/plasma acceptance claim. If the final Maxwell
feedback is large, the next step is staged Maxwell refresh rather than gate relaxation.
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
FINAL_TIME_S = 15.0e-6
FINAL_TIME_GATE_S = 1.0e-15
FEEDBACK_SCREEN_MAX = 5.0e-1


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--physics", required=True)
    p.add_argument("--plasma-input-100ns", type=Path, required=True)
    p.add_argument("--plasma-input-15us", type=Path, required=True)
    p.add_argument("--rf-plasma-overlay", type=Path, required=True)
    p.add_argument("--chemistry-overlay", type=Path, required=True)
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
        "gate": "A1 EI02+EI16 15 us frozen-field stability screen",
        "status": "ERROR",
        "failures": [],
    }

    try:
        physics = str(Path(a.physics).resolve())
        pin100 = str(a.plasma_input_100ns.resolve())
        pin15 = str(a.plasma_input_15us.resolve())
        rfov = str(a.rf_plasma_overlay.resolve())
        chemov = str(a.chemistry_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())
        tx, tm = base.table(a.transport_table)

        # Seed field only provides a valid RF-map object during the chemistry-OFF bootstrap.
        seed = out / "seed" / "maxwell"
        base.run([physics, "-i", minp, f"Outputs/file_base={seed}"], out / "seed" / "maxwell.log")
        seed_e = seed.with_suffix(".e")

        # 0 -> 100 ns: reproduce the common powered-chemistry starting state with
        # chemistry projections and RF heating disabled, while keeping topology identical.
        pbase = out / "bootstrap" / "plasma"
        common100 = [physics, "-i", pin100, rfov, chemov]
        base.run(
            common100
            + a1.chemistry_off_overrides()
            + [
                f"maxwell_solution_file_t6={seed_e}",
                "source_enable_t6=0",
                "rf_scale_t6=1",
                f"Outputs/file_base={pbase}",
            ],
            out / "bootstrap" / "run.log",
        )
        pe, pcsv = pbase.with_suffix(".e"), pbase.with_suffix(".csv")
        state100 = out / "bootstrap" / "state100ns.e"
        csv100 = out / "bootstrap" / "state100ns.csv"
        shutil.copy2(pe, state100)
        shutil.copy2(pcsv, csv100)

        active_cp = Path(str(pbase) + "_cp")
        checkpoint100 = out / "bootstrap" / "checkpoint100ns"
        if not active_cp.is_dir():
            raise RuntimeError("100 ns checkpoint missing")
        shutil.copytree(active_cp, checkpoint100)

        # Calibrate the same fixed coil drive used by T6-v2/A1 to 1000 W at 100 ns.
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

        # Reproduce the exact target-quadrature normalization used by A1.
        v2.restore_checkpoint(checkpoint100, active_cp)
        shutil.copy2(state100, pe)
        shutil.copy2(csv100, pcsv)
        base.run(
            common100
            + a1.chemistry_off_overrides()
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

        # 100 ns -> 15 us: EI02 + EI16 ON, RF heating ON, accepted staged time grid.
        # The Maxwell field is deliberately frozen at the calibrated 100 ns solution.
        v2.restore_checkpoint(checkpoint100, active_cp)
        shutil.copy2(state100, pe)
        shutil.copy2(csv100, pcsv)
        common15 = [physics, "-i", pin15, rfov, chemov]
        base.run(
            common15
            + [
                f"maxwell_solution_file_t6={m1e}",
                "source_enable_t6=1",
                f"rf_scale_t6={rf_scale:.17g}",
                f"Outputs/file_base={pbase}",
                "--recover",
            ],
            out / "A1_15us" / "plasma.log",
        )

        state15 = out / "A1_15us" / "state15us.e"
        csv15 = out / "A1_15us" / "state15us.csv"
        state15.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pe, state15)
        shutil.copy2(pcsv, csv15)
        c15 = base.csv_last(csv15)

        # Fixed-drive Maxwell feedback at the final chemistry-evolved state.
        mw15 = a1.maxwell_feedback(physics, minp, mov, state15, drive, out / "A1_15us_feedback")

        s100 = a1.state_fields(state100)
        s15 = a1.state_fields(state15)
        ex15 = base.exodus(state15)
        final_time = float(ex15["times"][-1])

        metrics = {
            "final_time_s": final_time,
            "target_power_error": base.rel(pabs1, TARGET_W),
            "raw_remesh_defect_at_100ns": base.rel(independent_raw, pabs1),
            "rf_deposition_scale": rf_scale,
            "final_rf_source_unit_closure": base.rel(
                c15["S_rf_eV_mol_s_t6"] * base.FARADAY,
                c15["P_rf_scaled_W_t6"],
            ),
            "final_rf_power_with_frozen_field_W": c15["P_rf_scaled_W_t6"],
            "final_fixed_drive_Maxwell_P_abs_W": mw15["P_abs"],
            "final_fixed_drive_power_feedback": base.rel(mw15["P_abs"], pabs1),
            "energy_response_100ns_to_15us": a1.rel_l2(s15["mean_en_eV"], s100["mean_en_eV"]),
            "electron_response_100ns_to_15us": a1.rel_l2(s15["ne_mol"], s100["ne_mol"]),
            "O2p_response_100ns_to_15us": a1.rel_l2(s15["o2p_mol"], s100["o2p_mol"]),
            "mean_energy_min_eV": float(np.min(s15["mean_en_eV"])),
            "mean_energy_max_eV": float(np.max(s15["mean_en_eV"])),
            "ne_min_mol_m3": float(np.min(s15["ne_mol"])),
            "O2p_min_mol_m3": float(np.min(s15["o2p_mol"])),
            "pressure_min_Pa": float(np.min(s15["p_Pa"])),
            "R_elastic_min": c15["a1_R_elastic_O2_min"],
            "R_elastic_max": c15["a1_R_elastic_O2_max"],
            "R_ion_min": c15["a1_R_ion_O2_min"],
            "R_ion_max": c15["a1_R_ion_O2_max"],
            "R_ion_integral_mol_s": c15["a1_R_ion_O2_integral"],
            "chem_energy_source_integral_eV_mol_s": c15["a1_energy_source_integral"],
            "heavy_mass_source_closure_kg_s": c15["a1_heavy_mass_closure_integral"],
            "charge_molar_source_closure_mol_s": c15["a1_charge_molar_closure_integral"],
        }

        failures: list[str] = []
        if abs(metrics["final_time_s"] - FINAL_TIME_S) > FINAL_TIME_GATE_S:
            failures.append("did not reach 15 us")
        if metrics["target_power_error"] > a1.TARGET_GATE:
            failures.append("1000 W calibration")
        if metrics["raw_remesh_defect_at_100ns"] > base.RAW_GATE:
            failures.append("RF remesh defect")
        if metrics["final_rf_source_unit_closure"] > base.SOURCE_UNIT_GATE:
            failures.append("final RF source-unit closure")
        if not finite_state(s15):
            failures.append("non-finite final plasma state")
        if not (
            a1.TABLE_LO
            <= metrics["mean_energy_min_eV"]
            <= metrics["mean_energy_max_eV"]
            <= a1.TABLE_HI
        ):
            failures.append("mean-energy lookup range")
        if metrics["ne_min_mol_m3"] <= 0 or metrics["O2p_min_mol_m3"] <= 0 or metrics["pressure_min_Pa"] <= 0:
            failures.append("final positivity")
        if metrics["R_elastic_max"] <= 0 or metrics["R_ion_max"] <= 0 or metrics["R_ion_integral_mol_s"] <= 0:
            failures.append("reaction progress not positive")
        if abs(metrics["heavy_mass_source_closure_kg_s"]) > a1.SOURCE_CLOSURE_GATE:
            failures.append("heavy-mass source closure")
        if abs(metrics["charge_molar_source_closure_mol_s"]) > a1.SOURCE_CLOSURE_GATE:
            failures.append("charge source closure")
        if metrics["energy_response_100ns_to_15us"] <= base.STATE_RESPONSE_MIN:
            failures.append("long-horizon energy response absent")
        if metrics["electron_response_100ns_to_15us"] <= base.STATE_RESPONSE_MIN:
            failures.append("long-horizon electron response absent")
        if metrics["O2p_response_100ns_to_15us"] <= base.STATE_RESPONSE_MIN:
            failures.append("long-horizon O2+ response absent")
        if metrics["final_fixed_drive_power_feedback"] >= FEEDBACK_SCREEN_MAX:
            failures.append("final Maxwell feedback exceeds frozen-field screen")

        report = {
            "issue": 395,
            "gate": "A1 EI02+EI16 15 us frozen-field stability screen",
            "status": "PASS" if not failures else "FAIL",
            "classification": (
                "ISSUE395_A1_15US_FROZEN_FIELD_SCREEN_PASS"
                if not failures
                else "ISSUE395_A1_15US_FROZEN_FIELD_SCREEN_FAIL"
            ),
            "scope": (
                "chemistry-OFF full-physics bootstrap to 100 ns; 1000 W Maxwell calibration at 100 ns; "
                "EI02+EI16 powered evolution from 100 ns to 15 us on the accepted staged time grid "
                "with the 100 ns Maxwell field frozen; final fixed-drive Maxwell feedback solve"
            ),
            "active_chemistry": ["EI02", "EI16"],
            "rf_field_policy": "frozen at calibrated 100 ns Maxwell solution during plasma evolution",
            "drive_policy": "fixed coil-current amplitude; no retuning after the 100 ns 1000 W calibration",
            "scientific_claim": "long-horizon stability screen only; not fully segregated long-time Maxwell/plasma acceptance",
            "custom_cpp_added": False,
            "standard_moose_source_projection": True,
            "drive_source_scale": drive,
            "effective_peak_coil_current_A": 10.0 * drive,
            "Maxwell_100ns_P_abs_W": pabs1,
            "state100ns": state100_stats,
            "metrics": metrics,
            "failures": failures,
        }
        report["status"] = "PASS" if not failures else "FAIL"
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
