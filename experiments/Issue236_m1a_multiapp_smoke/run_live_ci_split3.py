#!/usr/bin/env python3
"""Issue-236 three-stage multirate discriminator.

Per heavy interval the coupling order is intentionally:

1. freeze the heavy state and electrostatic potential;
2. subcycle only n_e and n_epsilon with dt_e = 1e-9 s;
3. copy the relaxed electron state to the parent and solve the heavy system once
   with dt_h = 1e-7 s while the electric field remains frozen;
4. solve Poisson once using the updated heavy state and relaxed electron density;
5. copy the updated potential back to the parent for the next interval.

The electron child therefore owns only n_e and n_epsilon.  potential_plasma is
an auxiliary mirror there.  The heavy parent owns only the heavy nonlinear
system; n_e, n_epsilon, and potential_plasma are auxiliary mirrors.  A second
Poisson child owns only potential_plasma and executes at TIMESTEP_END.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_pos as pos

live = pos.live
base = pos.base

_ELECTRON_SOLVER_VARIABLES = ("n_e", "n_epsilon")
_POTENTIAL = "potential_plasma"
_POISSON_APP = "poisson"
_POISSON_INPUT = "poisson_sub.i"
_POISSON_FILE_BASE = "poisson_sub"
_POISSON_PHI_PP = "m1_poisson_phi_avg"
_POISSON_MIRROR_VARIABLES = (*base.HEAVY_SOLVER_VARIABLES, *_ELECTRON_SOLVER_VARIABLES)

_pos_build_parent_input = base.build_parent_input
_pos_build_child_input = base.build_child_input
_pos_audit_parent = base._audit_parent
_pos_audit_child = base._audit_child
_pos_runtime_analysis = base._runtime_analysis


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["failed_checks"] = sorted(
        key for key, ok in result["checks"].items() if not ok
    )
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _build_parent_input(production_text: str) -> str:
    text = _pos_build_parent_input(production_text)

    # Electron child runs first.  Only n_e and n_epsilon return from it; the
    # potential is deliberately frozen until the end-of-step Poisson solve.
    fast_words = " ".join(_ELECTRON_SOLVER_VARIABLES)
    text = base.mp.upsert_parameter(
        text, "Transfers/fast_from_electron", "source_variable", f"'{fast_words}'"
    )
    text = base.mp.upsert_parameter(
        text, "Transfers/fast_from_electron", "variable", f"'{fast_words}'"
    )

    if base.mb.has_block(text, "Transfers/potential_to_electron"):
        raise base.Issue236Error("duplicate potential_to_electron transfer")
    text = base.mb.insert_child_block(
        text,
        "Transfers",
        f"""  [potential_to_electron]
    type = MultiAppCopyTransfer
    to_multi_app = electron
    source_variable = {_POTENTIAL}
    variable = {_POTENTIAL}
  []""",
    )

    if base.mb.has_block(text, f"MultiApps/{_POISSON_APP}"):
        raise base.Issue236Error("duplicate Poisson MultiApp")
    text = base.mb.insert_child_block(
        text,
        "MultiApps",
        f"""  [{_POISSON_APP}]
    type = TransientMultiApp
    input_files = '{_POISSON_INPUT}'
    execute_on = TIMESTEP_END
    sub_cycling = false
    output_sub_cycles = true
    print_sub_cycles = false
  []""",
    )

    state_words = " ".join(_POISSON_MIRROR_VARIABLES)
    for name in ("state_to_poisson", "phi_from_poisson"):
        if base.mb.has_block(text, f"Transfers/{name}"):
            raise base.Issue236Error(f"duplicate transfer: {name}")

    text = base.mb.insert_child_block(
        text,
        "Transfers",
        f"""  [state_to_poisson]
    type = MultiAppCopyTransfer
    to_multi_app = {_POISSON_APP}
    source_variable = '{state_words}'
    variable = '{state_words}'
  []""",
    )
    text = base.mb.insert_child_block(
        text,
        "Transfers",
        f"""  [phi_from_poisson]
    type = MultiAppCopyTransfer
    from_multi_app = {_POISSON_APP}
    source_variable = {_POTENTIAL}
    variable = {_POTENTIAL}
  []""",
    )
    return text


def _build_electron_input(production_text: str, *, dt_e: float) -> str:
    text = _pos_build_child_input(production_text, dt_e=dt_e)

    # potential_plasma is a transferred, frozen field during all electron
    # subcycles.  Remove its Poisson equation and boundary ownership here.
    text = base._move_variables_to_aux(text, (_POTENTIAL,))
    text, removed_bcs = base._remove_equations_owned_by(text, {_POTENTIAL})
    text = base._remove_postprocessors_for_missing_bcs(text, removed_bcs)
    return text


def _build_poisson_input(production_text: str) -> str:
    # Keep only potential_plasma as a solver variable.  All heavy/electron
    # states are transferred mirrors so the elliptic charge solve sees the
    # just-completed heavy state and the relaxed electron density.
    text = base._move_variables_to_aux(production_text, _POISSON_MIRROR_VARIABLES)
    text, _removed_bcs = base._remove_equations_owned_by(
        text, set(_POISSON_MIRROR_VARIABLES)
    )
    text = base._prune_child_flow_ownership(text)

    text = base._remove_top_if_present(text, "Postprocessors")
    text = base._remove_top_if_present(text, "VectorPostprocessors")
    text = base._insert_fast_pp(text, _POISSON_PHI_PP, _POTENTIAL)

    text = base.mp.upsert_parameter(
        text, "Executioner", "dt", f"{live.HEAVY_DT_S:.17g}"
    )
    text = base.mp.upsert_parameter(
        text, "Executioner", "end_time", f"{live.TOTAL_TIME_S:.17g}"
    )
    text = base.mp.upsert_parameter(text, "Executioner", "solve_type", "NEWTON")

    if base.mb.has_block(text, "Outputs"):
        text = base.mp.upsert_parameter(text, "Outputs", "file_base", _POISSON_FILE_BASE)
        text = base.mp.upsert_parameter(text, "Outputs", "csv", "true")
        text = base.mp.upsert_parameter(text, "Outputs", "exodus", "true")
        text = base.mp.upsert_parameter(
            text, "Outputs", "execute_on", "'INITIAL TIMESTEP_END FINAL'"
        )
    return text


def _audit_parent(text: str) -> dict[str, Any]:
    result = _pos_audit_parent(text)
    # The inherited two-stage audit expects potential_plasma to return from the
    # electron child.  In the three-stage contract it returns only from Poisson.
    for obsolete in ("fast_transfer_source", "fast_transfer_target"):
        result["checks"].pop(obsolete, None)

    result["checks"].update(
        {
            "electron_runs_at_timestep_begin": (
                base.mp.unquote(
                    base.mp.get_parameter(text, "MultiApps/electron", "execute_on")
                )
                == "TIMESTEP_BEGIN"
            ),
            "poisson_runs_at_timestep_end": (
                base.mb.has_block(text, f"MultiApps/{_POISSON_APP}")
                and base.mp.unquote(
                    base.mp.get_parameter(
                        text, f"MultiApps/{_POISSON_APP}", "execute_on"
                    )
                )
                == "TIMESTEP_END"
            ),
            "parent_potential_is_aux": (
                base.mb.has_block(text, f"AuxVariables/{_POTENTIAL}")
                and not base.mb.has_block(text, f"Variables/{_POTENTIAL}")
            ),
            "parent_has_no_poisson_equation": (
                not base.mb.has_block(text, "FVKernels/r31_phi_diffusion")
                and not base.mb.has_block(text, "FVKernels/r31_phi_charge_source")
            ),
            "electron_returns_density_and_energy_only": tuple(
                base.mp.words(
                    base.mp.get_parameter(
                        text, "Transfers/fast_from_electron", "source_variable"
                    )
                )
            )
            == _ELECTRON_SOLVER_VARIABLES,
            "potential_transferred_to_electron": (
                base.mp.get_parameter(
                    text, "Transfers/potential_to_electron", "to_multi_app"
                )
                == "electron"
                and tuple(
                    base.mp.words(
                        base.mp.get_parameter(
                            text, "Transfers/potential_to_electron", "source_variable"
                        )
                    )
                )
                == (_POTENTIAL,)
            ),
            "state_transferred_to_poisson": (
                base.mp.get_parameter(
                    text, "Transfers/state_to_poisson", "to_multi_app"
                )
                == _POISSON_APP
                and tuple(
                    base.mp.words(
                        base.mp.get_parameter(
                            text, "Transfers/state_to_poisson", "source_variable"
                        )
                    )
                )
                == _POISSON_MIRROR_VARIABLES
            ),
            "potential_returns_from_poisson": (
                base.mp.get_parameter(
                    text, "Transfers/phi_from_poisson", "from_multi_app"
                )
                == _POISSON_APP
                and tuple(
                    base.mp.words(
                        base.mp.get_parameter(
                            text, "Transfers/phi_from_poisson", "source_variable"
                        )
                    )
                )
                == (_POTENTIAL,)
            ),
        }
    )
    return _finalize(result)


def _audit_electron(text: str, *, dt_e: float) -> dict[str, Any]:
    result = _pos_audit_child(text, dt_e=dt_e)
    for obsolete in (
        "fast_solver:potential_plasma",
        "fast_not_aux:potential_plasma",
        "poisson_kernel_present",
    ):
        result["checks"].pop(obsolete, None)

    kernel_vars = base._owned_variables(text, "FVKernels")
    bc_vars = base._owned_variables(text, "FVBCs")
    result["checks"].update(
        {
            "electron_solver_variables_only": all(
                base.mb.has_block(text, f"Variables/{name}")
                for name in _ELECTRON_SOLVER_VARIABLES
            )
            and set(kernel_vars).issubset(set(_ELECTRON_SOLVER_VARIABLES))
            and set(bc_vars).issubset(set(_ELECTRON_SOLVER_VARIABLES)),
            "electron_potential_is_aux": (
                base.mb.has_block(text, f"AuxVariables/{_POTENTIAL}")
                and not base.mb.has_block(text, f"Variables/{_POTENTIAL}")
            ),
            "electron_has_no_poisson_equation": (
                not base.mb.has_block(text, "FVKernels/r31_phi_diffusion")
                and not base.mb.has_block(text, "FVKernels/r31_phi_charge_source")
            ),
        }
    )
    return _finalize(result)


def _audit_poisson(text: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    checks["potential_is_only_solver_variable"] = (
        base.mb.has_block(text, f"Variables/{_POTENTIAL}")
        and all(
            not base.mb.has_block(text, f"Variables/{name}")
            for name in _POISSON_MIRROR_VARIABLES
        )
    )
    checks["all_state_is_aux"] = all(
        base.mb.has_block(text, f"AuxVariables/{name}")
        for name in _POISSON_MIRROR_VARIABLES
    )
    checks["poisson_equation_present"] = (
        base.mb.has_block(text, "FVKernels/r31_phi_diffusion")
        and base.mb.has_block(text, "FVKernels/r31_phi_charge_source")
    )
    kernel_vars = base._owned_variables(text, "FVKernels")
    bc_vars = base._owned_variables(text, "FVBCs")
    checks["poisson_owns_all_equations"] = bool(kernel_vars) and all(
        name == _POTENTIAL for name in kernel_vars
    ) and all(name == _POTENTIAL for name in bc_vars)
    checks["poisson_dt_matches_heavy"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "dt") or "nan"),
        live.HEAVY_DT_S,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    checks["poisson_end_time"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        live.TOTAL_TIME_S,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    checks["poisson_phi_postprocessor"] = base.mb.has_block(
        text, f"Postprocessors/{_POISSON_PHI_PP}"
    )
    return _finalize({"checks": checks})


def _build_three_way_split(*, dt_e: float = live.ELECTRON_DT_S):
    if not math.isfinite(dt_e) or dt_e <= 0.0:
        raise base.Issue236Error(f"invalid electron timestep {dt_e}")
    ratio = live.HEAVY_DT_S / dt_e
    if not math.isclose(ratio, round(ratio), rel_tol=0.0, abs_tol=1.0e-9):
        raise base.Issue236Error(
            f"heavy/electron timestep ratio must be integer, got {ratio}"
        )

    production_text, production_meta = base.w5._build_case(
        dt_s=base.w5.BASELINE_DT_S, uniform_refine=0
    )
    parent = _build_parent_input(production_text)
    electron = _build_electron_input(production_text, dt_e=dt_e)
    poisson = _build_poisson_input(production_text)

    parent_audit = _audit_parent(parent)
    electron_audit = _audit_electron(electron, dt_e=dt_e)
    poisson_audit = _audit_poisson(poisson)
    meta = {
        "issue": 236,
        "parent_issue": 234,
        "claim": "electron_subcycle_then_heavy_then_poisson",
        "operator_split": (
            "freeze heavy+potential -> electron density/energy subcycles -> "
            "heavy solve with frozen potential -> Poisson solve -> potential update"
        ),
        "coupling_order": ["electron", "heavy", "poisson"],
        "field_policy": "frozen during electron and heavy stages; updated by Poisson at TIMESTEP_END",
        "electron_model": "solved n_e + solved n_epsilon; potential_plasma transferred auxiliary",
        "electron_surface_loss": (
            "COMSOL-style thermal particle and energy wall losses; ion-induced SEE retained"
        ),
        "total_time_s": live.TOTAL_TIME_S,
        "heavy_steps": live.HEAVY_STEPS,
        "dt_h_s": live.HEAVY_DT_S,
        "dt_e_s": dt_e,
        "subcycles_per_heavy": int(round(live.HEAVY_DT_S / dt_e)),
        "subcycles_expected": int(round(live.TOTAL_TIME_S / dt_e)),
        "production_reference": production_meta,
        "parent_audit": parent_audit,
        "electron_audit": electron_audit,
        "poisson_audit": poisson_audit,
    }
    if any(
        audit["status"] != "PASS"
        for audit in (parent_audit, electron_audit, poisson_audit)
    ):
        raise base.Issue236Error(meta)
    return parent, electron, poisson, meta


def _build_split(*, dt_e: float = live.ELECTRON_DT_S):
    parent, electron, _poisson, meta = _build_three_way_split(dt_e=dt_e)
    return parent, electron, meta


def _stage(out: Path, *, dt_e: float):
    parent, electron, poisson, meta = _build_three_way_split(dt_e=dt_e)
    case_dir = out / "case"
    staged = base.stage_case(
        base.SOURCE,
        case_dir,
        input_text=parent,
        input_name="input.i",
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=(
            "input_out*",
            "electron_sub*",
            "poisson_sub*",
            "*.log",
            "*.e",
            "*.exo",
            "prepare_evidence.json",
        ),
    )
    (case_dir / "electron_sub.i").write_text(electron, encoding="utf-8")
    (case_dir / _POISSON_INPUT).write_text(poisson, encoding="utf-8")
    base.w5.s5r._copy_runtime_assets(case_dir)

    meta["staging"] = staged
    meta["parent_references"] = base.validate_referenced_files(
        parent, case_dir, skip_dynamic=True
    )
    meta["electron_references"] = base.validate_referenced_files(
        electron, case_dir, skip_dynamic=True
    )
    meta["poisson_references"] = base.validate_referenced_files(
        poisson, case_dir, skip_dynamic=True
    )
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return case_dir, meta


def _find_poisson_csv(case_dir: Path) -> Path | None:
    candidates = sorted(
        path
        for path in case_dir.rglob("*.csv")
        if _POISSON_FILE_BASE in path.name and path.is_file()
    )
    return max(candidates, key=lambda path: path.stat().st_size) if candidates else None


def _runtime_analysis(
    case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool
) -> dict[str, Any]:
    result = _pos_runtime_analysis(
        case_dir, dt_e=dt_e, returncode=returncode, timed_out=timed_out
    )
    gates = result.setdefault("gates", {})

    # In the old two-stage contract parent phi was compared with the electron
    # child.  Here that child intentionally holds the pre-Poisson frozen field.
    gates.pop("mirror:m1_parent_phi_avg", None)
    gates.pop("mirror_column:m1_parent_phi_avg", None)
    if isinstance(result.get("mirror"), dict):
        result["mirror"].pop("m1_parent_phi_avg", None)

    poisson_csv = _find_poisson_csv(case_dir)
    result["poisson_csv"] = str(poisson_csv) if poisson_csv else None
    gates["poisson_csv_present"] = poisson_csv is not None

    parent_csv = case_dir / "input_out.csv"
    if poisson_csv is not None and parent_csv.is_file():
        parent_rows = live._unique_rows_by_time(base._read_csv(parent_csv))
        poisson_rows = live._unique_rows_by_time(base._read_csv(poisson_csv))
        result["poisson_physical_rows"] = len(poisson_rows)
        gates["poisson_step_count"] = len(poisson_rows) == live.HEAVY_STEPS
        gates["poisson_final_time"] = bool(poisson_rows) and math.isclose(
            float(poisson_rows[-1]["time"]),
            live.TOTAL_TIME_S,
            rel_tol=0.0,
            abs_tol=1e-14,
        )

        if (
            parent_rows
            and poisson_rows
            and "m1_parent_phi_avg" in parent_rows[-1]
            and _POISSON_PHI_PP in poisson_rows[-1]
        ):
            pv = float(parent_rows[-1]["m1_parent_phi_avg"])
            qv = float(poisson_rows[-1][_POISSON_PHI_PP])
            scale = max(abs(pv), abs(qv), 1e-300)
            rel = abs(pv - qv) / scale
            result["poisson_phi_mirror"] = {
                "parent": pv,
                "poisson": qv,
                "relative_difference": rel,
            }
            gates["poisson_phi_returns_to_parent"] = rel <= 1e-10
        else:
            gates["poisson_phi_returns_to_parent"] = False

    result["hard_pass"] = all(gates.values())
    return result


def _self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    try:
        parent, electron, poisson, meta = _build_three_way_split(
            dt_e=live.ELECTRON_DT_S
        )
        checks["split_builds"] = True
        checks["parent_audit"] = meta["parent_audit"]["status"] == "PASS"
        checks["electron_audit"] = meta["electron_audit"]["status"] == "PASS"
        checks["poisson_audit"] = meta["poisson_audit"]["status"] == "PASS"
        checks["coupling_order"] = meta["coupling_order"] == [
            "electron",
            "heavy",
            "poisson",
        ]
        checks["heavy_dt_1e_7"] = math.isclose(
            meta["dt_h_s"], 1.0e-7, rel_tol=0.0, abs_tol=0.0
        )
        checks["electron_dt_1e_9"] = math.isclose(
            meta["dt_e_s"], 1.0e-9, rel_tol=0.0, abs_tol=0.0
        )
        checks["hundred_electron_steps_per_heavy"] = (
            meta["subcycles_per_heavy"] == 100
        )
        checks["thousand_total_electron_steps"] = (
            meta["subcycles_expected"] == 1000
        )
        checks["ten_heavy_and_poisson_steps"] = meta["heavy_steps"] == 10
        checks["final_time_1e_6"] = math.isclose(
            meta["total_time_s"], 1.0e-6, rel_tol=0.0, abs_tol=0.0
        )
        checks["electron_surface_particle_loss"] = base.mb.has_block(
            electron, "FVBCs/s5r_electron_grounded_sheath"
        )
        checks["electron_surface_energy_loss"] = base.mb.has_block(
            electron, "FVBCs/s5r_electron_energy_grounded_sheath"
        )
        checks["electron_vi_positivity"] = all(
            pos._positivity_checks(electron).values()
        )
        checks["electron_field_frozen"] = (
            base.mb.has_block(electron, f"AuxVariables/{_POTENTIAL}")
            and not base.mb.has_block(electron, f"Variables/{_POTENTIAL}")
        )
        checks["heavy_field_frozen"] = (
            base.mb.has_block(parent, f"AuxVariables/{_POTENTIAL}")
            and not base.mb.has_block(parent, f"Variables/{_POTENTIAL}")
        )
        checks["poisson_updates_field"] = (
            base.mb.has_block(poisson, f"Variables/{_POTENTIAL}")
            and base.mb.has_block(poisson, "FVKernels/r31_phi_diffusion")
            and base.mb.has_block(poisson, "FVKernels/r31_phi_charge_source")
        )

        try:
            _build_three_way_split(dt_e=3.0e-9)
        except base.Issue236Error:
            checks["reject_noninteger_subcycle_ratio"] = True
        else:
            checks["reject_noninteger_subcycle_ratio"] = False
    except base.Issue236Error as error:
        detail = error.args[0] if error.args else str(error)
        return {
            "status": "FAIL",
            "checks": {"split_builds": False},
            "failed_checks": ["split_builds"],
            "detail": {"split_error": detail},
        }

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }


base.build_parent_input = _build_parent_input
base.build_child_input = _build_electron_input
base._audit_parent = _audit_parent
base._audit_child = _audit_electron
base.build_split = _build_split
base._stage = _stage
base._runtime_analysis = _runtime_analysis
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
