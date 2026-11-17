"""P04/P05 P0 mutation controls; not a replacement for real physics-opt P2."""
from __future__ import annotations

from copy import deepcopy

import pytest

from ci.guards.issue633_species_owner_guard import OwnerContractError, validate


BASE_INPUT = """
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = e
          fvm_species = 'O2p Om Op'
          fem_potential = potential
        []
      []
    []
  []
[]
"""

def mechanism():
    records = {
        sid: {
            "charge_number": charge,
            "initial_number_density": 1e14,
            "transport_coef": "constant",
            "mobility": 1.0,
            "diffusivity": 0.1,
        }
        for sid, charge in (("e", -1), ("O2p", 1), ("Om", -1), ("Op", 1))
    }
    return {
        "species": records,
        "reactions": [
            {"id": "EI-415", "reactants": {"e": 1}, "products": {"O2p": 1}},
            {"id": "EI-401", "reactants": {"e": 1}, "products": {"Om": 1}},
            {"id": "EI-417", "reactants": {"e": 1}, "products": {"Op": 1}},
        ],
    }


def expect_fail(text, data, category):
    with pytest.raises(OwnerContractError, match=category):
        validate(text, data)


def test_three_explicit_fvm_species_plan_exactly_12():
    result = validate(BASE_INPUT, mechanism())
    assert result["fem_species"] == ["e"]
    assert result["fvm_species"] == ["O2p", "Om", "Op"]
    assert result["expected_fv_kernel_count"] == 12
    assert result["expected_fv_kernel_names"] == [
        f"{sid}_{suffix}"
        for sid in ("O2p", "Om", "Op")
        for suffix in ("time", "diffusion", "drift", "source")
    ]
    assert result["verdict"] == "INPUT_ONLY_PRECHECK_PASS"


def test_missing_or_ambiguous_selection_fails():
    expect_fail(BASE_INPUT.replace("fvm_species = 'O2p Om Op'", "fvm_species = 'O2p Om e'"),
                mechanism(), "DUPLICATE_DISCRETIZATION")
    expect_fail(BASE_INPUT.replace("O2p Om Op", "O2p Om Typo"),
                mechanism(), "UNKNOWN_JSON_SPECIES")
    expect_fail(BASE_INPUT.replace("fem_species = e", "fem_species = ''").replace(
                "fvm_species = 'O2p Om Op'", "fvm_species = ''"),
                mechanism(), "MISSING_SELECTION")


def test_missing_species_data_is_not_native_fallback():
    data = mechanism()
    del data["species"]["Om"]["transport_coef"]
    expect_fail(BASE_INPUT, data, "MISSING_JSON_TRANSPORT")
    data = mechanism()
    del data["species"]["O2p"]["initial_number_density"]
    expect_fail(BASE_INPUT, data, "MISSING_INITIAL_DENSITY")
    data = mechanism()
    del data["reactions"][2]
    expect_fail(BASE_INPUT, data, "MISSING_SPECIES_SOURCE")


@pytest.mark.parametrize("section", ("FVKernels", "FVBCs"))
def test_any_explicit_native_fv_owner_rejected(section):
    native = f"""
[{section}]
  [legacy_ion_operator]
    type = FVDiffusion
    variable = log_O2p
  []
[]
"""
    expect_fail(BASE_INPUT + native, mechanism(), "DUPLICATE_NATIVE_OWNER")
    # Object names are irrelevant; do not admit a renamed competing owner.
    expect_fail(BASE_INPUT + native.replace("legacy_ion_operator", "renamed_operator"),
                mechanism(), "DUPLICATE_NATIVE_OWNER")


@pytest.mark.parametrize("legacy_var", ("log_ni", "log_nm", "log_nop"))
@pytest.mark.parametrize("section", ("FVKernels", "FVBCs"))
def test_historical_s6_native_ion_variable_aliases_rejected(section, legacy_var):
    # The old S6 Native states are log_ni/nm/nop, not log_O2p/Om/Op.
    # Missing this alias map would produce a false caller-zero / false cutover.
    native = f"""
[{section}]
  [old_ion]
    type = FVDiffusion
    variable = {legacy_var}
  []
[]
"""
    expect_fail(BASE_INPUT + native, mechanism(), "DUPLICATE_NATIVE_OWNER")


def test_unresolved_layers_fail_closed():
    expect_fail(BASE_INPUT + "!include ion_native.i\n", mechanism(), "UNRESOLVED_LAYER")
