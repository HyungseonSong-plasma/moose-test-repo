#!/usr/bin/env python3
"""Issue-236 boundary-face discriminator for transferred electron-density mirrors.

This wrapper extends ``run_live_ci_transfer_diag.py`` without changing the
multirate schedule, chemistry state, transfer payload, or the live solved
``n_e`` representation.  Three modes isolate where MOOSE FV boundary
reconstruction enters the frozen heavy-transport coupling:

* ``two_term``: parent ``n_e`` and child ``n_e_heavy_frozen`` both use two-term
  boundary extrapolation;
* ``one_term``: only the parent transferred ``n_e`` mirror uses one-term
  boundary evaluation (Run #34 control);
* ``mirrors_one_term``: both transferred/frozen mirrors use one-term boundary
  evaluation while live solved child ``n_e`` remains two-term.

The parent diagnostic snapshot always remains two-term.  Side extrema are taken
on the complete plasma boundary so the discriminator observes the same external
FaceArg representation used by boundary heavy-transport/SEE consumers.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_transfer_diag as diag

base = diag.base
live = diag.live

_diag_build_parent_input = base.build_parent_input
_diag_build_child_input = base.build_child_input
_diag_audit_parent = base._audit_parent
_diag_audit_child = base._audit_child
_diag_self_test = base.self_test
_diag_runtime_analysis = base._runtime_analysis

_MODE_ENV = "ISSUE236_NE_BOUNDARY_MODE"
_MODE = os.environ.get(_MODE_ENV, "two_term").strip().lower()
_ALLOWED_MODES = {"two_term", "one_term", "mirrors_one_term"}
if _MODE not in _ALLOWED_MODES:
    raise RuntimeError(f"{_MODE_ENV} must be one of {sorted(_ALLOWED_MODES)}, got {_MODE!r}")

_BOUNDARY = "r31_plasma_all_boundary"
_PARENT_NE = "AuxVariables/n_e"
_SNAPSHOT_NE = "AuxVariables/issue236_diag_snap_ne"
_CHILD_LIVE_NE = "Variables/n_e"
_CHILD_FROZEN_NE = "AuxVariables/n_e_heavy_frozen"
_CHILD_FROZEN_NE_PHYSICAL = "n_e_heavy_frozen_physical"

_PARENT_FACE_FIELDS = {
    "ne_face": "n_e",
    "ne_snap_face": "issue236_diag_snap_ne",
}
_CHILD_FACE_FIELDS = {
    "live_ne_face": "n_e",
    "frozen_ne_face": "n_e_heavy_frozen",
}
_NEGATIVE_NE_SIGNATURE = "requires electron_number_density >= 0"
_WALLS = {
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
}


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["failed_checks"] = sorted(key for key, ok in result["checks"].items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _insert_side_extreme_pp(
    text: str, *, lane: str, field_key: str, variable: str, value_type: str
) -> str:
    spec = diag._LANES[lane]
    name = f"issue236_diag_{lane}_{field_key}_{value_type}"
    return diag._insert_pp(
        text,
        name,
        f"""  [{name}]
    type = SideExtremeValue
    variable = {variable}
    boundary = {_BOUNDARY}
    value_type = {value_type}
    execute_on = '{spec['pp_execute_on']}'
    outputs = {spec['output']}
  []""",
    )


def _instrument_face_fields(text: str, *, lane: str, fields: dict[str, str]) -> str:
    for field_key, variable in fields.items():
        for value_type in ("min", "max"):
            text = _insert_side_extreme_pp(
                text,
                lane=lane,
                field_key=field_key,
                variable=variable,
                value_type=value_type,
            )
    return text


def _expected_parent_two_term() -> str:
    return "true" if _MODE == "two_term" else "false"


def _expected_child_frozen_two_term() -> str:
    return "false" if _MODE == "mirrors_one_term" else "true"


def _set_parent_boundary_mode(text: str) -> str:
    if not base.mb.has_block(text, _PARENT_NE):
        raise base.Issue236Error(f"parent lacks transferred electron mirror: {_PARENT_NE}")
    if not base.mb.has_block(text, _SNAPSHOT_NE):
        raise base.Issue236Error(f"parent lacks diagnostic electron snapshot: {_SNAPSHOT_NE}")

    text = base.mp.upsert_parameter(
        text,
        _PARENT_NE,
        "two_term_boundary_expansion",
        _expected_parent_two_term(),
    )
    # Immutable control: identical transferred cell state, baseline two-term
    # spatial representation.
    return base.mp.upsert_parameter(
        text,
        _SNAPSHOT_NE,
        "two_term_boundary_expansion",
        "true",
    )


def _set_child_boundary_mode(text: str) -> str:
    if not base.mb.has_block(text, _CHILD_LIVE_NE):
        raise base.Issue236Error(f"child lacks live electron solver variable: {_CHILD_LIVE_NE}")
    if not base.mb.has_block(text, _CHILD_FROZEN_NE):
        raise base.Issue236Error(
            f"child lacks frozen heavy-transport electron mirror: {_CHILD_FROZEN_NE}"
        )

    # Deliberately change only the frozen transfer mirror.  Live solved n_e is
    # left untouched and continues to inherit the production/global two-term
    # policy.
    return base.mp.upsert_parameter(
        text,
        _CHILD_FROZEN_NE,
        "two_term_boundary_expansion",
        _expected_child_frozen_two_term(),
    )


def _build_parent_input(production_text: str) -> str:
    text = _diag_build_parent_input(production_text)
    text = _set_parent_boundary_mode(text)
    for lane in ("parent_after_transfer", "parent_nonlinear"):
        text = _instrument_face_fields(text, lane=lane, fields=_PARENT_FACE_FIELDS)
    return text


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _diag_build_child_input(production_text, dt_e=dt_e)
    text = _set_child_boundary_mode(text)
    return _instrument_face_fields(text, lane="child_accepted", fields=_CHILD_FACE_FIELDS)


def _face_pp_audit(text: str, *, lane: str, fields: dict[str, str]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    spec = diag._LANES[lane]
    for field_key, variable in fields.items():
        for value_type in ("min", "max"):
            name = f"issue236_diag_{lane}_{field_key}_{value_type}"
            path = f"Postprocessors/{name}"
            checks[f"diag_face_pp:{name}"] = (
                base.mb.has_block(text, path)
                and base.mp.unquote(base.mp.get_parameter(text, path, "type"))
                == "SideExtremeValue"
                and base.mp.unquote(base.mp.get_parameter(text, path, "variable"))
                == variable
                and base.mp.words(base.mp.get_parameter(text, path, "boundary"))
                == [_BOUNDARY]
                and base.mp.unquote(base.mp.get_parameter(text, path, "value_type"))
                == value_type
                and base.mp.unquote(base.mp.get_parameter(text, path, "execute_on"))
                == spec["pp_execute_on"]
                and base.mp.words(base.mp.get_parameter(text, path, "outputs"))
                == [spec["output"]]
            )
    return checks


def _parent_boundary_audit(text: str) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    checks["diag_parent_ne_boundary_mode"] = (
        base.mp.unquote(
            base.mp.get_parameter(text, _PARENT_NE, "two_term_boundary_expansion")
        )
        == _expected_parent_two_term()
    )
    checks["diag_snapshot_ne_remains_two_term"] = (
        base.mp.unquote(
            base.mp.get_parameter(text, _SNAPSHOT_NE, "two_term_boundary_expansion")
        )
        == "true"
    )
    for lane in ("parent_after_transfer", "parent_nonlinear"):
        checks.update(_face_pp_audit(text, lane=lane, fields=_PARENT_FACE_FIELDS))
    return checks


def _resolved_live_ne_two_term(text: str) -> bool:
    local = base.mp.unquote(
        base.mp.get_parameter(text, _CHILD_LIVE_NE, "two_term_boundary_expansion")
    )
    if local not in (None, ""):
        return local.lower() == "true"
    global_value = base.mp.unquote(
        base.mp.get_parameter(text, "GlobalParams", "two_term_boundary_expansion")
    )
    return (global_value or "").lower() == "true"


def _float_param(text: str, path: str, name: str) -> float | None:
    value = base.mp.unquote(base.mp.get_parameter(text, path, name))
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _block_exact(
    text: str,
    path: str,
    *,
    scalar: dict[str, str] | None = None,
    words: dict[str, set[str]] | None = None,
    numeric: dict[str, float] | None = None,
) -> bool:
    if not base.mb.has_block(text, path):
        return False
    for name, expected in (scalar or {}).items():
        if base.mp.unquote(base.mp.get_parameter(text, path, name)) != expected:
            return False
    for name, expected in (words or {}).items():
        if set(base.mp.words(base.mp.get_parameter(text, path, name))) != expected:
            return False
    for name, expected in (numeric or {}).items():
        value = _float_param(text, path, name)
        if value is None or not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-15):
            return False
    return True


def _child_physics_binding_audit(text: str) -> dict[str, bool]:
    """Lock the child physics that makes frozen n_e an active SEE coefficient."""
    checks: dict[str, bool] = {}

    checks["diag_live_ne_remains_two_term"] = _resolved_live_ne_two_term(text)
    checks["diag_child_frozen_ne_boundary_mode"] = (
        base.mp.unquote(
            base.mp.get_parameter(text, _CHILD_FROZEN_NE, "two_term_boundary_expansion")
        )
        == _expected_child_frozen_two_term()
    )

    checks["diag_particle_diffusion_exact"] = _block_exact(
        text,
        "FVKernels/n_e_diffusion",
        scalar={
            "type": "FVDiffusion",
            "variable": "n_e",
            "coeff": "electron_diffusion",
            "block": "plasma",
        },
    )
    checks["diag_energy_diffusion_exact"] = _block_exact(
        text,
        "FVKernels/s5r_n_epsilon_diffusion",
        scalar={
            "type": "FVDiffusion",
            "variable": "n_epsilon",
            "coeff": "electron_energy_diffusion",
            "block": "plasma",
        },
    )

    particle_drift = "FVKernels/n_e_drift"
    energy_drift = "FVKernels/s5r_n_epsilon_drift"
    drift_topology = (
        "potential",
        "carrier",
        "charge_number",
        "advected_interp_method",
        "boundaries_to_avoid",
        "block",
    )
    checks["diag_particle_drift_exact"] = _block_exact(
        text,
        particle_drift,
        scalar={
            "type": "PhysicsFVElectrostaticDrift",
            "variable": "n_e",
            "mobility": "electron_mobility",
            "potential": "potential_plasma",
            "carrier": "carrier_one",
            "charge_number": "-1",
            "advected_interp_method": "upwind",
            "block": "plasma",
        },
        words={"boundaries_to_avoid": _WALLS | {"inlet", "outlet"}},
    )
    checks["diag_energy_drift_exact"] = _block_exact(
        text,
        energy_drift,
        scalar={
            "type": "PhysicsFVElectrostaticDrift",
            "variable": "n_epsilon",
            "mobility": "electron_energy_mobility",
            "potential": "potential_plasma",
            "carrier": "carrier_one",
            "charge_number": "-1",
            "advected_interp_method": "upwind",
            "block": "plasma",
        },
        words={"boundaries_to_avoid": _WALLS | {"inlet", "outlet"}},
    )
    checks["diag_energy_drift_topology_parameters_present"] = all(
        base.mp.get_parameter(text, particle_drift, parameter) is not None
        and base.mp.get_parameter(text, energy_drift, parameter) is not None
        and base.mp.get_parameter(text, particle_drift, parameter)
        == base.mp.get_parameter(text, energy_drift, parameter)
        for parameter in drift_topology
    )

    checks["diag_particle_wall_loss_exact"] = _block_exact(
        text,
        "FVBCs/issue217_grounded_sheath_primary_particle",
        scalar={
            "type": "FVFunctorNeumannBC",
            "variable": "n_e",
            "functor": "issue236_live_electron_surface_particle_flux",
        },
        words={"boundary": _WALLS},
        numeric={"factor": -1.0},
    )
    checks["diag_energy_wall_loss_exact"] = _block_exact(
        text,
        "FVBCs/issue217_grounded_sheath_primary_energy",
        scalar={
            "type": "FVFunctorNeumannBC",
            "variable": "n_epsilon",
            "functor": "issue236_live_electron_surface_energy_flux",
        },
        words={"boundary": _WALLS},
        numeric={"factor": -1.0},
    )
    checks["diag_particle_see_exact"] = _block_exact(
        text,
        "FVBCs/issue27_a8_see_electron_source",
        scalar={
            "type": "FVFunctorNeumannBC",
            "variable": "n_e",
            "functor": "issue27_a8_see_normalized_flux_inward",
        },
        words={"boundary": _WALLS},
        numeric={"factor": 1.0},
    )
    checks["diag_energy_see_exact"] = _block_exact(
        text,
        "FVBCs/issue26_see_energy_source",
        scalar={
            "type": "FVFunctorNeumannBC",
            "variable": "n_epsilon",
            "functor": "issue26_see_energy_normalized_flux_inward",
        },
        words={"boundary": _WALLS},
        numeric={"factor": 1.0},
    )

    heavy_transport = "FunctorMaterials/heavy_transport"
    frozen_material = "FunctorMaterials/issue236_frozen_heavy_electron_density"
    checks["diag_heavy_transport_uses_frozen_ne_exact"] = (
        _block_exact(
            text,
            heavy_transport,
            scalar={"electron_number_density": _CHILD_FROZEN_NE_PHYSICAL},
        )
        and _block_exact(
            text,
            frozen_material,
            scalar={
                "type": "ADParsedFunctorMaterial",
                "property_name": _CHILD_FROZEN_NE_PHYSICAL,
                "block": "plasma",
            },
            words={"functor_names": {"n_e_heavy_frozen"}},
        )
    )
    checks["diag_poisson_uses_live_ne_exact"] = _block_exact(
        text,
        "FunctorMaterials/r31_charge_density",
        scalar={"electron_density": "n_e_physical"},
    )

    mobility_ok = True
    ion_wall_ok = True
    for species, d_mix, mu in (
        ("O2p", "D_mix_O2p", "mu_O2p"),
        ("Om", "D_mix_Om", "mu_Om"),
        ("Op", "D_mix_Op", "mu_Op"),
    ):
        mobility_ok = mobility_ok and _block_exact(
            text,
            f"FunctorMaterials/mobility_{species}",
            words={"functor_names": {d_mix, "T_g"}},
        )
        ion_wall_ok = ion_wall_ok and _block_exact(
            text,
            f"FunctorMaterials/issue27_a6_{species}_wall_flux",
            scalar={"type": "PhysicsIonWallFluxMaterial", "mobility": mu},
        )
    checks["diag_see_mobility_consumes_dmix"] = mobility_ok and ion_wall_ok
    checks["diag_see_material_consumes_ion_wall_flux"] = _block_exact(
        text,
        "FunctorMaterials/issue27_a8_see_material",
        scalar={
            "type": "ADParsedFunctorMaterial",
            "property_name": "issue27_a8_see_normalized_flux_inward",
        },
        words={
            "functor_names": {
                "ion_surface_mass_flux_O2p",
                "ion_migration_mass_flux_O2p",
                "ion_surface_mass_flux_Op",
                "ion_migration_mass_flux_Op",
            }
        },
    )

    checks.update(_face_pp_audit(text, lane="child_accepted", fields=_CHILD_FACE_FIELDS))
    return checks


def _audit_parent(text: str):
    result = _diag_audit_parent(text)
    result["checks"].update(_parent_boundary_audit(text))
    result["boundary_mode"] = _MODE
    return _finalize(result)


def _audit_child(text: str, *, dt_e: float):
    result = _diag_audit_child(text, dt_e=dt_e)
    result["checks"].update(_child_physics_binding_audit(text))
    result["boundary_mode"] = _MODE
    return _finalize(result)


def _self_test_fail(error: Exception) -> dict[str, Any]:
    detail = error.args[0] if error.args else str(error)
    return {
        "status": "FAIL",
        "checks": {"boundary_split_builds": False},
        "failed_checks": ["boundary_split_builds"],
        "detail": {"split_error": detail},
        "boundary_mode": _MODE,
    }


def _self_test():
    try:
        result = _diag_self_test()
        checks = result.setdefault("checks", {})
        parent, child, meta = base.build_split(dt_e=live.ELECTRON_DT_S)
    except base.Issue236Error as error:
        return _self_test_fail(error)

    checks.update(_parent_boundary_audit(parent))
    checks.update(_child_physics_binding_audit(child))
    checks["diag_boundary_schedule_unchanged"] = (
        meta["subcycles_per_heavy"] == 100
        and meta["dt_h_s"] == 1.0e-8
        and meta["dt_e_s"] == 1.0e-10
    )
    result["boundary_mode"] = _MODE
    return _finalize(result)


def _float_or_none(row: dict[str, Any] | None, key: str) -> float | None:
    if not row:
        return None
    value = row.get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read_runtime_log(case_dir: Path) -> str:
    log_path = case_dir.parent / "runtime.log"
    if not log_path.is_file():
        return ""
    return log_path.read_text(encoding="utf-8", errors="replace")


def _lane_rows(case_dir: Path, lane: str) -> list[dict[str, float]]:
    path = diag._find_diag_csv(case_dir, diag._LANES[lane]["file_base"])
    return diag._numeric_rows(path)


def _noninitial(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    return [row for row in rows if row.get("time", 0.0) > 0.0]


def _first_noninitial(rows: list[dict[str, float]]) -> dict[str, float] | None:
    rows = _noninitial(rows)
    return min(rows, key=lambda row: row.get("time", math.inf)) if rows else None


def _min_over_rows(rows: list[dict[str, float]], key: str) -> float | None:
    values = [row[key] for row in _noninitial(rows) if key in row and math.isfinite(row[key])]
    return min(values) if values else None


def _max_time(rows: list[dict[str, float]]) -> float | None:
    values = [row.get("time") for row in _noninitial(rows) if row.get("time") is not None]
    return max(values) if values else None


def _boundary_discriminator(result: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    parent_rows = _lane_rows(case_dir, "parent_after_transfer")
    child_rows = _lane_rows(case_dir, "child_accepted")
    parent = _first_noninitial(parent_rows)
    lane = "parent_after_transfer"

    cell_min = _float_or_none(parent, f"issue236_diag_{lane}_ne_min")
    face_min = _float_or_none(parent, f"issue236_diag_{lane}_ne_face_min")
    snapshot_cell_min = _float_or_none(parent, f"issue236_diag_{lane}_ne_snap_min")
    snapshot_face_min = _float_or_none(parent, f"issue236_diag_{lane}_ne_snap_face_min")
    frozen_face_min = _min_over_rows(
        child_rows, "issue236_diag_child_accepted_frozen_ne_face_min"
    )
    live_face_min = _min_over_rows(
        child_rows, "issue236_diag_child_accepted_live_ne_face_min"
    )
    child_max_time = _max_time(child_rows)
    log_text = _read_runtime_log(case_dir)

    return {
        "mode": _MODE,
        "boundary": _BOUNDARY,
        "first_parent_transfer_time_s": _float_or_none(parent, "time"),
        "cell_ne_min": cell_min,
        "parent_face_ne_min": face_min,
        "snapshot_cell_ne_min": snapshot_cell_min,
        "snapshot_face_ne_min": snapshot_face_min,
        "child_frozen_face_ne_min_observed": frozen_face_min,
        "child_live_face_ne_min_observed": live_face_min,
        "child_max_accepted_time_s": child_max_time,
        "parent_cell_positive": cell_min is not None and cell_min > 0.0,
        "parent_face_negative": face_min is not None and face_min < 0.0,
        "parent_face_nonnegative": face_min is not None and face_min >= 0.0,
        "snapshot_cell_positive": snapshot_cell_min is not None and snapshot_cell_min > 0.0,
        "snapshot_face_negative": snapshot_face_min is not None and snapshot_face_min < 0.0,
        "child_frozen_face_negative_observed": (
            frozen_face_min is not None and frozen_face_min < 0.0
        ),
        "child_frozen_face_nonnegative_observed": (
            frozen_face_min is not None and frozen_face_min >= 0.0
        ),
        "negative_heavy_transport_signature_present": _NEGATIVE_NE_SIGNATURE in log_text,
        "runtime_parent_final_time_s": result.get("parent_final_time_s"),
        "runtime_child_final_time_s": result.get("child_final_time_s"),
        "interpretation": {
            "two_term": "two-term parent mirror + two-term child frozen mirror",
            "one_term": "one-term parent mirror + two-term child frozen mirror",
            "mirrors_one_term": "one-term parent and child frozen mirrors; live solved n_e unchanged",
        }[_MODE],
    }


def _runtime_analysis(case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool):
    result = _diag_runtime_analysis(
        case_dir, dt_e=dt_e, returncode=returncode, timed_out=timed_out
    )
    result["boundary_face_discriminator"] = _boundary_discriminator(result, case_dir)
    return result


base.build_parent_input = _build_parent_input
base.build_child_input = _build_child_input
base._audit_parent = _audit_parent
base._audit_child = _audit_child
base.self_test = _self_test
base._runtime_analysis = _runtime_analysis

if __name__ == "__main__":
    raise SystemExit(base.main())
