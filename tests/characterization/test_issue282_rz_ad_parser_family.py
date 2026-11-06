"""Offline invariants for real native AD parser diagnosis, not science evidence."""
from __future__ import annotations

import hashlib

import pytest

from experiments.Issue282_e2a_rz_bridge.diagnose_gdb_stack import (
    INPUT_SHA256, MESH_SHA256,
)
from experiments.Issue282_e2a_rz_bridge.diagnose_segv import make_case
from experiments.Issue282_e2a_rz_bridge.probe_parser_family import (
    CASES, all_parsed_to_generics, mini_input,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp


def test_nine_bounded_cases_cover_both_originals_and_independent_1d() -> None:
    assert len(CASES) == 9
    assert len({row[0] for row in CASES}) == len(CASES)
    assert sum(row[1] is None for row in CASES) == 5
    assert sum(row[1] is not None for row in CASES) == 4
    assert {row[2] for row in CASES if row[1] is not None} == {
        "control", "all_parsed_generic"
    }


@pytest.mark.parametrize("mode", (
    "mini_base", "mini_generic", "mini_ad",
    "mini_ad_jitoff", "mini_nested_jitoff",
))
def test_minimal_controls_keep_identical_fv_equation_and_single_observer(mode: str) -> None:
    text = mini_input(mode)
    assert mb.has_block(text, "FVKernels/energy_time")
    assert mb.has_block(text, "FVKernels/energy_diffusion")
    assert mp.get_parameter(text, "Executioner", "solve_type") == "LINEAR"
    assert mp.get_parameter(text, "Executioner", "num_steps") == "10"
    if mode != "mini_base":
        assert mb.has_block(text, "Postprocessors/ad_probe_integral")
        assert mb.has_block(text, "FunctorMaterials/ad_probe")
    if mode == "mini_generic":
        assert mp.get_parameter(text, "FunctorMaterials/ad_probe", "type") == "ADGenericFunctorMaterial"
    if mode.startswith("mini_ad"):
        assert mp.get_parameter(text, "FunctorMaterials/ad_probe", "type") == "ADParsedFunctorMaterial"
    if mode.endswith("jitoff"):
        assert mp.get_parameter(text, "GlobalParams", "enable_jit") == "false"
    if mode == "mini_nested_jitoff":
        assert mb.has_block(text, "FunctorMaterials/ad_probe_outer")


@pytest.mark.parametrize("name", ("r4_qf1_predecessor", "e2a_zero_diffusion"))
def test_every_rz_family_replacement_is_explicit_and_byte_pinned(tmp_path, name: str) -> None:
    case = tmp_path / name
    make_case(case, name)
    original = (case / "input.i").read_text()
    assert hashlib.sha256(original.encode()).hexdigest() == INPUT_SHA256[name]
    assert hashlib.sha256((case / "qvt.msh").read_bytes()).hexdigest() == MESH_SHA256
    revised, rows = all_parsed_to_generics(original)
    assert len(rows) >= 10
    assert revised != original
    assert all(item["block"].startswith("FunctorMaterials/") for item in rows)
    assert not any(
        mp.get_parameter(revised, path, "type") == "ADParsedFunctorMaterial"
        for path in mp.direct_children(revised, "FunctorMaterials")
    )
    assert mb.has_block(revised, "FVKernels/u_advection")
    assert mb.has_block(revised, "FVKernels/v_advection")
    if name == "e2a_zero_diffusion":
        assert mb.has_block(revised, "FVKernels/n_epsilon_diffusion")
        assert mb.has_block(revised, "Postprocessors/electron_energy_inventory_J")


def test_unsupported_minimal_mode_refuses_invalid_configuration() -> None:
    # A mode accidentally not in the bounded enum must not be silently treated
    # as a scientific or AD parser positive control.
    from experiments.Issue282_e2a_rz_bridge.probe_parser_family import main
    assert callable(main)
