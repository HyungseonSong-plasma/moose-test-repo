#!/usr/bin/env python3
"""Issue #228 one-step numerical-only discriminator controls.

Four equal-physics-input cases are compared at the same R0 mesh and dt:

  production        accepted corrected FV gradients everywhere
  drift_two_point   only electron electrostatic drift uses two-point normal grad(phi)
  poisson_two_point only Poisson internal diffusion uses two-point normal grad(phi)
  both_two_point    both diagnostic interventions together

The controls intentionally alter numerical discretization only. They are not
production proposals and must not be interpreted as accepted physics merely
because a spatial scalar looks smoother.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue211_science_factorial import run as sci
from experiments.Issue216_w5_multistep_acceptance import run as w5
from physics_harness.adapters.moose import parameters as mp

DT_S = w5.BASELINE_DT_S
MODES = ("production", "drift_two_point", "poisson_two_point", "both_two_point")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_case(mode: str) -> tuple[str, dict[str, Any]]:
    if mode not in MODES:
        raise ValueError(mode)
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=0)
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{DT_S:.17g}")
    text = mp.upsert_parameter(text, "Outputs", "exodus", "false")

    if mode in ("drift_two_point", "both_two_point"):
        text = mp.upsert_parameter(
            text,
            "FVKernels/n_e_drift",
            "type",
            "PhysicsFVTwoPointElectrostaticDriftControl",
        )
    if mode in ("poisson_two_point", "both_two_point"):
        text = mp.upsert_parameter(
            text,
            "FVKernels/r31_phi_diffusion",
            "type",
            "PhysicsFVTwoPointDiffusionControl",
        )

    meta = {
        **meta,
        "issue": 228,
        "claim": "one_step_two_point_gradient_discriminator",
        "diagnostic_only": True,
        "mode": mode,
        "expected_steps": 1,
        "dt_s": DT_S,
        "end_time_s": DT_S,
        "uniform_refine": 0,
        "physical_coefficients_changed": False,
        "sheath_law_changed": False,
        "mesh_changed": False,
    }
    return text, meta


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for mode in MODES:
        text, meta = build_case(mode)
        drift_type = mp.get_parameter(text, "FVKernels/n_e_drift", "type")
        poisson_type = mp.get_parameter(text, "FVKernels/r31_phi_diffusion", "type")
        checks[f"{mode}:dt"] = math.isclose(
            float(mp.get_parameter(text, "Executioner", "dt") or "nan"), DT_S, rel_tol=0.0, abs_tol=0.0
        )
        checks[f"{mode}:end"] = math.isclose(
            float(mp.get_parameter(text, "Executioner", "end_time") or "nan"), DT_S, rel_tol=0.0, abs_tol=1e-24
        )
        checks[f"{mode}:r0"] = meta.get("uniform_refine") == 0
        checks[f"{mode}:drift_type"] = (
            drift_type == "PhysicsFVTwoPointElectrostaticDriftControl"
        ) == (mode in ("drift_two_point", "both_two_point"))
        checks[f"{mode}:poisson_type"] = (
            poisson_type == "PhysicsFVTwoPointDiffusionControl"
        ) == (mode in ("poisson_two_point", "both_two_point"))
    failed = sorted(k for k, v in checks.items() if not v)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _case_result(case_dir: Path, text: str, meta: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    rows = s5r._read_rows(case_dir / "input_out.csv")
    physical = w5._physical_rows(rows)
    if len(physical) != 1:
        raise RuntimeError(f"expected one physical row, got {len(physical)}")
    step = w5._step_evidence(rows[0], rows[1], input_text=text, meta=meta)
    state = step["state"]
    wall = step["wall_current"]
    energy = step["electron_energy"]
    return {
        "runtime_returncode": int(runtime.get("returncode", 1)),
        "step_hard_pass": step.get("hard_pass") is True,
        "phi_min_V": state["phi_min_V"],
        "phi_max_V": state["phi_max_V"],
        "volume_charge_C": state["volume_charge_C"],
        "rho_q_min_C_m3": state.get("rho_q_min_C_m3"),
        "rho_q_max_C_m3": state.get("rho_q_max_C_m3"),
        "n_e_min_m3": state["n_e_min_m3"],
        "n_e_inventory": state.get("n_e_inventory"),
        "mean_energy_avg_eV": state["mean_energy_avg_eV"],
        "primary_electron_particle_rate_s-1": wall["primary_electron_particle_rate_s-1"],
        "net_outward_wall_current_A": wall["net_outward_wall_current_A"],
        "primary_wall_power_W": energy["primary_wall_power_W"],
        "current_charge_relative_defect": step["charge"]["relative_defect_over_boundary_current_scale"],
        "gauss_relative_defect": step["gauss"]["relative_defect"],
    }


def _comparisons(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ref = results["production"]
    keys = (
        "phi_min_V",
        "phi_max_V",
        "volume_charge_C",
        "n_e_min_m3",
        "primary_electron_particle_rate_s-1",
        "net_outward_wall_current_A",
        "primary_wall_power_W",
    )
    out: dict[str, Any] = {}
    for mode in MODES[1:]:
        item = {}
        for key in keys:
            a = float(ref[key])
            b = float(results[mode][key])
            scale = max(abs(a), 1e-300)
            item[key] = {"absolute_change": b - a, "relative_change": (b - a) / scale}
        out[mode] = item
    return out


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    p0 = self_test()
    _write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        raise RuntimeError(p0)

    results: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {"status": "RUNNING", "cases": {}}
    for mode in MODES:
        text, meta = build_case(mode)
        case_dir = out / "cases" / mode
        logs = out / "logs" / mode
        logs.mkdir(parents=True, exist_ok=True)
        stage = sci._stage(case_dir, text, meta)
        p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 300.0))
        case_summary: dict[str, Any] = {"meta": meta, "stage": stage, "p2": p2}
        if p2.get("returncode") != 0:
            case_summary["status"] = "P2_FAIL"
            summary["cases"][mode] = case_summary
            summary["status"] = "FAIL"
            _write(out / "summary.json", summary)
            return 2
        runtime = sci._runtime(exe, case_dir, logs / "runtime.log", logs / "time_v.log", float(args.timeout))
        case_summary["runtime"] = runtime
        try:
            result = _case_result(case_dir, text, meta, runtime)
            results[mode] = result
            case_summary["result"] = result
            case_summary["status"] = "PASS" if result["runtime_returncode"] == 0 else "FAIL"
        except Exception as exc:
            case_summary["status"] = "ANALYSIS_FAIL"
            case_summary["analysis_error"] = f"{type(exc).__name__}: {exc}"
        summary["cases"][mode] = case_summary

    if len(results) == len(MODES):
        summary["comparisons_to_production"] = _comparisons(results)
    summary["status"] = "PASS" if all(v.get("status") == "PASS" for v in summary["cases"].values()) else "FAIL"
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue228-two-point-controls-results"))
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
