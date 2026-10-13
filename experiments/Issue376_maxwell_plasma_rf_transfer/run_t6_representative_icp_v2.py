#!/usr/bin/env python3
"""Issue #376 T6-v2 representative oxygen ICP driver.

Fixes two T6-v1 failures without relaxing either gate:
1. the Maxwell overlay transfers physical electron density/mean energy before
   constitutive evaluation, avoiding nonlinear log-state remap bias;
2. RF deposition is normalized with the actual MOOSE target raw integral,
   while the independent reconstruction remains a discriminator only.

The first coupled Maxwell state is calibrated to 1000 W absorbed plasma power.
That calibrated coil-current amplitude is then held fixed for the feedback
Maxwell solve, so the second P_abs remains a genuine plasma-response metric.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np

import run_t6_representative_icp as base

TARGET_ABSORBED_POWER_W = 1000.0
TARGET_POWER_GATE = 1.0e-8


def restore_checkpoint(snapshot: Path, active: Path) -> None:
    if active.exists():
        shutil.rmtree(active)
    shutil.copytree(snapshot, active)


def main() -> int:
    a = base.args()
    out = a.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    analysis = a.analysis.resolve()
    report = {"issue": 376, "gate": "T6 representative full oxygen ICP v2", "status": "ERROR", "failures": []}

    try:
        physics = str(Path(a.physics).resolve())
        pin = str(a.plasma_input.resolve())
        pov = str(a.plasma_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())
        tx, tm = base.table(a.table)

        # Seed field is only needed while bootstrapping the RF-off plasma state.
        seed = out / "seed" / "maxwell"
        base.run([physics, "-i", minp, f"Outputs/file_base={seed}"], out / "seed" / "maxwell.log")
        seed_e = seed.with_suffix(".e")
        if not seed_e.is_file():
            raise RuntimeError("seed Maxwell Exodus missing")

        # Accepted full dielectric oxygen baseline through 100 ns, RF source off.
        pbase = out / "bootstrap" / "plasma"
        common_plasma = [physics, "-i", pin, pov]
        base.run(
            common_plasma
            + [
                f"maxwell_solution_file_t6={seed_e}",
                "source_enable_t6=0",
                "rf_scale_t6=1",
                f"Outputs/file_base={pbase}",
                "--check-input",
            ],
            out / "bootstrap" / "check.log",
        )
        base.run(
            common_plasma
            + [
                f"maxwell_solution_file_t6={seed_e}",
                "source_enable_t6=0",
                "rf_scale_t6=1",
                f"Outputs/file_base={pbase}",
            ],
            out / "bootstrap" / "run.log",
        )
        pe = pbase.with_suffix(".e")
        pcsv = pbase.with_suffix(".csv")
        if not pe.is_file() or not pcsv.is_file():
            raise RuntimeError("bootstrap plasma output missing")
        state100 = out / "bootstrap" / "state100ns.e"
        csv100 = out / "bootstrap" / "state100ns.csv"
        shutil.copy2(pe, state100)
        shutil.copy2(pcsv, csv100)

        # Save the exact 100 ns restart state because the target-quadrature probe
        # and the accepted source-on step must start from the identical state.
        active_cp = Path(str(pbase) + "_cp")
        checkpoint100 = out / "bootstrap" / "checkpoint100ns"
        if not active_cp.is_dir():
            raise RuntimeError(f"bootstrap checkpoint missing: {active_cp}")
        shutil.copytree(active_cp, checkpoint100)

        # Probe once at the original 10 A peak coil current, then exploit the
        # linear Maxwell solve (P_abs proportional to source_scale^2) to set the
        # first coupled field to exactly 1000 W absorbed plasma power.
        m1_probe = out / "maxwell1_probe" / "maxwell"
        base.run(
            [physics, "-i", minp, mov, f"plasma_solution_file_t6={state100}", "source_scale=1", f"Outputs/file_base={m1_probe}"],
            out / "maxwell1_probe" / "run.log",
        )
        pabs_probe = base.csv_last(m1_probe.with_suffix(".csv"))["P_abs"]
        if pabs_probe <= 0:
            raise RuntimeError("non-positive Maxwell probe power")
        drive_scale = math.sqrt(TARGET_ABSORBED_POWER_W / pabs_probe)

        m1 = out / "maxwell1" / "maxwell"
        m1_cmd = [
            physics,
            "-i",
            minp,
            mov,
            f"plasma_solution_file_t6={state100}",
            f"source_scale={drive_scale:.17g}",
            f"Outputs/file_base={m1}",
        ]
        base.run(m1_cmd + ["--check-input"], out / "maxwell1" / "check.log")
        base.run(m1_cmd, out / "maxwell1" / "run.log")
        m1e = m1.with_suffix(".e")
        m1csv = m1.with_suffix(".csv")
        pabs1 = base.csv_last(m1csv)["P_abs"]
        independent_raw, state_stats = base.mapped_raw_power(state100, m1e, tx, tm)
        if not (independent_raw > 0 and pabs1 > 0):
            raise RuntimeError("non-positive T6 RF power")

        # Probe the actual deposition discretization with source disabled. This
        # is the normalization owner. The independent integral above remains the
        # remesh-fidelity oracle and is deliberately NOT used as the scale owner.
        restore_checkpoint(checkpoint100, active_cp)
        shutil.copy2(state100, pe)
        shutil.copy2(csv100, pcsv)
        base.run(
            common_plasma
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
        praw_probe = base.csv_last(pcsv)["P_rf_raw_W_t6"]
        if praw_probe <= 0:
            raise RuntimeError("non-positive MOOSE target raw RF power")
        deposition_scale = pabs1 / praw_probe

        (out / "scale.json").write_text(
            json.dumps(
                {
                    "target_absorbed_power_W": TARGET_ABSORBED_POWER_W,
                    "Maxwell_probe_P_abs_W": pabs_probe,
                    "drive_source_scale": drive_scale,
                    "effective_peak_coil_current_A": 10.0 * drive_scale,
                    "Maxwell_P_abs_W": pabs1,
                    "target_power_relative_error": base.rel(pabs1, TARGET_ABSORBED_POWER_W),
                    "independent_target_raw_W": independent_raw,
                    "raw_relative_defect": base.rel(independent_raw, pabs1),
                    "MOOSE_target_raw_probe_W": praw_probe,
                    "rf_deposition_scale": deposition_scale,
                    "state": state_stats,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        # Restore the exact 100 ns state and perform the accepted 1000 W source
        # deposition step with target-quadrature power normalization.
        restore_checkpoint(checkpoint100, active_cp)
        shutil.copy2(state100, pe)
        shutil.copy2(csv100, pcsv)
        base.run(
            common_plasma
            + [
                f"maxwell_solution_file_t6={m1e}",
                "source_enable_t6=1",
                f"rf_scale_t6={deposition_scale:.17g}",
                "Executioner/end_time=1.01e-7",
                "Executioner/num_steps=101",
                f"Outputs/file_base={pbase}",
                "--recover",
            ],
            out / "source_on_recover.log",
        )
        state101 = out / "state101ns.e"
        csv101 = out / "state101ns.csv"
        shutil.copy2(pe, state101)
        shutil.copy2(pcsv, csv101)

        # Fixed-drive feedback: do not retune to 1000 W here. A changed P_abs is
        # evidence that the updated plasma state actually feeds back to Maxwell.
        m2 = out / "maxwell2" / "maxwell"
        base.run(
            [physics, "-i", minp, mov, f"plasma_solution_file_t6={state101}", f"source_scale={drive_scale:.17g}", f"Outputs/file_base={m2}"],
            out / "maxwell2" / "run.log",
        )
        m2csv = m2.with_suffix(".csv")

        c1 = base.csv_last(m1csv)
        c2 = base.csv_last(m2csv)
        pf = base.csv_last(csv101)
        pabs2 = c2["P_abs"]
        pscaled = pf["P_rf_scaled_W_t6"]
        praw_actual = pf["P_rf_raw_W_t6"]
        source_evmol = pf["S_rf_eV_mol_s_t6"]

        st0 = base.exodus(state100)
        st1 = base.exodus(state101)
        e0 = np.exp(st0["nodal"]["log_energy"][-1] - st0["nodal"]["log_ne"][-1])
        e1 = np.exp(st1["nodal"]["log_energy"][-1] - st1["nodal"]["log_ne"][-1])
        energy_response = float(np.linalg.norm(e1 - e0) / max(np.linalg.norm(e0), 1e-300))
        field1 = math.hypot(c1["E_real_l2"], c1["E_imag_l2"])
        field2 = math.hypot(c2["E_real_l2"], c2["E_imag_l2"])

        target_power_error = base.rel(pabs1, TARGET_ABSORBED_POWER_W)
        raw_defect = base.rel(independent_raw, pabs1)
        raw_probe_repro = base.rel(praw_actual, praw_probe)
        closure = base.rel(pscaled, pabs1)
        source_unit = base.rel(source_evmol * base.FARADAY, pscaled)
        power_feedback = base.rel(pabs2, pabs1)
        field_feedback = base.rel(field2, field1)

        required_nodal = {"log_ne", "log_energy", "potential"}
        required_elem = {"log_ni", "log_nm", "log_nop", "p", "w_O", "w_O2s", "w_Os"}
        nodal_ok = required_nodal.issubset(st1["nodal"])
        elem_ok = required_elem.issubset(st1["elem"].get("plasma", {}))
        finite_positive = bool(np.all(np.isfinite(e1)) and np.all(e1 > 0) and np.all(np.isfinite(st1["nodal"]["log_ne"][-1])))
        input_text = a.plasma_input.read_text(encoding="utf-8")
        overlay_text = a.plasma_overlay.read_text(encoding="utf-8")
        dielectric_tokens = ["eps_cover", "eps_wafer", "eps_focus_ring", "eps_vacuum", "sigma_s", "sigma_wafer", "sigma_focus_ring", "PhysicsADSurfaceChargePoissonBC"]
        dielectric_ok = all(t in input_text for t in dielectric_tokens)
        separate_owners = "PhysicsFEMLogMolarElectronJouleHeating" in input_text and overlay_text.count("material_property = q_rf_eV_mol_t6") == 1
        physical_mapping = "electron_density_state_t6" in a.maxwell_overlay.read_text(encoding="utf-8") and "electron_density_rf_state_t6" in overlay_text

        failures: list[str] = []
        if target_power_error > TARGET_POWER_GATE:
            failures.append(f"1000 W Maxwell calibration error {target_power_error:.6e} > {TARGET_POWER_GATE:.6e}")
        if raw_defect > base.RAW_GATE:
            failures.append(f"raw remesh power defect {raw_defect:.6e} > {base.RAW_GATE:.6e}")
        if raw_probe_repro > base.POWER_GATE:
            failures.append(f"MOOSE raw-power probe reproducibility {raw_probe_repro:.6e} > {base.POWER_GATE:.6e}")
        if closure > base.POWER_GATE:
            failures.append(f"deposited RF power closure {closure:.6e} > {base.POWER_GATE:.6e}")
        if source_unit > base.SOURCE_UNIT_GATE:
            failures.append(f"RF source unit closure {source_unit:.6e} > {base.SOURCE_UNIT_GATE:.6e}")
        if state_stats["sigma_real_cv"] < base.SIGMA_CV_MIN:
            failures.append(f"spatial sigma CV {state_stats['sigma_real_cv']:.6e} < {base.SIGMA_CV_MIN:.6e}")
        if state_stats["table_clamp_fraction"] > base.MAX_TABLE_CLAMP_FRACTION:
            failures.append(f"transport-table clamp fraction {state_stats['table_clamp_fraction']:.6e} > {base.MAX_TABLE_CLAMP_FRACTION:.6e}")
        if not (base.FEEDBACK_MIN < power_feedback < base.FEEDBACK_MAX):
            failures.append(f"Maxwell power feedback response {power_feedback:.6e} outside ({base.FEEDBACK_MIN:.6e},{base.FEEDBACK_MAX:.6e})")
        if field_feedback <= base.FEEDBACK_MIN:
            failures.append(f"Maxwell field did not respond: {field_feedback:.6e}")
        if energy_response <= base.STATE_RESPONSE_MIN:
            failures.append(f"electron-energy state did not respond: {energy_response:.6e}")
        if not nodal_ok:
            failures.append("required FEM plasma variables missing")
        if not elem_ok:
            failures.append("required oxygen/FV plasma variables missing")
        if not finite_positive:
            failures.append("non-finite/non-positive electron state")
        if not dielectric_ok:
            failures.append("full dielectric/surface-charge contract missing")
        if not separate_owners:
            failures.append("RF/electrostatic electron-heating ownership is not separated")
        if not physical_mapping:
            failures.append("physical-state Maxwell mapping contract missing")

        report = {
            "issue": 376,
            "gate": "T6 representative full oxygen ICP v2",
            "status": "PASS" if not failures else "FAIL",
            "scope": "100 ns full dielectric oxygen-plasma bootstrap; physical ne/mean-energy transfer to frequency-domain Maxwell; first Maxwell state calibrated to 1000 W absorbed power; target-quadrature conservative RF deposition for one 1 ns full-physics step; fixed-drive Maxwell feedback.",
            "standard_moose_only": True,
            "custom_cpp_added": False,
            "state100ns": state_stats,
            "rf_transfer": {
                "target_absorbed_power_W": TARGET_ABSORBED_POWER_W,
                "Maxwell_probe_P_abs_W": pabs_probe,
                "drive_source_scale": drive_scale,
                "effective_peak_coil_current_A": 10.0 * drive_scale,
                "Maxwell_P_abs_W": pabs1,
                "target_power_relative_error": target_power_error,
                "independent_target_raw_W": independent_raw,
                "raw_relative_defect": raw_defect,
                "MOOSE_target_raw_probe_W": praw_probe,
                "MOOSE_target_raw_W": praw_actual,
                "MOOSE_raw_probe_reproducibility": raw_probe_repro,
                "rf_deposition_scale": deposition_scale,
                "MOOSE_target_scaled_W": pscaled,
                "deposited_relative_closure": closure,
                "source_eV_mol_s": source_evmol,
                "source_unit_relative_closure": source_unit,
            },
            "feedback": {
                "Maxwell1_P_abs_W": pabs1,
                "Maxwell2_P_abs_W": pabs2,
                "power_relative_change": power_feedback,
                "Maxwell1_field_l2": field1,
                "Maxwell2_field_l2": field2,
                "field_relative_change": field_feedback,
                "electron_mean_energy_field_relative_change": energy_response,
            },
            "full_physics": {
                "required_nodal_variables_present": nodal_ok,
                "required_oxygen_FV_variables_present": elem_ok,
                "electron_state_finite_positive": finite_positive,
                "dielectric_surface_charge_contract_present": dielectric_ok,
                "RF_and_electrostatic_heating_separate": separate_owners,
                "physical_state_mapping": physical_mapping,
            },
            "tolerances": {
                "target_power_relative": TARGET_POWER_GATE,
                "raw_mapping_relative": base.RAW_GATE,
                "power_relative": base.POWER_GATE,
                "source_unit_relative": base.SOURCE_UNIT_GATE,
                "sigma_cv_min": base.SIGMA_CV_MIN,
                "feedback_min": base.FEEDBACK_MIN,
                "feedback_max": base.FEEDBACK_MAX,
                "state_response_min": base.STATE_RESPONSE_MIN,
                "max_table_clamp_fraction": base.MAX_TABLE_CLAMP_FRACTION,
            },
            "failures": failures,
        }
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("T6_REPRESENTATIVE_ICP_V2_" + report["status"])
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not failures else 1

    except Exception as exc:
        report["status"] = "ERROR"
        report["failures"] = [f"runtime: {exc}"]
        report["exception"] = repr(exc)
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"T6_REPRESENTATIVE_ICP_V2_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
