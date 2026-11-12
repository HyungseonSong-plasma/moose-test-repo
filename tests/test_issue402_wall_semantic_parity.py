"""Bounded mathematical parity contract for the retired S6 ion total Wall class.

This test compares a literal historical *equation specification* derived from
PhysicsIonWallTotalFluxMaterial.C at original Git blob
aec2d1f7547dacd9238663140f3f5bce8f23bfb9 with an independently expressed
active six-output PhysicsIonWallFluxMaterial formula and C++ source features.
It checks physical signs, default gates, units, sided normal conventions and
edge conditions. This is NOT full native S6 trajectory equivalence.
"""
from __future__ import annotations

import itertools
import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app/src/functormaterials/PhysicsIonWallFluxMaterial.C"
RETIRED = ROOT / "physics_app/src/functormaterials/PhysicsIonWallTotalFluxMaterial.C"
# Physics.h shares these physical constants; use standard independent values.
R_GAS = 8.31446261815324
AVOGADRO = 6.02214076e23
K_BOLTZ_EV_PER_K = 8.617333262145e-5


def original_legacy_total(n, mu, field_normal, z, M, sticking, gas_T,
                          ion_temp_eV=0., smoothing=0.):
    """Pre-retirement literal two-output thermal + migration wall equation."""
    thermal_temp = ion_temp_eV / K_BOLTZ_EV_PER_K if ion_temp_eV > 0 else gas_T
    thermal = sticking * 0.25 * n * math.sqrt(
        8.0 * R_GAS * thermal_temp / (math.pi * M))
    directed = z * field_normal
    if smoothing > 0:
        outward = 0.5 * directed * (1.0 + math.tanh(directed / smoothing))
    else:
        outward = directed if directed > 0 else 0.0
    number = thermal + n * mu * outward
    return number, number * M / AVOGADRO


def active_total_from_components(n, mu, field_normal, z, M, sticking, gas_T,
                                 ion_temp_eV=0., smoothing=0.):
    """Independently evaluate the active named number/mass output components."""
    T = (gas_T if ion_temp_eV == 0
         else ion_temp_eV / K_BOLTZ_EV_PER_K)
    speed = math.sqrt(8 * R_GAS / math.pi * (T / M))
    surface = (n * speed / 4) * sticking
    toward_outside = field_normal * z
    gate = (toward_outside > 0) if smoothing == 0 else None
    drift_speed = (max(0., toward_outside) if gate is not None else
                   toward_outside / 2 * (1 + math.tanh(toward_outside / smoothing)))
    migration = mu * n * drift_speed
    return surface + migration, ((surface * M) + (migration * M)) / AVOGADRO


@pytest.mark.parametrize("species,z,M", [
    ("O2p", +1, .032), ("Op", +1, .016), ("Om", -1, .016)])
@pytest.mark.parametrize("n,mu", [(1e12, 2e-3), (1e18, 1e-5)])
@pytest.mark.parametrize("field", [-1e5, -1., 0., 1., 1e5])
@pytest.mark.parametrize("width", [0., 1e-3, 200.])
@pytest.mark.parametrize("temp_ev", [0., .05])
@pytest.mark.parametrize("sticking", [0., .5, 1.])
def test_retired_vs_active_total_analytical_wall_flux(
        species, z, M, n, mu, field, width, temp_ev, sticking):
    params = (n, mu, field, z, M, sticking, 300., temp_ev, width)
    old_n, old_m = original_legacy_total(*params)
    new_n, new_m = active_total_from_components(*params)
    assert math.isclose(old_n, new_n, rel_tol=1e-13, abs_tol=1e-20)
    assert math.isclose(old_m, new_m, rel_tol=1e-13, abs_tol=1e-35)
    assert old_n >= 0 and new_n >= 0
    assert math.isclose(old_m / old_n, M / AVOGADRO, rel_tol=1e-13) if old_n else old_m == 0
    assert species in ("O2p", "Op", "Om")


def test_retired_factory_absent_but_active_wall_has_same_defaults_and_faces():
    assert not RETIRED.exists(), "Parent PR #523 removed the duplicate factory"
    text = APP.read_text(encoding="utf-8")
    assert 'registerMooseObject("PhysicsApp", PhysicsIonWallFluxMaterial)' in text
    for setting in ('"ion_temperature_eV",\n      0.0,',
                    '"migration_gate_smoothing_width",\n      0.0,',
                    '"sticking", 1.0,'):
        assert setting in text
    for symbol in ('"ion_number_density"', '"potential"', '"mobility"',
                   '"gas_temperature"', '"charge_number"', '"molar_mass"'):
        assert symbol in text
    assert "PHYSICS_CONSTANTS::R * T_i" in text
    assert "PHYSICS_CONSTANTS::pi * _molar_mass" in text
    assert "PHYSICS_CONSTANTS::N_A" in text
    assert "0.5 * directed_field" in text
    assert "tanh(directed_field / smoothing_width)" in text
    assert "return -n;" in text
    assert "r, state, _use_element_gradient_for_potential" in text
    assert "face.face_side" in text
    assert "ADReal(0.0)" in text
    assert 'wallName("ion_wall_number_flux", "number_flux")' in text
    assert 'wallName("ion_wall_mass_flux", "mass_flux")' in text


def test_s6_archive_owner_type_changes_only_in_disposable_scratch():
    from importlib import util
    filename = (ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/"
                "prepare_s6_run_input.py")
    spec = util.spec_from_file_location("wall_cutover_semantic", filename)
    assert spec and spec.loader
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._WALL_ION_PREFIX_TO_SPECIES == {
        "": "O2p", "atomic_positive_": "Op", "negative_": "Om"}
    text = filename.read_text(encoding="utf-8")
    assert "S6_WALL_DENSITY_IDENTITY_UNPROVED" in text
    assert "S6_WALL_CHARGE_IDENTITY_UNPROVED" in text
    assert "S6_WALL_RETIRED_TYPE_STILL_PRESENT" in text
    assert "PhysicsIonWallFluxMaterial" in text
    assert 'body = body[:type_line.end()] + "\n    species_id = "' not in text  # no literal newline in Python string
    assert "source_type" in text and "consumer_and_reference_replacements" in text


def test_no_unspecified_science_gate_bypass():
    assert "run_chemistry_s6_p3_once" not in (
        ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/"
        "prepare_s6_run_input.py").read_text()
