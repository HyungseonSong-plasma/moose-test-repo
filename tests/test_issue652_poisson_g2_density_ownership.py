"""G2 source-bound charged density ownership, preserving legacy sheath behavior."""
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app/src/physics/plasma"
CHEM = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"
N_A = 6.02214076e23


def source(name):
    return (APP / name).read_text()


@pytest.mark.parametrize("case", ("417", "941"))
def test_newonly_log_state_physically_converts_to_number_density(case):
    data = json.loads((CHEM / f"unified_s6_{case}_newonly.json").read_text())
    assert "poisson" in data
    for id in ("e", "O2p", "Om", "Op"):
        n = data["species"][id]["initial_number_density"]
        assert n > 0 and math.isfinite(n)
        log_c = math.log(n / N_A)
        assert N_A * math.exp(log_c) == pytest.approx(n, rel=2e-14)
    assert {id: data["species"][id]["charge_number"]
            for id in ("e", "O2p", "Om", "Op")} == {
                "e": -1, "O2p": 1, "Om": -1, "Op": 1,
            }


def test_poisson_opt_in_density_is_owned_by_continuity():
    continuity = source("DDContinuityEq.C")
    assert "const bool poisson_density = mechanism.poisson() != nullptr;" in continuity
    assert 'density.set<std::string>("property_name") = "n_e_physical";' in continuity
    assert 'density.set<std::vector<std::string>>("functor_names") = {"log_e"};' in continuity
    assert 'density.set<std::string>("expression") = "6.02214076e23*exp(c)";' in continuity
    assert 'name() + "_electron_number_density"' in continuity
    assert "if ((mechanism.hasIonWalls() || poisson_density) &&" in continuity
    assert 'params.set<std::string>("property_name") = id + "_number_density";' in continuity
    assert 'params.set<std::vector<std::string>>("functor_names") = {continuityStateName(id)};' in continuity
    assert "PHYSICS_CONSTANTS::N_A" in continuity
    assert 'getParam<bool>("dont_create_kernels")' in continuity
    assert '"O2p", "Om", "Op"' in continuity
    # Do not publish another Native compatibility alias as a second producer.
    for alias in ("n_i_physical", "n_m_physical", "n_op_physical"):
        assert f'"property_name") = "{alias}"' not in continuity


def test_energy_legacy_ownership_is_unchanged_when_poisson_absent():
    energy = source("DDEnergyEq.C")
    assert "if (!chemistryData().poisson())" in energy
    assert 'density.set<std::string>("property_name") = "n_e_physical";' in energy
    assert 'density.set<std::vector<std::string>>("functor_names") = {"log_e"};' in energy
    assert 'density.set<std::string>("expression") = "6.02214076e23*exp(c)";' in energy
    assert 'getProblem().addFunctorMaterial(density_type, name() + "_number_density", density);' in energy
    assert 'const std::string wall_type = "ESWallFluxMaterial";' in energy
    assert 'wall.set<MooseFunctorName>("electron_density") = "n_e_physical";' in energy
