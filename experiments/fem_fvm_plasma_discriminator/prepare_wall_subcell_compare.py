#!/usr/bin/env python3
from pathlib import Path

import prepare_hybrid_1ns as hybrid
import prepare_cases as base


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def method1_linear_reconstruction() -> str:
    text = hybrid.hybrid_1ns()
    old = """  [ne_drift]\n    type = PhysicsFVLogMolarElectrostaticDrift\n    variable = log_ne\n    potential = potential\n    mobility = electron_mobility\n    carrier = carrier_one\n    charge_number = -1\n    use_element_gradient_for_potential = true\n    advected_interp_method = upwind\n    boundaries_to_avoid = '{ground}'\n    block = plasma\n  []\n""".format(ground=base.GROUND)
    new = old.replace(
        "    advected_interp_method = upwind\n",
        "    use_limited_linear_reconstruction = true\n    advected_interp_method = upwind\n",
    )
    return replace_once(text, old, new, "electron drift block")


def method4_wall_subgrid() -> str:
    text = hybrid.hybrid_1ns()
    old = """  [electron_sheath]\n    type = PhysicsFVElectronGroundedSheathCollectionBC\n    variable = log_ne\n    mean_electron_energy = mean_en_solved\n    potential = potential\n    log_molar_state = true\n    boundary = '{ewall}'\n  []\n""".format(ewall=base.EWALL)
    new = """  [electron_sheath]\n    type = PhysicsFVElectronGroundedSheathCollectionBC\n    variable = log_ne\n    mean_electron_energy = mean_en_solved\n    potential = potential\n    mobility = electron_mobility\n    diffusion = electron_diffusion\n    charge_number = -1\n    log_molar_state = true\n    use_wall_subgrid_closure = true\n    boundary = '{ewall}'\n  []\n""".format(ewall=base.EWALL)
    return replace_once(text, old, new, "electron sheath block")


if __name__ == "__main__":
    here = Path(base.HERE)
    cases = {
        "hybrid_method1_linear_reconstruction.i": method1_linear_reconstruction(),
        "hybrid_method4_wall_subgrid.i": method4_wall_subgrid(),
    }
    for name, text in cases.items():
        path = here / name
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")

    print("common baseline: reconstructed FV charge -> FEM P1 Poisson")
    print("method 1: bounded linear reconstruction of electron upwind face log-density")
    print("method 4: analytic 1D wall-cell drift-diffusion/sheath subgrid closure")
    print(f"dt={base.DT} s; one step")
