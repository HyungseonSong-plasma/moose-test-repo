#!/usr/bin/env python3
from pathlib import Path

import prepare_cases as base
import prepare_cases_plasma_only  # mutates base.MESH to keep only the plasma block


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def build_case() -> str:
    text = base.fem()

    old_particle = f"""  [electron_sheath]\n    type = PhysicsFEMLogMolarElectronGroundedSheathBC\n    variable = log_ne\n    log_energy = log_energy\n    potential = potential\n    boundary = '{base.EWALL}'\n  []\n"""
    new_particle = f"""  [electron_sheath]\n    type = PhysicsFEMLogMolarElectronNoSheathSuppressionBC\n    variable = log_ne\n    log_energy = log_energy\n    boundary = '{base.EWALL}'\n  []\n"""
    text = replace_once(text, old_particle, new_particle, "electron particle wall BC")

    old_energy = f"""  [electron_energy_sheath]\n    type = PhysicsFEMLogMolarElectronGroundedSheathEnergyBC\n    variable = log_energy\n    log_electron_density = log_ne\n    potential = potential\n    boundary = '{base.EWALL}'\n  []\n"""
    new_energy = f"""  [electron_energy_sheath]\n    type = PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = '{base.EWALL}'\n  []\n"""
    text = replace_once(text, old_energy, new_energy, "electron-energy wall BC")

    if base.DT != 1.0e-9 or base.NSTEPS != 100:
        raise RuntimeError(
            f"unexpected base time settings: dt={base.DT}, steps={base.NSTEPS}; expected 1 ns x 100"
        )

    return text


if __name__ == "__main__":
    out = Path(base.HERE) / "full_fem_energy_no_sheath_dt1ns_100steps.i"
    out.write_text(build_case(), encoding="utf-8")
    print(f"wrote {out}")
    print("discretization: full FEM for log_ne, log_ni, log_energy, potential")
    print("mesh: plasma block only")
    print("electron particle wall BC: thermal-only, NO exp(-Delta phi/T_e)")
    print("electron particle wall flux = (1/4 c_e vbar_e)")
    print("electron energy wall BC: thermal-only, NO exp(-Delta phi/T_e), NO +Delta phi energy term")
    print("electron energy wall flux = (1/4 c_e vbar_e) * (5/2 T_e)")
    print("O2+ wall BC: unchanged, sticking=1 plus outward migration")
    print("Poisson: -laplacian(phi) = e(ni-ne)/epsilon0; epsilon_r=1 in plasma")
    print(f"dt={base.DT} s = {base.DT*1e9:g} ns")
    print(f"steps={base.NSTEPS}")
    print(f"end_time={base.END_TIME} s = {base.END_TIME*1e9:g} ns")
