"""Reaction 407 (EI10): Te-dependent O2(X) -> O2(a1Delta_g) provenance/ownership gates.

Source: Gudmundsson et al., J. Phys. D 33 (2000) 1323-1331, Table 3.
https://doi.org/10.1088/0022-3727/33/11/311
Maxwellian fit, Te in 1-7 eV; not an EEDF-resolved cross-section integration.
"""
from __future__ import annotations

import math
from pathlib import Path

from experiments.historical_recipe_support.issue192_s5r import (
    OWNER_BLOCKS,
    build_s5r_input,
)
from physics_harness.adapters.moose import parameters as mp


ROOT = Path(__file__).resolve().parents[2]
CPP = ROOT / "physics_app/src/materials/PhysicsElectronImpactO2sExcitationMaterial.C"
HEADER = ROOT / "physics_app/include/materials/PhysicsElectronImpactO2sExcitationMaterial.h"
BASE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
N_A = 6.02214076e23
M_O2 = 0.032


def _k_particle(te_eV: float) -> float:
    if not (1.0 <= te_eV <= 7.0):
        raise ValueError("Gudmundsson 2000 Maxwellian fit requires 1-7 eV")
    return 1.37e-15 * math.exp(-2.14 / te_eV)


def _check_cpp_surface(source: str) -> None:
    required = (
        'MooseEnum("constant_surrogate temperature_dependent", "constant_surrogate")',
        '"mean_energy", "mean_en_solved"',
        '_mean_energy = &getFunctor<ADReal>("mean_energy")',
        'const ADReal T_e = (2.0 / 3.0) * (*_mean_energy)(r, state);',
        'T_e.value() < 1.0 || T_e.value() > 7.0',
        'N_A * 1.37e-15 * exp(-2.14 / T_e)',
        'return K_O2S * (n_e / N_A) * c_o2;',
        'addFunctorProperty<ADReal>(\n      "R_O2s"',
    )
    for token in required:
        assert token in source, f"missing 407 production contract: {token}"


def test_407_source_formula_and_model_guard_mutations() -> None:
    source = CPP.read_text()
    _check_cpp_surface(source)
    assert "Gudmundsson" in source
    assert "10.1088/0022-3727/33/11/311" in HEADER.read_text()

    for bad in (
        source.replace("1.37e-15", "1.37e-14"),
        source.replace("exp(-2.14 / T_e)", "exp(-2.14)"),
        source.replace("T_e.value() > 7.0", "T_e.value() > 70.0"),
    ):
        try:
            _check_cpp_surface(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError("407 source-checker missed targeted rate/range mutation")


def test_407_maxwellian_oracle_state_dependence_and_units() -> None:
    k_lo = _k_particle(1.0)
    k_ref = _k_particle(3.82184)
    k_hi = _k_particle(7.0)
    assert 0 < k_lo < k_ref < k_hi
    assert math.isclose(N_A * k_ref, 4.7129490106933236e8, rel_tol=1e-12)

    n_e = 1.0e16
    c_o2 = 1.0e-3
    r_ref = (N_A * k_ref) * (n_e / N_A) * c_o2
    assert math.isclose(r_ref, k_ref * n_e * c_o2, rel_tol=1e-14)
    assert math.isclose((-M_O2 * r_ref) + (M_O2 * r_ref), 0.0, abs_tol=1e-15)

    for outside in (0.0, 0.99, 7.01, math.nan):
        try:
            _k_particle(outside)
        except ValueError:
            pass
        else:
            raise AssertionError(f"407 oracle accepted invalid temperature: {outside}")


def test_407_stage5_uses_dynamic_model_without_duplicate_rate_owner() -> None:
    generated, _ = build_s5r_input(BASE.read_text())
    owner = OWNER_BLOCKS["EI10"]
    assert mp.get_parameter(generated, owner, "type") == (
        "PhysicsElectronImpactO2sExcitationMaterial"
    )
    assert mp.get_parameter(generated, owner, "rate_model") == "temperature_dependent"
    assert mp.get_parameter(generated, owner, "mean_energy") == "mean_en_solved"
    assert generated.count("type = PhysicsElectronImpactO2sExcitationMaterial") == 1
    assert generated.count("reaction_progress = R_O2s") == 1
