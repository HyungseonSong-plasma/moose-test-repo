"""Issue #31 R4-QF1 closed electrostatic feedback policy.

R4-QF1 is the first self-consistent solved-Poisson successor to R4-QN0. It
preserves the quasi-neutral dimensional electron reference and the normalized
solver unknown, then connects solved `potential_plasma` to every charged
particle electrostatic drift operator and every heavy-species
mass-electromigration correction operator already present in accepted R3.

The QF1 initial plasma removes the historical neutral-O spatial perturbation so
the initial composition is uniform and consistent with the quasi-neutral
reference ledger. The QF1 feed is physically explicit: 20 sccm of pure O2.
Feed composition remains separate from the ionized initial plasma composition.
"""
from __future__ import annotations

import math
import re
from typing import Any

from physics_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4_qn0 import (
    _replace_top_level_assignment,
    _top_level_float,
    build_r4_qn0_input,
)

FEEDBACK_POTENTIAL = "potential_plasma"
ELECTROSTATIC_DRIFT_TYPE = "QPXFVElectrostaticDrift"
HEAVY_EM_CORRECTION_TYPE = "QPXFVHeavyMassElectromigrationCorrection"
PURE_O2_FEED_SCCM = 20.0
PURE_O2_MOLAR_MASS_KG_PER_MOL = 0.032
UNIFORM_INITIAL_O_MASS_FRACTION = 0.10
SOLVED_NON_O2_INLET_SPECIES = ("O2s", "O2p", "O", "Om", "Op", "Os")
EXPECTED_DRIFT_KERNELS = (
    "FVKernels/O2p_electrostatic_drift",
    "FVKernels/Om_electrostatic_drift",
    "FVKernels/Op_electrostatic_drift",
    "FVKernels/n_e_drift",
)
EXPECTED_HEAVY_EM_CORRECTION_KERNELS = (
    "FVKernels/O2s_heavy_mass_em_correction",
    "FVKernels/O2p_heavy_mass_em_correction",
    "FVKernels/O_heavy_mass_em_correction",
    "FVKernels/Om_heavy_mass_em_correction",
    "FVKernels/Op_heavy_mass_em_correction",
    "FVKernels/Os_heavy_mass_em_correction",
)
EXPECTED_FEEDBACK_KERNELS = EXPECTED_DRIFT_KERNELS + EXPECTED_HEAVY_EM_CORRECTION_KERNELS

ELECTROSTATIC_BOUNDARIES_TO_AVOID = (
    "inlet",
    "outlet",
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
CHARGED_HEAVY_C2 = {
    "O2p": {"z": 1, "molar_mass_kg_per_mol": 0.032},
    "Om": {"z": -1, "molar_mass_kg_per_mol": 0.016},
    "Op": {"z": 1, "molar_mass_kg_per_mol": 0.016},
}


class Issue31R4QF1Error(RuntimeError):
    pass


def _has_top_level_assignment(text: str, name: str) -> bool:
    return bool(re.search(rf"(?m)^\s*{re.escape(name)}\s*=", text))


def _remove_top_level_assignment(text: str, name: str) -> str:
    pattern = re.compile(rf"(?m)^\s*{re.escape(name)}\s*=\s*[^#\r\n]*(?:#.*)?(?:\r?\n|$)")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise Issue31R4QF1Error(
            f"expected one top-level assignment for removal {name}, found {len(matches)}"
        )
    match = matches[0]
    return text[: match.start()] + text[match.end() :]


def _feedback_kernel_paths(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    drift: list[str] = []
    correction: list[str] = []
    for path in mp.direct_children(text, "FVKernels"):
        typ = mp.get_parameter(text, path, "type")
        if typ == ELECTROSTATIC_DRIFT_TYPE:
            drift.append(path)
        elif typ == HEAVY_EM_CORRECTION_TYPE:
            correction.append(path)
    return tuple(sorted(drift)), tuple(sorted(correction))


def _uniformize_initial_plasma(text: str) -> tuple[str, dict[str, Any]]:
    """Remove the historical neutral-O perturbation from the R4 initial state."""
    old_expression = mp.get_parameter(text, "Functions/ic_w_O_transient", "expression")
    expected_initial_o = _top_level_float(text, "Yin_O")
    if not math.isclose(
        expected_initial_o,
        UNIFORM_INITIAL_O_MASS_FRACTION,
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        raise Issue31R4QF1Error(
            f"unexpected nominal initial O mass fraction {expected_initial_o}"
        )
    text = mp.upsert_parameter(
        text,
        "Functions/ic_w_O_transient",
        "expression",
        f"'{UNIFORM_INITIAL_O_MASS_FRACTION:.2f}'",
    )
    return text, {
        "neutral_O_spatial_perturbation": False,
        "w_O_initial_mass_fraction": UNIFORM_INITIAL_O_MASS_FRACTION,
        "w_O_initial_condition": "uniform FunctionIC",
        "previous_w_O_expression": old_expression,
        "quasi_neutral_intent": (
            "uniform heavy composition + uniform p/Tg + n_e_hat=1; actual t=0 "
            "integrated charge is still measured rather than assumed"
        ),
    }


def _apply_pure_o2_inlet(text: str) -> tuple[str, dict[str, Any]]:
    """Separate physical pure-O2 feed from the ionized initial plasma state."""
    old_q_sccm = _top_level_float(text, "Q_sccm")
    initial_mass_fractions = {
        species: _top_level_float(text, f"Yin_{species}")
        for species in ("O2", "O2s", "O2p", "O", "Om", "Op", "Os")
    }

    text = _replace_top_level_assignment(text, "Q_sccm", "20")
    text = _replace_top_level_assignment(text, "M_inlet", "0.032")
    for species in SOLVED_NON_O2_INLET_SPECIES:
        text = _replace_top_level_assignment(text, f"inlet_mdot_{species}_value", "0")

    # Yin_O2 and Yin_O were historically dual-purpose feed/initial aliases.
    # After QN-reference construction and uniform-IC construction they have no
    # runtime consumer. Preserve their values in metadata, then remove the
    # unused aliases rather than weakening MOOSE's unused-parameter check.
    for name in ("Yin_O2", "Yin_O"):
        text = _remove_top_level_assignment(text, name)

    return text, {
        "feed": "pure O2",
        "flow_sccm": PURE_O2_FEED_SCCM,
        "molar_mass_kg_per_mol": PURE_O2_MOLAR_MASS_KG_PER_MOL,
        "O2_feed_mass_fraction": 1.0,
        "non_O2_feed_mass_fractions": {
            species: 0.0 for species in SOLVED_NON_O2_INLET_SPECIES
        },
        "total_mass_flux_owner": "Postprocessors/inlet_mdot -> FVBCs/inlet_mass",
        "non_O2_scalar_flux_owners": {
            species: f"Postprocessors/inlet_mdot_{species} -> FVBCs/inlet_{species}"
            for species in SOLVED_NON_O2_INLET_SPECIES
        },
        "previous_flow_sccm": old_q_sccm,
        "initial_plasma_mass_fractions_preserved": initial_mass_fractions,
        "initial_plasma_composition_is_feed_composition": False,
        "removed_unused_initial_aliases": ["Yin_O2", "Yin_O"],
    }


def _enable_closed_feedback(text: str) -> tuple[str, dict[str, Any]]:
    drift, correction = _feedback_kernel_paths(text)
    if drift != tuple(sorted(EXPECTED_DRIFT_KERNELS)):
        raise Issue31R4QF1Error(
            f"unexpected electrostatic drift kernel set: {drift}; "
            f"expected {tuple(sorted(EXPECTED_DRIFT_KERNELS))}"
        )
    if correction != tuple(sorted(EXPECTED_HEAVY_EM_CORRECTION_KERNELS)):
        raise Issue31R4QF1Error(
            f"unexpected heavy EM correction kernel set: {correction}; "
            f"expected {tuple(sorted(EXPECTED_HEAVY_EM_CORRECTION_KERNELS))}"
        )

    evidence: dict[str, Any] = {"kernels": {}}
    for path in EXPECTED_FEEDBACK_KERNELS:
        old = mp.get_parameter(text, path, "potential")
        if old != "phi_prescribed":
            raise Issue31R4QF1Error(
                f"feedback predecessor mismatch at {path}/potential={old!r}"
            )
        boundary_tokens = tuple(mp.words(mp.get_parameter(text, path, "boundaries_to_avoid")))
        if boundary_tokens != ELECTROSTATIC_BOUNDARIES_TO_AVOID:
            raise Issue31R4QF1Error(
                f"unexpected electrostatic boundary policy at {path}: {boundary_tokens}"
            )
        text = mp.upsert_parameter(text, path, "potential", FEEDBACK_POTENTIAL)
        evidence["kernels"][path] = {
            "old_potential": old,
            "new_potential": FEEDBACK_POTENTIAL,
            "boundaries_to_avoid": list(boundary_tokens),
        }

    evidence["electron_boundary_current_policy"] = (
        "zero explicit external electron current: electron drift avoids all physical "
        "plasma boundaries, FVDiffusion retains natural zero-flux boundary behavior, "
        "and no electron bulk-advection boundary operator is enabled"
    )
    evidence["charged_heavy_boundary_current_policy"] = (
        "electrostatic drift/correction avoid physical boundaries; C2 external heavy "
        "charge current is reconstructed from charged-species inlet/outlet advective "
        "mass-flux postprocessors"
    )
    return text, evidence


def build_r4_qf1_input(base_text: str) -> tuple[str, dict[str, Any]]:
    """Build full charged-particle electrostatic feedback from accepted QN0."""
    text, qn0_meta = build_r4_qn0_input(base_text)
    expected_reference = float(
        qn0_meta["quasi_neutral_reference"]["electron_reference_density_m3"]
    )
    text, initial_plasma = _uniformize_initial_plasma(text)
    text, inlet = _apply_pure_o2_inlet(text)
    text, feedback = _enable_closed_feedback(text)
    audit = audit_r4_qf1_input(text, expected_reference_m3=expected_reference)
    if audit["status"] != "PASS":
        raise Issue31R4QF1Error(
            f"constructed R4-QF1 input failed audit: {audit['failed_checks']}"
        )
    return text, {
        "issue": 31,
        "model": "R4_QF1_ALL_GROUND_CLOSED_ELECTROSTATIC_FEEDBACK",
        "predecessor": qn0_meta,
        "poisson_enabled": True,
        "quasi_neutral_initialization": True,
        "electrostatic_feedback_enabled": True,
        "surface_accumulated_charge_enabled": False,
        "volumetric_reactions_enabled": False,
        "secondary_emission_enabled": False,
        "electron_solver_unknown": "n_e == n_hat",
        "electron_physical_density": "n_e_physical == n_e_value*n_e",
        "initial_plasma": initial_plasma,
        "inlet": inlet,
        "feedback_potential": FEEDBACK_POTENTIAL,
        "feedback": feedback,
        "c2_boundary_species": CHARGED_HEAVY_C2,
        "c2_time_discretization": "implicit Euler: Q_boundary = dt * I_boundary(t_{n+1})",
        "audit": audit,
    }


def audit_r4_qf1_input(
    text: str,
    *,
    expected_reference_m3: float | None = None,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    checks["normalized_electron_solver_ic"] = (
        mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    )
    checks["uniform_initial_O"] = (
        mp.get_parameter(text, "Functions/ic_w_O_transient", "expression") == "'0.10'"
    )
    checks["physical_density_bridge_preserved"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_density_physical",
            "expression",
        )
        == "'${n_e_value}*ne_hat'"
    )
    checks["heavy_uses_physical_n_e"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/heavy_transport",
            "electron_number_density",
        )
        == "n_e_physical"
    )
    checks["electron_lookup_live_p"] = (
        mp.get_parameter(text, "FunctorMaterials/electron_transport", "pressure") == "p"
    )
    checks["electron_lookup_live_Tg"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_transport",
            "gas_temperature",
        )
        == "T_g"
    )
    checks["charge_uses_physical_electron_density"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/r31_charge_density",
            "electron_density",
        )
        == "n_e_physical"
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

    checks["poisson_diffusion_connected"] = (
        mp.get_parameter(text, "FVKernels/r31_phi_diffusion", "variable")
        == "potential_plasma"
        and mp.get_parameter(text, "FVKernels/r31_phi_diffusion", "coeff")
        == "relative_permittivity"
    )
    checks["poisson_charge_connected"] = (
        mp.get_parameter(text, "FVKernels/r31_phi_charge_source", "v")
        == "poisson_charge_source"
    )
    checks["all_ground_phi"] = (
        mp.get_parameter(text, "FVBCs/r31_phi_ground_all", "variable")
        == "potential_plasma"
        and mp.get_parameter(text, "FVBCs/r31_phi_ground_all", "value") == "0"
    )

    checks["pure_o2_feed_flow_sccm"] = _top_level_float(text, "Q_sccm") == 20.0
    checks["pure_o2_feed_molar_mass"] = (
        _top_level_float(text, "M_inlet") == PURE_O2_MOLAR_MASS_KG_PER_MOL
    )
    for species in SOLVED_NON_O2_INLET_SPECIES:
        checks[f"zero_non_O2_inlet_flux:{species}"] = (
            _top_level_float(text, f"inlet_mdot_{species}_value") == 0.0
        )
    checks["unused_Yin_O2_removed"] = not _has_top_level_assignment(text, "Yin_O2")
    checks["unused_Yin_O_removed"] = not _has_top_level_assignment(text, "Yin_O")
    checks["initial_plasma_remains_ionized"] = any(
        _top_level_float(text, f"Yin_{species}") > 0.0
        for species in ("O2p", "Om", "Op")
    )

    drift, correction = _feedback_kernel_paths(text)
    checks["exact_drift_kernel_set"] = drift == tuple(sorted(EXPECTED_DRIFT_KERNELS))
    checks["exact_heavy_em_correction_kernel_set"] = correction == tuple(
        sorted(EXPECTED_HEAVY_EM_CORRECTION_KERNELS)
    )
    for path in EXPECTED_FEEDBACK_KERNELS:
        checks[f"feedback_potential:{path}"] = (
            mp.get_parameter(text, path, "potential") == FEEDBACK_POTENTIAL
        )
        checks[f"boundary_policy:{path}"] = tuple(
            mp.words(mp.get_parameter(text, path, "boundaries_to_avoid"))
        ) == ELECTROSTATIC_BOUNDARIES_TO_AVOID

    checks["no_feedback_kernel_uses_prescribed_phi"] = all(
        mp.get_parameter(text, path, "potential") != "phi_prescribed"
        for path in EXPECTED_FEEDBACK_KERNELS
    )

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }
