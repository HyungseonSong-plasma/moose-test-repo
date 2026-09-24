"""Issue #310 Generation 13 A1 small-gamma screened-Poisson discriminator.

Same qualified time-aware Picard-2x physics as Sequence08.  Only the Gummel
Poisson iteration operator is modified, using gamma in {0.025, 0.050}; the
screening correction vanishes at the converged fixed point.
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
MODE = "A1"
CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 400.0
HEAVY_CYCLES = 1
RATIO = 4
FP_MAX = 3000
E_OVER_EPS0 = 1.8095128179727827e-8
GAMMAS = (0.025, 0.050)
wall08.FINAL_TAU = FINAL_TAU

SPECS = (
    {"name": "picard2x_control", "gamma": 0.0},
    {"name": "a1_gamma0025", "gamma": 0.025},
    {"name": "a1_gamma0050", "gamma": 0.050},
)
CASE_NAMES = tuple(str(x["name"]) for x in SPECS)


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
        screening_mode=MODE,
        screening_gamma=float(raw["gamma"]),
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
    if fast.count(transfer_anchor) != 1:
        raise RuntimeError("log_e transfer anchor changed")

    if MODE == "A1":
        diagnostics = """  [mean_energy_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = mean_energy_out
    variable = mean_energy_frozen
    execute_on = SAME_AS_MULTIAPP
  []
"""
        aux = """  [mean_energy_frozen]
    type = MooseVariableFVReal
    initial_condition = 5.73276
  []
"""
    else:
        diagnostics = """  [mobility_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = mobility_out
    variable = mobility_frozen
    execute_on = SAME_AS_MULTIAPP
  []
  [diffusion_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = diffusion_out
    variable = diffusion_frozen
    execute_on = SAME_AS_MULTIAPP
  []
"""
        aux = """  [mobility_frozen]
    type = MooseVariableFVReal
    initial_condition = 9755.114369721427
  []
  [diffusion_frozen]
    type = MooseVariableFVReal
    initial_condition = 41257.29899041419
  []
"""

    diagnostics += """  [phi_anchor_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = potential_from_poisson
    variable = phi_anchor_frozen
    execute_on = SAME_AS_MULTIAPP
  []
"""
    fast = fast.replace(transfer_anchor, transfer_anchor + diagnostics, 1)

    aux_anchor = """  [log_e_frozen]
    type = MooseVariableFVReal
"""
    if poisson.count(aux_anchor) != 1:
        raise RuntimeError("Poisson aux anchor changed")
    poisson = poisson.replace(
        aux_anchor,
        aux + """  [phi_anchor_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
""" + aux_anchor,
        1,
    )

    material_anchor = """  [plasma_charge]
    type = PhysicsPlasmaChargeDensityMaterial
"""
    if poisson.count(material_anchor) != 1:
        raise RuntimeError("plasma charge anchor changed")

    if MODE == "A1":
        beta_material = f"""  [gummel_screening]
    type = ADParsedFunctorMaterial
    property_name = gummel_screen_beta
    functor_names = 'electron_density_m3 mean_energy_frozen'
    functor_symbols = 'ne mean_ev'
    expression = '{gamma:.17g}*{E_OVER_EPS0:.17g}*ne/((2.0/3.0)*max(mean_ev,1.0e-6))'
  []
"""
    else:
        beta_material = f"""  [gummel_screening]
    type = ADParsedFunctorMaterial
    property_name = gummel_screen_beta
    functor_names = 'electron_density_m3 mobility_frozen diffusion_frozen'
    functor_symbols = 'ne mu diff'
    expression = '{gamma:.17g}*{E_OVER_EPS0:.17g}*ne*mu/max(diff,1.0e-300)'
  []
"""

    screening_material = beta_material + """  [gummel_screen_residual_source]
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
        (d / "case.json").write_text(json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        built.append(p)
    return built


def p0() -> None:
    built = build()
    assert len(built) == 3
    control = GENERATED / "picard2x_control"
    assert "gummel_screen_reaction" not in (control / "poisson_sub.i").read_text()
    parent0 = (control / "input.i").read_text()
    for raw in SPECS[1:]:
        d = GENERATED / str(raw["name"])
        assert (d / "input.i").read_text() == parent0
        pp = (d / "poisson_sub.i").read_text()
        ff = (d / "fast_sub.i").read_text()
        assert "type = PhysicsFVSpeciesReactionSource" in pp
        assert "gummel_screen_residual_source" in pp
        assert "screening_correction_avg" in pp
        assert f"{float(raw['gamma']):.17g}*" in pp
        assert "no_restore = true" in ff
        if MODE == "A1":
            assert "mean_energy_to_poisson" in ff
            assert "mobility_to_poisson" not in ff
        else:
            assert "mobility_to_poisson" in ff and "diffusion_to_poisson" in ff
            assert "mean_energy_to_poisson" not in ff
        assert "TimeDerivative" not in pp
    print(f"ISSUE310_GEN13_{MODE}_P0: PASS")


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
    print(f"ISSUE310_GEN13_{MODE}_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for n in CASE_NAMES:
        for f in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(f"cd /workspace/{rel}/generated_fp13_a1/{n} && /workspace/physics_app/physics-opt --check-input -i {f}")
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print(f"ISSUE310_GEN13_{MODE}_P2: PASS")


def inner_run(name: str) -> int:
    _bind()
    RESULTS.mkdir(parents=True, exist_ok=True)
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
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq13_a1.py --inner-run {name}; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp13_a1 /workspace/{rel}/generated_fp13_a1"
    )
    result, code = seq08.analyze(name)
    result.update(sequence=13, screening_mode=MODE, screening_gamma=float(next(x["gamma"] for x in SPECS if x["name"] == name)))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ISSUE310_GEN13_{MODE}_CASE:", name, result["classification"])
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
    if control:
        cfp = control.get("cumulative_fixed_point_iterations")
        for raw in SPECS[1:]:
            name = str(raw["name"])
            item = found.get(name)
            if not item:
                continue
            fp = item.get("cumulative_fixed_point_iterations")
            comparisons[name] = {
                "gamma": float(raw["gamma"]),
                "evidence_valid": bool(item.get("evidence_valid")),
                "cumulative_fixed_point_iterations": fp,
                "average_fixed_point_iterations_per_observed_step": item.get("average_fixed_point_iterations_per_observed_step"),
                "fixed_point_reduction_fraction_vs_control": (
                    1.0 - float(fp) / float(cfp)
                    if isinstance(fp, (int, float)) and isinstance(cfp, (int, float)) and cfp
                    else None
                ),
                "classification": item.get("classification"),
            }
    summary = {
        "issue": 310,
        "sequence": 13,
        "lane": MODE,
        "classification": "GEN13_SCREENING_EVIDENCE_COMPLETE" if not missing else "GEN13_SCREENING_EVIDENCE_PARTIAL",
        "missing_cases": missing,
        "control": control,
        "trials": comparisons,
        "cases": found,
        "guard": "Screening changes only the Gummel iteration operator and vanishes at the fixed point; promotion still requires parity and later long-horizon validation.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"issue310_gen13_a1_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ISSUE310_GEN13_{MODE}_AGGREGATE:", summary["classification"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--inner-run", choices=CASE_NAMES)
    ap.add_argument("--case", choices=CASE_NAMES)
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()
    if args.p0: p0()
    elif args.p1: p1()
    elif args.p2: p2()
    elif args.inner_run: raise SystemExit(inner_run(args.inner_run))
    elif args.case: run_case(args.case)
    elif args.aggregate: aggregate()
    else: ap.error("choose one action")


if __name__ == "__main__":
    main()
