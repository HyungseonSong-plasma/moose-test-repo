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
    parent = text("physics_app/src/physics/plasma/ChemistryAction.C")
    shared = text("physics_app/src/physics/plasma/PlasmaInterface.C")
    continuity = text("physics_app/src/physics/plasma/DDContinuityEq.C")

    assert 'registerSyntax("ChemistryAction", "Physics/Plasmas")' in app
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
    assert [r["electron_energy_change_eV"] for r in reactions] == [-12.4, -17.0]
    assert all("progress" not in r for r in reactions)
    assert [progress_from_id(r["id"]) for r in reactions] == ["R_EI405", "R_EI406"]
    assert all(r["progress_units"] == "mol/(m^3 s)" for r in reactions)

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
    energy = sum(r["electron_energy_change_eV"] * progress[progress_from_id(r["id"])]
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
                   "missing explicit electron energy policy", "nonfinite electron energy change"):
        assert marker in parser

    assert "std::set<std::string> touched;" in chemistry
    assert "reaction.net(id)" in chemistry
    assert "realLiteral(reaction.electron_energy_change_eV)" in chemistry
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
    paths = (
        "physics_app/src/physics/plasma/DDEnergyEq.C",
        "physics_app/src/bcs/PhysicsFEMPlasmaWallBCs.C",
        "physics_app/src/bcs/PhysicsFEMLogMolarElectronNoSheathSuppressionBC.C",
        "physics_app/src/bcs/PhysicsFEMLogMolarElectronEnergyDielectricBC.C",
        "physics_harness/adapters/moose/species_plot.py",
        "physics_harness/adapters/moose/time_trace.py",
    )
    for path in paths:
        source = text(path)
        assert "log_energy" not in source
        if path.endswith("DDEnergyEq.C"):
            assert 'return "log_" + species + "_energy";' in source
        else:
            assert "log_e_energy" in source
    assert '"log_e_energy"' in text("physics_app/src/bcs/PhysicsFEMPlasmaWallBCs.C")


def test_native_positive_and_negative_fixtures_are_wired():
    input_file = (PILOT / "chemistry_two_channels.i").read_text()
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert "files = plasma_two_channels.json" in input_file
    assert "[Chemistry]" in input_file
    assert "[Continuity]" in input_file
    assert "[Energy]" in input_file
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
