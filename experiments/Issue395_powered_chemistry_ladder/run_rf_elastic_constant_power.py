#!/usr/bin/env python3
"""Issue #395 RF-ON + EI02 elastic loss with 1000 W plasma absorbed-power control."""
from __future__ import annotations

import argparse, json, math, shutil, sys
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


def args():
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


def accepted_times():
    t = [0.0]
    t.extend(i * 1.0e-9 for i in range(1, 101))
    t.append(1.10e-7)
    return t


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


def copy_file(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def snapshot(pbase: Path, dst: Path):
    cp = Path(str(pbase) + "_cp")
    if not cp.is_dir():
        raise RuntimeError(f"checkpoint missing: {cp}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(cp, dst)
    copy_file(pbase.with_suffix(".e"), dst.parent / "accepted.e")
    copy_file(pbase.with_suffix(".csv"), dst.parent / "accepted.csv")


def restore(pbase: Path, snap: Path):
    v2.restore_checkpoint(snap, Path(str(pbase) + "_cp"))
    copy_file(snap.parent / "accepted.e", pbase.with_suffix(".e"))
    copy_file(snap.parent / "accepted.csv", pbase.with_suffix(".csv"))


def main():
    a = args()
    out = a.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    analysis = a.analysis.resolve()
    report = {"issue": 395, "gate": "RF+EI02 elastic constant 1000 W", "status": "ERROR"}
    try:
        physics = str(Path(a.physics).resolve())
        pin = str(a.plasma_input.resolve())
        rfov = str(a.rf_plasma_overlay.resolve())
        elasticov = str(a.elastic_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())

        etxt = a.elastic_overlay.read_text(encoding="utf-8")
        for token in ("R_elastic_O2", "elastic_energy_source_EI02", "PhysicsElectronImpactRateMaterial"):
            if token not in etxt:
                raise RuntimeError(f"elastic overlay missing {token}")
        for token in ("R_diss_O2", "diss_energy", "12.62", "R_ion_O2"):
            if token in etxt:
                raise RuntimeError(f"forbidden chemistry present: {token}")

        seed = out / "seed" / "maxwell"
        base.run([physics, "-i", minp, f"Outputs/file_base={seed}"], out / "seed" / "run.log")
        seed_e = seed.with_suffix(".e")

        common = [physics, "-i", pin, rfov, elasticov]
        init = out / "initial" / "plasma"
        base.run(common + [f"maxwell_solution_file_t6={seed_e}", "source_enable_t6=0", "rf_scale_t6=1", "Executioner/num_steps=0", "Executioner/end_time=0", f"Outputs/file_base={init}"], out / "initial" / "run.log")
        current_state = init.with_suffix(".e")
        if not current_state.is_file():
            raise RuntimeError("t=0 state missing")

        pbase = out / "production" / "plasma"
        pe, pcsv = pbase.with_suffix(".e"), pbase.with_suffix(".csv")
        times = accepted_times()
        rows = []

        for i, target in enumerate(times[1:], 1):
            sd = out / "coupling" / f"step_{i:03d}"
            sd.mkdir(parents=True, exist_ok=True)

            mu = sd / "maxwell_unit" / "maxwell"
            base.run([physics, "-i", minp, mov, f"plasma_solution_file_t6={current_state}", "source_scale=1", f"Outputs/file_base={mu}"], sd / "maxwell_unit" / "run.log")
            mu_e = mu.with_suffix(".e")
            pmax_unit = base.csv_last(mu.with_suffix(".csv"))["P_abs"]
            if pmax_unit <= 0:
                raise RuntimeError(f"step {i}: nonpositive Maxwell unit power")

            snap = sd / "before_probe" / "checkpoint"
            if i > 1:
                snapshot(pbase, snap)

            probe = list(common) + [f"maxwell_solution_file_t6={mu_e}", "source_enable_t6=0", "rf_scale_t6=1", f"Executioner/end_time={target:.17g}", f"Outputs/file_base={pbase}"]
            if i > 1:
                probe.append("--recover")
            base.run(probe, sd / "probe.log")
            praw = base.csv_last(pcsv)["P_rf_raw_W_t6"]
            if praw <= 0:
                raise RuntimeError(f"step {i}: nonpositive target raw RF power")
            scale = math.sqrt(TARGET_W / praw)

            mt = sd / "maxwell_1000w" / "maxwell"
            base.run([physics, "-i", minp, mov, f"plasma_solution_file_t6={current_state}", f"source_scale={scale:.17g}", f"Outputs/file_base={mt}"], sd / "maxwell_1000w" / "run.log")
            mt_e = mt.with_suffix(".e")
            pmax = base.csv_last(mt.with_suffix(".csv"))["P_abs"]

            if i > 1:
                restore(pbase, snap)
            else:
                for f in (pe, pcsv):
                    if f.exists(): f.unlink()
                cp = Path(str(pbase) + "_cp")
                if cp.exists(): shutil.rmtree(cp)

            cmd = list(common) + [f"maxwell_solution_file_t6={mt_e}", "source_enable_t6=1", "rf_scale_t6=1", f"Executioner/end_time={target:.17g}", f"Outputs/file_base={pbase}"]
            if i > 1:
                cmd.append("--recover")
            base.run(cmd, sd / "production.log")

            c = base.csv_last(pcsv)
            s = state_fields(pe)
            prf = c["P_rf_scaled_W_t6"]
            perr = base.rel(prf, TARGET_W)
            uerr = base.rel(c["S_rf_eV_mol_s_t6"] * base.FARADAY, prf)
            row = {
                "step": i,
                "time_s": target,
                "dt_s": target - times[i-1],
                "plasma_absorbed_RF_W": prf,
                "power_relative_error": perr,
                "source_scale": scale,
                "effective_peak_coil_current_A": 10.0 * scale,
                "Maxwell_unit_P_abs_W": pmax_unit,
                "Maxwell_controlled_P_abs_W": pmax,
                "mean_energy_min_eV": float(np.min(s["mean_en_eV"])),
                "mean_energy_max_eV": float(np.max(s["mean_en_eV"])),
                "elastic_R_max": c.get("elastic_R_max"),
                "elastic_R_integral": c.get("elastic_R_integral"),
                "elastic_delta_e_min_eV": c.get("elastic_delta_e_min"),
                "elastic_delta_e_max_eV": c.get("elastic_delta_e_max"),
                "elastic_energy_source_eV_mol_s": c.get("elastic_energy_source_integral"),
            }
            rows.append(row)
            (sd / "step.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")

            if perr > POWER_GATE:
                raise RuntimeError(f"step {i}: absorbed RF power {prf} W not 1000 W")
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

            current_state = pe

        final = state_fields(pe)
        xt = np.asarray(base.exodus(pe)["times"], dtype=float)
        failures = []
        if abs(float(xt[-1]) - FINAL_TIME_S) > TIME_TOL:
            failures.append("did not reach 110 ns")
        if max(r["power_relative_error"] for r in rows) > POWER_GATE:
            failures.append("1000 W power control")
        emin, emax = float(np.min(final["mean_en_eV"])), float(np.max(final["mean_en_eV"]))
        if not (TABLE_LO <= emin <= emax <= TABLE_HI):
            failures.append("RF transport mean-energy range")

        report = {
            "issue": 395,
            "gate": "RF-ON + EI02 elastic with 1000 W plasma absorbed-power control",
            "status": "PASS" if not failures else "FAIL",
            "classification": "ISSUE395_RF_ELASTIC_CONSTANT_1000W_110NS_PASS" if not failures else "ISSUE395_RF_ELASTIC_CONSTANT_1000W_110NS_FAIL",
            "production_start": "fresh t=0",
            "production_uses_100ns_restart": False,
            "rf_activation": "t=0",
            "elastic_activation": "t=0",
            "dissociation_active": False,
            "ionization_active": False,
            "power_control": {
                "target_W": TARGET_W,
                "owner": "P_rf_raw_W_t6 target-grid integral",
                "law": "source_scale=sqrt(1000/P_rf_raw_unit_drive)",
                "frequency": "every accepted timestep",
                "max_relative_error": max(r["power_relative_error"] for r in rows),
            },
            "elastic": {
                "reaction": "e + O2 -> e + O2",
                "rate_table": "o2_elastic.txt",
                "energy_transfer_law": "3*m_e/m_O2*((2/3)*mean_en-kB*Tg/e)",
                "particle_source": 0,
                "heavy_species_source": 0,
            },
            "final": {"time_s": float(xt[-1]), "mean_energy_min_eV": emin, "mean_energy_max_eV": emax, "ne_min_mol_m3": float(np.min(final["ne_mol"]))},
            "steps": rows,
            "failures": failures,
        }
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not failures else 2
    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        raise

if __name__ == "__main__":
    raise SystemExit(main())
