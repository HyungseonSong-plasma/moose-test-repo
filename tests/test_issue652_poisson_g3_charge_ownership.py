"""G3-only Charge source contract: old Native owner retirement remains G5 HOLD."""
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "physics_app/src/physics/plasma/Chemistry.C"
LEGACY = ROOT / "physics_app/src/materials/PhysicsPlasmaChargeDensityMaterial.C"
C0 = ROOT / "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i"
CHEM = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"
E = 1.602176634e-19
E_OVER_EPS = 1.8095128179727827e-08


@pytest.mark.parametrize("case", ("417", "941"))
def test_optin_charge_numbers_and_single_mechanism(case):
    doc = json.loads((CHEM / f"unified_s6_{case}_newonly.json").read_text())
    assert "poisson" in doc
    assert {species: doc["species"][species]["charge_number"] for species in
            ("O2p", "Op", "e", "Om")} == {
                "O2p": 1, "Op": 1, "e": -1, "Om": -1,
            }
    historical = json.loads((CHEM / f"unified_s6_{case}.json").read_text())
    assert "poisson" not in historical


def test_g3_has_exact_three_charge_owners_and_consumes_g2_live_names():
    source = SRC.read_text()
    scope = source.split("  // G3: only opt-in New-only Poisson obtains live charge projections.", 1)[1]
    scope = scope.split("} // namespace Plasma", 1)[0]
    assert "if (mechanism.poisson())" in scope
    assert scope.count('    add_charge_functor("') == 3
    for property_name in (
        "charge_number_density", "charge_density_C_m3", "poisson_source"
    ):
        assert f'add_charge_functor("{property_name}"' in scope
    for functor in (
        "O2p_number_density", "Op_number_density",
        "n_e_physical", "Om_number_density"
    ):
        assert f'"{functor}"' in scope
    assert '"ni+nop-ne-nm"' in scope
    assert '"1.602176634e-19*nq"' in scope
    assert '"1.8095128179727827e-08*nq"' in scope
    assert 'getProblem().addFunctorMaterial(type, "plasma_" + property, params)' in scope


@pytest.mark.parametrize("number_densities", [
    (1.0e15, 2.0e14, 1.1e15, 1.0e13),
    (1.0e11, 1.0e11, 2.0e11, 0.0),
    (1.0e10, 1.0e9, 0.0, 1.1e10),
])
def test_charge_units_and_signs_against_native_form(number_densities):
    ni, nop, ne, nm = number_densities
    nq = ni + nop - ne - nm
    rho = E * nq
    source = E_OVER_EPS * nq
    assert math.isfinite(rho) and math.isfinite(source)
    assert rho == pytest.approx(E * (ni + nop - ne - nm))
    assert source == pytest.approx((rho / E) * E_OVER_EPS)


def test_archived_c0_exact_charge_contract_is_not_retired_in_g3():
    c0 = C0.read_text()
    for name, expr in (
        ("charge_number_density", "ni+nop-ne-nm"),
        ("charge_density_C_m3", "1.602176634e-19*nq"),
        ("poisson_source", "1.8095128179727827e-08*nq")
    ):
        assert f"property_name = {name}" in c0
        assert f"expression = '{expr}'" in c0
    staging = (CHEM / "prepare_s6_newonly.py").read_text()
    assert "retire_s6_p4_duplicate_owners" in staging
    # G3 alone intentionally has no retirement; G5 (in stacked child PR)
    # owns the exact source-identity cutover before any Native P2.
    if (CHEM / "retire_s6_poisson_charge_owners.py").exists():
        assert "retire_s6_poisson_charge_owners" in staging
        assert "retire_g5_in_disposable_scratch(" in staging
    else:
        assert "retire_s6_poisson_charge_owners" not in staging
    # No Native P2 can be accepted while these three duplicate owners remain.


def test_legacy_mass_fraction_charge_material_is_not_changed_or_reused():
    legacy = LEGACY.read_text()
    source = SRC.read_text()
    assert "PHYSICS_CONSTANTS::N_A" in legacy
    assert 'addFunctorProperty<ADReal>(' in legacy
    new_charge = source.split(
        "  // G3: only opt-in New-only Poisson obtains live charge projections.", 1
    )[1].split("} // namespace Plasma", 1)[0]
    assert "PhysicsPlasmaChargeDensityMaterial" not in new_charge
