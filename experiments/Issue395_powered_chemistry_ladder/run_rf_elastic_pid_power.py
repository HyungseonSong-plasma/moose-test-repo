#!/usr/bin/env python3
"""Issue #395 RF+EI02 elastic with minimal lagged power feedback.

No RF-off probe, throw-away plasma step, checkpoint snapshot, or rollback is used.
The accepted trajectory is strictly forward:

  accepted plasma state -> Maxwell solve -> one plasma production advance

The Maxwell source amplitude is calibrated once at t=0 and thereafter receives a
one-step-lag correction from the preceding Maxwell absorbed-power error.  The
standard-MOOSE PIDTransientControl in the plasma overlay handles the residual
target-grid power error on the following accepted timestep.
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

TARGET_W = 1000.0
POWER_GUARD = 2.0e-2
MAXWELL_POWER_GUARD = 1.0e-1
SOURCE_UNIT_GATE = 1.0e-8
FINAL_TIME_S = 1.10e-7
TIME_TOL = 5.0e-15
TABLE_LO = 1.40991
TABLE_HI = 22.1378


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--physics", required=True)
    p.add_argument("--plasma-input", type=Path, required=True)
    p.add_argument("--rf-plasma-overlay", type=Path, required=True)
    p.add_argument("--elastic-overlay", type=Path, required=True)
    p.add_argument("--maxwell-input", type=Path, required=True)
    p.add_argument("--maxwell-overlay", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    return p.parse_args()


def coupling_times():
    # Keep RF/Maxwell feedback cadence at 1 ns all the way through 110 ns.
    return [i * 1.0e-9 for i in range(0, 111)]


def state_fields(path: Path):
    st = base.exodus(path)
    nodes = np.unique(st["blocks"]["plasma"].reshape(-1))
    ln = st["nodal"]["log_ne"][-1][nodes]
    le = st["nodal"]["log_energy"][-1][nodes]
    return {
        "ne_mol": np.exp(ln),
        "mean_en_eV": np.exp(le - ln),
        "p_Pa": st["elem"]["plasma"]["p"][-1],
    }


def main() -> int:
    a = parse_args()
    out = a.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    analysis = a.analysis.resolve()
    report = {"issue": 395, "gate": "RF+EI02 elastic minimal lagged PID", "status": "ERROR"}

    try:
        physics = str(Path(a.physics).resolve())
        pin = str(a.plasma_input.resolve())
        rfov = str(a.rf_plasma_overlay.resolve())
        elasticov = str(a.elastic_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())

        rftxt = a.rf_plasma_overlay.read_text(encoding="utf-8")
        for token in ("type = PIDTransientControl", "parameter_pp = rf_pid_scale_t6", "postprocessor = P_rf_scaled_W_t6"):
            if token not in rftxt:
                raise RuntimeError(f"PID RF overlay missing {token}")
        if "rf_scale_t6" in rftxt:
            raise RuntimeError("legacy rf_scale_t6 remains in PID RF overlay")

        etxt = a.elastic_overlay.read_text(encoding="utf-8")
        for token in ("R_elastic_O2", "elastic_energy_source_EI02", "PhysicsElectronImpactRateMaterial"):
            if token not in etxt:
                raise RuntimeError(f"elastic overlay missing {token}")
        for token in ("R_diss_O2", "diss_energy", "12.62", "R_ion_O2"):
            if token in etxt:
                raise RuntimeError(f"forbidden chemistry present: {token}")

        # A seed Maxwell file is required only so the t=0 plasma input can map an
        # E-field while num_steps=0.  This does not advance the production state.
        seed = out / "seed" / "maxwell"
        base.run([physics, "-i", minp, f"Outputs/file_base={seed}"], out / "seed" / "run.log")
        seed_e = seed.with_suffix(".e")

        common = [physics, "-i", pin, rfov, elasticov]
        init = out / "initial" / "plasma"
        base.run(
            common
            + [
                f"maxwell_solution_file_t6={seed_e}",
                "source_enable_t6=0",
                "Executioner/num_steps=0",
                f"Outputs/file_base={init}",
            ],
            out / "initial" / "run.log",
        )
        current_state = init.with_suffix(".e")
        if not current_state.is_file():
            raise RuntimeError("t=0 state missing")

        times = coupling_times()
        pbase = out / "production" / "plasma"
        pe, pcsv = pbase.with_suffix(".e"), pbase.with_suffix(".csv")
        rows = []

        # One-time t=0 calibration.  This is the only extra Maxwell calibration
        # solve; there are no plasma probe/rollback solves anywhere in the run.
        cal = out / "calibration" / "maxwell_unit"
        base.run(
            [
                physics,
                "-i",
                minp,
                mov,
                f"plasma_solution_file_t6={current_state}",
                "source_scale=1",
                f"Outputs/file_base={cal}",
            ],
            out / "calibration" / "run.log",
        )
        p_unit = base.csv_last(cal.with_suffix(".csv"))["P_abs"]
        if p_unit <= 0:
            raise RuntimeError("nonpositive t0 unit-drive Maxwell power")
        source_scale = math.sqrt(TARGET_W / p_unit)

        for i, target in enumerate(times[1:], 1):
            sd = out / "coupling" / f"step_{i:03d}"
            sd.mkdir(parents=True, exist_ok=True)

            # Exactly one Maxwell solve for this accepted coupling step.
            mx = sd / "maxwell" / "maxwell"
            base.run(
                [
                    physics,
                    "-i",
                    minp,
                    mov,
                    f"plasma_solution_file_t6={current_state}",
                    f"source_scale={source_scale:.17g}",
                    f"Outputs/file_base={mx}",
                ],
                sd / "maxwell" / "run.log",
            )
            mx_e = mx.with_suffix(".e")
            pmax = base.csv_last(mx.with_suffix(".csv"))["P_abs"]
            if pmax <= 0 or not math.isfinite(pmax):
                raise RuntimeError(f"step {i}: invalid Maxwell absorbed power")

            # One accepted plasma advance.  No probe, no rollback, no retry.
            cmd = common + [
                f"maxwell_solution_file_t6={mx_e}",
                "source_enable_t6=1",
                f"Executioner/end_time={target:.17g}",
                f"Outputs/file_base={pbase}",
            ]
            if i > 1:
                cmd.append("--recover")
            base.run(cmd, sd / "production.log")

            c = base.csv_last(pcsv)
            s = state_fields(pe)
            prf = c["P_rf_scaled_W_t6"]
            perr = base.rel(prf, TARGET_W)
            maxwell_err = base.rel(pmax, TARGET_W)
            uerr = base.rel(c["S_rf_eV_mol_s_t6"] * base.FARADAY, prf)
            pid_scale = c.get("rf_pid_scale_t6")

            next_source_scale = source_scale * math.sqrt(TARGET_W / pmax)
            row = {
                "step": i,
                "time_s": target,
                "dt_s": target - times[i - 1],
                "Maxwell_absorbed_RF_W": pmax,
                "Maxwell_power_relative_error": maxwell_err,
                "Maxwell_source_scale": source_scale,
                "next_Maxwell_source_scale": next_source_scale,
                "effective_peak_coil_current_A": 10.0 * source_scale,
                "plasma_target_RF_W": prf,
                "plasma_target_power_relative_error": perr,
                "rf_pid_scale_t6": pid_scale,
                "mean_energy_min_eV": float(np.min(s["mean_en_eV"])),
                "mean_energy_max_eV": float(np.max(s["mean_en_eV"])),
                "elastic_R_max": c.get("elastic_R_max"),
                "elastic_R_integral": c.get("elastic_R_integral"),
                "elastic_delta_e_min_eV": c.get("elastic_delta_e_min"),
                "elastic_delta_e_max_eV": c.get("elastic_delta_e_max"),
                "elastic_energy_source_eV_mol_s": c.get("elastic_energy_source_integral"),
            }
            rows.append(row)
            (sd / "step.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            if perr > POWER_GUARD:
                raise RuntimeError(f"step {i}: target-grid RF power {prf} W outside 2% guardrail")
            if maxwell_err > MAXWELL_POWER_GUARD:
                raise RuntimeError(f"step {i}: Maxwell absorbed RF power {pmax} W outside 10% guardrail")
            if uerr > SOURCE_UNIT_GATE:
                raise RuntimeError(f"step {i}: RF unit closure")
            if not all(np.all(np.isfinite(v)) for v in s.values()):
                raise RuntimeError(f"step {i}: nonfinite plasma state")
            if np.min(s["ne_mol"]) <= 0 or np.min(s["p_Pa"]) <= 0:
                raise RuntimeError(f"step {i}: nonpositive plasma state")
            if (c.get("elastic_R_max") or 0) <= 0 or (c.get("elastic_R_integral") or 0) <= 0:
                raise RuntimeError(f"step {i}: elastic progress absent")
            if (c.get("elastic_delta_e_min") or 0) <= 0:
                raise RuntimeError(f"step {i}: elastic energy transfer not positive")
            if (c.get("elastic_energy_source_integral") or 0) >= 0:
                raise RuntimeError(f"step {i}: elastic term is not an electron-energy sink")

            # Lagged physical-drive correction for the next accepted timestep.
            source_scale = next_source_scale
            current_state = pe

        final = state_fields(pe)
        xt = np.asarray(base.exodus(pe)["times"], dtype=float)
        failures = []
        if abs(float(xt[-1]) - FINAL_TIME_S) > TIME_TOL:
            failures.append("did not reach 110 ns")
        if max(r["plasma_target_power_relative_error"] for r in rows) > POWER_GUARD:
            failures.append("target-grid 1000 W guardrail")
        if max(r["Maxwell_power_relative_error"] for r in rows) > MAXWELL_POWER_GUARD:
            failures.append("Maxwell 1000 W guardrail")
        emin = float(np.min(final["mean_en_eV"]))
        emax = float(np.max(final["mean_en_eV"]))
        if not (TABLE_LO <= emin <= emax <= TABLE_HI):
            failures.append("RF transport mean-energy range")

        report = {
            "issue": 395,
            "gate": "RF-ON + EI02 elastic with minimal lagged 1000 W feedback",
            "status": "PASS" if not failures else "FAIL",
            "classification": "ISSUE395_RF_ELASTIC_MINIMAL_PID_110NS_PASS" if not failures else "ISSUE395_RF_ELASTIC_MINIMAL_PID_110NS_FAIL",
            "production_start": "fresh t=0",
            "production_uses_100ns_restart": False,
            "rf_activation": "t=0",
            "elastic_activation": "t=0",
            "dissociation_active": False,
            "ionization_active": False,
            "probe_plasma_steps": 0,
            "rollback_steps": 0,
            "trial_step_iteration": False,
            "power_control": {
                "target_W": TARGET_W,
                "Maxwell_drive_feedback": "one-step lag: s_next=s*sqrt(1000/P_abs_Maxwell)",
                "plasma_residual_feedback": "MOOSE PIDTransientControl, accepted TIMESTEP_END -> following timestep",
                "K_proportional_per_W": -1.0e-3,
                "K_integral": 0.0,
                "K_derivative": 0.0,
                "pid_scale_bounds": [0.5, 1.5],
                "target_grid_guardrail_relative": POWER_GUARD,
                "Maxwell_guardrail_relative": MAXWELL_POWER_GUARD,
                "coupling_cadence_s": 1.0e-9,
            },
            "elastic": {
                "reaction": "e + O2 -> e + O2",
                "rate_table": "o2_elastic.txt",
                "energy_transfer_law": "3*m_e/m_O2*((2/3)*mean_en-kB*Tg/e)",
                "particle_source": 0,
                "heavy_species_source": 0,
            },
            "final": {
                "time_s": float(xt[-1]),
                "mean_energy_min_eV": emin,
                "mean_energy_max_eV": emax,
                "ne_min_mol_m3": float(np.min(final["ne_mol"])),
            },
            "steps": rows,
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
