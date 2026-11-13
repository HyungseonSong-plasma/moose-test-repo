"""P0 SCCM feed oracle from accepted Issue #19/#21 input contracts."""
from __future__ import annotations

from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
ACTION = APP / "src/physics/plasma/Chemistry.C"
FIXTURE = APP / "ci/json_species_live_all4_p2.json"
HISTORICAL = ROOT / "experiments/Issue19_sccm_pressure_boundary/expected.json"
ISSUE19 = ROOT / "experiments/Issue19_sccm_pressure_boundary/physics.i"
ISSUE21 = ROOT / "experiments/Issue21_qvt_six_species_bulk_advection/physics.i"
GAS_CONSTANT = 8.31446261815324


def convert(data: dict, sccm: float, area: float, vm: float, p: float, T: float):
    species = data["species"]
    inlet_y = {id: row["initial_inlet_mass_fraction"] for id, row in species.items()}
    mean_molar_mass = 1 / sum(
        inlet_y[id] / row["molar_mass_kg_mol"] for id, row in species.items()
    )
    mdot = sccm * 1e-6 / 60 * mean_molar_mass / vm
    rho = p * mean_molar_mass / (GAS_CONSTANT * T)
    flux = mdot / area
    speed = flux / rho
    species_flow = {id: mdot * inlet_y[id] for id in inlet_y}
    return mean_molar_mass, mdot, rho, flux, speed, species_flow


def test_original_issue19_sccm_oracle_is_reused():
    exp = json.loads(HISTORICAL.read_text())
    d = json.loads(FIXTURE.read_text())
    M, mdot, rho, flux, speed, parts = convert(
        d, exp["Q_sccm"], exp["inlet_area_m2"], exp["Vm_std_m3_per_mol"],
        1.33322, 300
    )
    assert math.isclose(M, 0.032, rel_tol=1e-15)
    assert math.isclose(mdot, exp["inlet_mdot_kg_per_s"], rel_tol=1e-12)
    assert math.isclose(flux, rho * speed, rel_tol=1e-14)
    assert math.isclose(sum(parts.values()), mdot, rel_tol=1e-14)
    assert "Q_std = ${fparse Q_sccm * 1e-6 / 60.0}" in ISSUE19.read_text()
    assert "inlet_mdot_value = ${fparse Q_std * M_inlet / Vm_std}" in ISSUE19.read_text()
    assert "mdot_pp = inlet_mdot" in ISSUE19.read_text()


def test_issue21_species_flow_identity_and_negative_mutations():
    d = json.loads(FIXTURE.read_text())
    d["species"]["O2"]["initial_inlet_mass_fraction"] = 0.75
    d["species"]["O"]["initial_inlet_mass_fraction"] = 0.25
    M, mdot, rho, flux, speed, parts = convert(
        d, 100, 0.05, 0.0224136, 1.33322, 300
    )
    assert math.isclose(M, 1/(.75/.032+.25/.016), rel_tol=1e-14)
    assert math.isclose(parts["O"], .25*mdot, rel_tol=1e-14)
    assert math.isclose(sum(parts.values()), mdot, rel_tol=1e-14)
    wrong_mdot = 100*1e-6/60*.032/.0224136
    assert not math.isclose(wrong_mdot, mdot, rel_tol=1e-3)
    assert not math.isclose(speed, mdot/rho, rel_tol=1e-3)  # missing area mutation
    assert "inlet_mdot_O_value = ${fparse inlet_mdot_value * Yin_O}" in ISSUE21.read_text()


def test_action_generates_numeric_receivers_not_duplicate_wcns_owners():
    source = ACTION.read_text()
    assert '"ConstantPostprocessor"' in source
    assert 'addConstant("plasma_inlet_mdot", inlet_mdot);' in source
    assert 'addConstant("plasma_inlet_mass_flux", inlet_mass_flux);' in source
    assert 'addConstant("plasma_inlet_speed", inlet_speed);' in source
    assert 'addConstant("plasma_inlet_mdot_" + id, inlet_mdot * inlet_y);' in source
    assert 'getParam<MooseEnum>("inlet_species_bc_ownership") == "root_dirichlet"' in source
    assert "AreaPostprocessor" not in source
    for i in ("json_surface_rate_p2.i", "json_species_live_all4_p2.i"):
        input_text = (APP / "ci" / i).read_text()
        assert "inlet_area = 0.05" in input_text
        assert "standard_molar_volume = 0.0224136" in input_text
        assert "WCNSFVMassFluxBC" not in input_text  # separate solver owner
