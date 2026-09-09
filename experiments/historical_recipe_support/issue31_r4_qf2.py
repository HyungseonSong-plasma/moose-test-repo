"""Issue #31 R4-QF2 local-charge relaxation discriminator.

QF2 is the final R4 architecture discriminator before Issue #31 closure.  It
starts from the accepted QF1 configuration (uniform quasi-neutral heavy state,
20 sccm pure-O2 inlet, solved Poisson, closed electron/charged-heavy feedback)
and adds one small mean-preserving electron-density perturbation on the
canonical real-qvt RZ mesh.

The perturbation is linear in the axial coordinate y and is centered on the
RZ-volume-weighted cell-centroid mean of the canonical plasma mesh.  For the
FV piecewise-constant initialization used here, this makes the discrete volume
mean of the perturbation zero to roundoff while creating a non-zero local
charge separation.  Runtime evidence still measures the actual initial global
charge and local charge extrema rather than assuming exact cancellation.
"""
from __future__ import annotations

import math
from typing import Any

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4_qf1 import (
    EXPECTED_FEEDBACK_KERNELS,
    FEEDBACK_POTENTIAL,
    build_r4_qf1_input,
)
from experiments.historical_recipe_support.issue31_r4_qn0 import _top_level_float

QF2_NE_PERTURBATION_AMPLITUDE = 1.0e-4
QVT_RZ_VOLUME_WEIGHTED_Y_MEAN_M = 0.1789375023987653
QVT_CELL_CENTROID_MAX_ABS_Y_OFFSET_M = 0.15883232862245206
QF2_NE_FUNCTION = "r31_qf2_ne_hat_ic"
QF2_NE_IC = "r31_qf2_ne_ic"
QF2_CHARGE_MIN_PP = "r31_qf2_charge_density_min"
QF2_CHARGE_MAX_PP = "r31_qf2_charge_density_max"


class Issue31R4QF2Error(RuntimeError):
    pass


def _perturbation_expression() -> str:
    return (
        "'1.0+"
        f"{QF2_NE_PERTURBATION_AMPLITUDE:.17g}*"
        f"(y-{QVT_RZ_VOLUME_WEIGHTED_Y_MEAN_M:.17g})/"
        f"{QVT_CELL_CENTROID_MAX_ABS_Y_OFFSET_M:.17g}'"
    )


def _apply_local_charge_perturbation(text: str) -> tuple[str, dict[str, Any]]:
    """Replace uniform n_hat=1 with a small mean-preserving axial perturbation."""
    old_ic = mp.get_parameter(text, "Variables/n_e", "initial_condition")
    if old_ic != "1.0":
        raise Issue31R4QF2Error(
            f"unexpected QF1 electron IC predecessor {old_ic!r}; expected '1.0'"
        )

    for path in (
        f"Functions/{QF2_NE_FUNCTION}",
        f"ICs/{QF2_NE_IC}",
        f"Postprocessors/{QF2_CHARGE_MIN_PP}",
        f"Postprocessors/{QF2_CHARGE_MAX_PP}",
    ):
        mb.require_absent(text, path)

    text = mp.remove_parameter(text, "Variables/n_e", "initial_condition")
    text = mb.insert_child_block(
        text,
        "Functions",
        f"""  [{QF2_NE_FUNCTION}]
    type = ParsedFunction
    expression = {_perturbation_expression()}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "ICs",
        f"""  [{QF2_NE_IC}]
    type = FunctionIC
    variable = n_e
    function = {QF2_NE_FUNCTION}
  []""",
    )

    # Measure the actual initial state and final relaxed state.  The existing
    # n_e postprocessors report physical density because the accepted R3/QF1
    # instrumentation is built on n_e_physical.
    for pp in ("n_e_min", "n_e_max", "n_e_avg", "r31_charge_integral"):
        text = mp.upsert_parameter(
            text,
            f"Postprocessors/{pp}",
            "execute_on",
            "'INITIAL TIMESTEP_END'",
        )

    for name, value_type in (
        (QF2_CHARGE_MIN_PP, "min"),
        (QF2_CHARGE_MAX_PP, "max"),
    ):
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{name}]
    type = ADElementExtremeFunctorValue
    functor = charge_density
    value_type = {value_type}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )

    return text, {
        "carrier": "electron normalized density n_hat",
        "function": QF2_NE_FUNCTION,
        "ic": QF2_NE_IC,
        "amplitude": QF2_NE_PERTURBATION_AMPLITUDE,
        "shape": "linear axial y mode",
        "expression": _perturbation_expression(),
        "qvt_rz_volume_weighted_y_mean_m": QVT_RZ_VOLUME_WEIGHTED_Y_MEAN_M,
        "qvt_cell_centroid_max_abs_y_offset_m": QVT_CELL_CENTROID_MAX_ABS_Y_OFFSET_M,
        "mean_preservation_intent": (
            "canonical qvt FV cell-centroid RZ-volume weighted perturbation mean = 0"
        ),
        "expected_n_hat_min": 1.0 - QF2_NE_PERTURBATION_AMPLITUDE,
        "expected_n_hat_max_approx": 1.0000875289081426,
        "actual_global_charge_measured": True,
        "actual_local_charge_extrema_measured": True,
    }


def build_r4_qf2_input(base_text: str) -> tuple[str, dict[str, Any]]:
    """Build the final bounded R4 local-charge relaxation discriminator."""
    text, qf1_meta = build_r4_qf1_input(base_text)
    if qf1_meta["audit"]["status"] != "PASS":
        raise Issue31R4QF2Error("QF1 predecessor audit is not PASS")

    reference = float(
        qf1_meta["predecessor"]["quasi_neutral_reference"][
            "electron_reference_density_m3"
        ]
    )
    text, perturbation = _apply_local_charge_perturbation(text)
    audit = audit_r4_qf2_input(text, expected_reference_m3=reference)
    if audit["status"] != "PASS":
        raise Issue31R4QF2Error(
            f"constructed R4-QF2 input failed audit: {audit['failed_checks']}"
        )

    return text, {
        "issue": 31,
        "model": "R4_QF2_LOCAL_CHARGE_RELAXATION",
        "predecessor": qf1_meta,
        "electron_reference_density_m3": reference,
        "poisson_enabled": True,
        "electrostatic_feedback_enabled": True,
        "surface_accumulated_charge_enabled": False,
        "volumetric_reactions_enabled": False,
        "secondary_emission_enabled": False,
        "all_ground_phi": True,
        "inlet": qf1_meta["inlet"],
        "initial_plasma": qf1_meta["initial_plasma"],
        "perturbation": perturbation,
        "closure_intent": (
            "one final bounded non-zero local electrostatic response/relaxation test; "
            "PASS supports closing R4 and moving to surface-reaction work"
        ),
        "audit": audit,
    }


def audit_r4_qf2_input(
    text: str,
    *,
    expected_reference_m3: float | None = None,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    checks["electron_variable_uniform_ic_removed"] = (
        mp.get_parameter(text, "Variables/n_e", "initial_condition") is None
    )
    checks["electron_ic_function_exists"] = mb.has_block(
        text, f"Functions/{QF2_NE_FUNCTION}"
    )
    checks["electron_function_ic_exists"] = mb.has_block(text, f"ICs/{QF2_NE_IC}")
    if checks["electron_ic_function_exists"]:
        checks["electron_perturbation_expression"] = (
            mp.get_parameter(text, f"Functions/{QF2_NE_FUNCTION}", "expression")
            == _perturbation_expression()
        )
    if checks["electron_function_ic_exists"]:
        checks["electron_function_ic_variable"] = (
            mp.get_parameter(text, f"ICs/{QF2_NE_IC}", "variable") == "n_e"
        )
        checks["electron_function_ic_binding"] = (
            mp.get_parameter(text, f"ICs/{QF2_NE_IC}", "function")
            == QF2_NE_FUNCTION
        )

    checks["uniform_initial_O_preserved"] = (
        mp.get_parameter(text, "Functions/ic_w_O_transient", "expression") == "'0.10'"
    )
    checks["pure_o2_20_sccm_preserved"] = _top_level_float(text, "Q_sccm") == 20.0
    checks["pure_o2_molar_mass_preserved"] = _top_level_float(text, "M_inlet") == 0.032
    for species in ("O2s", "O2p", "O", "Om", "Op", "Os"):
        checks[f"zero_non_O2_inlet_flux:{species}"] = (
            _top_level_float(text, f"inlet_mdot_{species}_value") == 0.0
        )

    checks["physical_density_bridge_preserved"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_density_physical",
            "expression",
        )
        == "'${n_e_value}*ne_hat'"
    )
    actual_reference = _top_level_float(text, "n_e_value")
    checks["reference_density_positive"] = actual_reference > 0.0
    if expected_reference_m3 is not None:
        checks["qn_reference_preserved"] = math.isclose(
            actual_reference,
            expected_reference_m3,
            rel_tol=1.0e-14,
            abs_tol=0.0,
        )

    for path in EXPECTED_FEEDBACK_KERNELS:
        checks[f"feedback_potential:{path}"] = (
            mp.get_parameter(text, path, "potential") == FEEDBACK_POTENTIAL
        )

    for pp in ("n_e_min", "n_e_max", "n_e_avg", "r31_charge_integral"):
        checks[f"initial_final_observation:{pp}"] = tuple(
            mp.words(mp.get_parameter(text, f"Postprocessors/{pp}", "execute_on"))
        ) == ("INITIAL", "TIMESTEP_END")

    for name, value_type in (
        (QF2_CHARGE_MIN_PP, "min"),
        (QF2_CHARGE_MAX_PP, "max"),
    ):
        path = f"Postprocessors/{name}"
        checks[f"block:{path}"] = mb.has_block(text, path)
        if mb.has_block(text, path):
            checks[f"functor:{path}"] = (
                mp.get_parameter(text, path, "functor") == "charge_density"
            )
            checks[f"value_type:{path}"] = (
                mp.get_parameter(text, path, "value_type") == value_type
            )
            checks[f"execute_on:{path}"] = tuple(
                mp.words(mp.get_parameter(text, path, "execute_on"))
            ) == ("INITIAL", "TIMESTEP_END")

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }
