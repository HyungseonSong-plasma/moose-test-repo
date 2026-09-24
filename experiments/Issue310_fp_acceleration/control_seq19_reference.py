"""Issue #310 Generation 19: establish the coupled reference root.

This generation removes the measured banded Jacobian correction entirely and
keeps the qualified Picard-2x relaxation/physics unchanged.  The only trial
change is the coupling-aware AND criterion

    default MOOSE fixed-point residual convergence
    AND max_i |phi_i^(k)-phi_i^(k-1)| <= delta_phi_abs_tol.

Cases:
  * legacy qualified stopping rule;
  * delta_phi_abs_tol = 1e-6 V;
  * delta_phi_abs_tol = 1e-8 V.

If the two delta-phi-aware unaccelerated controls converge to the same state as
Gen18's band5 delta-phi-aware cases, the historical baseline was coupling
under-converged rather than the accelerator selecting a different physical root.
"""
from __future__ import annotations

import argparse
import csv
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
GENERATED = ROOT / "generated_fp19_reference"
RESULTS = ROOT / "results_fp19_reference"

CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 400.0
HEAVY_CYCLES = 1
RATIO = 4
FP_MAX = 3000
BASE_ALPHA = 2.0 / (1.0 + CHI_E)

SPECS = (
    {
        "name": "picard2x_legacy",
        "custom_convergence": False,
        "delta_phi_abs_tol": None,
    },
    {
        "name": "picard2x_dphi1e6",
        "custom_convergence": True,
        "delta_phi_abs_tol": 1.0e-6,
    },
    {
        "name": "picard2x_dphi1e8",
        "custom_convergence": True,
        "delta_phi_abs_tol": 1.0e-8,
    },
)
CASE_NAMES = tuple(str(x["name"]) for x in SPECS)
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
        "relaxation_factor": BASE_ALPHA,
    }


def _params(raw: dict[str, object]) -> dict[str, object]:
    spec = _spec(raw)
    with wall08._clock(spec):
        p = wall08.wall03._params(spec)
    p.update(
        heavy_to_electron_dt_ratio=RATIO,
        architecture="transient_timeaware",
        fixed_point_algorithm="picard",
        relaxation_factor=BASE_ALPHA,
        custom_convergence=bool(raw["custom_convergence"]),
        delta_phi_abs_tol=raw["delta_phi_abs_tol"],
        banded_jacobian_width=0,
    )
    return p


def _render_base(raw: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
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
    if "    no_restore = true\n" not in fast:
        raise RuntimeError("Gen19 requires qualified no_restore=true architecture")
    return parent, fast, poisson


def _add_entering_phi_probe(fast: str, poisson: str) -> tuple[str, str]:
    aux_anchor = """  [elastic_loss_candidate_out]
    type = MooseVariableFVReal
    initial_condition = 4.622905967454569
  []
[]
"""
    if fast.count(aux_anchor) != 1:
        raise RuntimeError("fast AuxVariables anchor changed")
    fast = fast.replace(
        aux_anchor,
        """  [elastic_loss_candidate_out]
    type = MooseVariableFVReal
    initial_condition = 4.622905967454569
  []
  [fp_phi_anchor_diag]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]
""",
        1,
    )

    transfer_anchor = """  [log_e_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = log_e
    variable = log_e_frozen
    execute_on = SAME_AS_MULTIAPP
  []
"""
    if fast.count(transfer_anchor) != 1:
        raise RuntimeError("to-Poisson transfer anchor changed")
    fast = fast.replace(
        transfer_anchor,
        transfer_anchor + """  [phi_anchor_to_poisson_diag]
    type = MultiAppCopyTransfer
    to_multi_app = poisson
    source_variable = potential_from_poisson
    variable = phi_anchor_frozen
    execute_on = SAME_AS_MULTIAPP
  []
""",
        1,
    )

    phi_from = """  [phi_from_poisson]
    type = MultiAppCopyTransfer
    from_multi_app = poisson
    source_variable = potential_plasma
    variable = potential_from_poisson
    execute_on = SAME_AS_MULTIAPP
  []
"""
    if fast.count(phi_from) != 1:
        raise RuntimeError("from-Poisson transfer anchor changed")
    fast = fast.replace(
        phi_from,
        phi_from + """  [phi_anchor_from_poisson_diag]
    type = MultiAppCopyTransfer
    from_multi_app = poisson
    source_variable = phi_anchor_frozen
    variable = fp_phi_anchor_diag
    execute_on = SAME_AS_MULTIAPP
  []
""",
        1,
    )

    poisson_aux = """  [log_e_frozen]
    type = MooseVariableFVReal
"""
    if poisson.count(poisson_aux) != 1:
        raise RuntimeError("Poisson AuxVariables anchor changed")
    poisson = poisson.replace(
        poisson_aux,
        """  [phi_anchor_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
""" + poisson_aux,
        1,
    )
    return fast, poisson


def _add_delta_phi_metric(fast: str, tol: float) -> str:
    material_anchor = """  [electron_sheath_factor]
    type = ADParsedFunctorMaterial
"""
    if fast.count(material_anchor) != 1:
        raise RuntimeError("FunctorMaterials anchor changed")
    fast = fast.replace(
        material_anchor,
        """  [fp_delta_phi_abs]
    type = ADParsedFunctorMaterial
    property_name = fp_delta_phi_abs
    functor_names = 'potential_from_poisson fp_phi_anchor_diag'
    functor_symbols = 'phi phi0'
    expression = 'abs(phi-phi0)'
  []
""" + material_anchor,
        1,
    )

    pp_anchor = """  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
"""
    if fast.count(pp_anchor) != 1:
        raise RuntimeError("fixed-point postprocessor anchor changed")
    fast = fast.replace(
        pp_anchor,
        """  [fp_delta_phi_max]
    type = ADElementExtremeFunctorValue
    functor = fp_delta_phi_abs
    value_type = max
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
""" + pp_anchor,
        1,
    )

    exec_anchor = "  fixed_point_algorithm = 'picard'\n"
    if fast.count(exec_anchor) != 1:
        raise RuntimeError("fixed-point algorithm anchor changed")
    fast = fast.replace(
        exec_anchor,
        exec_anchor + "  multiapp_fixed_point_convergence = gummel_delta_phi\n",
        1,
    )

    conv = f"""
[Convergence]
  [gummel_delta_phi]
    type = PhysicsDeltaPhiMultiAppConvergence
    delta_phi_pp = fp_delta_phi_max
    delta_phi_abs_tol = {tol:.17g}
  []
[]
"""
    outputs_anchor = "\n[Outputs]\n"
    if fast.count(outputs_anchor) != 1:
        raise RuntimeError("Outputs anchor changed")
    fast = fast.replace(outputs_anchor, conv + outputs_anchor, 1)

    outputs = """[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    new_row_tolerance = 1.0e-30
  []
"""
    if fast.count(outputs) != 1:
        raise RuntimeError("step CSV anchor changed")
    fast = fast.replace(
        outputs,
        outputs + """  [fp_delta_csv]
    type = CSV
    execute_on = 'MULTIAPP_FIXED_POINT_ITERATION_END'
    execute_postprocessors_on = 'MULTIAPP_FIXED_POINT_ITERATION_END'
    new_row_detection_columns = all
    new_row_tolerance = 1.0e-30
    precision = 17
    scientific_notation = true
  []
""",
        1,
    )
    return fast


def render(raw: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    parent, fast, poisson = _render_base(raw, p)
    if bool(raw["custom_convergence"]):
        fast, poisson = _add_entering_phi_probe(fast, poisson)
        fast = _add_delta_phi_metric(fast, float(raw["delta_phi_abs_tol"]))
    return parent, fast, poisson


def build(clean: bool = True) -> list[dict[str, object]]:
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    built = []
    for raw in SPECS:
        p = _params(raw)
        d = GENERATED / str(raw["name"])
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
    legacy = GENERATED / "picard2x_legacy"
    legacy_parent = (legacy / "input.i").read_text(encoding="utf-8")
    legacy_fast = (legacy / "fast_sub.i").read_text(encoding="utf-8")
    legacy_poisson = (legacy / "poisson_sub.i").read_text(encoding="utf-8")
    assert "PhysicsDeltaPhiMultiAppConvergence" not in legacy_fast
    assert "gummel_banded_correction" not in legacy_poisson

    for raw in SPECS[1:]:
        d = GENERATED / str(raw["name"])
        fast = (d / "fast_sub.i").read_text(encoding="utf-8")
        poisson = (d / "poisson_sub.i").read_text(encoding="utf-8")
        assert (d / "input.i").read_text(encoding="utf-8") == legacy_parent
        assert "gummel_banded_correction" not in poisson
        assert "gummel_band_beta" not in poisson
        assert "n_epsilon_frozen" not in poisson
        assert "TimeDerivative" not in poisson
        assert "no_restore = true" in fast
        assert f"relaxation_factor = {BASE_ALPHA:.17g}" in fast
        assert "type = PhysicsDeltaPhiMultiAppConvergence" in fast
        assert "multiapp_fixed_point_convergence = gummel_delta_phi" in fast
        assert f"delta_phi_abs_tol = {float(raw['delta_phi_abs_tol']):.17g}" in fast
        # The Poisson equation is unchanged; only a passive auxiliary copy is added.
        probe = """  [phi_anchor_frozen]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
"""
        assert probe in poisson
        assert poisson.replace(probe, "", 1) == legacy_poisson

    print("ISSUE310_GEN19_REFERENCE_P0: PASS")


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    cmds = "; ".join(
        f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp19_reference/{n}/input.i"
        for n in CASE_NAMES
    )
    base._docker("set -euo pipefail; source /environment; export PYTHONPATH=/workspace; " + cmds)
    print("ISSUE310_GEN19_REFERENCE_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for n in CASE_NAMES:
        for f in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_fp19_reference/{n} && "
                f"/workspace/physics_app/physics-opt --check-input -i {f}"
            )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_GEN19_REFERENCE_P2: PASS")


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


def _delta_phi_diagnostic(name: str) -> dict[str, object]:
    raw = next(x for x in SPECS if x["name"] == name)
    if not bool(raw["custom_convergence"]):
        return {"delta_phi_diagnostic_available": False}
    d = GENERATED / name
    rows = []
    for path in sorted(d.glob("*fp_delta_csv.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            rr = list(csv.DictReader(handle))
        if rr and "fp_delta_phi_max" in rr[0]:
            rows = rr
    if not rows:
        return {"delta_phi_diagnostic_available": False}

    groups: dict[float, list[float]] = {}
    for row in rows:
        try:
            t = float(row["time"])
            v = float(row["fp_delta_phi_max"])
        except (KeyError, ValueError):
            continue
        if t > 0.0:
            groups.setdefault(t, []).append(v)

    per_step = []
    for t, vals in sorted(groups.items()):
        per_step.append({
            "time_s": t,
            "samples": len(vals),
            "first_delta_phi_V": vals[0],
            "last_delta_phi_V": vals[-1],
            "min_delta_phi_V": min(vals),
            "max_delta_phi_V": max(vals),
        })
    return {
        "delta_phi_diagnostic_available": True,
        "delta_phi_abs_tol_V": float(raw["delta_phi_abs_tol"]),
        "delta_phi_by_step": per_step,
    }


def run_case(name: str) -> None:
    _bind()
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq19_reference.py --inner-run {name}; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp19_reference /workspace/{rel}/generated_fp19_reference"
    )
    result, code = seq08.analyze(name)
    raw = next(x for x in SPECS if x["name"] == name)
    result.update(
        sequence=19,
        banded_jacobian_width=0,
        outer_relaxation_factor=BASE_ALPHA,
        custom_convergence=bool(raw["custom_convergence"]),
        delta_phi_abs_tol=raw["delta_phi_abs_tol"],
        **_delta_phi_diagnostic(name),
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_GEN19_REFERENCE_CASE:", name, result["classification"])
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
    legacy = found.get("picard2x_legacy")
    comparisons = {}
    if legacy:
        for name in ("picard2x_dphi1e6", "picard2x_dphi1e8"):
            item = found.get(name)
            if item and bool(legacy.get("evidence_valid")) and bool(item.get("evidence_valid")):
                comparisons[f"legacy_vs_{name}"] = {
                    "final_profile_parity": wall08._comparison(legacy, item),
                    "potential_time_series_parity": seq08._potential_series_parity(legacy, item),
                }

    a = found.get("picard2x_dphi1e6")
    b = found.get("picard2x_dphi1e8")
    root_convergence = None
    if a and b and bool(a.get("evidence_valid")) and bool(b.get("evidence_valid")):
        root_convergence = {
            "final_profile_parity": wall08._comparison(a, b),
            "potential_time_series_parity": seq08._potential_series_parity(a, b),
        }

    summary = {
        "issue": 310,
        "sequence": 19,
        "classification": (
            "GEN19_REFERENCE_EVIDENCE_COMPLETE"
            if not missing else "GEN19_REFERENCE_EVIDENCE_PARTIAL"
        ),
        "missing_cases": missing,
        "cases": found,
        "legacy_comparisons": comparisons,
        "dphi1e6_vs_dphi1e8": root_convergence,
        "guard": (
            "No banded/electron-Jacobian correction is present in any Gen19 case. "
            "Physics, timestep, no_restore architecture and Picard relaxation are frozen; "
            "only the fixed-point convergence acceptance rule is changed."
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "issue310_gen19_reference_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN19_REFERENCE_AGGREGATE:", summary["classification"])


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
