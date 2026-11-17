"""Issue #633 synthetic C2 P2: exact ion equation and typed BC handoff.

P0 checks only. The separate same-head native CI job must actually run
physics-opt --check-input before the P2 gate can be promoted.
"""
import json
from pathlib import Path

from ci.p1_ion_new_only_preflight import inspect
from ci.guards.issue633_c2_json_wiring import validate

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
DECK = PILOT / "issue633_ion_continuity_wall_bc_newonly_p2.i"
CHEM = PILOT / "issue633_ion_continuity_newonly_p2.json"
C2 = ROOT / "physics_app/ci/issue633_c2_wall_3ion_overlay.json"
RUNNER = PILOT / "run_native_binding_smoke.sh"

SIDES = {
    "inlet", "outlet", "plasma_electrode", "plasma_metal", "plasma_right",
    "plasma_cover", "plasma_wafer", "plasma_focus_ring",
}


def test_full_nativefree_selected_three_ion_equations_and_8_sidesets():
    deck = DECK.read_text()
    base = json.loads(CHEM.read_text())
    c2 = json.loads(C2.read_text())
    assert "fvm_species = 'O2p Om Op'" in deck
    assert "[Chemistry]" in deck
    assert "fem_potential = potential" in deck
    assert "[Poisson]" not in deck
    assert "[FVKernels]" not in deck and "[FVBCs]" not in deck
    assert "migration_smoothing_width =" not in deck  # default hard max
    assert "pressure = 1.333223684" in deck
    assert "temperature = 300" in deck
    assert "electron_wall_number_flux" in deck
    for species in ("O2p", "Om", "Op"):
        assert species in base["species"]
        assert species in c2["species"]
    assert {name for name in SIDES
            if "new_sideset_name = " + name in deck} == SIDES
    assert "SubdomainBoundingBoxGenerator" in deck
    assert 'block_name = plasma' in deck
    merged = {**base, "ion_surface_current": c2["ion_surface_current"]}
    merged["species"] = {k: {**v, **c2["species"].get(k, {})}
                         for k, v in base["species"].items()}
    result = inspect({DECK.name: deck}, merged, contract="new-only")
    assert result["status"] == "P0_STATIC_PASS_ONLY", result["errors"]
    assert result["c2_native_producer_collision_count"] == 0
    assert result["native_fv_owner_count"] == 0
    assert result["explicit_ion_wall_current_owner_count"] == 0
    c2_result = validate(c2)
    assert c2_result["ion_wall_materials"] == 3
    assert c2_result["normal_fvbcs"] == 3
    assert c2_result["dielectric_fvbcs"] == 9


def test_exact_head_runner_executes_c2_before_unrelated_legacy_negatives():
    runner = RUNNER.read_text()
    old = 'issue633_ion_continuity_newonly_p2.i'
    new = 'issue633_ion_continuity_wall_bc_newonly_p2.i'
    assert old in runner and new in runner
    assert runner.index(old) < runner.index(new)
    assert runner.index(new) < runner.index('invalid_fem_fv_swap')
    assert 'ISSUE633_ION_CONTINUITY_WALL_BC_NEW_ONLY_P2_PASS' in runner


def test_four_transport_and_source_operators_are_distinct_from_wall_bcs():
    source = (ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C").read_text()
    wall = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    for operation in ("time", "diffusion", "drift", "source"):
        assert f'getProblem().addFVKernel({operation}_type, id + "_{operation}"' in source
    assert 'drift_params.set<MooseFunctorName>("potential") = potential;' in source
    assert 'drift_params.set<MooseFunctorName>("mobility") = id + "_mobility";' in source
    assert 'source_params.set<MooseFunctorName>("v") = "S_" + id + "_molar";' in source
    assert 'expected_bcs.emplace(name, bc.type)' in source
    assert 'wall_sidesets.insert(boundary.mesh_boundaries.begin(),' in source
    assert 'params.set<MooseFunctorName>("ion_number_density") = id + "_number_density";' in wall
    assert 'params.set<MooseFunctorName>("signed_number_flux") = bc.signed_number_flux;' in wall
    assert '_problem->addFunctorMaterial(type, std::string(side) + "_surface_current", params);' in wall
    assert '_problem->addFVBC(bc.type, name, params);' in wall



def test_neumann_factor_uses_full_precision_functor_name_not_double():
    # The MOOSE FVFunctorNeumannBC factory parameter is MooseFunctorName.
    # General-ion wall conversion is -1/N_A (~1e-24); six-decimal
    # std::to_string would turn it into 0.000000 and erase the residual.
    source = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    assert 'params.set<MooseFunctorName>("factor") = factor_value.str();' in source
    assert 'std::setprecision(std::numeric_limits<Real>::max_digits10)' in source
    assert 'factor_value <<' in source and '<< bc.factor;' in source
    assert 'params.set<Real>("factor")' not in source
    assert "std::to_string(bc.factor)" not in source.split('params.set<MooseFunctorName>("factor")')[0].split('if (bc.type == "FVFunctorNeumannBC")')[-1]
    assert 'params.set<MooseFunctorName>("signed_number_flux") = bc.signed_number_flux;' in source

def test_new_surface_current_functors_retain_native_surface_charge_consumers():
    # Native lower-D sigma equations are allowed: only ion FV Kernel/BC
    # owners must be cut over. New C2 produces the same three current
    # property names that their existing surface-charge source Kernels read.
    legacy = (
        ROOT / "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i"
    ).read_text()
    generator = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    assert 'std::string(side) + "_net_surface_current_density"' in generator
    assert 'std::string(side) + "_surface_current"' in generator
    for side, state in (
        ("cover", "sigma_s"),
        ("wafer", "sigma_wafer"),
        ("focus_ring", "sigma_focus_ring"),
    ):
        current = f"{side}_net_surface_current_density"
        old_consumer = "sigma_surface_current" if side == "cover" else (
            f"sigma_{side}_surface_current"
        )
        assert f"[{old_consumer}]" in legacy
        assert "type = PhysicsLowerDSurfaceCurrent" in legacy
        assert f"surface_current_density = {current}" in legacy
        assert f"variable = {state}" in legacy
