"""Issue #91 R3 heavy + electron prescribed-field composition policy.

This module is deliberately qpx-free. It composes already accepted heavy and
electron transport semantics into one real-QVT pre-Poisson input. Framework
execution remains local and outside pytest.
"""
from __future__ import annotations

import math
import re
from typing import Any

from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp

ELECTRON_DT = 1.0e-8
MEAN_ELECTRON_ENERGY_EV = 5.73276
BOUNDARIES_TO_AVOID = (
    "inlet outlet plasma_electrode plasma_metal plasma_right "
    "plasma_cover plasma_wafer plasma_focus_ring"
)


class Issue91R3Error(RuntimeError):
    pass


def _replace_top_level_assignment(text: str, name: str, value: str) -> str:
    pattern = re.compile(
        rf"(?m)^(?P<prefix>\s*{re.escape(name)}\s*=\s*)"
        rf"(?P<value>[^#\r\n]*?)"
        rf"(?P<suffix>\s*(?:#.*)?$)"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise Issue91R3Error(
            f"expected exactly one top-level assignment for {name}, found {len(matches)}"
        )
    match = matches[0]
    return text[: match.start()] + match.group("prefix") + value + match.group("suffix") + text[match.end() :]


def _top_level_float(text: str, name: str) -> float:
    pattern = re.compile(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)")
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise Issue91R3Error(f"cannot resolve unique top-level scalar {name}")
    value = float(matches[0].strip())
    if not math.isfinite(value):
        raise Issue91R3Error(f"non-finite top-level scalar {name}={value}")
    return value


def _insert_r3_blocks(text: str) -> str:
    mb.require_absent(text, "Variables/n_e")
    mb.require_absent(text, "FunctorMaterials/electron_constants")
    mb.require_absent(text, "FunctorMaterials/electron_transport")
    mb.require_absent(text, "FVKernels/n_e_time")
    mb.require_absent(text, "FVKernels/n_e_diffusion")
    mb.require_absent(text, "FVKernels/n_e_drift")

    text = mb.insert_child_block(
        text,
        "Variables",
        """  [n_e]
    type = MooseVariableFVReal
    initial_condition = ${n_e_value}
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [electron_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en carrier_one'
    prop_values = '{MEAN_ELECTRON_ENERGY_EV} 1.0'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [electron_transport]
    type = QPXElectronTransportLookupMaterial
    property_table_file = electron_moments.txt
    mean_energy = mean_en
    pressure = p
    gas_temperature = T_g
    bounds_policy = error
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        """  [n_e_time]
    type = FVTimeKernel
    variable = n_e
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        """  [n_e_diffusion]
    type = FVDiffusion
    variable = n_e
    coeff = electron_diffusion
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [n_e_drift]
    type = QPXFVElectrostaticDrift
    variable = n_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = '{BOUNDARIES_TO_AVOID}'
    block = plasma
  []""",
    )

    postprocessors = (
        ("n_e_avg", "ElementAverageFunctorPostprocessor", "    functor = n_e\n    block = plasma"),
        ("n_e_min", "ADElementExtremeFunctorValue", "    functor = n_e\n    value_type = min\n    block = plasma"),
        ("n_e_max", "ADElementExtremeFunctorValue", "    functor = n_e\n    value_type = max\n    block = plasma"),
        ("n_e_inventory", "ADElementIntegralFunctorPostprocessor", "    functor = n_e\n    block = plasma"),
        ("domain_volume", "ADElementIntegralFunctorPostprocessor", "    functor = carrier_one\n    block = plasma"),
        ("electron_mobility_avg", "ElementAverageFunctorPostprocessor", "    functor = electron_mobility\n    block = plasma"),
        ("electron_diffusion_avg", "ElementAverageFunctorPostprocessor", "    functor = electron_diffusion\n    block = plasma"),
        ("electron_pressure_avg", "ElementAverageFunctorPostprocessor", "    functor = p\n    block = plasma"),
        ("electron_gas_temperature_avg", "ElementAverageFunctorPostprocessor", "    functor = T_g\n    block = plasma"),
    )
    for name, type_name, body in postprocessors:
        mb.require_absent(text, f"Postprocessors/{name}")
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"  [{name}]\n    type = {type_name}\n{body}\n  []",
        )
    return text


def build_r3_input(base_text: str, *, field_strength: float) -> tuple[str, dict[str, Any]]:
    if not math.isfinite(field_strength) or field_strength < 0.0:
        raise Issue91R3Error("field_strength must be finite and non-negative")
    for forbidden in ("potential_plasma", "r30_phi_diffusion", "r30_phi_charge_source"):
        if forbidden in base_text:
            raise Issue91R3Error(f"heavy base unexpectedly contains Poisson state: {forbidden}")

    text = _replace_top_level_assignment(base_text, "E0_migration", f"{field_strength:.17g}")
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/state_constants",
        "prop_names",
        "'T_g T_e mu_flow'",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/state_constants",
        "prop_values",
        "'${T_g_value} ${T_e_value} ${mu_const}'",
    )
    text = _insert_r3_blocks(text)
    text = mp.upsert_parameter(text, "Executioner", "dt", "1.0e-8")
    text = mp.upsert_parameter(text, "Executioner", "end_time", "1.0e-8")

    audit = audit_r3_input(text, expected_field=field_strength)
    if audit["status"] != "PASS":
        raise Issue91R3Error(f"constructed R3 input failed audit: {audit['failed_checks']}")
    return text, {
        "issue": 91,
        "model": "R3_HEAVY_PLUS_ELECTRON_PRESCRIBED_FIELD",
        "field_strength": field_strength,
        "common_timestep": ELECTRON_DT,
        "electron_initial_condition": "uniform_n_e_value",
        "electron_pressure": "p",
        "electron_gas_temperature": "T_g",
        "electron_mean_energy_eV": MEAN_ELECTRON_ENERGY_EV,
        "poisson_enabled": False,
        "scientific_evr_consumed_by_construction": 0,
        "audit": audit,
    }


def audit_r3_input(text: str, *, expected_field: float) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    required_blocks = (
        "Variables/n_e",
        "FunctorMaterials/heavy_transport",
        "FunctorMaterials/electron_transport",
        "FVKernels/n_e_time",
        "FVKernels/n_e_diffusion",
        "FVKernels/n_e_drift",
        "FVKernels/O2p_electrostatic_drift",
        "FVKernels/O2p_heavy_mass_em_correction",
        "Postprocessors/n_e_inventory",
        "Postprocessors/domain_volume",
    )
    for path in required_blocks:
        checks[f"block:{path}"] = mb.has_block(text, path)

    state_names = mp.words(
        mp.get_parameter(text, "FunctorMaterials/state_constants", "prop_names")
    )
    checks["no_constant_n_e_provider"] = "n_e" not in state_names
    checks["uniform_accepted_qvt_electron_ic"] = (
        mp.get_parameter(text, "Variables/n_e", "initial_condition") == "${n_e_value}"
    )
    checks["heavy_uses_live_n_e"] = (
        mp.get_parameter(
            text, "FunctorMaterials/heavy_transport", "electron_number_density"
        )
        == "n_e"
    )
    checks["electron_pressure_is_live_p"] = (
        mp.get_parameter(text, "FunctorMaterials/electron_transport", "pressure") == "p"
    )
    checks["electron_temperature_is_live_Tg"] = (
        mp.get_parameter(
            text, "FunctorMaterials/electron_transport", "gas_temperature"
        )
        == "T_g"
    )
    checks["shared_electron_potential"] = (
        mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "phi_prescribed"
    )
    checks["shared_heavy_potential"] = (
        mp.get_parameter(text, "FVKernels/O2p_electrostatic_drift", "potential")
        == "phi_prescribed"
    )
    checks["electron_dt"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "dt") or "nan"),
        ELECTRON_DT,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    checks["one_positive_step"] = math.isclose(
        float(mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        ELECTRON_DT,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    checks["field_strength"] = math.isclose(
        _top_level_float(text, "E0_migration"),
        expected_field,
        rel_tol=0.0,
        abs_tol=1.0e-18,
    )
    checks["poisson_absent"] = not any(
        token in text
        for token in ("potential_plasma", "r30_phi_diffusion", "r30_phi_charge_source")
    )
    failed = sorted(key for key, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }
