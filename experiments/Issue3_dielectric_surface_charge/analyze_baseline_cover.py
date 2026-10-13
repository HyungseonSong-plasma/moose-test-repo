#!/usr/bin/env python3
from __future__ import annotations
import csv, json, math, sys
from pathlib import Path

E_CHARGE = 1.602176634e-19
DT = 1.0e-9
N_STEPS = 100
T_FINAL = 1.0e-7
REL = 2.0e-5
ABS_Q = 2.0e-16

BASELINE_100NS = {
    'charge_integral': 2.4258918330092e-07,
    'ne_min': 9.6258559023579e13,
    'ne_max': 1.0605940414177e15,
    'ni_min': 5.8775874134403e14,
    'ni_max': 1.3154146364932e15,
    'nm_min': 1.1628343436002e14,
    'nm_max': 1.5272726100127e15,
    'nop_min': 5.8642886941968e14,
    'nop_max': 1.3102738259247e15,
    'mean_energy_min': 3.3448984241231,
    'mean_energy_max': 3.9049676496744,
    'potential_min': 0.0,
    'potential_max': 5.2600666661978,
    'neutral_p_min': 1.3322262049782,
    'neutral_p_max': 1.3333975088257,
    'neutral_mass_total': 6.9859825560335e-07,
}

REQUIRED = [
    'time','charge_integral','ne_min','ne_max','ni_min','ni_max','nm_min','nm_max','nop_min','nop_max',
    'mean_energy_min','mean_energy_max','potential_min','potential_max','neutral_p_min','neutral_p_max','neutral_mass_total',
    'cover_net_surface_current','cover_electron_primary_flux','cover_O2p_flux','cover_Om_flux','cover_Op_flux',
    'cover_surface_charge_total','cover_sigma_average','cover_sigma_min','cover_sigma_max','cover_interface_potential'
]

def close(a,b,rel=REL,abs_=1e-14):
    return abs(a-b) <= max(abs_, rel*max(abs(a),abs(b),1.0e-300))

def main():
    if len(sys.argv)!=3:
        raise SystemExit('usage: analyze_baseline_cover.py output.csv input.i')
    csv_path=Path(sys.argv[1]); inp=Path(sys.argv[2])
    with csv_path.open() as f:
        rows=list(csv.DictReader(f))
    if not rows: raise SystemExit('empty csv')
    missing=[k for k in REQUIRED if k not in rows[0]]
    if missing: raise SystemExit(f'missing CSV columns: {missing}')
    data=[{k:float(r[k]) for k in REQUIRED} for r in rows]
    text=inp.read_text()

    checks={}
    checks['row_count_initial_plus_100']=len(data)==N_STEPS+1
    checks['time_grid']=all(close(r['time'],i*DT,rel=0,abs_=5e-16) for i,r in enumerate(data)) and close(data[-1]['time'],T_FINAL,rel=0,abs_=5e-16)
    checks['initial_surface_charge_zero']=abs(data[0]['cover_surface_charge_total']) < 1e-20 and abs(data[0]['cover_sigma_average']) < 1e-20
    checks['charged_species_positive_all_steps']=all(min(r['ne_min'],r['ni_min'],r['nm_min'],r['nop_min'])>0.0 for r in data)
    checks['mean_energy_positive_all_steps']=all(r['mean_energy_min']>0.0 for r in data)
    checks['finite_all_steps']=all(all(math.isfinite(v) for v in r.values()) for r in data)

    current_identity=[]; surface_ledger=[]
    for i,r in enumerate(data):
        expected=E_CHARGE*(r['cover_O2p_flux']+r['cover_Op_flux']-r['cover_Om_flux']-r['cover_electron_primary_flux'])
        current_identity.append(close(r['cover_net_surface_current'],expected,rel=5e-8,abs_=1e-12))
        if i:
            dq=r['cover_surface_charge_total']-data[i-1]['cover_surface_charge_total']
            surface_ledger.append(abs(dq-r['cover_net_surface_current']*DT))
    checks['cover_current_flux_identity_all_steps']=all(current_identity)
    scale=max([abs(r['cover_surface_charge_total']) for r in data]+[1e-30])
    ledger_tol=max(ABS_Q,2e-5*scale)
    checks['cover_surface_charge_ledger_all_steps']=bool(surface_ledger) and max(surface_ledger)<=ledger_tol
    checks['dynamic_surface_charge_active']=max(abs(r['cover_sigma_average']) for r in data)>1e-16
    checks['cover_electrostatic_response_finite']=all(math.isfinite(r['cover_interface_potential']) for r in data)

    checks['cover_eps_r_3p6']="prop_values = '3.6'" in text and 'block = cover' in text
    checks['cover_lowerd_sigma_owner']=text.count('type = PhysicsLowerDSurfaceCurrent')==1 and text.count('type = PhysicsADSurfaceChargePoissonBC')==1
    checks['dedicated_dielectric_species_bcs']=text.count('type = PhysicsFVLogMolarDielectricFluxBC')==3 and text.count('type = PhysicsFEMLogMolarDielectricFluxBC')==1
    checks['cover_not_dirichlet_grounded']="boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_wafer plasma_focus_ring cover_outer_ground cover_outer_right'" in text
    checks['see_disabled']='see_number_flux' not in text and 'see_gamma' not in text
    checks['potential_spans_plasma_cover']="block = 'plasma cover'" in text

    final=data[-1]
    comparison={}
    for k,b in BASELINE_100NS.items():
        p=final[k]
        denom=max(abs(b),1e-300)
        comparison[k]={'baseline':b,'pilot':p,'delta':p-b,'relative_delta':(p-b)/denom}

    result={
        'classification':'BASELINE_COVER_DIELECTRIC_100NS_PASS' if all(checks.values()) else 'BASELINE_COVER_DIELECTRIC_100NS_FAIL',
        'scope':'Accepted Issue331 baseline physics, first 100 x 1 ns steps, cover-only epsilon_r=3.6 ideal-dielectric pilot; SEE=0; no bulk dielectric leakage model.',
        'checks':checks,
        'diagnostics':{
            'final_time_s':final['time'],
            'final_cover_surface_charge_C':final['cover_surface_charge_total'],
            'final_cover_sigma_average_C_m2':final['cover_sigma_average'],
            'final_cover_interface_potential_V':final['cover_interface_potential'],
            'final_cover_net_surface_current_A':final['cover_net_surface_current'],
            'max_surface_ledger_error_C':max(surface_ledger) if surface_ledger else None,
            'surface_ledger_tolerance_C':ledger_tol,
            'baseline_100ns_comparison':comparison,
        }
    }
    print(json.dumps(result,indent=2,sort_keys=True))
    raise SystemExit(0 if all(checks.values()) else 1)

if __name__=='__main__': main()
