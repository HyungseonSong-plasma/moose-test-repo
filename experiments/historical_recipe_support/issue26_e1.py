"""Issue #26 E1 normalized electron-energy zero-source construction."""
from __future__ import annotations

import math
from typing import Any

from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4_qf1 import build_r4_qf1_input
from experiments.historical_recipe_support.issue91_r3 import MEAN_ELECTRON_ENERGY_EV

ELEMENTARY_CHARGE_C = 1.602176634e-19
ENERGY_REFERENCE_EV = MEAN_ELECTRON_ENERGY_EV
E1_DT_S = 1.0e-8

ENERGY_VARIABLE = "n_epsilon"
ENERGY_TIME_KERNEL = "n_epsilon_time"
ENERGY_DENSITY_EV_FUNCTOR = "n_epsilon_physical_eV_m3"
ENERGY_DENSITY_J_FUNCTOR = "electron_energy_density_J_m3"
MEAN_EN_SOLVED_FUNCTOR = "mean_en_solved"

ENERGY_INVENTORY_PP = "electron_energy_inventory_J"
ENERGY_NORM_AVG_PP = "n_epsilon_avg"
ENERGY_NORM_MIN_PP = "n_epsilon_min"
ENERGY_NORM_MAX_PP = "n_epsilon_max"
MEAN_EN_AVG_PP = "mean_en_solved_avg"
MEAN_EN_MIN_PP = "mean_en_solved_min"
MEAN_EN_MAX_PP = "mean_en_solved_max"


class Issue26E1Error(RuntimeError):
    pass


def _top_level_float(text: str, name: str) -> float:
    import re
    matches = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", text)
    if len(matches) != 1:
        raise Issue26E1Error(f"cannot resolve unique top-level scalar {name}")
    value = float(matches[0].strip())
    if not math.isfinite(value):
        raise Issue26E1Error(f"non-finite scalar {name}={value}")
    return value


def build_issue26_e1_input(
    base_text: str,
    *,
    initial_energy_hat: float,
) -> tuple[str, dict[str, Any]]:
    if not math.isfinite(initial_energy_hat) or initial_energy_hat <= 0.0:
        raise Issue26E1Error("initial_energy_hat must be finite and positive")

    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue26E1Error("R4-QF1 predecessor audit is not PASS")

    for path in (
        f"Variables/{ENERGY_VARIABLE}",
        f"FunctorMaterials/{ENERGY_DENSITY_EV_FUNCTOR}",
        f"FunctorMaterials/{ENERGY_DENSITY_J_FUNCTOR}",
        f"FunctorMaterials/{MEAN_EN_SOLVED_FUNCTOR}",
        f"FVKernels/{ENERGY_TIME_KERNEL}",
        f"Postprocessors/{ENERGY_INVENTORY_PP}",
        f"Postprocessors/{ENERGY_NORM_AVG_PP}",
        f"Postprocessors/{ENERGY_NORM_MIN_PP}",
        f"Postprocessors/{ENERGY_NORM_MAX_PP}",
        f"Postprocessors/{MEAN_EN_AVG_PP}",
        f"Postprocessors/{MEAN_EN_MIN_PP}",
        f"Postprocessors/{MEAN_EN_MAX_PP}",
    ):
        mb.require_absent(text, path)

    n_ref = _top_level_float(text, "n_e_value")
    energy_scale_ev_m3 = n_ref * ENERGY_REFERENCE_EV
    energy_scale_j_m3 = energy_scale_ev_m3 * ELEMENTARY_CHARGE_C

    text = mb.insert_child_block(
        text,
        "Variables",
        f"""  [{ENERGY_VARIABLE}]
    type = MooseVariableFVReal
    initial_condition = {initial_energy_hat:.17g}
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{ENERGY_DENSITY_EV_FUNCTOR}]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_DENSITY_EV_FUNCTOR}
    functor_names = '{ENERGY_VARIABLE}'
    functor_symbols = 'eps_hat'
    expression = '{energy_scale_ev_m3:.17g}*eps_hat'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{ENERGY_DENSITY_J_FUNCTOR}]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_DENSITY_J_FUNCTOR}
    functor_names = '{ENERGY_VARIABLE}'
    functor_symbols = 'eps_hat'
    expression = '{energy_scale_j_m3:.17g}*eps_hat'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{MEAN_EN_SOLVED_FUNCTOR}]
    type = ADParsedFunctorMaterial
    property_name = {MEAN_EN_SOLVED_FUNCTOR}
    functor_names = '{ENERGY_VARIABLE} n_e'
    functor_symbols = 'eps_hat ne_hat'
    expression = '{ENERGY_REFERENCE_EV:.17g}*eps_hat/ne_hat'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [{ENERGY_TIME_KERNEL}]
    type = FVTimeKernel
    variable = {ENERGY_VARIABLE}
    block = plasma
  []""",
    )

    postprocessors = (
        (
            ENERGY_INVENTORY_PP,
            "ADElementIntegralFunctorPostprocessor",
            f"    functor = {ENERGY_DENSITY_J_FUNCTOR}\n    block = plasma",
        ),
        (
            ENERGY_NORM_AVG_PP,
            "ElementAverageFunctorPostprocessor",
            f"    functor = {ENERGY_VARIABLE}\n    block = plasma",
        ),
        (
            ENERGY_NORM_MIN_PP,
            "ADElementExtremeFunctorValue",
            f"    functor = {ENERGY_VARIABLE}\n    value_type = min\n    block = plasma",
        ),
        (
            ENERGY_NORM_MAX_PP,
            "ADElementExtremeFunctorValue",
            f"    functor = {ENERGY_VARIABLE}\n    value_type = max\n    block = plasma",
        ),
        (
            MEAN_EN_AVG_PP,
            "ElementAverageFunctorPostprocessor",
            f"    functor = {MEAN_EN_SOLVED_FUNCTOR}\n    block = plasma",
        ),
        (
            MEAN_EN_MIN_PP,
            "ADElementExtremeFunctorValue",
            f"    functor = {MEAN_EN_SOLVED_FUNCTOR}\n    value_type = min\n    block = plasma",
        ),
        (
            MEAN_EN_MAX_PP,
            "ADElementExtremeFunctorValue",
            f"    functor = {MEAN_EN_SOLVED_FUNCTOR}\n    value_type = max\n    block = plasma",
        ),
    )
    for name, type_name, body in postprocessors:
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{name}]
    type = {type_name}
{body}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )

    text = mp.upsert_parameter(text, "Executioner", "dt", f"{E1_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{E1_DT_S:.17g}")

    audit = audit_issue26_e1_input(text, initial_energy_hat=initial_energy_hat)
    if audit["status"] != "PASS":
        raise Issue26E1Error(f"E1 construction audit failed: {audit['failed_checks']}")

    return text, {
        "issue": 26,
        "phase": "E1",
        "model": "NORMALIZED_ELECTRON_ENERGY_ZERO_SOURCE",
        "predecessor": predecessor,
        "electron_density_unknown": "n_e == n_hat",
        "electron_energy_unknown": "n_epsilon == n_epsilon_hat",
        "electron_reference_density_m3": n_ref,
        "energy_reference_eV": ENERGY_REFERENCE_EV,
        "initial_energy_hat": initial_energy_hat,
        "initial_mean_energy_eV_if_ne_hat_1": ENERGY_REFERENCE_EV * initial_energy_hat,
        "energy_density_eV_m3": (
            "n_epsilon_physical_eV_m3 = n_ref * energy_reference_eV * n_epsilon_hat"
        ),
        "energy_density_J_m3": (
            "electron_energy_density_J_m3 = e * n_ref * energy_reference_eV * n_epsilon_hat"
        ),
        "solved_mean_energy": (
            "mean_en_solved = energy_reference_eV * n_epsilon_hat / n_e_hat"
        ),
        "transport_lookup_coupled_to_solved_energy": False,
        "fixed_lookup_mean_energy_eV": MEAN_ELECTRON_ENERGY_EV,
        "energy_transport_enabled": False,
        "joule_source_enabled": False,
        "wall_energy_flux_enabled": False,
        "see_energy_source_enabled": False,
        "volumetric_reaction_energy_sources_enabled": False,
        "timestep_s": E1_DT_S,
        "audit": audit,
    }


def audit_issue26_e1_input(
    text: str,
    *,
    initial_energy_hat: float,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    required = (
        f"Variables/{ENERGY_VARIABLE}",
        f"FunctorMaterials/{ENERGY_DENSITY_EV_FUNCTOR}",
        f"FunctorMaterials/{ENERGY_DENSITY_J_FUNCTOR}",
        f"FunctorMaterials/{MEAN_EN_SOLVED_FUNCTOR}",
        f"FVKernels/{ENERGY_TIME_KERNEL}",
        f"Postprocessors/{ENERGY_INVENTORY_PP}",
        f"Postprocessors/{ENERGY_NORM_AVG_PP}",
        f"Postprocessors/{ENERGY_NORM_MIN_PP}",
        f"Postprocessors/{ENERGY_NORM_MAX_PP}",
        f"Postprocessors/{MEAN_EN_AVG_PP}",
        f"Postprocessors/{MEAN_EN_MIN_PP}",
        f"Postprocessors/{MEAN_EN_MAX_PP}",
    )
    for path in required:
        checks[f"block:{path}"] = mb.has_block(text, path)

    checks["normalized_energy_ic"] = math.isclose(
        float(mp.get_parameter(text, f"Variables/{ENERGY_VARIABLE}", "initial_condition") or "nan"),
        initial_energy_hat,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    checks["energy_time_kernel_variable"] = (
        mp.get_parameter(text, f"FVKernels/{ENERGY_TIME_KERNEL}", "variable")
        == ENERGY_VARIABLE
    )
    checks["mean_energy_bridge_uses_solved_states"] = (
        mp.words(
            mp.get_parameter(
                text,
                f"FunctorMaterials/{MEAN_EN_SOLVED_FUNCTOR}",
                "functor_names",
            )
        )
        == [ENERGY_VARIABLE, "n_e"]
    )
    checks["lookup_still_fixed_e1"] = (
        mp.get_parameter(text, "FunctorMaterials/electron_transport", "mean_energy")
        == "mean_en"
    )
    checks["no_energy_diffusion_e1"] = not mb.has_block(text, "FVKernels/n_epsilon_diffusion")
    checks["no_energy_drift_e1"] = not mb.has_block(text, "FVKernels/n_epsilon_drift")
    checks["dt"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "dt") or "nan"),
        E1_DT_S,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    checks["one_step"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        E1_DT_S,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }


__all__ = [
    "E1_DT_S",
    "ELEMENTARY_CHARGE_C",
    "ENERGY_DENSITY_EV_FUNCTOR",
    "ENERGY_DENSITY_J_FUNCTOR",
    "ENERGY_INVENTORY_PP",
    "ENERGY_NORM_AVG_PP",
    "ENERGY_NORM_MAX_PP",
    "ENERGY_NORM_MIN_PP",
    "ENERGY_REFERENCE_EV",
    "ENERGY_TIME_KERNEL",
    "ENERGY_VARIABLE",
    "Issue26E1Error",
    "MEAN_EN_AVG_PP",
    "MEAN_EN_MAX_PP",
    "MEAN_EN_MIN_PP",
    "MEAN_EN_SOLVED_FUNCTOR",
    "audit_issue26_e1_input",
    "build_issue26_e1_input",
]
