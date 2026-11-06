"""Offline invariant tests; cannot substitute for the native 2D RZ discriminator."""
from __future__ import annotations

import hashlib

import pytest

from experiments.Issue282_e2a_rz_bridge.diagnose_gdb_stack import (
    INPUT_SHA256, MESH_SHA256,
)
from experiments.Issue282_e2a_rz_bridge.diagnose_segv import make_case
from experiments.Issue282_e2a_rz_bridge.isolate_ad_functors import (
    CASES, IMAGE, RHO_PATH, ENERGY_PP_PATH, transform,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp


def test_bounded_dependency_cases_are_distinct_and_never_package_adapter() -> None:
    assert len(CASES) == 10
    assert len({x[0] for x in CASES}) == len(CASES)
    assert {x[1] for x in CASES} == {"r4_qf1_predecessor", "e2a_zero_diffusion"}
    assert [x[2] for x in CASES].count("control") == 2
    assert IMAGE.startswith("ghcr.io/hyungseonsong-plasma/physics-runtime@sha256:")
    assert all("sol-adapter" not in x[0] for x in CASES)


@pytest.mark.parametrize("case_name", ("r4_qf1_predecessor", "e2a_zero_diffusion"))
def test_original_projected_input_exactly_matches_native_gdb_artifact(
    tmp_path, case_name,
) -> None:
    case = tmp_path / case_name
    make_case(case, case_name)
    original = (case / "input.historical.i").read_bytes()
    actual = (case / "input.i").read_bytes()
    assert original != actual
    assert hashlib.sha256(actual).hexdigest() == INPUT_SHA256[case_name]
    assert hashlib.sha256((case / "qvt.msh").read_bytes()).hexdigest() == MESH_SHA256


def test_r4_replacements_isolate_one_named_dependency_at_a_time(tmp_path) -> None:
    case = tmp_path / "r4"
    make_case(case, "r4_qf1_predecessor")
    original = (case / "input.i").read_text()
    assert transform(original, "control") == (original, [])
    for mode, target, new_type in (
        ("rho_generic", RHO_PATH, "ADGenericFunctorMaterial"),
        ("rho_parsed_constant", RHO_PATH, "ADParsedFunctorMaterial"),
        ("mn_generic", "FunctorMaterials/mean_molar_mass", "ADGenericFunctorMaterial"),
    ):
        changed, roots = transform(original, mode)
        assert roots == [target]
        assert changed != original
        assert mb.has_block(changed, target)
        assert mp.get_parameter(changed, target, "type") == new_type
        # Diagnostic mutation must NOT remove the actual RZ momentum equation.
        assert mb.has_block(changed, "FVKernels/u_advection")
        assert mb.has_block(changed, "FVKernels/v_advection")
        assert mp.get_parameter(changed, "Executioner", "automatic_scaling") == "false"


def test_e2a_replacements_keep_original_energy_equation_except_probed_observer(
    tmp_path,
) -> None:
    case = tmp_path / "e2a"
    make_case(case, "e2a_zero_diffusion")
    original = (case / "input.i").read_text()
    assert mb.has_block(original, ENERGY_PP_PATH)
    assert mb.has_block(original, "FVKernels/n_epsilon_diffusion")
    for mode in (
        "rho_generic", "energy_inventory_off", "energy_density_generic",
        "mass_integrals_off", "all_ad_integrals_off",
    ):
        changed, roots = transform(original, mode)
        assert changed != original
        assert roots
        assert mb.has_block(changed, "FVKernels/n_epsilon_diffusion")
        assert mb.has_block(changed, "FVKernels/n_epsilon_time")
        if mode == "energy_inventory_off":
            assert not mb.has_block(changed, ENERGY_PP_PATH)
        if mode == "all_ad_integrals_off":
            assert not any(
                mp.get_parameter(changed, path, "type") == "ADElementIntegralFunctorPostprocessor"
                for path in mp.direct_children(changed, "Postprocessors")
            )


def test_unsupported_or_noop_instrumentation_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported isolation mode"):
        transform("", "undocumented_backend_patch")
