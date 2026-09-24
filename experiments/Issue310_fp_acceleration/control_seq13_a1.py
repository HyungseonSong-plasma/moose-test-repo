"""Issue #310 Generation 13 A1 small-gamma screened-Poisson discriminator.

Starts from the immutable qualified baseline and changes only the Gummel
iteration operator.  The correction beta_eff*(phi-phi_anchor) vanishes at the
fixed point.  Variants gamma=0.025 and 0.05 are tested against a same-lane
Picard-2x control for one heavy cycle / four electron steps.
"""
from __future__ import annotations

import argparse
import json
import os
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
GENERATED = ROOT / "generated_fp13_a1"
RESULTS = ROOT / "results_fp13_a1"
CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 400.0
HEAVY_CYCLES = 1
RATIO = 4
FP_MAX = 3000
E_OVER_EPS0 = 1.8095128179727827e-8
MODE = "a1"

SPECS = (
    {"name": "picard2x_control", "gamma": 0.0},
    {"name": "a1_gamma0025", "gamma": 0.025},
    {"name": "a1_gamma0050", "gamma": 0.05},
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
        screening_gamma=float(raw["gamma"]),
        screening_surrogate=MODE,
    )
    return p


def _timeaware(raw: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
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


def _apply_screening(fast: str, poisson: str, gamma: float) -> tuple[str, str]:
    transfer_anchor = """  [log_e_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = log_e
    variable = log_e_frozen
    execute_on = SAME_AS_MULTIAPP
  []
"""
    transfer_extra = transfer_anchor + """  [screen_state_to_poisson]
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
    if fast.count(transfer_anchor) != 1:
        raise RuntimeError("log_e transfer anchor changed")
    fast = fast.replace(transfer_anchor, transfer_extra, 1)

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
    expression = '{gamma:.17g}*{E_OVER_EPS0:.17g}*ne/((2.0/3.0)*max(mean_ev,1.0e-6))'
  []
  [gummel_screening_residual]
    type = ADParsedFunctorMaterial
    property_name = gummel_screen_residual_source
    functor_names = 'gummel_screen_beta potential_plasma phi_anchor_frozen'
    functor_symbols = 'beta phi phi0'
    expression = '-beta*(phi-phi0)'
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
    type = PhysicsFVSpeciesReactionSource
    variable = potential_plasma
    source = gummel_screen_residual_source
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
    gamma = float(raw["gamma"])
    if gamma > 0.0:
        fast, poisson = _apply_screening(fast, poisson, gamma)
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
    assert len(built) == 3
    dirs = [GENERATED / n for n in CASE_NAMES]
    assert all((dirs[0] / "input.i").read_text() == (d / "input.i").read_text() for d in dirs[1:])
    assert "gummel_screen_reaction" not in (dirs[0] / "poisson_sub.i").read_text()
    for d in dirs[1:]:
        p = (d / "poisson_sub.i").read_text()
        f = (d / "fast_sub.i").read_text()
        assert "type = PhysicsFVSpeciesReactionSource" in p
        assert "source = gummel_screen_residual_source" in p
        assert "gummel_screen_beta" in p
        assert "screening_correction_avg" in p
        assert "TimeDerivative" not in p
        assert "phi_anchor_to_poisson" in f and "no_restore = true" in f
    assert {float(x["screening_gamma"]) for x in built} == {0.0, 0.025, 0.05}
    print("ISSUE310_GEN13_A1_P0: PASS")


def _bind() -> None:
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
        f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp13_a1/{n}/input.i"
        for n in CASE_NAMES
    )
    base._docker("set -euo pipefail; source /environment; export PYTHONPATH=/workspace; " + cmds)
    print("ISSUE310_GEN13_A1_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for n in CASE_NAMES:
        for f in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_fp13_a1/{n} && "
                f"/workspace/physics_app/physics-opt --check-input -i {f}"
            )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_GEN13_A1_P2: PASS")


def inner_run(name: str) -> int:
    _bind()
    return seq08.inner_run(name)


def run_case(name: str) -> None:
    _bind()
    if not GENERATED.exists():
        build()
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq13_a1.py --inner-run {name}; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp13_a1 /workspace/{rel}/generated_fp13_a1/{name}"
    )
    result, code = seq08.analyze(name)
    result.update(sequence=13, screening_surrogate=MODE, screening_gamma=float(next(x["gamma"] for x in SPECS if x["name"] == name)))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN13_A1_CASE:", name, result.get("classification"))
    if code:
        raise SystemExit(code)


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
    found = {}
    for path in Path(root).rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [n for n in CASE_NAMES if n not in found]
    control = found.get("picard2x_control")
    comparisons = {}
    if control is not None:
        for n in CASE_NAMES[1:]:
            trial = found.get(n)
            if trial is None:
                continue
            comp = {
                "control_classification": control.get("classification"),
                "trial_classification": trial.get("classification"),
                "control_cumulative_fp": control.get("cumulative_fixed_point_iterations"),
                "trial_cumulative_fp": trial.get("cumulative_fixed_point_iterations"),
                "control_avg_fp_per_step": control.get("average_fixed_point_iterations_per_observed_step"),
                "trial_avg_fp_per_step": trial.get("average_fixed_point_iterations_per_observed_step"),
            }
            a = control.get("cumulative_fixed_point_iterations")
            b = trial.get("cumulative_fixed_point_iterations")
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a:
                comp["fp_reduction_fraction"] = 1.0 - float(b) / float(a)
            if bool(control.get("evidence_valid")) and bool(trial.get("evidence_valid")):
                comp["final_profile_parity"] = wall08._comparison(control, trial)
            comparisons[n] = comp
    summary = {
        "issue": 310,
        "sequence": 13,
        "lane": MODE,
        "classification": "GEN13_A1_EVIDENCE_COMPLETE" if not missing else "GEN13_A1_EVIDENCE_PARTIAL",
        "missing_cases": missing,
        "cases": found,
        "comparisons_vs_control": comparisons,
        "guard": "Execution success is not promotion. Require stable four-step completion, material FP reduction and equal-physics parity."
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "issue310_gen13_a1_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN13_A1_AGGREGATE:", summary["classification"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--case", choices=CASE_NAMES)
    ap.add_argument("--inner-run", choices=CASE_NAMES)
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()
    if args.p0: p0()
    elif args.p1: p1()
    elif args.p2: p2()
    elif args.inner_run: raise SystemExit(inner_run(args.inner_run))
    elif args.case: run_case(args.case)
    elif args.aggregate: aggregate()
    else: ap.error("choose an action")


if __name__ == "__main__":
    main()
