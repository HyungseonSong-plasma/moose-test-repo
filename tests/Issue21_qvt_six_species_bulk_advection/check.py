#!/usr/bin/env python3
from pathlib import Path
import csv,json,math,sys

def rel(a,b): return abs(a-b)/max(abs(b),1e-300)

def evaluate(row,exp):
    def v(name):
        if name not in row: return None,f'missing CSV column {name}'
        try: return float(row[name]),None
        except Exception: return None,f'non-numeric {name}={row[name]!r}'
    need=['inlet_area','inlet_mdot','outlet_mass_actual','outlet_p_avg','sum_w_min','sum_w_max','Mn_avg','rho_avg']
    allsp=['O2','O2s','O2p','O','Om','Op','Os']
    for s in allsp:
        need += [f'w_{s}_avg',f'w_{s}_min',f'w_{s}_max',f'Dmix_{s}_avg',f'outlet_mdot_{s}']
    d={}
    for name in need:
        x,e=v(name)
        if e: return False,e
        d[name]=x
    A=exp['analytic_inlet_area_m2']; md=exp['expected_total_mdot_kg_per_s']; po=exp['outlet_pressure_Pa']; Y=exp['inlet_mass_fractions']
    if rel(d['inlet_area'],A)>1e-6: return False,f'inlet area mismatch {d["inlet_area"]} vs {A}'
    if rel(d['inlet_mdot'],md)>2e-8: return False,f'inlet mdot mismatch {d["inlet_mdot"]} vs {md}'
    if not d['outlet_mass_actual']>0: return False,'outlet total mass flow must be positive'
    if rel(d['outlet_mass_actual'],md)>2e-2: return False,f'outlet total mass flow mismatch {d["outlet_mass_actual"]} vs {md}'
    if rel(d['outlet_p_avg'],po)>5e-3: return False,f'outlet pressure mismatch {d["outlet_p_avg"]} vs {po}'
    if max(abs(d['sum_w_min']-1),abs(d['sum_w_max']-1))>1e-10: return False,f'sum(w) closure failed: {d["sum_w_min"]}, {d["sum_w_max"]}'
    outlet_species_sum=0.0
    for s in allsp:
        mn=d[f'w_{s}_min']; mx=d[f'w_{s}_max']; av=d[f'w_{s}_avg']; D=d[f'Dmix_{s}_avg']; om=d[f'outlet_mdot_{s}']
        if mn < -1e-10 or mx > 1+1e-10: return False,f'{s} out of bounds: min={mn}, max={mx}'
        if not math.isfinite(D) or D<=0: return False,f'{s} D_mix not positive finite: {D}'
        # Constant-composition invariant: this is intentional in EVR1.
        if max(abs(mn-Y[s]),abs(mx-Y[s]),abs(av-Y[s]))>2e-5:
            return False,f'{s} constant-composition invariant failed: min/avg/max={mn}/{av}/{mx}, expected {Y[s]}'
        target=Y[s]*md
        if rel(om,target)>3e-2: return False,f'{s} outlet species flow mismatch {om} vs {target}'
        outlet_species_sum += om
    if rel(outlet_species_sum,d['outlet_mass_actual'])>5e-3:
        return False,f'sum species outlet flow {outlet_species_sum} != total {d["outlet_mass_actual"]}'
    if not (0.016 <= d['Mn_avg'] <= 0.032): return False,f'Mn out of physical oxygen bounds: {d["Mn_avg"]}'
    if not math.isfinite(d['rho_avg']) or d['rho_avg']<=0: return False,f'rho not positive finite: {d["rho_avg"]}'
    return True,d

def self_test():
    exp={'analytic_inlet_area_m2':0.05954574715614091,'expected_total_mdot_kg_per_s':1.9189578063424318e-6,'outlet_pressure_Pa':1.33322,
         'inlet_mass_fractions':{'O2':.70,'O2s':.05,'O2p':.01,'O':.10,'Om':.01,'Op':.01,'Os':.12}}
    row={'inlet_area':'0.05954574715614091','inlet_mdot':'1.9189578063424318e-6','outlet_mass_actual':'1.9189578063424318e-6','outlet_p_avg':'1.33322','sum_w_min':'1','sum_w_max':'1','Mn_avg':'0.0258064516129','rho_avg':'7e-6'}
    for s,y in exp['inlet_mass_fractions'].items():
        row[f'w_{s}_avg']=row[f'w_{s}_min']=row[f'w_{s}_max']=str(y)
        row[f'Dmix_{s}_avg']='1.0'
        row[f'outlet_mdot_{s}']=str(y*exp['expected_total_mdot_kg_per_s'])
    ok,msg=evaluate(row,exp)
    if not ok: raise SystemExit('R21_CHECKER_SELFTEST: FAIL good row: '+str(msg))
    muts={
      'closure':('sum_w_max','0.99'),
      'negative_species':('w_Om_min','-0.01'),
      'wrong_outlet_total':('outlet_mass_actual','1e-6'),
      'wrong_species_flow':('outlet_mdot_O','1e-8'),
      'bad_dmix':('Dmix_Op_avg','0'),
      'wrong_pressure':('outlet_p_avg','2.0'),
      'composition_changed':('w_O_avg','0.2')}
    for name,(k,val) in muts.items():
        r=dict(row); r[k]=val
        ok,_=evaluate(r,exp)
        if ok: raise SystemExit('R21_CHECKER_SELFTEST: FAIL mutation escaped '+name)
    print('R21_CHECKER_SEMANTIC_SELFTEST: PASS')
    print('R21_CHECKER_NEGATIVE_CONTROLS: PASS')

def main():
    if len(sys.argv)==2 and sys.argv[1]=='--self-test': return self_test()
    if len(sys.argv)!=3: raise SystemExit('usage: check.py input_out.csv expected.json | --self-test')
    cp=Path(sys.argv[1]); ep=Path(sys.argv[2])
    if not cp.is_file(): raise SystemExit('missing CSV '+str(cp))
    exp=json.loads(ep.read_text())
    with cp.open() as f: rows=list(csv.DictReader(f))
    if not rows: raise SystemExit('empty CSV')
    ok,msg=evaluate(rows[-1],exp)
    if not ok: raise SystemExit('FAIL '+str(msg))
    print('R21_QVT_SIX_SPECIES_BULK_ADVECTION_CHECK: PASS')
if __name__=='__main__': main()
