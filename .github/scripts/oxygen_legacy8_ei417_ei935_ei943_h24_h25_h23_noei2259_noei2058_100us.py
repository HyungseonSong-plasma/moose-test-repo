#!/usr/bin/env python3
"""14-channel fresh Oxygen ICP: add H23 after EI943+H24+H25.

New reaction H23 O+ + O- -> 2 O(3P); original screenshot QDB-API 1377
A=1e-7 cm3/s, n=0, E=0 -> provisional k=1e-13 m3/s.
400W/1000W 0-100us; keep H24/H25, exclude EI2058/EI2259/H05/EI2072/EI2074.
Research only: numeric source, ion-neutral energy partition SCIENCE_HOLD.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os
from pathlib import Path

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
NEW_ID="H23"
K_CM3_S=1.0e-7
K_M3_S=1.0e-13
N_A=6.02214076e23
EXCLUDED={"H05","EI-2058","EI-2259","EI-2072","EI-2074"}
VARIANT="LEGACY8_EI417_EI935_EI943_H24_H25_H23_NO_EI2058_NO_EI2259_NO_HOLD"

CONTENT="""# H23: O+ + O- -> 2 O(3P); mutual neutralization.
# QDB-API 1377 screenshot A=1e-7 cm3/s n=0 E=0; science HOLD.
# c_Op/c_Om in mol/m3; R=k*N_A*c_Op*c_Om [mol/m3/s].
# O+ -R, O- -R, neutral O +2R; net neutral mass +0.032*R.
# Electron number source=0; electron energy source=0 (no invented heating).
# Energy partition from ionic neutralization remains unmodelled SCIENCE_HOLD.
[FunctorMaterials]
  [h23_op_target]
    type = ADParsedFunctorMaterial
    property_name = c_Op_H23
    functor_names = 'log_nop'
    functor_symbols = 'lncp'
    expression = 'exp(lncp)'
    block = plasma
  []
  [h23_om_target]
    type = ADParsedFunctorMaterial
    property_name = c_Om_H23
    functor_names = 'log_nm'
    functor_symbols = 'lncm'
    expression = 'exp(lncm)'
    block = plasma
  []
  [h23_progress]
    type = ADParsedFunctorMaterial
    property_name = R_H23
    functor_names = 'c_Op_H23 c_Om_H23'
    functor_symbols = 'cp cm'
    expression = '6.02214076e10*cp*cm'
    block = plasma
  []
  [h23_positive_ion_loss]
    type = ADParsedFunctorMaterial
    property_name = S_Op_molar_H23
    functor_names = 'R_H23'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [h23_negative_ion_loss]
    type = ADParsedFunctorMaterial
    property_name = S_Om_molar_H23
    functor_names = 'R_H23'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [h23_atomic_oxygen_birth]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_H23
    functor_names = 'R_H23'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [h23_neutral_mass_birth]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_H23
    functor_names = 'R_H23'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [h23_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_H23
    functor_names = 'S_Op_molar_H23 S_Om_molar_H23'
    functor_symbols = 'op om'
    expression = 'op-om'
    block = plasma
  []
  [h23_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_H23
    functor_names = 'S_Op_molar_H23 S_Om_molar_H23 S_O_mass_H23'
    functor_symbols = 'op om o'
    expression = '0.016*op+0.016*om+o'
    block = plasma
  []
  [h23_neutral_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_closure_H23
    functor_names = 'S_neutral_mass_H23 S_O_mass_H23'
    functor_symbols = 'total o'
    expression = 'total-o'
    block = plasma
  []
  [h23_oxygen_atoms_closure]
    type = ADParsedFunctorMaterial
    property_name = S_oxygen_nuclei_closure_H23
    functor_names = 'S_Op_molar_H23 S_Om_molar_H23 R_H23'
    functor_symbols = 'op om prog'
    expression = 'op+om+2*prog'
    block = plasma
  []
[]
[FVKernels]
  [h23_atomic_positive_ion]
    type = FVCoupledForce
    variable = log_nop
    v = S_Op_molar_H23
    coef = 1.0
    block = plasma
  []
  [h23_negative_ion]
    type = FVCoupledForce
    variable = log_nm
    v = S_Om_molar_H23
    coef = 1.0
    block = plasma
  []
  [h23_atomic_oxygen]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_H23
    block = plasma
  []
  [h23_neutral_pressure]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_H23
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [h23_progress_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_H23
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h23_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_H23
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h23_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_H23
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h23_neutral_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_closure_H23
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h23_oxygen_atoms_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_oxygen_nuclei_closure_H23
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def load_parent():
    path=Path(os.environ.get("H25",
        "_legacy6_control/.github/scripts/oxygen_legacy8_ei417_ei935_ei943_h24_h25_noei2259_noei2058_100us.py"))
    spec=importlib.util.spec_from_file_location("h23_h25_parent",path)
    if not spec or not spec.loader:raise FileNotFoundError(path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def overlay(power):
    return CHEM/f"h23_op_om_mutual_neutralization_{power}w_100us_dt1000ns_overlay.i"

def expected(parent):
    return parent.expected(parent.load_parent())+[NEW_ID]

def validate(src):
    for token in (
        "property_name = R_H23",
        "functor_names = 'log_nop'",
        "functor_names = 'log_nm'",
        "functor_names = 'c_Op_H23 c_Om_H23'",
        "expression = '6.02214076e10*cp*cm'",
        "variable = log_nop",
        "variable = log_nm",
        "variable = w_O",
        "variable = p",
        "v = S_Op_molar_H23",
        "v = S_Om_molar_H23",
        "source = S_O_mass_H23",
        "v = S_neutral_mass_H23",
        "expression = '-R'",
        "expression = '0.032*R'",
        "expression = 'op-om'",
        "expression = '0.016*op+0.016*om+o'",
        "expression = 'total-o'",
        "expression = 'op+om+2*prog'",
    ):
        if token not in src:raise ValueError("H23 missing term "+token)
    if src.count("property_name = R_H23")!=1:
        raise ValueError("H23 must have exactly one rate owner")
    if src.count("variable = log_nop")!=1 or src.count("variable = log_nm")!=1:
        raise ValueError("H23 must remove each ion once")
    if src.count("type = FVCoupledForce")!=3:
        raise ValueError("H23 needs two ion sinks and one pressure/mass source")
    if any(token in src for token in (
        "variable = log_ne","variable = log_energy","variable = log_ni",
        "R_H05","R_EI2058","R_EI2259","R_EI2072","R_EI2074"
    )):
        raise ValueError("H23 has forbidden electron or excluded chemistry")

def verify(power):
    h25=load_parent();h24=h25.load_parent();ei943=h24.load_parent();ei935=ei943.load_parent()
    b8=ei935.l8();l7=b8.l7();m=l7.legacy6()
    for key,value in (
        ("OXYGEN_RESEARCH_EI2738_FORMULA","1"),
        ("OXYGEN_RESEARCH_FULL24","0"),
        ("OXYGEN_RESEARCH_LUMPED_O2A","0"),
    ):
        if os.environ.get(key)!=value:raise ValueError("unexpected research flag "+key)
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    b8.overlay_ok(b8.overlay(power).read_text())
    if ei935.f417(power).read_text()!=ei935.c417():
        raise ValueError("EI417 source changed")
    ei935.validate_935(ei935.f935(power).read_text())
    ei943.validate(ei943.overlay(power).read_text())
    h24.validate(h24.overlay(power).read_text())
    h25.validate(h25.overlay(power).read_text())
    validate(overlay(power).read_text())
    tables=(b8.RATE,ei935.R417,ei935.R935,ei943.RATE)
    digest={name:b8.table_ok(CHEM/"private_rates"/name) for name in tables}
    j=json.loads((m.result(power)/"legacy6_latest_variant.json").read_text())
    channels=expected(h25)
    if j.get("chemistry_channels")!=channels or len(channels)!=14:
        raise ValueError("not exact 14-channel H23 chemistry")
    if EXCLUDED.intersection(channels):
        raise ValueError("excluded or held reaction enabled")
    if any((
        j.get("variant")!=VARIANT,
        j.get("native_initialization")!="fresh_not_restarted",
        j.get("scientific_acceptance")!="HOLD",
        j.get("physics_source_sha")!="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
        j.get("ei407_lookup_sha256")!=digest[b8.RATE],
        j.get("ei417_lookup_sha256")!=digest[ei935.R417],
        j.get("ei935_lookup_sha256")!=digest[ei935.R935],
        j.get("ei943_lookup_sha256")!=digest[ei943.RATE],
        j.get("h24_k_m3_s")!=h24.K_M3_S,
        j.get("h25_k_m3_s_at_300K")!=h25.K_M3_S_AT_300K,
        j.get("h23_k_m3_s")!=K_M3_S,
        any(key.startswith(("ei2058_","ei2259_")) for key in j),
    )):
        raise ValueError("H23 configuration and source provenance mismatch")
    print("H23_14CH_P0_PASS",power)
    return h25,h24,ei943,ei935,b8,l7,m,j

def prepare(power):
    h25=load_parent()
    h25.prepare(power)  # exact self-validating fresh 13-channel parent
    validate(CONTENT)
    dest=overlay(power)
    if dest.exists():raise ValueError("refuse existing H23 overlay overwrite")
    dest.write_text(CONTENT)
    h24=h25.load_parent();ei943=h24.load_parent();ei935=ei943.load_parent()
    m=ei935.l8().l7().legacy6()
    path=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(path.read_text())
    if j.get("chemistry_channels")!=h25.expected(h24):
        raise ValueError("H23 parent is not exact 13-channel H25 configuration")
    j.update({
        "variant":VARIANT,
        "chemistry_channels":expected(h25),
        "hold_excluded":sorted(EXCLUDED),
        "h23_reaction":"O+ + O- -> 2 O(3P)",
        "h23_qdb_api_id":1377,
        "h23_coefficient_source":"QDB screenshot; numeric rate and energy partition independent verification pending",
        "h23_rate_coefficient_cgs_cm3_s":K_CM3_S,
        "h23_k_m3_s":K_M3_S,
        "h23_rate_mode":"provisional_constant_heavy_ion_mutual_neutralization",
        "h23_energy_partition":"no_electron_energy_source_ion_neutralization_heat_science_HOLD",
        "h23_neutral_mass_effect":"positive_0.032kg_per_mol_reaction",
        "scientific_acceptance":"HOLD",
    })
    path.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("H23_14CH_PREPARED",power)

def patch(power):
    h25,h24,ei943,ei935,b8,l7,m,j=verify(power)
    path=m.CHEM/"issue397_l1_power_scan_replay.sh"
    before=path.read_text()
    new_check=ei935.NEW_CHECK+" '$EI943_OVERLAY' '$H24_OVERLAY' '$H25_OVERLAY' '$H23_OVERLAY'"
    new_solve=ei935.NEW_SOLVE.replace(" Outputs/file_base=",
        " '$EI943_OVERLAY' '$H24_OVERLAY' '$H25_OVERLAY' '$H23_OVERLAY' Outputs/file_base=")
    if before.count(ei935.OLD_CHECK)!=1 or before.count(ei935.OLD_SOLVE)!=1:
        raise ValueError("pinned replay commands no longer match")
    if any(name in before for name in (
        "$EI407_OVERLAY","$EI417_OVERLAY","$EI935_OVERLAY","$EI943_OVERLAY",
        "$H24_OVERLAY","$H25_OVERLAY","$H23_OVERLAY","$EI2058_OVERLAY",
        "$EI2259_OVERLAY","$H05_OVERLAY","$EI2072_OVERLAY","$EI2074_OVERLAY"
    )):
        raise ValueError("replay already patched")
    after=before.replace(ei935.OLD_CHECK,new_check,1).replace(ei935.OLD_SOLVE,new_solve,1)
    if after.count(new_check)!=1 or after.count(new_solve)!=1:
        raise ValueError("H23 injected argv count mismatch")
    if "$EI2058_OVERLAY" in after or "$EI2259_OVERLAY" in after:
        raise ValueError("excluded chemistry in replay")
    path.write_text(after)
    (m.result(power)/"h23_argv_patch.json").write_text(json.dumps({
        "power_W":power,
        "source_sha256":hashlib.sha256(before.encode()).hexdigest(),
        "patched_sha256":hashlib.sha256(after.encode()).hexdigest(),
        "overlays":["EI-2738","EI-407","EI-417","EI-935","EI-943","H24","H25","H23"],
        "h24_k_m3_s":h24.K_M3_S,
        "h25_k_m3_s_at_300K":h25.K_M3_S_AT_300K,
        "h25_tgas_K":h25.T_GAS_K,
        "h23_k_m3_s":K_M3_S,
        "excluded":sorted(EXCLUDED),
        "scientific_acceptance":"HOLD",
    },indent=2,sort_keys=True)+"\n")
    print("H23_14CH_ARGV_PASS",power)

def archive(power):
    h25,h24,ei943,ei935,b8,l7,m,j=verify(power)
    files=(l7.overlay_path(m,power),b8.overlay(power),ei935.f417(power),
           ei935.f935(power),ei943.overlay(power),h24.overlay(power),
           h25.overlay(power),overlay(power))
    m.PERSIST=tuple(m.PERSIST)+tuple(file.name for file in files)
    m.verify_and_archive(power)
    manifest=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(manifest.read_text())
    if any((
        not saved.get("verified_full_native_100us_checkpoint"),
        saved.get("native_endpoint_s")!=1e-4,
        saved.get("chemistry_channels")!=expected(h25),
        saved.get("variant")!=VARIANT,
        saved.get("scientific_acceptance")!="HOLD",
        bool(EXCLUDED.intersection(saved.get("chemistry_channels",[]))),
    )):
        raise ValueError("14-channel 100us checkpoint or restart not verified")
    inputs=[item["path"] for item in saved["inventory"]["inputs"]]
    for f in files:
        if not any(path.endswith("/"+f.name) for path in inputs):
            raise ValueError("missing archived input "+f.name)
    if any("private_rates" in name or any(t in name.lower() for t in (
        "h05_associative","ei2058_o2a","ei2259_o2plus","ei2072_o2a","ei2074_o2a"
    )) for name in inputs):
        raise ValueError("archived private or excluded input")
    saved.update({
        "restart_requires_exact_ei417_ei935_ei943_h24_h25_h23_chemistry":True,
        "restart_requires_exact_legacy6_chemistry":False,
        "hold_excluded":sorted(EXCLUDED),
        "h24_recovery_k_m3_s":h24.K_M3_S,
        "h25_recovery_k_m3_s_at_300K":h25.K_M3_S_AT_300K,
        "h23_recovery_k_m3_s":K_M3_S,
        "h23_scientific_status":"HOLD",
        "h24_scientific_status":"HOLD",
        "h25_scientific_status":"HOLD",
    })
    for key,name in (
        ("ei407",b8.RATE),("ei417",ei935.R417),
        ("ei935",ei935.R935),("ei943",ei943.RATE)
    ):
        saved[key+"_recovery_private_rate_required"]=name
        saved[key+"_recovery_rate_sha256"]=j[key+"_lookup_sha256"]
    manifest.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("H23_14CH_NATIVE_100US_PASS",power)

def self_test():
    h25=load_parent()
    h25.self_test()
    channels=expected(h25)
    assert len(channels)==len(set(channels))==14
    assert not EXCLUDED.intersection(channels)
    assert abs(K_M3_S-K_CM3_S*1e-6)/K_M3_S<1e-14
    assert abs(K_M3_S*N_A-6.02214076e10)/6.02214076e10<1e-14
    assert abs(-0.016-0.016+0.032)<1e-15
    assert abs(0.032-0.032)<1e-15
    assert -1-1+2==0
    assert -1-(-1)==0
    validate(CONTENT)
    for mutant in (
        CONTENT.replace("property_name = R_H23","property_name = R_INVALID"),
        CONTENT.replace("variable = log_nop","variable = log_ni"),
        CONTENT.replace("variable = log_nm","variable = log_ne"),
        CONTENT.replace("expression = '6.02214076e10*cp*cm'",
                        "expression = '6.02214076e16*cp*cm'"),
        CONTENT.replace("expression = 'op-om'","expression = 'op+om'"),
        CONTENT.replace("expression = '0.032*R'","expression = '0.016*R'"),
        CONTENT.replace("expression = '0.016*op+0.016*om+o'",
                        "expression = '0.032*op+0.016*om+o'"),
        CONTENT.replace("expression = 'op+om+2*prog'","expression = 'op+om+prog'"),
    ):
        try:validate(mutant)
        except ValueError:pass
        else:raise AssertionError("invalid H23 mutation not rejected")
    print("H23_14CH_SELFTEST_PASS")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    for name in ("self-test","prepare-variant","verify-fourteen",
                 "patch-replay-argv","verify-and-archive"):
        group.add_argument("--"+name,action="store_true")
    parser.add_argument("--power-w",type=int,choices=(400,1000))
    args=parser.parse_args()
    if args.self_test:self_test()
    elif args.power_w is None:parser.error("--power-w required")
    elif args.prepare_variant:prepare(args.power_w)
    elif args.verify_fourteen:verify(args.power_w)
    elif args.patch_replay_argv:patch(args.power_w)
    else:archive(args.power_w)
