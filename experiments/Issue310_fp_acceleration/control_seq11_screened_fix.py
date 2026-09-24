"""Gen11 lane-local repairs for the screened-Poisson discriminator.

Repair 1: FVReaction::rate is scalar in the installed MOOSE build. Realize the
spatial correction with PhysicsFVSpeciesReactionSource and an AD functor source
-source=-beta*(phi-phi_anchor), yielding +beta*(phi-phi_anchor) in the residual.

Repair 2: Sequence08 run_case launches control_seq08.py in a fresh Docker Python
process, where Gen11's monkey-patched CASE_NAMES do not exist. Keep the scientific
case unchanged but own the Docker inner-run dispatch in this Gen11 wrapper.
"""
from __future__ import annotations

import json
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
    return fast, poisson.replace(bad, good, 1)


gen11._apply_screening = _apply_screening


def p0() -> None:
    built = gen11.build()
    assert len(built) == 2
    a, b = (gen11.GENERATED / n for n in gen11.CASE_NAMES)
    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert "gummel_screen_reaction" not in (a / "poisson_sub.i").read_text()
    trial_p = (b / "poisson_sub.i").read_text()
    trial_f = (b / "fast_sub.i").read_text()
    for token in ("type = Transient", "fixed_point_algorithm = 'picard'",
                  "gummel_screen_beta", "type = PhysicsFVSpeciesReactionSource",
                  "source = gummel_screen_residual_source", "screening_correction_avg"):
        assert token in trial_p
    assert "rate = gummel_screen_beta" not in trial_p
    assert "TimeDerivative" not in trial_p
    assert "mean_energy_to_poisson" in trial_f and "phi_anchor_to_poisson" in trial_f
    assert "no_restore = true" in trial_f
    print("ISSUE310_GEN11_SCREENED_FIX_P0: PASS")


def inner_run(name: str) -> int:
    gen11._bind_seq08()
    return gen11.seq08.inner_run(name)


def run_case(name: str) -> None:
    gen11._bind_seq08()
    if not gen11.GENERATED.exists():
        gen11.build()
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    gen11.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq11_screened_fix.py --inner-run {name}"
    )
    result, code = gen11.seq08.analyze(name)
    gen11.RESULTS.mkdir(parents=True, exist_ok=True)
    (gen11.RESULTS / f"{name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_GEN11_CASE:", name, result["classification"])
    if code:
        raise SystemExit(code)


def main() -> None:
    if "--p0" in sys.argv:
        p0(); return
    if "--inner-run" in sys.argv:
        i = sys.argv.index("--inner-run")
        raise SystemExit(inner_run(sys.argv[i + 1]))
    if "--case" in sys.argv:
        i = sys.argv.index("--case")
        name = sys.argv[i + 1]
        if name not in gen11.CASE_NAMES:
            raise SystemExit(f"unknown Gen11 case: {name}")
        run_case(name); return
    gen11.main()


if __name__ == "__main__":
    main()
