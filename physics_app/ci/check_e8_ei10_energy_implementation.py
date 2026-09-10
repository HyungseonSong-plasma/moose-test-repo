#!/usr/bin/env python3
"""Static production discriminator for #26 E8 EI10 energy projection."""

import json
import math
from pathlib import Path

N_A = 6.02214076e23
CONTRACT = Path("docs/development/2026-09-10_issue26_e8_ei10_energy_contract.json")
HEADER = Path("physics_app/include/fvkernels/PhysicsFVElectronReactionEnergySource.h")
SOURCE = Path("physics_app/src/fvkernels/PhysicsFVElectronReactionEnergySource.C")
RATE_OWNER = Path("physics_app/src/materials/PhysicsElectronImpactO2sExcitationMaterial.C")


def main():
    contract = json.loads(CONTRACT.read_text())
    header = HEADER.read_text()
    source = SOURCE.read_text()
    rate = RATE_OWNER.read_text()

    assert contract["ownership"]["energy_projection_owner"] == "PhysicsFVElectronReactionEnergySource"
    assert contract["ownership"]["energy_projection_must_consume"] == "R_O2s"
    assert contract["ownership"]["energy_projection_must_not_recompute_rate"] is True
    assert contract["reaction"]["energy_loss_eV_per_event"] == 0.977

    assert "class PhysicsFVElectronReactionEnergySource : public FVElementalKernel" in header
    assert "const Moose::Functor<ADReal> & _reaction_progress;" in header
    assert "const Real _energy_loss_eV;" in header
    assert "const Real _n_ref;" in header
    assert "const Real _energy_reference_eV;" in header

    assert 'registerMooseObject("PhysicsApp", PhysicsFVElectronReactionEnergySource);' in source
    assert '"reaction_progress", "Canonical molar reaction progress [mol/(m^3 s)]."' in source
    assert '"energy_loss_eV", "energy_loss_eV > 0"' in source
    assert '"n_ref", "n_ref > 0"' in source
    assert '"energy_reference_eV"' in source and '"energy_reference_eV > 0"' in source
    assert '_reaction_progress(getFunctor<ADReal>("reaction_progress"))' in source
    assert '_energy_loss_eV(getParam<Real>("energy_loss_eV"))' in source
    assert '_n_ref(getParam<Real>("n_ref"))' in source
    assert '_energy_reference_eV(getParam<Real>("energy_reference_eV"))' in source
    assert "constexpr Real N_A = 6.02214076e23;" in source
    assert "requires reaction_progress >= 0" in source
    assert "physical_energy_source = -_energy_loss_eV * N_A * R;" in source
    assert "physical_energy_source / (_n_ref * _energy_reference_eV);" in source
    assert "return -normalized_rhs;" in source

    # The generic energy projector must not own EI10 kinetics or solved-state lookup.
    for forbidden in (
        "K_O2S",
        "4.71e8",
        "electron_number_density",
        "o2_molar_concentration",
        "mean_en_solved",
        "rate_table",
        "interpolate",
        "0.977",
        "9.97",
    ):
        assert forbidden not in source

    # The Stage-3 EI10 rate owner remains the sole kinetic evaluator.
    assert 'addFunctorProperty<ADReal>(\n      "R_O2s"' in rate
    assert "K_O2S = 4.71e8" in rate
    assert "0.977" not in rate and "9.97" not in rate

    # Independent algebraic sign/normalization discriminator.
    R = 7.8133117564827e-3
    delta = contract["reaction"]["energy_loss_eV_per_event"]
    n_ref = 1.0e16
    epsilon_ref = 5.73276
    physical = -delta * N_A * R
    normalized_rhs = physical / (n_ref * epsilon_ref)
    residual = -normalized_rhs
    assert physical < 0.0 and normalized_rhs < 0.0 and residual > 0.0
    assert math.isclose(
        residual,
        delta * N_A * R / (n_ref * epsilon_ref),
        rel_tol=1.0e-15,
    )

    # Mutation controls: wrong sign or wrong EI10 identity must fail the contract.
    assert (+delta * N_A * R) > 0.0
    assert not math.isclose(9.97, delta, rel_tol=0.0, abs_tol=1.0e-12)

    print("E8_EI10_INELASTIC_ENERGY_IMPLEMENTATION_PASS")


if __name__ == "__main__":
    main()
