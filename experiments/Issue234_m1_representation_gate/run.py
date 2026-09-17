#!/usr/bin/env python3
"""Issue #234 M1 representation gate: T2-derived frozen-heavy MultiApp construction.

This gate deliberately proves construction only:

* parent: no-solve state carrier for one heavy interval;
* child: sole nonlinear owner of log_e, c_epsilon, and potential_plasma;
* heavy state: frozen auxiliary mirrors copied parent -> child;
* fast state: copied child -> parent at synchronization;
* scalar wall-energy ledger: integrated in the child over subcycles and copied
  back to a parent Receiver.

It does not advance the heavy equations and does not qualify timestep promotion.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any, Iterable

from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue243_t1_log_molar_coupled_particle import run as t1
from experiments.Issue245_t2_molar_electron_energy import run as t2
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.input import MooseInput
from physics_harness.execution.cases import stage_case, validate_referenced_files
from physics_harness.execution.runtime import run_physics

ROOT = Path(__file__).resolve().parents[2]
SOURCE = w45.SOURCE

DT_H_S = 1.0e-8
DT_E_CONSTRUCTION_S = 1.0e-10

FAST_SOLVER_VARIABLES = (t1.LOG_E, t2.C_EPSILON, "potential_plasma")
LEGACY_FAST_SOLVER_VARIABLES = ("n_e", "n_epsilon")
HEAVY_TRANSFER_VARIABLES = (
    "p",
    "w_O2s",
    "w_O2p",
    "w_O",
    "w_Om",
    "w_Op",
    "w_Os",
)
FLOW_VARIABLES = ("u", "v")
HEAVY_STATE_VARIABLES = (*FLOW_VARIABLES, *HEAVY_TRANSFER_VARIABLES)
EXPECTED_VARIABLES = set((*HEAVY_STATE_VARIABLES, *FAST_SOLVER_VARIABLES))

PARENT_FAST_PPS = {
    "m1_parent_log_e_avg": t1.LOG_E,
    "m1_parent_c_epsilon_avg": t2.C_EPSILON,
    "m1_parent_phi_avg": "potential_plasma",
}
CHILD_FAST_PPS = {
    "m1_child_log_e_avg": t1.LOG_E,
    "m1_child_c_epsilon_avg": t2.C_EPSILON,
    "m1_child_phi_avg": "potential_plasma",
}

CHILD_ENERGY_POWER_PP = w45.ENERGY_POWER_PP
CHILD_ENERGY_LEDGER_PP = "m1_child_primary_energy_integral_J"
PARENT_ENERGY_LEDGER_PP = "m1_parent_primary_energy_integral_J"


class Issue234M1Error(RuntimeError):
    pass


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _children(text: str, parent: str) -> list[str]:
    return mp.direct_children(text, parent) if mb.has_block(text, parent) else []


def _name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _ensure_top_block(text: str, name: str) -> str:
    if mb.has_block(text, name):
        return text
    return mb.append_top_level_block(text, f"[{name}]\n[]")


def _remove_top_if_present(text: str, name: str) -> str:
    return mb.remove_block(text, name) if mb.has_block(text, name) else text


def _aux_block_from_variable(text: str, name: str) -> str:
    path = f"Variables/{name}"
    if not mb.has_block(text, path):
        raise Issue234M1Error(f"missing solver variable required by split: {path}")
    lines = [f"  [{name}]", "    type = MooseVariableFVReal"]
    initial = mp.get_parameter(text, path, "initial_condition")
    block = mp.get_parameter(text, path, "block")
    if initial is not None:
        lines.append(f"    initial_condition = {initial}")
    if block is not None:
        lines.append(f"    block = {block}")
    lines.append("  []")
    return "\n".join(lines)


def _move_variables_to_aux(text: str, names: Iterable[str]) -> str:
    names = tuple(names)
    payloads = [_aux_block_from_variable(text, name) for name in names]
    text = _ensure_top_block(text, "AuxVariables")
    for name in names:
        text = mb.remove_block(text, f"Variables/{name}")
    for payload in payloads:
        text = mb.insert_child_block(text, "AuxVariables", payload)
    return text


def _remove_solver_variables(text: str, names: Iterable[str]) -> str:
    for name in names:
        path = f"Variables/{name}"
        if mb.has_block(text, path):
            text = mb.remove_block(text, path)
    return text


def _insert_fast_pp(text: str, name: str, functor: str) -> str:
    text = _ensure_top_block(text, "Postprocessors")
    if mb.has_block(text, f"Postprocessors/{name}"):
        raise Issue234M1Error(f"duplicate M1 postprocessor: {name}")
    return mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{name}]
    type = ElementAverageFunctorPostprocessor
    functor = {functor}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )


def _remove_equations_owned_by(
    text: str, owners: set[str]
) -> tuple[str, set[str]]:
    removed_bc_names: set[str] = set()
    for section in ("FVKernels", "FVBCs"):
        for path in list(_children(text, section)):
            variable = mp.unquote(mp.get_parameter(text, path, "variable"))
            if variable in owners:
                if section == "FVBCs":
                    removed_bc_names.add(_name(path))
                text = mb.remove_block(text, path)
    return text, removed_bc_names


def _remove_postprocessors_for_missing_bcs(text: str, removed_bcs: set[str]) -> str:
    removed_pp: set[str] = set()
    changed = True
    while changed:
        changed = False
        for path in list(_children(text, "Postprocessors")):
            if not mb.has_block(text, path):
                continue
            fvbcs = set(mp.words(mp.get_parameter(text, path, "fvbcs") or ""))
            value = mp.unquote(mp.get_parameter(text, path, "value"))
            if (fvbcs & removed_bcs) or (value in removed_pp):
                removed_pp.add(_name(path))
                text = mb.remove_block(text, path)
                changed = True
    return text


def _prune_child_flow_ownership(text: str) -> str:
    if mb.has_block(text, "UserObjects/rc"):
        text = mb.remove_block(text, "UserObjects/rc")
    for name in ("rhie_chow_user_object", "advected_interp_method", "velocity_interp_method"):
        if mb.has_block(text, "GlobalParams"):
            text = mp.remove_parameter(text, "GlobalParams", name)
    for path in (
        "FunctorMaterials/transient_state_dot_aliases",
        "FunctorMaterials/mean_molar_mass_dot",
        "FunctorMaterials/mixture_density_dot",
    ):
        if mb.has_block(text, path):
            text = mb.remove_block(text, path)
    return text


def _set_outputs(text: str, *, file_base: str) -> str:
    text = _ensure_top_block(text, "Outputs")
    text = mp.upsert_parameter(text, "Outputs", "file_base", file_base)
    text = mp.upsert_parameter(text, "Outputs", "csv", "true")
    text = mp.upsert_parameter(text, "Outputs", "exodus", "false")
    return text


def _insert_child_energy_ledger(text: str) -> str:
    text = _ensure_top_block(text, "Postprocessors")
    if not mb.has_block(text, f"Postprocessors/{CHILD_ENERGY_POWER_PP}"):
        raise Issue234M1Error(
            f"T2 child missing primary energy power postprocessor {CHILD_ENERGY_POWER_PP}"
        )
    mb.require_absent(text, f"Postprocessors/{CHILD_ENERGY_LEDGER_PP}")
    return mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{CHILD_ENERGY_LEDGER_PP}]
    type = TimeIntegratedPostprocessor
    value = {CHILD_ENERGY_POWER_PP}
    time_integration_scheme = trapezoidal-rule
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )


def _insert_parent_energy_receiver(text: str) -> str:
    text = _ensure_top_block(text, "Postprocessors")
    mb.require_absent(text, f"Postprocessors/{PARENT_ENERGY_LEDGER_PP}")
    return mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{PARENT_ENERGY_LEDGER_PP}]
    type = Receiver
    default = 0
    execute_on = 'INITIAL TIMESTEP_END TRANSFER'
  []""",
    )


def build_parent_input(production_text: str) -> str:
    variable_names = {_name(path) for path in _children(production_text, "Variables")}
    if variable_names != EXPECTED_VARIABLES:
        raise Issue234M1Error(
            f"unexpected T2 variable set: {sorted(variable_names)}; "
            f"expected {sorted(EXPECTED_VARIABLES)}"
        )

    # M1 construction parent is intentionally not a heavy solve. It is a
    # frozen state carrier for exactly one parent interval.
    text = _move_variables_to_aux(production_text, tuple(sorted(EXPECTED_VARIABLES)))
    for section in (
        "FVKernels",
        "FVBCs",
        "Kernels",
        "BCs",
        "ScalarKernels",
        "AuxKernels",
        "FunctorMaterials",
        "Materials",
        "UserObjects",
        "Preconditioning",
        "Postprocessors",
        "VectorPostprocessors",
    ):
        text = _remove_top_if_present(text, section)

    text = mp.upsert_parameter(text, "Problem", "solve", "false")
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{DT_H_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{DT_H_S:.17g}")
    text = _set_outputs(text, file_base="input_out")

    for name, functor in PARENT_FAST_PPS.items():
        text = _insert_fast_pp(text, name, functor)
    text = _insert_parent_energy_receiver(text)

    text = _ensure_top_block(text, "MultiApps")
    mb.require_absent(text, "MultiApps/electron")
    text = mb.insert_child_block(
        text,
        "MultiApps",
        """  [electron]
    type = TransientMultiApp
    input_files = 'electron_sub.i'
    execute_on = TIMESTEP_BEGIN
    sub_cycling = true
    output_sub_cycles = true
    print_sub_cycles = false
  []""",
    )

    text = _ensure_top_block(text, "Transfers")
    for path in (
        "Transfers/heavy_to_electron",
        "Transfers/fast_from_electron",
        "Transfers/energy_ledger_from_electron",
    ):
        mb.require_absent(text, path)

    heavy_words = " ".join(HEAVY_TRANSFER_VARIABLES)
    fast_words = " ".join(FAST_SOLVER_VARIABLES)
    text = mb.insert_child_block(
        text,
        "Transfers",
        f"""  [heavy_to_electron]
    type = MultiAppCopyTransfer
    to_multi_app = electron
    source_variable = '{heavy_words}'
    variable = '{heavy_words}'
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Transfers",
        f"""  [fast_from_electron]
    type = MultiAppCopyTransfer
    from_multi_app = electron
    source_variable = '{fast_words}'
    variable = '{fast_words}'
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Transfers",
        f"""  [energy_ledger_from_electron]
    type = MultiAppPostprocessorTransfer
    from_multi_app = electron
    from_postprocessor = {CHILD_ENERGY_LEDGER_PP}
    to_postprocessor = {PARENT_ENERGY_LEDGER_PP}
    reduction_type = average
  []""",
    )
    return text


def build_child_input(production_text: str, *, dt_e: float) -> str:
    if not math.isfinite(dt_e) or dt_e <= 0.0 or dt_e > DT_H_S:
        raise Issue234M1Error(f"invalid child timestep {dt_e}")
    ratio = DT_H_S / dt_e
    if not math.isclose(ratio, round(ratio), rel_tol=0.0, abs_tol=1.0e-9):
        raise Issue234M1Error(f"parent/child timestep ratio must be integer, got {ratio}")

    variable_names = {_name(path) for path in _children(production_text, "Variables")}
    if variable_names != EXPECTED_VARIABLES:
        raise Issue234M1Error(
            f"unexpected T2 variable set: {sorted(variable_names)}; "
            f"expected {sorted(EXPECTED_VARIABLES)}"
        )

    # Child owns only the canonical T2 fast nonlinear subsystem.
    text = _move_variables_to_aux(production_text, HEAVY_TRANSFER_VARIABLES)
    text = _remove_solver_variables(text, FLOW_VARIABLES)
    text, removed_bcs = _remove_equations_owned_by(text, set(HEAVY_STATE_VARIABLES))
    text = _remove_postprocessors_for_missing_bcs(text, removed_bcs)
    text = _prune_child_flow_ownership(text)

    text = mp.upsert_parameter(text, "Executioner", "dt", f"{dt_e:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{DT_H_S:.17g}")
    text = _set_outputs(text, file_base="electron_sub")

    for name, functor in CHILD_FAST_PPS.items():
        text = _insert_fast_pp(text, name, functor)
    text = _insert_child_energy_ledger(text)
    return text


def _owned_variables(text: str, section: str) -> list[str]:
    result: list[str] = []
    for path in _children(text, section):
        variable = mp.unquote(mp.get_parameter(text, path, "variable"))
        if variable:
            result.append(variable)
    return result


def _audit_parent(text: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    solve = (mp.unquote(mp.get_parameter(text, "Problem", "solve")) or "true").lower()
    checks["parent_no_solve"] = solve == "false"
    checks["parent_dt"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "dt") or "nan"), DT_H_S
    )
    checks["parent_end_time"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "end_time") or "nan"), DT_H_S
    )

    checks["parent_no_nonlinear_variables"] = len(_children(text, "Variables")) == 0
    for name in EXPECTED_VARIABLES:
        checks[f"parent_aux:{name}"] = mb.has_block(text, f"AuxVariables/{name}")
    for name in LEGACY_FAST_SOLVER_VARIABLES:
        checks[f"legacy_fast_absent:{name}"] = (
            not mb.has_block(text, f"Variables/{name}")
            and not mb.has_block(text, f"AuxVariables/{name}")
        )

    checks["parent_no_fv_equations"] = (
        len(_children(text, "FVKernels")) == 0
        and len(_children(text, "FVBCs")) == 0
    )
    checks["multiapp_type"] = (
        mp.get_parameter(text, "MultiApps/electron", "type") == "TransientMultiApp"
    )
    checks["multiapp_at_timestep_begin"] = (
        mp.unquote(mp.get_parameter(text, "MultiApps/electron", "execute_on"))
        == "TIMESTEP_BEGIN"
    )
    checks["subcycling"] = (
        (mp.unquote(mp.get_parameter(text, "MultiApps/electron", "sub_cycling")) or "").lower()
        == "true"
    )
    checks["child_file"] = (
        mp.unquote(mp.get_parameter(text, "MultiApps/electron", "input_files"))
        == "electron_sub.i"
    )

    checks["heavy_transfer_direction"] = (
        mp.get_parameter(text, "Transfers/heavy_to_electron", "to_multi_app") == "electron"
    )
    checks["heavy_transfer_source"] = tuple(
        mp.words(mp.get_parameter(text, "Transfers/heavy_to_electron", "source_variable") or "")
    ) == HEAVY_TRANSFER_VARIABLES
    checks["heavy_transfer_target"] = tuple(
        mp.words(mp.get_parameter(text, "Transfers/heavy_to_electron", "variable") or "")
    ) == HEAVY_TRANSFER_VARIABLES

    checks["fast_transfer_direction"] = (
        mp.get_parameter(text, "Transfers/fast_from_electron", "from_multi_app") == "electron"
    )
    checks["fast_transfer_source"] = tuple(
        mp.words(mp.get_parameter(text, "Transfers/fast_from_electron", "source_variable") or "")
    ) == FAST_SOLVER_VARIABLES
    checks["fast_transfer_target"] = tuple(
        mp.words(mp.get_parameter(text, "Transfers/fast_from_electron", "variable") or "")
    ) == FAST_SOLVER_VARIABLES

    checks["ledger_receiver_present"] = mb.has_block(
        text, f"Postprocessors/{PARENT_ENERGY_LEDGER_PP}"
    )
    checks["ledger_transfer_type"] = (
        mp.get_parameter(text, "Transfers/energy_ledger_from_electron", "type")
        == "MultiAppPostprocessorTransfer"
    )
    checks["ledger_transfer_direction"] = (
        mp.get_parameter(text, "Transfers/energy_ledger_from_electron", "from_multi_app")
        == "electron"
    )
    checks["ledger_source_integrated"] = (
        mp.get_parameter(
            text, "Transfers/energy_ledger_from_electron", "from_postprocessor"
        )
        == CHILD_ENERGY_LEDGER_PP
    )
    checks["ledger_target_receiver"] = (
        mp.get_parameter(text, "Transfers/energy_ledger_from_electron", "to_postprocessor")
        == PARENT_ENERGY_LEDGER_PP
    )

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _audit_child(text: str, *, dt_e: float) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    variable_names = {_name(path) for path in _children(text, "Variables")}
    checks["fast_solver_set_exact"] = variable_names == set(FAST_SOLVER_VARIABLES)
    for name in FAST_SOLVER_VARIABLES:
        checks[f"fast_solver:{name}"] = mb.has_block(text, f"Variables/{name}")
        checks[f"fast_not_aux:{name}"] = not mb.has_block(text, f"AuxVariables/{name}")
    for name in HEAVY_TRANSFER_VARIABLES:
        checks[f"heavy_aux:{name}"] = mb.has_block(text, f"AuxVariables/{name}")
        checks[f"heavy_not_solver:{name}"] = not mb.has_block(text, f"Variables/{name}")
    for name in FLOW_VARIABLES:
        checks[f"flow_absent:{name}"] = (
            not mb.has_block(text, f"Variables/{name}")
            and not mb.has_block(text, f"AuxVariables/{name}")
        )
    for name in LEGACY_FAST_SOLVER_VARIABLES:
        checks[f"legacy_solver_absent:{name}"] = not mb.has_block(text, f"Variables/{name}")

    kernel_vars = _owned_variables(text, "FVKernels")
    bc_vars = _owned_variables(text, "FVBCs")
    checks["all_kernel_owners_fast"] = bool(kernel_vars) and all(
        v in FAST_SOLVER_VARIABLES for v in kernel_vars
    )
    checks["all_bc_owners_fast"] = all(v in FAST_SOLVER_VARIABLES for v in bc_vars)
    checks["poisson_kernel_present"] = (
        mb.has_block(text, "FVKernels/r31_phi_diffusion")
        and mb.has_block(text, "FVKernels/r31_phi_charge_source")
    )
    checks["particle_time_log_molar"] = (
        mp.get_parameter(text, "FVKernels/n_e_time", "variable") == t1.LOG_E
    )
    checks["energy_time_molar"] = (
        mp.get_parameter(text, "FVKernels/s5r_n_epsilon_time", "variable") == t2.C_EPSILON
    )
    checks["child_dt"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "dt") or "nan"), dt_e
    )
    checks["child_end_time"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "end_time") or "nan"), DT_H_S
    )
    checks["energy_ledger_present"] = mb.has_block(
        text, f"Postprocessors/{CHILD_ENERGY_LEDGER_PP}"
    )
    checks["energy_ledger_is_time_integral"] = (
        mp.get_parameter(text, f"Postprocessors/{CHILD_ENERGY_LEDGER_PP}", "type")
        == "TimeIntegratedPostprocessor"
    )
    checks["energy_ledger_source_power"] = (
        mp.get_parameter(text, f"Postprocessors/{CHILD_ENERGY_LEDGER_PP}", "value")
        == CHILD_ENERGY_POWER_PP
    )

    # This is the strongest representation-preservation gate: after removing
    # heavy ownership, the exact T2 fast residual/wall/SEE contracts still pass.
    t2_audit = t2.audit_t2_input(text)
    checks["t2_fast_contract_preserved"] = t2_audit["status"] == "PASS"

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "kernel_variables": kernel_vars,
        "bc_variables": bc_vars,
        "t2_audit": t2_audit,
    }


def build_split(*, dt_e: float = DT_E_CONSTRUCTION_S) -> tuple[str, str, dict[str, Any]]:
    production_text, production_meta = t2.build_t2_input()
    production_audit = t2.audit_t2_input(production_text)
    if production_audit["status"] != "PASS":
        raise Issue234M1Error(
            f"T2 source-of-truth audit failed: {production_audit['failed_checks']}"
        )

    parent = build_parent_input(production_text)
    child = build_child_input(production_text, dt_e=dt_e)
    parent_audit = _audit_parent(parent)
    child_audit = _audit_child(child, dt_e=dt_e)

    meta = {
        "issue": 234,
        "phase": "M1 representation migration / construction gate",
        "claim": "t2_derived_no_solve_parent_plus_subcycled_fast_child_with_integrated_scalar_ledger",
        "dt_h_s": DT_H_S,
        "dt_e_s": dt_e,
        "subcycles_expected": int(round(DT_H_S / dt_e)),
        "fast_solver_variables": list(FAST_SOLVER_VARIABLES),
        "heavy_transfer_variables": list(HEAVY_TRANSFER_VARIABLES),
        "production_reference": production_meta,
        "production_audit": production_audit,
        "parent_audit": parent_audit,
        "child_audit": child_audit,
        "construction_limits": {
            "heavy_solve_performed": False,
            "spatial_source_average_qualified": False,
            "timestep_promoted": False,
            "scientific_m1_convergence_claim": False,
        },
    }
    if parent_audit["status"] != "PASS" or child_audit["status"] != "PASS":
        raise Issue234M1Error(meta)
    return parent, child, meta


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    detail: dict[str, Any] = {}
    try:
        parent, child, meta = build_split(dt_e=DT_E_CONSTRUCTION_S)
    except Issue234M1Error as error:
        payload = error.args[0] if error.args else str(error)
        return {
            "status": "FAIL",
            "checks": {"split_builds": False},
            "failed_checks": ["split_builds"],
            "detail": {"split_error": payload},
        }

    checks["split_builds"] = True
    checks["parent_audit"] = meta["parent_audit"]["status"] == "PASS"
    checks["child_audit"] = meta["child_audit"]["status"] == "PASS"
    checks["construction_subcycles"] = meta["subcycles_expected"] == 100
    checks["parent_hit_parse"] = bool(MooseInput(parent).blocks)
    checks["child_hit_parse"] = bool(MooseInput(child).blocks)

    # Representation mutation: old normalized particle ownership in the fast
    # return transfer must be rejected.
    mutated_parent = mp.upsert_parameter(
        parent,
        "Transfers/fast_from_electron",
        "source_variable",
        "'n_e c_epsilon potential_plasma'",
    )
    parent_mutation_audit = _audit_parent(mutated_parent)
    checks["reject_legacy_fast_transfer"] = (
        parent_mutation_audit["status"] == "FAIL"
        and "fast_transfer_source" in parent_mutation_audit["failed_checks"]
    )

    # Temporal mutation: child must synchronize exactly to the heavy interval.
    mutated_child = mp.upsert_parameter(
        child, "Executioner", "end_time", f"{0.5 * DT_H_S:.17g}"
    )
    child_temporal_audit = _audit_child(mutated_child, dt_e=DT_E_CONSTRUCTION_S)
    checks["reject_wrong_child_sync_time"] = (
        child_temporal_audit["status"] == "FAIL"
        and "child_end_time" in child_temporal_audit["failed_checks"]
    )

    # Ledger mutation: endpoint power is not an acceptable substitute for the
    # interval-integrated scalar construction ledger.
    mutated_parent = mp.upsert_parameter(
        parent,
        "Transfers/energy_ledger_from_electron",
        "from_postprocessor",
        CHILD_ENERGY_POWER_PP,
    )
    ledger_mutation_audit = _audit_parent(mutated_parent)
    checks["reject_endpoint_power_transfer"] = (
        ledger_mutation_audit["status"] == "FAIL"
        and "ledger_source_integrated" in ledger_mutation_audit["failed_checks"]
    )

    try:
        production = t2.build_t2_input()[0]
        build_child_input(production, dt_e=3.0e-11)
    except Issue234M1Error:
        checks["reject_noninteger_subcycle_ratio"] = True
    else:
        checks["reject_noninteger_subcycle_ratio"] = False

    detail["parent_mutation_failed_checks"] = parent_mutation_audit["failed_checks"]
    detail["temporal_mutation_failed_checks"] = child_temporal_audit["failed_checks"]
    detail["ledger_mutation_failed_checks"] = ledger_mutation_audit["failed_checks"]

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "detail": detail,
    }


def _stage(out: Path, *, dt_e: float) -> tuple[Path, dict[str, Any]]:
    parent, child, meta = build_split(dt_e=dt_e)
    case_dir = out / "case"
    stage = stage_case(
        SOURCE,
        case_dir,
        input_text=parent,
        input_name="input.i",
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=(
            "input_out*",
            "electron_sub*",
            "*.log",
            "*.e",
            "*.exo",
            "prepare_evidence.json",
        ),
    )
    (case_dir / "electron_sub.i").write_text(child, encoding="utf-8")
    w45.s5r._copy_runtime_assets(case_dir)
    meta["staging"] = stage
    meta["parent_references"] = validate_referenced_files(parent, case_dir, skip_dynamic=True)
    meta["child_references"] = validate_referenced_files(child, case_dir, skip_dynamic=True)
    _write(case_dir / "prepare_evidence.json", meta)
    return case_dir, meta


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _num(row: dict[str, str], key: str) -> float:
    return float(row[key])


def _find_child_csv(case_dir: Path) -> Path | None:
    candidates = sorted(
        p for p in case_dir.rglob("*.csv") if "electron_sub" in p.name and p.is_file()
    )
    return max(candidates, key=lambda p: p.stat().st_size) if candidates else None


def _runtime_analysis(
    case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool
) -> dict[str, Any]:
    expected_subcycles = int(round(DT_H_S / dt_e))
    parent_csv = case_dir / "input_out.csv"
    child_csv = _find_child_csv(case_dir)
    result: dict[str, Any] = {
        "returncode": returncode,
        "timed_out": timed_out,
        "parent_csv": str(parent_csv) if parent_csv.is_file() else None,
        "child_csv": str(child_csv) if child_csv else None,
        "expected_subcycles": expected_subcycles,
    }
    gates = {
        "runtime_returncode_zero": returncode == 0,
        "not_timed_out": not timed_out,
        "parent_csv_present": parent_csv.is_file(),
        "child_csv_present": child_csv is not None,
    }
    if not all((parent_csv.is_file(), child_csv is not None)):
        result["gates"] = gates
        result["hard_pass"] = all(gates.values())
        return result

    parent_rows = _read_csv(parent_csv)
    child_rows = _read_csv(child_csv)
    parent_physical = [row for row in parent_rows if _num(row, "time") > 0.0]
    child_physical = [row for row in child_rows if _num(row, "time") > 0.0]
    parent_final = parent_physical[-1] if parent_physical else {}
    child_final = child_physical[-1] if child_physical else {}

    gates.update(
        {
            "one_parent_step": len(parent_physical) == 1,
            "child_subcycle_count": len(child_physical) == expected_subcycles,
            "parent_sync_time": bool(parent_final)
            and math.isclose(_num(parent_final, "time"), DT_H_S, rel_tol=0.0, abs_tol=1.0e-18),
            "child_sync_time": bool(child_final)
            and math.isclose(_num(child_final, "time"), DT_H_S, rel_tol=0.0, abs_tol=1.0e-18),
        }
    )

    mirror_pairs = (
        ("m1_parent_log_e_avg", "m1_child_log_e_avg"),
        ("m1_parent_c_epsilon_avg", "m1_child_c_epsilon_avg"),
        ("m1_parent_phi_avg", "m1_child_phi_avg"),
    )
    mirror: dict[str, Any] = {}
    for parent_key, child_key in mirror_pairs:
        if parent_key not in parent_final or child_key not in child_final:
            gates[f"mirror_column:{parent_key}"] = False
            continue
        parent_value = _num(parent_final, parent_key)
        child_value = _num(child_final, child_key)
        scale = max(abs(parent_value), abs(child_value), 1.0e-300)
        relative_difference = abs(parent_value - child_value) / scale
        mirror[parent_key] = {
            "parent": parent_value,
            "child": child_value,
            "relative_difference": relative_difference,
        }
        gates[f"mirror:{parent_key}"] = relative_difference <= 1.0e-10

    ledger: dict[str, Any] = {}
    if (
        PARENT_ENERGY_LEDGER_PP in parent_final
        and CHILD_ENERGY_LEDGER_PP in child_final
    ):
        parent_value = _num(parent_final, PARENT_ENERGY_LEDGER_PP)
        child_value = _num(child_final, CHILD_ENERGY_LEDGER_PP)
        scale = max(abs(parent_value), abs(child_value), 1.0e-300)
        relative_difference = abs(parent_value - child_value) / scale
        ledger = {
            "parent_J": parent_value,
            "child_J": child_value,
            "relative_difference": relative_difference,
        }
        gates["integrated_energy_ledger_transfer"] = (
            math.isfinite(parent_value)
            and math.isfinite(child_value)
            and relative_difference <= 1.0e-12
        )
    else:
        gates["integrated_energy_ledger_columns_present"] = False

    result.update(
        {
            "parent_physical_rows": len(parent_physical),
            "child_physical_rows": len(child_physical),
            "parent_final_time_s": _num(parent_final, "time") if parent_final else None,
            "child_final_time_s": _num(child_final, "time") if child_final else None,
            "mirror": mirror,
            "integrated_energy_ledger": ledger,
            "gates": gates,
            "hard_pass": all(gates.values()),
        }
    )
    return result


def prepare(args: argparse.Namespace) -> int:
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    p0 = self_test()
    _write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        _write(out / "summary.json", {"status": "CONSTRUCTION_FAIL", "self_test": p0})
        return 2
    case_dir, meta = _stage(out, dt_e=args.dt_e)
    _write(
        out / "summary.json",
        {
            "status": "PREPARED",
            "meta": meta,
            "case_dir": str(case_dir),
        },
    )
    return 0


def run(args: argparse.Namespace) -> int:
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    p0 = self_test()
    _write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        _write(out / "summary.json", {"status": "CONSTRUCTION_FAIL", "self_test": p0})
        return 2

    case_dir, meta = _stage(out, dt_e=args.dt_e)
    runtime = run_physics(
        args.physics_opt.resolve(),
        cwd=case_dir,
        input_name="input.i",
        log_path=out / "runtime.log",
        timeout_seconds=float(args.timeout),
    )
    analysis = _runtime_analysis(
        case_dir,
        dt_e=args.dt_e,
        returncode=runtime.returncode,
        timed_out=runtime.timed_out,
    )
    summary = {
        "status": "PASS" if analysis.get("hard_pass") else "FAIL",
        "meta": meta,
        "runtime": {
            "returncode": runtime.returncode,
            "wall_seconds": runtime.wall_seconds,
            "timed_out": runtime.timed_out,
        },
        "analysis": analysis,
    }
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("issue234-m1-representation-gate-results"),
    )
    parser.add_argument("--dt-e", type=float, default=DT_E_CONSTRUCTION_S)
    parser.add_argument("--timeout", type=float, default=1800.0)
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.prepare_only:
        return prepare(args)
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test or --prepare-only")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
