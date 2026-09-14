#!/usr/bin/env python3
"""Fast causal science campaign for Issue #211.

Two-factor design:
  A: sheath-potential suppression OFF/ON
  B: primary-electron wall-energy feedback OFF/ON

The full 2x2 factorial is run at R0 and R1.  The accepted production
combination (A=ON, B=ON) is additionally run at R2 with a low-observability
science profile. Governing equations, solver, dt, end time, and wall model
implementation are otherwise unchanged.
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
from experiments.Issue216_w5_multistep_acceptance import run as w5
from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue224_observability_memory import run_c5r as c5r
from experiments.Issue224_science_profiles import run as science_profiles
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case, validate_case_references
from physics_harness.execution.runtime import run_command

DT_S = w5.BASELINE_DT_S
END_TIME_S = w5.END_TIME_S
ZERO_PHI_FUNCTOR = "issue211_science_zero_potential"
ZERO_NE_FUNCTOR = "issue211_science_zero_electron_density"
PARTICLE_BC_PATH = f"FVBCs/{w45.PARTICLE_BC}"
ENERGY_BC_PATH = f"FVBCs/{w45.ENERGY_BC}"
FUNCTIONAL_KEEP = {"Postprocessors/inlet_area"}
R2_KEEP = set(science_profiles.MONITORED_KEEP) | FUNCTIONAL_KEEP

CASE_SPECS: dict[str, dict[str, Any]] = {
    "r0_s0_e0": {"refine": 0, "suppression": False, "energy": False, "lean": False},
    "r0_s0_e1": {"refine": 0, "suppression": False, "energy": True, "lean": False},
    "r0_s1_e0": {"refine": 0, "suppression": True, "energy": False, "lean": False},
    "r0_s1_e1": {"refine": 0, "suppression": True, "energy": True, "lean": False},
    "r1_s0_e0": {"refine": 1, "suppression": False, "energy": False, "lean": False},
    "r1_s0_e1": {"refine": 1, "suppression": False, "energy": True, "lean": False},
    "r1_s1_e0": {"refine": 1, "suppression": True, "energy": False, "lean": False},
    "r1_s1_e1": {"refine": 1, "suppression": True, "energy": True, "lean": False},
    "r2_prod": {"refine": 2, "suppression": True, "energy": True, "lean": True},
}


class Science211Error(RuntimeError):
    pass


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _insert_zero_functor(text: str, name: str) -> str:
    path = f"FunctorMaterials/{name}"
    if mb.has_block(text, path):
        return text
    return mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{name}]
    type = ADGenericFunctorMaterial
    prop_names = '{name}'
    prop_values = '0'
    block = plasma
  []""",
    )


def _apply_factors(text: str, *, suppression: bool, energy: bool) -> str:
    if not suppression:
        text = _insert_zero_functor(text, ZERO_PHI_FUNCTOR)
        text = mp.upsert_parameter(text, PARTICLE_BC_PATH, "potential", ZERO_PHI_FUNCTOR)
        text = mp.upsert_parameter(text, ENERGY_BC_PATH, "potential", ZERO_PHI_FUNCTOR)
    if not energy:
        text = _insert_zero_functor(text, ZERO_NE_FUNCTOR)
        text = mp.upsert_parameter(text, ENERGY_BC_PATH, "electron_density", ZERO_NE_FUNCTOR)
    return text


def build_case(case_name: str) -> tuple[str, dict[str, Any]]:
    if case_name not in CASE_SPECS:
        raise Science211Error(f"unknown case {case_name!r}")
    spec = CASE_SPECS[case_name]
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=int(spec["refine"]))
    text = _apply_factors(
        text,
        suppression=bool(spec["suppression"]),
        energy=bool(spec["energy"]),
    )
    profile_meta: dict[str, Any] = {"mode": "FULL_SCIENCE_DIAGNOSTICS"}
    if spec["lean"]:
        text, profile_meta = science_profiles._profile(text, R2_KEEP)
    return text, {
        **meta,
        "issue": 211,
        "claim": "sheath_potential_suppression_x_wall_energy_feedback_factorial",
        "case_name": case_name,
        "sheath_potential_suppression": bool(spec["suppression"]),
        "wall_energy_feedback": bool(spec["energy"]),
        "uniform_refine": int(spec["refine"]),
        "science_profile": "LEAN_MONITORED" if spec["lean"] else "FULL",
        "profile": profile_meta,
        "factor_definition": {
            "suppression_off": "set grounded-sheath potential functor to exactly 0 V for particle and energy owners",
            "energy_feedback_off": "set grounded-sheath energy-owner electron-density functor to exactly 0, leaving particle owner unchanged",
        },
    }


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    for name, spec in CASE_SPECS.items():
        text, meta = build_case(name)
        particle_phi = mp.get_parameter(text, PARTICLE_BC_PATH, "potential")
        energy_phi = mp.get_parameter(text, ENERGY_BC_PATH, "potential")
        energy_ne = mp.get_parameter(text, ENERGY_BC_PATH, "electron_density")
        checks[f"{name}_particle_suppression_semantics"] = (
            particle_phi == "potential_plasma" if spec["suppression"] else particle_phi == ZERO_PHI_FUNCTOR
        )
        checks[f"{name}_energy_suppression_semantics"] = (
            energy_phi == "potential_plasma" if spec["suppression"] else energy_phi == ZERO_PHI_FUNCTOR
        )
        checks[f"{name}_energy_feedback_semantics"] = (
            energy_ne == "n_e" if spec["energy"] else energy_ne == ZERO_NE_FUNCTOR
        )
        checks[f"{name}_dt_unchanged"] = math.isclose(
            float(mp.get_parameter(text, "Executioner", "dt") or "nan"), DT_S, rel_tol=0.0, abs_tol=0.0
        )
        checks[f"{name}_end_time_unchanged"] = math.isclose(
            float(mp.get_parameter(text, "Executioner", "end_time") or "nan"), END_TIME_S, rel_tol=0.0, abs_tol=0.0
        )
        checks[f"{name}_refinement"] = int(meta["uniform_refine"]) == int(spec["refine"])
        if spec["lean"]:
            inlet_execute = (mp.get_parameter(text, "Postprocessors/inlet_area", "execute_on") or "").strip().strip("'\"")
            checks[f"{name}_functional_inlet_area_kept"] = inlet_execute != "NONE"
            checks[f"{name}_observer_reduction_active"] = int(meta["profile"]["disabled_passive_count"]) > 0
        details[name] = {
            "particle_potential": particle_phi,
            "energy_potential": energy_phi,
            "energy_electron_density": energy_ne,
            "profile": meta["science_profile"],
        }
    failed = sorted(k for k, v in checks.items() if not v)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed, "details": details}


def _stage(case_dir: Path, text: str, meta: Mapping[str, Any]) -> dict[str, Any]:
    staged = stage_case(
        w5.SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    s5r._copy_runtime_assets(case_dir)
    refs = validate_case_references(case_dir)
    _write(case_dir / "prepare_evidence.json", {**dict(meta), "references": refs})
    return {"staging": staged, "references": refs}


def _runtime(exe: Path, case_dir: Path, runtime_log: Path, time_log: Path, timeout: float) -> dict[str, Any]:
    command = [
        str(c5r.TIME_BIN), "-v", "-o", str(time_log.resolve()),
        str(exe), "-i", "input.i", "-snes_monitor", "-snes_converged_reason", "-ksp_converged_reason",
    ]
    result = run_command(command, cwd=case_dir, log_path=runtime_log, timeout_seconds=timeout)
    log_text = runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""
    time_text = time_log.read_text(errors="replace") if time_log.is_file() else ""
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "runtime_facts": s5r._runtime_log_facts(log_text, returncode=result.returncode, timed_out=result.timed_out),
        "os_max_rss_mib": c5r._parse_time_max_rss_mib(time_text),
    }


def _science_step_pass(step: Mapping[str, Any], *, energy_feedback: bool) -> bool:
    gates = dict(step.get("gates", {}))
    if not energy_feedback:
        gates.pop("primary_energy_owner_active", None)
    return bool(gates) and all(bool(v) for v in gates.values())


def _full_analysis(case_dir: Path, text: str, meta: Mapping[str, Any], runtime_log: Path, returncode: int) -> dict[str, Any]:
    evidence = w5._analyze_case(
        case_dir,
        input_text=text,
        meta=meta,
        runtime_log=runtime_log,
        runtime_returncode=returncode,
    )
    step_passes = [
        _science_step_pass(step, energy_feedback=bool(meta["wall_energy_feedback"]))
        for step in evidence.get("steps", [])
    ]
    science_gates = {
        "runtime_complete": evidence.get("gates", {}).get("runtime_complete") is True,
        "expected_step_count": evidence.get("gates", {}).get("expected_step_count") is True,
        "state_invariants": evidence.get("gates", {}).get("state_invariants") is True,
        "solver_evidence": evidence.get("gates", {}).get("solver_evidence") is True,
        "science_step_ledgers": bool(step_passes) and all(step_passes),
    }
    chronology = []
    for step in evidence.get("steps", []):
        chronology.append({
            "time_s": step["time_final_s"],
            "phi_min_V": step["state"]["phi_min_V"],
            "phi_max_V": step["state"]["phi_max_V"],
            "volume_charge_C": step["state"]["volume_charge_C"],
            "n_e_min_m3": step["state"]["n_e_min_m3"],
            "n_e_inventory": step["state"]["n_e_inventory"],
            "mean_energy_avg_eV": step["state"]["mean_energy_avg_eV"],
            "primary_electron_particle_rate_s-1": step["wall_current"]["primary_electron_particle_rate_s-1"],
            "net_outward_wall_current_A": step["wall_current"]["net_outward_wall_current_A"],
            "primary_wall_power_W": step["electron_energy"]["primary_wall_power_W"],
            "particle_balance_rel_defect": step["electron_particle"]["relative_defect"],
            "energy_balance_rel_defect": step["electron_energy"]["relative_defect"],
            "current_charge_rel_defect": step["charge"]["relative_defect_over_boundary_current_scale"],
            "gauss_rel_defect": step["gauss"]["relative_defect"],
        })
    return {
        "w5_evidence": evidence,
        "chronology": chronology,
        "science_gates": science_gates,
        "science_hard_pass": all(science_gates.values()),
    }


def _lean_analysis(case_dir: Path, meta: Mapping[str, Any], runtime_log: Path, returncode: int) -> dict[str, Any]:
    rows = []
    try:
        rows = [r for r in s5r._read_rows(case_dir / "input_out.csv") if s5r._num(r, "time") > 1.0e-15]
    except Exception:
        rows = []
    solver = w5._solver_evidence(runtime_log, returncode=returncode)
    fingerprint: dict[str, float] = {}
    monitored: dict[str, float] = {}
    sanity: dict[str, Any] = {"pass": False, "reason": "no_physical_rows"}
    final_time = math.nan
    if rows:
        row = rows[-1]
        final_time = s5r._num(row, "time")
        try:
            fingerprint = {key: s5r._num(row, key) for key in science_profiles.FINGERPRINT_KEYS}
            sanity = science_profiles._state_sanity(fingerprint)
            monitored = {
                "s5r_mean_en_avg": s5r._num(row, "s5r_mean_en_avg"),
                "s5r_mean_en_min": s5r._num(row, "s5r_mean_en_min"),
                "s5r_mean_en_max": s5r._num(row, "s5r_mean_en_max"),
            }
        except Exception as exc:
            sanity = {"pass": False, "error": f"{type(exc).__name__}: {exc}"}
    expected_steps = int(meta["expected_steps"])
    gates = {
        "runtime_complete": returncode == 0 and math.isclose(final_time, END_TIME_S, rel_tol=0.0, abs_tol=1.0e-18),
        "expected_step_count": len(rows) == expected_steps,
        "solver_evidence": solver.get("healthy") is True,
        "state_sanity": sanity.get("pass") is True,
    }
    return {
        "measured_steps": len(rows),
        "expected_steps": expected_steps,
        "final_time_s": final_time,
        "fingerprint": fingerprint,
        "monitored": monitored,
        "state_sanity": sanity,
        "solver": solver,
        "science_gates": gates,
        "science_hard_pass": all(gates.values()),
    }


def run_case(args: argparse.Namespace) -> int:
    if args.case not in CASE_SPECS:
        raise Science211Error(f"unknown case: {args.case}")
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Science211Error(f"invalid physics-opt: {exe}")

    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    p0 = self_test()
    _write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        raise Science211Error(f"self-test failed: {p0['failed_checks']}")

    text, meta = build_case(args.case)
    case_dir = out / "case"
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stage = _stage(case_dir, text, meta)
    p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 600.0))
    summary: dict[str, Any] = {
        "status": "RUNNING",
        "case": args.case,
        "meta": meta,
        "stage": stage,
        "p2": p2,
        "science_hard_pass": False,
    }
    if p2.get("returncode") != 0:
        summary["status"] = "P2_FAIL"
        _write(out / "summary.json", summary)
        return 2

    runtime_log = logs / "runtime.log"
    runtime = _runtime(exe, case_dir, runtime_log, logs / "time_v.log", float(args.timeout))
    summary["runtime"] = runtime
    try:
        if bool(CASE_SPECS[args.case]["lean"]):
            analysis = _lean_analysis(case_dir, meta, runtime_log, int(runtime.get("returncode", 1)))
        else:
            analysis = _full_analysis(case_dir, text, meta, runtime_log, int(runtime.get("returncode", 1)))
    except Exception as exc:
        analysis = {"science_hard_pass": False, "analysis_error": f"{type(exc).__name__}: {exc}"}
    summary["analysis"] = analysis
    summary["science_hard_pass"] = analysis.get("science_hard_pass") is True
    summary["status"] = "PASS" if summary["science_hard_pass"] else ("TIMEOUT_PARTIAL" if runtime.get("timed_out") else "FAIL")
    _write(out / "summary.json", summary)
    return 0 if summary["science_hard_pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue211-science-results"))
    parser.add_argument("--case", choices=tuple(CASE_SPECS))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None or args.case is None:
        parser.error("--physics-opt and --case are required unless --self-test is used")
    return run_case(args)


if __name__ == "__main__":
    raise SystemExit(main())
