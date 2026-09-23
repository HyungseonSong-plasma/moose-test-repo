"""Issue #310 Generation 11: Debye-screened Poisson Gummel discriminator.

Qualified immutable source: d2f9d75f8bdf392e647165ad25f7c5808dfd2b40.
The trial changes only the iteration operator.  It adds
  beta * (phi - phi_anchor), beta=e*n_e/(eps0*T_e[eV]),
to the Poisson residual, with T_e=(2/3)*mean electron energy.  The correction
vanishes at a converged Gummel fixed point; the converged plasma equations and
BC ownership are unchanged.

Short discriminator: one heavy cycle / four electron steps / 400 initial tau.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq08 as seq08
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08

base = wall08.base
GENERATED = ROOT / "generated_fp11_screened"
RESULTS = ROOT / "results_fp11_screened"
CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 400.0
HEAVY_CYCLES = 1
RATIO = 4
FP_MAX = 3000
E_OVER_EPS0 = 1.8095128179727827e-8

SPECS = (
    {"name": "picard2x_control", "screened": False},
    {"name": "screened_thermal_picard2x", "screened": True},
)
CASE_NAMES = tuple(x["name"] for x in SPECS)
wall08.FINAL_TAU = FINAL_TAU


def _spec(raw: dict[str, object]) -> dict[str, object]:
    return {
        **raw,
        "architecture": "transient_timeaware",
        "algorithm": "picard",
        "mode": "thermal",
        "chi": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "ratio": RATIO,
        "fp_max": FP_MAX,
        "relaxation_factor": 2.0 / (1.0 + CHI_E),
    }


def _params(raw: dict[str, object]) -> dict[str, object]:
    spec = _spec(raw)
    with wall08._clock(spec):
        p = wall08.wall03._params(spec)
    p.update(
        heavy_to_electron_dt_ratio=RATIO,
        architecture="transient_timeaware",
        fixed_point_algorithm="picard",
        relaxation_factor=2.0 / (1.0 + CHI_E),
        screened_poisson=bool(raw["screened"]),
    )
    return p


def _timeaware(raw: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    # Reuse the qualified Sequence08 renderer, but under the short Generation11 clock.
    spec = _spec(raw)
    old_final = seq08.FINAL_TAU
    old_cycles = seq08.HEAVY_CYCLES
    try:
        seq08.FINAL_TAU = FINAL_TAU
        seq08.HEAVY_CYCLES = HEAVY_CYCLES
        with wall08._clock(spec):
            parent, fast, poisson = seq08._render_case(spec, p)
    finally:
        seq08.FINAL_TAU = old_final
        seq08.HEAVY_CYCLES = old_cycles
    return parent, fast, poisson


def _apply_screening(fast: str, poisson: str) -> tuple[str, str]:
    # Transfer the entering outer iterate and local electron temperature proxy.
    anchor = """  [log_e_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = log_e
    variable = log_e_frozen
    execute_on = SAME_AS_MULTIAPP
  []
"""
    extra = anchor + """  [mean_energy_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = mean_energy_out
    variable = mean_energy_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [phi_anchor_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = potential_from_poisson
    variable = phi_anchor_frozen
    execute_on = SAME_AS_MULTIAPP
  []
"""
    if fast.count(anchor) != 1:
        raise RuntimeError("log_e transfer anchor changed")
    fast = fast.replace(anchor, extra, 1)

    aux_anchor = """  [log_e_frozen]
    type = MooseVariableFVReal
"""
    if poisson.count(aux_anchor) != 1:
        raise RuntimeError("Poisson aux anchor changed")
    poisson = poisson.replace(
        aux_anchor,
        """  [mean_energy_frozen]
    type = MooseVariableFVReal
    initial_condition = 5.73276
  []
  [phi_anchor_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [log_e_frozen]
    type = MooseVariableFVReal
""",
        1,
    )

    material_anchor = """  [plasma_charge]
    type = PhysicsPlasmaChargeDensityMaterial
"""
    if poisson.count(material_anchor) != 1:
        raise RuntimeError("plasma charge anchor changed")
    screening_material = f"""  [gummel_screening]
    type = ADParsedFunctorMaterial
    property_name = gummel_screen_beta
    functor_names = 'electron_density_m3 mean_energy_frozen'
    functor_symbols = 'ne mean_ev'
    expression = '{E_OVER_EPS0:.17g}*ne/((2.0/3.0)*max(mean_ev,1.0e-6))'
  []
  [gummel_screening_source]
    type = ADParsedFunctorMaterial
    property_name = gummel_screen_anchor_source
    functor_names = 'gummel_screen_beta phi_anchor_frozen'
    functor_symbols = 'beta phi0'
    expression = 'beta*phi0'
  []
  [gummel_screening_correction_abs]
    type = ADParsedFunctorMaterial
    property_name = gummel_screen_correction_abs
    functor_names = 'gummel_screen_beta potential_plasma phi_anchor_frozen'
    functor_symbols = 'beta phi phi0'
    expression = 'abs(beta*(phi-phi0))'
  []
"""
    poisson = poisson.replace(material_anchor, screening_material + material_anchor, 1)

    kernel_anchor = """  [phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = poisson_charge_source
    coef = 1.0
  []
"""
    if poisson.count(kernel_anchor) != 1:
        raise RuntimeError("Poisson charge kernel anchor changed")
    poisson = poisson.replace(
        kernel_anchor,
        kernel_anchor + """  [gummel_screen_reaction]
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
""",
        1,
    )

    pp_anchor = """  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
"""
    if poisson.count(pp_anchor) != 1:
        raise RuntimeError("Poisson postprocessor anchor changed")
    poisson = poisson.replace(
        pp_anchor,
        """  [screening_correction_avg]
    type = ElementAverageFunctorPostprocessor
    functor = gummel_screen_correction_abs
    execute_on = 'INITIAL FINAL'
  []
  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
""",
        1,
    )
    return fast, poisson


def render(raw: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    parent, fast, poisson = _timeaware(raw, p)
    if raw["screened"]:
        fast, poisson = _apply_screening(fast, poisson)
    return parent, fast, poisson


def build(clean: bool = True) -> list[dict[str, object]]:
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    built = []
    for raw in SPECS:
        p = _params(raw)
        d = GENERATED / str(p["name"])
        d.mkdir(parents=True, exist_ok=True)
        parent, fast, poisson = render(raw, p)
        (d / "input.i").write_text(parent, encoding="utf-8")
        (d / "fast_sub.i").write_text(fast, encoding="utf-8")
        (d / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(json.dumps(p, indent=2, sort_keys=True) + "\n")
        built.append(p)
    return built


def p0() -> None:
    built = build()
    assert len(built) == 2
    a, b = (GENERATED / n for n in CASE_NAMES)
    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert "gummel_screen_reaction" not in (a / "poisson_sub.i").read_text()
    trial_p = (b / "poisson_sub.i").read_text()
    trial_f = (b / "fast_sub.i").read_text()
    for token in (
        "type = Transient", "fixed_point_algorithm = 'picard'", "gummel_screen_beta",
        "type = FVReaction", "gummel_screen_anchor_source", "screening_correction_avg",
    ):
        assert token in trial_p
    assert "TimeDerivative" not in trial_p
    assert "mean_energy_to_poisson" in trial_f and "phi_anchor_to_poisson" in trial_f
    assert "no_restore = true" in trial_f
    print("ISSUE310_GEN11_SCREENED_P0: PASS")


def _bind_seq08() -> None:
    seq08.GENERATED = GENERATED
    seq08.RESULTS = RESULTS
    seq08.FINAL_TAU = FINAL_TAU
    seq08.HEAVY_CYCLES = HEAVY_CYCLES
    seq08.CASE_NAMES = CASE_NAMES
    seq08.SPECS = tuple(_spec(x) for x in SPECS)
    wall08.FINAL_TAU = FINAL_TAU


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    cmds = "; ".join(
        f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp11_screened/{n}/input.i"
        for n in CASE_NAMES
    )
    base._docker("set -euo pipefail; source /environment; export PYTHONPATH=/workspace; " + cmds)
    print("ISSUE310_GEN11_SCREENED_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for n in CASE_NAMES:
        for f in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(f"cd /workspace/{rel}/generated_fp11_screened/{n} && /workspace/physics_app/physics-opt --check-input -i {f}")
    base._docker("set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks))
    print("ISSUE310_GEN11_SCREENED_P2: PASS")


def run_case(name: str) -> None:
    _bind_seq08()
    if not GENERATED.exists():
        build()
    seq08.run_case(name)


def aggregate() -> None:
    _bind_seq08()
    seq08.aggregate()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--case", choices=CASE_NAMES)
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()
    if args.p0: p0()
    elif args.p1: p1()
    elif args.p2: p2()
    elif args.case: run_case(args.case)
    elif args.aggregate: aggregate()
    else: ap.error("choose --p0/--p1/--p2/--case/--aggregate")


if __name__ == "__main__":
    main()
