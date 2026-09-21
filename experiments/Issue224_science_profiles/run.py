#!/usr/bin/env python3
"""Issue #224 terminal R2 science-profile qualification.

Qualifies three execution profiles on the exact W5 R2 physical case:
FULL, SCIENCE_LEAN, and SCIENCE_MONITORED.  LEAN/MONITORED change only
passive Postprocessor execution schedules; governing physics, solver, mesh,
timestep, and end time are unchanged.

LEAN also writes a checkpoint.  A fourth DIAGNOSTIC_REPLAY case recovers the
LEAN final state, executes the full passive diagnostic surface on EXEC_FINAL,
and performs no additional physical timestep.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue216_w5_multistep_acceptance import run as w5
from experiments.Issue224_observability_memory import run as c3
from experiments.Issue224_observability_memory import run_c5 as c5
from experiments.Issue224_observability_memory import run_c5r as c5r
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case, validate_case_references
from physics_harness.execution.runtime import run_command

R2_LEVEL = 2
DT_S = w5.BASELINE_DT_S
END_TIME_S = w5.END_TIME_S
PARITY_TOL = 1.0e-4

LEAN_KEEP = {
    "Postprocessors/domain_volume",
    "Postprocessors/n_e_inventory",
    "Postprocessors/s5r_n_epsilon_inventory",
    "Postprocessors/n_e_min",
    "Postprocessors/s5r_n_epsilon_min",
    "Postprocessors/n_e_avg",
    "Postprocessors/sum_w_min",
    "Postprocessors/sum_w_max",
    "Postprocessors/w_O2_avg",
    "Postprocessors/w_O2s_avg",
    "Postprocessors/w_O2p_avg",
    "Postprocessors/w_O_avg",
    "Postprocessors/w_Om_avg",
    "Postprocessors/w_Op_avg",
    "Postprocessors/w_Os_avg",
    "Postprocessors/issue217_phi_min",
    "Postprocessors/issue217_phi_max",
}
MONITORED_EXTRA = {
    "Postprocessors/s5r_mean_en_avg",
    "Postprocessors/s5r_mean_en_min",
    "Postprocessors/s5r_mean_en_max",
    "Postprocessors/electron_mobility_avg",
    "Postprocessors/electron_diffusion_avg",
    "Postprocessors/electron_pressure_avg",
    "Postprocessors/electron_gas_temperature_avg",
}
MONITORED_KEEP = LEAN_KEEP | MONITORED_EXTRA
FINGERPRINT_KEYS = (
    "domain_volume", "n_e_inventory", "s5r_n_epsilon_inventory", "n_e_min",
    "s5r_n_epsilon_min", "n_e_avg", "sum_w_min", "sum_w_max", "w_O2_avg",
    "w_O2s_avg", "w_O2p_avg", "w_O_avg", "w_Om_avg", "w_Op_avg", "w_Os_avg",
    "issue217_phi_min", "issue217_phi_max",
)

class Issue224ScienceProfileError(RuntimeError):
    pass

def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

def _base() -> tuple[str, dict[str, Any]]:
    return w5._build_case(dt_s=DT_S, uniform_refine=R2_LEVEL)

def _profile(text: str, keep: set[str], *, schedule: str = "'INITIAL TIMESTEP_END'") -> tuple[str, dict[str, Any]]:
    paths = c3._postprocessor_paths(text)
    passive, receivers, unknown = [], [], []
    before = c5._observer_snapshot(text)
    for path in paths:
        typ = mp.get_parameter(text, path, "type")
        if typ == "Receiver":
            receivers.append(path); continue
        if typ not in c3.PASSIVE_TYPES:
            unknown.append({"path": path, "type": typ}); continue
        target = schedule if path in keep else "'NONE'"
        old = mp.get_parameter(text, path, "execute_on")
        text = mp.upsert_parameter(text, path, "execute_on", target)
        passive.append({"path": path, "type": typ, "old_execute_on": old, "new_execute_on": target})
    if unknown:
        raise Issue224ScienceProfileError(f"unclassified postprocessors: {unknown}")
    if len(passive) != c3.EXPECTED_PASSIVE_COUNT:
        raise Issue224ScienceProfileError(f"expected {c3.EXPECTED_PASSIVE_COUNT} passive observers, got {len(passive)}")
    missing = sorted(keep - {x["path"] for x in passive})
    if missing:
        raise Issue224ScienceProfileError(f"profile keep paths missing/not passive: {missing}")
    after = c5._observer_snapshot(text)
    changed_outside = sorted(p for p in before if p not in {x["path"] for x in passive} and before[p] != after[p])
    if changed_outside:
        raise Issue224ScienceProfileError(f"non-passive postprocessor drift: {changed_outside}")
    return text, {
        "postprocessor_count": len(paths), "passive_count": len(passive),
        "receiver_count": len(receivers), "kept_passive_count": len(keep),
        "disabled_passive_count": len(passive) - len(keep), "kept_paths": sorted(keep),
        "receivers": sorted(receivers), "changed_non_passive_count": 0,
    }

def build_profile(profile: str) -> tuple[str, dict[str, Any]]:
    text, meta = _base()
    if profile == "FULL":
        profile_meta = {"postprocessor_count": len(c3._postprocessor_paths(text)), "passive_count": c3.EXPECTED_PASSIVE_COUNT, "kept_passive_count": c3.EXPECTED_PASSIVE_COUNT, "disabled_passive_count": 0, "kept_paths": "production"}
    elif profile == "SCIENCE_LEAN":
        text, profile_meta = _profile(text, LEAN_KEEP)
        text = mp.upsert_parameter(text, "Outputs", "checkpoint", "true")
    elif profile == "SCIENCE_MONITORED":
        text, profile_meta = _profile(text, MONITORED_KEEP)
    elif profile == "DIAGNOSTIC_REPLAY":
        all_passive = {p for p in c3._postprocessor_paths(text) if mp.get_parameter(text, p, "type") in c3.PASSIVE_TYPES}
        text, profile_meta = _profile(text, all_passive, schedule="'FINAL'")
        text = mp.upsert_parameter(text, "Outputs", "checkpoint", "true")
        text = mp.upsert_parameter(text, "Outputs", "execute_on", "'FINAL'")
    else:
        raise Issue224ScienceProfileError(f"unknown profile {profile!r}")
    return text, {**meta, "issue": 224, "claim": "R2_science_profile_operational_qualification", "science_profile": profile, "uniform_refine": R2_LEVEL, "profile": profile_meta, "governing_physics_changed": False, "solver_changed": False, "mesh_changed": False, "timestep_changed": False, "end_time_changed": False}

def _stage(case_dir: Path, text: str, meta: Mapping[str, Any]) -> None:
    stage_case(w5.SOURCE, case_dir, input_text=text, purge_directory_names=(".jitcache", "checkpoint", "checkpoints"), purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"))
    s5r._copy_runtime_assets(case_dir)
    refs = validate_case_references(case_dir)
    (case_dir / "prepare_evidence.json").write_text(json.dumps({**dict(meta), "references": refs}, indent=2, sort_keys=True) + "\n")

def _runtime(exe: Path, case_dir: Path, runtime_log: Path, time_log: Path, *, timeout: float, recover: bool = False) -> dict[str, Any]:
    command = [str(c5r.TIME_BIN), "-v", "-o", str(time_log.resolve()), str(exe), "-i", "input.i", "-snes_monitor", "-snes_converged_reason", "-ksp_converged_reason"]
    if recover: command.append("--recover")
    result = run_command(command, cwd=case_dir, log_path=runtime_log, timeout_seconds=timeout)
    log_text = runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""
    time_text = time_log.read_text(errors="replace") if time_log.is_file() else ""
    return {"returncode": result.returncode, "wall_seconds": result.wall_seconds, "timed_out": result.timed_out, "runtime_facts": s5r._runtime_log_facts(log_text, returncode=result.returncode, timed_out=result.timed_out), "os_max_rss_mib": c5r._parse_time_max_rss_mib(time_text), "recover": recover}

def _physical_rows(case_dir: Path) -> list[dict[str, str]]:
    rows = s5r._read_rows(case_dir / "input_out.csv")
    return [r for r in rows if s5r._num(r, "time") > 1.0e-15]

def _fingerprint(case_dir: Path) -> dict[str, float]:
    rows = _physical_rows(case_dir)
    if not rows: raise Issue224ScienceProfileError("no physical rows for fingerprint")
    row = rows[-1]
    return {key: s5r._num(row, key) for key in FINGERPRINT_KEYS}

def _compare(a: Mapping[str, float], b: Mapping[str, float]) -> dict[str, Any]:
    keys = sorted(set(a) & set(b)); values = {}
    for key in keys:
        av, bv = float(a[key]), float(b[key])
        diff = abs(av - bv) / max(abs(av), abs(bv), 1.0e-300)
        values[key] = {"a": av, "b": bv, "symmetric_relative_difference": diff}
    mx = max((v["symmetric_relative_difference"] for v in values.values()), default=math.inf)
    return {"values": values, "max_symmetric_relative_difference": mx, "tolerance": PARITY_TOL, "pass": bool(values) and mx <= PARITY_TOL}

def _state_sanity(fp: Mapping[str, float]) -> dict[str, Any]:
    checks = {"finite": all(math.isfinite(float(v)) for v in fp.values()), "electron_density_positive": float(fp["n_e_min"]) >= -1.0e-12, "electron_energy_positive": float(fp["s5r_n_epsilon_min"]) > 0.0, "composition_min": abs(float(fp["sum_w_min"]) - 1.0) <= 1.0e-8, "composition_max": abs(float(fp["sum_w_max"]) - 1.0) <= 1.0e-8, "domain_positive": float(fp["domain_volume"]) > 0.0}
    return {"checks": checks, "pass": all(checks.values())}

def _execute_physical(exe: Path, out: Path, name: str, profile: str, *, timeout: float) -> dict[str, Any]:
    text, meta = build_profile(profile); case_dir = out / "cases" / name; logs = out / "logs"; logs.mkdir(parents=True, exist_ok=True)
    _stage(case_dir, text, meta)
    p2 = s5r._p2(exe, case_dir, logs / f"{name}_p2.log", timeout=timeout)
    item: dict[str, Any] = {"profile": profile, "meta": meta, "p2": p2, "hard_pass": False}
    if p2.get("returncode") != 0: item["reason"] = "P2_FAIL"; return item
    runtime_log = logs / f"{name}_runtime.log"
    runtime = _runtime(exe, case_dir, runtime_log, logs / f"{name}_time_v.log", timeout=timeout)
    item["runtime"] = runtime; item["memory"] = {"os_max_rss_mib": runtime.get("os_max_rss_mib"), "authoritative_peak_metric": "os_max_rss_mib"}
    if profile == "FULL":
        try:
            evidence = w5._analyze_case(case_dir, input_text=text, meta=meta, runtime_log=runtime_log, runtime_returncode=int(runtime.get("returncode", 1))); fp = _fingerprint(case_dir)
        except Exception as exc:
            evidence = {"hard_pass": False, "analysis_error": f"{type(exc).__name__}: {exc}"}; fp = {}
        item["evidence"] = evidence; item["fingerprint"] = fp
        item["hard_pass"] = runtime.get("returncode") == 0 and isinstance(runtime.get("os_max_rss_mib"), (int, float)) and evidence.get("hard_pass") is True and bool(fp)
    else:
        rows = []
        try:
            rows = _physical_rows(case_dir); fp = _fingerprint(case_dir); sanity = _state_sanity(fp); solver = w5._solver_evidence(runtime_log, returncode=int(runtime.get("returncode", 1))); final_time = s5r._num(rows[-1], "time") if rows else math.nan; steps_ok = len(rows) == int(meta["expected_steps"])
        except Exception as exc:
            fp = {}; sanity = {"pass": False, "error": f"{type(exc).__name__}: {exc}"}; solver = {"healthy": False}; final_time = math.nan; steps_ok = False
        item["fingerprint"] = fp; item["state_sanity"] = sanity; item["solver"] = solver; item["final_time_s"] = final_time; item["measured_physical_rows"] = len(rows)
        item["hard_pass"] = runtime.get("returncode") == 0 and isinstance(runtime.get("os_max_rss_mib"), (int, float)) and solver.get("healthy") is True and sanity.get("pass") is True and steps_ok and math.isclose(final_time, END_TIME_S, rel_tol=0.0, abs_tol=1.0e-18)
    if not item["hard_pass"]: item["reason"] = "R2_PHYSICAL_PROFILE_FAIL"
    return item

def _checkpoint_present(case_dir: Path) -> bool:
    return any(p.is_dir() and p.name.endswith("_cp") for p in case_dir.iterdir())

def _execute_replay(exe: Path, out: Path, lean_dir: Path, full_endpoint: Mapping[str, float], *, timeout: float) -> dict[str, Any]:
    replay_dir = out / "cases" / "diagnostic_replay"
    if replay_dir.exists(): shutil.rmtree(replay_dir)
    shutil.copytree(lean_dir, replay_dir)
    text, meta = build_profile("DIAGNOSTIC_REPLAY"); (replay_dir / "input.i").write_text(text)
    logs = out / "logs"; logs.mkdir(parents=True, exist_ok=True)
    p2 = s5r._p2(exe, replay_dir, logs / "diagnostic_replay_p2.log", timeout=timeout)
    item: dict[str, Any] = {"profile": "DIAGNOSTIC_REPLAY", "meta": meta, "p2": p2, "hard_pass": False}
    if p2.get("returncode") != 0: item["reason"] = "P2_FAIL"; return item
    runtime_log = logs / "diagnostic_replay_runtime.log"
    runtime = _runtime(exe, replay_dir, runtime_log, logs / "diagnostic_replay_time_v.log", timeout=timeout, recover=True)
    item["runtime"] = runtime; item["memory"] = {"os_max_rss_mib": runtime.get("os_max_rss_mib"), "authoritative_peak_metric": "os_max_rss_mib"}
    log_text = runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""; step_markers = re.findall(r"\bTime Step\s+\d+", log_text)
    item["guards"] = {"checkpoint_present": _checkpoint_present(replay_dir), "no_additional_physical_timestep": len(step_markers) == 0, "time_step_markers": step_markers}
    try:
        rows = s5r._read_rows(replay_dir / "input_out.csv"); row = rows[-1]; endpoint = w5._endpoint([row], meta=meta); parity = _compare(full_endpoint, endpoint); state = s5r._state_evidence([row])
    except Exception as exc:
        endpoint = {}; parity = {"pass": False, "error": f"{type(exc).__name__}: {exc}"}; state = {"hard_pass": False}
    item["endpoint"] = endpoint; item["endpoint_vs_full"] = parity; item["state"] = state
    item["hard_pass"] = runtime.get("returncode") == 0 and isinstance(runtime.get("os_max_rss_mib"), (int, float)) and item["guards"]["checkpoint_present"] and item["guards"]["no_additional_physical_timestep"] and parity.get("pass") is True and state.get("hard_pass") is True
    if not item["hard_pass"]: item["reason"] = "DIAGNOSTIC_REPLAY_FAIL"
    return item

def _reduction(full: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    f = full.get("memory", {}).get("os_max_rss_mib"); c = candidate.get("memory", {}).get("os_max_rss_mib")
    if not isinstance(f, (int, float)) or not isinstance(c, (int, float)): return {"status": "UNRESOLVED"}
    red = float(f) - float(c); frac = red / float(f) if float(f) else None; material = red >= c5.MAJOR_ABS_MB or (frac is not None and frac >= c5.MAJOR_REL)
    return {"status": "MEASURED", "full_mib": float(f), "candidate_mib": float(c), "reduction_mib": red, "reduction_fraction": frac, "material": material, "criteria": {"absolute_mib": c5.MAJOR_ABS_MB, "fraction": c5.MAJOR_REL}}

def self_test() -> dict[str, Any]:
    base, meta = _base(); paths = set(c3._postprocessor_paths(base)); passive = {p for p in paths if mp.get_parameter(base, p, "type") in c3.PASSIVE_TYPES}
    lean, lm = build_profile("SCIENCE_LEAN"); monitored, mm = build_profile("SCIENCE_MONITORED"); replay, rm = build_profile("DIAGNOSTIC_REPLAY")
    checks = {"r2_level": mp.get_parameter(base, "Mesh", "uniform_refine") == "2", "five_steps": int(meta["expected_steps"]) == 5, "passive_count": len(passive) == c3.EXPECTED_PASSIVE_COUNT, "lean_keep_subset": LEAN_KEEP <= passive, "monitored_keep_subset": MONITORED_KEEP <= passive, "lean_disabled": lm["profile"]["disabled_passive_count"] == c3.EXPECTED_PASSIVE_COUNT - len(LEAN_KEEP), "monitored_disabled": mm["profile"]["disabled_passive_count"] == c3.EXPECTED_PASSIVE_COUNT - len(MONITORED_KEEP), "replay_all_passive_final": rm["profile"]["disabled_passive_count"] == 0, "lean_checkpoint": mp.get_parameter(lean, "Outputs", "checkpoint") == "true", "replay_checkpoint": mp.get_parameter(replay, "Outputs", "checkpoint") == "true", "replay_output_final": mp.get_parameter(replay, "Outputs", "execute_on") == "FINAL"}
    failed = sorted(k for k, ok in checks.items() if not ok); return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}

def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK): raise Issue224ScienceProfileError(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS": raise Issue224ScienceProfileError(f"P0 failed: {p0}")
    out = args.results_root.resolve(); summary: dict[str, Any] = {"schema_version": 1, "issue": 224, "base_sha": os.environ.get("EXPERIMENT_BASE_SHA") or os.environ.get("GITHUB_SHA"), "physics_opt_sha256": w5._sha256(exe), "qualification": "R2_SCIENCE_PROFILE_TERMINAL", "p0": p0, "cases": {}, "decision": {}}; _write(out, summary)
    full = _execute_physical(exe, out, "full", "FULL", timeout=args.timeout); summary["cases"]["full"] = full; _write(out, summary)
    lean = _execute_physical(exe, out, "science_lean", "SCIENCE_LEAN", timeout=args.timeout); summary["cases"]["science_lean"] = lean; _write(out, summary)
    monitored = _execute_physical(exe, out, "science_monitored", "SCIENCE_MONITORED", timeout=args.timeout); summary["cases"]["science_monitored"] = monitored; _write(out, summary)
    lean_parity = _compare(full["fingerprint"], lean["fingerprint"]) if full.get("hard_pass") and lean.get("hard_pass") else {"pass": False, "reason": "CASE_FAILURE"}
    monitored_parity = _compare(full["fingerprint"], monitored["fingerprint"]) if full.get("hard_pass") and monitored.get("hard_pass") else {"pass": False, "reason": "CASE_FAILURE"}
    replay = _execute_replay(exe, out, out / "cases" / "science_lean", full["evidence"]["endpoint"], timeout=args.timeout) if full.get("hard_pass") and lean.get("hard_pass") else {"profile": "DIAGNOSTIC_REPLAY", "hard_pass": False, "reason": "PREREQUISITE_FAILURE"}
    summary["cases"]["diagnostic_replay"] = replay
    lean_reduction = _reduction(full, lean); monitored_reduction = _reduction(full, monitored)
    promotion = full.get("hard_pass") is True and lean.get("hard_pass") is True and monitored.get("hard_pass") is True and replay.get("hard_pass") is True and lean_parity.get("pass") is True and monitored_parity.get("pass") is True and lean_reduction.get("material") is True
    summary["decision"] = {"full_w5_r2_pass": full.get("hard_pass") is True, "science_lean_r2_pass": lean.get("hard_pass") is True, "science_monitored_r2_pass": monitored.get("hard_pass") is True, "diagnostic_replay_pass": replay.get("hard_pass") is True, "science_lean_fingerprint_parity": lean_parity, "science_monitored_fingerprint_parity": monitored_parity, "science_lean_memory": lean_reduction, "science_monitored_memory": monitored_reduction, "promotion_authorized": promotion, "promoted_profile": "SCIENCE_LEAN" if promotion else None, "monitored_profile_available": bool(monitored.get("hard_pass") is True and monitored_parity.get("pass") is True), "validation_full_remains_canonical": True, "claim_boundary": "Promotion authorizes low-memory science execution by changing passive observer schedules only. It does not relax W5 validation gates; VALIDATION_FULL remains the canonical acceptance/regression surface."}
    summary["status"] = "ISSUE224_SCIENCE_LEAN_PROMOTION_READY" if promotion else "ISSUE224_SCIENCE_PROFILE_HOLD"; _write(out, summary); print((out / "summary.json").read_text()); return 0 if promotion else 1

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--physics-opt", type=Path); parser.add_argument("--results-root", type=Path, default=Path("issue224-science-profile-results")); parser.add_argument("--timeout", type=float, default=7200.0); parser.add_argument("--self-test", action="store_true"); args = parser.parse_args()
    if args.self_test:
        result = self_test(); print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None: parser.error("--physics-opt is required unless --self-test is used")
    return run(args)

if __name__ == "__main__": raise SystemExit(main())
