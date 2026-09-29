#!/usr/bin/env python3
"""Issue #351: frozen-heavy dedicated Gummel-driver parity against qualified Gen34.

Scientific control:
  A: qualified Gen34 PlasmaClosures topology, where the fast/electron app owns Gummel.
  B: identical heavy parent and Poisson physics, but fast_sub.i becomes a solve=false
     GUMMEL_DRIVER and the electron equations move to electron_sub.i.

The historical qualified repository is imported read-only through QUALIFIED_REPO.
All runs use the current branch's physics_app/physics-opt.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

QUALIFIED_REPO = Path(os.environ.get("QUALIFIED_REPO", "/tmp/qualified")).resolve()
if not QUALIFIED_REPO.is_dir():
    raise SystemExit(f"QUALIFIED_REPO missing: {QUALIFIED_REPO}")
sys.path.insert(0, str(QUALIFIED_REPO))

from experiments.Issue337_plasma_closures_migration import control as g337  # type: ignore
from experiments.Issue310_fp_acceleration import control_seq08 as seq08  # type: ignore
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08  # type: ignore
from physics_harness.adapters.moose import blocks as mb  # type: ignore

CASE_NAMES = ("qualified_fast_owner", "frozen_heavy_driver")
PAIR_ORDERS = {
    "pair_ab": CASE_NAMES,
    "pair_ba": tuple(reversed(CASE_NAMES)),
}
DPHI_TOL = 1.0e-6
QUALIFIED_SOURCE_COMMIT = "c9726d45e912f2476958d580c88e3421b5d4868b"
GEN34_CANONICAL_SHA = "cdba1cba025da3c8442c0ad2993aeccab0111732"

GENERATED = ROOT / "generated"
RESULTS = ROOT / "results"


def _cycles(horizon: str) -> int:
    if horizon == "short":
        return 1
    if horizon == "full":
        return 88
    raise ValueError(horizon)


def _case_root(horizon: str) -> Path:
    return GENERATED / horizon


def _result_root(horizon: str) -> Path:
    return RESULTS / horizon


def _qualified_case(horizon: str) -> Path:
    generated, _, _, _ = g337._bind(horizon)
    return generated / "plasma_closures"


def _extract_line(text: str, name: str, default: str | None = None) -> str:
    m = re.search(rf"^\s*{re.escape(name)}\s*=\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if m:
        return m.group(1).strip()
    if default is not None:
        return default
    raise RuntimeError(f"missing input parameter line: {name}")


def _aux_initial(text: str, variable: str, default: str) -> str:
    m = re.search(
        rf"\[{re.escape(variable)}\]\s*[\r\n]+"
        rf"(?:(?!^\s*\[\]).)*?^\s*initial_condition\s*=\s*(.+?)\s*$",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return m.group(1).strip() if m else default


def _remove_exec_line(text: str, name: str) -> str:
    return re.sub(
        rf"^\s*{re.escape(name)}\s*=.*\n",
        "",
        text,
        count=1,
        flags=re.MULTILINE,
    )


def _electron_only(fast: str) -> str:
    """Remove only fixed-point/Gummel ownership from the qualified fast app."""
    text = mb.remove_block(fast, "GummelIteration")
    text = mb.remove_block(text, "AuxVariables/fp_phi_anchor_diag")
    text = mb.remove_block(text, "FunctorMaterials/fp_delta_phi_abs")

    for i in range(20):
        text = mb.remove_block(text, f"Postprocessors/fp_phi_current_{i:02d}")
        text = mb.remove_block(text, f"Postprocessors/fp_phi_anchor_{i:02d}")

    for name in (
        "fp_delta_phi_max",
        "fixed_point_iterations",
        "cumulative_fixed_point_iterations",
    ):
        text = mb.remove_block(text, f"Postprocessors/{name}")

    for name in (
        "fixed_point_algorithm",
        "transformed_variables",
        "multiapp_fixed_point_convergence",
        "fixed_point_min_its",
        "fixed_point_max_its",
        "fixed_point_rel_tol",
        "fixed_point_abs_tol",
        "accept_on_max_fixed_point_iteration",
    ):
        text = _remove_exec_line(text, name)

    # Driver owns fixed-point output. Electron keeps physical FINAL profiles only.
    text = mb.remove_block(text, "Outputs/step_csv")
    text = mb.remove_block(text, "Outputs/fp_anchor_csv")
    return text


def _driver_input(fast: str) -> str:
    dt = _extract_line(fast, "dt")
    dtmin = _extract_line(fast, "dtmin", dt)
    dtmax = _extract_line(fast, "dtmax", dt)
    end_time = _extract_line(fast, "end_time")
    num_steps = _extract_line(fast, "num_steps")
    timestep_tol = _extract_line(fast, "timestep_tolerance")
    fp_min = _extract_line(fast, "fixed_point_min_its", "2")
    fp_max = _extract_line(fast, "fixed_point_max_its", "3000")
    fp_rel = _extract_line(fast, "fixed_point_rel_tol", "1.0e-8")
    fp_abs = _extract_line(fast, "fixed_point_abs_tol", "1.0e-12")

    w_o2p = _aux_initial(fast, "w_O2p_h", "0.001")
    w_om = _aux_initial(fast, "w_Om_h", "0.001")
    w_op = _aux_initial(fast, "w_Op_h", "0.001")
    ne0 = _aux_initial(fast, "electron_density_out", "1.0e16")
    mean0 = _aux_initial(fast, "mean_energy_out", "5.73276")

    return f"""# Issue #351 dedicated frozen-heavy Gummel driver.
# Heavy state enters this app once per outer heavy step and is unchanged during
# every inner electron/Poisson fixed-point iteration.

[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 20
  xmin = 0.0
  xmax = 0.01
[]

[Problem]
  solve = false
  kernel_coverage_check = false
[]

[AuxVariables]
  [w_O2p_h]
    type = MooseVariableFVReal
    initial_condition = {w_o2p}
  []
  [w_Om_h]
    type = MooseVariableFVReal
    initial_condition = {w_om}
  []
  [w_Op_h]
    type = MooseVariableFVReal
    initial_condition = {w_op}
  []
  [potential_from_poisson]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [fp_phi_anchor_diag]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [electron_density_out]
    type = MooseVariableFVReal
    initial_condition = {ne0}
  []
  [mean_energy_out]
    type = MooseVariableFVReal
    initial_condition = {mean0}
  []
[]

[FunctorMaterials]
  [fp_delta_phi_abs]
    type = ADParsedFunctorMaterial
    property_name = fp_delta_phi_abs
    functor_names = 'potential_from_poisson fp_phi_anchor_diag'
    functor_symbols = 'phi phi0'
    expression = 'abs(phi-phi0)'
  []
[]

[GummelIteration]
  [electron_poisson]
    electron_multiapp = electron
    electron_input_file = electron_sub.i
    electron_multiapp_type = TransientMultiApp

    poisson_multiapp = poisson
    poisson_input_file = poisson_sub.i
    poisson_multiapp_type = TransientMultiApp

    electron_state_variables = 'log_e n_epsilon'

    electron_density_variable = log_e
    poisson_electron_density_variable = log_e_frozen

    poisson_potential_variable = potential_plasma
    electron_potential_variable = potential_from_poisson
    potential_transfer_mode = through_parent
    parent_potential_variable = potential_from_poisson

    electron_to_poisson_source_variables = 'n_epsilon'
    electron_to_poisson_variables = 'n_epsilon_frozen'

    parent_to_poisson_source_variables =
      'potential_from_poisson w_O2p_h w_Om_h w_Op_h'
    parent_to_poisson_variables =
      'phi_anchor_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'

    poisson_to_parent_source_variables = 'phi_anchor_frozen'
    poisson_to_parent_variables = 'fp_phi_anchor_diag'

    electron_to_parent_source_variables =
      'electron_density_out mean_energy_out'
    electron_to_parent_variables =
      'electron_density_out mean_energy_out'

    poisson_transformed_variables = 'potential_plasma'
    relaxation_factor = 0.45
    no_restore = true

    manage_convergence = true
    convergence_name = gummel_delta_phi
    delta_phi_postprocessor = fp_delta_phi_max
    delta_phi_abs_tol = {DPHI_TOL:.17g}
  []
[]

[Postprocessors]
  [fp_delta_phi_max]
    type = ADElementExtremeFunctorValue
    functor = fp_delta_phi_abs
    value_type = max
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
  [cumulative_fixed_point_iterations]
    type = CumulativeValuePostprocessor
    postprocessor = fixed_point_iterations
    execute_on = 'TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {dt}
  dtmin = {dtmin}
  dtmax = {dtmax}
  end_time = {end_time}
  num_steps = {num_steps}
  timestep_tolerance = {timestep_tol}

  fixed_point_min_its = {fp_min}
  fixed_point_max_its = {fp_max}
  fixed_point_rel_tol = {fp_rel}
  fixed_point_abs_tol = {fp_abs}
  accept_on_max_fixed_point_iteration = false

  fixed_point_algorithm = steffensen
  transformed_variables = 'potential_from_poisson'
  multiapp_fixed_point_convergence = gummel_delta_phi
[]

[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    execute_vector_postprocessors_on = 'NONE'
    new_row_tolerance = 1.0e-30
  []
  [final_csv]
    type = CSV
    execute_on = 'FINAL'
    execute_vector_postprocessors_on = 'FINAL'
  []
[]
"""


def _copy_case(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "input.i",
        "fast_sub.i",
        "poisson_sub.i",
        "electron_moments.txt",
        "o2_elastic.txt",
        "transport_data.txt",
        "case.json",
    ):
        shutil.copy2(src / name, dst / name)


def build(horizon: str, clean: bool = True) -> None:
    cycles = _cycles(horizon)
    if clean:
        shutil.rmtree(_case_root(horizon), ignore_errors=True)
        shutil.rmtree(_result_root(horizon), ignore_errors=True)

    # Generate the exact historical PlasmaClosures-qualified Gen34 lane.
    g337.build(horizon)
    src = _qualified_case(horizon)
    root = _case_root(horizon)
    baseline = root / CASE_NAMES[0]
    trial = root / CASE_NAMES[1]

    _copy_case(src, baseline)
    _copy_case(src, trial)

    baseline_fast = (baseline / "fast_sub.i").read_text(encoding="utf-8")
    trial_fast = (trial / "fast_sub.i").read_text(encoding="utf-8")

    # In the trial, fast_sub.i keeps the exact outer interface but becomes the driver.
    (trial / "electron_sub.i").write_text(_electron_only(trial_fast), encoding="utf-8")
    (trial / "fast_sub.i").write_text(_driver_input(trial_fast), encoding="utf-8")

    for name in CASE_NAMES:
        p = root / name / "case.json"
        meta = json.loads(p.read_text(encoding="utf-8"))
        meta.update(
            name=name,
            issue=351,
            phase="frozen_heavy_driver_parity",
            horizon=horizon,
            heavy_cycles=cycles,
            electron_steps=4 * cycles,
            topology=(
                "qualified_fast_owner"
                if name == CASE_NAMES[0]
                else "frozen_heavy_dedicated_driver"
            ),
            qualified_source_commit=QUALIFIED_SOURCE_COMMIT,
            gen34_canonical_sha=GEN34_CANONICAL_SHA,
        )
        p.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def p0(horizon: str) -> None:
    build(horizon)
    root = _case_root(horizon)
    a = root / CASE_NAMES[0]
    b = root / CASE_NAMES[1]

    parent_a = (a / "input.i").read_text(encoding="utf-8")
    parent_b = (b / "input.i").read_text(encoding="utf-8")
    poisson_a = (a / "poisson_sub.i").read_text(encoding="utf-8")
    poisson_b = (b / "poisson_sub.i").read_text(encoding="utf-8")
    fast_a = (a / "fast_sub.i").read_text(encoding="utf-8")
    driver = (b / "fast_sub.i").read_text(encoding="utf-8")
    electron = (b / "electron_sub.i").read_text(encoding="utf-8")

    assert parent_a == parent_b
    assert poisson_a == poisson_b
    assert "[PlasmaClosures]" in parent_a
    assert "[PlasmaClosures]" in poisson_a
    assert "[PlasmaClosures]" in fast_a
    assert "[PlasmaClosures]" in electron

    assert "[GummelIteration]" in fast_a
    assert "electron_input_file" not in fast_a
    assert "fixed_point_algorithm = 'steffensen'" in fast_a
    assert "transformed_variables = 'potential_from_poisson'" in fast_a

    assert "solve = false" in driver
    assert "[GummelIteration]" in driver
    assert "electron_input_file = electron_sub.i" in driver
    assert "potential_transfer_mode = through_parent" in driver
    assert "parent_potential_variable = potential_from_poisson" in driver
    assert "fixed_point_algorithm = steffensen" in driver
    assert "transformed_variables = 'potential_from_poisson'" in driver
    assert "multiapp_fixed_point_convergence = gummel_delta_phi" in driver
    assert "[sync_final_phi_to_electron]" not in driver
    assert "auto_advance = true" not in driver
    assert f"delta_phi_abs_tol = {DPHI_TOL:.17g}" in driver

    assert "[GummelIteration]" not in electron
    assert "[MultiApps]" not in electron
    assert "[Transfers]" not in electron
    assert "type = PhysicsFVElectronEnergyJouleHeating" in electron
    assert "role = electron" in electron or "create_electron_closure = true" in electron
    assert "potential = potential_from_poisson" in electron
    assert "fixed_point_algorithm" not in electron

    assert "type = FVElectronResponseBandedCorrection" in poisson_a
    assert "bandwidth = 5" in poisson_a
    assert "phi_anchor_frozen" in poisson_a
    assert "n_epsilon_frozen" in poisson_a

    print(
        f"ISSUE351_FROZEN_HEAVY_DRIVER_P0_{horizon.upper()}: PASS "
        f"cycles={_cycles(horizon)}"
    )


def p1(horizon: str) -> None:
    build(horizon)
    exe = REPO / "physics_app" / "physics-opt"
    if not exe.exists():
        raise SystemExit("physics-opt missing")

    root = _case_root(horizon)
    checks = {
        CASE_NAMES[0]: ("poisson_sub.i", "fast_sub.i", "input.i"),
        CASE_NAMES[1]: ("poisson_sub.i", "electron_sub.i", "fast_sub.i", "input.i"),
    }
    for name, files in checks.items():
        for input_name in files:
            cp = subprocess.run(
                [str(exe), "--check-input", "-i", input_name],
                cwd=root / name,
                check=False,
            )
            if cp.returncode:
                raise SystemExit(cp.returncode)

    print(f"ISSUE351_FROZEN_HEAVY_DRIVER_P1_{horizon.upper()}: PASS")


def _clean_runtime_outputs(case_dir: Path) -> None:
    keep = {
        "input.i",
        "fast_sub.i",
        "electron_sub.i",
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
    results = _result_root(horizon)
    results.mkdir(parents=True, exist_ok=True)
    case_dir = _case_root(horizon) / name
    _clean_runtime_outputs(case_dir)

    log = results / f"{name}_runtime.log"
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        cp = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-t", "-i", "input.i"],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    (results / f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    (results / f"{name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    return cp.returncode


def _bind_analysis(horizon: str) -> None:
    cycles = _cycles(horizon)
    final_tau = 400.0 * cycles
    seq08.GENERATED = _case_root(horizon)
    seq08.RESULTS = _result_root(horizon)
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


def _analyze(horizon: str, name: str) -> tuple[dict[str, object], int]:
    _bind_analysis(horizon)
    result, code = seq08.analyze(name)
    result.update(
        issue=351,
        phase="frozen_heavy_driver_parity",
        horizon=horizon,
        topology=name,
        elapsed_seconds=float(
            (_result_root(horizon) / f"{name}_elapsed_seconds.txt").read_text().strip()
        ),
    )
    return result, code


def _compare(a: dict[str, object], b: dict[str, object]) -> dict[str, object]:
    profile = wall08._comparison(a, b)
    trajectory = seq08._potential_series_parity(a, b)

    fp_a = [
        int(x["fixed_point_iterations"])
        for x in a.get("fixed_point_time_series", [])
        if float(x.get("time_s", 0.0)) > 0.0
    ]
    fp_b = [
        int(x["fixed_point_iterations"])
        for x in b.get("fixed_point_time_series", [])
        if float(x.get("time_s", 0.0)) > 0.0
    ]
    profile_values = [
        abs(float(v)) for v in profile.values() if isinstance(v, (int, float))
    ]
    trajectory_values = [
        abs(float(v))
        for key, v in trajectory.items()
        if isinstance(v, (int, float)) and key.endswith("_delta")
    ]

    ta = float(a["elapsed_seconds"])
    tb = float(b["elapsed_seconds"])
    return {
        "fp_history_qualified": fp_a,
        "fp_history_driver": fp_b,
        "fp_history_equal": fp_a == fp_b,
        "fp_total_qualified": sum(fp_a),
        "fp_total_driver": sum(fp_b),
        "max_profile_metric": max(profile_values) if profile_values else 0.0,
        "max_trajectory_abs_delta": max(trajectory_values) if trajectory_values else 0.0,
        "profile": profile,
        "trajectory": trajectory,
        "qualified_elapsed_s": ta,
        "driver_elapsed_s": tb,
        "runtime_ratio_driver_over_qualified": tb / ta if ta else None,
    }


def run_pair(horizon: str, pair: str) -> dict[str, object]:
    build(horizon)
    codes: dict[str, int] = {}
    for name in PAIR_ORDERS[pair]:
        codes[name] = _run_one(horizon, name)

    runs: dict[str, dict[str, object]] = {}
    analysis_codes: dict[str, int] = {}
    for name in CASE_NAMES:
        runs[name], analysis_codes[name] = _analyze(horizon, name)

    comparison = _compare(runs[CASE_NAMES[0]], runs[CASE_NAMES[1]])
    valid = (
        all(code == 0 for code in codes.values())
        and all(code == 0 for code in analysis_codes.values())
        and all(bool(run.get("evidence_valid")) for run in runs.values())
        and bool(comparison["fp_history_equal"])
        and float(comparison["max_profile_metric"]) <= 1.0e-10
        and float(comparison["max_trajectory_abs_delta"]) <= 1.0e-9
    )

    out = {
        "issue": 351,
        "phase": "frozen_heavy_driver_parity",
        "horizon": horizon,
        "pair": pair,
        "order": list(PAIR_ORDERS[pair]),
        "heavy_cycles": _cycles(horizon),
        "electron_steps": 4 * _cycles(horizon),
        "classification": (
            "FROZEN_HEAVY_DRIVER_SCIENTIFIC_PARITY_PASS"
            if valid
            else "FROZEN_HEAVY_DRIVER_PARITY_FAIL"
        ),
        "evidence_valid": valid,
        "comparison": comparison,
        "runs": runs,
        "guard": (
            "Heavy parent input and Poisson input are byte-identical. Both lanes use the "
            "qualified PlasmaClosures composition. The controlled change is Gummel ownership: "
            "fast/electron owner versus solve=false dedicated driver with sibling electron/Poisson."
        ),
    }
    results = _result_root(horizon)
    results.mkdir(parents=True, exist_ok=True)
    (results / f"{pair}_result.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print(
        f"ISSUE351_FROZEN_HEAVY_DRIVER_{horizon.upper()}_{pair.upper()}",
        json.dumps(comparison, sort_keys=True),
    )

    if not valid:
        raise SystemExit(2)
    return out


def run(horizon: str) -> None:
    if horizon == "short":
        run_pair(horizon, "pair_ab")
        return

    pairs = [run_pair(horizon, "pair_ab"), run_pair(horizon, "pair_ba")]
    ratios = [
        float(pair["comparison"]["runtime_ratio_driver_over_qualified"])
        for pair in pairs
    ]
    geo = math.sqrt(ratios[0] * ratios[1])
    exact_fp = all(bool(pair["comparison"]["fp_history_equal"]) for pair in pairs)
    valid = all(bool(pair["evidence_valid"]) for pair in pairs)

    summary = {
        "issue": 351,
        "phase": "frozen_heavy_driver_parity",
        "horizon": "full",
        "classification": (
            "FROZEN_HEAVY_DRIVER_FULL_QUALIFIED"
            if valid and exact_fp
            else "FROZEN_HEAVY_DRIVER_FULL_FAIL"
        ),
        "evidence_valid": valid,
        "exact_fp_history_both_orders": exact_fp,
        "geometric_mean_runtime_ratio_driver_over_qualified": geo,
        "runtime_regression_fraction": geo - 1.0,
        "qualified_source_commit": QUALIFIED_SOURCE_COMMIT,
        "gen34_canonical_sha": GEN34_CANONICAL_SHA,
        "pairs": {pair["pair"]: pair for pair in pairs},
    }
    results = _result_root("full")
    results.mkdir(parents=True, exist_ok=True)
    (results / "full_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE351_FROZEN_HEAVY_DRIVER_FULL_SUMMARY", json.dumps(summary, sort_keys=True))
    if summary["classification"] != "FROZEN_HEAVY_DRIVER_FULL_QUALIFIED":
        raise SystemExit(3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", choices=("short", "full"), required=True)
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
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
