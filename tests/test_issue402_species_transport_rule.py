"""Source-contract proof for Issue #402 species-owned DriftDiffusion providers.

Native P1/P2 on the same exact HEAD is still required separately; these
assertions do not claim that a provider has correct physical coefficients.
"""
from pathlib import Path
import ast
import hashlib


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


def test_electron_closure_keeps_old_and_new_functors_same_numeric_closure():
    src = text("physics_app/src/materials/ElectronClosureMaterial.C")
    for old in ('"electron_mobility_output"', '"electron_diffusion_output"'):
        assert old in src
    assert 'addFunctorProperty<ADReal>("e_mobility", particle_mobility)' in src
    assert 'addFunctorProperty<ADReal>("e_diffusivity", particle_diffusivity)' in src
    assert 'addFunctorProperty<ADReal>(legacy_mobility, particle_mobility)' in src
    assert 'addFunctorProperty<ADReal>(legacy_diffusivity, particle_diffusivity)' in src
    assert 'legacy_mobility != "e_mobility"' in src
    assert 'legacy_diffusivity != "e_diffusivity"' in src
    assert "interpolate(mean_energy(r, state), 0) / neutral_density(r, state)" in src
    assert "interpolate(mean_energy(r, state), 1) / neutral_density(r, state)" in src


def test_dd_material_unifies_constant_and_lookup_with_electron_energy_projection():
    src = text("physics_app/src/materials/DDMaterial.C")
    header = text("physics_app/include/materials/DDMaterial.h")
    assert 'registerMooseObject("PhysicsApp", DDMaterial);' in src
    assert '"lookup constant"' in src
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


def test_ion_aliases_are_unscaled_ad_functors_and_do_not_replace_rho_diffusion():
    src = text("physics_app/src/materials/PlasmaChargeTransportMaterial.C")
    assert 'id + "_mobility"' in src
    assert 'id + "_diffusivity"' in src
    assert "(*_ion_mobilities[i])(r, state)" in src
    assert "(*_ion_diffusions[i])(r, state)" in src
    # D [m²/s] must not silently become rho*D [kg/(m s)].
    assert '"rho_diffusivity_" + id' in src
    assert "_density(r, state) * (*_ion_diffusions[i])(r, state)" in src


def test_native_control_and_public_417_941_are_user_coefficient_free():
    positive = text("experiments/Issue402_plasma_dsl_g1/valid_generated_transport_options.i")
    # Constant species transport now comes from the sole DD coefficient owner.
    assert "type = DDMaterial" in positive
    assert "model = constant" in positive
    assert "species_id = e" in positive
    assert "mobility = 1" in positive and "diffusivity = 1" in positive
    assert "SpeciesTransportAliasMaterial" not in positive
    py = text("experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py")
    tree = ast.parse(py)
    overlay = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == "OVERLAY"
                       for target in node.targets))
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
        "14288d9f0686f26cde86888824babc468016ece99188114ded31b8e5bd360d9a"
    )
    # Protected original P3 inputs and their native old provider spelling
    # remain outside this migration PR.
    source = text("experiments/Issue402_plasma_dsl_g1/prepare_s6_single_kernel_migration.py")
    assert '"electron_diffusion"' in source
    assert "ne_transport" in source
