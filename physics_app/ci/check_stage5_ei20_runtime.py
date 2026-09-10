#!/usr/bin/env python3
"""Governed Stage-5 S5-B discriminator for EI20 O ionization."""
import argparse,csv,hashlib,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CONTRACT=ROOT/"docs/development/2026-09-10_issue176_stage5_reaction_ownership_contract.json"
TABLE=ROOT/"physics_app/data/electron_impact/o_ionization.txt"
NA=6.02214076e23
NREF=1e16
EREF=5.73276
MO=0.016
RHO=3.1998e-5
W0=1e-3
DT=1e-7
LOSS=13.618
XMIN,XMAX=1.40991,22.1378
ANCHORS={XMIN:0.0,EREF:5.41e7,XMAX:1.19e10}
EXPECTED_BLOB="43d73a4f8a70ea1fb262383e71164d8f18844ae8"
PROGRESS="R_ion_O"
ECOEF=-(LOSS*NA/(NREF*EREF))

def close(a,b,rel=8e-6,abs_=1e-12,label="value"):
    if not math.isclose(a,b,rel_tol=rel,abs_tol=abs_):
        raise AssertionError(f"{label}: {a:.17g} != {b:.17g}")

def num(row,key):
    value=float(row[key])
    if not math.isfinite(value): raise AssertionError(f"non-finite {key}")
    return value

def blob_sha(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()

def read_table(data):
    rows=[]
    for n,raw in enumerate(data.decode().splitlines(),1):
        if not raw.strip(): continue
        fields=raw.split()
        if len(fields)!=2: raise AssertionError(f"table line {n}: expected two columns")
        x,y=map(float,fields)
        if not(math.isfinite(x) and math.isfinite(y)) or y<0:
            raise AssertionError(f"table line {n}: invalid value")
        rows.append((x,y))
    if len(rows)!=100: raise AssertionError(f"EI20 table expected 100 rows, got {len(rows)}")
    if any(b[0]<=a[0] for a,b in zip(rows,rows[1:])): raise AssertionError("EI20 grid not strictly increasing")
    if rows[0][0]!=XMIN or rows[-1][0]!=XMAX: raise AssertionError("EI20 strict lookup domain changed")
    vals=dict(rows)
    for x,y in ANCHORS.items():
        if vals.get(x)!=y: raise AssertionError(f"EI20 frozen anchor mismatch at {x} eV")
    return rows

def interp(table,x):
    if x<table[0][0] or x>table[-1][0]: raise AssertionError(f"mean energy outside strict lookup range: {x}")
    if x==table[0][0]: return table[0][1]
    if x==table[-1][0]: return table[-1][1]
    for (x0,y0),(x1,y1) in zip(table,table[1:]):
        if x0<=x<=x1: return y0+(x-x0)*(y1-y0)/(x1-x0)
    raise AssertionError("strict interpolation bracket failure")

def runtime_input(mean=EREF):
    ep0=mean/EREF
    return f"""[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 3
    nx = 1
    ny = 1
    nz = 1
    xmin = 0
    xmax = 1
    ymin = 0
    ymax = 0.01
    zmin = 0
    zmax = 0.01
  []
[]
[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1
  []
  [n_epsilon]
    type = MooseVariableFVReal
    initial_condition = {ep0:.17g}
  []
  [w_Op]
    type = MooseVariableFVReal
    initial_condition = {W0:.17g}
  []
[]
[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const'
    prop_values = '{RHO:.17g}'
  []
  [o_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O_constraint
    functor_names = 'w_Op'
    functor_symbols = 'wop'
    expression = '1-wop'
  []
  [electron_number_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'n_e'
    functor_symbols = 'nehat'
    expression = '{NREF:.17g}*nehat'
  []
  [o_molar_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O
    functor_names = 'rho_const w_O_constraint'
    functor_symbols = 'dens wo'
    expression = 'dens*wo/{MO:.17g}'
  []
  [mean_energy_bridge]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = n_epsilon
    electron_density = n_e
    energy_reference_eV = {EREF:.17g}
  []
  [ei20_rate]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = o_ionization.txt
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O
    reaction_progress = {PROGRESS}
  []
  [o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = O_ei20_mass_source
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '-{MO:.17g}*rprog'
  []
  [op_mass_source]
    type = ADParsedFunctorMaterial
    property_name = Op_ei20_mass_source
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '{MO:.17g}*rprog'
  []
  [electron_number_source]
    type = ADParsedFunctorMaterial
    property_name = electron_ei20_number_source
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '6.02214076e23*rprog'
  []
[]
[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
  []
  [n_e_source]
    type = PhysicsFVElectronReactionSource
    variable = n_e
    number_source = electron_ei20_number_source
    n_ref = {NREF:.17g}
  []
  [n_epsilon_time]
    type = FVTimeKernel
    variable = n_epsilon
  []
  [ei20_energy_loss]
    type = FVCoupledForce
    variable = n_epsilon
    v = {PROGRESS}
    coef = {ECOEF:.17g}
  []
  [w_Op_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_Op
    rho = rho_const
  []
  [w_Op_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Op
    source = Op_ei20_mass_source
  []
[]
[Postprocessors]
  [n_e_hat_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_epsilon_hat_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_epsilon
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_Op_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O_constraint
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_solved_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [R_avg]
    type = ElementAverageFunctorPostprocessor
    functor = {PROGRESS}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = O_ei20_mass_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = Op_ei20_mass_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_ei20_number_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  dt = {DT:.17g}
  end_time = {DT:.17g}
  solve_type = NEWTON
[]
[Outputs]
  csv = true
  exodus = false
[]
"""

def validate(rows,table):
    if len(rows)<2: raise AssertionError("expected initial and final rows")
    i,f=rows[0],rows[-1]
    ni,nf=num(i,"n_e_hat_avg"),num(f,"n_e_hat_avg")
    ei,ef=num(i,"n_epsilon_hat_avg"),num(f,"n_epsilon_hat_avg")
    pi,pf=num(i,"w_Op_avg"),num(f,"w_Op_avg")
    oi,of=num(i,"w_O_avg"),num(f,"w_O_avg")
    mi,mf=num(i,"mean_en_solved_avg"),num(f,"mean_en_solved_avg")
    r=num(f,"R_avg"); so=num(f,"O_source_avg"); sp=num(f,"Op_source_avg"); se=num(f,"electron_source_avg")
    if not nf>ni>0: raise AssertionError("EI20 electron production")
    if not 0<ef<ei: raise AssertionError("EI20 energy sink")
    if not(0<=pi<pf<1 and oi>of>0): raise AssertionError("EI20 O/Op direction/positivity")
    if not(XMIN<=mi<=XMAX and XMIN<=mf<=XMAX): raise AssertionError("strict lookup range")
    close(oi+pi,1,rel=0,abs_=2e-12,label="initial heavy sum")
    close(of+pf,1,rel=0,abs_=2e-12,label="final heavy sum")
    close(mi,EREF*ei/ni,label="initial mean energy"); close(mf,EREF*ef/nf,label="final mean energy")
    if not(r>0 and so<0<sp and se>0): raise AssertionError("EI20 source signs")
    close(-so/MO,r,label="O/shared progress"); close(sp/MO,r,label="Op/shared progress"); close(se/NA,r,label="electron/shared progress")
    close(so+sp,0,rel=0,abs_=1e-12,label="heavy source closure")
    k=interp(table,mf); expected=k*(NREF*nf/NA)*(RHO*of/MO)
    close(r,expected,rel=8e-6,abs_=1e-14,label="strict lookup canonical progress")
    close(NREF*(nf-ni)/DT,se,rel=9e-6,abs_=1,label="electron BE closure")
    close(RHO*(pf-pi)/DT,sp,rel=9e-6,abs_=1e-12,label="Op BE closure")
    close(RHO*(of-oi)/DT,so,rel=9e-6,abs_=1e-12,label="O BE closure")
    rhs=ECOEF*r; close((ef-ei)/DT,rhs,rel=9e-6,abs_=1e-8,label="EI20 energy BE closure")
    de=NREF*(nf-ni); dp=NA*RHO*(pf-pi)/MO; close(de,dp,rel=9e-6,abs_=1,label="charge closure")
    oxy_i=RHO*(oi+pi)/MO; oxy_f=RHO*(of+pf)/MO; close(oxy_f,oxy_i,rel=2e-12,abs_=1e-14,label="oxygen inventory")
    return {"initial":{"n_e_hat":ni,"n_epsilon_hat":ei,"w_O":oi,"w_Op":pi,"mean_en_solved_eV":mi},
            "final":{"n_e_hat":nf,"n_epsilon_hat":ef,"w_O":of,"w_Op":pf,"mean_en_solved_eV":mf,"R_ion_O_mol_m3_s":r,"electron_source_m3_s":se},
            "closure":{"heavy_mass_source_sum_kg_m3_s":so+sp,"oxygen_atom_molar_inventory_initial":oxy_i,
                       "oxygen_atom_molar_inventory_final":oxy_f,"electron_particle_delta":de,"positive_ion_particle_delta":dp,
                       "energy_loss_eV_per_event":LOSS,"standard_moose_object":"FVCoupledForce","energy_coef":ECOEF,
                       "normalized_energy_rhs_per_s":rhs,"observed_dn_epsilon_hat_dt_per_s":(ef-ei)/DT,"lookup_k_m3_mol_s":k}}

def synthetic_rows(table):
    r=interp(table,EREF)*(NREF/NA)*(RHO*(1-W0)/MO)
    for _ in range(500):
        ne=1+DT*NA*r/NREF; wp=W0+DT*MO*r/RHO; ep=1+DT*ECOEF*r; mean=EREF*ep/ne
        new=interp(table,mean)*(NREF*ne/NA)*(RHO*(1-wp)/MO)
        if math.isclose(new,r,rel_tol=1e-14,abs_tol=1e-18): r=new; break
        r=new
    ne=1+DT*NA*r/NREF; wp=W0+DT*MO*r/RHO; ep=1+DT*ECOEF*r; mean=EREF*ep/ne
    r0=interp(table,EREF)*(NREF/NA)*(RHO*(1-W0)/MO)
    return [{"n_e_hat_avg":1,"n_epsilon_hat_avg":1,"w_Op_avg":W0,"w_O_avg":1-W0,"mean_en_solved_avg":EREF,
             "R_avg":r0,"O_source_avg":-MO*r0,"Op_source_avg":MO*r0,"electron_source_avg":NA*r0},
            {"n_e_hat_avg":ne,"n_epsilon_hat_avg":ep,"w_Op_avg":wp,"w_O_avg":1-wp,"mean_en_solved_avg":mean,
             "R_avg":r,"O_source_avg":-MO*r,"Op_source_avg":MO*r,"electron_source_avg":NA*r}]

def expect_fail(fn,*args):
    try: fn(*args)
    except AssertionError: return
    raise AssertionError("negative mutation unexpectedly passed")

def self_test():
    table=[(XMIN,ANCHORS[XMIN]),(EREF,ANCHORS[EREF]),(XMAX,ANCHORS[XMAX])]
    rows=synthetic_rows(table); validate(rows,table)
    for key,mut in [("n_e_hat_avg",lambda x:1.0),("n_epsilon_hat_avg",lambda x:1+abs(x-1)),
                    ("Op_source_avg",lambda x:x*1.01),("electron_source_avg",lambda x:x*2),
                    ("R_avg",lambda x:x*1.01),("w_Op_avg",lambda x:-1e-6)]:
        bad=[dict(r) for r in rows]; bad[-1][key]=mut(bad[-1][key]); expect_fail(validate,bad,table)
    expect_fail(interp,table,XMIN-.1); expect_fail(interp,table,XMAX+.1)
    text=runtime_input()
    required=("type = PhysicsElectronImpactRateMaterial",f"reaction_progress = {PROGRESS}",
              "type = PhysicsFVSpeciesReactionSource","source = Op_ei20_mass_source",
              "type = PhysicsFVElectronReactionSource","number_source = electron_ei20_number_source",
              "type = FVCoupledForce",f"v = {PROGRESS}","O_ei20_mass_source","Op_ei20_mass_source","electron_ei20_number_source")
    for token in required:
        if token not in text: raise AssertionError(f"runtime input missing {token}")
    if text.count("type = PhysicsElectronImpactRateMaterial")!=1 or text.count(f"reaction_progress = {PROGRESS}")!=1:
        raise AssertionError("EI20 must have exactly one progress owner")
    for token in ("PhysicsFVElectronReactionEnergySource","o_excitation_1d.txt","R_excitation_O_1p968","PhysicsElectronImpactIonizationMaterial"):
        if token in text: raise AssertionError(f"wrong/deprecated Stage-5 surface activated: {token}")
    for alias in ("wop","nehat","dens","wo","rprog"):
        if alias in {"x","y","z","t","pi","e"}: raise AssertionError("reserved parser alias")
    print("STAGE5_EI20_RUNTIME_CHECKER_SELFTEST_PASS")

def static_gate():
    contract=json.loads(CONTRACT.read_text())
    if contract.get("status")!="CONTRACT_FROZEN" or contract.get("stage")!="STAGE_5_FULL_CHEMISTRY_REPRESENTATIVE_REAL_QVT":
        raise AssertionError("Stage-5 ownership contract is not frozen")
    rxn={x["id"]:x for x in contract["stage5_admitted_primary_channels"]}["EI20_O_IONIZATION"]
    if rxn["admission"]!="DATA_READY_SECOND_SLICE" or rxn["canonical_progress"]!=PROGRESS or rxn["energy_loss_eV_per_event"]!=LOSS:
        raise AssertionError("EI20 frozen progress/energy contract changed")
    if rxn["heavy_stoichiometry"]!={"O":-1,"Op":1} or rxn["net_electron_particle_stoich"]!=1 or rxn["electron_number_source"]!="+N_A*R_ion_O":
        raise AssertionError("EI20 stoichiometry/electron projection changed")
    data=TABLE.read_bytes()
    if blob_sha(data)!=EXPECTED_BLOB: raise AssertionError(f"EI20 production table blob changed: {blob_sha(data)}")
    read_table(data)
    owner=(ROOT/"physics_app/src/materials/PhysicsElectronImpactRateMaterial.C").read_text()
    for token in ('addRequiredParam<std::string>("reaction_progress"',"return k_raw * (n_e / N_A) * c_target;","strict Stage-4 policy forbids clamp/floor"):
        if token not in owner: raise AssertionError(f"generic progress owner contract missing: {token}")
    ek=(ROOT/"physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C").read_text()
    if "return -physical_number_source / _n_ref;" not in ek: raise AssertionError("electron source projection semantics changed")
    self_test(); print("STAGE5_EI20_IMPLEMENTATION_P0_PASS")

def preflight(path):
    subprocess.run([sys.executable,str(ROOT/"bin/physics.py"),"preflight",str(path)],cwd=ROOT,check=True)

def execute_case(exe,work,name,mean,strict_fail=False):
    d=work/name; d.mkdir(); shutil.copy2(TABLE,d/TABLE.name); inp=d/f"{name}.i"; inp.write_text(runtime_input(mean)); preflight(inp)
    p2=subprocess.run([str(exe),"--check-input","-i",inp.name],cwd=d,text=True,capture_output=True)
    if strict_fail:
        out=p2.stdout+p2.stderr
        if p2.returncode==0:
            p3=subprocess.run([str(exe),"-i",inp.name],cwd=d,text=True,capture_output=True)
            if p3.returncode==0: raise AssertionError(f"{name}: out-of-range EI20 unexpectedly ran")
            out=p3.stdout+p3.stderr
        if "outside lookup range" not in out or "strict Stage-4 policy forbids clamp/floor" not in out:
            raise AssertionError(f"{name}: strict lookup failure signature missing")
        return
    if p2.returncode: raise AssertionError(f"{name}: P2 failed\n{p2.stdout}\n{p2.stderr}")
    p3=subprocess.run([str(exe),"-i",inp.name],cwd=d,text=True,capture_output=True)
    if p3.returncode: raise AssertionError(f"{name}: P3 failed\n{p3.stdout}\n{p3.stderr}")
    return validate(list(csv.DictReader((d/f"{name}_out.csv").open(newline=""))),read_table(TABLE.read_bytes()))

def run(executable,evidence_out=None,repository_sha=None,build_base_ref=None):
    static_gate(); exe=Path(executable).resolve()
    if not exe.is_file(): raise SystemExit(f"Physics executable does not exist: {exe}")
    with tempfile.TemporaryDirectory(prefix="stage5-ei20-") as tmp:
        work=Path(tmp); result=execute_case(exe,work,"stage5_ei20_runtime",EREF)
        execute_case(exe,work,"stage5_ei20_below_lookup",XMIN-.01,True); execute_case(exe,work,"stage5_ei20_above_lookup",XMAX+.01,True)
    data=TABLE.read_bytes()
    evidence={"schema_version":1,"stage":"STAGE_5","slice":"S5-B_EI20","decision":"LOCAL_RUNTIME_ACCURACY","result":"PASS",
              "integrated_physics_accuracy":"NOT_ESTABLISHED","repository_sha":repository_sha,"build_base_ref":build_base_ref,
              "executable":str(exe),"executable_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),
              "production_table":{"path":str(TABLE.relative_to(ROOT)),"git_blob_sha":blob_sha(data),"sha256":hashlib.sha256(data).hexdigest(),
                                  "rows":100,"lookup_domain_eV":[XMIN,XMAX],"anchors_m3_per_mol_s":{str(k):v for k,v in ANCHORS.items()}},
              "runtime":result,"strict_bounds_negative_controls":"PASS","upstream_regressions":"enforced by governed science workflow"}
    if evidence_out: Path(evidence_out).write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n")
    print(f"STAGE5_EI20_LOCAL_RUNTIME_PASS R={result['final']['R_ion_O_mol_m3_s']:.12g} n_e_hat={result['final']['n_e_hat']:.12g} mean_en={result['final']['mean_en_solved_eV']:.12g}")

def main():
    p=argparse.ArgumentParser(); p.add_argument("--self-test",action="store_true"); p.add_argument("--static",action="store_true")
    p.add_argument("--executable"); p.add_argument("--evidence-out"); p.add_argument("--repository-sha"); p.add_argument("--build-base-ref"); a=p.parse_args()
    if a.self_test: self_test()
    elif a.static: static_gate()
    elif a.executable: run(a.executable,a.evidence_out,a.repository_sha,a.build_base_ref)
    else: p.error("choose --self-test, --static, or --executable")
if __name__=="__main__": main()
