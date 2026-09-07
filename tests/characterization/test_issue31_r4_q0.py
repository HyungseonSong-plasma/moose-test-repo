from __future__ import annotations

import csv
from pathlib import Path

from experiments.Issue31_r4_q0_all_ground import run as issue31_run
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4 import (
    EPSILON_0,
    MATERIAL_COVERAGE_FUNCTOR,
    MATERIAL_COVERAGE_ONLY_BLOCKS,
    PERMITTIVITY_MATERIALS,
    PLASMA_ALL_BOUNDARY,
    audit_r4_q0_input,
    build_r4_q0_input,
)

ROOT = Path(__file__).resolve().parents[2]
R3_E0 = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"


def _base() -> str:
    return (R3_E0 / "heavy_base.i").read_text()


def test_r4_q0_build_preserves_accepted_r3_and_adds_poisson() -> None:
    text, meta = build_r4_q0_input(_base())
    audit = audit_r4_q0_input(text)

    assert audit["status"] == "PASS"
    assert meta["poisson_enabled"] is True
    assert meta["electrostatic_feedback_enabled"] is False
    assert meta["surface_accumulated_charge_enabled"] is False
    assert meta["charge_electron_density"] == "n_e_physical"
    assert meta["ground_boundary"] == PLASMA_ALL_BOUNDARY
    assert meta["relative_permittivity_provider"] == (
        "block-scoped functor relative_permittivity"
    )
    assert meta["legacy_base_material_policy"] == (
        "removed; conductivity/material_name not preserved"
    )
    assert meta["material_coverage_policy"] == (
        "coverage-only functor on electrostatically inactive mesh blocks"
    )
    assert tuple(meta["material_coverage_only_blocks"]) == MATERIAL_COVERAGE_ONLY_BLOCKS

    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/heavy_transport",
            "electron_number_density",
        )
        == "n_e_physical"
    )
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/r31_charge_density",
            "electron_density",
        )
        == "n_e_physical"
    )
    assert mp.get_parameter(
        text,
        "FVKernels/r31_phi_charge_source",
        "v",
    ) == "poisson_charge_source"


def test_r4_q0_replaces_base_materials_with_permittivity_functors() -> None:
    base = _base()
    text, meta = build_r4_q0_input(base)

    assert set(meta["relative_permittivity_migration"]) == set(PERMITTIVITY_MATERIALS)
    assert "r31_relative_permittivity" not in text

    for material, (expected_value, expected_blocks) in PERMITTIVITY_MATERIALS.items():
        material_path = f"Materials/{material}"
        functor_path = f"FunctorMaterials/permittivity_{material}"

        # The frozen accepted R3 source retains the historical BaseMaterial.
        assert mb.has_block(base, material_path)
        assert mp.get_parameter(base, material_path, "type") == "BaseMaterial"
        assert mp.get_parameter(base, material_path, "relative_permittivity") is not None

        # Every generated R4 candidate removes the complete legacy provider.
        assert not mb.has_block(text, material_path)

        assert mp.get_parameter(text, functor_path, "type") == "ADGenericFunctorMaterial"
        assert mp.words(mp.get_parameter(text, functor_path, "prop_names")) == [
            "relative_permittivity"
        ]
        values = mp.words(mp.get_parameter(text, functor_path, "prop_values"))
        assert len(values) == 1
        assert float(values[0]) == expected_value
        assert tuple(mp.words(mp.get_parameter(text, functor_path, "block"))) == (
            expected_blocks
        )

        migration = meta["relative_permittivity_migration"][material]
        assert migration["legacy_provider"] == "BaseMaterial"
        assert migration["legacy_provider_removed"] is True
        assert migration["discarded_metadata"] == ["conductivity", "material_name"]
        if material == "plasma":
            assert migration["legacy_scope"] == "global_unrestricted"
        else:
            assert migration["legacy_scope"] == "explicit"

    # Conductivity has no current R4 consumer and is not promoted into a functor.
    assert "prop_names = 'conductivity'" not in text
    assert mp.get_parameter(
        text,
        "FVKernels/r31_phi_diffusion",
        "coeff",
    ) == "relative_permittivity"


def test_r4_q0_restores_material_integrity_without_inventing_inactive_eps_r() -> None:
    text, _ = build_r4_q0_input(_base())
    path = f"FunctorMaterials/{MATERIAL_COVERAGE_FUNCTOR}"

    assert mp.get_parameter(text, path, "type") == "ADGenericFunctorMaterial"
    assert mp.words(mp.get_parameter(text, path, "prop_names")) == [
        MATERIAL_COVERAGE_FUNCTOR
    ]
    assert mp.words(mp.get_parameter(text, path, "prop_values")) == ["0"]
    assert tuple(mp.words(mp.get_parameter(text, path, "block"))) == (
        MATERIAL_COVERAGE_ONLY_BLOCKS
    )

    # The five coverage-only blocks do not receive a speculative eps_r provider.
    physics_blocks = {
        block
        for _, (_, blocks) in PERMITTIVITY_MATERIALS.items()
        for block in blocks
    }
    assert physics_blocks.isdisjoint(MATERIAL_COVERAGE_ONLY_BLOCKS)


def test_r4_q0_charge_mapping_is_explicit_and_signed() -> None:
    text, _ = build_r4_q0_input(_base())
    path = "FunctorMaterials/r31_charge_density"

    assert mp.words(mp.get_parameter(text, path, "ion_ids")) == ["O2p", "Om", "Op"]
    assert mp.words(mp.get_parameter(text, path, "ion_mass_fractions")) == [
        "w_O2p",
        "w_Om",
        "w_Op",
    ]
    assert mp.words(mp.get_parameter(text, path, "ion_molar_masses")) == [
        "0.032",
        "0.016",
        "0.016",
    ]
    assert mp.words(mp.get_parameter(text, path, "ion_charges")) == ["1", "-1", "1"]


def test_r4_q0_grounds_complete_plasma_subdomain_boundary() -> None:
    text, _ = build_r4_q0_input(_base())
    mesh = f"Mesh/{PLASMA_ALL_BOUNDARY}"
    bc = "FVBCs/r31_phi_ground_all"

    assert mp.get_parameter(text, mesh, "type") == "SideSetsAroundSubdomainGenerator"
    assert mp.get_parameter(text, mesh, "block") == "plasma"
    assert mp.get_parameter(text, mesh, "new_boundary") == PLASMA_ALL_BOUNDARY

    assert mp.get_parameter(text, bc, "type") == "FVDirichletBC"
    assert mp.get_parameter(text, bc, "variable") == "potential_plasma"
    assert mp.get_parameter(text, bc, "boundary") == PLASMA_ALL_BOUNDARY
    assert mp.get_parameter(text, bc, "value") == "0"


def test_r4_q0_does_not_enable_electrostatic_transport_feedback() -> None:
    text, _ = build_r4_q0_input(_base())

    # R4-Q0 solves potential_plasma, but the accepted R3-E0 transport operators
    # remain attached to the zero prescribed potential for attribution.
    for path in mp.direct_children(text, "FVKernels"):
        typ = mp.get_parameter(text, path, "type")
        if typ in {
            "QPXFVElectrostaticDrift",
            "QPXFVHeavyMassElectromigrationCorrection",
        }:
            assert mp.get_parameter(text, path, "potential") == "phi_prescribed"


def test_r4_q0_gauss_observables_match_declared_c1_ledger() -> None:
    text, _ = build_r4_q0_input(_base())

    reduced = "Postprocessors/r31_gauss_flux_reduced"
    scaled = "Postprocessors/r31_gauss_flux_charge"
    charge = "Postprocessors/r31_charge_integral"

    assert mp.get_parameter(text, charge, "functor") == "charge_density"
    assert mp.get_parameter(text, reduced, "type") == "SideDiffusiveFluxIntegral"
    assert mp.get_parameter(text, reduced, "variable") == "potential_plasma"
    assert mp.get_parameter(text, reduced, "boundary") == PLASMA_ALL_BOUNDARY
    assert (
        mp.get_parameter(text, reduced, "functor_diffusivity")
        == "relative_permittivity"
    )
    assert mp.get_parameter(text, reduced, "diffusivity") is None
    assert mp.get_parameter(text, scaled, "type") == "ScalePostprocessor"
    assert mp.get_parameter(text, scaled, "value") == "r31_gauss_flux_reduced"
    assert float(mp.get_parameter(text, scaled, "scaling_factor") or "nan") == EPSILON_0


def test_r4_q0_stage_reuses_accepted_r3_assets(tmp_path: Path) -> None:
    target = tmp_path / "R4_Q0"
    staged = issue31_run._stage(target)

    assert staged["construction"]["audit"]["status"] == "PASS"
    assert staged["construction"]["surface_accumulated_charge_enabled"] is False
    assert staged["construction"]["relative_permittivity_provider"] == (
        "block-scoped functor relative_permittivity"
    )
    assert staged["construction"]["legacy_base_material_policy"] == (
        "removed; conductivity/material_name not preserved"
    )
    assert tuple(staged["construction"]["material_coverage_only_blocks"]) == (
        MATERIAL_COVERAGE_ONLY_BLOCKS
    )
    for name in (
        "qvt.msh",
        "transport_data.txt",
        "electron_moments.txt",
        "check.py",
        "expected.json",
    ):
        assert (target / name).is_file(), name

    text = (target / "input.i").read_text()
    assert mp.get_parameter(
        text,
        "FunctorMaterials/r31_charge_density",
        "electron_density",
    ) == "n_e_physical"
    for material in PERMITTIVITY_MATERIALS:
        assert not mb.has_block(text, f"Materials/{material}")
        assert mb.has_block(text, f"FunctorMaterials/permittivity_{material}")
    assert mb.has_block(text, f"FunctorMaterials/{MATERIAL_COVERAGE_FUNCTOR}")


def test_gauss_evidence_reports_measurement_without_predeclared_tolerance(tmp_path: Path) -> None:
    path = tmp_path / "input_out.physical.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("time", "r31_charge_integral", "r31_gauss_flux_charge"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "time": "1e-8",
                "r31_charge_integral": "2.0e-12",
                "r31_gauss_flux_charge": "2.2e-12",
            }
        )

    evidence = issue31_run._gauss_evidence(path)
    assert evidence["status"] == "MEASURED"
    assert evidence["volume_charge_C"] == 2.0e-12
    assert evidence["boundary_displacement_flux_C"] == 2.2e-12
    assert abs(evidence["signed_defect_C"] - 2.0e-13) <= 1.0e-28
    assert abs(evidence["relative_defect"] - (2.0e-13 / 2.2e-12)) <= 1.0e-15
    assert evidence["acceptance"] == "UNSET_FIRST_CONTROL_MEASUREMENT"
