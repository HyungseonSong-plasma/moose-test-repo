"""FEM Poisson AD Functor coupling and single-source guard (Issue #402)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app/src/physics/plasma/PoissonEq.C"
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"


def test_poisson_generates_functor_rhs_with_correct_sign_and_block():
    source = APP.read_text()
    assert 'params.addParam<MooseFunctorName>(' in source
    assert '"charge_source_functor"' in source
    assert 'const std::string type = "FunctorKernel";' in source
    assert 'params.set<MooseFunctorName>("functor") =' in source
    assert 'getParam<MooseFunctorName>("charge_source_functor")' in source
    assert 'params.set<bool>("functor_on_rhs") = true;' in source
    assert 'assignBlocks(params, _blocks);' in source
    assert 'getProblem().addKernel(type, name() + "_charge_source", params);' in source
    assert 'requireUniqueFEKernel(' in source
    assert 'isParamValid("charge_source_functor") ? "FunctorKernel" : "MatBodyForce"' in source


def test_poisson_accepts_one_source_mode_and_retains_legacy_material_path():
    source = APP.read_text()
    assert '"charge_source_material"' in source
    assert 'isParamValid("charge_source_material") && isParamValid("charge_source_functor")' in source
    assert '"Poisson may have only one charge RHS owner' in source
    assert 'const std::string type = "MatBodyForce";' in source
    assert 'params.set<MaterialPropertyName>("material_property")' in source
    assert 'getProblem().addBoundaryCondition(type, name() + "_ground_" + boundary, params);' in source


def test_charge_density_material_is_actual_functor_owner_and_p2_inputs_are_typed():
    charge = (ROOT / "physics_app/src/materials/PhysicsPlasmaChargeDensityMaterial.C").read_text()
    assert 'addFunctorProperty<ADReal>(\n      "poisson_charge_source"' in charge
    assert 'return PHYSICS_CONSTANTS::e * n_charge / PHYSICS_CONSTANTS::eps_0;' in charge
    good = (PILOT / "valid_fem_poisson_charge_functor_p2.i").read_text()
    bad = (PILOT / "invalid_fem_poisson_dual_source_p2.i").read_text()
    assert "type = PhysicsPlasmaChargeDensityMaterial" in good
    assert "charge_source_functor = poisson_charge_source" in good
    assert "ground_boundaries = 'left right'" in good
    assert "charge_source_material" not in good
    assert "charge_source_material = legacy_charge_property" in bad
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert "valid_fem_poisson_charge_functor_p2.i" in runner
    assert "invalid_fem_poisson_dual_source_p2.i" in runner
    assert "PLASMA_FEM_POISSON_CHARGE_FUNCTOR_P2_PASS" in runner
    assert "PLASMA_FEM_POISSON_DUAL_SOURCE_REJECTED" in runner
