"""Issue #31 R4-Q0 all-ground solved-Poisson composition policy.

This module is qpx-free. It starts from the accepted Issue #91 R3-E0
transport state, promotes legacy material permittivity metadata to canonical
block-scoped functors, adds physical volume charge and a solved plasma
potential, and deliberately leaves electrostatic transport feedback disabled
so the first Poisson/Gauss-law discriminator is attributable.

Surface accumulated charge (sigma_s) is out of scope for this phase.
"""
from __future__ import annotations

from typing import Any

from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from recipes.issue91_r3 import audit_r3_input, build_r3_input

EPSILON_0 = 8.8541878128e-12
PLASMA_ALL_BOUNDARY = "r31_plasma_all_boundary"
MESH_INPUT_BEFORE_R4 = "bottom_electrode"

# Canonical electrostatic material contract for the current qvt topology.
# The values originate in the accepted R3 BaseMaterial metadata, but R4 removes
# those legacy parameters from the generated candidate and exposes one common
# functor name, relative_permittivity, over disjoint material blocks.
PERMITTIVITY_MATERIALS: dict[str, tuple[float, tuple[str, ...]]] = {
    "vacuum": (1.0, ("vacuum",)),
    "outer": (1.0, ("top", "right", "bottom")),
    "cover": (3.6, ("cover",)),
    "electrode": (1.0, ("electrode",)),
    "wafer": (12.5, ("wafer",)),
    "focus_ring": (8.0, ("focus_ring",)),
    "plasma": (1.0, ("plasma",)),
}


class Issue31R4Error(RuntimeError):
    pass


def _block_value(blocks: tuple[str, ...]) -> str:
    value = " ".join(blocks)
    return value if len(blocks) == 1 else f"'{value}'"


def _migrate_relative_permittivity_to_functors(
    text: str,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Replace legacy BaseMaterial permittivity metadata with block functors."""
    evidence: dict[str, dict[str, Any]] = {}
    for material, (expected_value, expected_blocks) in PERMITTIVITY_MATERIALS.items():
        material_path = f"Materials/{material}"
        if not mb.has_block(text, material_path):
            raise Issue31R4Error(f"missing accepted material block {material_path}")

        raw_value = mp.get_parameter(text, material_path, "relative_permittivity")
        if raw_value is None:
            raise Issue31R4Error(
                f"missing legacy {material_path}/relative_permittivity before migration"
            )
        token = mp.unquote(raw_value)
        try:
            value = float(token or "nan")
        except ValueError as exc:
            raise Issue31R4Error(
                f"non-numeric {material_path}/relative_permittivity={raw_value!r}"
            ) from exc
        if abs(value - expected_value) > 1.0e-15:
            raise Issue31R4Error(
                f"unexpected {material_path}/relative_permittivity={value}; "
                f"expected {expected_value}"
            )

        explicit_blocks = tuple(mp.words(mp.get_parameter(text, material_path, "block")))
        if explicit_blocks:
            blocks = explicit_blocks
        else:
            material_name = mp.unquote(
                mp.get_parameter(text, material_path, "material_name")
            )
            blocks = (material_name or material,)
        if blocks != expected_blocks:
            raise Issue31R4Error(
                f"unexpected block scope for {material_path}: {blocks}; "
                f"expected {expected_blocks}"
            )

        functor_name = f"permittivity_{material}"
        functor_path = f"FunctorMaterials/{functor_name}"
        mb.require_absent(text, functor_path)
        text = mp.remove_parameter(text, material_path, "relative_permittivity")
        text = mb.insert_child_block(
            text,
            "FunctorMaterials",
            f"""  [{functor_name}]
    type = ADGenericFunctorMaterial
    prop_names = 'relative_permittivity'
    prop_values = '{token}'
    block = {_block_value(blocks)}
  []""",
        )
        evidence[material] = {
            "legacy_material_path": material_path,
            "functor_path": functor_path,
            "property": "relative_permittivity",
            "value": value,
            "blocks": list(blocks),
        }
    return text, evidence


def _insert_r4_q0_blocks(text: str) -> str:
    mb.require_absent(text, f"Mesh/{PLASMA_ALL_BOUNDARY}")
    if not mb.has_block(text, f"Mesh/{MESH_INPUT_BEFORE_R4}"):
        raise Issue31R4Error(
            f"accepted qvt mesh chain missing Mesh/{MESH_INPUT_BEFORE_R4}"
        )
    text = mb.insert_child_block(
        text,
        "Mesh",
        f"""  [{PLASMA_ALL_BOUNDARY}]
    type = SideSetsAroundSubdomainGenerator
    input = {MESH_INPUT_BEFORE_R4}
    block = plasma
    new_boundary = {PLASMA_ALL_BOUNDARY}
  []""",
    )

    for path in (
        "Variables/potential_plasma",
        "FunctorMaterials/r31_charge_density",
        "FVKernels/r31_phi_diffusion",
        "FVKernels/r31_phi_charge_source",
        "Postprocessors/r31_charge_integral",
        "Postprocessors/r31_phi_min",
        "Postprocessors/r31_phi_max",
        "Postprocessors/r31_gauss_flux_reduced",
        "Postprocessors/r31_gauss_flux_charge",
    ):
        mb.require_absent(text, path)

    text = mb.insert_child_block(
        text,
        "Variables",
        """  [potential_plasma]
    type = MooseVariableFVReal
    initial_condition = 0
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [r31_charge_density]
    type = QPXPlasmaChargeDensityMaterial
    density = rho_mat
    electron_density = n_e_physical
    ion_ids = 'O2p Om Op'
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_molar_masses = '0.032 0.016 0.016'
    ion_charges = '1 -1 1'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        """  [r31_phi_diffusion]
    type = FVDiffusion
    variable = potential_plasma
    coeff = relative_permittivity
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        """  [r31_phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = poisson_charge_source
    coef = 1
    block = plasma
  []""",
    )

    mb.require_absent(text, "FVBCs/r31_phi_ground_all")
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [r31_phi_ground_all]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = {PLASMA_ALL_BOUNDARY}
    value = 0
  []""",
    )

    postprocessors = (
        """  [r31_charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density
    block = plasma
  []""",
        """  [r31_phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = min
    block = plasma
  []""",
        """  [r31_phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    block = plasma
  []""",
        f"""  [r31_gauss_flux_reduced]
    type = SideDiffusiveFluxIntegral
    variable = potential_plasma
    boundary = {PLASMA_ALL_BOUNDARY}
    functor_diffusivity = relative_permittivity
  []""",
        f"""  [r31_gauss_flux_charge]
    type = ScalePostprocessor
    value = r31_gauss_flux_reduced
    scaling_factor = {EPSILON_0:.17g}
  []""",
    )
    for block in postprocessors:
        text = mb.insert_child_block(text, "Postprocessors", block)

    return text


def build_r4_q0_input(base_text: str) -> tuple[str, dict[str, Any]]:
    """Build the first R4 solved-Poisson discriminator from accepted R3-E0."""
    text, r3_meta = build_r3_input(base_text, field_strength=0.0)
    text, permittivity = _migrate_relative_permittivity_to_functors(text)
    text = _insert_r4_q0_blocks(text)
    audit = audit_r4_q0_input(text)
    if audit["status"] != "PASS":
        raise Issue31R4Error(
            f"constructed R4-Q0 input failed audit: {audit['failed_checks']}"
        )
    return text, {
        "issue": 31,
        "model": "R4_Q0_ALL_GROUND_VOLUME_CHARGE_POISSON",
        "r3_control": r3_meta,
        "poisson_enabled": True,
        "electrostatic_feedback_enabled": False,
        "surface_accumulated_charge_enabled": False,
        "electrostatic_boundary_policy": "phi=0 on complete boundary of plasma subdomain",
        "ground_boundary": PLASMA_ALL_BOUNDARY,
        "charge_electron_density": "n_e_physical",
        "relative_permittivity_provider": "block-scoped functor relative_permittivity",
        "relative_permittivity_migration": permittivity,
        "gauss_law_observables": {
            "volume_charge_C": "r31_charge_integral",
            "boundary_displacement_flux_C": "r31_gauss_flux_charge",
        },
        "audit": audit,
    }


def audit_r4_q0_input(text: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    r3 = audit_r3_input(text, expected_field=0.0)
    # audit_r3_input intentionally rejects Poisson tokens, so only carry the
    # R3 invariants that remain meaningful after R4 construction.
    checks["normalized_electron_solver_ic"] = (
        mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
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
    checks["r3_zero_field_preserved"] = r3["checks"].get("field_strength", False)

    required_blocks = (
        "Variables/potential_plasma",
        "FunctorMaterials/r31_charge_density",
        "FVKernels/r31_phi_diffusion",
        "FVKernels/r31_phi_charge_source",
        "Postprocessors/r31_charge_integral",
        "Postprocessors/r31_gauss_flux_reduced",
        "Postprocessors/r31_gauss_flux_charge",
    )
    for path in required_blocks:
        checks[f"block:{path}"] = mb.has_block(text, path)

    for material, (expected_value, expected_blocks) in PERMITTIVITY_MATERIALS.items():
        material_path = f"Materials/{material}"
        functor_path = f"FunctorMaterials/permittivity_{material}"
        checks[f"permittivity_legacy_removed:{material}"] = (
            mp.get_parameter(text, material_path, "relative_permittivity") is None
        )
        checks[f"permittivity_functor_exists:{material}"] = mb.has_block(
            text, functor_path
        )
        if mb.has_block(text, functor_path):
            checks[f"permittivity_property:{material}"] = mp.words(
                mp.get_parameter(text, functor_path, "prop_names")
            ) == ["relative_permittivity"]
            value_tokens = mp.words(mp.get_parameter(text, functor_path, "prop_values"))
            try:
                functor_value = float(value_tokens[0]) if len(value_tokens) == 1 else float("nan")
            except ValueError:
                functor_value = float("nan")
            checks[f"permittivity_value:{material}"] = (
                abs(functor_value - expected_value) <= 1.0e-15
            )
            checks[f"permittivity_blocks:{material}"] = tuple(
                mp.words(mp.get_parameter(text, functor_path, "block"))
            ) == expected_blocks

    checks["legacy_r31_permittivity_absent"] = (
        "r31_relative_permittivity" not in text
        and not mb.has_block(text, "FunctorMaterials/r31_poisson_relative_permittivity")
    )
    checks["charge_uses_physical_electron_density"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/r31_charge_density",
            "electron_density",
        )
        == "n_e_physical"
    )
    checks["charge_density_source"] = (
        mp.get_parameter(text, "FunctorMaterials/r31_charge_density", "density")
        == "rho_mat"
    )
    checks["ion_ids"] = mp.words(
        mp.get_parameter(text, "FunctorMaterials/r31_charge_density", "ion_ids")
    ) == ["O2p", "Om", "Op"]
    checks["ion_mass_fractions"] = mp.words(
        mp.get_parameter(
            text,
            "FunctorMaterials/r31_charge_density",
            "ion_mass_fractions",
        )
    ) == ["w_O2p", "w_Om", "w_Op"]
    checks["ion_molar_masses"] = mp.words(
        mp.get_parameter(
            text,
            "FunctorMaterials/r31_charge_density",
            "ion_molar_masses",
        )
    ) == ["0.032", "0.016", "0.016"]
    checks["ion_charges"] = mp.words(
        mp.get_parameter(text, "FunctorMaterials/r31_charge_density", "ion_charges")
    ) == ["1", "-1", "1"]

    checks["poisson_diffusion_variable"] = (
        mp.get_parameter(text, "FVKernels/r31_phi_diffusion", "variable")
        == "potential_plasma"
    )
    checks["poisson_diffusion_coeff"] = (
        mp.get_parameter(text, "FVKernels/r31_phi_diffusion", "coeff")
        == "relative_permittivity"
    )
    checks["poisson_charge_source"] = (
        mp.get_parameter(text, "FVKernels/r31_phi_charge_source", "v")
        == "poisson_charge_source"
    )

    checks["all_plasma_boundary_sideset"] = (
        mb.has_block(text, f"Mesh/{PLASMA_ALL_BOUNDARY}")
        and mp.get_parameter(text, f"Mesh/{PLASMA_ALL_BOUNDARY}", "input")
        == MESH_INPUT_BEFORE_R4
        and mp.get_parameter(text, f"Mesh/{PLASMA_ALL_BOUNDARY}", "block")
        == "plasma"
        and mp.get_parameter(
            text, f"Mesh/{PLASMA_ALL_BOUNDARY}", "new_boundary"
        )
        == PLASMA_ALL_BOUNDARY
    )
    checks["all_ground_dirichlet"] = (
        mb.has_block(text, "FVBCs/r31_phi_ground_all")
        and mp.get_parameter(text, "FVBCs/r31_phi_ground_all", "variable")
        == "potential_plasma"
        and mp.get_parameter(text, "FVBCs/r31_phi_ground_all", "boundary")
        == PLASMA_ALL_BOUNDARY
        and mp.get_parameter(text, "FVBCs/r31_phi_ground_all", "value") == "0"
    )

    # Q0 solves phi but does not feed it back to transport yet.
    checks["electron_feedback_off"] = (
        mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "phi_prescribed"
    )
    for path in mp.direct_children(text, "FVKernels"):
        typ = mp.get_parameter(text, path, "type")
        if typ in {
            "QPXFVElectrostaticDrift",
            "QPXFVHeavyMassElectromigrationCorrection",
        } and path != "FVKernels/n_e_drift":
            checks[f"feedback_off:{path}"] = (
                mp.get_parameter(text, path, "potential") == "phi_prescribed"
            )

    checks["gauss_flux_boundaries"] = mp.words(
        mp.get_parameter(text, "Postprocessors/r31_gauss_flux_reduced", "boundary")
    ) == [PLASMA_ALL_BOUNDARY]
    checks["gauss_flux_functor_diffusivity"] = (
        mp.get_parameter(
            text,
            "Postprocessors/r31_gauss_flux_reduced",
            "functor_diffusivity",
        )
        == "relative_permittivity"
    )
    checks["gauss_scale_eps0"] = (
        mp.get_parameter(text, "Postprocessors/r31_gauss_flux_charge", "value")
        == "r31_gauss_flux_reduced"
        and abs(
            float(
                mp.get_parameter(
                    text,
                    "Postprocessors/r31_gauss_flux_charge",
                    "scaling_factor",
                )
                or "nan"
            )
            - EPSILON_0
        )
        <= 1.0e-30
    )

    failed = sorted(key for key, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }
