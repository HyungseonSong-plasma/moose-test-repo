"""G4 New-only Poisson FEM operator source contract, no Native run claimed."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
CHEM = PILOT / "chemistry"
POISSON = APP / "src/physics/plasma/PoissonEq.C"


def source():
    return POISSON.read_text()


@pytest.mark.parametrize("case", ("417", "941"))
def test_native_parity_eight_blocks_five_material_groups(case):
    json_data = json.loads((CHEM / f"unified_s6_{case}_newonly.json").read_text())
    eps = json_data["poisson"]["relative_permittivity"]
    assert eps == {
        "plasma": 1, "cover": 3.6, "wafer": 12.5,
        "focus_ring": 8, "vacuum": 1, "coil1": 1, "coil2": 1, "coil3": 1
    }
    native = (PILOT / "native/s6_c0_physics_base_no_d1.i").read_text()
    for group, value in (
        ("plasma", "1.0"), ("cover", "3.6"), ("wafer", "12.5"),
        ("focus_ring", "8.0"), ("vacuum", "1.0")
    ):
        chunk = native.split(f"[eps_{group}]", 1)[1].split("  []", 1)[0]
        assert "type = ADGenericConstantMaterial" in chunk
        assert f"prop_values = '{value}'" in chunk
    assert "block = 'vacuum coil1 coil2 coil3'" in native
    g4 = source().split("void\nPoissonEq::addMaterials()", 1)[1].split(
        "using Plasma::PoissonEq", 1)[0]
    for name in ("plasma", "cover", "wafer", "focus_ring", "vacuum"):
        assert f'{{"{name}", ' in g4
    assert '{"vacuum", {"vacuum", "coil1", "coil2", "coil3"}}' in g4
    assert 'getProblem().addMaterial(type, name() + "_eps_" + group.id, params);' in g4
    assert 'params.set<std::vector<std::string>>("prop_names") = {"relative_permittivity"};' in g4
    assert 'params.set<std::vector<Real>>("prop_values") = {epsilon};' in g4
    assert 'params.set<std::vector<std::string>>("prop_values")' not in g4
    assert 'params.set<std::vector<SubdomainName>>("block") = group.blocks;' in g4


@pytest.mark.parametrize("case", ("417", "941"))
def test_newonly_exact_11_plus_3_bc_geometry_parity(case):
    doc = json.loads((CHEM / f"unified_s6_{case}_newonly.json").read_text())
    boundary = doc["poisson"]["boundaries"]
    assert len(boundary["ground"]) == 11
    assert len(set(boundary["ground"])) == 11
    assert boundary["surface_charge"] == {
        "plasma_cover": "sigma_s",
        "plasma_wafer": "sigma_wafer",
        "plasma_focus_ring": "sigma_focus_ring",
    }
    native = (PILOT / "native/s6_c0_physics_base_no_d1.i").read_text()
    ground = native.split("[grounded_potential]", 1)[1].split("  []", 1)[0]
    assert set(ground.split("boundary = '", 1)[1].split("'", 1)[0].split()) == set(boundary["ground"])
    for side, sigma in boundary["surface_charge"].items():
        assert f"boundary = {side}\n    surface_charge = {sigma}" in native


def test_generated_kernels_use_eight_block_ad_material_diffusion_and_plasma_rhs():
    g4 = source().split("void\nPoissonEq::addFEKernels()", 1)[1].split(
        "void\nPoissonEq::addFEBCs()", 1)[0]
    assert "if (const auto * model = chemistryData().poisson())" in g4
    modern = g4.split("if (const auto * model = chemistryData().poisson())", 1)[1].split(
        "\n    return;\n  }", 1)[0]
    assert 'const std::string type = "ADMatDiffusion";' in modern
    assert 'params.set<MaterialPropertyName>("diffusivity") = "relative_permittivity";' in modern
    assert "assignBlocks(params, poissonBlocks(*model));" in modern
    assert 'const std::string type = "FunctorKernel";' in modern
    assert 'params.set<MooseFunctorName>("functor") = "poisson_source";' in modern
    assert 'params.set<bool>("functor_on_rhs") = true;' in modern
    assert 'assignBlocks(params, {"plasma"});' in modern
    assert 'const std::string type = "Diffusion";' in g4  # Legacy still present outside new branch
    assert 'const std::string type = "MatBodyForce";' in g4


def test_one_ground_owner_three_lower_d_coupled_bcs():
    g4 = source().split("void\nPoissonEq::addFEBCs()", 1)[1].split(
        "void\nPoissonEq::addMaterials()", 1)[0]
    assert 'name() + "_grounded_potential"' in g4
    assert 'const std::string type = "DirichletBC";' in g4
    assert 'model->ground_boundaries' in g4
    assert 'ground.set<Real>("value") = 0.0;' in g4
    assert 'const std::string surface_type = "PhysicsADSurfaceChargePoissonBC";' in g4
    assert 'params.set<std::vector<VariableName>>("surface_charge") = {sigma};' in g4
    assert 'getProblem().addBoundaryCondition(' in g4
    assert '"surface_charge") = {sigma};' in g4
    assert 'params.set<MooseFunctorName>("surface_charge")' not in g4


def test_no_legacy_activation_or_native_source_retirement_at_g4():
    src = source()
    header = (APP / "include/physics/plasma/PoissonEq.h").read_text()
    template = (PILOT / "issue633_newonly_s6_417_continuity.template.i").read_text()
    native = (PILOT / "native/s6_c0_physics_base_no_d1.i").read_text()
    assert 'void addMaterials() override;' in header
    assert src.index("PoissonEq::addMaterials()") < src.index("} // namespace Plasma")
    assert 'registerMooseAction("PhysicsApp", PoissonEq, "add_materials_physics");' in src
    assert 'requireUniqueFEKernel("ADMatDiffusion", potential);' in src
    assert 'requireUniqueFEKernel("FunctorKernel", potential);' in src
    assert 'if (chemistryData().poisson())' in src
    assert 'if (!isParamValid("charge_source_material") &&' in src
    assert '"charge_source_material"' in src
    assert '"charge_source_functor"' in src
    assert 'params.set<MooseFunctorName>("functor") =' in src
    assert "[Poisson]" not in template
    for old in ("[phi_diffusion]", "[phi_source]", "[grounded_potential]",
                "[cover_surface_charge_poisson]", "[wafer_surface_charge_poisson]",
                "[focus_ring_surface_charge_poisson]"):
        assert old in native
    assert 'getProblem().addFunctorMaterial(' not in src


def test_runtime_parser_rejects_epsilon_drift_even_if_python_stage_bypassed():
    parser = (APP / "src/physics/plasma/Chemistry.C").read_text()
    assert 'const std::map<std::string, double> expected_eps' in parser
    assert 'value != expected_eps.at(it.key())' in parser
