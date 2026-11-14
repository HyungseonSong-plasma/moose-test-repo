"""Issue402: structural completeness of JSON-owned electron FEM equations.

This is a P0 contract *in addition to*, never instead of, source-bound
physics-opt --check-input P2. It audits electron continuity and energy only.
RF, potential solve, ion FV and full private-data S6 parity are external gates.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app/src"
CHEM = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"


def code(path: str) -> str:
    return (APP / path).read_text(encoding="utf-8")


def assert_parts(source: str, fragments: tuple[str, ...]) -> None:
    for fragment in fragments:
        assert fragment in source, fragment


def test_continuity_has_one_fem_log_state_time_transport_and_chemistry_rhs():
    dd = code("physics/plasma/DDContinuityEq.C")
    assert_parts(dd, (
        'return "log_" + species;',
        '"Electron continuity is FEM-only',
        '".initial_number_density in Chemistry JSON [1/m^3]; "',
        'getProblem().addVariable(type, variable, params);',
        'getProblem().addInitialCondition(type, name() + "_" + species + "_density_ic", params);',
        'const std::string time_type = "FEMLogMolarTimeDerivative";',
        'const std::string type = "FEMLogMolarDriftDiffusion";',
        'params.set<MooseFunctorName>("mobility") = species[i] + "_mobility";',
        'params.set<MooseFunctorName>("diffusion") = species[i] + "_diffusivity";',
        'params.set<Real>("charge_number") = mechanism.species(species[i]).charge_number;',
        'getProblem().addKernel(time_type, species[i] + "_time", time_params);',
        'getProblem().addKernel(type, kernel_name, params);',
        'source_params.set<MooseFunctorName>("functor") = "S_" + species[i] + "_molar";',
        'source_params.set<bool>("functor_on_rhs") = true;',
        'getProblem().addKernel(source_type, species[i] + "_source", source_params);',
        'requireUniqueFEKernel("FEMLogMolarTimeDerivative", variables[i]);',
        'requireUniqueFEKernel("FEMLogMolarDriftDiffusion", variables[i]);',
    ))
    assert 'std::find(_fvm_species.begin(), _fvm_species.end(), "e")' in dd


def test_energy_has_one_log_state_time_transport_joule_and_chemistry_rhs():
    energy = code("physics/plasma/DDEnergyEq.C")
    assert_parts(energy, (
        'return "log_" + species + "_energy";',
        'Electron energy requires fem_species =',
        '"initial_molar_energy_density_eV"',
        'std::isfinite(initial)',
        'getProblem().addVariable(type, variable, params);',
        'std::log(getParam<Real>("initial_molar_energy_density_eV"))',
        'getProblem().addInitialCondition(type, name() + "_initial_energy", params);',
        'requireUniqueFEKernel("FEMLogMolarTimeDerivative", variable);',
        'requireUniqueFEKernel("FEMLogMolarDriftDiffusion", variable);',
        'requireUniqueFEKernel("FEMLogMolarElectronJouleHeating", variable);',
        'getProblem().addKernel(time_type, name() + "_time", time);',
        'transport.set<MooseFunctorName>("mobility") = "e_energy_mobility";',
        'transport.set<MooseFunctorName>("diffusion") = "e_energy_diffusivity";',
        'transport.set<Real>("charge_number") = chemistryData().species("e").charge_number;',
        'getProblem().addKernel(transport_type, name() + "_transport", transport);',
        'joule.set<std::vector<VariableName>>("electron_log_density") = {"log_e"};',
        'joule.set<MooseFunctorName>("mobility") = "e_mobility";',
        'joule.set<MooseFunctorName>("diffusion") = "e_diffusivity";',
        'getProblem().addKernel(joule_type, name() + "_joule", joule);',
        'params.set<MooseFunctorName>("functor") = "Q_e_molar_eV";',
        'params.set<bool>("functor_on_rhs") = true;',
        'getProblem().addKernel(type, name() + "_chemistry_energy", params);',
        'mean.set<MooseFunctorName>("electron_energy_density") = "log_e_energy";',
        'mean.set<MooseFunctorName>("electron_density") = "log_e";',
        'getProblem().addFunctorMaterial(mean_type, name() + "_mean_energy", mean);',
    ))
    # The electric potential and RF heating are explicitly external interfaces.
    assert 'if (isParamValid("fem_potential"))' in energy
    assert 'if (isParamValid("rf_heating_material"))' in energy


def test_residual_units_and_source_ownership_are_conservative():
    kernel = code("kernels/FEMPlasmaTransport.C")
    bridge = code("materials/ElectronEnergyMaterial.C")
    transport = code("materials/DDTransportMaterial.C")
    chemistry = code("physics/plasma/Chemistry.C")
    continuity = code("physics/plasma/DDContinuityEq.C")
    assert_parts(kernel, (
        '(exp(_u[_qp]) - exp(_u_old[_qp])) / _dt',
        'const ADReal c = exp(_u[_qp]);',
        'const ADRealVectorValue grad_c = c * _grad_u[_qp];',
        'D * grad_c + _charge_number * mu * c * _grad_potential[_qp];',
        'return minus_flux * _grad_test[_i][_qp];',
        'const ADRealVectorValue electric_field = -_grad_potential[_qp];',
        'return _test[_i][_qp] * (electric_field * electron_flux);',
    ))
    assert 'const ADReal mean_energy = exp(energy_state - density_state);' in bridge
    assert 'constexpr Real energy_factor = 5.0 / 3.0;' in transport
    for field in ('"e_energy_mobility"', '"e_energy_diffusivity"'):
        assert field in transport
    assert 'density.set<std::string>("expression") = "6.02214076e23*exp(c)";' in continuity
    assert_parts(chemistry, (
        'const auto coefficient = reaction.net(id);',
        'source.parts.push_back("(" + std::to_string(coefficient) + ")*" + symbol);',
        'energy.parts.push_back("(-1.0)*(" + loss + ")*" + progress);',
        'params.set<std::string>("property_name") = "Q_e_molar_eV";',
        'params.set<std::string>("property_name") = "S_" + id + "_molar";',
    ))


def test_s6_reaction_projection_electron_stoichiometry_and_losses():
    for variant in ("417", "941"):
        payload = json.loads((CHEM / f"unified_s6_{variant}.json").read_text())
        e = payload["species"]["e"]
        assert e["charge_number"] == -1
        assert e["transport_coef"] == "lookup"
        assert e["energy_transport_coef"] == "fluid"
        assert e["initial_number_density"] > 0
        reactions = {r["id"]: r for r in payload["reactions"]}
        assert len(reactions) == 8
        assert sum("table" in r for r in reactions.values()) == 7
        assert reactions["H25"]["rate"]["model"] == "power_law"
        # Electron continuity source = R_EI415 - R_EI401 + R_EI{variant}.
        expected = {"EI-415": 1, "EI-401": -1, f"EI-{variant}": 1}
        net = {key: r["products"].get("e", 0) - r["reactants"].get("e", 0)
               for key, r in reactions.items()}
        assert {key: value for key, value in net.items() if value} == expected
        assert reactions["EI-02"]["energy_loss_eV"] == {"model": "elastic"}
        assert reactions["EI-17"]["energy_loss_eV"] == {"model": "elastic"}
        assert reactions["EI-401"]["energy_loss_eV"] == 0
        assert reactions["H25"]["energy_loss_eV"] == {"model": "none"}
        assert reactions["EI-415"]["energy_loss_eV"] == 12.06
        assert reactions["EI-407"]["energy_loss_eV"] == 0.977
        assert reactions["EI-2069"]["energy_loss_eV"] == 5.02
        assert reactions[f"EI-{variant}"]["energy_loss_eV"] == (
            17 if variant == "417" else 13.62
        )
        assert all("table_sha256" not in r and
                   "target_molar_concentration" not in r
                   for r in reactions.values())


def test_electron_wall_flux_is_one_owner_for_both_molar_bcs():
    continuity = code("physics/plasma/DDContinuityEq.C")
    energy = code("physics/plasma/DDEnergyEq.C")
    particle_bc = code("bcs/FEMElectronSheathBC.C")
    energy_bc = code("bcs/FEMElectronEnergySheathBC.C")
    assert 'wall.set<std::string>("species_id") = "e";' in continuity
    assert 'wall.set<MooseFunctorName>("electron_density") = "n_e_physical";' in continuity
    assert 'wall.set<MooseFunctorName>("mean_energy") = "e_energy_eV";' in continuity
    assert 'getProblem().addFunctorMaterial(wall_type, name() + "_sheath_wall_flux", wall);' in continuity
    assert 'params.set<MooseFunctorName>("wall_number_flux") = bc.wall_number_flux;' in continuity
    assert 'params.set<MooseFunctorName>("wall_number_flux") = bc.wall_number_flux;' in energy
    assert 'params.set<MooseFunctorName>("mean_energy") = bc.mean_energy;' in energy
    assert 'number_flux / PHYSICS_CONSTANTS::N_A' in particle_bc
    assert '(particle_flux / PHYSICS_CONSTANTS::N_A) * (2.5 * Te)' in energy_bc
    assert 'const ADReal Te = (2.0 / 3.0) * mean_energy;' in energy_bc
    for variant in ("417", "941"):
        d = json.loads((CHEM / f"unified_s6_{variant}.json").read_text())
        bcs = [bc for group in d["boundaries"].values()
               for bc in group["bcs"].values()]
        assert len(bcs) == 8
        assert sum(bc["type"] == "FEMElectronSheathBC" for bc in bcs) == 4
        assert sum(bc["type"] == "FEMElectronEnergySheathBC" for bc in bcs) == 4
        assert all(bc["wall_number_flux"] == "e_wall_number_flux" for bc in bcs)
        assert all(bc["mean_energy"] == "e_energy_eV" for bc in bcs
                   if bc["type"] == "FEMElectronEnergySheathBC")
