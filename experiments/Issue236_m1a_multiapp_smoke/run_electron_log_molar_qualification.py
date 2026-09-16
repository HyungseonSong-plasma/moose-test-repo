#!/usr/bin/env python3
"""Issue-236 electron-only log-molar representation counterfactual.

Control: run_electron_sheath_qualification.py (already qualified at dt_e=1e-10).
Counterfactual: replace only the electron-density solved representation

    n_e [1/m^3] = N_A * c_e [mol/m^3]
    c_e = exp(log_e) * (1 mol/m^3)

while retaining the accepted grounded-sheath physics, frozen heavy state,
n_epsilon normalization/transport, Poisson model, SEE model, and 100-step
schedule.  The n_epsilon equation intentionally remains on the legacy
n_ref*epsilon_ref normalization.  A compatibility bridge reconstructs the old
n_e_hat = n_e/n_ref coordinate for mean-energy and energy-wall closures.

This is a representation/positivity counterfactual, not production acceptance.
The transformed time residual is the exact backward-Euler conservative-state
difference.  Drift uses the same face/upwind topology as the accepted particle
drift.  Diffusion uses the continuous identity -D*grad(c_e) =
-D*c_e*grad(log_e) through the FV gradient machinery; therefore this run is not
a claim of discrete algebraic identity with FVDiffusion on n_e_hat.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_electron_sheath_qualification as control
from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_nochem as nochem
from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_pos as pos

base, live, w45 = control.base, control.live, control.w45
DT_E, END_TIME, N_STEPS = control.DT_E, control.END_TIME, control.N_STEPS
AVOGADRO = 6.02214076e23
LOG_VAR = "log_e"
MOLAR_FUNCTOR = "issue236_electron_molar_concentration"
PHYSICAL_FUNCTOR = "n_e_physical"
COMPAT_HAT_FUNCTOR = "issue236_n_e_hat_compat"
SEE_MOLAR_FUNCTOR = "issue236_see_molar_flux"
MOLAR_BRIDGE = "issue236_log_e_molar_bridge"
COMPAT_BRIDGE = "issue236_log_e_compat_bridge"
SEE_MOLAR_BRIDGE = "issue236_log_e_see_molar_bridge"
OUT = control.OUT
FILE_BASE = "issue236_electron_log_molar"

_TIME = "FVKernels/n_e_time"
_DIFF = "FVKernels/n_e_diffusion"
_DRIFT = "FVKernels/n_e_drift"
_LOG_TIME = "FVKernels/issue236_log_e_time"
_LOG_DIFF = "FVKernels/issue236_log_e_diffusion"
_LOG_DRIFT = "FVKernels/issue236_log_e_drift"
_PARTICLE_BC = f"FVBCs/{w45.PARTICLE_BC}"
_ENERGY_BC = f"FVBCs/{w45.ENERGY_BC}"
_SEE_PARTICLE_BC = f"FVBCs/{nochem._SEE_PARTICLE_BC}"
_SEE_ENERGY_BC = f"FVBCs/{nochem._SEE_ENERGY_BC}"
_DENSITY_BRIDGE = "FunctorMaterials/electron_density_physical"


def _finalize(d: dict[str, Any]) -> dict[str, Any]:
    d["failed_checks"] = sorted(k for k, v in d["checks"].items() if not v)
    d["status"] = "PASS" if not d["failed_checks"] else "FAIL"
    return d


def _top_level_float(text: str, name: str) -> float:
    matches = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", text)
    if len(matches) != 1:
        raise base.Issue236Error(f"cannot resolve unique top-level scalar {name}: {len(matches)}")
    value = float(matches[0].strip())
    if not math.isfinite(value) or value <= 0.0:
        raise base.Issue236Error(f"{name} must be finite and positive, got {value}")
    return value


def _one_path_of_type(text: str, section: str, type_name: str) -> str:
    paths = [
        path
        for path in base._children(text, section)
        if base.mp.unquote(base.mp.get_parameter(text, path, "type")) == type_name
    ]
    if len(paths) != 1:
        raise base.Issue236Error(
            f"expected exactly one {type_name} in {section}, found {paths}"
        )
    return paths[0]


def _copy_param(text: str, path: str, name: str, *, required: bool = True) -> str | None:
    value = base.mp.get_parameter(text, path, name)
    if value is None and required:
        raise base.Issue236Error(f"missing required parameter {path}/{name}")
    return value


def _replace_density_variable(text: str, *, n_ref: float) -> str:
    old = "Variables/n_e"
    if not base.mb.has_block(text, old):
        raise base.Issue236Error("control child lacks Variables/n_e")

    block = _copy_param(text, old, "block") or "plasma"
    two_term = _copy_param(text, old, "two_term_boundary_expansion", required=False)
    log_initial = math.log(n_ref / AVOGADRO)

    text = base.mb.remove_block(text, old)
    payload = [
        f"  [{LOG_VAR}]",
        "    type = MooseVariableFVReal",
        f"    initial_condition = {log_initial:.17g}",
        f"    block = {block}",
    ]
    if two_term is not None:
        payload.append(f"    two_term_boundary_expansion = {two_term}")
    payload.append("  []")
    text = base.mb.insert_child_block(text, "Variables", "\n".join(payload))
    return text


def _replace_particle_transport(text: str) -> str:
    for path in (_TIME, _DIFF, _DRIFT):
        if not base.mb.has_block(text, path):
            raise base.Issue236Error(f"control child lacks particle transport owner {path}")

    coeff = _copy_param(text, _DIFF, "coeff")
    coeff_interp = _copy_param(text, _DIFF, "coeff_interp_method", required=False)
    diff_block = _copy_param(text, _DIFF, "block") or "plasma"

    drift_params = {
        name: _copy_param(text, _DRIFT, name)
        for name in (
            "potential",
            "mobility",
            "carrier",
            "charge_number",
            "advected_interp_method",
            "boundaries_to_avoid",
            "block",
        )
    }

    for path in (_TIME, _DIFF, _DRIFT):
        text = base.mb.remove_block(text, path)

    text = base.mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [issue236_log_e_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = {LOG_VAR}
    block = plasma
  []""",
    )

    diffusion_lines = [
        "  [issue236_log_e_diffusion]",
        "    type = PhysicsFVLogMolarElectronDiffusion",
        f"    variable = {LOG_VAR}",
        f"    coeff = {coeff}",
    ]
    if coeff_interp is not None:
        diffusion_lines.append(f"    coeff_interp_method = {coeff_interp}")
    diffusion_lines.extend((f"    block = {diff_block}", "  []"))
    text = base.mb.insert_child_block(text, "FVKernels", "\n".join(diffusion_lines))

    return base.mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [issue236_log_e_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = {LOG_VAR}
    potential = {drift_params['potential']}
    mobility = {drift_params['mobility']}
    carrier = {drift_params['carrier']}
    charge_number = {drift_params['charge_number']}
    advected_interp_method = {drift_params['advected_interp_method']}
    boundaries_to_avoid = {drift_params['boundaries_to_avoid']}
    block = {drift_params['block']}
  []""",
    )


def _replace_density_bridges(text: str, *, n_ref: float) -> str:
    if not base.mb.has_block(text, _DENSITY_BRIDGE):
        raise base.Issue236Error(f"control child lacks {_DENSITY_BRIDGE}")

    text = base.mp.upsert_parameter(text, _DENSITY_BRIDGE, "functor_names", f"'{LOG_VAR}'")
    text = base.mp.upsert_parameter(text, _DENSITY_BRIDGE, "functor_symbols", "'le'")
    text = base.mp.upsert_parameter(
        text,
        _DENSITY_BRIDGE,
        "expression",
        f"'{AVOGADRO:.17g}*exp(le)'",
    )

    for path in (f"FunctorMaterials/{MOLAR_BRIDGE}", f"FunctorMaterials/{COMPAT_BRIDGE}"):
        base.mb.require_absent(text, path)

    text = base.mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{MOLAR_BRIDGE}]
    type = ADParsedFunctorMaterial
    property_name = {MOLAR_FUNCTOR}
    functor_names = '{LOG_VAR}'
    functor_symbols = 'le'
    expression = 'exp(le)'
    block = plasma
  []""",
    )
    return base.mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{COMPAT_BRIDGE}]
    type = ADParsedFunctorMaterial
    property_name = {COMPAT_HAT_FUNCTOR}
    functor_names = '{LOG_VAR}'
    functor_symbols = 'le'
    expression = '{AVOGADRO / n_ref:.17g}*exp(le)'
    block = plasma
  []""",
    )


def _rewire_energy_compatibility(text: str) -> str:
    mean_path = _one_path_of_type(text, "FunctorMaterials", "PhysicsElectronMeanEnergyMaterial")
    text = base.mp.upsert_parameter(text, mean_path, "electron_density", COMPAT_HAT_FUNCTOR)
    if not base.mb.has_block(text, _ENERGY_BC):
        raise base.Issue236Error(f"control child lacks {_ENERGY_BC}")
    return base.mp.upsert_parameter(text, _ENERGY_BC, "electron_density", COMPAT_HAT_FUNCTOR)


def _replace_particle_sheath(text: str) -> str:
    if not base.mb.has_block(text, _PARTICLE_BC):
        raise base.Issue236Error(f"control child lacks {_PARTICLE_BC}")
    boundaries = _copy_param(text, _PARTICLE_BC, "boundary")
    mean_energy = _copy_param(text, _PARTICLE_BC, "mean_electron_energy")
    potential = _copy_param(text, _PARTICLE_BC, "potential")
    text = base.mb.remove_block(text, _PARTICLE_BC)
    return base.mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{w45.PARTICLE_BC}]
    type = PhysicsFVLogMolarElectronGroundedSheathBC
    variable = {LOG_VAR}
    boundary = {boundaries}
    mean_electron_energy = {mean_energy}
    potential = {potential}
  []""",
    )


def _replace_see_particle_flux(text: str, *, n_ref: float) -> str:
    if not base.mb.has_block(text, _SEE_PARTICLE_BC):
        raise base.Issue236Error(f"control child lacks {_SEE_PARTICLE_BC}")
    old_functor = _copy_param(text, _SEE_PARTICLE_BC, "functor")
    base.mb.require_absent(text, f"FunctorMaterials/{SEE_MOLAR_BRIDGE}")
    text = base.mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{SEE_MOLAR_BRIDGE}]
    type = ADParsedFunctorMaterial
    property_name = {SEE_MOLAR_FUNCTOR}
    functor_names = '{old_functor}'
    functor_symbols = 'see_hat'
    expression = '{n_ref / AVOGADRO:.17g}*see_hat'
    block = plasma
  []""",
    )
    text = base.mp.upsert_parameter(text, _SEE_PARTICLE_BC, "variable", LOG_VAR)
    return base.mp.upsert_parameter(text, _SEE_PARTICLE_BC, "functor", SEE_MOLAR_FUNCTOR)


def _remove_density_bound(text: str) -> str:
    ne_bound = f"Bounds/{pos._NE_LOWER_BOUND}"
    eps_bound = f"Bounds/{pos._EPS_LOWER_BOUND}"
    if not base.mb.has_block(text, ne_bound) or not base.mb.has_block(text, eps_bound):
        raise base.Issue236Error("control child does not contain both registered VI lower bounds")
    text = base.mb.remove_block(text, ne_bound)
    return text


def _rewire_observers(text: str) -> str:
    # Preserve control-comparable n_e_hat columns by observing the compatibility bridge.
    for name in ("sheath_ne_avg", "sheath_ne_min", "m1_child_n_e_hat_avg"):
        path = f"Postprocessors/{name}"
        if base.mb.has_block(text, path) and base.mp.get_parameter(text, path, "functor") is not None:
            text = base.mp.upsert_parameter(text, path, "functor", COMPAT_HAT_FUNCTOR)

    # Any remaining generic functor observer directly targeting n_e must follow the bridge.
    for path in base._children(text, "Postprocessors"):
        if base.mp.unquote(base.mp.get_parameter(text, path, "functor")) == "n_e":
            text = base.mp.upsert_parameter(text, path, "functor", COMPAT_HAT_FUNCTOR)

    diagnostics = (
        ("log_e_min", LOG_VAR, "min"),
        ("log_e_max", LOG_VAR, "max"),
        ("molar_min", MOLAR_FUNCTOR, "min"),
        ("molar_max", MOLAR_FUNCTOR, "max"),
        ("physical_ne_min", PHYSICAL_FUNCTOR, "min"),
    )
    for suffix, functor, value_type in diagnostics:
        name = f"issue236_log_molar_{suffix}"
        path = f"Postprocessors/{name}"
        base.mb.require_absent(text, path)
        text = control._pp(
            text,
            name,
            f"""    type = ElementExtremeFunctorValue
    functor = {functor}
    value_type = {value_type}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
    outputs = {OUT}""",
        )

    avg_name = "issue236_log_molar_molar_avg"
    base.mb.require_absent(text, f"Postprocessors/{avg_name}")
    text = control._pp(
        text,
        avg_name,
        f"""    type = ElementAverageFunctorPostprocessor
    functor = {MOLAR_FUNCTOR}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
    outputs = {OUT}""",
    )

    output_path = f"Outputs/{OUT}"
    if not base.mb.has_block(text, output_path):
        raise base.Issue236Error(f"control child lacks {output_path}")
    return base.mp.upsert_parameter(text, output_path, "file_base", FILE_BASE)


def _assert_no_direct_ne_solver_ownership(text: str) -> bool:
    if base.mb.has_block(text, "Variables/n_e"):
        return False
    for section in ("FVKernels", "FVBCs"):
        for path in base._children(text, section):
            if base.mp.unquote(base.mp.get_parameter(text, path, "variable")) == "n_e":
                return False
    return True


def build_input(production: str) -> str:
    text = control.build_input(production)
    n_ref = _top_level_float(text, "n_e_value")
    text = _replace_density_variable(text, n_ref=n_ref)
    text = _replace_particle_transport(text)
    text = _replace_density_bridges(text, n_ref=n_ref)
    text = _rewire_energy_compatibility(text)
    text = _replace_particle_sheath(text)
    text = _replace_see_particle_flux(text, n_ref=n_ref)
    text = _remove_density_bound(text)
    text = _rewire_observers(text)
    text = base.mp.upsert_parameter(text, "Executioner", "scheme", "implicit-euler")
    return live._prune_dead_root_parameters(text)


def audit(text: str) -> dict[str, Any]:
    n_ref = _top_level_float(text, "n_e_value")
    mean_path = _one_path_of_type(text, "FunctorMaterials", "PhysicsElectronMeanEnergyMaterial")
    poisson_path = "FunctorMaterials/r31_charge_density"
    eps_bound = f"Bounds/{pos._EPS_LOWER_BOUND}"
    ne_bound = f"Bounds/{pos._NE_LOWER_BOUND}"

    checks: dict[str, bool] = {
        "log_e_solver_present": base.mb.has_block(text, f"Variables/{LOG_VAR}"),
        "legacy_n_e_solver_absent": not base.mb.has_block(text, "Variables/n_e"),
        "direct_n_e_solver_ownership_absent": _assert_no_direct_ne_solver_ownership(text),
        "log_time_owner": base.mp.unquote(base.mp.get_parameter(text, _LOG_TIME, "type")) == "PhysicsFVLogMolarElectronTimeDerivative",
        "log_diffusion_owner": base.mp.unquote(base.mp.get_parameter(text, _LOG_DIFF, "type")) == "PhysicsFVLogMolarElectronDiffusion",
        "log_drift_owner": base.mp.unquote(base.mp.get_parameter(text, _LOG_DRIFT, "type")) == "PhysicsFVLogMolarElectrostaticDrift",
        "log_transport_targets_log_e": all(base.mp.unquote(base.mp.get_parameter(text, p, "variable")) == LOG_VAR for p in (_LOG_TIME, _LOG_DIFF, _LOG_DRIFT)),
        "accepted_drift_topology_potential": base.mp.unquote(base.mp.get_parameter(text, _LOG_DRIFT, "potential")) == "potential_plasma",
        "accepted_drift_topology_mobility": base.mp.unquote(base.mp.get_parameter(text, _LOG_DRIFT, "mobility")) == "electron_mobility",
        "accepted_drift_charge": math.isclose(float(base.mp.get_parameter(text, _LOG_DRIFT, "charge_number") or "nan"), -1.0, rel_tol=0.0, abs_tol=0.0),
        "physical_density_bridge": base.mp.unquote(base.mp.get_parameter(text, _DENSITY_BRIDGE, "expression")) == f"{AVOGADRO:.17g}*exp(le)",
        "compat_density_bridge": base.mp.unquote(base.mp.get_parameter(text, f"FunctorMaterials/{COMPAT_BRIDGE}", "expression")) == f"{AVOGADRO / n_ref:.17g}*exp(le)",
        "mean_energy_uses_compat_hat": base.mp.unquote(base.mp.get_parameter(text, mean_path, "electron_density")) == COMPAT_HAT_FUNCTOR,
        "energy_sheath_uses_compat_hat": base.mp.unquote(base.mp.get_parameter(text, _ENERGY_BC, "electron_density")) == COMPAT_HAT_FUNCTOR,
        "poisson_uses_physical_ne": base.mb.has_block(text, poisson_path) and base.mp.unquote(base.mp.get_parameter(text, poisson_path, "electron_density")) == PHYSICAL_FUNCTOR,
        "particle_sheath_log_molar_owner": base.mp.unquote(base.mp.get_parameter(text, _PARTICLE_BC, "type")) == "PhysicsFVLogMolarElectronGroundedSheathBC",
        "particle_sheath_targets_log_e": base.mp.unquote(base.mp.get_parameter(text, _PARTICLE_BC, "variable")) == LOG_VAR,
        "particle_sheath_uses_potential": base.mp.unquote(base.mp.get_parameter(text, _PARTICLE_BC, "potential")) == "potential_plasma",
        "energy_sheath_remains_accepted": base.mp.unquote(base.mp.get_parameter(text, _ENERGY_BC, "type")) == "PhysicsFVElectronGroundedSheathEnergyBC",
        "see_particle_targets_log_e": base.mp.unquote(base.mp.get_parameter(text, _SEE_PARTICLE_BC, "variable")) == LOG_VAR,
        "see_particle_molar_bridge": base.mp.unquote(base.mp.get_parameter(text, _SEE_PARTICLE_BC, "functor")) == SEE_MOLAR_FUNCTOR,
        "see_energy_still_targets_nepsilon": base.mp.unquote(base.mp.get_parameter(text, _SEE_ENERGY_BC, "variable")) == "n_epsilon",
        "density_vi_bound_removed": not base.mb.has_block(text, ne_bound),
        "energy_vi_bound_retained": base.mb.has_block(text, eps_bound) and base.mp.unquote(base.mp.get_parameter(text, eps_bound, "bounded_variable")) == "n_epsilon",
        "implicit_euler_required": base.mp.unquote(base.mp.get_parameter(text, "Executioner", "scheme")) == "implicit-euler",
        "abort_on_solve_fail": (base.mp.unquote(base.mp.get_parameter(text, "Executioner", "abort_on_solve_fail")) or "").lower() == "true",
        "standalone_no_multiapp": not base.mb.has_block(text, "MultiApps"),
        "standalone_no_transfers": not base.mb.has_block(text, "Transfers"),
        "registered_100_steps": N_STEPS == round(END_TIME / DT_E),
        "issue217_cpp_suppression_contract": w45._cpp_contract_audit()["status"] == "PASS",
        "issue217_analytic_suppression_contract": w45._analytic_contract_audit()["status"] == "PASS",
    }

    log_initial = float(base.mp.get_parameter(text, f"Variables/{LOG_VAR}", "initial_condition") or "nan")
    compat_initial = (AVOGADRO / n_ref) * math.exp(log_initial)
    checks["initial_compat_hat_is_one"] = math.isclose(compat_initial, 1.0, rel_tol=1e-14, abs_tol=1e-14)
    checks["initial_physical_density_matches_legacy_ref"] = math.isclose(AVOGADRO * math.exp(log_initial), n_ref, rel_tol=1e-14, abs_tol=1e-3)

    return _finalize({
        "checks": checks,
        "n_ref_legacy_m3": n_ref,
        "avogadro_per_mol": AVOGADRO,
        "initial_log_e": log_initial,
        "initial_molar_concentration_mol_m3": math.exp(log_initial),
        "representation": "n_e = N_A*exp(log_e); n_epsilon remains legacy-normalized",
        "discrete_equivalence_scope": {
            "time": "exact backward-Euler conservative-state difference",
            "drift": "same accepted E/mobility/sign/upwind topology; transported state exp(log_e)",
            "diffusion": "continuous chain-rule identity via FV gradient; not asserted discretely identical",
        },
    })


def self_test() -> dict[str, Any]:
    production, _ = base.w5._build_case(dt_s=base.w5.BASELINE_DT_S, uniform_refine=0)
    return audit(build_input(production))


def stage(out: Path) -> tuple[Path, dict[str, Any]]:
    production, production_meta = base.w5._build_case(dt_s=base.w5.BASELINE_DT_S, uniform_refine=0)
    text = build_input(production)
    qualified = audit(text)
    if qualified["status"] != "PASS":
        raise base.Issue236Error(qualified)

    case = out / "case"
    staged = base.stage_case(
        base.SOURCE,
        case,
        input_text=text,
        input_name="input.i",
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", f"{FILE_BASE}*", "*.log", "*.e", "*.exo"),
    )
    base.w5.s5r._copy_runtime_assets(case)
    refs = base.validate_referenced_files(text, case, skip_dynamic=True)
    meta = {
        "issue": 236,
        "parent_issue": 234,
        "claim": "electron-only Avogadro/log-molar representation counterfactual",
        "control": "accepted-sheath standalone 100-step qualification",
        "dt_e_s": DT_E,
        "end_time_s": END_TIME,
        "expected_steps": N_STEPS,
        "heavy_state": "frozen AuxVariables; parent solve absent",
        "chemistry": "volumetric electron chemistry off",
        "see": "retained with particle flux converted to molar units",
        "n_epsilon": "legacy normalization retained through n_e_hat compatibility bridge",
        "intent": "test positivity/normalization representation only; not production acceptance",
        "discrete_equivalence_caveat": (
            "time and drift preserve the declared transformed discrete topology; diffusion uses "
            "-D*exp(log_e)*grad(log_e), which is continuously equivalent to -D*grad(c_e) but "
            "is not claimed algebraically identical to legacy FVDiffusion at finite resolution"
        ),
        "audit": qualified,
        "production_reference": production_meta,
        "staging": staged,
        "references": refs,
    }
    base._write(case / "prepare_evidence.json", meta)
    return case, meta


def analyze(case: Path, rc: int, timed_out: bool) -> dict[str, Any]:
    path = case / f"{FILE_BASE}.csv"
    gates = {
        "runtime_returncode_zero": rc == 0,
        "not_timed_out": not timed_out,
        "csv_present": path.is_file(),
    }
    result: dict[str, Any] = {
        "returncode": rc,
        "timed_out": timed_out,
        "csv": str(path) if path.is_file() else None,
    }
    if not path.is_file():
        result.update(gates=gates, hard_pass=all(gates.values()))
        return result

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    physical = [row for row in rows if float(row["time"]) > 0.0]
    final = physical[-1] if physical else {}
    times = [float(row["time"]) for row in physical]

    gates.update({
        "exact_100_steps": len(physical) == N_STEPS,
        "fixed_dt": len(times) == N_STEPS and all(
            math.isclose(t, i * DT_E, rel_tol=0.0, abs_tol=1e-16)
            for i, t in enumerate(times, 1)
        ),
        "reaches_1e_8": bool(final) and math.isclose(float(final["time"]), END_TIME, rel_tol=0.0, abs_tol=1e-16),
        "no_failed_steps": bool(final) and int(round(float(final["sheath_failed"]))) == 0,
        "molar_density_positive": bool(final) and float(final["issue236_log_molar_molar_min"]) > 0.0,
        "physical_density_positive": bool(final) and float(final["issue236_log_molar_physical_ne_min"]) > 0.0,
        "compat_hat_positive": bool(final) and float(final["sheath_ne_min"]) > 0.0,
        "nepsilon_positive": bool(final) and float(final["sheath_nepsilon_min"]) >= 0.0,
        "grounded_branch_valid": bool(final) and float(final["sheath_phi_min"]) >= -1e-10,
        "log_state_finite": bool(final) and math.isfinite(float(final["issue236_log_molar_log_e_min"])) and math.isfinite(float(final["issue236_log_molar_log_e_max"])),
    })

    observation = {}
    if rows and final:
        initial = rows[0]
        observation = {
            "initial_log_e_min": float(initial["issue236_log_molar_log_e_min"]),
            "final_log_e_min": float(final["issue236_log_molar_log_e_min"]),
            "final_log_e_max": float(final["issue236_log_molar_log_e_max"]),
            "initial_molar_avg_mol_m3": float(initial["issue236_log_molar_molar_avg"]),
            "final_molar_avg_mol_m3": float(final["issue236_log_molar_molar_avg"]),
            "final_compat_n_e_hat_avg": float(final["sheath_ne_avg"]),
            "final_compat_n_e_hat_min": float(final["sheath_ne_min"]),
            "final_mean_energy_eV": float(final["sheath_mean_en_avg"]),
            "final_phi_avg_V": float(final["sheath_phi_avg"]),
            "final_primary_particle_wall_flux_mol_s": float(final["sheath_particle_flux"]),
            "final_primary_energy_wall_flux_legacy_normalized": float(final["sheath_energy_flux"]),
        }

    result.update(
        physical_rows=len(physical),
        final=final,
        observation=observation,
        gates=gates,
        hard_pass=all(gates.values()),
    )
    return result


def run(args: argparse.Namespace) -> int:
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    p0 = self_test()
    base._write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        base._write(out / "summary.json", {"status": "CONSTRUCTION_FAIL", "self_test": p0})
        return 2

    case, meta = stage(out)

    preflight = base.run_physics(
        args.physics_opt.resolve(),
        cwd=case,
        input_name="input.i",
        log_path=out / "check_input.log",
        extra_args=("--check-input",),
        timeout_seconds=min(float(args.timeout), 300.0),
    )
    if preflight.returncode != 0 or preflight.timed_out:
        summary = {
            "status": "CHECK_INPUT_FAIL",
            "meta": meta,
            "check_input": {
                "returncode": preflight.returncode,
                "timed_out": preflight.timed_out,
                "wall_seconds": preflight.wall_seconds,
            },
        }
        base._write(out / "summary.json", summary)
        return 2

    runtime = base.run_physics(
        args.physics_opt.resolve(),
        cwd=case,
        input_name="input.i",
        log_path=out / "runtime.log",
        timeout_seconds=float(args.timeout),
    )
    analysis = analyze(case, runtime.returncode, runtime.timed_out)
    summary = {
        "status": "PASS" if analysis["hard_pass"] else "FAIL",
        "meta": meta,
        "check_input": {
            "returncode": preflight.returncode,
            "timed_out": preflight.timed_out,
            "wall_seconds": preflight.wall_seconds,
        },
        "runtime": {
            "returncode": runtime.returncode,
            "timed_out": runtime.timed_out,
            "wall_seconds": runtime.wall_seconds,
        },
        "analysis": analysis,
    }
    base._write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument(
        "--results-root", type=Path, default=Path("issue236-electron-log-molar-results")
    )
    parser.add_argument("--timeout", type=float, default=1800.0)
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
