#!/usr/bin/env python3
"""Issue #376 T5 Maxwell-to-electron-energy RF power closure gate."""
from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
import subprocess
from pathlib import Path

import run_t4_coupling as t4

FARADAY = 96485.33212331001
ACCEPTED_T4_FINE_ENERGY_EV = 11.3314040066
DT = 1.0e-8
RAW_TOL = 2.0e-2
POWER_TOL = 1.0e-10
ENERGY_TOL = 2.0e-8
ZERO_ABS_TOL = 1.0e-12


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--physics", required=True)
    p.add_argument("--maxwell", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--table", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--analysis", required=True)
    return p.parse_args()


def rows(path: Path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def run(cmd, log: Path):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as f:
        f.write("$ " + " ".join(shlex.quote(str(x)) for x in cmd) + "\n")
        f.flush()
        r = subprocess.run([str(x) for x in cmd], stdout=f, stderr=subprocess.STDOUT, text=True)
    if r.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-80:])
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(map(str, cmd))}\n{tail}")


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1.0e-300)


def main() -> int:
    a = parse_args()
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    analysis = Path(a.analysis)
    report = {
        "issue": 376,
        "gate": "T5 Maxwell absorbed power -> electron-energy RF source closure",
        "accepted_T4_fine_mean_energy_eV": ACCEPTED_T4_FINE_ENERGY_EV,
        "failures": [],
    }
    try:
        x, muN = t4.table(a.table)
        cond = t4.sigma(ACCEPTED_T4_FINE_ENERGY_EV, x, muN)
        sr = cond["sigma_real_S_per_m"]
        si = cond["sigma_imag_S_per_m"]

        mb = out / "maxwell"
        run([
            a.physics, "-i", a.maxwell,
            f"plasma_sigma_real={sr:.17g}",
            f"plasma_sigma_imag={si:.17g}",
            f"Outputs/file_base={mb}",
        ], out / "maxwell.log")
        mr = rows(mb.with_suffix(".csv"))[-1]
        pabs = float(mr["P_abs"])
        field_l2 = math.hypot(float(mr["E_real_l2"]), float(mr["E_imag_l2"]))
        if not (pabs > 0.0 and field_l2 > 0.0 and math.isfinite(pabs)):
            raise RuntimeError("invalid Maxwell response")

        case = Path(a.target).parent
        me_rel = mb.with_suffix(".e").relative_to(case)
        ne_mol = t4.NE / t4.NA
        u0 = ne_mol * ACCEPTED_T4_FINE_ENERGY_EV
        logu0 = math.log(u0)
        common = [
            a.physics, "-i", a.target,
            f"maxwell_solution_file={me_rel}",
            f"plasma_sigma_real={sr:.17g}",
            f"energy_initial_log={logu0:.17g}",
            f"dt_t4={DT:.17g}",
        ]

        run([
            a.physics, "--check-input", "-i", a.target,
            f"maxwell_solution_file={me_rel}",
            f"plasma_sigma_real={sr:.17g}",
            f"energy_initial_log={logu0:.17g}",
            f"dt_t4={DT:.17g}",
            "source_enable=0", "rf_scale=1",
        ], out / "check_target.log")

        offb = out / "source_off"
        run(common + ["source_enable=0", "rf_scale=1", f"Outputs/file_base={offb}"], out / "source_off.log")
        offr = rows(offb.with_suffix(".csv"))
        p_raw = float(offr[-1]["P_rf_raw_W"])
        if p_raw <= 0.0:
            raise RuntimeError("non-positive raw mapped RF power")
        scale = pabs / p_raw

        onb = out / "source_on"
        run(common + ["source_enable=1", f"rf_scale={scale:.17g}", f"Outputs/file_base={onb}"], out / "source_on.log")
        onr = rows(onb.with_suffix(".csv"))

        p_scaled = float(onr[-1]["P_rf_scaled_W"])
        s_evmol = float(onr[-1]["S_rf_eV_mol_s"])
        e0 = float(onr[0]["electron_energy_inventory_eV_mol"])
        e1 = float(onr[-1]["electron_energy_inventory_eV_mol"])
        off_e0 = float(offr[0]["electron_energy_inventory_eV_mol"])
        off_e1 = float(offr[-1]["electron_energy_inventory_eV_mol"])
        emin = float(onr[-1]["electron_energy_min_eV_mol_m3"])
        emax = float(onr[-1]["electron_energy_max_eV_mol_m3"])

        raw_def = rel(p_raw, pabs)
        transfer_closure = rel(p_scaled, pabs)
        source_reconstructed = s_evmol * FARADAY
        source_closure = rel(source_reconstructed, pabs)
        inventory_power = (e1 - e0) * FARADAY / DT
        inventory_closure = rel(inventory_power, pabs)
        off_drift = off_e1 - off_e0

        target_text = Path(a.target).read_text(encoding="utf-8")
        rf_owner_count = target_text.count("material_property = q_rf_eV_mol")
        electrostatic_joule_present = "PhysicsFEMLogMolarElectronJouleHeating" in target_text

        failures = []
        if raw_def > RAW_TOL:
            failures.append(f"raw_mapping_relative_defect={raw_def:.6e} > {RAW_TOL:.6e}")
        if transfer_closure > POWER_TOL:
            failures.append(f"deposited_power_closure={transfer_closure:.6e} > {POWER_TOL:.6e}")
        if source_closure > POWER_TOL:
            failures.append(f"source_unit_closure={source_closure:.6e} > {POWER_TOL:.6e}")
        if inventory_closure > ENERGY_TOL:
            failures.append(f"electron_energy_inventory_closure={inventory_closure:.6e} > {ENERGY_TOL:.6e}")
        if abs(off_drift) > ZERO_ABS_TOL:
            failures.append(f"source_off_inventory_drift={off_drift:.6e} > {ZERO_ABS_TOL:.6e}")
        if not (e1 > e0 > 0.0 and emin > 0.0 and emax >= emin):
            failures.append("electron-energy positivity/direction failure")
        if rf_owner_count != 1:
            failures.append(f"expected exactly one RF MatBodyForce owner, found {rf_owner_count}")
        if electrostatic_joule_present:
            failures.append("isolated T5 target unexpectedly includes electrostatic Joule heating")

        report.update({
            "status": "PASS" if not failures else "FAIL",
            "conductivity": cond,
            "maxwell": {"field_l2": field_l2, "P_abs_W": pabs},
            "transfer": {
                "P_raw_W": p_raw,
                "raw_mapping_relative_defect": raw_def,
                "rf_scale": scale,
                "P_scaled_W": p_scaled,
                "deposited_vs_Maxwell_relative_closure": transfer_closure,
            },
            "source_units": {
                "integrated_source_eV_mol_s": s_evmol,
                "reconstructed_power_W": source_reconstructed,
                "relative_closure_vs_Maxwell": source_closure,
            },
            "electron_energy": {
                "dt_s": DT,
                "initial_inventory_eV_mol": e0,
                "final_inventory_eV_mol": e1,
                "inventory_derived_RF_power_W": inventory_power,
                "relative_closure_vs_Maxwell": inventory_closure,
                "source_off_inventory_drift_eV_mol": off_drift,
                "final_min_eV_mol_m3": emin,
                "final_max_eV_mol_m3": emax,
            },
            "ownership": {
                "rf_MatBodyForce_owner_count": rf_owner_count,
                "electrostatic_Joule_present_in_isolated_T5": electrostatic_joule_present,
                "double_counting_detected": electrostatic_joule_present or rf_owner_count != 1,
            },
            "tolerances": {
                "raw_mapping_relative": RAW_TOL,
                "power_relative": POWER_TOL,
                "inventory_relative": ENERGY_TOL,
                "source_off_abs_eV_mol": ZERO_ABS_TOL,
            },
            "failures": failures,
        })
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("T5_POWER_CLOSURE_" + report["status"])
        print(f"sigma=({sr:.12g},{si:.12g}) S/m  P_abs={pabs:.12g} W")
        print(f"raw_defect={raw_def:.6e} scale={scale:.12g} deposited_closure={transfer_closure:.6e}")
        print(f"source_closure={source_closure:.6e} inventory_closure={inventory_closure:.6e} off_drift={off_drift:.6e}")
        print(f"failures={failures}")
        return 0 if not failures else 1
    except Exception as exc:
        report["status"] = "ERROR"
        report["failures"] = [f"runtime: {exc}"]
        report["exception"] = repr(exc)
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"T5_POWER_CLOSURE_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
