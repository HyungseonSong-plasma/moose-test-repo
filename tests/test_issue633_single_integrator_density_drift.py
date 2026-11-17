"""P18 source-contract regression for the single-head FV ion C2 handoff.

Static tests only: they do not assert a compiled MOOSE warehouse or S6 P2/P3.
The active C2 JSON sidesets, rather than an independent hardcoded FV drift
boundary list, must be passed to the generated drift Kernel.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTINUITY = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"
C2_JSON = ROOT / "physics_app/ci/issue633_c2_wall_3ion_overlay.json"
IDS = ("O2p", "Om", "Op")
EXPECTED_SIDES = {
    "inlet", "outlet", "plasma_electrode", "plasma_metal", "plasma_right",
    "plasma_cover", "plasma_wafer", "plasma_focus_ring",
}


def test_canonical_live_particle_density_is_created_once_per_selected_wall_ion():
    source = CONTINUITY.read_text()
    section = source.split("DDContinuityEq::addFunctorMaterials()", 1)[1]
    assert 'if (mechanism.hasIonWalls() && !getParam<bool>("dont_create_kernels"))' in section
    assert 'for (const auto & id : _fvm_species)' in section
    assert 'if (!mechanism.species(id).ion_wall)' in section
    assert section.count('params.set<std::string>("property_name") = id + "_number_density";') == 1
    assert 'params.set<std::vector<std::string>>("functor_names") = {continuityStateName(id)};' in section
    assert 'params.set<std::vector<std::string>>("functor_symbols") = {"log_c"};' in section
    assert 'number_scale << std::setprecision(17) << PHYSICS_CONSTANTS::N_A;' in section
    assert 'number_scale.str() + "*exp(log_c)"' in section
    assert 'getProblem().addFunctorMaterial(type, name() + "_" + id + "_number_density", params);' in section
    # The Poisson/diagnostic native aliases are not re-published under a second name here.
    for alias in ("n_i_physical", "n_m_physical", "n_op_physical"):
        assert f'params.set<std::string>("property_name") = "{alias}"' not in section


def test_generated_fv_drift_skips_exact_c2_wall_sides_from_json():
    source = CONTINUITY.read_text()
    section = source.split("DDContinuityEq::addFVKernels()", 1)[1].split(
        "DDContinuityEq::addFunctorMaterials()", 1)[0]
    for token in (
        "for (const auto & [group, boundary] : mechanism.boundaries())",
        'bc.variable == variable',
        'bc.type == "FVFunctorNeumannBC"',
        'bc.type == "FVLogMolarDielectricFluxBC"',
        'drift_params.set<MooseEnum>("advected_interp_method") = "upwind";',
        "wall_sidesets.insert(boundary.mesh_boundaries.begin(),",
        'if (mechanism.hasIonWalls() && wall_sidesets.empty())',
        'drift_params.set<std::vector<BoundaryName>>("boundaries_to_avoid")',
        "std::vector<BoundaryName>(wall_sidesets.begin(), wall_sidesets.end())",
    ):
        assert token in section
    data = json.loads(C2_JSON.read_text())
    for sid in IDS:
        targets = set()
        for label, group in data["boundaries"].items():
            if any(bc.get("variable") == f"log_{sid}" and
                   bc["type"] in ("FVFunctorNeumannBC", "FVLogMolarDielectricFluxBC")
                   for bc in group["bcs"].values()):
                targets.update(label.split())
        assert targets == EXPECTED_SIDES
    # This is only the current S6 characterization. The generator does not
    # require a fixed count and follows each species' actual BC declarations.
    assert "wall_sidesets.size() != 8" not in section
    assert 'if (!wall_sidesets.empty())' in section


def test_density_and_drift_mutation_controls_are_fail_closed():
    source = CONTINUITY.read_text()
    required = (
        'number_scale.str() + "*exp(log_c)"',
        'if (!mechanism.species(id).ion_wall)',
        'if (mechanism.hasIonWalls() && wall_sidesets.empty())',
        'drift_params.set<std::vector<BoundaryName>>("boundaries_to_avoid")',
    )
    for token in required:
        assert token in source
        mutant = source.replace(token, "", 1)
        assert token not in mutant


def test_boundaries_to_avoid_is_not_a_json_input_owner():
    catalogue = C2_JSON.read_text()
    assert '"boundaries_to_avoid"' not in catalogue
    parser = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    assert 'if (root.is_object() && root.contains("boundaries_to_avoid"))' in parser
    assert 'if (record.contains("boundaries_to_avoid"))' in parser
    assert 'use the boundaries BC catalogue' in parser
    continuity = CONTINUITY.read_text()
    assert 'drift_params.set<std::vector<BoundaryName>>("boundaries_to_avoid")' in continuity
    assert 'wall_sidesets.insert(boundary.mesh_boundaries.begin(),' in continuity
