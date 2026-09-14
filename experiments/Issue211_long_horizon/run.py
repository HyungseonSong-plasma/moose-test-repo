#!/usr/bin/env python3
"""100-step standalone production check for Issue #211 with Exodus output.

Runs accepted production wall physics (sheath suppression ON + wall-energy
feedback ON) at the baseline R0 mesh for 100 physical steps. CSV, checkpoint,
and Exodus outputs are retained so the long-horizon scalar ledgers and full
spatial fields can both be inspected. This does not establish mesh convergence.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue211_science_factorial import run as sci
from experiments.Issue216_w5_multistep_acceptance import run as w5
from physics_harness.adapters.moose import parameters as mp

DT_S = w5.BASELINE_DT_S
ALLOWED_STEPS = (100,)


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_case(steps: int) -> tuple[str, dict[str, Any]]:
    if steps not in ALLOWED_STEPS:
        raise ValueError(f"steps must be one of {ALLOWED_STEPS}")
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=0)
    end_time = steps * DT_S
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{end_time:.17g}")
    text = mp.upsert_parameter(text, "Outputs", "exodus", "true")
    meta = {
        **meta,
        "issue": 211,
        "claim": "standalone_100step_long_horizon_with_exodus",
        "expected_steps": steps,
        "end_time_s": end_time,
        "uniform_refine": 0,
        "sheath_potential_suppression": True,
        "wall_energy_feedback": True,
        "exodus_output": True,
    }
    return text, meta


def self_test() -> dict[str, Any]:
    checks = {}
    for steps in ALLOWED_STEPS:
        text, meta = build_case(steps)
        checks[f"steps_{steps}_count"] = meta["expected_steps"] == steps
        checks[f"steps_{steps}_dt"] = math.isclose(
            float(mp.get_parameter(text, "Executioner", "dt") or "nan"), DT_S, rel_tol=0.0, abs_tol=0.0
        )
        checks[f"steps_{steps}_end"] = math.isclose(
            float(mp.get_parameter(text, "Executioner", "end_time") or "nan"),
            steps * DT_S,
            rel_tol=0.0,
            abs_tol=1e-24,
        )
        exodus = (mp.get_parameter(text, "Outputs", "exodus") or "").strip().strip("'\"").lower()
        checks[f"steps_{steps}_exodus"] = exodus == "true"
    failed = sorted(k for k, v in checks.items() if not v)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _analyze(case_dir: Path, text: str, meta: Mapping[str, Any], runtime_log: Path, returncode: int) -> dict[str, Any]:
    rows = s5r._read_rows(case_dir / "input_out.csv")
    physical = w5._physical_rows(rows)
    if not physical:
        raise RuntimeError("no physical TIMESTEP_END rows")

    steps_ev = [
        w5._step_evidence(prev, cur, input_text=text, meta=meta)
        for prev, cur in zip(rows[:-1], rows[1:])
    ]
    final_time = s5r._num(physical[-1], "time")
    expected_steps = int(meta["expected_steps"])
    solver = w5._solver_evidence(runtime_log, returncode=returncode)
    state = s5r._state_evidence(physical)
    target_time = float(meta["end_time_s"])
    exodus_files = sorted(path.name for path in case_dir.glob("*.e*"))
    gates = {
        "runtime_complete": returncode == 0 and math.isclose(final_time, target_time, rel_tol=0.0, abs_tol=1e-18),
        "expected_step_count": len(steps_ev) == expected_steps,
        "all_step_ledgers": bool(steps_ev) and all(step["hard_pass"] for step in steps_ev),
        "state_invariants": state.get("hard_pass") is True,
        "solver_evidence": solver.get("healthy") is True,
        "exodus_output_present": bool(exodus_files),
    }
    checkpoints = {}
    for idx in (5, 10, 20, 30, 50, 75, 100):
        if idx <= len(steps_ev):
            step = steps_ev[idx - 1]
            checkpoints[str(idx)] = {
                "time_s": step["time_final_s"],
                "phi_min_V": step["state"]["phi_min_V"],
                "phi_max_V": step["state"]["phi_max_V"],
                "volume_charge_C": step["state"]["volume_charge_C"],
                "mean_energy_avg_eV": step["state"]["mean_energy_avg_eV"],
                "n_e_min_m3": step["state"]["n_e_min_m3"],
                "primary_electron_particle_rate_s-1": step["wall_current"]["primary_electron_particle_rate_s-1"],
                "net_outward_wall_current_A": step["wall_current"]["net_outward_wall_current_A"],
                "primary_wall_power_W": step["electron_energy"]["primary_wall_power_W"],
                "hard_pass": step["hard_pass"],
            }
    phi_series = [step["state"]["phi_max_V"] for step in steps_ev]
    current_series = [step["wall_current"]["net_outward_wall_current_A"] for step in steps_ev]
    tail = phi_series[-min(5, len(phi_series)):]
    plateau_span = max(tail) - min(tail) if tail else math.nan
    plateau_rel = plateau_span / max(abs(sum(tail) / len(tail)), 1e-300) if tail else math.nan
    return {
        "final_time_s": final_time,
        "expected_steps": expected_steps,
        "measured_steps": len(steps_ev),
        "gates": gates,
        "hard_pass": all(gates.values()),
        "state": state,
        "solver": solver,
        "endpoint": w5._endpoint(physical, meta=meta),
        "checkpoints": checkpoints,
        "exodus_files": exodus_files,
        "phi_max_series_V": phi_series,
        "net_wall_current_series_A": current_series,
        "tail_5step_phi_span_V": plateau_span,
        "tail_5step_phi_relative_span": plateau_rel,
        "max_defects": {
            "electron_particle": max(step["electron_particle"]["relative_defect"] for step in steps_ev),
            "electron_energy": max(step["electron_energy"]["relative_defect"] for step in steps_ev),
            "current_charge": max(step["charge"]["relative_defect_over_boundary_current_scale"] for step in steps_ev),
            "gauss": max(step["gauss"]["relative_defect"] for step in steps_ev),
        },
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

    text, meta = build_case(args.steps)
    case_dir = out / "case"
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stage = sci._stage(case_dir, text, meta)
    p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 600.0))
    summary: dict[str, Any] = {"meta": meta, "stage": stage, "p2": p2, "status": "RUNNING"}
    if p2.get("returncode") != 0:
        summary["status"] = "P2_FAIL"
        _write(out / "summary.json", summary)
        return 2

    runtime_log = logs / "runtime.log"
    runtime = sci._runtime(exe, case_dir, runtime_log, logs / "time_v.log", float(args.timeout))
    summary["runtime"] = runtime
    try:
        analysis = _analyze(case_dir, text, meta, runtime_log, int(runtime.get("returncode", 1)))
    except Exception as exc:
        analysis = {"hard_pass": False, "analysis_error": f"{type(exc).__name__}: {exc}"}
    summary["analysis"] = analysis
    summary["status"] = "PASS" if analysis.get("hard_pass") else ("TIMEOUT_PARTIAL" if runtime.get("timed_out") else "FAIL")
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue211-long-horizon-results"))
    parser.add_argument("--steps", type=int, choices=ALLOWED_STEPS)
    parser.add_argument("--timeout", type=float, default=4800.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None or args.steps is None:
        parser.error("--physics-opt and --steps are required unless --self-test is used")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
