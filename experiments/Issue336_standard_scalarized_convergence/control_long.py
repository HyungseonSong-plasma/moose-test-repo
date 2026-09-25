#!/usr/bin/env python3
"""Issue #336 R2b full qualification.

Qualified custom PhysicsDeltaPhiMultiAppConvergence versus the standard-only
scalarized AND gate over the full Gen34 19.941 ns horizon.

Two same-run orders are executed:
  pair_ab: custom -> standard
  pair_ba: standard -> custom
"""
from __future__ import annotations

import argparse
import json
import math
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
from experiments.Issue336_standard_scalarized_convergence import control as r2b

GENERATED = ROOT / "generated_r2b_long"
RESULTS = ROOT / "results_r2b_long"

HEAVY_CYCLES = 88
FINAL_TAU = 400.0 * HEAVY_CYCLES
DELTA_PHI_TOL = 1.0e-6

SPECS = (
    {
        "name": "custom_and_20ns",
        "role": "custom",
        "bandwidth": 5,
        "relaxation_factor": 0.45,
        "custom_convergence": True,
        "delta_phi_abs_tol": DELTA_PHI_TOL,
        "fp_algorithm": "steffensen",
        "compute_scaling_once": True,
        "suppress_fp_anchor_output": True,
        "vector_profiles_final_only": True,
    },
    {
        "name": "standard_scalar_and_20ns",
        "role": "standard",
        "bandwidth": 5,
        "relaxation_factor": 0.45,
        "custom_convergence": True,
        "delta_phi_abs_tol": DELTA_PHI_TOL,
        "fp_algorithm": "steffensen",
        "compute_scaling_once": True,
        "suppress_fp_anchor_output": True,
        "vector_profiles_final_only": True,
    },
)
CASE_NAMES = tuple(x["name"] for x in SPECS)
PAIR_ORDERS = {
    "pair_ab": (CASE_NAMES[0], CASE_NAMES[1]),
    "pair_ba": (CASE_NAMES[1], CASE_NAMES[0]),
}

def _bind() -> None:
    gen34.HEAVY_CYCLES = HEAVY_CYCLES
    gen34.FINAL_TAU = FINAL_TAU
    gen34._bind_clock()

    seq08.GENERATED = GENERATED
    seq08.RESULTS = RESULTS
    seq08.FINAL_TAU = FINAL_TAU
    seq08.HEAVY_CYCLES = HEAVY_CYCLES
    seq08.CASE_NAMES = CASE_NAMES
    seq08.SPECS = tuple(g._spec(x) for x in SPECS)
    wall08.FINAL_TAU = FINAL_TAU

def build(clean: bool = True) -> None:
    _bind()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    for raw in SPECS:
        parent, fast, poisson, params = gen34._optimized_inputs(raw)
        if raw["role"] == "standard":
            fast = r2b._standardize(fast)

        d = GENERATED / raw["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(parent)
        (d / "fast_sub.i").write_text(fast)
        (d / "poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(
            json.dumps(
                {
                    **params,
                    "issue": 336,
                    "phase": "R2b",
                    "role": raw["role"],
                    "heavy_cycles": HEAVY_CYCLES,
                    "electron_steps": HEAVY_CYCLES * 4,
                    "final_tau": FINAL_TAU,
                    "convergence_owner": (
                        "PhysicsDeltaPhiMultiAppConvergence"
                        if raw["role"] == "custom"
                        else "DefaultMultiAppFixedPointConvergence+ParsedPostprocessor+Terminator"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

def p0() -> None:
    build()
    a = GENERATED / CASE_NAMES[0]
    b = GENERATED / CASE_NAMES[1]

    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert (a / "poisson_sub.i").read_text() == (b / "poisson_sub.i").read_text()

    fa = (a / "fast_sub.i").read_text()
    fb = (b / "fast_sub.i").read_text()

    assert "type = PhysicsDeltaPhiMultiAppConvergence" in fa
    assert "type = PhysicsDeltaPhiMultiAppConvergence" not in fb
    assert "type = DefaultMultiAppFixedPointConvergence" in fb
    assert "type = ParsedConvergence" not in fb
    assert "type = ParsedPostprocessor" in fb
    assert "type = Residual" in fb
    assert "type = Terminator" in fb
    assert "custom_pp = fp_and_gate" in fb
    assert "direct_pp_value = true" in fb
    assert "disable_fixed_point_residual_norm_check = true" in fb
    assert "multiapp_fixed_point_convergence = gummel_scalar_and" in fb
    assert "num_steps = 352" in fa
    assert "num_steps = 352" in fb
    assert "num_steps = 88" in (a / "input.i").read_text()
    assert "num_steps = 88" in (b / "input.i").read_text()

    print("ISSUE336_R2B_LONG_P0: PASS")

def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for name in CASE_NAMES:
        for fname in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_r2b_long/{name} && "
                f"/workspace/physics_app/physics-opt --check-input -i {fname}"
            )

    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE336_R2B_LONG_P1: PASS")

def _inner_run(name: str) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    log = RESULTS / f"{name}_runtime.log"
    start = time.perf_counter()
    with log.open("w") as handle:
        cp = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-t", "-i", "input.i"],
            cwd=GENERATED / name,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - start
    (RESULTS / f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    (RESULTS / f"{name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    return cp.returncode

def _inner_pair(pair: str) -> int:
    first = 0
    for name in PAIR_ORDERS[pair]:
        rc = _inner_run(name)
        if rc and not first:
            first = rc
    return first

def _analyze(name: str) -> tuple[dict[str, object], int]:
    _bind()
    result, code = seq08.analyze(name)
    result["elapsed_seconds"] = float((RESULTS / f"{name}_elapsed_seconds.txt").read_text())
    result["issue"] = 336
    result["phase"] = "R2b"
    result["role"] = next(x["role"] for x in SPECS if x["name"] == name)
    (RESULTS / f"{name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result, code

def run_pair(pair: str) -> None:
    _bind()
    if not GENERATED.exists():
        build()

    rel = ROOT.relative_to(REPO)
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"set +e; python3 /workspace/{rel}/control_long.py --inner-pair {pair}; rc=$?; set -e; "
        f"chmod -R a+rwX /workspace/{rel}/results_r2b_long /workspace/{rel}/generated_r2b_long; "
        "exit $rc"
    )

    runs = {}
    codes = []
    for name in PAIR_ORDERS[pair]:
        result, code = _analyze(name)
        runs[name] = result
        codes.append(code)

    custom = runs[CASE_NAMES[0]]
    standard = runs[CASE_NAMES[1]]

    profile = wall08._comparison(custom, standard)
    trajectory = seq08._potential_series_parity(custom, standard)

    fp_custom = [
        x["fixed_point_iterations"]
        for x in custom.get("fixed_point_time_series", [])
        if x.get("time_s", 0) > 0
    ]
    fp_standard = [
        x["fixed_point_iterations"]
        for x in standard.get("fixed_point_time_series", [])
        if x.get("time_s", 0) > 0
    ]

    max_profile = max(
        abs(float(v)) for v in profile.values() if isinstance(v, (int, float))
    )
    trajectory_metrics = [
        abs(float(v))
        for k, v in trajectory.items()
        if isinstance(v, (int, float)) and k.endswith("_delta")
    ]
    max_traj = max(trajectory_metrics) if trajectory_metrics else 0.0

    tc = float(custom["elapsed_seconds"])
    ts = float(standard["elapsed_seconds"])

    comparison = {
        "custom_elapsed_s": tc,
        "standard_elapsed_s": ts,
        "runtime_ratio_standard_over_custom": ts / tc,
        "fp_history_equal": fp_custom == fp_standard,
        "custom_fp_total": sum(fp_custom),
        "standard_fp_total": sum(fp_standard),
        "custom_fp_history": fp_custom,
        "standard_fp_history": fp_standard,
        "max_profile_metric": max_profile,
        "max_trajectory_abs_delta": max_traj,
        "profile": profile,
        "trajectory": trajectory,
    }

    valid = (
        all(c == 0 for c in codes)
        and bool(custom.get("evidence_valid"))
        and bool(standard.get("evidence_valid"))
        and fp_custom == fp_standard
        and max_profile <= 1.0e-10
        and max_traj <= 1.0e-9
    )

    out = {
        "issue": 336,
        "phase": "R2b",
        "case": pair,
        "classification": "R2B_LONG_SCIENTIFIC_PASS" if valid else "R2B_LONG_FAIL",
        "evidence_valid": valid,
        "comparison": comparison,
        "runs": runs,
    }
    (RESULTS / f"{pair}_result.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE336_R2B_LONG_PAIR", pair, json.dumps(comparison, sort_keys=True))
    if not valid:
        raise SystemExit(2)

def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")

    found = {}
    for path in Path(root).rglob("*_result.json"):
        item = json.loads(path.read_text())
        if item.get("case") in PAIR_ORDERS:
            found[item["case"]] = item

    if len(found) != 2:
        raise SystemExit("missing R2b pair evidence")

    scientific_valid = all(bool(x.get("evidence_valid")) for x in found.values())
    ratios = [
        float(found[p]["comparison"]["runtime_ratio_standard_over_custom"])
        for p in ("pair_ab", "pair_ba")
    ]
    geo = math.sqrt(ratios[0] * ratios[1])

    exact_fp = all(
        bool(found[p]["comparison"]["fp_history_equal"])
        for p in ("pair_ab", "pair_ba")
    )

    classification = (
        "STANDARD_REPLACEMENT_QUALIFIED"
        if scientific_valid and exact_fp and geo <= 1.05
        else (
            "SCIENTIFICALLY_EQUIVALENT_RUNTIME_REGRESSION"
            if scientific_valid and exact_fp
            else "STANDARD_CANDIDATE_SEMANTICS_MISMATCH"
        )
    )

    summary = {
        "issue": 336,
        "phase": "R2b",
        "classification": classification,
        "evidence_valid": scientific_valid,
        "exact_fp_history_both_orders": exact_fp,
        "runtime_gate_pass": geo <= 1.05,
        "geometric_mean_runtime_ratio_standard_over_custom": geo,
        "runtime_regression_fraction": geo - 1.0,
        "pairs": found,
        "nonfinite_guard": (
            "Qualified separately by the current branch short prepare probes "
            "for NaN and +Inf using standard Terminator."
        ),
    }

    Path("r2b_long_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE336_R2B_LONG_AGGREGATE", json.dumps(summary, sort_keys=True))
    if classification != "STANDARD_REPLACEMENT_QUALIFIED":
        raise SystemExit(3)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--inner-pair", choices=PAIR_ORDERS)
    ap.add_argument("--case", choices=PAIR_ORDERS)
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()

    if args.p0:
        p0()
    elif args.p1:
        p1()
    elif args.inner_pair:
        raise SystemExit(_inner_pair(args.inner_pair))
    elif args.case:
        run_pair(args.case)
    elif args.aggregate:
        aggregate()
    else:
        ap.error("choose an action")

if __name__ == "__main__":
    main()
