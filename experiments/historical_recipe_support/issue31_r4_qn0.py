"""Issue #31 R4-QN0 quasi-neutral initialization policy.

This qpx-free successor starts from the accepted R4-Q0 construction and changes
only the electron reference density.  The solver unknown remains normalized
(`n_e == n_hat`, initial condition 1.0); the dimensional bridge
`n_e_physical = n_e_value*n_e` is preserved.  The new `n_e_value` is computed
reproducibly from the frozen initial heavy-species charge ledger so that the
initial volume state is quasi-neutral before electrostatic transport feedback
is enabled.
"""
from __future__ import annotations

import math
import re
from typing import Any

from physics_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4 import audit_r4_q0_input, build_r4_q0_input

AVOGADRO = 6.02214076e23
GAS_CONSTANT = 8.31446

# Frozen species ordering/molar masses in the accepted oxygen heavy-state input.
INITIAL_SPECIES_MOLAR_MASS_KG_PER_MOL: dict[str, float] = {
    "O2": 0.032,
    "O2s": 0.032,
    "O2p": 0.032,
    "O": 0.016,
    "Om": 0.016,
    "Op": 0.016,
    "Os": 0.016,
}
INITIAL_CHARGE_NUMBER: dict[str, int] = {
    "O2p": 1,
    "Om": -1,
    "Op": 1,
}


class Issue31R4QN0Error(RuntimeError):
    pass


def _top_level_float(text: str, name: str) -> float:
    pattern = re.compile(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)")
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise Issue31R4QN0Error(
            f"expected one top-level scalar {name}, found {len(matches)}"
        )
    try:
        value = float(matches[0].strip())
    except ValueError as exc:
        raise Issue31R4QN0Error(
            f"top-level scalar {name} is not directly numeric: {matches[0]!r}"
        ) from exc
    if not math.isfinite(value):
        raise Issue31R4QN0Error(f"non-finite top-level scalar {name}={value}")
    return value


def _replace_top_level_assignment(text: str, name: str, value: str) -> str:
    pattern = re.compile(
        rf"(?m)^(?P<prefix>\s*{re.escape(name)}\s*=\s*)"
        rf"(?P<value>[^#\r\n]*?)"
        rf"(?P<suffix>\s*(?:#.*)?$)"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise Issue31R4QN0Error(
            f"expected one top-level assignment for {name}, found {len(matches)}"
        )
    match = matches[0]
    return (
        text[: match.start()]
        + match.group("prefix")
        + value
        + match.group("suffix")
        + text[match.end() :]
    )


def initial_quasi_neutral_reference(text: str) -> dict[str, Any]:
    """Derive initial quasi-neutral electron density from frozen heavy inputs."""
    mass_fractions = {
        species: _top_level_float(text, f"Yin_{species}")
        for species in INITIAL_SPECIES_MOLAR_MASS_KG_PER_MOL
    }
    total_y = sum(mass_fractions.values())
    if not math.isclose(total_y, 1.0, rel_tol=0.0, abs_tol=1.0e-12):
        raise Issue31R4QN0Error(f"initial mass fractions do not sum to one: {total_y}")

    inverse_molar_mass = sum(
        mass_fractions[species] / molar_mass
        for species, molar_mass in INITIAL_SPECIES_MOLAR_MASS_KG_PER_MOL.items()
    )
    mixture_molar_mass = 1.0 / inverse_molar_mass
    pressure = _top_level_float(text, "outlet_pressure")
    gas_temperature = _top_level_float(text, "T_g_value")
    if pressure <= 0.0 or gas_temperature <= 0.0:
        raise Issue31R4QN0Error("initial pressure and gas temperature must be positive")
    rho0 = pressure * mixture_molar_mass / (GAS_CONSTANT * gas_temperature)

    charged_heavy_number_density: dict[str, float] = {}
    signed_heavy_charge_number_density = 0.0
    for species, charge_number in INITIAL_CHARGE_NUMBER.items():
        number_density = (
            rho0
            * mass_fractions[species]
            * AVOGADRO
            / INITIAL_SPECIES_MOLAR_MASS_KG_PER_MOL[species]
        )
        charged_heavy_number_density[species] = number_density
        signed_heavy_charge_number_density += charge_number * number_density

    if signed_heavy_charge_number_density <= 0.0:
        raise Issue31R4QN0Error(
            "initial heavy charge ledger does not define a positive electron reference"
        )

    electron_reference = signed_heavy_charge_number_density
    closure = signed_heavy_charge_number_density - electron_reference
    return {
        "formula": (
            "rho0*N_A*(Yin_O2p/0.032 - Yin_Om/0.016 + Yin_Op/0.016)"
        ),
        "pressure_Pa": pressure,
        "gas_temperature_K": gas_temperature,
        "mixture_molar_mass_kg_per_mol": mixture_molar_mass,
        "initial_density_kg_per_m3": rho0,
        "mass_fractions": mass_fractions,
        "charged_heavy_number_density_m3": charged_heavy_number_density,
        "signed_heavy_charge_number_density_m3": signed_heavy_charge_number_density,
        "electron_reference_density_m3": electron_reference,
        "initial_charge_number_closure_m3": closure,
    }


def build_r4_qn0_input(base_text: str) -> tuple[str, dict[str, Any]]:
    """Build quasi-neutral, feedback-off R4-QN0 from the R4-Q0 construction."""
    text, q0_meta = build_r4_q0_input(base_text)
    old_reference = _top_level_float(text, "n_e_value")
    qn = initial_quasi_neutral_reference(text)
    new_reference = float(qn["electron_reference_density_m3"])
    text = _replace_top_level_assignment(text, "n_e_value", f"{new_reference:.17g}")

    audit = audit_r4_qn0_input(text)
    if audit["status"] != "PASS":
        raise Issue31R4QN0Error(
            f"constructed R4-QN0 input failed audit: {audit['failed_checks']}"
        )
    return text, {
        "issue": 31,
        "model": "R4_QN0_ALL_GROUND_QUASI_NEUTRAL_VOLUME_CHARGE_POISSON",
        "predecessor": q0_meta,
        "poisson_enabled": True,
        "electrostatic_feedback_enabled": False,
        "surface_accumulated_charge_enabled": False,
        "electron_solver_unknown": "n_e == n_hat",
        "electron_initial_condition": "normalized_1.0",
        "electron_physical_density": "n_e_physical == n_e_value*n_e",
        "original_r3_reference_density_m3": old_reference,
        "quasi_neutral_reference": qn,
        "reference_density_ratio_to_r3": new_reference / old_reference,
        "audit": audit,
    }


def audit_r4_qn0_input(text: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    q0 = audit_r4_q0_input(text)
    checks["r4_q0_contract_preserved"] = q0["status"] == "PASS"
    checks["normalized_electron_solver_ic"] = (
        mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    )
    checks["physical_density_bridge_preserved"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_density_physical",
            "expression",
        )
        == "'${n_e_value}*ne_hat'"
    )
    checks["transport_feedback_still_off"] = (
        mp.get_parameter(text, "FVKernels/n_e_drift", "potential")
        == "phi_prescribed"
    )

    qn = initial_quasi_neutral_reference(text)
    expected = float(qn["electron_reference_density_m3"])
    actual = _top_level_float(text, "n_e_value")
    checks["reference_density_matches_initial_heavy_charge"] = math.isclose(
        actual,
        expected,
        rel_tol=1.0e-14,
        abs_tol=0.0,
    )
    scale = max(abs(expected), 1.0)
    checks["initial_charge_number_closure"] = (
        abs(float(qn["initial_charge_number_closure_m3"])) / scale <= 1.0e-15
    )
    checks["reference_density_positive"] = actual > 0.0

    failed = sorted(key for key, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "q0_audit": q0,
        "quasi_neutral_reference": qn,
    }
