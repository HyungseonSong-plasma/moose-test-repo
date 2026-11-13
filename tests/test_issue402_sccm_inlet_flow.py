"""P0 analytical and source-bound tests for physical SCCM inlet conversion.

Accepted reference contract: Issue19 (0 C, 1 atm) Vm_std=0.0224136 m^3/mol.
P1/P2 native gate separately compiles the generated MOOSE Postprocessors/flow BC.
"""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
ACTION = (APP / "src/physics/plasma/Chemistry.C").read_text()
CPP = (APP / "src/userobjects/PhysicsSCCMInletFlowPostprocessor.C").read_text()
HEADER = (APP / "include/userobjects/PhysicsSCCMInletFlowPostprocessor.h").read_text()
VM_STANDARD = .0224136
R = 8.31446261815324


def convert(q_sccm, y, masses, pressure, temperature, area):
    assert q_sccm > 0 and pressure > 0 and temperature > 0 and area > 0
    assert abs(sum(y.values()) - 1) < 1e-12
    M = 1.0 / sum(y[s] / masses[s] for s in y)
    q_std = q_sccm * 1e-6 / 60.0
    mdot = q_std * M / VM_STANDARD
    rho = pressure * M / (R * temperature)
    return {
        "M_inlet": M, "rho_inlet": rho, "mdot": mdot,
        "mass_flux": mdot/area,
        "velocity": mdot/(rho*area),
        "species_mdot": {s: mdot*y[s] for s in y},
    }


def test_issue19_canonical_pure_o2_sccm_reference():
    case=json.loads((ROOT/"experiments/Issue19_sccm_pressure_boundary/expected.json").read_text())
    output=convert(100, {"O2": 1.0}, {"O2": .032},
                   case["outlet_pressure_Pa"], 300,
                   case["inlet_area_m2"])
    assert math.isclose(output["mdot"], case["inlet_mdot_kg_per_s"], rel_tol=1e-13)
    assert math.isclose(output["mass_flux"], case["inlet_mass_flux_kg_per_m2_s"], rel_tol=1e-13)
    # Historic reference speed used its independently rounded rho_const=1.71e-5.
    expected_velocity=case["inlet_mass_flux_kg_per_m2_s"] / (
        case["outlet_pressure_Pa"]*.032/(R*300))
    assert math.isclose(output["velocity"], expected_velocity, rel_tol=1e-13)
    assert math.isclose(sum(output["species_mdot"].values()),output["mdot"],rel_tol=1e-14)


def test_mixture_mass_rate_conservation_and_pressure_speed():
    y={"O2": .89, "O": .10, "Op": .01}
    masses={"O2": .032, "O": .016, "Op": .016}
    o=convert(100,y,masses,1.333223684,300,.05954574715614091)
    assert 0 < o["M_inlet"] < .032
    assert math.isclose(sum(o["species_mdot"].values()),o["mdot"],rel_tol=1e-14)
    assert math.isclose(o["velocity"],(100e-6/60)*R*300/(VM_STANDARD*1.333223684*.05954574715614091),rel_tol=1e-14)
    assert math.isclose(o["species_mdot"]["O"], o["mdot"]*.1, rel_tol=1e-14)


def test_action_registers_actual_total_species_mass_and_area_diagnostics():
    assert 'registerMooseAction("PhysicsApp", PlasmasAction, "add_postprocessor");' in ACTION
    for name in ("inlet_mdot", "inlet_mdot_", "inlet_area", "inlet_mass_flux", "inlet_velocity"):
        assert name in ACTION
    assert 'getParam<Real>("sccm") * 1.0e-6 / 60.0' in ACTION
    assert 'standard_molar_volume_m3_per_mol = 0.0224136' in ACTION
    assert 'record.initial_inlet_mass_fraction / record.molar_mass_kg_mol' in ACTION
    assert '_problem->addPostprocessor("Receiver", name, params);' in ACTION
    assert '_problem->addPostprocessor("AreaPostprocessor", "inlet_area", area);' in ACTION
    assert "PhysicsSCCMInletFlowPostprocessor" in HEADER+CPP+ACTION
    assert 'inlet_mdot * *_data.species(id).initial_inlet_mass_fraction' in ACTION


def test_mass_flux_and_speed_use_mesh_measured_area_with_zero_area_guard():
    assert 'registerMooseObject("PhysicsApp", PhysicsSCCMInletFlowPostprocessor);' in CPP
    assert 'getPostprocessorValue("area_pp")' in CPP
    assert 'const Real flux = _mdot / _inlet_area;' in CPP
    assert 'return flux / _inlet_density;' in CPP
    assert '_inlet_area <= 0.0' in CPP
    assert 'params.set<Real>("rho_inlet_kg_per_m3") = inlet_density;' in ACTION


def test_flow_bc_is_only_generated_with_explicit_solver_binding_and_orientation():
    assert '"inlet_flow_variables"' in ACTION
    assert '"inlet_flow_direction"' in ACTION
    assert 'WCNSFVMassFluxBC' in ACTION
    assert 'WCNSFVMomentumFluxBC' in ACTION
    assert 'params.set<PostprocessorName>("mdot_pp") = "inlet_mdot";' in ACTION
    assert 'params.set<PostprocessorName>("area_pp") = "inlet_area";' in ACTION
    assert 'params.set<MooseFunctorName>("rho") = "rho_g_inlet";' in ACTION
    assert 'params.set<Point>("direction") = getParam<Point>("inlet_flow_direction");' in ACTION
    assert 'if (flow[0] == "p")' in ACTION
    p2=(APP/"ci/json_sccm_flow_p2.i").read_text()
    assert "inlet_flow_variables = 'p_flow u v'" in p2
    assert "inlet_flow_direction = '-1 0 0'" in p2


def test_sccm_is_not_conflated_with_electron_sheath_bcs():
    for p in ("DDContinuityEq.C", "DDEnergyEq.C"):
        c=(APP/"src/physics/plasma"/p).read_text()
        assert 'registerMooseAction("PhysicsApp", '+p[:-2]+', "add_bc");' not in c
    assert '"initial_inlet_mass_fraction"' in ACTION
    assert 'params.set<Real>("value") = *record.initial_inlet_mass_fraction;' in ACTION
