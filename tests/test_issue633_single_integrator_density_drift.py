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
        "wall_sidesets.insert(boundary.mesh_boundaries.begin(),",
        'if (mechanism.hasIonWalls() && wall_sidesets.size() != 8)',
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
    assert len(EXPECTED_SIDES) == 8


def test_density_and_drift_mutation_controls_are_fail_closed():
    source = CONTINUITY.read_text()
    required = (
        'number_scale.str() + "*exp(log_c)"',
        'if (!mechanism.species(id).ion_wall)',
        'if (mechanism.hasIonWalls() && wall_sidesets.size() != 8)',
        'drift_params.set<std::vector<BoundaryName>>("boundaries_to_avoid")',
    )
    for token in required:
        assert token in source
        mutant = source.replace(token, "", 1)
        assert token not in mutant
