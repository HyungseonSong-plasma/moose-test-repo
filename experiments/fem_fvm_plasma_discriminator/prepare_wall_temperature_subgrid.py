#!/usr/bin/env python3
from pathlib import Path

import prepare_cases as base
import prepare_wall_subcell_compare as compare


def method4t_wall_temperature_subgrid() -> str:
    text = compare.method4_particle_energy_subgrid()
    old = """  [electron_energy_sheath]\n    type = PhysicsFVElectronGroundedSheathEnergyBC\n    variable = log_energy\n    electron_density = electron_molar_density\n    mean_electron_energy = mean_en_solved\n    potential = potential\n    mobility = electron_mobility\n    diffusion = electron_diffusion\n    charge_number = -1\n    molar_energy_state = true\n    use_wall_subgrid_closure = true\n    boundary = '{ewall}'\n  []\n""".format(ewall=base.EWALL)
    new = """  [electron_energy_sheath]\n    type = PhysicsFVElectronGroundedSheathEnergyBC\n    variable = log_energy\n    electron_density = electron_molar_density\n    electron_energy_density = electron_molar_energy_density\n    mean_electron_energy = mean_en_solved\n    potential = potential\n    mobility = electron_mobility\n    diffusion = electron_diffusion\n    energy_mobility = electron_energy_mobility\n    energy_diffusion = electron_energy_diffusion\n    charge_number = -1\n    molar_energy_state = true\n    use_wall_subgrid_closure = true\n    use_wall_energy_subgrid_closure = true\n    boundary = '{ewall}'\n  []\n""".format(ewall=base.EWALL)
    if text.count(old) != 1:
        raise RuntimeError("expected exactly one Method 4E energy sheath block")
    return text.replace(old, new, 1)


if __name__ == "__main__":
    out = Path(base.HERE) / "hybrid_method4t_wall_temperature_subgrid.i"
    out.write_text(method4t_wall_temperature_subgrid(), encoding="utf-8")
    print(f"wrote {out}")
