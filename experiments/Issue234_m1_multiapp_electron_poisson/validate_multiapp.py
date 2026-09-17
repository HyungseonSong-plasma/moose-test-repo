#!/usr/bin/env python3
from __future__ import annotations
import csv, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT / "heavy_parent.i"
ELECTRON = ROOT / "electron_sub.i"
POISSON = ROOT / "poisson_sub.i"
CSV = ROOT / "heavy_parent_out.csv"

NE0 = 1.0e17
END = 1.0e-9
MDOT = 20.0e-6 / 60.0 * 0.032 / 0.0224136

def static_contract():
    hp=PARENT.read_text()
    el=ELECTRON.read_text()
    ps=POISSON.read_text()
    return {
        "parent_transient_multiapp": "type = TransientMultiApp" in hp and "input_files = electron_sub.i" in hp,
        "parent_subcycling": "sub_cycling = true" in hp,
        "parent_fast_before_heavy": "execute_on = TIMESTEP_BEGIN" in hp,
        "parent_heavy_dt": "dt = 1.0e-9" in hp and "end_time = 1.0e-9" in hp,
        "parent_no_electron_nonlinear": "[log_e]" not in hp,
        "parent_receives_fast_ne": "source_variable = electron_density_out" in hp and "variable = electron_density_from_sub" in hp,
        "parent_receives_fast_phi": "source_variable = potential_from_poisson" in hp and "variable = potential_from_sub" in hp,
        "electron_dt": "dt = 1.0e-10" in el and "end_time = 1.0e-9" in el,
        "electron_uses_lagged_phi": "potential = potential_from_poisson" in el,
        "electron_thermal_wall": "[right_thermal_surface_loss]" in el,
        "electron_nested_poisson": "type = FullSolveMultiApp" in el and "input_files = poisson_sub.i" in el,
        "poisson_after_electron_step": "execute_on = TIMESTEP_END" in el,
        "electron_to_poisson_freeze": all(tok in el for tok in (
            "source_variable = log_e", "variable = log_e_frozen",
            "source_variable = w_O2p_h", "variable = w_O2p_frozen",
            "source_variable = w_Om_h", "variable = w_Om_frozen",
            "source_variable = w_Op_h", "variable = w_Op_frozen",
        )),
        "poisson_returns_phi": "source_variable = potential_plasma" in el and "variable = potential_from_poisson" in el,
        "poisson_only_phi_nonlinear": ps.count("[Variables]") == 1 and "[potential_plasma]" in ps and "[log_e]" not in ps,
        "poisson_frozen_aux": all(tok in ps for tok in ("[log_e_frozen]","[w_O2p_frozen]","[w_Om_frozen]","[w_Op_frozen]")),
        "poisson_charge_material": "type = PhysicsPlasmaChargeDensityMaterial" in ps,
        "poisson_left_ground": "[left_ground]" in ps and "boundary = left" in ps and "value = 0.0" in ps,
        "poisson_right_natural": "boundary = right\n    value = 0.0" not in ps,
        "no_bulk_chemistry": "ReactionSource" not in hp+el+ps,
        "no_see": "secondary" not in (hp+el+ps).lower(),
    }

def close(a,b,rel=1e-7,abs_=1e-15):
    return math.isclose(a,b,rel_tol=rel,abs_tol=abs_)

def main():
    static=static_contract()
    failed_static=[k for k,v in static.items() if not v]
    if failed_static:
        raise SystemExit(f"static contract failed: {failed_static}")
    rows=list(csv.DictReader(CSV.open()))
    if len(rows)<2:
        raise SystemExit("parent CSV missing final row")
    initial, final = rows[0], rows[-1]
    names=("time","inlet_mdot","inlet_mass_actual","outlet_mass_actual","outlet_p_avg",
           "sum_w_min","sum_w_max","O2_min","u_min","u_max",
           "fast_ne_min","fast_ne_max","fast_phi_min","fast_phi_max")
    missing=[n for n in names if n not in final]
    if missing:
        raise SystemExit(f"missing columns: {missing}")
    vi={k:float(initial[k]) for k in names}
    vf={k:float(final[k]) for k in names}
    finite=all(math.isfinite(v) for v in (*vi.values(),*vf.values()))
    runtime={
        "finite": finite,
        "final_time": close(vf["time"],END,rel=0,abs_=1e-18),
        "sccm_contract": close(vf["inlet_mdot"],MDOT,rel=2e-8,abs_=1e-18),
        "flow_direction": vf["inlet_mass_actual"]<0 and vf["outlet_mass_actual"]>0,
        "flow_closure": abs(vf["outlet_mass_actual"]-MDOT)/MDOT < 2e-2,
        "pressure_outlet": close(vf["outlet_p_avg"],1.33322,rel=5e-3,abs_=1e-10),
        "heavy_mass_fraction_closure": abs(vf["sum_w_min"]-1)<1e-10 and abs(vf["sum_w_max"]-1)<1e-10,
        "heavy_O2_positive": vf["O2_min"]>0,
        "fast_electron_positive": vf["fast_ne_min"]>0,
        "fast_electron_evolved": vf["fast_ne_min"]<NE0 and vf["fast_ne_max"]<=NE0*(1+1e-10),
        "fast_potential_finite": math.isfinite(vf["fast_phi_min"]) and math.isfinite(vf["fast_phi_max"]),
        "fast_potential_nontrivial": abs(vf["fast_phi_max"]-vf["fast_phi_min"])>1e-6,
    }
    failed=[k for k,v in runtime.items() if not v]
    summary={
        "status":"PASS" if not failed else "FAIL",
        "claim_scope":"Issue #234 MultiApp smoke: heavy parent -> electron subcycle -> frozen-charge nested Poisson -> heavy solve",
        "heavy_dt_s":1e-9,
        "electron_dt_s":1e-10,
        "expected_fast_subcycles":10,
        "electrostatic_feedback":"lagged phi from prior nested Poisson solve",
        "heavy_ion_policy":"frozen over parent interval",
        "science_claim":False,
        "timestep_convergence_claim":False,
        "static_checks":static,
        "runtime_checks":runtime,
        "final":vf,
        "failed_runtime_checks":failed,
    }
    (ROOT/"validation_multiapp_summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print(json.dumps(summary,indent=2,sort_keys=True))
    if failed:
        raise SystemExit(f"runtime validation failed: {failed}")

if __name__=="__main__":
    main()
