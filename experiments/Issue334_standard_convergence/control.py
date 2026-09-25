#!/usr/bin/env python3
"""Issue #334 R2: replace custom delta-phi convergence with Standard MOOSE composition.

Short discriminator:
  - 1 heavy cycle / 4 electron steps
  - qualified Gen34 optimized endpoint
  - custom PhysicsDeltaPhiMultiAppConvergence versus
    DefaultMultiAppFixedPointConvergence + ParsedConvergence AND delta-phi PP.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from experiments.Issue310_fp_acceleration import control_seq34_relax2x_reference_input as gen34
from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g
from experiments.Issue310_fp_acceleration import control_seq08 as seq08
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_r2"
RESULTS = ROOT / "results_r2"

HEAVY_CYCLES = 1
FINAL_TAU = 400.0
TOL = 1.0e-6
CASE_NAMES = ("custom_convergence", "standard_convergence")

_BASE_SPEC = {
    "bandwidth": 5,
    "relaxation_factor": 0.45,
    "custom_convergence": True,
    "delta_phi_abs_tol": TOL,
    "fp_algorithm": "steffensen",
    "compute_scaling_once": True,
    "suppress_fp_anchor_output": True,
    "vector_profiles_final_only": True,
}

CUSTOM_CONV = f"""[Convergence]
  [gummel_delta_phi]
    type = PhysicsDeltaPhiMultiAppConvergence
    delta_phi_pp = fp_delta_phi_max
    delta_phi_abs_tol = {TOL:.17g}
  []
[]
"""

STANDARD_CONV = f"""[Convergence]
  [gummel_default]
    type = DefaultMultiAppFixedPointConvergence
  []
  [gummel_delta_phi_standard]
    type = ParsedConvergence
    convergence_expression = 'base & (dphi <= tol)'
    symbol_names = 'base dphi tol'
    symbol_values = 'gummel_default fp_delta_phi_max {TOL:.17g}'
  []
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
    old = "  multiapp_fixed_point_convergence = gummel_delta_phi\n"
    if fast.count(old) != 1:
        raise RuntimeError("fixed-point convergence name anchor changed")
    fast = fast.replace(
        old,
        "  multiapp_fixed_point_convergence = gummel_delta_phi_standard\n",
        1,
    )
    return fast

def build(clean: bool = True) -> None:
    _bind_clock()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    for name in CASE_NAMES:
        raw = _raw(name)
        parent, fast, poisson, p = gen34._optimized_inputs(raw)
        if name == "standard_convergence":
            fast = _standardize(fast)
        d = GENERATED / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(parent)
        (d / "fast_sub.i").write_text(fast)
        (d / "poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(json.dumps({**p, "r2_variant": name}, indent=2, sort_keys=True) + "\n")

def p0() -> None:
    build()
    a = GENERATED / "custom_convergence"
    b = GENERATED / "standard_convergence"
    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert (a / "poisson_sub.i").read_text() == (b / "poisson_sub.i").read_text()
    fa = (a / "fast_sub.i").read_text()
    fb = (b / "fast_sub.i").read_text()
    assert "PhysicsDeltaPhiMultiAppConvergence" in fa
    assert "PhysicsDeltaPhiMultiAppConvergence" not in fb
    assert "type = DefaultMultiAppFixedPointConvergence" in fb
    assert "type = ParsedConvergence" in fb
    assert "convergence_expression = 'base & (dphi <= tol)'" in fb
    assert "symbol_values = 'gummel_default fp_delta_phi_max 9.9999999999999995e-07'" in fb
    assert "multiapp_fixed_point_convergence = gummel_delta_phi_standard" in fb
    assert "functor = fp_delta_phi_abs" in fa and "functor = fp_delta_phi_abs" in fb
    assert "execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'" in fa
    assert "execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'" in fb
    print("ISSUE334_R2_P0: PASS")

def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for name in CASE_NAMES:
        for fname in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_r2/{name} && "
                f"/workspace/physics_app/physics-opt --check-input -i {fname}"
            )
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE334_R2_P2: PASS")

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
            cwd=GENERATED / name, stdout=h, stderr=subprocess.STDOUT, check=False
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
    result["r2_variant"] = name
    (RESULTS / f"{name}_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
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
        f"chmod -R a+rwX /workspace/{rel}/results_r2 /workspace/{rel}/generated_r2; exit $rc"
    )
    runs = {}
    codes = []
    for name in CASE_NAMES:
        r, c = _analyze(name)
        runs[name] = r
        codes.append(c)
    a, b = runs[CASE_NAMES[0]], runs[CASE_NAMES[1]]
    profile = wall08._comparison(a, b)
    trajectory = seq08._potential_series_parity(a, b)
    fp_a = [x["fixed_point_iterations"] for x in a.get("fixed_point_time_series", []) if x.get("time_s", 0) > 0]
    fp_b = [x["fixed_point_iterations"] for x in b.get("fixed_point_time_series", []) if x.get("time_s", 0) > 0]
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
        "runtime_ratio_standard_over_custom": b["elapsed_seconds"]/a["elapsed_seconds"],
    }
    valid = all(c == 0 for c in codes) and bool(a.get("evidence_valid")) and bool(b.get("evidence_valid"))
    out = {
        "issue": 334,
        "case": "short_ab",
        "classification": "R2_SHORT_COMPLETE" if valid else "R2_SHORT_INVALID",
        "evidence_valid": valid,
        "runs": runs,
        "comparison": comparison,
        "semantic_note": "Standard ParsedConvergence preserves nominal AND stopping logic; non-finite delta-phi fail-fast behavior remains a separate acceptance check."
    }
    (RESULTS / "short_ab_result.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("ISSUE334_R2_SHORT", json.dumps(comparison, sort_keys=True))
    if not valid:
        raise SystemExit(2)

def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    matches = list(Path(root).rglob("short_ab_result.json"))
    if not matches:
        raise SystemExit("missing R2 result")
    result = json.loads(matches[-1].read_text())
    comp = result["comparison"]
    qualified = bool(result.get("evidence_valid")) and bool(comp.get("fp_history_equal"))
    if comp.get("max_profile_metric") is not None:
        qualified = qualified and float(comp["max_profile_metric"]) <= 1.0e-7
    result["terminal_short_classification"] = (
        "STANDARD_REPLACEMENT_SHORT_GATE_PASS" if qualified else "R2_SHORT_GATE_FAIL"
    )
    Path("r2_aggregate.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("ISSUE334_R2_AGGREGATE", result["terminal_short_classification"])
    if not qualified:
        raise SystemExit(3)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--case")
    ap.add_argument("--inner-pair", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    a = ap.parse_args()
    if a.p0: p0()
    elif a.p2: p2()
    elif a.inner_pair: raise SystemExit(_inner_pair())
    elif a.case == "short_ab": run_case()
    elif a.aggregate: aggregate()
    else: ap.error("choose an action")

if __name__ == "__main__":
    main()

