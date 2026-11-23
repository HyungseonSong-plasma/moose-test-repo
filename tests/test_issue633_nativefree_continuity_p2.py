"""Issue #633 Poisson-free, native-ion-free FV Continuity P0 fixture.

P0 only; actual PhysicsApp --check-input P2 is owned by the existing
run_native_binding_smoke.sh, against a same-job exact-head binary.
"""
import copy
import json
from pathlib import Path

from ci.p1_ion_new_only_preflight import inspect

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
INPUT = PILOT / "issue633_ion_continuity_newonly_p2.i"
JSON = PILOT / "issue633_ion_continuity_newonly_p2.json"
SOURCE = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"
SPECIES = ("O2p", "Om", "Op")


def _source_and_json():
    return INPUT.read_text(), json.loads(JSON.read_text())


def test_fv_continuity_selected_without_native_ion_owners_or_poisson():
    deck, mechanism = _source_and_json()
    assert "fvm_species = 'O2p Om Op'" in deck
    assert "fem_species" not in deck
    assert "dont_create_kernels" not in deck
    assert "[Poisson]" not in deck
    assert "[FVKernels]" not in deck and "[FVBCs]" not in deck
    assert "[Chemistry]" in deck
    assert "files = issue633_ion_continuity_newonly_p2.json" in deck
    result = inspect({INPUT.name: deck}, mechanism, contract="new-only")
    assert result["status"] == "P0_STATIC_PASS_ONLY", result["errors"]
    assert result["native_fv_owner_count"] == 0
    assert result["explicit_ion_wall_current_owner_count"] == 0


def test_json_supplies_all_three_species_initial_transport_and_volume_sources():
    _, mechanism = _source_and_json()
    for sid in SPECIES:
        s = mechanism["species"][sid]
        assert s["initial_number_density"] > 0
        assert s["transport_coef"] == "constant"
        assert s["mobility"] >= 0 and s["diffusivity"] >= 0
        assert "ion_wall" not in s
        assert any(
            reaction["products"].get(sid, 0) != reaction["reactants"].get(sid, 0)
            for reaction in mechanism["reactions"]
        ), sid
    assert not mechanism.get("boundaries")
    assert "boundaries_to_avoid" not in mechanism
    assert all(r["units"] == "mol/(m^3 s)" and
               r["energy_loss_eV"] == {"model": "none"}
               for r in mechanism["reactions"])


def test_json_reaction_charge_and_element_balance_without_poisson():
    _, mechanism = _source_and_json()
    for rxn in mechanism["reactions"]:
        charge = 0
        element = 0
        for sign, members in ((-1, rxn["reactants"]), (1, rxn["products"])):
            for sid, stoich in members.items():
                charge += sign * stoich * mechanism["species"][sid]["charge_number"]
                element += sign * stoich * mechanism["species"][sid]["elements"].get("O", 0)
        assert charge == 0
        assert element == 0


def test_missing_json_transport_and_remaining_native_kernel_are_rejected():
    deck, mechanism = _source_and_json()
    malformed = copy.deepcopy(mechanism)
    del malformed["species"]["Om"]["transport_coef"]
    assert "P1_JSON_TRANSPORT_MISSING_OR_INVALID:Om" in inspect(
        {INPUT.name: deck}, malformed)["errors"]
    native_kernel = deck + """
[FVKernels]
  [legacy_ni_time]
    type = FVLogMolarTimeDerivative
    variable = log_O2p
  []
[]
"""
    result = inspect({INPUT.name: native_kernel}, mechanism)
    assert result["status"] == "FAIL"
    assert "P1_NATIVE_FV_ION_OWNER_PRESENT_1" in result["errors"]


def test_source_contract_owns_12_fv_operators_without_binding_only_mode():
    source = SOURCE.read_text()
    assert 'registerMooseAction("PhysicsApp", DDContinuityEq, "add_fv_kernel");' in source
    assert "const bool generate_kernels = !getParam<bool>(\"dont_create_kernels\");" in source
    for token in (
        'getProblem().addFVKernel(time_type, id + "_time", time_params);',
        'getProblem().addFVKernel(diffusion_type, id + "_diffusion", diffusion_params);',
        'getProblem().addFVKernel(drift_type, id + "_drift", drift_params);',
        'getProblem().addFVKernel(source_type, id + "_source", source_params);',
        'if (!mechanism.hasSpeciesSource(id))',
        'source_params.set<MooseFunctorName>("v") = "S_" + id + "_molar";',
    ):
        assert token in source


def test_real_negative_p2_fixture_om_source_is_absent_but_other_contracts_survive():
    negative_i = PILOT / "issue633_ion_continuity_missing_om_source_p2.i"
    negative_j = PILOT / "issue633_ion_continuity_missing_om_source_p2.json"
    positive_i, positive_json = _source_and_json()
    mutated = json.loads(negative_j.read_text())
    assert negative_i.read_text().replace(
        "issue633_ion_continuity_missing_om_source_p2.json",
        "issue633_ion_continuity_newonly_p2.json"
    ).split("[Mesh]", 1)[1] == positive_i.split("[Mesh]", 1)[1]
    assert {r["id"] for r in positive_json["reactions"]} == {
        "EI-415", "EI-401", "EI-417"
    }
    assert {r["id"] for r in mutated["reactions"]} == {"EI-415", "EI-417"}
    assert "EI-401" not in mutated["equations"]
    assert all(r["products"].get("Om", 0) == r["reactants"].get("Om", 0)
               for r in mutated["reactions"])
    assert inspect({negative_i.name: negative_i.read_text()},
                   mutated)["status"] == "P0_STATIC_PASS_ONLY"
    # Deliberately shows selector-only preflight is weaker than the required
    # C++ Source gate; the exact-head Native P2 negative must reject it.
    smoke = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert "issue633_ion_continuity_missing_om_source_p2.i" in smoke
    assert "requires a nonzero volume reaction source" in smoke
