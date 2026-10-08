#!/usr/bin/env python3
from pathlib import Path
import prepare_cases as base


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


# The custom mesh is already plasma-only and already carries the final named boundaries.
base.MESH = r'''[Mesh]
  coord_type = RZ
  rz_coord_axis = Y
  [main]
    type = FileMeshGenerator
    file = 'plasma_contour_l3_4p5mm.msh'
  []
[]
'''


def build_case() -> str:
    text = base.fem()

    old_particle = f"""  [electron_sheath]\n    type = PhysicsFEMLogMolarElectronGroundedSheathBC\n    variable = log_ne\n    log_energy = log_energy\n    potential = potential\n    boundary = '{base.EWALL}'\n  []\n"""
    new_particle = f"""  [electron_sheath]\n    type = PhysicsFEMLogMolarElectronNoSheathSuppressionBC\n    variable = log_ne\n    log_energy = log_energy\n    boundary = '{base.EWALL}'\n  []\n"""
    text = replace_once(text, old_particle, new_particle, "electron particle wall BC")

    old_energy = f"""  [electron_energy_sheath]\n    type = PhysicsFEMLogMolarElectronGroundedSheathEnergyBC\n    variable = log_energy\n    log_electron_density = log_ne\n    potential = potential\n    boundary = '{base.EWALL}'\n  []\n"""
    new_energy = f"""  [electron_energy_sheath]\n    type = PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = '{base.EWALL}'\n  []\n"""
    text = replace_once(text, old_energy, new_energy, "electron-energy wall BC")

    if base.DT != 1.0e-9 or base.NSTEPS != 100:
        raise RuntimeError(f"unexpected base time settings: dt={base.DT}, steps={base.NSTEPS}")
    return text


if __name__ == "__main__":
    out = Path(base.HERE) / "full_fem_contour_mesh_dt1ns_100steps.i"
    out.write_text(build_case(), encoding="utf-8")
    print(f"wrote {out}")
    print("mesh: custom plasma-only 3-level wall-distance contour mesh")
    print("L1 h=22 mm; L2 h=11 mm; L3/boundary h=4.5 mm")
    print("L3 thickness=15.5 mm; L2 thickness=19 mm")
    print("electron particle wall BC: thermal-only")
    print("electron energy wall BC: thermal-only")
    print(f"dt={base.DT} s; steps={base.NSTEPS}; end_time={base.END_TIME} s")
