"""Issue #402: JSON mechanism and per-channel signed-energy regression contract.

These checks deliberately complement, not replace, MOOSE Native P1/P2.
EI-405 and EI-406 here are synthetic channel-ID examples; do not interpret
these assignments as independently verified EI physical source data.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
APP = ROOT / "physics_app"


def text(path: str) -> str:
    return (ROOT / path).read_text()


def test_mechanism_is_the_only_high_level_charge_owner():
    app = text("physics_app/src/base/PhysicsApp.C")
    parent = text("physics_app/src/physics/plasma/Chemistry.C")
    shared = text("physics_app/src/physics/plasma/PlasmaInterface.C")
    continuity = text("physics_app/src/physics/plasma/DDContinuityEq.C")

    assert 'registerSyntax("PlasmasAction", "Physics/Plasmas")' in app
    assert "class PlasmasAction : public Action" in text("physics_app/include/physics/plasma/Chemistry.h")
    assert 'registerMooseAction("PhysicsApp", PlasmasAction, "check_integrity");' in parent
    assert '"files"' in parent and 'getParam<std::vector<FileName>>("files")' in parent
    assert "chemistryData()" in shared
    assert "mechanism.species(species[i]).charge_number" in continuity
    assert 'params.set<Real>("charge_number")' in continuity
    assert '"fem_charge_numbers"' not in continuity
    assert '"fvm_charge_numbers"' not in continuity

    full_s6 = text("experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py")
    assert "files = plasma_species_only.json" in full_s6


def progress_from_id(reaction_id):
    if reaction_id.startswith("EI-") and reaction_id[3:].isdigit():
        return "R_EI" + reaction_id[3:]
    if reaction_id.startswith("H") and reaction_id[1:].isdigit():
        return "R_H" + reaction_id[1:]
    raise ValueError(reaction_id)


def test_same_equation_different_id_different_energy_channels_are_not_collapsed():
    mechanism = json.loads((PILOT / "plasma_two_channels.json").read_text())
    reactions = mechanism["reactions"]
    assert [r["id"] for r in reactions] == ["EI-405", "EI-406"]
    assert len({r["id"] for r in reactions}) == 2
    assert len({mechanism["equations"][r["id"]] for r in reactions}) == 1
    assert [r["energy_loss_eV"] for r in reactions] == [12.4, 17.0]
    assert all("progress" not in r for r in reactions)
    assert [progress_from_id(r["id"]) for r in reactions] == ["R_EI405", "R_EI406"]
    assert all(r["units"] == "mol/(m^3 s)" for r in reactions)

    source = {}
    for reaction in reactions:
        for species in set(reaction["reactants"]) | set(reaction["products"]):
            net = reaction["products"].get(species, 0) - reaction["reactants"].get(species, 0)
            if net:
                source.setdefault(species, []).append((net, progress_from_id(reaction["id"])))
    assert source["e"] == [(1, "R_EI405"), (1, "R_EI406")]
    assert source["O2"] == [(-1, "R_EI405"), (-1, "R_EI406")]
    assert source["O2p"] == [(1, "R_EI405"), (1, "R_EI406")]

    # Distinct progress values must yield the independent signed projection.
    progress = {"R_EI405": 1.0, "R_EI406": 2.0}
    energy = -sum(r["energy_loss_eV"] * progress[progress_from_id(r["id"])]
                 for r in reactions)
    assert abs(energy - (-12.4 * 1.0 - 17.0 * 2.0)) < 1e-12


def test_json_equation_stoichiometry_and_species_charge_are_consistent():
    obj = json.loads((PILOT / "plasma_two_channels.json").read_text())
    species = obj["species"]
    for reaction in obj["reactions"]:
        assert obj["equations"][reaction["id"]] == "e + O2 -> 2e + O2p"
        left, right = reaction["reactants"], reaction["products"]
        for element in {"O"}:
            assert sum(species[s]["elements"].get(element, 0) * n
                       for s, n in left.items()) == sum(
                           species[s]["elements"].get(element, 0) * n
                           for s, n in right.items())
        assert sum(species[s]["charge_number"] * n for s, n in left.items()) == sum(
            species[s]["charge_number"] * n for s, n in right.items())


def test_compiled_catalogue_checks_and_signed_functor_sources_exist():
    parser = text("physics_app/src/physics/plasma/Chemistry.C")
    chemistry = parser
    continuity = text("physics_app/src/physics/plasma/DDContinuityEq.C")
    energy = text("physics_app/src/physics/plasma/DDEnergyEq.C")

    for marker in ("charge conservation failed", "elemental balance failed",
                   "equation text and structured stoichiometry differ",
                   "duplicate reaction ID or generated progress owner",
                   "missing explicit electron energy policy", "electron energy loss must be finite and nonnegative"):
        assert marker in parser

    assert "std::set<std::string> touched;" in chemistry
    assert "reaction.net(id)" in chemistry
    assert "realLiteral(reaction.energy_loss_eV)" in chemistry
    assert 'energy.parts.push_back("(-1.0)*("' in chemistry
    assert '"Q_e_molar_eV"' in chemistry
    assert '"S_" + id + "_molar"' in chemistry
    assert "getProblem().addFunctorMaterial" in chemistry

    assert '"S_" + species[i] + "_molar"' in continuity
    assert '"Q_e_molar_eV"' in energy
    assert 'params.set<bool>("functor_on_rhs") = true;' in continuity
    assert 'params.set<bool>("functor_on_rhs") = true;' in energy
    assert "getProblem().addKernel" in energy
    assert "getProblem().addKernel" in continuity


def test_s6_uses_canonical_progress_providers_without_alias_materials():
    for variant in ("417", "941"):
        for name in (f"s6_{variant}_chemistry_run.template.i",
                     f"chemistry_s6_{variant}_catalogue_p2.i"):
            contents = (PILOT / name).read_text()
            for legacy in ("R_elastic_O2", "R_elastic_O", "R_ion_O2"):
                assert legacy not in contents
            # Full S6 overlays consume progress Functors from the renamed
            # staged native layers; synthetic P2 fixtures declare them here.
            if name.endswith("_catalogue_p2.i"):
                for expected in ("R_EI02", "R_EI17", "R_EI415"):
                    assert expected in contents
            assert "_progress_alias" not in contents

    stage = text("experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py")
    for before, after in (("R_elastic_O2", "R_EI02"),
                          ("R_elastic_O", "R_EI17"),
                          ("R_ion_O2", "R_EI415"),
                          ("log_energy", "log_e_energy")):
        assert f'"{before}": "{after}"' in stage
    # Old names only appear in the safeguarded historical conversion, never
    # as rate sources/consumers within the new runtime overlay.


def test_active_energy_state_binding_is_canonical_across_bc_and_readers():
    # The BC factory is deliberately species-agnostic: the owning Energy
    # Physics connects its generic 'variable' input to the canonical log state.
    energy = text("physics_app/src/physics/plasma/DDEnergyEq.C")
    assert "log_energy" not in energy
    assert 'return "log_" + species + "_energy";' in energy
    assert 'if (bc.variable != "log_e_energy")' in energy
    assert 'getProblem().addBoundaryCondition(bc.type, bc_name, params);' in energy

    bc_path = "physics_app/src/bcs/FEMElectronEnergySheathBC.C"
    bc = text(bc_path)
    assert 'registerMooseObject("PhysicsApp", FEMElectronEnergySheathBC);' in bc
    assert 'getFunctor<ADReal>("wall_number_flux")' in bc
    assert 'getFunctor<ADReal>("mean_energy")' in bc
    assert "log_energy" not in bc
    assert not (APP / "src/bcs/PhysicsFEMLogMolarElectronEnergyDielectricBC.C").exists()
    assert not (APP / "src/bcs/PhysicsFEMLogMolarElectronNoSheathSuppressionBC.C").exists()

    for path in ("physics_harness/adapters/moose/species_plot.py",
                 "physics_harness/adapters/moose/time_trace.py"):
        source = text(path)
        assert "log_e_energy" in source
        assert "log_energy" not in source


def test_native_positive_and_negative_fixtures_are_wired():
    input_file = (PILOT / "chemistry_two_channels.i").read_text()
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert "files = plasma_two_channels.json" in input_file
    assert "[Chemistry]" in input_file
    assert "[Continuity]" in input_file
    assert "[Energy]" in input_file
    assert "SpeciesTransportAliasMaterial" not in input_file
    chemistry = json.loads((PILOT / "plasma_two_channels.json").read_text())
    assert chemistry["species"]["e"]["transport_coef"] == "constant"
    assert chemistry["species"]["e"]["mobility"] == 1
    assert chemistry["species"]["e"]["diffusivity"] == 1
    assert "transport_coefficients" not in chemistry
    assert "chemistry_two_channels.i" in runner
    assert "PLASMA_CHEMISTRY_TWO_CHANNELS_P2_PASS" in runner
    assert "invalid_chemistry_reactions" in runner

    negative = json.loads((PILOT / "plasma_duplicate_id.json").read_text())
    assert [r["id"] for r in negative["reactions"]] == ["EI-405", "EI-405"]
    assert all("progress" not in r for r in negative["reactions"])
    assert progress_from_id(negative["reactions"][0]["id"]) == progress_from_id(negative["reactions"][1]["id"])


def test_derived_progress_and_hidden_energy_rule_are_enforced_in_cpp():
    chem = text("physics_app/src/physics/plasma/Chemistry.C")
    energy = text("physics_app/src/physics/plasma/DDEnergyEq.C")
    assert "progressFromReactionId(reaction.id, file)" in chem
    assert "if (entry.contains(\"progress\"))" in chem
    assert "return \"R_EI\" + match[1].str();" in chem
    assert "return \"R_H\" + match[1].str();" in chem
    assert "log_\" + species + \"_energy" in energy
    assert 'addRequiredParam<VariableName>("variable"' not in energy
    assert 'getParam<VariableName>("variable")' not in energy


def test_chemistry_electron_rhs_is_generated_with_fem_continuity():
    """Volume electron chemistry sources are projected once into the FEM RHS."""
    mechanism = text("physics_app/src/physics/plasma/Chemistry.C")
    continuity = text("physics_app/src/physics/plasma/DDContinuityEq.C")
    assert 'return !_awh.getActions<Plasma::Chemistry>().empty();' in text(
        "physics_app/src/physics/plasma/PlasmaInterface.C")
    assert 'reaction.domain == "volume" && reaction.net(id) != 0' in mechanism
    assert '"S_" + id + "_molar"' in mechanism
    assert 'source.parts.push_back("(" + std::to_string(coefficient) + ")*" + symbol);' in mechanism
    assert 'getProblem().addFunctorMaterial(type, "chemistry_" + id + "_source", params);' in mechanism
    assert 'if (!isParamValid("fem_potential"))' in continuity
    assert 'if (chemistryEnabled() && mechanism.hasSpeciesSource(species[i]))' in continuity
    assert 'source_params.set<NonlinearVariableName>("variable") = variables[i];' in continuity
    assert 'source_params.set<MooseFunctorName>("functor") = "S_" + species[i] + "_molar";' in continuity
    assert 'source_params.set<bool>("functor_on_rhs") = true;' in continuity
    assert 'getProblem().addKernel(source_type, species[i] + "_source", source_params);' in continuity
    assert 'requireUniqueFEKernel("FunctorKernel", variables[i]);' in continuity


def test_json_rate_lookup_providers_and_electron_sheath_have_unique_owners():
    """P0: check full e/e-energy object graph, not native P2 time integration."""
    mechanism = text("physics_app/src/physics/plasma/Chemistry.C")
    rate_h = text("physics_app/src/materials/HRateCoefMaterial.C")
    continuity = text("physics_app/src/physics/plasma/DDContinuityEq.C")
    energy = text("physics_app/src/physics/plasma/DDEnergyEq.C")
    staging = text("experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py")
    runner = text("experiments/Issue402_plasma_dsl_g1/run_native_binding_smoke.sh")

    assert 'reaction.rate.table_file =' in mechanism
    assert 'resolveDataFile(entry.at("table").get<std::string>(), file)' in mechanism
    assert 'if (entry.contains("table_sha256") || entry.contains("target_molar_concentration"))' in mechanism
    assert 'params.set<FileName>("rate_table_file") = reaction.rate.table_file;' in mechanism
    assert 'params.set<MooseFunctorName>("mean_energy") = "e_energy_eV";' in mechanism
    assert 'params.set<MooseFunctorName>("electron_number_density") = "n_e_physical";' in mechanism
    assert 'params.set<MooseFunctorName>("target_molar_concentration") = "c_" + target;' in mechanism
    assert 'params.set<std::string>("reaction_progress") = reaction.progress;' in mechanism
    assert 'getProblem().addFunctorMaterial(type, "chemistry_" + reaction.progress + "_rate", params);' in mechanism
    assert 'params.set<std::vector<MooseFunctorName>>("reactant_concentrations") = concentrations;' in mechanism
    assert 'getProblem().addFunctorMaterial(type, name() + "_heavy_rates", params);' in mechanism
    assert '"reactant_concentrations"' in rate_h
    assert 'reaction.elastic_energy_loss' in mechanism
    assert '"delta_epsilon_" +' in mechanism
    assert '"(-1.0)*("' in mechanism
    assert '"Q_e_molar_eV"' in mechanism
    assert '"S_e_molar"' not in mechanism or '"S_" + id + "_molar"' in mechanism
    assert 'wall.set<std::string>("species_id") = "e";' in continuity
    assert 'bc.wall_number_flux != "e_wall_number_flux"' in continuity
    assert 'getProblem().addFunctorMaterial(density_type, name() + "_number_density", density);' in continuity
    assert continuity.index('getProblem().addFunctorMaterial(density_type') < continuity.index('if (!sheath_wall)')
    assert '"ESWallFluxMaterial"' not in energy
    assert '"ElectronEnergyMaterial"' in energy
    assert '"Q_e_molar_eV"' in energy
    assert 'retire_staged_kinetic_owners' in staging
    assert 'HYBRID_DUPLICATE_NATIVE_RATE_OWNER_' in staging
    assert 'source = source[:old.start()] + source[old.end():]' in staging
    assert 'check_issue402_dd_json_plasma_boundary_p2.py' in runner

    for variant in ("417", "941"):
        source = json.loads((PILOT / f"chemistry/unified_s6_{variant}.json").read_text())
        assert set(source) == {"species", "equations", "reactions", "boundaries"}
        assert len(source["reactions"]) == 8
        assert sum("table" in r for r in source["reactions"]) == 7
        assert sum("rate" in r for r in source["reactions"]) == 1
        assert not any("table_sha256" in r or "target_molar_concentration" in r or
                       "provenance" in r for r in source["reactions"])
        bcs = [bc for group in source["boundaries"].values() for bc in group["bcs"].values()]
        assert len(bcs) == 8
        assert {bc["type"] for bc in bcs} == {
            "FEMElectronSheathBC", "FEMElectronEnergySheathBC"
        }
        assert all(bc["wall_number_flux"] == "e_wall_number_flux" for bc in bcs)
