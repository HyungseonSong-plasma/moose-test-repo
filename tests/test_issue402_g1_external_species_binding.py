"""Check the plasma input validation classes and example inputs.

These tests do not replace building or running the solver.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
CASE = ROOT / "experiments/Issue402_plasma_dsl_g1"


def sources():
    base_header = (APP / "include/physics/plasma/PlasmaInterface.h").read_text()
    base_source = (APP / "src/physics/plasma/PlasmaInterface.C").read_text()
    header = (APP / "include/physics/plasma/ContinuityPhysics.h").read_text()
    source = (APP / "src/physics/plasma/ContinuityPhysics.C").read_text()
    app = (APP / "src/base/PhysicsApp.C").read_text()
    return base_header, base_source, header, source, app


def test_continuity_uses_shared_plasma_validation():
    base_header, base_source, header, source, app = sources()
    assert "class PlasmaInterface : public PhysicsBase" in base_header
    assert "class ContinuityPhysics : public PlasmaInterface" in header
    assert "namespace Plasma" in header
    assert "void checkIntegrity() const override;" in header
    assert "validateSpeciesInputs(" in base_source
    assert "validateExistingSpeciesVariables(" in base_source
    assert "validateSpeciesInputs(" in source
    assert "validateExistingSpeciesVariables(" in source
    assert "using Plasma::ContinuityPhysics;" in source
    assert 'registerPhysicsBaseTasks("PhysicsApp", ContinuityPhysics);' in source
    assert 'registerMooseAction("PhysicsApp", ContinuityPhysics, "check_integrity");' in source
    assert 'registerSyntax("ContinuityPhysics",' in app
    assert '"Physics/Plasmas/Transport/DriftDiffusion/Continuity"' in app
    assert 'syntax.registerActionSyntax("PlasmaClosuresAction", "PlasmaClosures/*");' in app
    assert 'syntax.registerActionSyntax("GummelIterationAction", "GummelIteration/*");' in app


def test_existing_variables_only():
    _, base_source, _, source, _ = sources()
    assert 'addParam<std::vector<std::string>>(\n      "fem_species"' in source
    assert 'addParam<std::vector<std::string>>(\n      "fvm_species"' in source
    assert '"owner_mode"' not in base_source
    assert '"owner_mode"' not in source
    assert "Repeated or empty species in fem_species:" in base_source
    assert "Repeated or empty species in fvm_species" in base_source
    assert "Species '" in base_source
    assert "solverVariableExists(variable)" in base_source
    assert "isVariableFV(variable)" in base_source
    # Shared input validation never creates solver objects.
    assert "getProblem().add" not in base_source

    # Continuity can add drift-diffusion only when the required physical
    # coefficients have been supplied explicitly.
    assert 'if (!isParamValid("fem_potential"))' in source
    assert '"fem_mobility"' in source
    assert '"fem_diffusion"' in source
    assert '"fem_charge_numbers"' in source
    assert "getProblem().addKernel(" in source
    assert "PhysicsFEMLogMolarDriftDiffusion" in source
    assert "schema_version" not in base_source + source
    assert '"discretization"' not in base_source + source


def test_small_example_has_finite_element_and_finite_volume_equations():
    text = (CASE / "baseline.i").read_text()
    assert "[u_fe]" in text and "family = LAGRANGE" in text
    assert "[u_fv]" in text and "type = MooseVariableFVReal" in text
    assert "type = Diffusion" in text
    assert "type = FVDiffusion" in text
    assert "type = FVDirichletBC" in text
    assert "[Executioner]" in text and "type = Steady" in text


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("valid_bindings.i", "fem_species = 'e'"),
        ("invalid_overlap.i", "fem_species = 'e O2p'"),
        ("invalid_fem_fv_swap.i", "variables = 'u_fv u_fe'"),
        ("invalid_no_species.i", "variables = 'u_fe u_fv'"),
        ("invalid_missing_variable.i", "missing_fe"),
    ],
)
def test_example_inputs(filename, expected):
    text = (CASE / filename).read_text()
    assert expected in text
    assert "[Physics]" in text
    assert "[Plasmas]" in text
    assert "[DriftDiffusion]" in text
    assert "[Continuity]" in text
    assert "schema_version" not in text


def test_native_build_and_comparison_script():
    runner = (CASE / "run_native_binding_smoke.sh").read_text()
    assert "physics-opt" in runner and "make -C physics_app -j2" in runner
    assert "app_non_unity_dirs='%/utils'" in runner
    assert "PLASMA_RESULTS_MATCH" in runner
    assert "invalid_overlap invalid_fem_fv_swap invalid_no_species invalid_missing_variable" in runner
    assert "sha256sum" in runner
    assert "physics_app/src/physics/plasma/PlasmaInterface.C" in runner
    assert "physics_app/src/physics/plasma/ContinuityPhysics.C" in runner
    for name in ("EnergyPhysics", "ChemistryPhysics", "PoissonPhysics", "MaxwellPhysics"):
        header = (APP / f"include/physics/plasma/{name}.h").read_text()
        source = (APP / f"src/physics/plasma/{name}.C").read_text()
        assert f"class {name} : public PlasmaInterface" in header
        assert f'registerPhysicsBaseTasks("PhysicsApp", {name});' in source
        assert f'registerMooseAction("PhysicsApp", {name}, "check_integrity");' in source
        assert f'registerSyntax("{name}",' in (APP / "src/base/PhysicsApp.C").read_text()
        assert f"physics_app/src/physics/plasma/{name}.C" in runner
    rich_input = (CASE / "valid_all_physics.i").read_text()
    for block in ("[Energy]", "[Chemistry]", "[Poisson]", "[Maxwell]"):
        assert block in rich_input
    for filename in ("valid_bindings.i", "valid_all_physics.i", "s6_external_bindings.i"):
        assert "owner_mode" not in (CASE / filename).read_text()
    assert "owner_mode" not in (APP / "src/physics/plasma/PlasmaInterface.C").read_text()
    assert "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:" in runner
    assert "Do not change existing production simulation inputs" in runner


def test_real_solver_object_wiring():
    for name, markers in {
        "ContinuityPhysics": ["addFEKernels", "PhysicsFEMLogMolarDriftDiffusion"],
        "EnergyPhysics": ["addFEKernels", "MatBodyForce"],
        "ChemistryPhysics": ["addFunctorMaterials", "PhysicsElectronImpactRateMaterial"],
        "PoissonPhysics": ["addFEKernels", "Diffusion", "MatBodyForce", "addFEBCs"],
        "MaxwellPhysics": ["addFEKernels", "MatReaction", "MatCoupledForce", "addFEBCs"],
    }.items():
        source = (APP / f"src/physics/plasma/{name}.C").read_text()
        assert all(marker in source for marker in markers)
    assert "reaction_material = neg_a" in (CASE / "rf_generated.i").read_text()
    assert "type = MatCoupledForce" in (CASE / "rf_explicit.i").read_text()
    assert "rf_builder_parity.json" in (CASE / "run_native_binding_smoke.sh").read_text()


def test_generated_physics_requires_explicit_inputs():
    source_dir = APP / "src/physics/plasma"
    activating_parameters = {
        "ContinuityPhysics": '"fem_potential"',
        "EnergyPhysics": '"rf_heating_material"',
        "ChemistryPhysics": '"rate_table_files"',
        "PoissonPhysics": '"charge_source_material"',
        "MaxwellPhysics": '"reaction_material"',
    }
    for name, parameter in activating_parameters.items():
        source = (source_dir / f"{name}.C").read_text()
        assert parameter in source
        assert "if (!isParamValid(" in source
    maxwell = (source_dir / "MaxwellPhysics.C").read_text()
    assert "variable == real ? 1.0 : -1.0" in maxwell
    assert "getProblem().addBoundaryCondition" in maxwell
    assert "getProblem().addKernel" in maxwell


def test_duplicate_kernel_protection_and_s6_preparer():
    shared = (APP / "src/physics/plasma/PlasmaInterface.C").read_text()
    continuity = (APP / "src/physics/plasma/ContinuityPhysics.C").read_text()
    runner = (CASE / "run_native_binding_smoke.sh").read_text()
    assert "requireUniqueFEKernel" in shared
    assert "getKernelWarehouse().getObjects()" in shared
    assert "must have exactly one owner" in shared
    assert '"fem_kernel_names"' in continuity
    assert "kernel_names[i]" in continuity
    assert "duplicate_maxwell.i" in runner
    assert "PLASMA_DUPLICATE_NATIVE_KERNEL_REJECTED" in runner
    preparer = (CASE / "prepare_s6_single_kernel_migration.py").read_text()
    assert "PhysicsFEMLogMolarDriftDiffusion" in preparer
    assert 'fem_kernel_names = \'ne_transport\'' in preparer
    assert '"native_400W_100us_parity": "NOT_EVALUATED"' in preparer
    assert "original_layer_count" in preparer
