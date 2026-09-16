#!/usr/bin/env python3
"""Standalone Issue-236 electron/energy/Poisson qualification with Issue-217 sheath owners."""
from __future__ import annotations

import argparse, csv, json, math, shutil
from pathlib import Path

from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_nochem as nochem

base, live = nochem.base, nochem.live
DT_E, END_TIME, N_STEPS = 1.0e-10, 1.0e-8, 100
OUT, FILE_BASE = "issue236_electron_sheath_csv", "issue236_electron_sheath"
live.TOTAL_TIME_S, live.HEAVY_STEPS = END_TIME, 1
live.HEAVY_DT_S, live.ELECTRON_DT_S = END_TIME, DT_E
live.ELECTRON_STEPS_PER_HEAVY = N_STEPS
base.DT_H_S, base.DT_E_SMOKE_S = END_TIME, DT_E
_prior_child, _prior_audit = base.build_child_input, base._audit_child


def _finalize(d):
    d["failed_checks"] = sorted(k for k, v in d["checks"].items() if not v)
    d["status"] = "PASS" if not d["failed_checks"] else "FAIL"
    return d


def _pp(text, name, body):
    text = base._ensure_top_block(text, "Postprocessors")
    return base.mb.insert_child_block(text, "Postprocessors", f"  [{name}]\n{body}\n  []")


def _restore_sheath(text):
    for name in (live.PARTICLE_MATERIAL, live.ENERGY_MATERIAL):
        path = f"FunctorMaterials/{name}"
        if not base.mb.has_block(text, path):
            raise base.Issue236Error(f"missing temporary thermal material: {path}")
        text = base.mb.remove_block(text, path)
    for name in (w45.PARTICLE_BC, w45.ENERGY_BC):
        path = f"FVBCs/{name}"
        if not base.mb.has_block(text, path):
            raise base.Issue236Error(f"missing temporary wall BC: {path}")
        text = base.mb.remove_block(text, path)
    walls = "'" + " ".join(w45.WALLS) + "'"
    text = base.mb.insert_child_block(text, "FVBCs", f"""  [{w45.PARTICLE_BC}]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_e
    boundary = {walls}
    mean_electron_energy = mean_en_solved
    potential = potential_plasma
  []""")
    return base.mb.insert_child_block(text, "FVBCs", f"""  [{w45.ENERGY_BC}]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = n_epsilon
    boundary = {walls}
    electron_density = n_e
    mean_electron_energy = mean_en_solved
    potential = potential_plasma
    energy_reference_eV = {w45.ENERGY_REFERENCE_EV:.17g}
  []""")


def _instrument(text):
    walls = "'" + " ".join(w45.WALLS) + "'"
    for key, functor in (("ne", "n_e"), ("nepsilon", "n_epsilon"), ("phi", "potential_plasma"), ("mean_en", "mean_en_solved")):
        text = _pp(text, f"sheath_{key}_avg", f"""    type = ElementAverageFunctorPostprocessor
    functor = {functor}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
    outputs = {OUT}""")
        text = _pp(text, f"sheath_{key}_min", f"""    type = ElementExtremeFunctorValue
    functor = {functor}
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
    outputs = {OUT}""")
    for key, bc in (("particle_flux", w45.PARTICLE_BC), ("energy_flux", w45.ENERGY_BC)):
        text = _pp(text, f"sheath_{key}", f"""    type = SideFVFluxBCIntegral
    boundary = {walls}
    fvbcs = '{bc}'
    execute_on = 'INITIAL TIMESTEP_END'
    outputs = {OUT}""")
    for key, typ in (("step", "NumTimeSteps"), ("failed", "NumFailedTimeSteps"), ("dt", "TimestepSize")):
        text = _pp(text, f"sheath_{key}", f"""    type = {typ}
    execute_on = 'INITIAL TIMESTEP_END'
    outputs = {OUT}""")
    text = base._ensure_top_block(text, "Outputs")
    return base.mb.insert_child_block(text, "Outputs", f"""  [{OUT}]
    type = CSV
    file_base = {FILE_BASE}
    execute_on = 'INITIAL TIMESTEP_END'
    new_row_detection_columns = all
    precision = 17
  []""")


def build_input(production):
    text = _prior_child(production, dt_e=DT_E)
    text = _restore_sheath(text)
    text = base.mp.upsert_parameter(text, "Executioner", "dt", f"{DT_E:.17g}")
    text = base.mp.upsert_parameter(text, "Executioner", "end_time", f"{END_TIME:.17g}")
    text = base.mp.upsert_parameter(text, "Executioner", "abort_on_solve_fail", "true")
    return live._prune_dead_root_parameters(_instrument(text))


def audit(text):
    d = _prior_audit(text, dt_e=DT_E)
    c = d["checks"]
    for k in ("electron_particle_surface_loss_active", "electron_energy_surface_loss_active", "surface_loss_materials_present"):
        c.pop(k, None)
    p, e = f"FVBCs/{w45.PARTICLE_BC}", f"FVBCs/{w45.ENERGY_BC}"
    c.update({
        "accepted_particle_owner": base.mp.unquote(base.mp.get_parameter(text, p, "type")) == "PhysicsFVElectronGroundedSheathCollectionBC",
        "accepted_energy_owner": base.mp.unquote(base.mp.get_parameter(text, e, "type")) == "PhysicsFVElectronGroundedSheathEnergyBC",
        "temporary_thermal_materials_absent": all(not base.mb.has_block(text, f"FunctorMaterials/{x}") for x in (live.PARTICLE_MATERIAL, live.ENERGY_MATERIAL)),
        "accepted_particle_uses_potential": base.mp.unquote(base.mp.get_parameter(text, p, "potential")) == "potential_plasma",
        "accepted_energy_uses_potential": base.mp.unquote(base.mp.get_parameter(text, e, "potential")) == "potential_plasma",
        "abort_on_solve_fail": (base.mp.unquote(base.mp.get_parameter(text, "Executioner", "abort_on_solve_fail")) or "").lower() == "true",
        "standalone_no_multiapp": not base.mb.has_block(text, "MultiApps"),
        "standalone_no_transfers": not base.mb.has_block(text, "Transfers"),
        "fast_variables_exact": {base._name(x) for x in base._children(text, "Variables")} == set(base.FAST_SOLVER_VARIABLES),
        "issue217_cpp_suppression_contract": w45._cpp_contract_audit()["status"] == "PASS",
        "issue217_analytic_suppression_contract": w45._analytic_contract_audit()["status"] == "PASS",
    })
    return _finalize(d)


def self_test():
    prod, _ = base.w5._build_case(dt_s=base.w5.BASELINE_DT_S, uniform_refine=0)
    d = audit(build_input(prod))
    d["checks"]["registered_100_steps"] = N_STEPS == round(END_TIME / DT_E)
    return _finalize(d)


def stage(out):
    prod, meta0 = base.w5._build_case(dt_s=base.w5.BASELINE_DT_S, uniform_refine=0)
    text, d = build_input(prod), None
    d = audit(text)
    if d["status"] != "PASS":
        raise base.Issue236Error(d)
    case = out / "case"
    staged = base.stage_case(base.SOURCE, case, input_text=text, input_name="input.i", purge_directory_names=(".jitcache", "checkpoint", "checkpoints"), purge_patterns=("input_out*", f"{FILE_BASE}*", "*.log", "*.e", "*.exo"))
    base.w5.s5r._copy_runtime_assets(case)
    refs = base.validate_referenced_files(text, case, skip_dynamic=True)
    meta = {"issue": 236, "parent_issue": 234, "claim": "one standalone 1e-8 electron interval with Issue-217 accepted sheath", "dt_e_s": DT_E, "expected_steps": N_STEPS, "heavy_state": "frozen AuxVariables; parent solve absent", "chemistry": "volumetric electron chemistry off", "see": "retained", "audit": d, "production_reference": meta0, "staging": staged, "references": refs}
    base._write(case / "prepare_evidence.json", meta)
    return case, meta


def analyze(case, rc, timed_out):
    path = case / f"{FILE_BASE}.csv"
    gates = {"runtime_returncode_zero": rc == 0, "not_timed_out": not timed_out, "csv_present": path.is_file()}
    result = {"returncode": rc, "timed_out": timed_out, "csv": str(path) if path.is_file() else None}
    if not path.is_file():
        result.update(gates=gates, hard_pass=all(gates.values())); return result
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    physical = [r for r in rows if float(r["time"]) > 0]
    final = physical[-1] if physical else {}
    times = [float(r["time"]) for r in physical]
    gates.update({
        "exact_100_steps": len(physical) == N_STEPS,
        "fixed_dt": len(times) == N_STEPS and all(math.isclose(t, i * DT_E, rel_tol=0, abs_tol=1e-16) for i, t in enumerate(times, 1)),
        "reaches_1e_8": bool(final) and math.isclose(float(final["time"]), END_TIME, rel_tol=0, abs_tol=1e-16),
        "no_failed_steps": bool(final) and int(round(float(final["sheath_failed"]))) == 0,
        "ne_positive": bool(final) and float(final["sheath_ne_min"]) >= 0,
        "nepsilon_positive": bool(final) and float(final["sheath_nepsilon_min"]) >= 0,
        "grounded_branch_valid": bool(final) and float(final["sheath_phi_min"]) >= -1e-10,
    })
    obs = {}
    if rows and final:
        r0 = rows[0]
        p0, p1 = float(r0["sheath_particle_flux"]), float(final["sheath_particle_flux"])
        q0, q1 = float(r0["sheath_energy_flux"]), float(final["sheath_energy_flux"])
        phi0, phi1 = float(r0["sheath_phi_avg"]), float(final["sheath_phi_avg"])
        n0, n1 = float(r0["sheath_ne_avg"]), float(final["sheath_ne_avg"])
        te0 = max((2/3)*float(r0["sheath_mean_en_avg"]), 1e-300); te1 = max((2/3)*float(final["sheath_mean_en_avg"]), 1e-300)
        proxy0 = p0 / max(n0 * math.sqrt(te0), 1e-300); proxy1 = p1 / max(n1 * math.sqrt(te1), 1e-300)
        obs = {"particle_flux_initial": p0, "particle_flux_final": p1, "particle_flux_ratio": p1/p0 if p0 else None, "energy_flux_ratio": q1/q0 if q0 else None, "phi_avg_initial_V": phi0, "phi_avg_final_V": phi1, "bulk_normalized_flux_proxy_ratio": proxy1/proxy0 if proxy0 else None, "directionally_consistent_with_suppression": phi1 > phi0 and p1 < p0 and proxy1 < proxy0, "note": "Exact exp(-DeltaPhi/Te) ownership is a structural/analytic gate; runtime proxy is observational because it uses bulk averages."}
    result.update(physical_rows=len(physical), final=final, suppression_observation=obs, gates=gates, hard_pass=all(gates.values()))
    return result


def run(args):
    out = args.results_root.resolve()
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    p0 = self_test(); base._write(out / "self_test.json", p0)
    if p0["status"] != "PASS": base._write(out / "summary.json", {"status": "CONSTRUCTION_FAIL", "self_test": p0}); return 2
    case, meta = stage(out)
    r = base.run_physics(args.physics_opt.resolve(), cwd=case, input_name="input.i", log_path=out / "runtime.log", timeout_seconds=args.timeout)
    a = analyze(case, r.returncode, r.timed_out)
    s = {"status": "PASS" if a["hard_pass"] else "FAIL", "meta": meta, "runtime": {"returncode": r.returncode, "wall_seconds": r.wall_seconds, "timed_out": r.timed_out}, "analysis": a}
    base._write(out / "summary.json", s); return 0 if s["status"] == "PASS" else 1


def main():
    p = argparse.ArgumentParser(); p.add_argument("--self-test", action="store_true"); p.add_argument("--physics-opt", type=Path); p.add_argument("--results-root", type=Path, default=Path("issue236-electron-sheath-results")); p.add_argument("--timeout", type=float, default=1800.0); a = p.parse_args()
    if a.self_test:
        d = self_test(); print(json.dumps(d, indent=2, sort_keys=True)); return 0 if d["status"] == "PASS" else 1
    if a.physics_opt is None: p.error("--physics-opt is required unless --self-test")
    return run(a)

if __name__ == "__main__": raise SystemExit(main())
