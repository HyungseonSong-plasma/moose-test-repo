#!/usr/bin/env python3
"""Issue #395 RF-ON + O2 dissociation with 1000 W plasma-absorbed-power control.

Production semantics:
- fresh production trajectory starts at t=0 (no 100 ns restart);
- source-backed O2 dissociation is active from t=0;
- RF heating is active from t=0;
- at every accepted plasma timestep, the Maxwell source amplitude is recalibrated
  so the RF power deposited on the plasma target discretization is 1000 W;
- the calibration probe starts from the exact same checkpoint as the accepted
  production step and is discarded;
- no chemistry-free state is used to initialize production.

The power-control owner is the actual MOOSE target-grid raw RF integral,
P_rf_raw_W_t6, not the Maxwell-mesh P_abs diagnostic.  For fixed plasma state the
frequency-domain Maxwell problem is linear in source amplitude and RF deposition
is quadratic, therefore

    source_scale = sqrt(1000 W / P_rf_raw(unit-drive))

sets the subsequent accepted step to 1000 W absorbed by the plasma.
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
POWER_GATE = 1.0e-8
SOURCE_UNIT_GATE = 1.0e-8
FINAL_TIME_S = 1.10e-7
TIME_TOL = 5.0e-15
TABLE_LO = 1.40991
TABLE_HI = 22.1378
SOURCE_CLOSURE_GATE = 1.0e-10


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--physics", required=True)
    p.add_argument("--plasma-input", type=Path, required=True)
    p.add_argument("--rf-plasma-overlay", type=Path, required=True)
    p.add_argument("--dissociation-overlay", type=Path, required=True)
    p.add_argument("--maxwell-input", type=Path, required=True)
    p.add_argument("--maxwell-overlay", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    return p.parse_args()


def accepted_times() -> list[float]:
    times = [0.0]
    times.extend(i * 1.0e-9 for i in range(1, 101))
    times.append(1.10e-7)
    return times


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


def finite_state(s: dict[str, np.ndarray]) -> bool:
    return all(np.all(np.isfinite(v)) for v in s.values())


def copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise RuntimeError(f"required file missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def snapshot_restart(pbase: Path, dst: Path) -> None:
    active_cp = Path(str(pbase) + "_cp")
    if not active_cp.is_dir():
        raise RuntimeError(f"active checkpoint missing: {active_cp}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(active_cp, dst)
    copy_file(pbase.with_suffix(".e"), dst.parent / "accepted_state.e")
    copy_file(pbase.with_suffix(".csv"), dst.parent / "accepted_state.csv")


def restore_restart(pbase: Path, snapshot: Path) -> None:
    active_cp = Path(str(pbase) + "_cp")
    v2.restore_checkpoint(snapshot, active_cp)
    copy_file(snapshot.parent / "accepted_state.e", pbase.with_suffix(".e"))
    copy_file(snapshot.parent / "accepted_state.csv", pbase.with_suffix(".csv"))


def main() -> int:
    a = args()
    out = a.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    analysis = a.analysis.resolve()
    report: dict = {
        "issue": 395,
        "gate": "RF-ON + O2 dissociation with 1000 W plasma absorbed-power control",
        "status": "ERROR",
        "failures": [],
    }

    try:
        physics = str(Path(a.physics).resolve())
        pin = str(a.plasma_input.resolve())
        rfov = str(a.rf_plasma_overlay.resolve())
        dissov = str(a.dissociation_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())

        seed = out / "seed" / "maxwell"
        base.run(
            [physics, "-i", minp, f"Outputs/file_base={seed}"],
            out / "seed" / "maxwell.log",
        )
        seed_e = seed.with_suffix(".e")
        if not seed_e.is_file():
            raise RuntimeError("seed Maxwell Exodus missing")

        common = [physics, "-i", pin, rfov, dissov]

        init_base = out / "initial_state" / "plasma"
        base.run(
            common
            + [
                f"maxwell_solution_file_t6={seed_e}",
                "source_enable_t6=0",
                "rf_scale_t6=1",
                "Executioner/num_steps=0",
                "Executioner/end_time=0",
                f"Outputs/file_base={init_base}",
            ],
            out / "initial_state" / "run.log",
        )
        init_e = init_base.with_suffix(".e")
        if not init_e.is_file():
            raise RuntimeError("zero-step t=0 plasma Exodus missing")

        pbase = out / "production" / "plasma"
        pe = pbase.with_suffix(".e")
        pcsv = pbase.with_suffix(".csv")
        times = accepted_times()
        step_rows: list[dict] = []
        current_state = init_e

        for step_idx, target_time in enumerate(times[1:], start=1):
            step_dir = out / "coupling" / f"step_{step_idx:03d}"
            step_dir.mkdir(parents=True, exist_ok=True)

            munit = step_dir / "maxwell_unit" / "maxwell"
            base.run(
                [
                    physics,
                    "-i",
                    minp,
                    mov,
                    f"plasma_solution_file_t6={current_state}",
                    "source_scale=1",
                    f"Outputs/file_base={munit}",
                ],
                step_dir / "maxwell_unit" / "run.log",
            )
            munit_e = munit.with_suffix(".e")
            maxwell_unit_power = base.csv_last(munit.with_suffix(".csv"))["P_abs"]
            if maxwell_unit_power <= 0.0:
                raise RuntimeError(f"step {step_idx}: non-positive unit-drive Maxwell power")

            snapshot = step_dir / "accepted_before_probe" / "checkpoint"
            if step_idx > 1:
                snapshot_restart(pbase, snapshot)

            probe_cmd = list(common)
            probe_cmd += [
                f"maxwell_solution_file_t6={munit_e}",
                "source_enable_t6=0",
                "rf_scale_t6=1",
                f"Executioner/end_time={target_time:.17g}",
                f"Outputs/file_base={pbase}",
            ]
            if step_idx > 1:
                probe_cmd.append("--recover")

            base.run(probe_cmd, step_dir / "raw_power_probe.log")
            probe = base.csv_last(pcsv)
            praw_unit = probe["P_rf_raw_W_t6"]
            if praw_unit <= 0.0:
                raise RuntimeError(f"step {step_idx}: non-positive target-grid unit-drive RF power")

            drive_scale = math.sqrt(TARGET_W / praw_unit)

            mtarget = step_dir / "maxwell_1000w" / "maxwell"
            base.run(
                [
                    physics,
                    "-i",
                    minp,
                    mov,
                    f"plasma_solution_file_t6={current_state}",
                    f"source_scale={drive_scale:.17g}",
                    f"Outputs/file_base={mtarget}",
                ],
                step_dir / "maxwell_1000w" / "run.log",
            )
            mtarget_e = mtarget.with_suffix(".e")
            maxwell_target_power = base.csv_last(mtarget.with_suffix(".csv"))["P_abs"]

            if step_idx > 1:
                restore_restart(pbase, snapshot)
            else:
                if pe.exists():
                    pe.unlink()
                if pcsv.exists():
                    pcsv.unlink()
                active_cp = Path(str(pbase) + "_cp")
                if active_cp.exists():
                    shutil.rmtree(active_cp)

            prod_cmd = list(common)
            prod_cmd += [
                f"maxwell_solution_file_t6={mtarget_e}",
                "source_enable_t6=1",
                "rf_scale_t6=1",
                f"Executioner/end_time={target_time:.17g}",
                f"Outputs/file_base={pbase}",
            ]
            if step_idx > 1:
                prod_cmd.append("--recover")

            base.run(prod_cmd, step_dir / "production.log")
            c = base.csv_last(pcsv)
            pscaled = c["P_rf_scaled_W_t6"]
            source_evmol = c["S_rf_eV_mol_s_t6"]
            power_error = base.rel(pscaled, TARGET_W)
            source_unit_error = base.rel(source_evmol * base.FARADAY, pscaled)

            state = state_fields(pe)
            mean_min = float(np.min(state["mean_en_eV"]))
            mean_max = float(np.max(state["mean_en_eV"]))
            row = {
                "step": step_idx,
                "target_time_s": target_time,
                "dt_s": target_time - times[step_idx - 1],
                "unit_drive_target_raw_W": praw_unit,
                "controlled_source_scale": drive_scale,
                "effective_peak_coil_current_A": 10.0 * drive_scale,
                "Maxwell_unit_P_abs_W": maxwell_unit_power,
                "Maxwell_controlled_P_abs_W": maxwell_target_power,
                "plasma_absorbed_RF_W": pscaled,
                "plasma_absorbed_power_relative_error": power_error,
                "rf_source_unit_relative_error": source_unit_error,
                "mean_energy_min_eV": mean_min,
                "mean_energy_max_eV": mean_max,
                "diss_R_min_mol_m3_s": c.get("diss_R_min", float("nan")),
                "diss_R_max_mol_m3_s": c.get("diss_R_max", float("nan")),
                "diss_R_integral_mol_s": c.get("diss_R_integral", float("nan")),
                "diss_energy_source_eV_mol_s": c.get(
                    "diss_energy_source_integral", float("nan")
                ),
                "diss_heavy_mass_closure_kg_s": c.get(
                    "diss_heavy_mass_closure_integral", float("nan")
                ),
            }
            step_rows.append(row)
            (step_dir / "step.json").write_text(
                json.dumps(row, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            if power_error > POWER_GATE:
                raise RuntimeError(
                    f"step {step_idx}: plasma absorbed RF power {pscaled:.12g} W "
                    f"does not close to 1000 W; rel={power_error:.6e}"
                )
            if source_unit_error > SOURCE_UNIT_GATE:
                raise RuntimeError(
                    f"step {step_idx}: RF source unit closure {source_unit_error:.6e}"
                )
            if not finite_state(state):
                raise RuntimeError(f"step {step_idx}: non-finite plasma state")
            if float(np.min(state["ne_mol"])) <= 0.0 or float(np.min(state["p_Pa"])) <= 0.0:
                raise RuntimeError(f"step {step_idx}: non-positive plasma state")
            if c.get("diss_R_max", 0.0) <= 0.0:
                raise RuntimeError(f"step {step_idx}: dissociation progress not positive")
            if c.get("diss_energy_source_integral", 0.0) >= 0.0:
                raise RuntimeError(f"step {step_idx}: dissociation energy term is not a sink")
            if abs(c.get("diss_heavy_mass_closure_integral", float("inf"))) > SOURCE_CLOSURE_GATE:
                raise RuntimeError(f"step {step_idx}: dissociation heavy-mass source closure")

            current_state = pe

        final_state = state_fields(pe)
        ex = base.exodus(pe)
        ex_times = np.asarray(ex["times"], dtype=float)
        final_csv = base.csv_last(pcsv)
        power_errors = [r["plasma_absorbed_power_relative_error"] for r in step_rows]
        powers = [r["plasma_absorbed_RF_W"] for r in step_rows]
        drives = [r["controlled_source_scale"] for r in step_rows]

        failures: list[str] = []
        if abs(float(ex_times[-1]) - FINAL_TIME_S) > TIME_TOL:
            failures.append("did not reach 110 ns")
        if max(power_errors) > POWER_GATE:
            failures.append("1000 W plasma absorbed-power control")
        if not (
            TABLE_LO
            <= float(np.min(final_state["mean_en_eV"]))
            <= float(np.max(final_state["mean_en_eV"]))
            <= TABLE_HI
        ):
            failures.append("final RF transport mean-energy range")

        report = {
            "issue": 395,
            "gate": "RF-ON + O2 dissociation with 1000 W plasma absorbed-power control",
            "status": "PASS" if not failures else "FAIL",
            "classification": (
                "ISSUE395_RF_DISSOCIATION_CONSTANT_1000W_110NS_PASS"
                if not failures
                else "ISSUE395_RF_DISSOCIATION_CONSTANT_1000W_110NS_FAIL"
            ),
            "scope": (
                "fresh t=0 production; RF and source-backed O2 dissociation active from t=0; "
                "Maxwell source amplitude recalibrated at every accepted plasma timestep from "
                "the exact MOOSE target-grid raw RF integral so plasma absorbed RF power is 1000 W"
            ),
            "production_start": "fresh t=0",
            "production_uses_100ns_restart": False,
            "rf_activation": "t=0 / INITIAL",
            "dissociation_activation": "t=0 / INITIAL",
            "power_control": {
                "target_plasma_absorbed_power_W": TARGET_W,
                "owner": "P_rf_raw_W_t6 on plasma target discretization",
                "law": "source_scale=sqrt(1000/P_rf_raw_unit_drive)",
                "control_frequency": "every accepted plasma timestep",
                "rf_deposition_scale": 1.0,
                "max_relative_error": max(power_errors),
                "min_plasma_absorbed_W": min(powers),
                "max_plasma_absorbed_W": max(powers),
                "min_source_scale": min(drives),
                "max_source_scale": max(drives),
                "min_effective_peak_coil_current_A": 10.0 * min(drives),
                "max_effective_peak_coil_current_A": 10.0 * max(drives),
            },
            "dissociation": {
                "reaction": "e + O2 -> e + 2O",
                "rate_law": "1.41e-15*Te_eV^0.22*exp(-12.62/Te_eV) m3/s; Te=(2/3)*mean_en_solved",
                "energy_loss_eV": 12.62,
                "historical_csv_used": False,
            },
            "final": {
                "time_s": float(ex_times[-1]),
                "time_points": int(len(ex_times)),
                "mean_energy_min_eV": float(np.min(final_state["mean_en_eV"])),
                "mean_energy_max_eV": float(np.max(final_state["mean_en_eV"])),
                "ne_min_mol_m3": float(np.min(final_state["ne_mol"])),
                "pressure_min_Pa": float(np.min(final_state["p_Pa"])),
                "w_O_min": float(np.min(final_state["w_O"])),
                "w_O_max": float(np.max(final_state["w_O"])),
                "diss_R_max_mol_m3_s": final_csv.get("diss_R_max"),
                "diss_energy_source_eV_mol_s": final_csv.get("diss_energy_source_integral"),
            },
            "steps": step_rows,
            "tolerances": {
                "plasma_absorbed_power_relative": POWER_GATE,
                "rf_source_unit_relative": SOURCE_UNIT_GATE,
                "dissociation_heavy_mass_closure_kg_s": SOURCE_CLOSURE_GATE,
                "transport_mean_energy_range_eV": [TABLE_LO, TABLE_HI],
            },
            "failures": failures,
        }
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not failures else 2

    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
