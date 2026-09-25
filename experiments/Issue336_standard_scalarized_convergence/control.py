#!/usr/bin/env python3
"""Issue #336 R2b: standard-only scalarized AND convergence discriminator.

A: qualified DeltaPhiMultiAppConvergence
B: DefaultMultiAppFixedPointConvergence + standard Residual/ParsedPostprocessor gate

Short horizon: 1 heavy cycle / 4 electron steps.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq34_relax2x_reference_input as gen34
from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g
from experiments.Issue310_fp_acceleration import control_seq08 as seq08
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08

GENERATED = ROOT / "generated_r2b"
RESULTS = ROOT / "results_r2b"

HEAVY_CYCLES = 1
FINAL_TAU = 400.0
DPHI_TOL = 1.0e-6
FP_ABS_TOL = 1.0e-12
FP_REL_TOL = 1.0e-8
CASE_NAMES = ("custom_and", "standard_scalar_and")

_BASE_SPEC = {
    "bandwidth": 5,
    "relaxation_factor": 0.45,
    "custom_convergence": True,
    "delta_phi_abs_tol": DPHI_TOL,
    "fp_algorithm": "steffensen",
    "compute_scaling_once": True,
    "suppress_fp_anchor_output": True,
    "vector_profiles_final_only": True,
}

CUSTOM_CONV = f"""[Convergence]
  [gummel_delta_phi]
    type = DeltaPhiMultiAppConvergence
    delta_phi_pp = fp_delta_phi_max
    delta_phi_abs_tol = {DPHI_TOL:.17g}
  []
[]
"""

STANDARD_CONV = f"""[Convergence]
  [gummel_scalar_and]
    type = DefaultMultiAppFixedPointConvergence
    fixed_point_min_its = 2
    fixed_point_max_its = 3000
    disable_fixed_point_residual_norm_check = true
    custom_pp = fp_and_gate
    direct_pp_value = true
    custom_abs_tol = 0.5
    custom_rel_tol = 1.0e-50
    accept_on_max_fixed_point_iteration = false
  []
[]
"""

STANDARD_TERMINATOR = """
[UserObjects]
  [fp_delta_phi_nonfinite_guard]
    type = Terminator
    expression = 'fp_delta_phi_max-fp_delta_phi_max'
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
    fail_mode = HARD
    error_level = ERROR
    message = 'Non-finite delta-phi convergence metric'
  []
[]
"""

STANDARD_PP = f"""
  [fp_residual_initial]
    type = Residual
    residual_type = COMPUTE
    execute_on = 'MULTIAPP_FIXED_POINT_BEGIN'
  []
  [fp_residual_current]
    type = Residual
    residual_type = COMPUTE
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
  [fp_and_gate]
    type = ParsedPostprocessor
    pp_names = 'fp_residual_current fp_residual_initial fp_delta_phi_max'
    pp_symbols = 'R R0 dphi'
    expression = 'if((((R < {FP_ABS_TOL:.17g}) | (R < R0*{FP_REL_TOL:.17g})) & (dphi <= {DPHI_TOL:.17g})),0,2)'
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
"""

def _bind_clock() -> None:
    gen34.HEAVY_CYCLES = HEAVY_CYCLES
    gen34.FINAL_TAU = FINAL_TAU
    gen34._bind_clock()

def _raw(name: str) -> dict[str, object]:
    return {"name": name, "role": "optimized", **_BASE_SPEC}

def _standardize(fast: str) -> str:
    if fast.count(CUSTOM_CONV) != 1:
        raise RuntimeError("custom convergence block changed")
    fast = fast.replace(CUSTOM_CONV, STANDARD_CONV, 1)

    old_name = "  multiapp_fixed_point_convergence = gummel_delta_phi\n"
    if fast.count(old_name) != 1:
        raise RuntimeError("convergence name anchor changed")
    fast = fast.replace(
        old_name,
        "  multiapp_fixed_point_convergence = gummel_scalar_and\n",
        1,
    )

    # Insert the standard residual/gate Postprocessors next to the existing
    # fp_delta_phi_max Postprocessor. The existing delta-phi diagnostic remains
    # byte-identical in both A and B.
    pp_anchor = """  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
"""
    if fast.count(pp_anchor) != 1:
        raise RuntimeError("postprocessor anchor changed")
    fast = fast.replace(pp_anchor, STANDARD_PP + pp_anchor, 1)

    # Convergence parameters are now owned by the explicit standard
    # DefaultMultiAppFixedPointConvergence object, not the Executioner.
    for line in (
        "  fixed_point_min_its = 2\n",
        "  fixed_point_max_its = 3000\n",
        "  fixed_point_rel_tol = 1.0e-8\n",
        "  fixed_point_abs_tol = 1.0e-12\n",
        "  accept_on_max_fixed_point_iteration = false\n",
    ):
        if fast.count(line) < 1:
            raise RuntimeError(f"executioner FP parameter anchor changed: {line.strip()}")
        # Executioner occurs before [Convergence], so first occurrence is the
        # Executioner copy.
        fast = fast.replace(line, "", 1)

    outputs_anchor = "\n[Outputs]\n"
    if fast.count(outputs_anchor) != 1:
        raise RuntimeError("Outputs anchor changed for Terminator insertion")
    fast = fast.replace(outputs_anchor, "\n" + STANDARD_TERMINATOR + outputs_anchor, 1)
    return fast

def build(clean: bool = True) -> None:
    _bind_clock()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    for name in CASE_NAMES:
        parent, fast, poisson, params = gen34._optimized_inputs(_raw(name))
        if name == "standard_scalar_and":
            fast = _standardize(fast)

        d = GENERATED / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(parent)
        (d / "fast_sub.i").write_text(fast)
        (d / "poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(
            json.dumps({**params, "r2b_variant": name}, indent=2, sort_keys=True) + "\n"
        )

    probe_template = """[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Variables]
  [u]
    order = FIRST
    family = LAGRANGE
    initial_condition = 0
  []
[]

[Kernels]
  [diff]
    type = Diffusion
    variable = u
  []
  [time]
    type = TimeDerivative
    variable = u
  []
[]

[Postprocessors]
  [bad]
    type = ParsedPostprocessor
    expression = '__BAD_EXPR__'
    evalerror_behavior = nan
    execute_on = TIMESTEP_END
  []
[]

[UserObjects]
  [catch_nonfinite]
    type = Terminator
    expression = 'bad-bad'
    execute_on = TIMESTEP_END
    fail_mode = HARD
    error_level = ERROR
    message = 'NONFINITE_GATE_CAUGHT'
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]

[Outputs]
  console = true
[]
"""
    (GENERATED / "nonfinite_nan_probe.i").write_text(
        probe_template.replace("__BAD_EXPR__", "1/0")
    )
    (GENERATED / "nonfinite_inf_probe.i").write_text(
        probe_template.replace("__BAD_EXPR__", "1e308*1e308")
    )

def p0() -> None:
    build()
    a = GENERATED / "custom_and"
    b = GENERATED / "standard_scalar_and"

    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert (a / "poisson_sub.i").read_text() == (b / "poisson_sub.i").read_text()

    fa = (a / "fast_sub.i").read_text()
    fb = (b / "fast_sub.i").read_text()

    assert "type = DeltaPhiMultiAppConvergence" in fa
    assert "type = DeltaPhiMultiAppConvergence" not in fb
    assert "type = ParsedConvergence" not in fb
    assert "type = DefaultMultiAppFixedPointConvergence" in fb
    assert "multiapp_fixed_point_convergence = gummel_scalar_and" in fb
    assert "disable_fixed_point_residual_norm_check = true" in fb
    assert "custom_pp = fp_and_gate" in fb
    assert "direct_pp_value = true" in fb
    assert "type = ParsedPostprocessor" in fb
    assert "type = Residual" in fb
    assert "residual_type = COMPUTE" in fb
    assert "MULTIAPP_FIXED_POINT_BEGIN" in fb
    assert "MULTIAPP_FIXED_POINT_CONVERGENCE" in fb
    assert "functor = fp_delta_phi_abs" in fa and "functor = fp_delta_phi_abs" in fb
    assert "type = Terminator" in fb
    assert "expression = 'fp_delta_phi_max-fp_delta_phi_max'" in fb
    assert "Non-finite delta-phi convergence metric" in fb

    print("ISSUE336_R2B_P0: PASS")

def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for name in CASE_NAMES:
        for fname in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_r2b/{name} && "
                f"/workspace/physics_app/physics-opt --check-input -i {fname}"
            )

    probe_dir = f"/workspace/{rel}/generated_r2b"
    probe_checks = (
        f"cd {probe_dir}; "
        "for probe in nonfinite_nan_probe.i nonfinite_inf_probe.i; do "
        "set +e; /workspace/physics_app/physics-opt -i $probe > $probe.log 2>&1; rc=$?; set -e; "
        "echo PROBE=$probe RC=$rc; tail -n 80 $probe.log; "
        "test $rc -ne 0; grep -q NONFINITE_GATE_CAUGHT $probe.log; "
        "done"
    )
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks) + "; " + probe_checks
    )
    print("ISSUE336_R2B_P2: PASS")

def _bind_analysis() -> None:
    _bind_clock()
    seq08.GENERATED = GENERATED
    seq08.RESULTS = RESULTS
    seq08.FINAL_TAU = FINAL_TAU
    seq08.HEAVY_CYCLES = HEAVY_CYCLES
    seq08.CASE_NAMES = CASE_NAMES
    seq08.SPECS = tuple(g._spec(_raw(n)) for n in CASE_NAMES)
    wall08.FINAL_TAU = FINAL_TAU

def _inner_run(name: str) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    log = RESULTS / f"{name}_runtime.log"
    t0 = time.perf_counter()
    with log.open("w") as h:
        cp = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-t", "-i", "input.i"],
            cwd=GENERATED / name,
            stdout=h,
            stderr=subprocess.STDOUT,
            check=False,
        )
    (RESULTS / f"{name}_elapsed_seconds.txt").write_text(f"{time.perf_counter()-t0:.9f}\n")
    (RESULTS / f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    return cp.returncode

def _inner_pair() -> int:
    first = 0
    for name in CASE_NAMES:
        rc = _inner_run(name)
        if rc and not first:
            first = rc
    return first

def _analyze(name: str) -> tuple[dict[str, object], int]:
    _bind_analysis()
    result, code = seq08.analyze(name)
    result["elapsed_seconds"] = float((RESULTS / f"{name}_elapsed_seconds.txt").read_text())
    result["r2b_variant"] = name
    (RESULTS / f"{name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result, code

def run_case() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)

    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"set +e; python3 /workspace/{rel}/control.py --inner-pair; rc=$?; set -e; "
        f"chmod -R a+rwX /workspace/{rel}/results_r2b /workspace/{rel}/generated_r2b; exit $rc"
    )

    runs = {}
    codes = []
    for name in CASE_NAMES:
        result, code = _analyze(name)
        runs[name] = result
        codes.append(code)

    a, b = runs[CASE_NAMES[0]], runs[CASE_NAMES[1]]
    profile = wall08._comparison(a, b)
    trajectory = seq08._potential_series_parity(a, b)

    fp_a = [
        x["fixed_point_iterations"]
        for x in a.get("fixed_point_time_series", [])
        if x.get("time_s", 0) > 0
    ]
    fp_b = [
        x["fixed_point_iterations"]
        for x in b.get("fixed_point_time_series", [])
        if x.get("time_s", 0) > 0
    ]

    metrics = [abs(float(v)) for v in profile.values() if isinstance(v, (int, float))]
    comparison = {
        "fp_history_custom": fp_a,
        "fp_history_standard": fp_b,
        "fp_history_equal": fp_a == fp_b,
        "fp_total_custom": a.get("cumulative_fixed_point_iterations"),
        "fp_total_standard": b.get("cumulative_fixed_point_iterations"),
        "profile_parity": profile,
        "max_profile_metric": max(metrics) if metrics else None,
        "potential_time_series_parity": trajectory,
        "custom_elapsed_seconds": a["elapsed_seconds"],
        "standard_elapsed_seconds": b["elapsed_seconds"],
        "runtime_ratio_standard_over_custom": b["elapsed_seconds"] / a["elapsed_seconds"],
    }

    valid = (
        all(c == 0 for c in codes)
        and bool(a.get("evidence_valid"))
        and bool(b.get("evidence_valid"))
    )

    out = {
        "issue": 336,
        "case": "short_ab",
        "classification": "R2B_SHORT_COMPLETE" if valid else "R2B_SHORT_INVALID",
        "evidence_valid": valid,
        "runs": runs,
        "comparison": comparison,
    }
    (RESULTS / "short_ab_result.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE336_R2B_SHORT", json.dumps(comparison, sort_keys=True))

    if not valid:
        raise SystemExit(2)

def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    matches = list(Path(root).rglob("short_ab_result.json"))
    if not matches:
        raise SystemExit("missing R2b result")

    result = json.loads(matches[-1].read_text())
    comp = result["comparison"]
    qualified = bool(result.get("evidence_valid")) and bool(comp.get("fp_history_equal"))
    if comp.get("max_profile_metric") is not None:
        qualified = qualified and float(comp["max_profile_metric"]) <= 1.0e-7

    result["terminal_short_classification"] = (
        "STANDARD_REPLACEMENT_SHORT_GATE_PASS"
        if qualified
        else "STANDARD_CANDIDATE_SEMANTICS_MISMATCH"
    )
    Path("r2b_aggregate.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("ISSUE336_R2B_AGGREGATE", result["terminal_short_classification"])
    if not qualified:
        raise SystemExit(3)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--case")
    ap.add_argument("--inner-pair", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()

    if args.p0:
        p0()
    elif args.p2:
        p2()
    elif args.inner_pair:
        raise SystemExit(_inner_pair())
    elif args.case == "short_ab":
        run_case()
    elif args.aggregate:
        aggregate()
    else:
        ap.error("choose an action")

if __name__ == "__main__":
    main()

