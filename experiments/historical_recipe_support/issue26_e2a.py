"""Issue #26 E2a controlled electron-energy diffusion construction."""
from __future__ import annotations

import math
from typing import Any

from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from experiments.historical_recipe_support.issue26_e1 import (
    E1_DT_S,
    ENERGY_INVENTORY_PP,
    ENERGY_NORM_AVG_PP,
    ENERGY_NORM_MAX_PP,
    ENERGY_NORM_MIN_PP,
    ENERGY_REFERENCE_EV,
    ENERGY_VARIABLE,
    build_issue26_e1_input,
)

E2A_DT_S = E1_DT_S
E2A_DIFFUSIVITY_M2_S = 100.0
E2A_INITIAL_FUNCTION = "e2a_energy_profile"
E2A_DIFFUSIVITY_MATERIAL = "e2a_energy_diffusivity"
E2A_DIFFUSION_KERNEL = "n_epsilon_diffusion"
E2A_IC = "e2a_n_epsilon_ic"
E2A_INITIAL_EXPRESSION = (
    "1.0 + 0.5*exp(-800.0*(x-0.12)^2 - 80.0*(y-0.22)^2)"
)


class Issue26E2AError(RuntimeError):
    pass


def build_issue26_e2a_input(
    base_text: str,
    *,
    diffusivity_m2_s: float,
) -> tuple[str, dict[str, Any]]:
    if not math.isfinite(diffusivity_m2_s) or diffusivity_m2_s < 0.0:
        raise Issue26E2AError("diffusivity_m2_s must be finite and non-negative")

    text, predecessor = build_issue26_e1_input(base_text, initial_energy_hat=1.0)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue26E2AError("E1 predecessor audit is not PASS")

    for path in (
        f"Functions/{E2A_INITIAL_FUNCTION}",
        f"ICs/{E2A_IC}",
        f"FunctorMaterials/{E2A_DIFFUSIVITY_MATERIAL}",
        f"FVKernels/{E2A_DIFFUSION_KERNEL}",
    ):
        mb.require_absent(text, path)

    text = mp.remove_parameter(text, f"Variables/{ENERGY_VARIABLE}", "initial_condition")
    text = mb.insert_child_block(
        text,
        "Functions",
        f"""  [{E2A_INITIAL_FUNCTION}]
    type = ParsedFunction
    expression = '{E2A_INITIAL_EXPRESSION}'
  []""",
    )
    text = mb.insert_child_block(
        text,
        "ICs",
        f"""  [{E2A_IC}]
    type = FunctionIC
    variable = {ENERGY_VARIABLE}
    function = {E2A_INITIAL_FUNCTION}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{E2A_DIFFUSIVITY_MATERIAL}]
    type = ADGenericFunctorMaterial
    prop_names = 'electron_energy_diffusivity_control'
    prop_values = '{diffusivity_m2_s:.17g}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [{E2A_DIFFUSION_KERNEL}]
    type = FVDiffusion
    variable = {ENERGY_VARIABLE}
    coeff = electron_energy_diffusivity_control
    block = plasma
  []""",
    )
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{E2A_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{E2A_DT_S:.17g}")

    audit = audit_issue26_e2a_input(text, diffusivity_m2_s=diffusivity_m2_s)
    if audit["status"] != "PASS":
        raise Issue26E2AError(f"E2a construction audit failed: {audit['failed_checks']}")

    return text, {
        "issue": 26,
        "phase": "E2a",
        "model": "CONTROLLED_ELECTRON_ENERGY_DIFFUSION",
        "predecessor": predecessor,
        "electron_energy_unknown": "n_epsilon == n_epsilon_hat",
        "energy_reference_eV": ENERGY_REFERENCE_EV,
        "initial_profile": E2A_INITIAL_EXPRESSION,
        "diffusivity_m2_s": diffusivity_m2_s,
        "natural_zero_energy_flux_boundaries": True,
        "transport_lookup_coupled_to_solved_energy": False,
        "energy_diffusion_enabled": True,
        "energy_drift_enabled": False,
        "joule_source_enabled": False,
        "wall_energy_flux_enabled": False,
        "see_energy_source_enabled": False,
        "volumetric_reaction_energy_sources_enabled": False,
        "timestep_s": E2A_DT_S,
        "observables": {
            "inventory": ENERGY_INVENTORY_PP,
            "average": ENERGY_NORM_AVG_PP,
            "minimum": ENERGY_NORM_MIN_PP,
            "maximum": ENERGY_NORM_MAX_PP,
        },
        "audit": audit,
    }


def audit_issue26_e2a_input(
    text: str,
    *,
    diffusivity_m2_s: float,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    required = (
        f"Functions/{E2A_INITIAL_FUNCTION}",
        f"ICs/{E2A_IC}",
        f"FunctorMaterials/{E2A_DIFFUSIVITY_MATERIAL}",
        f"FVKernels/{E2A_DIFFUSION_KERNEL}",
    )
    for path in required:
        checks[f"block:{path}"] = mb.has_block(text, path)

    checks["variable_has_no_uniform_ic"] = (
        mp.get_parameter(text, f"Variables/{ENERGY_VARIABLE}", "initial_condition") is None
    )
    checks["function_ic_targets_energy"] = (
        mp.get_parameter(text, f"ICs/{E2A_IC}", "variable") == ENERGY_VARIABLE
        and mp.get_parameter(text, f"ICs/{E2A_IC}", "function") == E2A_INITIAL_FUNCTION
    )
    checks["diffusion_targets_energy"] = (
        mp.get_parameter(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}", "variable")
        == ENERGY_VARIABLE
    )
    checks["diffusion_uses_controlled_coefficient"] = (
        mp.get_parameter(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}", "coeff")
        == "electron_energy_diffusivity_control"
    )
    checks["controlled_diffusivity_value"] = math.isclose(
        float(
            mp.words(
                mp.get_parameter(
                    text,
                    f"FunctorMaterials/{E2A_DIFFUSIVITY_MATERIAL}",
                    "prop_values",
                )
            )[0]
        ),
        diffusivity_m2_s,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    checks["lookup_still_fixed_e2a"] = (
        mp.get_parameter(text, "FunctorMaterials/electron_transport", "mean_energy")
        == "mean_en"
    )
    checks["no_energy_drift_e2a"] = not mb.has_block(text, "FVKernels/n_epsilon_drift")
    checks["dt"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "dt") or "nan"),
        E2A_DT_S,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    checks["one_step"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        E2A_DT_S,
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
    "E2A_DIFFUSION_KERNEL",
    "E2A_DIFFUSIVITY_M2_S",
    "E2A_DT_S",
    "E2A_IC",
    "E2A_INITIAL_EXPRESSION",
    "E2A_INITIAL_FUNCTION",
    "Issue26E2AError",
    "audit_issue26_e2a_input",
    "build_issue26_e2a_input",
]
