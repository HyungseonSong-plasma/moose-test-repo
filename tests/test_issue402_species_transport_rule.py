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
    assert "Generated FEM transport requires FEM species." in src
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


def test_fv_ion_and_heavy_mass_correction_do_not_consume_derived_velocities():
    drift = text("physics_app/src/fvkernels/PhysicsFVElectrostaticDrift.C")
    heavy = text("physics_app/src/fvkernels/PhysicsFVHeavyMassElectromigrationCorrection.C")
    assert 'const ADRealVectorValue electric_field =' in drift
    assert '-_potential.gradient(centered_face, state)' in drift
    assert 'const ADReal mobility_face = _mobility(centered_face, state);' in drift
    assert '_charge_number * mobility_face * (electric_field * _normal)' in drift
    assert 'ion_drift_velocity_' not in drift
    assert 'heavy_mass_correction_velocity' not in heavy
    assert '(*_ion_mobilities[i])(centered_face, state)' in heavy
    assert 'const ADReal correction_mass_flux_normal =' in heavy
    assert '-direct_mass_flux_normal;' in heavy


def test_accepted_path_b_heavy_correction_reaches_solved_neutral_species():
    # Accepted #15 source is separate from S6-417/941; do not infer S6
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
