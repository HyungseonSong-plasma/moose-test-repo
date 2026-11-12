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
    mean = text("physics_app/src/materials/PhysicsElectronMeanEnergyMaterial.C")
    dd = text("physics_app/src/materials/DDMaterial.C")
    assert 'getParam<MooseFunctorName>("mean_energy_output")' in mean
    assert "electron_energy_density" in mean and "electron_density" in mean
    assert 'addFunctorProperty<ADReal>("electron_mobility", particle_mu)' in dd
    assert '"electron_energy_mobility"' in dd
    assert not (ROOT / "physics_app/src/materials/ElectronClosureMaterial.C").exists()

def test_dd_material_unifies_constant_and_lookup_with_electron_energy_projection():
    src = text("physics_app/src/materials/DDMaterial.C")
    header = text("physics_app/include/materials/DDMaterial.h")
    assert 'registerMooseObject("PhysicsApp", DDMaterial);' in src
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
    # Species IDs trigger Material generation from the JSON, not user blocks.
    assert "files = plasma_auto_constant.json" in positive
    assert "[FunctorMaterials]" not in positive
    payload = json.loads(text("experiments/Issue402_plasma_dsl_g1/plasma_auto_constant.json"))
    coefficient = payload["transport_coefficients"]["drift_diffusion"]["e"]
    assert coefficient == {"model": "constant", "mobility": 1, "diffusivity": 1}
    py = text("experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py")
    tree = ast.parse(py)
    overlay = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == "OVERLAY"
                       for target in node.targets))
    assert overlay.count("type = DDMaterial") == 3
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
        "dcac4502c6bece4481651f97879699c27be994c97a6b09ad4443aca9c2edd544"
    )
    # Protected original P3 inputs and their native old provider spelling
    # remain outside this migration PR.
    source = text("experiments/Issue402_plasma_dsl_g1/prepare_s6_single_kernel_migration.py")
    assert '"electron_diffusion"' in source
    assert "ne_transport" in source
