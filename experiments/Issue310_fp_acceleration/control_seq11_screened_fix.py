"""Gen11 lane-local repair: realize beta*(phi-phi_anchor) with an AD functor source.

FVReaction::rate is a scalar Real in the installed MOOSE build, so it cannot consume
the spatial functor gummel_screen_beta.  This wrapper preserves the Gen11 physics
and replaces only that invalid realization.  PhysicsFVSpeciesReactionSource returns
-source; defining source=-beta*(phi-phi_anchor) therefore contributes the desired
+beta*(phi-phi_anchor) residual with AD derivatives in phi.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq11_screened as gen11

_ORIGINAL = gen11._apply_screening


def _apply_screening(fast: str, poisson: str) -> tuple[str, str]:
    fast, poisson = _ORIGINAL(fast, poisson)

    material_anchor = """  [gummel_screening_correction_abs]
    type = ADParsedFunctorMaterial
    property_name = gummel_screen_correction_abs
    functor_names = 'gummel_screen_beta potential_plasma phi_anchor_frozen'
    functor_symbols = 'beta phi phi0'
    expression = 'abs(beta*(phi-phi0))'
  []
"""
    material_replacement = material_anchor + """  [gummel_screen_residual_source]
    type = ADParsedFunctorMaterial
    property_name = gummel_screen_residual_source
    functor_names = 'gummel_screen_beta potential_plasma phi_anchor_frozen'
    functor_symbols = 'beta phi phi0'
    expression = '-beta*(phi-phi0)'
  []
"""
    if poisson.count(material_anchor) != 1:
        raise RuntimeError("screening correction material anchor changed")
    poisson = poisson.replace(material_anchor, material_replacement, 1)

    bad = """  [gummel_screen_reaction]
    type = FVReaction
    variable = potential_plasma
    rate = gummel_screen_beta
  []
  [gummel_screen_anchor]
    type = FVCoupledForce
    variable = potential_plasma
    v = gummel_screen_anchor_source
    coef = 1.0
  []
"""
    good = """  [gummel_screen_reaction]
    type = PhysicsFVSpeciesReactionSource
    variable = potential_plasma
    source = gummel_screen_residual_source
  []
"""
    if poisson.count(bad) != 1:
        raise RuntimeError("invalid FVReaction realization anchor changed")
    poisson = poisson.replace(bad, good, 1)
    return fast, poisson


gen11._apply_screening = _apply_screening


def p0() -> None:
    built = gen11.build()
    assert len(built) == 2
    a, b = (gen11.GENERATED / n for n in gen11.CASE_NAMES)
    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert "gummel_screen_reaction" not in (a / "poisson_sub.i").read_text()
    trial_p = (b / "poisson_sub.i").read_text()
    trial_f = (b / "fast_sub.i").read_text()
    for token in (
        "type = Transient",
        "fixed_point_algorithm = 'picard'",
        "gummel_screen_beta",
        "type = PhysicsFVSpeciesReactionSource",
        "source = gummel_screen_residual_source",
        "screening_correction_avg",
    ):
        assert token in trial_p
    assert "rate = gummel_screen_beta" not in trial_p
    assert "TimeDerivative" not in trial_p
    assert "mean_energy_to_poisson" in trial_f and "phi_anchor_to_poisson" in trial_f
    assert "no_restore = true" in trial_f
    print("ISSUE310_GEN11_SCREENED_FIX_P0: PASS")


def main() -> None:
    if "--p0" in sys.argv:
        p0()
    else:
        gen11.main()


if __name__ == "__main__":
    main()
