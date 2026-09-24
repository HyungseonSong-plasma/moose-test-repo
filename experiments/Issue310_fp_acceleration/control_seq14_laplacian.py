"""Issue #310 Generation 14: row-sum-preserving Laplacian electron-Jacobian discriminator.

Gen13 showed that diagonal screened-Poisson reactions create an artificial
absolute-potential stiffness.  This experiment instead adds

    -div(kappa_e * grad(phi - phi_anchor))

to the Poisson iteration operator on internal FV faces only.  The correction
therefore vanishes at the converged Gummel fixed point and annihilates a
constant potential shift.

Two state-aware coefficients are tested from the Gen13 direct basis Jacobian:
  nnfit    c = 0.11722721584956464
  fullfit  c = 0.28655741183724337

with
  kappa_e = c * (e/eps0) * (n_e / T_e[eV]) * dx^2.

The first coefficient matches directly measured nearest-neighbor coupling; the
second is the least-squares row-sum-preserving local-Laplacian projection of
the full 20x20 basis Jacobian.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
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
GENERATED = ROOT / "generated_fp14_laplacian"
RESULTS = ROOT / "results_fp14_laplacian"

CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 400.0
HEAVY_CYCLES = 1
RATIO = 4
FP_MAX = 3000
DX = 0.01 / 20.0
DX2 = DX * DX
E_OVER_EPS0 = 1.8095128179727827e-8
MEAN_E0_EV = 5.73276
NE0 = 1.0e16

NN_FACTOR = 0.11722721584956464
FULL_FACTOR = 0.28655741183724337

wall08.FINAL_TAU = FINAL_TAU

SPECS = (
    {"name": "picard2x_control", "laplacian_factor": 0.0, "variant": "control"},
    {"name": "laplacian_nnfit", "laplacian_factor": NN_FACTOR, "variant": "nearest_neighbor_fit"},
    {"name": "laplacian_fullfit", "laplacian_factor": FULL_FACTOR, "variant": "full_jacobian_laplacian_projection"},
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
        laplacian_factor=float(raw["laplacian_factor"]),
        laplacian_variant=str(raw["variant"]),
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


def _apply_laplacian(fast: str, poisson: str, factor: float) -> tuple[str, str]:
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

    extra_transfers = transfer_anchor + """  [n_epsilon_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = n_epsilon
    variable = n_epsilon_frozen
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
    fast = fast.replace(transfer_anchor, extra_transfers, 1)

    aux_anchor = """  [log_e_frozen]
    type = MooseVariableFVReal
"""
    if poisson.count(aux_anchor) != 1:
        raise RuntimeError("Poisson aux anchor changed")
    poisson = poisson.replace(
        aux_anchor,
        """  [n_epsilon_frozen]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [phi_anchor_frozen]
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
        raise RuntimeError("plasma charge material anchor changed")

    materials = f"""  [gummel_mean_energy]
    type = ADParsedFunctorMaterial
    property_name = gummel_mean_energy_ev
    functor_names = 'electron_density_m3 n_epsilon_frozen'
    functor_symbols = 'ne n_eps'
    expression = '{MEAN_E0_EV:.17g}*n_eps/max(ne/{NE0:.17g},1.0e-30)'
  []
  [gummel_laplacian_coefficient]
    type = ADParsedFunctorMaterial
    property_name = gummel_laplacian_coeff
    functor_names = 'electron_density_m3 gummel_mean_energy_ev'
    functor_symbols = 'ne mean_ev'
    expression = '{factor:.17g}*{E_OVER_EPS0:.17g}*ne/((2.0/3.0)*max(mean_ev,1.0e-6))*{DX2:.17g}'
  []
  [gummel_delta_phi_abs]
    type = ADParsedFunctorMaterial
    property_name = gummel_delta_phi_abs
    functor_names = 'potential_plasma phi_anchor_frozen'
    functor_symbols = 'phi phi0'
    expression = 'abs(phi-phi0)'
  []
"""
    poisson = poisson.replace(material_anchor, materials + material_anchor, 1)

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
        kernel_anchor + """  [gummel_laplacian_correction]
    type = PhysicsFVGummelLaplacianCorrection
    variable = potential_plasma
    anchor = phi_anchor_frozen
    coeff = gummel_laplacian_coeff
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
        """  [gummel_laplacian_coeff_avg]
    type = ElementAverageFunctorPostprocessor
    functor = gummel_laplacian_coeff
    execute_on = 'INITIAL FINAL'
  []
  [gummel_delta_phi_abs_avg]
    type = ElementAverageFunctorPostprocessor
    functor = gummel_delta_phi_abs
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
    factor = float(raw["laplacian_factor"])
    if factor > 0.0:
        fast, poisson = _apply_laplacian(fast, poisson, factor)
    return parent, fast, poisson


def build(clean: bool = True) -> list[dict[str, object]]:
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    built: list[dict[str, object]] = []
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
    control_parent = (control / "input.i").read_text(encoding="utf-8")
    control_poisson = (control / "poisson_sub.i").read_text(encoding="utf-8")
    assert "gummel_laplacian_correction" not in control_poisson

    for raw in SPECS[1:]:
        d = GENERATED / str(raw["name"])
        parent = (d / "input.i").read_text(encoding="utf-8")
        fast = (d / "fast_sub.i").read_text(encoding="utf-8")
        poisson = (d / "poisson_sub.i").read_text(encoding="utf-8")
        assert parent == control_parent
        assert "type = PhysicsFVGummelLaplacianCorrection" in poisson
        assert "anchor = phi_anchor_frozen" in poisson
        assert "coeff = gummel_laplacian_coeff" in poisson
        assert "n_epsilon_to_poisson" in fast
        assert "phi_anchor_to_poisson" in fast
        assert "mean_energy_to_poisson" not in fast
        assert "type = PhysicsFVSpeciesReactionSource" not in poisson
        assert "TimeDerivative" not in poisson
        assert "no_restore = true" in fast
        assert f"{float(raw['laplacian_factor']):.17g}*" in poisson

    print("ISSUE310_GEN14_LAPLACIAN_P0: PASS")


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    cmds = "; ".join(
        f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp14_laplacian/{n}/input.i"
        for n in CASE_NAMES
    )
    base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; " + cmds
    )
    print("ISSUE310_GEN14_LAPLACIAN_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for n in CASE_NAMES:
        for f in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_fp14_laplacian/{n} && "
                f"/workspace/physics_app/physics-opt --check-input -i {f}"
            )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_GEN14_LAPLACIAN_P2: PASS")


def _bind() -> None:
    seq08.GENERATED = GENERATED
    seq08.RESULTS = RESULTS
    seq08.FINAL_TAU = FINAL_TAU
    seq08.HEAVY_CYCLES = HEAVY_CYCLES
    seq08.CASE_NAMES = CASE_NAMES
    seq08.SPECS = tuple(_spec(x) for x in SPECS)
    wall08.FINAL_TAU = FINAL_TAU


def inner_run(name: str) -> int:
    _bind()
    RESULTS.mkdir(parents=True, exist_ok=True)
    return seq08.inner_run(name)


def _poisson_diagnostics(name: str) -> dict[str, object]:
    d = GENERATED / name
    candidates = sorted(d.glob("*poisson*step_csv.csv"))
    rows: list[dict[str, str]] = []
    for path in candidates:
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                current = list(csv.DictReader(handle))
        except OSError:
            continue
        if current and "gummel_laplacian_coeff_avg" in current[0]:
            rows = current
    if not rows:
        return {}

    coeffs = []
    deltas = []
    for row in rows:
        try:
            coeffs.append(float(row["gummel_laplacian_coeff_avg"]))
        except (KeyError, TypeError, ValueError):
            pass
        try:
            deltas.append(float(row["gummel_delta_phi_abs_avg"]))
        except (KeyError, TypeError, ValueError):
            pass
    out: dict[str, object] = {}
    if coeffs:
        out["laplacian_coeff_avg_min"] = min(coeffs)
        out["laplacian_coeff_avg_max"] = max(coeffs)
    if deltas:
        out["delta_phi_abs_avg_final"] = deltas[-1]
    return out


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
        f"python3 /workspace/{rel}/control_seq14_laplacian.py --inner-run {name}; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp14_laplacian /workspace/{rel}/generated_fp14_laplacian"
    )

    result, code = seq08.analyze(name)
    raw = next(x for x in SPECS if x["name"] == name)
    result.update(
        sequence=14,
        laplacian_variant=str(raw["variant"]),
        laplacian_factor=float(raw["laplacian_factor"]),
        **_poisson_diagnostics(name),
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_GEN14_LAPLACIAN_CASE:", name, result["classification"])
    if code:
        raise SystemExit(code)


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")

    found: dict[str, dict[str, object]] = {}
    for path in Path(root).rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item

    missing = [n for n in CASE_NAMES if n not in found]
    control = found.get("picard2x_control")
    trials: dict[str, object] = {}

    if control is not None:
        cfp = control.get("cumulative_fixed_point_iterations")
        for raw in SPECS[1:]:
            name = str(raw["name"])
            item = found.get(name)
            if item is None:
                continue
            fp = item.get("cumulative_fixed_point_iterations")
            comp: dict[str, object] = {
                "variant": raw["variant"],
                "factor": float(raw["laplacian_factor"]),
                "evidence_valid": bool(item.get("evidence_valid")),
                "classification": item.get("classification"),
                "cumulative_fixed_point_iterations": fp,
                "average_fixed_point_iterations_per_observed_step": item.get(
                    "average_fixed_point_iterations_per_observed_step"
                ),
                "laplacian_coeff_avg_min": item.get("laplacian_coeff_avg_min"),
                "laplacian_coeff_avg_max": item.get("laplacian_coeff_avg_max"),
                "delta_phi_abs_avg_final": item.get("delta_phi_abs_avg_final"),
            }
            if isinstance(fp, (int, float)) and isinstance(cfp, (int, float)) and cfp:
                comp["fixed_point_reduction_fraction_vs_control"] = 1.0 - float(fp) / float(cfp)
            if bool(control.get("evidence_valid")) and bool(item.get("evidence_valid")):
                comp["final_profile_parity"] = wall08._comparison(control, item)
                comp["potential_time_series_parity"] = seq08._potential_series_parity(control, item)
            trials[name] = comp

    summary = {
        "issue": 310,
        "sequence": 14,
        "classification": (
            "GEN14_LAPLACIAN_EVIDENCE_COMPLETE"
            if not missing
            else "GEN14_LAPLACIAN_EVIDENCE_PARTIAL"
        ),
        "missing_cases": missing,
        "control": control,
        "trials": trials,
        "cases": found,
        "gen13_basis_source": {
            "run": 35978463311,
            "head": "864fd4ed3a10bb1de3a25e5b8938a529fa85f8e0",
            "nn_factor": NN_FACTOR,
            "full_laplacian_projection_factor": FULL_FACTOR,
        },
        "guard": (
            "The correction is an iteration-operator preconditioner only: it acts on "
            "phi-phi_anchor on internal faces, preserves constant-potential null response, "
            "and vanishes at the converged Gummel fixed point. Promotion still requires "
            "stable performance improvement plus parity and later long-horizon validation."
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "issue310_gen14_laplacian_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN14_LAPLACIAN_AGGREGATE:", summary["classification"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--inner-run", choices=CASE_NAMES)
    ap.add_argument("--case", choices=CASE_NAMES)
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()

    if args.p0:
        p0()
    elif args.p1:
        p1()
    elif args.p2:
        p2()
    elif args.inner_run:
        raise SystemExit(inner_run(args.inner_run))
    elif args.case:
        run_case(args.case)
    elif args.aggregate:
        aggregate()
    else:
        ap.error("choose one action")


if __name__ == "__main__":
    main()
