"""Check the plasma input validation classes and example inputs.

These tests do not replace building or running the solver.
"""
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
CASE = ROOT / "experiments/Issue402_plasma_dsl_g1"


def sources():
    base_header = (APP / "include/physics/plasma/PlasmaInterface.h").read_text()
    base_source = (APP / "src/physics/plasma/PlasmaInterface.C").read_text()
    header = (APP / "include/physics/plasma/DDContinuityEq.h").read_text()
    source = (APP / "src/physics/plasma/DDContinuityEq.C").read_text()
    app = (APP / "src/base/PhysicsApp.C").read_text()
    return base_header, base_source, header, source, app


def test_continuity_uses_shared_plasma_validation():
    base_header, base_source, header, source, app = sources()
    assert "class PlasmaInterface : public PhysicsBase" in base_header
    assert "class DDContinuityEq : public PlasmaInterface" in header
    assert "namespace Plasma" in header
    assert "void checkIntegrity() const override;" in header
    assert "validateSpeciesInputs(" in base_source
    assert "validateExistingSpeciesVariables(" in base_source
    assert "validateSpeciesInputs(" in source
    assert "validateExistingSpeciesVariables(" in source
    assert "using Plasma::DDContinuityEq;" in source
    assert 'registerPhysicsBaseTasks("PhysicsApp", DDContinuityEq);' in source
    assert 'registerMooseAction("PhysicsApp", DDContinuityEq, "check_integrity");' in source
    assert 'registerSyntax("DDContinuityEq",' in app
    assert '"Physics/Plasmas/Transport/DriftDiffusion/Continuity"' in app
    assert "PlasmaClosuresAction" not in app
    assert "PlasmaClosures/*" not in app
    assert not (APP / "src/actions/PlasmaClosuresAction.C").exists()
    assert not (APP / "include/actions/PlasmaClosuresAction.h").exists()
    assert 'GummelIterationAction' not in app
    assert 'GummelIteration/*' not in app


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
    assert 'paramError("variables"' not in base_source
    assert 'paramError(is_finite_volume ? "fvm_species" : "fem_species"' in base_source
    assert "isVariableFV(variable)" in base_source
    # Shared input validation never creates solver objects.
    assert "getProblem().add" not in base_source

    # Continuity uses the shared JSON species charges, and derived coefficient Functors.
    assert 'if (!isParamValid("fem_potential"))' in source
    assert '"mobility", "Species-ordered' not in source
    assert '"diffusivity", "Species-ordered' not in source
    assert 'species[i] + "_mobility"' in source
    assert 'species[i] + "_diffusivity"' in source
    assert '"fvm_charge_numbers"' not in source
    assert '"fem_mobility"' not in source
    assert '"fem_diffusion"' not in source
    assert '"fem_kernel_names"' not in source
    assert '"variables"' not in source
    assert 'params.set<MooseFunctorName>("diffusion") = species[i] + "_diffusivity"' in source
    assert 'species[i] + "_transport"' in source
    assert 'return "log_" + species;' in source
    assert '"legacy_s6_state_names"' not in source
    assert 'legacyS6StateName' not in source
    assert 'return "log_" + species;' in source
    assert 'resolved.push_back(continuityStateName(species));' in source
    assert '"fem_charge_numbers"' not in source
    assert "getProblem().addKernel(" in source
    assert "FEMLogMolarDriftDiffusion" in source
    assert "schema_version" not in base_source + source
    assert '"discretization"' not in base_source + source



def test_continuity_e_time_is_generated_from_existing_species_without_new_options():
    """Generated e_time must reuse the exact Native conservative time operator."""
    _, _, _, source, _ = sources()
    kernel = (APP / "src/kernels/FEMPlasmaTransport.C").read_text()
    pilot = (CASE / "public_option_s6_p2.py").read_text()
    runner = (CASE / "run_native_binding_smoke.sh").read_text()

    assert 'const std::string time_type = "FEMLogMolarTimeDerivative";' in source
    assert 'time_params.set<NonlinearVariableName>("variable") = variables[i];' in source
    assert 'assignBlocks(time_params, _blocks);' in source
    assert 'getProblem().addKernel(time_type, species[i] + "_time", time_params);' in source
    assert 'requireUniqueFEKernel("FEMLogMolarTimeDerivative", variables[i]);' in source
    assert 'requireUniqueFEKernel("FEMLogMolarDriftDiffusion", variables[i]);' in source
    assert 'if (!isParamValid("fem_potential"))' in source
    assert 'params.addParam<bool>("generate_time"' not in source
    assert "FEMLogMolarTimeDerivative::computeQpResidual()" in kernel
    fixture = (CASE / "valid_generated_transport_options.i").read_text()
    assert "type = Transient" in fixture
    assert "num_steps = 1" in fixture
    for old in ("PhysicsFEMLogMolarTimeDerivative", "PhysicsFEMLogMolarDriftDiffusion", "PhysicsFEMLogMolarElectronJouleHeating"):
        assert old not in kernel
    assert "(exp(_u[_qp]) - exp(_u_old[_qp])) / _dt" in kernel

    assert "Original ne_time parameters differ from pinned Native S6" in pilot
    assert "Expected exactly one original ne_time in staged S6 D" in pilot
    assert '"generated_name": "e_time"' in pilot
    assert "SCRATCH_ONLY_CANONICAL_STATE_AND_TIME_OWNER_REWRITE" in pilot

    duplicate = (CASE / "duplicate_e_time.i").read_text()
    assert "type = FEMLogMolarTimeDerivative" in duplicate
    assert "variable = log_e" in duplicate
    assert "duplicate_e_time.i" in runner
    assert "PLASMA_DUPLICATE_E_TIME_REJECTED" in runner



def test_small_example_has_finite_element_and_finite_volume_equations():
    text = (CASE / "baseline.i").read_text()
    assert "[log_e]" in text and "family = LAGRANGE" in text
    assert "[log_O2p]" in text and "type = MooseVariableFVReal" in text
    assert "type = Diffusion" in text
    assert "type = FVDiffusion" in text
    assert "type = FVDirichletBC" in text
    assert "[Executioner]" in text and "type = Steady" in text


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("valid_bindings.i", "fem_species = 'e'"),
        ("invalid_overlap.i", "fem_species = 'e O2p'"),
        ("invalid_fem_fv_swap.i", "fem_species = 'O2p'"),
        ("invalid_no_species.i", "[Continuity]"),
        ("invalid_missing_variable.i", "fem_species = 'missing'"),
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
    assert "invalid_legacy_variables invalid_legacy_kernel_names invalid_missing_fvm_charges" in runner
    assert "invalid_incomplete_coefficients invalid_wrong_charge_sign" in runner
    assert "PLASMA_OPTION_ONLY_FEM_GENERATION_P2_PASS" in runner
    positive = (CASE / "valid_generated_transport_options.i").read_text()
    assert "[FunctorMaterials]" not in positive
    assert "mobility =" not in positive and "diffusivity =" not in positive
    assert "files = plasma_auto_constant.json" in positive
    json_config = json.loads((CASE / "plasma_auto_constant.json").read_text())
    assert json_config["transport_coefficients"]["drift_diffusion"]["e"] == {
        "model": "constant", "mobility": 1, "diffusivity": 1
    }
    assert "fem_charge_numbers" not in positive
    assert "fem_kernel_names" not in positive and "variables =" not in positive
    assert "sha256sum" in runner
    assert "physics_app/src/physics/plasma/PlasmaInterface.C" in runner
    assert "physics_app/src/physics/plasma/DDContinuityEq.C" in runner
    assert "generic_four_species.i" in runner
    assert "PLASMA_GENERIC_SPECIES_STATE_NAMES_P2_PASS" in runner
    generic = (CASE / "generic_four_species.i").read_text()
    for state in ("log_e", "log_O2p", "log_Om", "log_Op"):
        assert f"[{state}]" in generic
    assert "legacy_s6_state_names" not in generic
    assert "legacy_s6_state_names" not in (CASE / "s6_external_bindings.i").read_text()
    for name in ("DDEnergyEq", "Chemistry", "PoissonPhysics", "MaxwellPhysics"):
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
        "DDContinuityEq": ["addFEKernels", "FEMLogMolarDriftDiffusion"],
        "DDEnergyEq": ["addFEKernels", "MatBodyForce"],
        "Chemistry": ["addFunctorMaterials", "ADParsedFunctorMaterial"],
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
        "DDContinuityEq": '"fem_potential"',
        "DDEnergyEq": '"rf_heating_material"',
        "PoissonPhysics": '"charge_source_material"',
        "MaxwellPhysics": '"reaction_material"',
    }
    for name, parameter in activating_parameters.items():
        source = (source_dir / f"{name}.C").read_text()
        assert parameter in source
        if name != "DDEnergyEq":
            assert "if (!isParamValid(" in source
        else:
            assert 'if (isParamValid("rf_heating_material"))' in source
    chemistry = (source_dir / "Chemistry.C").read_text()
    assert "chemistryData().reactions().empty()" in chemistry
    assert '"Q_e_molar_eV"' in chemistry
    maxwell = (source_dir / "MaxwellPhysics.C").read_text()
    assert "variable == real ? 1.0 : -1.0" in maxwell
    assert "getProblem().addBoundaryCondition" in maxwell
    assert "getProblem().addKernel" in maxwell


def test_duplicate_kernel_protection_and_s6_preparer():
    shared = (APP / "src/physics/plasma/PlasmaInterface.C").read_text()
    continuity = (APP / "src/physics/plasma/DDContinuityEq.C").read_text()
    runner = (CASE / "run_native_binding_smoke.sh").read_text()
    assert "requireUniqueFEKernel" in shared
    assert "getKernelWarehouse().getObjects()" in shared
    assert "must have exactly one owner" in shared
    assert '"fem_kernel_names"' not in continuity
    assert 'species[i] + "_transport"' in continuity
    assert "duplicate_maxwell.i" in runner
    assert "PLASMA_DUPLICATE_NATIVE_KERNEL_REJECTED" in runner
    preparer = (CASE / "prepare_s6_single_kernel_migration.py").read_text()
    assert "PhysicsFEMLogMolarDriftDiffusion" in preparer
    assert 'fem_kernel_names = \'ne_transport\'' in preparer
    assert '"native_400W_100us_parity": "NOT_EVALUATED"' in preparer
    assert "original_layer_count" in preparer


def test_archived_s6_single_kernel_migration_from_synthetic_zip(tmp_path):
    """The preparer must copy all ten sources and move exactly one kernel."""
    import json
    import runpy
    import zipfile

    preparation = runpy.run_path(str(CASE / "prepare_s6_single_kernel_migration.py"))
    prepare = preparation["prepare"]
    original_kernel = """  [ne_transport]
    type = PhysicsFEMLogMolarDriftDiffusion
    variable = log_ne
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    charge_number = -1
    block = plasma
  []
"""
    base = "[Kernels]\n" + original_kernel + "[]\n"
    for branch in ("417", "941"):
        case = f"S6-{branch}-407-2069-H25"
        names = ["base.i"] + [f"layer_{i}.i" for i in range(1, 10)]
        archive = tmp_path / f"{branch}.zip"
        manifest = {
            "case": case,
            "source_sha": "29d1acc6ef7969908b86719e4b95c73a1565136d",
            "science_acceptance": "HOLD",
            "power_W": 400,
            "expected_native_steps": 460,
            "input_paths": names,
        }
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(f"results/{case}/case_manifest.json", json.dumps(manifest))
            for name in names:
                bundle.writestr(name, base if name == "base.i" else f"# {name}\n")
        report = prepare(archive, tmp_path / "prepared")
        root = tmp_path / "prepared" / case
        assert report["static_operator_mapping"] == "MATCH"
        assert report["native_400W_100us_parity"] == "NOT_EVALUATED"
        assert original_kernel in (root / "baseline" / "base.i").read_text()
        assert original_kernel not in (root / "candidate" / "base.i").read_text()
        assert "fem_kernel_names = 'ne_transport'" in (
            root / "candidate" / "migrated_continuity.i"
        ).read_text()
        for name in names[1:]:
            assert (root / "baseline" / name).read_bytes() == (
                root / "candidate" / name
            ).read_bytes()


def test_full_s6_gate_never_uses_private_secrets_in_pr_ci():
    runner = (CASE / "run_s6_full_native_parity.py").read_text()
    assert "OXYGEN24_RATES_TAR_XZ_B64" not in runner
    assert "check_prepared_workspace" in runner
    assert "ARCHIVE_DIGESTS" in runner
    assert "461" in runner and "0.0001" in runner
    assert 'source_root / CHEM / "private_rates" / name' in runner
    assert "check_native_timesteps" in runner
    assert "compare_diagnostics" in runner
    assert "historical_vs_new_baseline" in runner
    assert "new_baseline_vs_migration" in runner
    assert "BOTH_S6_460_STEP_NATIVE_PARITY_PASS__SCIENCE_HOLD" in runner
    assert "S6_FULL_NATIVE_PARITY_NOT_PROVEN" in runner


def test_full_s6_runner_import_and_460_step_assertion(tmp_path):
    """Verify the replay gate is executable and rejects incomplete histories."""
    import importlib.util
    import sys

    import numpy as np
    import pytest
    from scipy.io import netcdf_file

    runner_path = CASE / "run_s6_full_native_parity.py"
    spec = importlib.util.spec_from_file_location("issue402_native_s6_gate", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(CASE))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(CASE))

    good = tmp_path / "original.e"
    with netcdf_file(good, "w") as exodus:
        exodus.createDimension("time_step", 461)
        variable = exodus.createVariable("time_whole", "f8", ("time_step",))
        variable[:] = np.linspace(0.0, 0.0001, 461)
    assert module.check_native_timesteps(good)["timepoints"] == 461

    incomplete = tmp_path / "incomplete.e"
    with netcdf_file(incomplete, "w") as exodus:
        exodus.createDimension("time_step", 460)
        variable = exodus.createVariable("time_whole", "f8", ("time_step",))
        variable[:] = np.linspace(0.0, 0.0001, 460)
    with pytest.raises(ValueError, match="460-step"):
        module.check_native_timesteps(incomplete)


def test_full_s6_runner_checks_csv_diagnostics(tmp_path):
    """A mismatched diagnostic must invalidate full numerical parity."""
    import importlib.util
    import sys

    import pytest

    runner_path = CASE / "run_s6_full_native_parity.py"
    spec = importlib.util.spec_from_file_location("issue402_native_s6_csv_gate", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(CASE))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(CASE))

    old = tmp_path / "before.csv"
    new = tmp_path / "after.csv"
    data = "time,power\n" + "".join(
        f"{i / 460 * 0.0001:.15g},400\n" for i in range(461)
    )
    old.write_text(data)
    new.write_text(data)
    assert module.compare_diagnostics(old, new, 1e-11, 1e-12)["diagnostic_rows"] == 461
    new.write_text(data.replace(",400\n", ",401\n", 1))
    with pytest.raises(ValueError, match="diagnostic differs"):
        module.compare_diagnostics(old, new, 1e-11, 1e-12)


def test_continuity_option_contract_rejects_legacy_keys():
    """The generated C++ schema must not accept the old user-facing options."""
    _, _, _, source, _ = sources()
    for old in ('"variables"', '"fem_kernel_names"', '"fvm_kernel_names"',
                '"fem_mobility"', '"fem_diffusion"', '"fvm_mobility"',
                '"fvm_diffusion"'):
        assert old not in source
    for retired in ('"fem_charge_numbers"', '"fvm_charge_numbers"'):
        assert retired not in source
    assert 'params.set<MooseFunctorName>("mobility") = species[i] + "_mobility"' in source
    assert 'params.set<MooseFunctorName>("diffusion") = species[i] + "_diffusivity"' in source
    assert 'const std::string kernel_name = species[i] + "_transport";' in source
    assert 'return "log_" + species;' in source
    # Canonical-only resolution must not branch on known species IDs.
    for species, name in (("O2p", "log_ni"), ("Om", "log_nm"), ("Op", "log_nop")):
        assert f'if (species == "{species}")' not in source
        assert f'return "{name}"' not in source


@pytest.mark.parametrize(
    "fixture,option",
    [
        ("invalid_legacy_variables.i", "variables"),
        ("invalid_legacy_kernel_names.i", "fem_kernel_names"),
        ("invalid_missing_fvm_charges.i", "fem_charge_numbers"),
        ("invalid_incomplete_coefficients.i", "diffusivity"),
        ("invalid_wrong_charge_sign.i", "fem_charge_numbers"),
    ],
)
def test_native_negative_option_cases_exist(fixture, option):
    text = (CASE / fixture).read_text()
    assert "[Continuity]" in text
    assert option in text


def test_small_s6_binding_stays_alias_compatible():
    deck = (CASE / "s6_external_bindings.i").read_text()
    assert "fem_species = 'e'" in deck
    assert "fvm_species = 'O2p Om Op'" in deck
    assert "variables =" not in deck
    # The archived S6 preparer is intentionally left unchanged: the
    # legacy source and provider names are immutable P3 evidence.
    preparer = (CASE / "prepare_s6_single_kernel_migration.py").read_text()
    assert "fem_kernel_names = 'ne_transport'" in preparer
    assert '"diffusion": "electron_diffusion"' in preparer
