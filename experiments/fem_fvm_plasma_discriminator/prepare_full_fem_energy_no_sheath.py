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

    old = f"""  [electron_energy_sheath]\n    type = PhysicsFEMLogMolarElectronGroundedSheathEnergyBC\n    variable = log_energy\n    log_electron_density = log_ne\n    potential = potential\n    boundary = '{base.EWALL}'\n  []\n"""
    new = f"""  [electron_energy_sheath]\n    type = PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = '{base.EWALL}'\n  []\n"""
    text = replace_once(text, old, new, "electron-energy wall BC")

    # base.fem() is already the requested 1 ns x 100 configuration.
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
    print("electron particle wall BC: standard sheath-suppressed model")
    print("electron energy wall BC: NO exp(-Delta phi/T_e), NO +Delta phi energy term")
    print("energy wall flux = (1/4 c_e vbar_e) * (5/2 T_e)")
    print(f"dt={base.DT} s = {base.DT*1e9:g} ns")
    print(f"steps={base.NSTEPS}")
    print(f"end_time={base.END_TIME} s = {base.END_TIME*1e9:g} ns")
