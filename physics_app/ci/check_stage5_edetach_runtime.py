#!/usr/bin/env python3
"""Stage-5 S5-C bounded check: e + O- -> O + 2e."""
import argparse,csv,hashlib,json,math,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]; C=R/"docs/development/2026-09-10_issue176_stage5_s5c_edetach_contract.json"
NA=6.02214076e23; NR=1e16; ER=5.73276; M=.016; D=3.1998e-5; W=1e-3; DT=1e-7; L=12.; A=5.47e-14; E=2.98; B=.324; P="R_detach_Om"; EC=-L*NA/(NR*ER)
def eq(a,b,r=1.2e-5,a0=1e-12):
    if not math.isclose(a,b,rel_tol=r,abs_tol=a0): raise AssertionError((a,b))
def k(t):
    if not math.isfinite(t) or t<=0: raise AssertionError("Te")
    return A*math.exp(-E/t)*t**B
def rate(n,q,w):
    if min(n,q)<=0 or w<0: raise AssertionError("state")
    return k((2/3)*ER*q/n)*(NR*n)*(D*w/M)
def text():
 return f"""[Mesh]
 [m]
  type=GeneratedMeshGenerator
  dim=3
  nx=1
  ny=1
  nz=1
 []
[]
[Variables]
 [n_e]
  type=MooseVariableFVReal
  initial_condition=1
 []
 [n_epsilon]
  type=MooseVariableFVReal
  initial_condition=1
 []
 [w_Om]
  type=MooseVariableFVReal
  initial_condition={W}
 []
[]
[FunctorMaterials]
 [c]
  type=ADGenericFunctorMaterial
  prop_names='rho_const'
  prop_values='{D}'
 []
 [wo]
  type=ADParsedFunctorMaterial
  property_name=w_O_constraint
  functor_names='w_Om'
  functor_symbols='womass'
  expression='1-womass'
 []
 [ne]
  type=ADParsedFunctorMaterial
  property_name=n_e_physical
  functor_names='n_e'
  functor_symbols='nehat'
  expression='{NR}*nehat'
 []
 [ce]
  type=ADParsedFunctorMaterial
  property_name=c_electron
  functor_names='n_e_physical'
  functor_symbols='nephys'
  expression='nephys/{NA}'
 []
 [co]
  type=ADParsedFunctorMaterial
  property_name=c_Om
  functor_names='rho_const w_Om'
  functor_symbols='dens womass'
  expression='dens*womass/{M}'
 []
 [me]
  type=PhysicsElectronMeanEnergyMaterial
  electron_energy_density=n_epsilon
  electron_density=n_e
  energy_reference_eV={ER}
 []
 [te]
  type=ADParsedFunctorMaterial
  property_name=Te_eV
  functor_names='mean_en_solved'
  functor_symbols='meanen'
  expression='(2.0/3.0)*meanen'
 []
 [rr]
  type=ADParsedFunctorMaterial
  property_name={P}
  functor_names='c_electron c_Om Te_eV'
  functor_symbols='celec comneg teev'
  expression='{A*NA}*celec*comneg*exp(-{E}/teev)*(teev^{B})'
 []
 [sm]
  type=ADParsedFunctorMaterial
  property_name=Om_edetach_mass_source
  functor_names='{P}'
  functor_symbols='rprog'
  expression='-{M}*rprog'
 []
 [so]
  type=ADParsedFunctorMaterial
  property_name=O_edetach_mass_source
  functor_names='{P}'
  functor_symbols='rprog'
  expression='{M}*rprog'
 []
 [se]
  type=ADParsedFunctorMaterial
  property_name=electron_edetach_number_source
  functor_names='{P}'
  functor_symbols='rprog'
  expression='{NA}*rprog'
 []
[]
[FVKernels]
 [nt]
  type=FVTimeKernel
  variable=n_e
 []
 [ns]
  type=PhysicsFVElectronReactionSource
  variable=n_e
  number_source=electron_edetach_number_source
  n_ref={NR}
 []
 [et]
  type=FVTimeKernel
  variable=n_epsilon
 []
 [es]
  type=FVCoupledForce
  variable=n_epsilon
  v={P}
  coef={EC}
 []
 [wt]
  type=PhysicsFVMassFractionTimeDerivative
  variable=w_Om
  rho=rho_const
 []
 [ws]
  type=PhysicsFVSpeciesReactionSource
  variable=w_Om
  source=Om_edetach_mass_source
 []
[]
[Postprocessors]
 [ne]
  type=ElementAverageFunctorPostprocessor
  functor=n_e
  execute_on='INITIAL TIMESTEP_END'
 []
 [ee]
  type=ElementAverageFunctorPostprocessor
  functor=n_epsilon
  execute_on='INITIAL TIMESTEP_END'
 []
 [wm]
  type=ElementAverageFunctorPostprocessor
  functor=w_Om
  execute_on='INITIAL TIMESTEP_END'
 []
 [wo]
  type=ElementAverageFunctorPostprocessor
  functor=w_O_constraint
  execute_on='INITIAL TIMESTEP_END'
 []
 [me]
  type=ElementAverageFunctorPostprocessor
  functor=mean_en_solved
  execute_on='INITIAL TIMESTEP_END'
 []
 [te]
  type=ElementAverageFunctorPostprocessor
  functor=Te_eV
  execute_on='INITIAL TIMESTEP_END'
 []
 [rr]
  type=ElementAverageFunctorPostprocessor
  functor={P}
  execute_on='INITIAL TIMESTEP_END'
 []
 [sm]
  type=ElementAverageFunctorPostprocessor
  functor=Om_edetach_mass_source
  execute_on='INITIAL TIMESTEP_END'
 []
 [so]
  type=ElementAverageFunctorPostprocessor
  functor=O_edetach_mass_source
  execute_on='INITIAL TIMESTEP_END'
 []
 [se]
  type=ElementAverageFunctorPostprocessor
  functor=electron_edetach_number_source
  execute_on='INITIAL TIMESTEP_END'
 []
[]
[Executioner]
 type=Transient
 dt={DT}
 end_time={DT}
 solve_type=NEWTON
[]
[Outputs]
 csv=true
 exodus=false
[]
"""
def val(z):
 if len(z)<2: raise AssertionError("rows")
 a,b=z[0],z[-1]; g=lambda x,n:float(x[n])
 n0,n=g(a,"ne"),g(b,"ne"); e0,e=g(a,"ee"),g(b,"ee"); w0,w=g(a,"wm"),g(b,"wm"); o0,o=g(a,"wo"),g(b,"wo"); m=g(b,"me"); t=g(b,"te"); q=g(b,"rr"); sm=g(b,"sm"); so=g(b,"so"); se=g(b,"se")
 if not(n>n0>0 and 0<e<e0 and 0<w<w0 and o>o0>0 and q>0 and sm<0<so and se>0): raise AssertionError("sign")
 eq(o+w,1,r=0,a0=2e-12); eq(m,ER*e/n); eq(t,(2/3)*m); eq(-sm/M,q); eq(so/M,q); eq(se/NA,q); eq(sm+so,0,r=0)
 eq(q,rate(n,e,w),r=9e-6,a0=1e-15); eq(NR*(n-n0)/DT,se,a0=1); eq(D*(w-w0)/DT,sm); eq(D*(o-o0)/DT,so); eq((e-e0)/DT,EC*q,a0=1e-8)
 de=NR*(n-n0); dm=NA*D*(w-w0)/M; eq(de+dm,0,r=0,a0=max(2,2e-5*abs(de)))
 return {"initial":{"n_e_hat":n0,"n_epsilon_hat":e0,"w_Om":w0},"final":{"n_e_hat":n,"n_epsilon_hat":e,"w_Om":w,"w_O":o,"mean_en_solved_eV":m,"Te_eV":t,"R_detach_Om_mol_m3_s":q},"closure":{"heavy_mass_source_sum":sm+so,"charge_delta_sum":de+dm,"energy_loss_eV_per_event":L}}
def syn():
 q=rate(1,1,W)
 for _ in range(300):
  n=1+DT*NA*q/NR; w=W-DT*M*q/D; e=1+DT*EC*q; q2=rate(n,e,w)
  if math.isclose(q,q2,rel_tol=1e-14): q=q2; break
  q=q2
 def row(n,e,w,q): return {"ne":n,"ee":e,"wm":w,"wo":1-w,"me":ER*e/n,"te":(2/3)*ER*e/n,"rr":q,"sm":-M*q,"so":M*q,"se":NA*q}
 return [row(1,1,W,rate(1,1,W)),row(n,e,w,q)]
def selftest():
 z=syn(); val(z)
 for key,fn in [("rr",lambda x:1.01*x),("se",lambda x:2*x),("sm",lambda x:-x),("te",lambda x:1.01*x),("ee",lambda x:1+abs(x-1))]:
  y=[dict(x) for x in z]; y[-1][key]=fn(y[-1][key])
  try: val(y)
  except AssertionError: pass
  else: raise AssertionError("mutation")
 s=text()
 req=("property_name=R_detach_Om","type=PhysicsFVSpeciesReactionSource","type=PhysicsFVElectronReactionSource","type=FVCoupledForce","v=R_detach_Om")
 if any(x not in s for x in req) or s.count("property_name=R_detach_Om")!=1: raise AssertionError("owner")
 if any(x in s for x in ("PhysicsElectronImpactRateMaterial","PhysicsFVElectronReactionEnergySource")): raise AssertionError("wrong owner")
 print("STAGE5_EDETACH_RUNTIME_CHECKER_SELFTEST_PASS")
def static():
 c=json.loads(C.read_text()); r=c["reaction"]; q=c["rate_law"]; p=c["projection"]; s=c["source_provenance"]
 if c["status"]!="CONTRACT_FROZEN" or c["slice"]!="S5-C_EDETACH_OM" or r["canonical_progress"]!=P or r["heavy_stoichiometry"]!={"Om":-1,"O":1} or r["net_electron_particle_stoich"]!=1: raise AssertionError("contract")
 if (q["particle_rate_prefactor_m3_s"],q["activation_eV"],q["temperature_exponent"],q["progress_owner"])!=(A,E,B,"ADParsedFunctorMaterial"): raise AssertionError("rate")
 if q["canonical_temperature_mapping"]!="Te_eV=(2/3)*mean_en_solved_eV" or s["collision_type"]!="Ionization" or s["collision_metadata_value"]!=L or p["electron_number_source"]!="+N_A*R_detach_Om" or p["energy_projection_owner"]!="FVCoupledForce": raise AssertionError("semantics")
 selftest(); print("STAGE5_EDETACH_IMPLEMENTATION_P0_PASS")
def run(exe,out,sha,base):
 static(); exe=Path(exe).resolve()
 with tempfile.TemporaryDirectory() as td:
  d=Path(td); i=d/"c.i"; i.write_text(text()); subprocess.run([sys.executable,str(R/"bin/physics.py"),"preflight",str(i)],cwd=R,check=True)
  for cmd in ([str(exe),"--check-input","-i",i.name],[str(exe),"-i",i.name]):
   p=subprocess.run(cmd,cwd=d,text=True,capture_output=True)
   if p.returncode: raise AssertionError(p.stdout+p.stderr)
  x=val(list(csv.DictReader((d/"c_out.csv").open())))
 ev={"schema_version":1,"stage":"STAGE_5","slice":"S5-C_EDETACH_OM","decision":"LOCAL_RUNTIME_ACCURACY","result":"PASS","integrated_physics_accuracy":"NOT_ESTABLISHED","repository_sha":sha,"build_base_ref":base,"executable_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"runtime":x}
 if out: Path(out).write_text(json.dumps(ev,indent=2,sort_keys=True)+"\n")
 z=x["final"]; print(f"STAGE5_EDETACH_LOCAL_RUNTIME_PASS R={z['R_detach_Om_mol_m3_s']:.12g} n_e_hat={z['n_e_hat']:.12g} mean_en={z['mean_en_solved_eV']:.12g}")
def main():
 p=argparse.ArgumentParser(); p.add_argument("--self-test",action="store_true"); p.add_argument("--static",action="store_true"); p.add_argument("--executable"); p.add_argument("--evidence-out"); p.add_argument("--repository-sha"); p.add_argument("--build-base-ref"); a=p.parse_args()
 if a.self_test:selftest()
 elif a.static:static()
 elif a.executable:run(a.executable,a.evidence_out,a.repository_sha,a.build_base_ref)
 else:p.error("mode")
if __name__=="__main__":main()
