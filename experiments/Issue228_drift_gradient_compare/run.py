#!/usr/bin/env python3
"""Issue #228 electron-drift gradient treatment comparison.

Equal-physics one-step controls:

  production  : current corrected multidimensional electron-drift gradient, R0
  two_point   : two-point face-normal electron-drift gradient, R0
  limit_050   : non-orthogonal correction capped at 0.5*|central|, R0
  limit_100   : non-orthogonal correction capped at 1.0*|central|, R0
  production_r1 : current production gradient with uniform_refine=1

No physical coefficient, sheath law, chemistry, dt, or physical horizon is
changed. production_r1 is a resolution control, not a mesh-angle-quality fix.
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
MODES = ("production", "two_point", "limit_050", "limit_100", "production_r1")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_case(mode: str) -> tuple[str, dict[str, Any]]:
    if mode not in MODES:
        raise ValueError(mode)
    refine = 1 if mode == "production_r1" else 0
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=refine)
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{DT_S:.17g}")
    text = mp.upsert_parameter(text, "Outputs", "exodus", "true")

    if mode == "two_point":
        text = mp.upsert_parameter(
            text, "FVKernels/n_e_drift", "type", "PhysicsFVTwoPointElectrostaticDriftControl"
        )
    elif mode in ("limit_050", "limit_100"):
        text = mp.upsert_parameter(
            text, "FVKernels/n_e_drift", "type", "PhysicsFVLimitedElectrostaticDriftControl"
        )
        ratio = "0.5" if mode == "limit_050" else "1.0"
        text = mp.upsert_parameter(text, "FVKernels/n_e_drift", "correction_cap_ratio", ratio)

    meta = {
        **meta,
        "issue": 228,
        "claim": "electron_drift_gradient_treatment_comparison",
        "diagnostic_only": True,
        "mode": mode,
        "expected_steps": 1,
        "dt_s": DT_S,
        "end_time_s": DT_S,
        "uniform_refine": refine,
        "physical_coefficients_changed": False,
        "sheath_law_changed": False,
        "chemistry_changed": False,
    }
    return text, meta


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for mode in MODES:
        text, meta = build_case(mode)
        drift_type = mp.get_parameter(text, "FVKernels/n_e_drift", "type")
        cap = mp.get_parameter(text, "FVKernels/n_e_drift", "correction_cap_ratio")
        checks[f"{mode}:dt"] = math.isclose(
            float(mp.get_parameter(text, "Executioner", "dt") or "nan"), DT_S, rel_tol=0.0, abs_tol=0.0
        )
        checks[f"{mode}:end"] = math.isclose(
            float(mp.get_parameter(text, "Executioner", "end_time") or "nan"), DT_S,
            rel_tol=0.0, abs_tol=1e-24
        )
        checks[f"{mode}:refine"] = meta["uniform_refine"] == (1 if mode == "production_r1" else 0)
        if mode == "two_point":
            checks[f"{mode}:type"] = drift_type == "PhysicsFVTwoPointElectrostaticDriftControl"
        elif mode in ("limit_050", "limit_100"):
            checks[f"{mode}:type"] = drift_type == "PhysicsFVLimitedElectrostaticDriftControl"
            checks[f"{mode}:cap"] = math.isclose(float(cap or "nan"), 0.5 if mode == "limit_050" else 1.0)
        else:
            checks[f"{mode}:type"] = drift_type == "PhysicsFVElectrostaticDrift"
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
    phi_min = float(state["phi_min_V"])
    phi_max = float(state["phi_max_V"])
    return {
        "runtime_returncode": int(runtime.get("returncode", 1)),
        "timed_out": bool(runtime.get("timed_out", False)),
        "step_hard_pass": step.get("hard_pass") is True,
        "phi_min_V": phi_min,
        "phi_max_V": phi_max,
        "phi_span_V": phi_max - phi_min,
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
        "exodus_files": sorted(path.name for path in case_dir.glob("*.e*")),
    }


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

    summary: dict[str, Any] = {"status": "RUNNING", "cases": {}}
    good = True
    for mode in MODES:
        text, meta = build_case(mode)
        case_dir = out / "cases" / mode
        logs = out / "logs" / mode
        logs.mkdir(parents=True, exist_ok=True)
        stage = sci._stage(case_dir, text, meta)
        p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 300.0))
        cs: dict[str, Any] = {"meta": meta, "stage": stage, "p2": p2}
        if p2.get("returncode") != 0:
            cs["status"] = "P2_FAIL"
            good = False
            summary["cases"][mode] = cs
            continue
        runtime = sci._runtime(exe, case_dir, logs / "runtime.log", logs / "time_v.log", float(args.timeout))
        cs["runtime"] = runtime
        try:
            result = _case_result(case_dir, text, meta, runtime)
            cs["result"] = result
            cs["status"] = "PASS" if result["runtime_returncode"] == 0 and result["step_hard_pass"] else "FAIL"
            good = good and cs["status"] == "PASS"
        except Exception as exc:
            cs["status"] = "ANALYSIS_FAIL"
            cs["analysis_error"] = f"{type(exc).__name__}: {exc}"
            good = False
        summary["cases"][mode] = cs
        _write(out / "summary.partial.json", summary)

    prod = summary["cases"].get("production", {}).get("result")
    if prod:
        comparisons = {}
        for mode in MODES[1:]:
            result = summary["cases"].get(mode, {}).get("result")
            if not result:
                continue
            comparisons[mode] = {
                "phi_span_reduction_fraction": 1.0 - float(result["phi_span_V"]) / max(float(prod["phi_span_V"]), 1e-300),
                "volume_charge_relative_change": (float(result["volume_charge_C"]) - float(prod["volume_charge_C"])) / max(abs(float(prod["volume_charge_C"])), 1e-300),
                "wall_current_relative_change": (float(result["net_outward_wall_current_A"]) - float(prod["net_outward_wall_current_A"])) / max(abs(float(prod["net_outward_wall_current_A"])), 1e-300),
                "primary_electron_rate_relative_change": (float(result["primary_electron_particle_rate_s-1"]) - float(prod["primary_electron_particle_rate_s-1"])) / max(abs(float(prod["primary_electron_particle_rate_s-1"])), 1e-300),
            }
        summary["comparisons_to_production"] = comparisons

    summary["status"] = "PASS" if good else "PARTIAL_OR_FAIL"
    _write(out / "summary.json", summary)
    return 0 if good else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue228-drift-gradient-compare-results"))
    parser.add_argument("--timeout", type=float, default=900.0)
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
