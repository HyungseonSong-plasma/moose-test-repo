#!/usr/bin/env python3
"""Issue #395 A0/A1 powered chemistry discriminator.

A0 is the merged #376 chemistry-off powered baseline. A1 starts from the exact
same 100 ns checkpoint and enables only EI02 + EI16 for one 1 ns RF-heated step.
The chemistry overlay is present in both branches so restart/output topology is
identical; A0 disables only the chemistry source projections.
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

TARGET_W = 1000.0
TARGET_GATE = 1.0e-8
SOURCE_CLOSURE_GATE = 1.0e-10
TABLE_LO = 1.40991
TABLE_HI = 22.1378


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--physics", required=True)
    p.add_argument("--plasma-input", type=Path, required=True)
    p.add_argument("--rf-plasma-overlay", type=Path, required=True)
    p.add_argument("--chemistry-overlay", type=Path, required=True)
    p.add_argument("--maxwell-input", type=Path, required=True)
    p.add_argument("--maxwell-overlay", type=Path, required=True)
    p.add_argument("--transport-table", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    return p.parse_args()


def rel_l2(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-300))


def chemistry_off_overrides() -> list[str]:
    """Keep A1 owners/diagnostics instantiated while zeroing all A1 projections."""
    return [
        "FunctorMaterials/a1_electron_source/expression=0",
        "FunctorMaterials/a1_o2p_source/expression=0",
        "FunctorMaterials/a1_neutral_mass_source/expression=0",
        "FunctorMaterials/a1_o2p_mass_source/expression=0",
        "FunctorMaterials/a1_energy_source/expression=0",
    ]


def state_fields(path: Path) -> dict[str, np.ndarray]:
    st = base.exodus(path)
    ne = np.exp(st["nodal"]["log_ne"][-1])
    eps = np.exp(st["nodal"]["log_energy"][-1] - st["nodal"]["log_ne"][-1])
    ni = np.exp(st["elem"]["plasma"]["log_ni"][-1])
    p = st["elem"]["plasma"]["p"][-1]
    return {"ne_mol": ne, "mean_en_eV": eps, "o2p_mol": ni, "p_Pa": p}


def maxwell_feedback(physics: str, minp: str, mov: str, state: Path, drive: float, out: Path) -> dict[str, float]:
    fb = out / "maxwell"
    base.run(
        [physics, "-i", minp, mov, f"plasma_solution_file_t6={state}", f"source_scale={drive:.17g}", f"Outputs/file_base={fb}"],
        out / "maxwell.log",
    )
    return base.csv_last(fb.with_suffix(".csv"))


def main() -> int:
    a = args()
    out = a.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    analysis = a.analysis.resolve()
    report: dict = {"issue": 395, "gate": "A0/A1 powered EI02+EI16", "status": "ERROR", "failures": []}

    try:
        physics = str(Path(a.physics).resolve())
        pin = str(a.plasma_input.resolve())
        rfov = str(a.rf_plasma_overlay.resolve())
        chemov = str(a.chemistry_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())
        tx, tm = base.table(a.transport_table)

        # Keep one fixed object/output topology from bootstrap through A0/A1.
        # Chemistry rate owners and diagnostics exist throughout, while the A1
        # source projections are identically zero during bootstrap/A0.
        seed = out / "seed" / "maxwell"
        base.run([physics, "-i", minp, f"Outputs/file_base={seed}"], out / "seed" / "maxwell.log")
        seed_e = seed.with_suffix(".e")

        pbase = out / "bootstrap" / "plasma"
        common = [physics, "-i", pin, rfov, chemov]
        base.run(
            common
            + chemistry_off_overrides()
            + [f"maxwell_solution_file_t6={seed_e}", "source_enable_t6=0", "rf_scale_t6=1", f"Outputs/file_base={pbase}"],
            out / "bootstrap" / "run.log",
        )
        pe, pcsv = pbase.with_suffix(".e"), pbase.with_suffix(".csv")
        state100, csv100 = out / "bootstrap" / "state100ns.e", out / "bootstrap" / "state100ns.csv"
        shutil.copy2(pe, state100)
        shutil.copy2(pcsv, csv100)
        active_cp = Path(str(pbase) + "_cp")
        checkpoint100 = out / "bootstrap" / "checkpoint100ns"
        if not active_cp.is_dir():
            raise RuntimeError("100 ns checkpoint missing")
        shutil.copytree(active_cp, checkpoint100)

        # Calibrate the same fixed coil-current amplitude to 1000 W at the common initial state.
        probe = out / "maxwell_probe" / "maxwell"
        base.run(
            [physics, "-i", minp, mov, f"plasma_solution_file_t6={state100}", "source_scale=1", f"Outputs/file_base={probe}"],
            out / "maxwell_probe" / "run.log",
        )
        pprobe = base.csv_last(probe.with_suffix(".csv"))["P_abs"]
        drive = math.sqrt(TARGET_W / pprobe)
        m1 = out / "maxwell1" / "maxwell"
        base.run(
            [physics, "-i", minp, mov, f"plasma_solution_file_t6={state100}", f"source_scale={drive:.17g}", f"Outputs/file_base={m1}"],
            out / "maxwell1" / "run.log",
        )
        m1e = m1.with_suffix(".e")
        m1c = base.csv_last(m1.with_suffix(".csv"))
        pabs1 = m1c["P_abs"]
        independent_raw, state_stats = base.mapped_raw_power(state100, m1e, tx, tm)

        # Probe the actual target quadrature once. Both branches use the same deposition scale.
        v2.restore_checkpoint(checkpoint100, active_cp)
        shutil.copy2(state100, pe)
        shutil.copy2(csv100, pcsv)
        base.run(
            common
            + chemistry_off_overrides()
            + [
                f"maxwell_solution_file_t6={m1e}", "source_enable_t6=0", "rf_scale_t6=1",
                "Executioner/end_time=1.01e-7", "Executioner/num_steps=101", f"Outputs/file_base={pbase}", "--recover"
            ],
            out / "target_raw_probe.log",
        )
        praw = base.csv_last(pcsv)["P_rf_raw_W_t6"]
        rf_scale = pabs1 / praw

        def run_branch(name: str, chemistry: bool) -> tuple[Path, dict[str, float]]:
            v2.restore_checkpoint(checkpoint100, active_cp)
            shutil.copy2(state100, pe)
            shutil.copy2(csv100, pcsv)
            cmd = list(common)
            if not chemistry:
                cmd += chemistry_off_overrides()
            cmd += [
                f"maxwell_solution_file_t6={m1e}", "source_enable_t6=1", f"rf_scale_t6={rf_scale:.17g}",
                "Executioner/end_time=1.01e-7", "Executioner/num_steps=101", f"Outputs/file_base={pbase}", "--recover"
            ]
            base.run(cmd, out / name / "plasma.log")
            state = out / name / "state101ns.e"
            csv = out / name / "state101ns.csv"
            state.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pe, state)
            shutil.copy2(pcsv, csv)
            return state, base.csv_last(csv)

        state_a0, c_a0 = run_branch("A0", False)
        state_a1, c_a1 = run_branch("A1", True)

        mw_a0 = maxwell_feedback(physics, minp, mov, state_a0, drive, out / "A0_feedback")
        mw_a1 = maxwell_feedback(physics, minp, mov, state_a1, drive, out / "A1_feedback")

        s100 = state_fields(state100)
        s0 = state_fields(state_a0)
        s1 = state_fields(state_a1)

        metrics = {
            "target_power_error": base.rel(pabs1, TARGET_W),
            "raw_remesh_defect": base.rel(independent_raw, pabs1),
            "A0_rf_power_closure": base.rel(c_a0["P_rf_scaled_W_t6"], pabs1),
            "A1_rf_power_closure": base.rel(c_a1["P_rf_scaled_W_t6"], pabs1),
            "A0_rf_source_unit_closure": base.rel(c_a0["S_rf_eV_mol_s_t6"] * base.FARADAY, c_a0["P_rf_scaled_W_t6"]),
            "A1_rf_source_unit_closure": base.rel(c_a1["S_rf_eV_mol_s_t6"] * base.FARADAY, c_a1["P_rf_scaled_W_t6"]),
            "A0_energy_response": rel_l2(s0["mean_en_eV"], s100["mean_en_eV"]),
            "A1_energy_response": rel_l2(s1["mean_en_eV"], s100["mean_en_eV"]),
            "A1_vs_A0_energy_effect": rel_l2(s1["mean_en_eV"], s0["mean_en_eV"]),
            "A1_vs_A0_electron_effect": rel_l2(s1["ne_mol"], s0["ne_mol"]),
            "A1_vs_A0_O2p_effect": rel_l2(s1["o2p_mol"], s0["o2p_mol"]),
            "A0_fixed_drive_power_feedback": base.rel(mw_a0["P_abs"], pabs1),
            "A1_fixed_drive_power_feedback": base.rel(mw_a1["P_abs"], pabs1),
            "A1_vs_A0_feedback_power_effect": base.rel(mw_a1["P_abs"], mw_a0["P_abs"]),
            "A1_mean_energy_min_eV": float(np.min(s1["mean_en_eV"])),
            "A1_mean_energy_max_eV": float(np.max(s1["mean_en_eV"])),
            "A1_ne_min_mol_m3": float(np.min(s1["ne_mol"])),
            "A1_O2p_min_mol_m3": float(np.min(s1["o2p_mol"])),
            "A0_chem_energy_source_integral_eV_mol_s": c_a0["a1_energy_source_integral"],
            "R_elastic_min": c_a1["a1_R_elastic_O2_min"],
            "R_elastic_max": c_a1["a1_R_elastic_O2_max"],
            "R_ion_min": c_a1["a1_R_ion_O2_min"],
            "R_ion_max": c_a1["a1_R_ion_O2_max"],
            "R_ion_integral_mol_s": c_a1["a1_R_ion_O2_integral"],
            "chem_energy_source_integral_eV_mol_s": c_a1["a1_energy_source_integral"],
            "heavy_mass_source_closure_kg_s": c_a1["a1_heavy_mass_closure_integral"],
            "charge_molar_source_closure_mol_s": c_a1["a1_charge_molar_closure_integral"],
        }

        failures: list[str] = []
        if metrics["target_power_error"] > TARGET_GATE:
            failures.append("1000 W calibration")
        if metrics["raw_remesh_defect"] > base.RAW_GATE:
            failures.append("RF remesh defect")
        for key in ("A0_rf_power_closure", "A1_rf_power_closure"):
            if metrics[key] > base.POWER_GATE:
                failures.append(key)
        for key in ("A0_rf_source_unit_closure", "A1_rf_source_unit_closure"):
            if metrics[key] > base.SOURCE_UNIT_GATE:
                failures.append(key)
        if abs(metrics["A0_chem_energy_source_integral_eV_mol_s"]) > SOURCE_CLOSURE_GATE:
            failures.append("A0 chemistry projection not zero")
        if metrics["R_elastic_max"] <= 0 or metrics["R_ion_max"] <= 0 or metrics["R_ion_integral_mol_s"] <= 0:
            failures.append("A1 reaction progress not positive")
        if abs(metrics["heavy_mass_source_closure_kg_s"]) > SOURCE_CLOSURE_GATE:
            failures.append("A1 heavy-mass source closure")
        if abs(metrics["charge_molar_source_closure_mol_s"]) > SOURCE_CLOSURE_GATE:
            failures.append("A1 charge source closure")
        if not (TABLE_LO <= metrics["A1_mean_energy_min_eV"] <= metrics["A1_mean_energy_max_eV"] <= TABLE_HI):
            failures.append("A1 mean-energy lookup range")
        if metrics["A1_ne_min_mol_m3"] <= 0 or metrics["A1_O2p_min_mol_m3"] <= 0:
            failures.append("A1 positivity")
        if metrics["A0_energy_response"] <= base.STATE_RESPONSE_MIN:
            failures.append("A0 powered response absent")
        if metrics["A1_energy_response"] <= base.STATE_RESPONSE_MIN:
            failures.append("A1 powered response absent")
        if metrics["A1_vs_A0_electron_effect"] <= 1e-12 or metrics["A1_vs_A0_O2p_effect"] <= 1e-12:
            failures.append("A1 chemistry particle response absent")
        if not (base.FEEDBACK_MIN < metrics["A0_fixed_drive_power_feedback"] < base.FEEDBACK_MAX):
            failures.append("A0 Maxwell feedback")
        if not (base.FEEDBACK_MIN < metrics["A1_fixed_drive_power_feedback"] < base.FEEDBACK_MAX):
            failures.append("A1 Maxwell feedback")

        report = {
            "issue": 395,
            "gate": "A0/A1 powered EI02+EI16",
            "status": "PASS" if not failures else "FAIL",
            "classification": "ISSUE395_A1_POWERED_EI02_EI16_PASS" if not failures else "ISSUE395_A1_POWERED_EI02_EI16_FAIL",
            "scope": "common 100 ns checkpoint and chemistry-overlay/output topology; A0 chemistry projections OFF; A1 enables only EI02+EI16 projections for the same 1 ns RF-heated step",
            "active_chemistry_A1": ["EI02", "EI16"],
            "A0_chemistry_projection_enabled": False,
            "A1_chemistry_projection_enabled": True,
            "custom_cpp_added": False,
            "standard_moose_source_projection": True,
            "drive_source_scale": drive,
            "effective_peak_coil_current_A": 10.0 * drive,
            "Maxwell1_P_abs_W": pabs1,
            "rf_deposition_scale": rf_scale,
            "state100ns": state_stats,
            "A0_feedback_P_abs_W": mw_a0["P_abs"],
            "A1_feedback_P_abs_W": mw_a1["P_abs"],
            "metrics": metrics,
            "failures": failures,
        }
    except Exception as exc:
        report["status"] = "ERROR"
        report["failures"] = [str(exc)]

    analysis.parent.mkdir(parents=True, exist_ok=True)
    analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
