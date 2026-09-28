#!/usr/bin/env python3
"""Issue #335 R3: Standard-MOOSE electron mean-energy discriminator.

A = qualified PhysicsElectronMeanEnergyMaterial
B = guarded ADParsedFunctorMaterial

The standard candidate must preserve the qualified algebra and fail-fast contract:
  mean_en = 5.73276 * n_epsilon / electron_density_hat
  electron_density_hat > 0
  n_epsilon >= 0
  finite inputs and output
  no floor and no clamp

Short nominal discriminator: 1 heavy cycle / 4 electron steps.
Invalid-state probes are executed before the scientific A/B run.
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

GENERATED = ROOT / "generated_r3"
RESULTS = ROOT / "results_r3"

HEAVY_CYCLES = 1
FINAL_TAU = 400.0
ENERGY_REFERENCE_EV = 5.73276
CASE_NAMES = ("custom_mean_energy", "standard_mean_energy")

_BASE_SPEC = {
    "bandwidth": 5,
    "relaxation_factor": 0.45,
    "custom_convergence": True,
    "delta_phi_abs_tol": 1.0e-6,
    "fp_algorithm": "steffensen",
    "compute_scaling_once": True,
    "suppress_fp_anchor_output": True,
    "vector_profiles_final_only": True,
}

CUSTOM_BLOCK = """  [mean_energy_bridge]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = n_epsilon
    electron_density = electron_density_hat
    energy_reference_eV = 5.73276
  []
"""

# Finite detection intentionally uses x-x == 0 with the fparser optimizer disabled.
# For NaN/Inf, x-x is NaN and the comparison is false. Invalid states are routed
# to sqrt(-abs(ne)-1), forcing NaN; evalerror_behavior=error then hard-fails.
#
# The inner guard repeats the exact quotient and rejects overflow of the output.
# There is no denominator floor, fallback value, or clamp.
STANDARD_EXPRESSION = (
    "if((((ne-ne)==0)&((eps-eps)==0)&(ne>0)&(eps>=0)),"
    "if(((({eref}*eps/ne)-({eref}*eps/ne))==0),"
    "{eref}*eps/ne,sqrt(-abs(ne)-1)),"
    "sqrt(-abs(ne)-1))"
).format(eref=repr(ENERGY_REFERENCE_EV))

STANDARD_BLOCK = f"""  [mean_energy_bridge]
    type = ADParsedFunctorMaterial
    property_name = mean_en_solved
    functor_names = 'n_epsilon electron_density_hat'
    functor_symbols = 'eps ne'
    expression = '{STANDARD_EXPRESSION}'
    disable_fpoptimizer = true
    evalerror_behavior = error
  []
"""


def _bind_clock() -> None:
    gen34.HEAVY_CYCLES = HEAVY_CYCLES
    gen34.FINAL_TAU = FINAL_TAU
    gen34._bind_clock()


def _raw(name: str) -> dict[str, object]:
    return {"name": name, "role": "optimized", **_BASE_SPEC}


def _replace_mean_energy(fast: str) -> str:
    if fast.count(CUSTOM_BLOCK) != 1:
        raise RuntimeError("qualified mean-energy block changed")
    return fast.replace(CUSTOM_BLOCK, STANDARD_BLOCK, 1)


def _probe_source(expr: str, name: str) -> str:
    return f"""  [{name}]
    type = ADParsedFunctorMaterial
    property_name = {name}
    expression = '{expr}'
    evalerror_behavior = nan
    disable_fpoptimizer = true
  []
"""


def _probe_input(variant: str, energy_expr: str, density_expr: str) -> str:
    mean_block = (
        """  [mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = probe_energy
    electron_density = probe_density
    energy_reference_eV = 5.73276
  []
"""
        if variant == "custom"
        else f"""  [mean_energy]
    type = ADParsedFunctorMaterial
    property_name = mean_en_solved
    functor_names = 'probe_energy probe_density'
    functor_symbols = 'eps ne'
    expression = '{STANDARD_EXPRESSION}'
    disable_fpoptimizer = true
    evalerror_behavior = error
  []
"""
    )
    return f"""[Mesh]
  type = GeneratedMesh
  dim = 3
  nx = 1
  ny = 1
  nz = 1
[]

[Problem]
  solve = false
[]

[FunctorMaterials]
{_probe_source(energy_expr, "probe_energy")}
{_probe_source(density_expr, "probe_density")}
{mean_block}[]

[Postprocessors]
  [force_mean_energy_eval]
    type = ADElementExtremeFunctorValue
    functor = mean_en_solved
    value_type = max
    execute_on = INITIAL
  []
[]

[Executioner]
  type = Steady
[]

[Outputs]
  console = true
[]
"""


PROBES = {
    # Valid boundary states
    "valid_nominal": ("1.0", "1.0", True),
    "valid_zero_energy": ("0.0", "1.0", True),
    # Invalid inputs
    "zero_density": ("1.0", "0.0", False),
    "negative_density": ("1.0", "-1.0", False),
    "negative_energy": ("-1.0", "1.0", False),
    "nan_density": ("1.0", "sqrt(-1)", False),
    "nan_energy": ("sqrt(-1)", "1.0", False),
    "inf_density": ("1.0", "1e308*1e308", False),
    "inf_energy": ("1e308*1e308", "1.0", False),
    # Both inputs are finite/valid but the quotient overflows.
    "overflow_output": ("1e308", "1e-308", False),
}


def build(clean: bool = True) -> None:
    _bind_clock()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    for name in CASE_NAMES:
        parent, fast, poisson, params = gen34._optimized_inputs(_raw(name))
        if name == "standard_mean_energy":
            fast = _replace_mean_energy(fast)

        d = GENERATED / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(parent)
        (d / "fast_sub.i").write_text(fast)
        (d / "poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(
            json.dumps({**params, "r3_variant": name}, indent=2, sort_keys=True) + "\n"
        )

    probes = GENERATED / "probes"
    for variant in ("custom", "standard"):
        for probe_name, (energy_expr, density_expr, _should_pass) in PROBES.items():
            d = probes / f"{variant}_{probe_name}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "input.i").write_text(_probe_input(variant, energy_expr, density_expr))


def p0() -> None:
    build()
    a = GENERATED / "custom_mean_energy"
    b = GENERATED / "standard_mean_energy"

    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert (a / "poisson_sub.i").read_text() == (b / "poisson_sub.i").read_text()

    fa = (a / "fast_sub.i").read_text()
    fb = (b / "fast_sub.i").read_text()

    assert fa.count(CUSTOM_BLOCK) == 1
    assert "type = PhysicsElectronMeanEnergyMaterial" in fa
    assert "type = PhysicsElectronMeanEnergyMaterial" not in fb
    assert "property_name = mean_en_solved" in fb
    assert "functor_names = 'n_epsilon electron_density_hat'" in fb
    assert "disable_fpoptimizer = true" in fb
    assert "evalerror_behavior = error" in fb

    # Fail-closed structural contract: no floor/clamp/fallback is introduced.
    forbidden = ("max(ne", "min(ne", "1e-30", "1e-20", "epsilon_floor", "density_floor")
    for token in forbidden:
        assert token not in STANDARD_BLOCK, token

    # Explicit finite/positivity/output-overflow guards must all remain.
    for token in (
        "(ne-ne)==0",
        "(eps-eps)==0",
        "(ne>0)",
        "(eps>=0)",
        "sqrt(-abs(ne)-1)",
        f"{ENERGY_REFERENCE_EV}*eps/ne",
    ):
        assert token in STANDARD_EXPRESSION, token

    print("ISSUE335_R3_P0: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for name in CASE_NAMES:
        for fname in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_r3/{name} && "
                f"/workspace/physics_app/physics-opt --check-input -i {fname}"
            )

    # The probes force evaluation through ADElementExtremeFunctorValue. Valid
    # states must run; every invalid state must hard-fail for both realizations.
    probe_script = [
        f"cd /workspace/{rel}/generated_r3/probes",
        "rm -f probe_matrix.tsv",
    ]
    for variant in ("custom", "standard"):
        for probe_name, (_energy_expr, _density_expr, should_pass) in PROBES.items():
            case = f"{variant}_{probe_name}"
            expected = "0" if should_pass else "nonzero"
            probe_script.extend([
                f"cd /workspace/{rel}/generated_r3/probes/{case}",
                "set +e",
                f"/workspace/physics_app/physics-opt -i input.i > runtime.log 2>&1",
                "rc=$?",
                "set -e",
                f"echo '{case}\t{expected}\t'$rc >> /workspace/{rel}/generated_r3/probes/probe_matrix.tsv",
            ])
            if should_pass:
                probe_script.append("test $rc -eq 0")
            else:
                probe_script.append("test $rc -ne 0")
                if variant == "custom":
                    probe_script.append(
                        "grep -Eq 'PhysicsElectronMeanEnergyMaterial requires|Floating point exception' runtime.log"
                    )
                else:
                    probe_script.append(
                        "grep -q 'Parsed function evaluation encountered an error' runtime.log"
                    )

    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; "
        + "; ".join(checks)
        + "; "
        + "; ".join(probe_script)
    )
    print((GENERATED / "probes" / "probe_matrix.tsv").read_text(), end="")
    print("ISSUE335_R3_P2: PASS")


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
    (RESULTS / f"{name}_elapsed_seconds.txt").write_text(
        f"{time.perf_counter() - t0:.9f}\n"
    )
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
    result["elapsed_seconds"] = float(
        (RESULTS / f"{name}_elapsed_seconds.txt").read_text()
    )
    result["r3_variant"] = name
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
        f"chmod -R a+rwX /workspace/{rel}/results_r3 /workspace/{rel}/generated_r3; exit $rc"
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
        "issue": 335,
        "case": "short_ab",
        "classification": "R3_SHORT_COMPLETE" if valid else "R3_SHORT_INVALID",
        "evidence_valid": valid,
        "runs": runs,
        "comparison": comparison,
    }
    (RESULTS / "short_ab_result.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE335_R3_SHORT", json.dumps(comparison, sort_keys=True))
    if not valid:
        raise SystemExit(2)


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    matches = list(Path(root).rglob("short_ab_result.json"))
    if not matches:
        raise SystemExit("missing R3 result")
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
    Path("r3_aggregate.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("ISSUE335_R3_AGGREGATE", result["terminal_short_classification"])
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
