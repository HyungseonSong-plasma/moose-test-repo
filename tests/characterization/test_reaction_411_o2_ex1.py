"""Reaction 411 4.5-eV excitation: formula, units, single owner, no O production.

Gudmundsson et al., J. Phys. D: Appl. Phys. 33 (2000) 1323-1331,
Table 3, DOI 10.1088/0022-3727/33/11/311.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from experiments.Issue395_powered_chemistry_ladder.build_o2_ex1_411_overlay import (
    ENERGY_LOSS_EV,
    ENERGY_SOURCE,
    PROGRESS,
    build,
)

ROOT = Path(__file__).resolve().parents[2]
CPP = ROOT / "physics_app/src/materials/PhysicsElectronImpactO2Ex1ExcitationMaterial.C"
HEADER = ROOT / "physics_app/include/materials/PhysicsElectronImpactO2Ex1ExcitationMaterial.h"
N_A = 6.02214076e23
BASE = "\n".join((
    "property_name = n_e_physical",
    "mean_energy = mean_en_solved",
    "property_name = rho_neutral",
    "property_name = w_O2_constraint",
    "[log_energy]",
))


def k_particle(te_eV: float) -> float:
    if not math.isfinite(te_eV) or te_eV < 1.0 or te_eV > 7.0:
        raise ValueError("Te outside valid Gudmundsson 1-7 eV fit")
    return 1.07e-15 * math.exp(-3.43 / te_eV)


def test_411_reference_rate_is_dynamic_and_molar_units_close() -> None:
    k1, k3, k7 = (k_particle(t) for t in (1.0, 3.0, 7.0))
    assert 0 < k1 < k3 < k7
    n_e = 3.0e16  # [particles/m^3]
    c_o2 = 0.002  # [mol/m^3]
    r = (N_A * k3) * (n_e / N_A) * c_o2  # [mol/(m^3 s)]
    assert math.isclose(r, k3 * n_e * c_o2, rel_tol=1e-14)
    assert r > 0
    source_e = -ENERGY_LOSS_EV * r  # [eV mol/(m^3 s)]
    assert source_e < 0
    assert math.isclose(source_e / r, -4.5)
    for invalid in (0.0, 0.99, 7.01, math.nan, math.inf):
        with pytest.raises(ValueError):
            k_particle(invalid)


def test_411_overlay_is_formula_only_energy_sink_and_zero_other_sources() -> None:
    text = build(BASE)
    assert text.count("type = PhysicsElectronImpactO2Ex1ExcitationMaterial") == 1
    assert text.count(f"functor_names = '{PROGRESS}'") == 1
    assert f"property_name = {ENERGY_SOURCE}" in text
    assert "expression = '-4.5*R'" in text
    assert "variable = log_energy" in text
    assert "functor_on_rhs = true" in text
    for forbidden in (
        "[FVKernels]", "variable = w_O", "variable = log_ne",
        "variable = log_nm", "variable = p", "S_O_mass",
        "PhysicsElectronImpactRateMaterial", "R_diss_O2"
    ):
        assert forbidden not in text


def test_411_rejects_missing_or_duplicate_kinetic_owner() -> None:
    with pytest.raises(ValueError, match="capability audit"):
        build(BASE.replace("[log_energy]", "[log_ne]"))
    with pytest.raises(ValueError, match="inherited reaction progress"):
        build(BASE + f"\nproperty_name = {PROGRESS}")


def test_411_cpp_owner_guard_and_mutations() -> None:
    src, hdr = CPP.read_text(), HEADER.read_text()
    assert "10.1088/0022-3727/33/11/311" in hdr
    required = (
        'addFunctorProperty<ADReal>(\n      "R_O2_ex1_411"',
        "K_PREF_M3_S = 1.07e-15;",
        "BETA_EV = 3.43;",
        "const ADReal T_e = (2.0 / 3.0) * _mean_energy(r, state);",
        "T_e.value() < 1.0 || T_e.value() > 7.0",
        "k_molar * (n_e / N_A) * c_o2",
        "exp(-BETA_EV / T_e)",
    )
    for token in required:
        assert token in src

    for faulty in (
        src.replace("K_PREF_M3_S = 1.07e-15;", "K_PREF_M3_S = 1.07e-14;"),
        src.replace("exp(-BETA_EV / T_e)", "exp(-BETA_EV)"),
        src.replace("T_e.value() > 7.0", "T_e.value() > 70.0"),
    ):
        assert not all(x in faulty for x in required), "mutation must be detected"


def test_411_powered_replay_is_opt_in_and_keeps_baseline_off() -> None:
    replay = (
        ROOT
        / "experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh"
    ).read_text()
    assert 'export EI411_CHANNEL="${EI411_CHANNEL:-off}"' in replay
    assert 'case "$EI411_CHANNEL" in on|off)' in replay
    assert 'if [[ "$EI411_CHANNEL" == on ]]; then' in replay
    assert 'export RESULT="${RESULT}_plus_411_ex1"' in replay
    assert 'build_o2_ex1_411_overlay.py' in replay
    assert replay.count("'$OELASTIC' $EI411_CLI") == 2
    assert 'EI411_CLI=""' in replay
    assert '''EI411_CLI="'$EI411'"''' in replay
