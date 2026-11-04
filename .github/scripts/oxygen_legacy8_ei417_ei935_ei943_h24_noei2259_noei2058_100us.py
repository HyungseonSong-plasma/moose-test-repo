#!/usr/bin/env python3
"""H24-only controlled extension of Run 41798717903.

Baseline 11 channels: Legacy8 + EI-417 + EI-935 + EI-943.
Addition: H24, O- + O2+ -> O2 + O.
Exclude EI-2058, EI-2259, H05, EI-2072, EI-2074.
Fresh 0-100us 400/1000W. SCIENCE_HOLD for unverified QDB coefficients
and unmodelled neutralization heat/ion-energy partition.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os
from pathlib import Path

CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
NEW_ID = "H24"
K_CM3_S = 1.0e-7
K_M3_S = 1.0e-13
NA = 6.02214076e23
EXCLUDED = {"H05", "EI-2058", "EI-2259", "EI-2072", "EI-2074"}
VARIANT = "LEGACY8_EI417_EI935_EI943_H24_NO_EI2058_NO_EI2259_NO_HOLD"

CONTENT = """# H24 O- + O2+ -> O2(X) + O(3P): ion-ion mutual neutralization.
# QDB-API 1378 screenshot A=1e-7 cm3/s, n=0, E=0 (research/provisional).
# k=1e-13 m3/s. c_Om and c_O2p are mol/m3, hence R=k*N_A*c_Om*c_O2p.
# Net electron source = 0; net electron energy source = 0 in this model.
# Neutralization exothermicity and neutral/ion heating remain SCIENCE_HOLD.
# Neutral O2 is constrained remainder; pressure gets +0.048*R and
# w_O gets +0.016*R, leaving O2 mass source +0.032*R in remainder.
[FunctorMaterials]
  [h24_om_target]
    type = ADParsedFunctorMaterial
    property_name = c_Om_H24
    functor_names = 'log_nm'
    functor_symbols = 'lncm'
    expression = 'exp(lncm)'
    block = plasma
  []
  [h24_o2p_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2p_H24
    functor_names = 'log_ni'
    functor_symbols = 'lnci'
    expression = 'exp(lnci)'
    block = plasma
  []
  [h24_progress]
    type = ADParsedFunctorMaterial
    property_name = R_H24
    functor_names = 'c_Om_H24 c_O2p_H24'
    functor_symbols = 'cm ci'
    expression = '6.02214076e10*cm*ci'
    block = plasma
  []
  [h24_negative_ion_loss]
    type = ADParsedFunctorMaterial
    property_name = S_Om_molar_H24
    functor_names = 'R_H24'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [h24_positive_ion_loss]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_molar_H24
    functor_names = 'R_H24'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [h24_o_mass]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_H24
    functor_names = 'R_H24'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [h24_o2_mass_implicit]
    type = ADParsedFunctorMaterial
    property_name = S_O2_mass_H24_implicit
    functor_names = 'R_H24'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [h24_neutral_mass]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_H24
    functor_names = 'R_H24'
    functor_symbols = 'R'
    expression = '0.048*R'
    block = plasma
  []
  [h24_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_H24
    functor_names = 'S_Om_molar_H24 S_O2p_molar_H24'
    functor_symbols = 'om ip'
    expression = '-om+ip'
    block = plasma
  []
  [h24_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_H24
    functor_names = 'S_Om_molar_H24 S_O2p_molar_H24 S_O_mass_H24 S_O2_mass_H24_implicit'
    functor_symbols = 'om ip o o2'
    expression = '0.016*om+0.032*ip+o+o2'
    block = plasma
  []
  [h24_neutral_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_closure_H24
    functor_names = 'S_neutral_mass_H24 S_O_mass_H24 S_O2_mass_H24_implicit'
    functor_symbols = 'total o o2'
    expression = 'total-o-o2'
    block = plasma
  []
  [h24_oxygen_atoms_closure]
    type = ADParsedFunctorMaterial
    property_name = S_oxygen_nuclei_closure_H24
    functor_names = 'S_Om_molar_H24 S_O2p_molar_H24 R_H24'
    functor_symbols = 'om ip prog'
    expression = 'om+2*ip+3*prog'
    block = plasma
  []
[]
[FVKernels]
  [h24_negative_ion]
    type = FVCoupledForce
    variable = log_nm
    v = S_Om_molar_H24
    coef = 1.0
    block = plasma
  []
  [h24_molecular_positive_ion]
    type = FVCoupledForce
    variable = log_ni
    v = S_O2p_molar_H24
    coef = 1.0
    block = plasma
  []
  [h24_atomic_oxygen]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_H24
    block = plasma
  []
  [h24_neutral_pressure]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_H24
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [h24_progress_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_H24
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h24_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_H24
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h24_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_H24
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h24_neutral_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_closure_H24
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h24_oxygen_atoms_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_oxygen_nuclei_closure_H24
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def load_parent():
    path = Path(os.environ.get(
        "EI943", "_legacy6_control/.github/scripts/oxygen_legacy8_ei417_ei935_ei943_no2259_no2058_100us.py"
    ))
    spec = importlib.util.spec_from_file_location("h24_ei943_parent", path)
    if not spec or not spec.loader:
        raise FileNotFoundError(path)
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    return p

def overlay(power):
    return CHEM/f"h24_om_o2p_mutual_neutralization_{power}w_100us_dt1000ns_overlay.i"

def expected(parent):
    return parent.expected(parent.load_parent()) + [NEW_ID]

def validate(src):
    for token in (
        "property_name = R_H24",
        "functor_names = 'c_Om_H24 c_O2p_H24'",
        "expression = '6.02214076e10*cm*ci'",
        "variable = log_nm",
        "variable = log_ni",
        "variable = w_O",
        "variable = p",
        "v = S_Om_molar_H24",
        "v = S_O2p_molar_H24",
        "source = S_O_mass_H24",
        "v = S_neutral_mass_H24",
        "expression = '-R'",
        "expression = '0.016*R'",
        "expression = '0.032*R'",
        "expression = '0.048*R'",
        "expression = '-om+ip'",
        "expression = '0.016*om+0.032*ip+o+o2'",
        "expression = 'total-o-o2'",
        "expression = 'om+2*ip+3*prog'",
    ):
        if token not in src:
            raise ValueError("H24 source missing "+token)
    if src.count("property_name = R_H24") != 1:
        raise ValueError("H24 must have one rate owner")
    if src.count("variable = log_nm") != 1 or src.count("variable = log_ni") != 1:
        raise ValueError("H24 must remove both ions once")
    if any(t in src for t in ("variable = log_ne", "variable = log_energy",
            "R_H05", "R_EI2058", "R_EI2259", "R_EI2072", "R_EI2074")):
        raise ValueError("H24 contains electron or excluded chemistry source")
    if src.count("type = FVCoupledForce") != 3:
        raise ValueError("H24 requires two ion sinks and one neutral mass source")

def verify(power):
    p=load_parent();b=p.load_parent();b8=b.l8();l7=b8.l7();m=l7.legacy6()
    for key,val in (
        ("OXYGEN_RESEARCH_EI2738_FORMULA","1"),
        ("OXYGEN_RESEARCH_FULL24","0"),
        ("OXYGEN_RESEARCH_LUMPED_O2A","0"),
    ):
        if os.environ.get(key)!=val:
            raise ValueError("unexpected research flag "+key)
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    b8.overlay_ok(b8.overlay(power).read_text())
    if b.f417(power).read_text()!=b.c417():
        raise ValueError("EI417 source changed")
    b.validate_935(b.f935(power).read_text())
    p.validate(p.overlay(power).read_text())
    validate(overlay(power).read_text())
    rate_names=(b8.RATE,b.R417,b.R935,p.RATE)
    digests={name:b8.table_ok(CHEM/"private_rates"/name) for name in rate_names}
    manifest=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(manifest.read_text())
    if j.get("chemistry_channels") != expected(p) or len(expected(p)) != 12:
        raise ValueError("not exact twelve-channel H24 chemistry")
    if EXCLUDED.intersection(j.get("chemistry_channels",[])):
        raise ValueError("excluded chemistry active")
    if any((
        j.get("variant") != VARIANT,
        j.get("native_initialization")!="fresh_not_restarted",
        j.get("scientific_acceptance")!="HOLD",
        j.get("physics_source_sha")!="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
        j.get("ei407_lookup_sha256")!=digests[b8.RATE],
        j.get("ei417_lookup_sha256")!=digests[b.R417],
        j.get("ei935_lookup_sha256")!=digests[b.R935],
        j.get("ei943_lookup_sha256")!=digests[p.RATE],
        j.get("h24_k_m3_s")!=K_M3_S,
        any(key.startswith(("ei2058_","ei2259_")) for key in j),
    )):
        raise ValueError("12-channel H24 source or provenance mismatch")
    print("H24_12CH_P0_PASS",power)
    return p,b,b8,l7,m,j

def prepare(power):
    p=load_parent()
    p.prepare(power)  # self-validating exact fresh 11ch EI943 parent
    validate(CONTENT)
    path=overlay(power)
    if path.exists():
        raise ValueError("refuse H24 overlay overwrite")
    path.write_text(CONTENT)
    b=p.load_parent();m=b.l8().l7().legacy6()
    manifest=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(manifest.read_text())
    if j.get("chemistry_channels")!=p.expected(b):
        raise ValueError("H24 parent is not exact 11-channel EI943 model")
    j.update({
        "variant":VARIANT,
        "chemistry_channels":expected(p),
        "hold_excluded":sorted(EXCLUDED),
        "h24_reaction":"O- + O2+ -> O2(X) + O(3P)",
        "h24_qdb_api_id":1378,
        "h24_coefficient_source":"QDB screenshot, numeric source and temperature convention pending verification",
        "h24_rate_coefficient_cgs_cm3_s":K_CM3_S,
        "h24_k_m3_s":K_M3_S,
        "h24_rate_mode":"provisional_constant_heavy_ion_mutual_neutralization",
        "h24_energy_mode":"no_explicit_electron_energy_source_neutralization_heat_science_HOLD",
        "h24_neutral_o2_representation":"constrained_mass_fraction_remainder",
        "scientific_acceptance":"HOLD",
    })
    manifest.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("H24_12CH_PREPARED",power)

def patch(power):
    p,b,b8,l7,m,j=verify(power)
    script=m.CHEM/"issue397_l1_power_scan_replay.sh"
    original=script.read_text()
    new_check=b.NEW_CHECK+" '$EI943_OVERLAY' '$H24_OVERLAY'"
    new_solve=b.NEW_SOLVE.replace(" Outputs/file_base=",
        " '$EI943_OVERLAY' '$H24_OVERLAY' Outputs/file_base=")
    if original.count(b.OLD_CHECK)!=1 or original.count(b.OLD_SOLVE)!=1:
        raise ValueError("pinned unmodified replay command differs")
    if any(name in original for name in (
        "$EI407_OVERLAY","$EI417_OVERLAY","$EI935_OVERLAY","$EI943_OVERLAY",
        "$H24_OVERLAY","$EI2259_OVERLAY","$EI2058_OVERLAY",
        "$H05_OVERLAY","$EI2072_OVERLAY","$EI2074_OVERLAY"
    )):
        raise ValueError("replay already contains channel overlays")
    updated=original.replace(b.OLD_CHECK,new_check,1).replace(b.OLD_SOLVE,new_solve,1)
    if updated.count(new_check)!=1 or updated.count(new_solve)!=1:
        raise ValueError("H24 replay argv patch mismatch")
    if "$EI2058_OVERLAY" in updated or "$EI2259_OVERLAY" in updated:
        raise ValueError("unintended held channels in replay")
    script.write_text(updated)
    patchfile=m.result(power)/"h24_argv_patch.json"
    patchfile.write_text(json.dumps({
        "power_W":power,
        "source_sha256":hashlib.sha256(original.encode()).hexdigest(),
        "patched_sha256":hashlib.sha256(updated.encode()).hexdigest(),
        "overlays":["EI-2738","EI-407","EI-417","EI-935","EI-943","H24"],
        "h24_rate_coefficient_m3_s":K_M3_S,
        "excluded":sorted(EXCLUDED),
        "scientific_acceptance":"HOLD",
    },indent=2,sort_keys=True)+"\n")
    print("H24_12CH_ARGV_PASS",power)

def archive(power):
    p,b,b8,l7,m,j=verify(power)
    files=(l7.overlay_path(m,power),b8.overlay(power),
           b.f417(power),b.f935(power),p.overlay(power),overlay(power))
    m.PERSIST=tuple(m.PERSIST)+tuple(f.name for f in files)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if any((
        not saved.get("verified_full_native_100us_checkpoint"),
        saved.get("native_endpoint_s")!=1e-4,
        saved.get("chemistry_channels")!=expected(p),
        saved.get("variant")!=VARIANT,
        saved.get("scientific_acceptance")!="HOLD",
        bool(EXCLUDED.intersection(saved.get("chemistry_channels",[]))),
    )):
        raise ValueError("H24 12-channel 100us checkpoint not verified")
    inventory=[entry["path"] for entry in saved["inventory"]["inputs"]]
    for file in files:
        if not any(name.endswith("/"+file.name) for name in inventory):
            raise ValueError("archive missing required overlay "+file.name)
    if any("private_rates" in name or any(t in name.lower() for t in (
        "h05_associative","ei2058_o2a","ei2259_o2plus","ei2072_o2a","ei2074_o2a"))
        for name in inventory):
        raise ValueError("archived forbidden or private input")
    saved.update({
        "restart_requires_exact_ei417_ei935_ei943_h24_chemistry":True,
        "restart_requires_exact_legacy6_chemistry":False,
        "hold_excluded":sorted(EXCLUDED),
        "h24_recovery_k_m3_s":K_M3_S,
        "h24_energy_partition":"SCIENTIFIC_HOLD",
        "h24_scientific_status":"HOLD",
    })
    for key,name in (
        ("ei407",b8.RATE),("ei417",b.R417),("ei935",b.R935),("ei943",p.RATE)
    ):
        saved[key+"_recovery_private_rate_required"]=name
        saved[key+"_recovery_rate_sha256"]=j[key+"_lookup_sha256"]
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("H24_12CH_NATIVE_100US_PASS",power)

def self_test():
    p=load_parent()
    p.self_test()
    chem=expected(p)
    assert len(chem)==len(set(chem))==12
    assert not EXCLUDED.intersection(chem)
    assert K_M3_S==K_CM3_S*1.0e-6
    assert K_M3_S*NA==6.02214076e10
    assert abs(-0.016-0.032+0.016+0.032)<1e-15
    assert abs(0.048-0.016-0.032)<1e-15
    assert abs(-1-2+1+2)<1e-15
    assert abs(-(-1)+(-1))<1e-15
    validate(CONTENT)
    for corrupt in (
        CONTENT.replace("property_name = R_H24","property_name = R_WRONG"),
        CONTENT.replace("variable = log_nm","variable = log_nop"),
        CONTENT.replace("variable = log_ni","variable = log_nop"),
        CONTENT.replace("expression = '6.02214076e10*cm*ci'",
                        "expression = '6.02214076e16*cm*ci'"),
        CONTENT.replace("expression = '0.048*R'","expression = '0.032*R'"),
        CONTENT.replace("expression = '-om+ip'","expression = 'om+ip'"),
        CONTENT.replace("expression = '0.016*om+0.032*ip+o+o2'",
                        "expression = '0.016*om+0.016*ip+o+o2'"),
    ):
        try:validate(corrupt)
        except ValueError:pass
        else:raise AssertionError("H24 negative mutation not rejected")
    print("H24_12CH_SELFTEST_PASS")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    for arg in ("self-test","prepare-variant","verify-twelve",
                "patch-replay-argv","verify-and-archive"):
        group.add_argument("--"+arg,action="store_true")
    parser.add_argument("--power-w",type=int,choices=[400,1000])
    args=parser.parse_args()
    if args.self_test:self_test()
    elif args.power_w is None:parser.error("--power-w is required")
    elif args.prepare_variant:prepare(args.power_w)
    elif args.verify_twelve:verify(args.power_w)
    elif args.patch_replay_argv:patch(args.power_w)
    else:archive(args.power_w)
