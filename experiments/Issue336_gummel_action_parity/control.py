#!/usr/bin/env python3
"""Issue #336: GummelIterationAction wiring parity against qualified Gen34 manual wiring.

The controlled change is only construction of the electron<->Poisson coupling:
  A: explicit [MultiApps] + [Transfers] + [Convergence]
  B: [GummelIteration] Action

Electron equations, Poisson physics, banded electron response, acceleration,
clock, convergence metric, output policy, and tolerances are identical.
"""
from __future__ import annotations

import argparse
import json
import re
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

CASE_NAMES = ("manual_wiring", "action_wiring")
PAIR_ORDERS = {
    "pair_ab": CASE_NAMES,
    "pair_ba": tuple(reversed(CASE_NAMES)),
}
DPHI_TOL = 1.0e-6

BASE_SPEC = {
    "name": "gummel_action_parity",
    "role": "optimized",
    "bandwidth": 5,
    "relaxation_factor": 0.45,
    "custom_convergence": True,
    "delta_phi_abs_tol": DPHI_TOL,
    "fp_algorithm": "steffensen",
    "compute_scaling_once": True,
    "suppress_fp_anchor_output": True,
    "vector_profiles_final_only": True,
}

def _paths(horizon: str) -> tuple[Path, Path, int, float]:
    if horizon == "short":
        cycles = 1
    elif horizon == "full":
        cycles = 88
    else:
        raise ValueError(horizon)
    return (
        ROOT / f"generated_{horizon}",
        ROOT / f"results_{horizon}",
        cycles,
        400.0 * cycles,
    )

def _bind(horizon: str) -> tuple[Path, Path, int, float]:
    generated, results, cycles, final_tau = _paths(horizon)

    gen34.HEAVY_CYCLES = cycles
    gen34.FINAL_TAU = final_tau
    gen34._bind_clock()

    seq08.GENERATED = generated
    seq08.RESULTS = results
    seq08.FINAL_TAU = final_tau
    seq08.HEAVY_CYCLES = cycles
    seq08.CASE_NAMES = CASE_NAMES
    seq08.SPECS = tuple(
        {
            "name": name,
            "architecture": name,
            "algorithm": "steffensen",
            "relaxation_factor": 0.45,
        }
        for name in CASE_NAMES
    )
    wall08.FINAL_TAU = final_tau
    return generated, results, cycles, final_tau

def _action_block() -> str:
    return f"""[GummelIteration]
  [electron_poisson]
    poisson_multiapp = poisson
    poisson_input_file = poisson_sub.i
    poisson_multiapp_type = TransientMultiApp

    electron_state_variables = 'log_e n_epsilon'

    electron_to_poisson_source_variables = 'log_e n_epsilon potential_from_poisson w_O2p_h w_Om_h w_Op_h'
    electron_to_poisson_variables = 'log_e_frozen n_epsilon_frozen phi_anchor_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'

    poisson_to_electron_source_variables = 'potential_plasma phi_anchor_frozen'
    poisson_to_electron_variables = 'potential_from_poisson fp_phi_anchor_diag'

    poisson_transformed_variables = 'potential_plasma'
    relaxation_factor = 0.45
    no_restore = true

    manage_convergence = true
    convergence_name = gummel_delta_phi
    delta_phi_postprocessor = fp_delta_phi_max
    delta_phi_abs_tol = {DPHI_TOL:.17g}
  []
[]
"""

def _actionize(fast: str) -> str:
    start = fast.index("[MultiApps]\n")
    post = fast.index("[Postprocessors]\n", start)
    fast = fast[:start] + _action_block() + "\n" + fast[post:]

    conv = f"""[Convergence]
  [gummel_delta_phi]
    type = DeltaPhiMultiAppConvergence
    delta_phi_pp = fp_delta_phi_max
    delta_phi_abs_tol = {DPHI_TOL:.17g}
  []
[]

"""
    if fast.count(conv) != 1:
        raise RuntimeError("qualified convergence block changed")
    fast = fast.replace(conv, "", 1)

    owner = "  multiapp_fixed_point_convergence = gummel_delta_phi\n"
    if fast.count(owner) != 1:
        raise RuntimeError("qualified convergence-owner line changed")
    fast = fast.replace(owner, "", 1)
    return fast

def _normalize_wiring(fast: str) -> str:
    fast = re.sub(
        r"\[MultiApps\][\s\S]*?\n\[Postprocessors\]",
        "<GUMMEL_WIRING>\n[Postprocessors]",
        fast,
        count=1,
    )
    fast = re.sub(
        r"\[GummelIteration\][\s\S]*?\n\[Postprocessors\]",
        "<GUMMEL_WIRING>\n[Postprocessors]",
        fast,
        count=1,
    )
    fast = re.sub(
        r"\n\[Convergence\]\n  \[gummel_delta_phi\][\s\S]*?\n\[\]\n",
        "\n",
        fast,
        count=1,
    )
    fast = fast.replace("  multiapp_fixed_point_convergence = gummel_delta_phi\n", "")
    return fast

def build(horizon: str, clean: bool = True) -> None:
    generated, results, cycles, final_tau = _bind(horizon)
    if clean:
        shutil.rmtree(generated, ignore_errors=True)
        shutil.rmtree(results, ignore_errors=True)
    generated.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)

    parent, manual_fast, poisson, params = gen34._optimized_inputs(dict(BASE_SPEC))
    action_fast = _actionize(manual_fast)

    for name, fast in (
        ("manual_wiring", manual_fast),
        ("action_wiring", action_fast),
    ):
        d = generated / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(parent, encoding="utf-8")
        (d / "fast_sub.i").write_text(fast, encoding="utf-8")
        (d / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(
            json.dumps(
                {
                    **params,
                    "name": name,
                    "issue": 336,
                    "phase": "gummel_action_parity",
                    "horizon": horizon,
                    "heavy_cycles": cycles,
                    "electron_steps": 4 * cycles,
                    "final_tau": final_tau,
                    "wiring": name,
                    "fixed_point_algorithm": "steffensen",
                    "relaxation_factor": 0.45,
                    "bandwidth": 5,
                    "delta_phi_abs_tol": DPHI_TOL,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

def p0(horizon: str) -> None:
    build(horizon)
    generated, _, cycles, _ = _bind(horizon)
    a = generated / CASE_NAMES[0]
    b = generated / CASE_NAMES[1]

    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert (a / "poisson_sub.i").read_text() == (b / "poisson_sub.i").read_text()

    fa = (a / "fast_sub.i").read_text()
    fb = (b / "fast_sub.i").read_text()

    # Everything outside the explicit Gummel wiring/convergence ownership must
    # remain byte-identical. Compare the electron-physics prefix, diagnostics,
    # executioner (after removing only the manual convergence-owner line), and
    # outputs independently so whitespace inside the replacement block is irrelevant.
    assert fa[:fa.index("[MultiApps]\\n")] == fb[:fb.index("[GummelIteration]\\n")]

    pp_a = fa[fa.index("[Postprocessors]\\n"):fa.index("[Executioner]\\n")]
    pp_b = fb[fb.index("[Postprocessors]\\n"):fb.index("[Executioner]\\n")]
    assert pp_a == pp_b

    exec_a = re.search(r"\\[Executioner\\][\\s\\S]*?\\n\\[\\]\\n", fa)
    exec_b = re.search(r"\\[Executioner\\][\\s\\S]*?\\n\\[\\]\\n", fb)
    assert exec_a is not None and exec_b is not None
    assert exec_a.group(0).replace(
        "  multiapp_fixed_point_convergence = gummel_delta_phi\\n", ""
    ) == exec_b.group(0)

    assert fa[fa.index("[Outputs]\\n"):] == fb[fb.index("[Outputs]\\n"):]

    assert "[MultiApps]" in fa and "[Transfers]" in fa
    assert "type = DeltaPhiMultiAppConvergence" in fa
    assert "[GummelIteration]" not in fa

    assert "[GummelIteration]" in fb
    assert "[MultiApps]" not in fb
    assert "[Transfers]" not in fb
    assert "[Convergence]" not in fb
    assert "multiapp_fixed_point_convergence = gummel_delta_phi" not in fb
    assert "electron_state_variables = 'log_e n_epsilon'" in fb
    assert "potential_from_poisson w_O2p_h w_Om_h w_Op_h" in fb
    assert "potential_plasma phi_anchor_frozen" in fb
    assert "delta_phi_postprocessor = fp_delta_phi_max" in fb

    for d in (a, b):
        pp = (d / "poisson_sub.i").read_text()
        assert "type = FVElectronResponseBandedCorrection" in pp
        assert "bandwidth = 5" in pp
        assert "electron_response_beta" in pp

    print(f"ISSUE336_GUMMEL_ACTION_P0_{horizon.upper()}: PASS cycles={cycles}")

def p1(horizon: str) -> None:
    build(horizon)
    generated, _, _, _ = _bind(horizon)
    exe = REPO / "physics_app" / "physics-opt"
    if not exe.exists():
        raise SystemExit("physics-opt missing")
    for name in CASE_NAMES:
        for input_name in ("poisson_sub.i", "fast_sub.i", "input.i"):
            cp = subprocess.run(
                [str(exe), "--check-input", "-i", input_name],
                cwd=generated / name,
                check=False,
            )
            if cp.returncode:
                raise SystemExit(cp.returncode)
    print(f"ISSUE336_GUMMEL_ACTION_P1_{horizon.upper()}: PASS")

def _clean_runtime_outputs(case_dir: Path) -> None:
    keep = {
        "input.i",
        "fast_sub.i",
        "poisson_sub.i",
        "electron_moments.txt",
        "o2_elastic.txt",
        "transport_data.txt",
        "case.json",
    }
    for item in case_dir.iterdir():
        if item.name in keep:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

def _run_one(horizon: str, name: str) -> int:
    generated, results, _, _ = _bind(horizon)
    case_dir = generated / name
    _clean_runtime_outputs(case_dir)
    log = results / f"{name}_runtime.log"
    start = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        cp = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-t", "-i", "input.i"],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - start
    (results / f"{name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    (results / f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    return cp.returncode

def _analyze(horizon: str, name: str) -> tuple[dict[str, object], int]:
    _, results, _, _ = _bind(horizon)
    result, code = seq08.analyze(name)
    result["issue"] = 336
    result["phase"] = "gummel_action_parity"
    result["horizon"] = horizon
    result["wiring"] = name
    result["fixed_point_algorithm"] = "steffensen"
    result["elapsed_seconds"] = float(
        (results / f"{name}_elapsed_seconds.txt").read_text()
    )
    return result, code

def _compare(manual: dict[str, object], action: dict[str, object]) -> dict[str, object]:
    profile = wall08._comparison(manual, action)
    trajectory = seq08._potential_series_parity(manual, action)
    fp_m = [
        int(x["fixed_point_iterations"])
        for x in manual.get("fixed_point_time_series", [])
        if float(x.get("time_s", 0.0)) > 0.0
    ]
    fp_a = [
        int(x["fixed_point_iterations"])
        for x in action.get("fixed_point_time_series", [])
        if float(x.get("time_s", 0.0)) > 0.0
    ]
    profile_metrics = [
        abs(float(v)) for v in profile.values() if isinstance(v, (int, float))
    ]
    traj_metrics = [
        abs(float(v))
        for key, v in trajectory.items()
        if isinstance(v, (int, float)) and key.endswith("_delta")
    ]
    tm = float(manual["elapsed_seconds"])
    ta = float(action["elapsed_seconds"])
    return {
        "fp_history_manual": fp_m,
        "fp_history_action": fp_a,
        "fp_history_equal": fp_m == fp_a,
        "fp_total_manual": sum(fp_m),
        "fp_total_action": sum(fp_a),
        "max_profile_metric": max(profile_metrics) if profile_metrics else 0.0,
        "max_trajectory_abs_delta": max(traj_metrics) if traj_metrics else 0.0,
        "profile": profile,
        "trajectory": trajectory,
        "manual_elapsed_s": tm,
        "action_elapsed_s": ta,
        "runtime_ratio_action_over_manual": ta / tm if tm else None,
    }

def run_pair(horizon: str, pair: str) -> dict[str, object]:
    generated, results, cycles, final_tau = _bind(horizon)
    if not generated.exists():
        build(horizon)
    codes: dict[str, int] = {}
    for name in PAIR_ORDERS[pair]:
        codes[name] = _run_one(horizon, name)

    runs = {}
    analysis_codes = {}
    for name in CASE_NAMES:
        runs[name], analysis_codes[name] = _analyze(horizon, name)

    comparison = _compare(runs["manual_wiring"], runs["action_wiring"])
    valid = (
        all(v == 0 for v in codes.values())
        and all(v == 0 for v in analysis_codes.values())
        and all(bool(r.get("evidence_valid")) for r in runs.values())
        and bool(comparison["fp_history_equal"])
        and float(comparison["max_profile_metric"]) <= 1.0e-10
        and float(comparison["max_trajectory_abs_delta"]) <= 1.0e-9
    )
    out = {
        "issue": 336,
        "phase": "gummel_action_parity",
        "horizon": horizon,
        "pair": pair,
        "heavy_cycles": cycles,
        "final_tau": final_tau,
        "classification": (
            "GUMMEL_ACTION_SCIENTIFIC_PARITY_PASS"
            if valid
            else "GUMMEL_ACTION_PARITY_FAIL"
        ),
        "evidence_valid": valid,
        "comparison": comparison,
        "runs": runs,
    }
    (results / f"{pair}_result.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print(
        f"ISSUE336_GUMMEL_ACTION_{horizon.upper()}_{pair.upper()}",
        json.dumps(comparison, sort_keys=True),
    )
    if not valid:
        raise SystemExit(2)
    return out

def run(horizon: str) -> None:
    build(horizon)
    if horizon == "short":
        run_pair(horizon, "pair_ab")
        return

    pairs = [run_pair(horizon, "pair_ab"), run_pair(horizon, "pair_ba")]
    ratios = [
        float(p["comparison"]["runtime_ratio_action_over_manual"]) for p in pairs
    ]
    geo = (ratios[0] * ratios[1]) ** 0.5
    exact = all(bool(p["comparison"]["fp_history_equal"]) for p in pairs)
    valid = all(bool(p["evidence_valid"]) for p in pairs)
    summary = {
        "issue": 336,
        "phase": "gummel_action_parity",
        "horizon": "full",
        "classification": (
            "GUMMEL_ACTION_FULL_QUALIFIED"
            if valid and exact
            else "GUMMEL_ACTION_FULL_FAIL"
        ),
        "evidence_valid": valid,
        "exact_fp_history_both_orders": exact,
        "geometric_mean_runtime_ratio_action_over_manual": geo,
        "runtime_regression_fraction": geo - 1.0,
        "pairs": {
            p["pair"]: p for p in pairs
        },
    }
    (_, results, _, _) = _bind("full")
    (results / "full_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE336_GUMMEL_ACTION_FULL_SUMMARY", json.dumps(summary, sort_keys=True))
    if summary["classification"] != "GUMMEL_ACTION_FULL_QUALIFIED":
        raise SystemExit(3)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", choices=("short", "full"), required=True)
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()

    if args.p0:
        p0(args.horizon)
    elif args.p1:
        p1(args.horizon)
    elif args.run:
        run(args.horizon)
    else:
        ap.error("choose --p0, --p1, or --run")

if __name__ == "__main__":
    main()
