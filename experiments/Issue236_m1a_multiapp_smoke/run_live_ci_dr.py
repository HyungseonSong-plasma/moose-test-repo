#!/usr/bin/env python3
"""Issue-236 dielectric-relaxation-resolved live-electron discriminator.

Coupling per heavy interval:

1. hold the heavy state and heavy-transport electron-density input fixed;
2. solve n_e, n_epsilon, and potential_plasma together for 100 fast substeps;
3. transfer the relaxed electron/energy/Poisson state back to the parent;
4. advance the heavy system once.

Schedule:
* electron + Poisson dt_e = 1e-10 s;
* 100 fast substeps per heavy step;
* heavy dt_h = 1e-8 s;
* 2 heavy steps;
* total time = 2e-8 s;
* 200 electron/Poisson steps total.

The production strict electron-impact lookup policy remains enabled.  Heavy
transport is deliberately evaluated with a frozen copy of the parent electron
density during each fast interval: heavy species are not advanced in the fast
child, so their Debye-Huckel transport/mobility closure must not depend on an
intermediate electron Newton trial state.  Live n_e remains coupled to electron
chemistry and Poisson.
"""
from __future__ import annotations

import math

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_pos as pos

live = pos.live
base = pos.base

live.TOTAL_TIME_S = 2.0e-8
live.HEAVY_STEPS = 2
live.HEAVY_DT_S = 1.0e-8
live.ELECTRON_DT_S = 1.0e-10
live.ELECTRON_STEPS_PER_HEAVY = 100

base.DT_H_S = live.HEAVY_DT_S
base.DT_E_SMOKE_S = live.ELECTRON_DT_S

_pos_build_parent_input = base.build_parent_input
_pos_build_child_input = base.build_child_input
_pos_audit_parent = base._audit_parent
_pos_audit_child = base._audit_child
_pos_self_test = base.self_test

_FROZEN_NE_AUX = "n_e_heavy_frozen"
_FROZEN_NE_PHYSICAL = "n_e_heavy_frozen_physical"
_FROZEN_NE_TRANSFER = "frozen_ne_to_electron"
_FROZEN_NE_MATERIAL = "issue236_frozen_heavy_electron_density"


def _finalize(result):
    result["failed_checks"] = sorted(
        key for key, ok in result["checks"].items() if not ok
    )
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _build_parent_input(production_text: str) -> str:
    text = _pos_build_parent_input(production_text)
    path = f"Transfers/{_FROZEN_NE_TRANSFER}"
    if base.mb.has_block(text, path):
        raise base.Issue236Error(f"duplicate frozen-electron transfer: {path}")
    text = base.mb.insert_child_block(
        text,
        "Transfers",
        f"""  [{_FROZEN_NE_TRANSFER}]
    type = MultiAppCopyTransfer
    to_multi_app = electron
    source_variable = n_e
    variable = {_FROZEN_NE_AUX}
    execute_on = TIMESTEP_BEGIN
  []""",
    )
    return text


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _pos_build_child_input(production_text, dt_e=dt_e)

    text = base._ensure_top_block(text, "AuxVariables")
    aux_path = f"AuxVariables/{_FROZEN_NE_AUX}"
    if base.mb.has_block(text, aux_path):
        raise base.Issue236Error(f"duplicate frozen heavy electron variable: {aux_path}")
    text = base.mb.insert_child_block(
        text,
        "AuxVariables",
        f"""  [{_FROZEN_NE_AUX}]
    type = MooseVariableFVReal
    initial_condition = 1.0
    block = plasma
  []""",
    )

    material_path = f"FunctorMaterials/{_FROZEN_NE_MATERIAL}"
    if base.mb.has_block(text, material_path):
        raise base.Issue236Error(f"duplicate frozen heavy electron material: {material_path}")
    text = base.mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{_FROZEN_NE_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {_FROZEN_NE_PHYSICAL}
    functor_names = '{_FROZEN_NE_AUX}'
    functor_symbols = 'ne_hat_frozen'
    expression = '${{n_e_value}}*ne_hat_frozen'
    block = plasma
  []""",
    )

    heavy_transport = "FunctorMaterials/heavy_transport"
    if not base.mb.has_block(text, heavy_transport):
        raise base.Issue236Error("live child lacks FunctorMaterials/heavy_transport")
    text = base.mp.upsert_parameter(
        text,
        heavy_transport,
        "electron_number_density",
        _FROZEN_NE_PHYSICAL,
    )
    return text


def _audit_parent(text: str):
    result = _pos_audit_parent(text)
    path = f"Transfers/{_FROZEN_NE_TRANSFER}"
    result["checks"]["frozen_ne_transfer"] = (
        base.mb.has_block(text, path)
        and base.mp.unquote(base.mp.get_parameter(text, path, "type"))
        == "MultiAppCopyTransfer"
        and base.mp.unquote(base.mp.get_parameter(text, path, "to_multi_app")) == "electron"
        and base.mp.words(base.mp.get_parameter(text, path, "source_variable")) == ["n_e"]
        and base.mp.words(base.mp.get_parameter(text, path, "variable")) == [_FROZEN_NE_AUX]
        and base.mp.unquote(base.mp.get_parameter(text, path, "execute_on"))
        == "TIMESTEP_BEGIN"
    )
    return _finalize(result)


def _audit_child(text: str, *, dt_e: float):
    result = _pos_audit_child(text, dt_e=dt_e)
    aux_path = f"AuxVariables/{_FROZEN_NE_AUX}"
    material_path = f"FunctorMaterials/{_FROZEN_NE_MATERIAL}"
    heavy_transport = "FunctorMaterials/heavy_transport"
    result["checks"]["frozen_heavy_ne_aux"] = (
        base.mb.has_block(text, aux_path)
        and base.mp.unquote(base.mp.get_parameter(text, aux_path, "type"))
        == "MooseVariableFVReal"
        and base.mp.unquote(base.mp.get_parameter(text, aux_path, "block")) == "plasma"
    )
    result["checks"]["frozen_heavy_ne_material"] = (
        base.mb.has_block(text, material_path)
        and base.mp.unquote(base.mp.get_parameter(text, material_path, "type"))
        == "ADParsedFunctorMaterial"
        and base.mp.unquote(base.mp.get_parameter(text, material_path, "property_name"))
        == _FROZEN_NE_PHYSICAL
        and base.mp.words(base.mp.get_parameter(text, material_path, "functor_names"))
        == [_FROZEN_NE_AUX]
    )
    result["checks"]["heavy_transport_uses_frozen_ne"] = (
        base.mb.has_block(text, heavy_transport)
        and base.mp.unquote(
            base.mp.get_parameter(text, heavy_transport, "electron_number_density")
        )
        == _FROZEN_NE_PHYSICAL
    )
    result["checks"]["poisson_still_uses_live_ne"] = (
        base.mb.has_block(text, "FunctorMaterials/r31_charge_density")
        and base.mp.unquote(
            base.mp.get_parameter(
                text, "FunctorMaterials/r31_charge_density", "electron_density"
            )
        )
        == "n_e_physical"
    )
    return _finalize(result)


def _self_test():
    result = _pos_self_test()
    checks = result.setdefault("checks", {})

    # Remove schedule assertions inherited from the older 1e-7/1e-9 run.
    for obsolete in (
        "smoke_subcycles",
        "heavy_dt_1e_8",
        "heavy_dt_1e_7",
        "electron_dt_1e_9",
        "ten_heavy_steps",
        "ten_electron_steps_per_heavy",
        "hundred_total_electron_steps",
        "hundred_electron_steps_per_heavy",
        "thousand_total_electron_steps",
        "final_time_1e_6",
        "multirate_ratio_100",
    ):
        checks.pop(obsolete, None)

    parent, child, meta = base.build_split(dt_e=live.ELECTRON_DT_S)

    checks["heavy_dt_1e_8"] = math.isclose(
        meta["dt_h_s"], 1.0e-8, rel_tol=0.0, abs_tol=0.0
    )
    checks["electron_poisson_dt_1e_10"] = math.isclose(
        meta["dt_e_s"], 1.0e-10, rel_tol=0.0, abs_tol=0.0
    )
    checks["two_heavy_steps"] = meta["heavy_steps"] == 2
    checks["hundred_fast_steps_per_heavy"] = meta["subcycles_per_heavy"] == 100
    checks["two_hundred_fast_steps_total"] = meta["subcycles_expected"] == 200
    checks["final_time_2e_8"] = math.isclose(
        meta["total_time_s"], 2.0e-8, rel_tol=0.0, abs_tol=0.0
    )
    checks["multirate_ratio_100"] = math.isclose(
        meta["dt_h_s"] / meta["dt_e_s"], 100.0, rel_tol=0.0, abs_tol=1.0e-12
    )

    checks["electron_poisson_coupled_fast_system"] = (
        all(
            base.mb.has_block(child, f"Variables/{name}")
            for name in ("n_e", "n_epsilon", "potential_plasma")
        )
        and base.mb.has_block(child, "FVKernels/r31_phi_diffusion")
        and base.mb.has_block(child, "FVKernels/r31_phi_charge_source")
    )
    checks["heavy_parent_has_no_poisson"] = (
        not base.mb.has_block(parent, "Variables/potential_plasma")
        and not base.mb.has_block(parent, "FVKernels/r31_phi_diffusion")
        and not base.mb.has_block(parent, "FVKernels/r31_phi_charge_source")
    )
    checks["electron_first_execute_point"] = (
        base.mp.unquote(base.mp.get_parameter(parent, "MultiApps/electron", "execute_on"))
        == "TIMESTEP_BEGIN"
    )
    checks["single_fast_multiapp"] = set(base._children(parent, "MultiApps")) == {
        "MultiApps/electron"
    }
    checks["strict_lookup_policy_retained"] = all(
        base.mp.get_parameter(child, path, "clamp_mean_energy_to_table") is None
        for path in base._children(child, "FunctorMaterials")
    )
    checks["heavy_transport_frozen_during_fast_solve"] = (
        base.mp.unquote(
            base.mp.get_parameter(
                child, "FunctorMaterials/heavy_transport", "electron_number_density"
            )
        )
        == _FROZEN_NE_PHYSICAL
        and base.mb.has_block(child, f"AuxVariables/{_FROZEN_NE_AUX}")
        and base.mb.has_block(parent, f"Transfers/{_FROZEN_NE_TRANSFER}")
    )
    checks["live_ne_retained_for_poisson"] = (
        base.mp.unquote(
            base.mp.get_parameter(
                child, "FunctorMaterials/r31_charge_density", "electron_density"
            )
        )
        == "n_e_physical"
    )

    result["failed_checks"] = sorted(key for key, ok in checks.items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


base.build_parent_input = _build_parent_input
base.build_child_input = _build_child_input
base._audit_parent = _audit_parent
base._audit_child = _audit_child
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
