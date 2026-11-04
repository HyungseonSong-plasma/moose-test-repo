#!/usr/bin/env python3
"""13-channel oxygen ICP: add H25 onto the H24 + EI943 experiment.

Cumulative comparison to Run 41803381239 (12 channels, H24 already present).
New channel: H25 O+ + O2(X) -> O(3P) + O2+.
QDB-API 1115 screenshot: A=2e-11 cm3/s, n=-0.4, E=0;
provisional k=2e-17*(Tg/300 K)**(-0.4) m3/s, Tg=300 K fixed here.
No EI-2058, EI-2259, H05, EI-2072, EI-2074.
The Tref convention, branching and energy exchange remain SCIENCE_HOLD.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os
from pathlib import Path

CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
NEW_ID = "H25"
K_CM3_S_AT_300K = 2.0e-11
K_M3_S_AT_300K = 2.0e-17
N_TG = -0.4
T_REFERENCE_K = 300.0
T_GAS_K = 300.0
N_A = 6.02214076e23
EXCLUDED = {"H05","EI-2058","EI-2259","EI-2072","EI-2074"}
VARIANT = "LEGACY8_EI417_EI935_EI943_H24_H25_NO_EI2058_NO_EI2259_NO_HOLD"

CONTENT = """# H25 O+(3P) + O2(X) -> O(3P) + O2+: charge transfer.
# Research-only QDB-API 1115 screenshot: A=2e-11 cm3/s, n=-0.4, E=0.
# Provisional model k(Tg)=2e-17*(Tg/300 K)^(-0.4) [m3/s].
# The baseline gas temperature is frozen at Tg=300K (not electron temperature).
# c_Op=exp(log_nop), c_O2=rho_neutral*w_O2_constraint/0.032 [mol/m3].
# R_H25=k*N_A*c_Op*c_O2 [mol/m3/s], N_A is Avogadro's constant.
# O+: -R; O2+: +R; neutral O: +R; neutral O2: -R (constrained).
# Neutral mass: -0.016 R; net electron source and energy source both 0.
# Ion-neutral charge-transfer energy exchange remains SCIENCE_HOLD.
[FunctorMaterials]
  [h25_op_target]
    type = ADParsedFunctorMaterial
    property_name = c_Op_H25
    functor_names = 'log_nop'
    functor_symbols = 'lncp'
    expression = 'exp(lncp)'
    block = plasma
  []
  [h25_o2_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2_H25
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w2'
    expression = 'rho*w2/0.032'
    block = plasma
  []
  [h25_fixed_tgas]
    type = ADParsedFunctorMaterial
    property_name = Tg_H25_K
    expression = '300.0'
    block = plasma
  []
  [h25_progress]
    type = ADParsedFunctorMaterial
    property_name = R_H25
    functor_names = 'c_Op_H25 c_O2_H25 Tg_H25_K'
    functor_symbols = 'cp c2 tg'
    expression = '1.204428152e7*(300.0/tg)^0.4*cp*c2'
    block = plasma
  []
  [h25_op_loss]
    type = ADParsedFunctorMaterial
    property_name = S_Op_molar_H25
    functor_names = 'R_H25'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [h25_o2p_birth]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_molar_H25
    functor_names = 'R_H25'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [h25_o_mass]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_H25
    functor_names = 'R_H25'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [h25_o2_mass_implicit]
    type = ADParsedFunctorMaterial
    property_name = S_O2_mass_H25_implicit
    functor_names = 'R_H25'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [h25_neutral_mass]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_H25
    functor_names = 'R_H25'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [h25_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_H25
    functor_names = 'S_Op_molar_H25 S_O2p_molar_H25'
    functor_symbols = 'op ip'
    expression = 'op+ip'
    block = plasma
  []
  [h25_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_H25
    functor_names = 'S_Op_molar_H25 S_O2p_molar_H25 S_O_mass_H25 S_O2_mass_H25_implicit'
    functor_symbols = 'op ip o o2'
    expression = '0.016*op+0.032*ip+o+o2'
    block = plasma
  []
  [h25_neutral_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_closure_H25
    functor_names = 'S_neutral_mass_H25 S_O_mass_H25 S_O2_mass_H25_implicit'
    functor_symbols = 'total o o2'
    expression = 'total-o-o2'
    block = plasma
  []
  [h25_oxygen_atoms_closure]
    type = ADParsedFunctorMaterial
    property_name = S_oxygen_nuclei_closure_H25
    functor_names = 'S_Op_molar_H25 S_O2p_molar_H25 R_H25'
    functor_symbols = 'op ip prog'
    expression = 'op+2*ip-prog'
    block = plasma
  []
[]
[FVKernels]
  [h25_atomic_positive_ion]
    type = FVCoupledForce
    variable = log_nop
    v = S_Op_molar_H25
    coef = 1.0
    block = plasma
  []
  [h25_molecular_positive_ion]
    type = FVCoupledForce
    variable = log_ni
    v = S_O2p_molar_H25
    coef = 1.0
    block = plasma
  []
  [h25_atomic_oxygen]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_H25
    block = plasma
  []
  [h25_neutral_pressure]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_H25
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [h25_progress_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_H25
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h25_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_H25
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h25_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_H25
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h25_neutral_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_closure_H25
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [h25_oxygen_atoms_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_oxygen_nuclei_closure_H25
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def load_parent():
    path = Path(os.environ.get(
        "H24", "_legacy6_control/.github/scripts/oxygen_legacy8_ei417_ei935_ei943_h24_noei2259_noei2058_100us.py"
    ))
    spec = importlib.util.spec_from_file_location("h25_h24_parent", path)
    if not spec or not spec.loader:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def overlay(power):
    return CHEM/f"h25_op_o2_charge_transfer_{power}w_100us_dt1000ns_overlay.i"

def expected(parent):
    return parent.expected(parent.load_parent())+[NEW_ID]

def validate(src):
    for token in (
        "property_name = R_H25",
        "property_name = Tg_H25_K",
        "expression = '300.0'",
        "functor_names = 'log_nop'",
        "functor_names = 'rho_neutral w_O2_constraint'",
        "functor_names = 'c_Op_H25 c_O2_H25 Tg_H25_K'",
        "expression = '1.204428152e7*(300.0/tg)^0.4*cp*c2'",
        "variable = log_nop",
        "variable = log_ni",
        "variable = w_O",
        "variable = p",
        "v = S_Op_molar_H25",
        "v = S_O2p_molar_H25",
        "source = S_O_mass_H25",
        "v = S_neutral_mass_H25",
        "expression = '-R'",
        "expression = 'R'",
        "expression = '0.016*R'",
        "expression = '-0.032*R'",
        "expression = '-0.016*R'",
        "expression = 'op+ip'",
        "expression = '0.016*op+0.032*ip+o+o2'",
        "expression = 'total-o-o2'",
        "expression = 'op+2*ip-prog'",
    ):
        if token not in src:
            raise ValueError("H25 source missing "+token)
    if src.count("property_name = R_H25")!=1:
        raise ValueError("H25 must have exactly one rate owner")
    if src.count("variable = log_nop")!=1 or src.count("variable = log_ni")!=1:
        raise ValueError("H25 must have exactly two ion source kernels")
    if src.count("type = FVCoupledForce")!=3:
        raise ValueError("H25 must have two ion sources and one neutral-mass source")
    if any(t in src for t in (
        "variable = log_ne","variable = log_energy","variable = log_nm",
        "R_H05","R_EI2058","R_EI2259","R_EI2072","R_EI2074",
    )):
        raise ValueError("H25 introduces unapproved electron or held reaction source")

def verify(power):
    h24=load_parent();ei943=h24.load_parent();ei935=ei943.load_parent()
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
    validate(overlay(power).read_text())
    rate_names=(b8.RATE,ei935.R417,ei935.R935,ei943.RATE)
    checks={name:b8.table_ok(CHEM/"private_rates"/name) for name in rate_names}
    j=json.loads((m.result(power)/"legacy6_latest_variant.json").read_text())
    chem=expected(h24)
    if j.get("chemistry_channels")!=chem or len(chem)!=13 or EXCLUDED.intersection(chem):
        raise ValueError("unexpected 13-channel H24+H25 active chemistry")
    if any((
        j.get("variant")!=VARIANT,
        j.get("native_initialization")!="fresh_not_restarted",
        j.get("scientific_acceptance")!="HOLD",
        j.get("physics_source_sha")!="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
        j.get("ei407_lookup_sha256")!=checks[b8.RATE],
        j.get("ei417_lookup_sha256")!=checks[ei935.R417],
        j.get("ei935_lookup_sha256")!=checks[ei935.R935],
        j.get("ei943_lookup_sha256")!=checks[ei943.RATE],
        j.get("h24_k_m3_s")!=h24.K_M3_S,
        j.get("h25_k_m3_s_at_300K")!=K_M3_S_AT_300K,
        j.get("h25_tgas_K")!=T_GAS_K,
        j.get("h25_temperature_exponent")!=N_TG,
        any(key.startswith(("ei2058_","ei2259_")) for key in j),
    )):
        raise ValueError("H25 chemical configuration or source provenance mismatch")
    print("H25_13CH_P0_PASS",power)
    return h24,ei943,ei935,b8,l7,m,j

def prepare(power):
    h24=load_parent()
    h24.prepare(power)   # strict 12ch native case before H25 addition
    validate(CONTENT)
    dest=overlay(power)
    if dest.exists():
        raise ValueError("refuse H25 overlay overwrite")
    dest.write_text(CONTENT)
    ei943=h24.load_parent();ei935=ei943.load_parent()
    m=ei935.l8().l7().legacy6()
    manifest=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(manifest.read_text())
    if j.get("chemistry_channels")!=h24.expected(ei943):
        raise ValueError("H25 must start from exact H24 12ch parent")
    j.update({
        "variant":VARIANT,
        "chemistry_channels":expected(h24),
        "hold_excluded":sorted(EXCLUDED),
        "h25_reaction":"O+ + O2(X) -> O(3P) + O2+",
        "h25_qdb_api_id":1115,
        "h25_source":"QDB screenshot A=2e-11 cm3/s n=-0.4 E=0; independently unverified",
        "h25_k_cm3_s_at_300K":K_CM3_S_AT_300K,
        "h25_k_m3_s_at_300K":K_M3_S_AT_300K,
        "h25_temperature_exponent":N_TG,
        "h25_temperature_reference_K":T_REFERENCE_K,
        "h25_tgas_K":T_GAS_K,
        "h25_temperature_model":"provisional_(Tg/300K)^-0.4; fixed_tgas_300K",
        "h25_energy_partition":"not_explicitly_modelled_scientific_HOLD",
        "h25_o2_representation":"w_O2_constraint_constrained_remainder",
        "scientific_acceptance":"HOLD",
    })
    manifest.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("H25_13CH_PREPARED",power)

def patch(power):
    h24,ei943,ei935,b8,l7,m,j=verify(power)
    path=m.CHEM/"issue397_l1_power_scan_replay.sh"
    before=path.read_text()
    new_check=ei935.NEW_CHECK+" '$EI943_OVERLAY' '$H24_OVERLAY' '$H25_OVERLAY'"
    new_solve=ei935.NEW_SOLVE.replace(
        " Outputs/file_base=",
        " '$EI943_OVERLAY' '$H24_OVERLAY' '$H25_OVERLAY' Outputs/file_base="
    )
    if before.count(ei935.OLD_CHECK)!=1 or before.count(ei935.OLD_SOLVE)!=1:
        raise ValueError("pinned replay command changed unexpectedly")
    if any(name in before for name in (
        "$EI407_OVERLAY","$EI417_OVERLAY","$EI935_OVERLAY","$EI943_OVERLAY",
        "$H24_OVERLAY","$H25_OVERLAY","$EI2058_OVERLAY","$EI2259_OVERLAY",
        "$H05_OVERLAY","$EI2072_OVERLAY","$EI2074_OVERLAY",
    )):
        raise ValueError("replay already modified")
    after=before.replace(ei935.OLD_CHECK,new_check,1).replace(ei935.OLD_SOLVE,new_solve,1)
    if after.count(new_check)!=1 or after.count(new_solve)!=1:
        raise ValueError("H25 replay argv patch mismatch")
    if "$EI2058_OVERLAY" in after or "$EI2259_OVERLAY" in after:
        raise ValueError("excluded chemistry accidentally enabled")
    path.write_text(after)
    (m.result(power)/"h25_argv_patch.json").write_text(json.dumps({
        "power_W":power,
        "source_sha256":hashlib.sha256(before.encode()).hexdigest(),
        "patched_sha256":hashlib.sha256(after.encode()).hexdigest(),
        "overlays":["EI-2738","EI-407","EI-417","EI-935","EI-943","H24","H25"],
        "h24_k_m3_s":h24.K_M3_S,
        "h25_k_m3_s_at_300K":K_M3_S_AT_300K,
        "h25_tgas_K":T_GAS_K,
        "excluded":sorted(EXCLUDED),
        "scientific_acceptance":"HOLD",
    },indent=2,sort_keys=True)+"\n")
    print("H25_13CH_ARGV_PASS",power)

def archive(power):
    h24,ei943,ei935,b8,l7,m,j=verify(power)
    files=(l7.overlay_path(m,power),b8.overlay(power),ei935.f417(power),
           ei935.f935(power),ei943.overlay(power),h24.overlay(power),overlay(power))
    m.PERSIST=tuple(m.PERSIST)+tuple(f.name for f in files)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if any((
        not saved.get("verified_full_native_100us_checkpoint"),
        saved.get("native_endpoint_s")!=1e-4,
        saved.get("chemistry_channels")!=expected(h24),
        saved.get("variant")!=VARIANT,
        saved.get("scientific_acceptance")!="HOLD",
        bool(EXCLUDED.intersection(saved.get("chemistry_channels",[]))),
    )):
        raise ValueError("H25 native 100us checkpoint/13ch verification failed")
    inventory=[item["path"] for item in saved["inventory"]["inputs"]]
    for file in files:
        if not any(x.endswith("/"+file.name) for x in inventory):
            raise ValueError("missing required H24+H25 overlay "+file.name)
    if any("private_rates" in item or any(t in item.lower() for t in (
        "h05_associative","ei2058_o2a","ei2259_o2plus","ei2072_o2a","ei2074_o2a"))
        for item in inventory):
        raise ValueError("secret or excluded chemistry in archived model")
    saved.update({
        "restart_requires_exact_ei417_ei935_ei943_h24_h25_chemistry":True,
        "restart_requires_exact_legacy6_chemistry":False,
        "hold_excluded":sorted(EXCLUDED),
        "h24_recovery_k_m3_s":h24.K_M3_S,
        "h25_recovery_k_m3_s_at_300K":K_M3_S_AT_300K,
        "h25_recovery_temperature_model":"provisional_Tg_300K",
        "h25_scientific_status":"HOLD",
        "h24_scientific_status":"HOLD",
    })
    for key,name in (
        ("ei407",b8.RATE),("ei417",ei935.R417),
        ("ei935",ei935.R935),("ei943",ei943.RATE),
    ):
        saved[key+"_recovery_private_rate_required"]=name
        saved[key+"_recovery_rate_sha256"]=j[key+"_lookup_sha256"]
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("H25_13CH_NATIVE_100US_PASS",power)

def self_test():
    h24=load_parent()
    h24.self_test()
    chem=expected(h24)
    assert len(chem)==len(set(chem))==13
    assert not EXCLUDED.intersection(chem)
    assert abs(K_M3_S_AT_300K-K_CM3_S_AT_300K*1e-6)/K_M3_S_AT_300K<1e-14
    assert abs(K_M3_S_AT_300K*N_A-1.204428152e7)/1.204428152e7<1e-14
    assert N_TG==-0.4 and T_GAS_K==T_REFERENCE_K==300.0
    assert abs(-0.016+0.032+0.016-0.032)<1e-15
    assert abs(-0.016-(0.016-0.032))<1e-15
    assert -1+1==0
    assert -1+2+1-2==0
    validate(CONTENT)
    for corrupted in (
        CONTENT.replace("property_name = R_H25","property_name = R_BAD"),
        CONTENT.replace("variable = log_nop","variable = log_nm"),
        CONTENT.replace("variable = log_ni","variable = log_ne"),
        CONTENT.replace("expression = '1.204428152e7*(300.0/tg)^0.4*cp*c2'",
                        "expression = '1.204428152e13*(300.0/tg)^0.4*cp*c2'"),
        CONTENT.replace("expression = 'op+ip'","expression = 'op-ip'"),
        CONTENT.replace("expression = '-0.032*R'","expression = '0.032*R'"),
        CONTENT.replace("expression = '0.016*op+0.032*ip+o+o2'",
                        "expression = '0.032*op+0.032*ip+o+o2'"),
        CONTENT.replace("expression = 'op+2*ip-prog'","expression = 'op+ip-prog'"),
    ):
        try:validate(corrupted)
        except ValueError:pass
        else:raise AssertionError("H25 validator failed negative mutation")
    print("H25_13CH_SELFTEST_PASS")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    for name in ("self-test","prepare-variant","verify-thirteen",
                 "patch-replay-argv","verify-and-archive"):
        group.add_argument("--"+name,action="store_true")
    parser.add_argument("--power-w",type=int,choices=(400,1000))
    args=parser.parse_args()
    if args.self_test:self_test()
    elif args.power_w is None:parser.error("--power-w required")
    elif args.prepare_variant:prepare(args.power_w)
    elif args.verify_thirteen:verify(args.power_w)
    elif args.patch_replay_argv:patch(args.power_w)
    else:archive(args.power_w)
