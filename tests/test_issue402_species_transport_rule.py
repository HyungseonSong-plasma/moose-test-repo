"""Source-contract proof for Issue #402 species-owned DriftDiffusion providers.

Native P1/P2 on the same exact HEAD is still required separately; these
assertions do not claim that a provider has correct physical coefficients.
"""
from pathlib import Path
import ast
import hashlib
import json


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app/src"
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"


def text(path):
    return (ROOT / path).read_text()


def test_user_drift_diffusion_transport_coefficient_options_are_removed():
    src = text("physics_app/src/physics/plasma/DDContinuityEq.C")
    params = src.split("DDContinuityEq::validParams()", 1)[1].split(
        "DDContinuityEq::DDContinuityEq(", 1)[0]
    for option in ('"mobility"', '"diffusivity"', '"fem_mobility"',
                   '"fem_diffusion"', '"variables"', '"fem_kernel_names"'):
        assert option not in params
    assert 'species[i] + "_mobility"' in src
    assert 'species[i] + "_diffusivity"' in src
    assert 'params.set<MooseFunctorName>("mobility") = species[i] + "_mobility"' in src
    assert 'params.set<MooseFunctorName>("diffusion") = species[i] + "_diffusivity"' in src
    # P04: FEM-only was the old constraint. FV-only is now valid when the
    # caller provides explicit potential/JSON transport and Chemistry sources.
    assert "Selected fem_species/fvm_species require an explicit potential" in src
    assert 'validate(_fvm_species, "fvm_species", "FVM");' in src
    assert "if (!isParamValid(\"fem_potential\"))" in src
    assert "mechanism.species(species[i]).charge_number" in src
    assert '"fem_charge_numbers"' not in src and '"fvm_charge_numbers"' not in src


def test_mean_energy_bridge_and_dd_transport_are_distinct_providers():
    mean = text("physics_app/src/materials/ElectronEnergyMaterial.C")
    dd = text("physics_app/src/materials/DDTransportMaterial.C")
    assert 'addFunctorProperty<ADReal>(\n      "e_energy_eV"' in mean
    assert '"mean_energy_output"' not in mean
    assert '"energy_reference_eV"' not in mean
    assert "electron_energy_density" in mean and "electron_density" in mean
    assert 'addFunctorProperty<ADReal>("electron_mobility", particle_mu)' in dd
    assert '"electron_energy_mobility"' in dd
    assert not (ROOT / "physics_app/src/materials/ElectronClosureMaterial.C").exists()

def test_lookup_axis_is_fixed_to_solved_mean_energy_and_aliases_are_removed():
    src = text("physics_app/src/materials/DDTransportMaterial.C")
    header = text("physics_app/include/materials/DDTransportMaterial.h")
    assert 'getFunctorByName<ADReal>("e_energy_eV")' in src
    assert 'const Moose::Functor<ADReal> * _mean_energy = nullptr;' in header
    assert '(*_mean_energy)(r, state)' in header
    for obsolete in ("ElectronTransportLookupMaterial", "PhysicsElectronTransportLookupMaterial",
                     '"coordinate"', '"mean_energy"', '"property_table_file"'):
        assert obsolete not in src
    assert '"table_file"' in src
    assert "Specify exactly one table_file or property_table_file." not in src


def test_dd_material_unifies_constant_and_lookup_with_electron_energy_projection():
    src = text("physics_app/src/materials/DDTransportMaterial.C")
    header = text("physics_app/include/materials/DDTransportMaterial.h")
    assert 'registerMooseObject("PhysicsApp", DDTransportMaterial);' in src
    assert '"lookup constant functor"' in src
    assert '"mobility"' in src and '"diffusivity"' in src
    assert 'std::make_unique<PhysicsLookupTable1D>' in src
    assert '_species + "_mobility"' in src
    assert '_species + "_diffusivity"' in src
    assert 'addFunctorProperty<ADReal>("electron_mobility", particle_mu)' in src
    assert 'addFunctorProperty<ADReal>("electron_diffusion", particle_D)' in src
    assert '"electron_energy_mobility"' in src and '"electron_energy_diffusion"' in src
    assert 'constexpr Real energy_factor = 5.0 / 3.0' in src
    assert 'return _reduced ? raw / neutralNumberDensity(r, state) : raw;' in header
    assert not (ROOT / "physics_app/src/materials/ElectronTransportLookupMaterial.C").exists()
    assert not (ROOT / "physics_app/src/materials/PhysicsElectronTransportCoefficients.C").exists()


def test_ddmaterial_is_only_canonical_species_coefficient_publisher():
    dd = text("physics_app/src/materials/DDTransportMaterial.C")
    retired = ROOT / "physics_app/src/materials/PlasmaChargeTransportMaterial.C"
    assert not retired.exists()
    assert not (ROOT / "physics_app/include/materials/PlasmaChargeTransportMaterial.h").exists()
    assert 'addFunctorProperty<ADReal>(_species + "_mobility", particle_mu)' in dd
    assert 'addFunctorProperty<ADReal>(_species + "_diffusivity", particle_D)' in dd
    assert 'getFunctor<ADReal>("mobility_source")' in dd
    assert 'getFunctor<ADReal>("diffusivity_source")' in dd
    fixture = text("experiments/Issue402_plasma_dsl_g1/charge_core_ddmaterial_owner_p2.i")
    assert fixture.count("type = DDTransportMaterial") == 3
    assert "type = PlasmaChargeTransportMaterial" not in fixture
    assert "type = PhysicsPlasmaChargeDensityMaterial" in fixture
    for sp in ("O2p", "Om", "Op"):
        assert f"functor = {sp}_mobility" in fixture
        assert f"functor = {sp}_diffusivity" in fixture
    assert "functor = poisson_charge_source" in fixture


def test_current_fv_ion_drift_remains_and_old_heavy_correction_is_retired():
    drift = text("physics_app/src/fvkernels/PhysicsFVElectrostaticDrift.C")
    assert 'const ADRealVectorValue electric_field =' in drift
    assert '-_potential.gradient(centered_face, state)' in drift
    assert 'const ADReal mobility_face = _mobility(centered_face, state);' in drift
    assert '_charge_number * mobility_face * (electric_field * _normal)' in drift
    assert 'ion_drift_velocity_' not in drift

    # Historical #15 correction formula belongs to original blob/run evidence.
    # It is not a current New-only registered Factory or an alternative drift.
    assert not (ROOT / "physics_app/src/fvkernels/PhysicsFVHeavyMassElectromigrationCorrection.C").exists()
    assert not (ROOT / "physics_app/include/fvkernels/PhysicsFVHeavyMassElectromigrationCorrection.h").exists()
    assert 'PhysicsFVHeavyMassElectromigrationCorrection' not in drift


def test_accepted_path_b_heavy_correction_reaches_solved_neutral_species():
    # Frozen historical #15 source is separate from S6-417/941; do not infer S6
    # scientific activation or transport parity from this static proof.
    flux = text("experiments/Issue15_charged_heavy_migration/physics.i")
    assert flux.count("type = QPXFVElectrostaticDrift") == 3
    assert flux.count("type = QPXFVHeavyMassElectromigrationCorrection") == 6
    for species in ("O2s", "O", "Os"):  # three independently solved neutrals
        assert f"[{species}_heavy_mass_em_correction]" in flux
        assert f"[{species}_electrostatic_drift]" not in flux
    for species in ("O2p", "Om", "Op"):
        assert f"[{species}_heavy_mass_em_correction]" in flux
        assert f"[{species}_electrostatic_drift]" in flux
    # Constrained O2 is not independently solved. Face flux, not a Material
    # vector slip alias, balances the charged-heavy mass flux.
    assert "[O2_heavy_mass_em_correction]" not in flux
    assert "heavy_mass_correction_velocity" not in flux
    assert "ion_drift_velocity_" not in flux


def test_native_control_and_public_417_941_are_user_coefficient_free():
    positive = text("experiments/Issue402_plasma_dsl_g1/valid_generated_transport_options.i")
    # Species IDs trigger Material generation from the JSON, not user blocks.
    assert "files = plasma_auto_constant.json" in positive
    assert "[FunctorMaterials]" not in positive
    payload = json.loads(text("experiments/Issue402_plasma_dsl_g1/plasma_auto_constant.json"))
    coefficient = payload["species"]["e"]
    assert {k: coefficient[k] for k in ("transport_coef", "mobility", "diffusivity")} == {
        "transport_coef": "constant", "mobility": 1, "diffusivity": 1
    }
    assert "transport_coefficients" not in payload
    py = text("experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py")
    tree = ast.parse(py)
    overlay = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == "OVERLAY"
                       for target in node.targets))
    assert overlay.count("type = DDTransportMaterial") == 3
    assert overlay.count("model = functor") == 3
    assert "mobility =" not in overlay and "diffusivity =" not in overlay
    assert "fem_species = 'e'" in overlay
    assert "fvm_species = 'O2p Om Op'" in overlay
    assert "legacy_s6_state_names" not in overlay
    for species, source in (("O2p", "ion"), ("Om", "negative_ion"),
                            ("Op", "atomic_positive_ion")):
        assert f"species_id = {species}" in overlay
        assert f"mobility_source = {source}_mobility" in overlay
        assert f"diffusivity_source = {source}_diffusion" in overlay
    assert hashlib.sha256(overlay.encode()).hexdigest() == (
        "edf3f8e8194927e93783d136066799d60df2673af9245d6d4b990fb7d267b513"
    )
    # Protected original P3 inputs and their native old provider spelling
    # remain outside this migration PR.
    source = text("experiments/Issue402_plasma_dsl_g1/prepare_s6_single_kernel_migration.py")
    assert '"electron_diffusion"' in source
    assert "ne_transport" in source

def test_json_owned_signed_charge_reaches_fem_residual_with_mutation_sentinels():
    """P0 source/sign contract, not signed-drift Native P3 or scientific parity.

    The retired positional charge-vector negative rejects an obsolete option;
    it is NOT a physical charge-sign test. This independent gate verifies the
    JSON -> generated parameter -> FEM signed-flux source path.
    """
    import copy

    mechanism = json.loads(text(
        "experiments/Issue402_plasma_dsl_g1/plasma_species_initial_p2.json"))
    continuity = text("physics_app/src/physics/plasma/DDContinuityEq.C")
    energy = text("physics_app/src/physics/plasma/DDEnergyEq.C")
    kernel = text("physics_app/src/kernels/FEMPlasmaTransport.C")
    retired = text("experiments/Issue402_plasma_dsl_g1/invalid_wrong_charge_sign.i")

    expected_signs = {"e": -1, "O2p": 1, "Om": -1, "Op": 1}
    signed_source = (
        "D * grad_c + _charge_number * mu * c * _grad_potential[_qp]"
    )
    continuity_source = (
        'params.set<Real>("charge_number") = '
        'mechanism.species(species[i]).charge_number;'
    )
    energy_source = (
        'transport.set<Real>("charge_number") = '
        'chemistryData().species("e").charge_number;'
    )

    def p0_charge_path(data, dd, energy_dd, transport):
        signs = {name: data["species"][name]["charge_number"]
                 for name in expected_signs}
        return (
            signs == expected_signs
            and continuity_source in dd
            and energy_source in energy_dd
            and signed_source in transport
            and 'params.addRequiredParam<Real>("charge_number"' in transport
            and 'paramError("charge_number", "Drift-diffusion requires nonzero charge_number.")'
            in transport
            and '"fem_charge_numbers"' not in dd
            and '"fvm_charge_numbers"' not in dd
        )

    assert p0_charge_path(mechanism, continuity, energy, kernel)
    wrong_e = copy.deepcopy(mechanism)
    wrong_e["species"]["e"]["charge_number"] = 1
    assert not p0_charge_path(wrong_e, continuity, energy, kernel)
    wrong_om = copy.deepcopy(mechanism)
    wrong_om["species"]["Om"]["charge_number"] = 1
    assert not p0_charge_path(wrong_om, continuity, energy, kernel)
    assert not p0_charge_path(mechanism, continuity.replace(
        continuity_source, 'params.set<Real>("charge_number") = 1.0;', 1
    ), energy, kernel)
    assert not p0_charge_path(mechanism, continuity, energy, kernel.replace(
        signed_source,
        "D * grad_c - _charge_number * mu * c * _grad_potential[_qp]", 1
    ))

    # In E=-grad(phi), the sign of z changes drift direction for positive mu.
    def physical_drift(charge: int, mobility=2.0, concentration=3.0, electric_field=1.0):
        return charge * mobility * concentration * electric_field
    assert physical_drift(expected_signs["e"]) == -6.0
    assert physical_drift(expected_signs["O2p"]) == 6.0
    assert physical_drift(expected_signs["Om"]) == -6.0

    # Classify the historical negative for what it actually proves.
    assert "fem_charge_numbers = '1'" in retired
    assert "fvm_charge_numbers = '1'" in retired
    assert "files = plasma_species_only.json" not in retired
