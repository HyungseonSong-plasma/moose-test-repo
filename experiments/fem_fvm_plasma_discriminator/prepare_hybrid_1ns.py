#!/usr/bin/env python3
from pathlib import Path
import re

import prepare_cases as base
import prepare_cases_plasma_only as plasma_only


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label} block, found {count}")
    return text.replace(old, new, 1)


def hybrid_1ns() -> str:
    # Importing prepare_cases_plasma_only already mutates base.MESH to keep only
    # the plasma block while preserving the plasma interface side sets.
    text = base.fvm()

    # Keep transport variables cell-centered FV, but solve electrostatic potential
    # with a continuous P1 FEM variable on the same geometric mesh.
    text = replace_once(
        text,
        """  [potential]\n    type = MooseVariableFVReal\n    initial_condition = 0.0\n    block = plasma\n  []\n""",
        """  [potential]\n    family = LAGRANGE\n    order = FIRST\n    initial_condition = 0.0\n    block = plasma\n  []\n""",
        "potential variable",
    )

    # MOOSE FE functors do not implement FaceArg gradients. For the three FV drift
    # kernels, evaluate grad(phi) in the two adjacent P1 elements and average it at
    # the FV face. This preserves the FEM electric-field reconstruction instead of
    # reverting to a cell-center potential difference.
    old = "    advected_interp_method = upwind\n"
    new = "    use_element_gradient_for_potential = true\n    advected_interp_method = upwind\n"
    if text.count(old) != 3:
        raise RuntimeError(f"expected three FV drift interpolation settings, found {text.count(old)}")
    text = text.replace(old, new)

    # Remove the FV Poisson operator/source. The charge functor remains computed
    # directly from FV log_ne/log_ni and is consumed by the FEM weak source below.
    text = replace_once(
        text,
        """  [phi_diffusion]\n    type = FVDiffusion\n    variable = potential\n    coeff = relative_permittivity\n    block = plasma\n  []\n  [phi_source]\n    type = FVCoupledForce\n    variable = potential\n    v = poisson_source\n    coef = 1.0\n    block = plasma\n  []\n""",
        "",
        "FV Poisson",
    )

    fem_poisson = """[Kernels]\n  [phi_diffusion]\n    type = ADDiffusion\n    variable = potential\n    block = plasma\n  []\n  [phi_source]\n    type = FunctorKernel\n    variable = potential\n    functor = poisson_source\n    functor_on_rhs = true\n    block = plasma\n  []\n[]\n\n"""
    text = replace_once(text, "[FVBCs]\n", fem_poisson + "[FVBCs]\n", "FVBCs section start")

    # Potential grounding belongs to the FEM variable; all transport wall BCs stay FV.
    text = replace_once(
        text,
        f"""  [grounded_potential]\n    type = FVDirichletBC\n    variable = potential\n    value = 0.0\n    boundary = '{base.GROUND}'\n  []\n""",
        "",
        "FV potential BC",
    )

    fem_bc = f"""[BCs]\n  [grounded_potential]\n    type = DirichletBC\n    variable = potential\n    value = 0.0\n    boundary = '{base.GROUND}'\n  []\n[]\n\n"""
    text = replace_once(text, "[Postprocessors]\n", fem_bc + "[Postprocessors]\n", "Postprocessors section start")

    # One physical step only: isolate the earliest charge/Poisson response before
    # the electrostatic transport feedback has time to accumulate.
    text, n_num = re.subn(r"  num_steps = \d+\n", "  num_steps = 1\n", text, count=1)
    text, n_end = re.subn(r"  end_time = [^\n]+\n", f"  end_time = {base.DT:.17g}\n", text, count=1)
    if n_num != 1 or n_end != 1:
        raise RuntimeError("failed to reduce hybrid case to exactly one 1 ns step")

    return text


if __name__ == "__main__":
    out = Path(base.HERE) / "hybrid_plasma_discriminator.i"
    out.write_text(hybrid_1ns(), encoding="utf-8")
    print(f"wrote {out}")
    print("hybrid: FV log_ne/log_ni/log_energy + FEM P1 potential")
    print("Poisson RHS: charge functor evaluated directly from FV cell states")
    print("FV drift field: average of adjacent FEM P1 element gradients")
    print(f"dt={base.DT} s; steps=1; end_time={base.DT} s")
    print("axis: natural RZ symmetry; no explicit r=0 potential BC")
