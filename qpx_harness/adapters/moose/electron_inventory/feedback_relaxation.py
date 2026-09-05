"""Reusable MOOSE construction for closed electron/bulk-Poisson feedback."""
from __future__ import annotations

from typing import Any

from qpx_harness.moose.input import MooseInput, MooseInputError
from qpx_harness.analysis.scale_audit import DEFAULT_PRESSURE

MEAN_ENERGY_EV = 5.73276
PERTURBATION_FRACTION = 1.0e-6
RELAX_TOL = 1.0e-4
INVENTORY_REL_TOL = 1.0e-6
CHARGE_REL_TOL = 1.0e-6
E_CHARGE = 1.602176634e-19
EPS0 = 8.8541878128e-12
DT_FEEDBACK_BASE = 1.0e-13
DT_FEEDBACK_SMALL = 1.0e-14
DT_FEEDBACK_LARGE = 1.0e-12

REQUIRED_COLUMNS = (
    "time",
    "n_min",
    "n_max",
    "inventory",
    "domain_volume",
    "r43_n_l2",
    "r43_phi_l2",
    "r43_phi_min",
    "r43_phi_max",
    "r43_phi_integral",
    "r43_charge_integral",
    "r43_background_inventory",
    "r43_charge_min",
    "r43_charge_max",
)

STATE_COLUMNS = (
    "r43_n_l2",
    "n_min",
    "n_max",
    "r43_phi_l2",
    "r43_phi_min",
    "r43_phi_max",
)


class Issue43FastRelaxationError(RuntimeError):
    pass


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def _insert_top_level_before(text: str, marker: str, block: str) -> str:
    needle = f"\n[{marker}]\n"
    if text.count(needle) != 1:
        raise Issue43FastRelaxationError(
            f"expected one top-level [{marker}] marker, found {text.count(needle)}"
        )
    payload = block if block.endswith("\n") else block + "\n"
    return text.replace(needle, "\n" + payload + needle, 1)


def build_fast_input(
    base_text: str,
    *,
    gas_temperature: float,
    electron_density: float,
    dt: float,
    end_time: float,
    radial_span: float,
) -> tuple[str, dict[str, Any]]:
    """Construct the Issue43 frozen-heavy electron/Poisson relaxation input."""
    if radial_span <= 0 or dt <= 0 or end_time <= 0:
        raise Issue43FastRelaxationError(
            "radial span, dt and end_time must be positive"
        )

    try:
        text, constants_meta = MooseInput(base_text).replace_parameters(
            "FunctorMaterials/electron_constants",
            {
                "prop_values": (
                    f"'{_fmt(MEAN_ENERGY_EV)} "
                    f"{_fmt(DEFAULT_PRESSURE)} "
                    f"{_fmt(gas_temperature)} 1.0'"
                )
            },
        )
        text, drift_meta = MooseInput(text).replace_parameters(
            "FVKernels/drift", {"potential": "potential_plasma"}
        )
        text, _ = MooseInput(text).insert_before_close(
            "Variables",
            """  [potential_plasma]
    type = MooseVariableFVReal
    initial_condition = 0
    block = plasma
  []""",
        )

        e_over_eps0 = E_CHARGE / EPS0
        background_expr = (
            f"{_fmt(electron_density)}*"
            f"(1.0+{_fmt(PERTURBATION_FRACTION)}*"
            f"cos(2*pi*x/{_fmt(radial_span)}))"
        )
        text, _ = MooseInput(text).insert_before_close(
            "FunctorMaterials",
            f"""  [r43_background]
    type = ADParsedFunctorMaterial
    property_name = r43_positive_background
    expression = '{background_expr}'
    block = plasma
  []
  [r43_relative_permittivity]
    type = ADGenericFunctorMaterial
    prop_names = 'r43_relative_permittivity'
    prop_values = '1.0'
    block = plasma
  []
  [r43_charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = r43_charge_number_density
    functor_names = 'r43_positive_background n_e'
    functor_symbols = 'nb nelec'
    expression = 'nb-nelec'
    block = plasma
  []
  [r43_charge_density]
    type = ADParsedFunctorMaterial
    property_name = r43_charge_density
    functor_names = 'r43_charge_number_density'
    functor_symbols = 'qnum'
    expression = '{_fmt(E_CHARGE)}*qnum'
    block = plasma
  []
  [r43_poisson_source]
    type = ADParsedFunctorMaterial
    property_name = r43_poisson_source
    functor_names = 'r43_charge_number_density'
    functor_symbols = 'qnum'
    expression = '{_fmt(e_over_eps0)}*qnum'
    block = plasma
  []""",
        )
        text, _ = MooseInput(text).insert_before_close(
            "FVKernels",
            """  [r43_phi_diffusion]
    type = FVDiffusion
    variable = potential_plasma
    coeff = r43_relative_permittivity
    block = plasma
  []
  [r43_phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = r43_poisson_source
    coef = 1
    block = plasma
  []""",
        )
        text, _ = MooseInput(text).insert_before_close(
            "Postprocessors",
            """  [r43_n_l2]
    type = ElementL2Norm
    variable = n_e
    block = plasma
  []
  [r43_phi_l2]
    type = ElementL2Norm
    variable = potential_plasma
    block = plasma
  []
  [r43_phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = min
    block = plasma
  []
  [r43_phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    block = plasma
  []
  [r43_phi_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = potential_plasma
    block = plasma
  []
  [r43_charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = r43_charge_density
    block = plasma
  []
  [r43_background_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = r43_positive_background
    block = plasma
  []
  [r43_charge_min]
    type = ADElementExtremeFunctorValue
    functor = r43_charge_density
    value_type = min
    block = plasma
  []
  [r43_charge_max]
    type = ADElementExtremeFunctorValue
    functor = r43_charge_density
    value_type = max
    block = plasma
  []""",
        )
        text, execution_meta = MooseInput(text).replace_parameters(
            "Executioner",
            {
                "dt": _fmt(dt),
                "end_time": _fmt(end_time),
                "compute_scaling_once": "true",
            },
        )
    except MooseInputError as exc:
        raise Issue43FastRelaxationError(
            f"fast-block input transform failed: {exc}"
        ) from exc

    fvbc = """[FVBCs]
  [r43_phi_plasma_metal]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_metal
    value = 0
  []
  [r43_phi_plasma_electrode]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_electrode
    value = 0
  []
  [r43_phi_plasma_right]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_right
    value = 0
  []
  [r43_phi_inlet]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = inlet
    value = 0
  []
  [r43_phi_outlet]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = outlet
    value = 0
  []
[]
"""
    text = _insert_top_level_before(text, "Postprocessors", fvbc)

    if "potential = phi_prescribed" in text:
        raise Issue43FastRelaxationError(
            "prescribed-field electron drift remained active"
        )
    required = (
        "potential = potential_plasma",
        "r43_positive_background",
        "r43_phi_diffusion",
        "r43_phi_charge_source",
        "r43_phi_plasma_metal",
        "r43_n_l2",
        "r43_phi_l2",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise Issue43FastRelaxationError(
            "generated fast-block input is missing: " + ", ".join(missing)
        )

    return text, {
        "gas_temperature_K": gas_temperature,
        "electron_density_m-3": electron_density,
        "dt_s": dt,
        "end_time_s": end_time,
        "radial_span_m": radial_span,
        "background_perturbation_fraction": PERTURBATION_FRACTION,
        "diagnostic_state": "frozen quasi-neutral positive background with a small reactor-scale charge perturbation",
        "electron_constants_change": constants_meta,
        "drift_change": drift_meta,
        "executioner_change": execution_meta,
    }

