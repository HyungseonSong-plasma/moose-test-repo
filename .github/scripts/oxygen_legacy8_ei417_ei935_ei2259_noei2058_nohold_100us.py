#!/usr/bin/env python3
"""Fresh 11-channel oxygen ICP: Legacy8 + EI417 + EI935 + EI2259 (EI2058 excluded).

HOLD EXCLUDED: H05, EI2072, EI2074. Research-only, not science accepted.
EI-2259 e + O2+ -> O(3P) + O(3P); thermal DR benchmark (Peverall et al.,
J. Chem. Phys. 114, 6679 (2001)): k = 2.4e-13 (300/T_e[K])^0.70 [m3/s].
This is a research temperature-dependent formula, NOT a verified HPEM sigma
or EEDF lookup. At ICP multi-eV Te, extrapolation/branching remain SCIENCE_HOLD.
Electron removal kinetic energy uses provisional -(mean_en_solved)*R; no
fictitious fixed ionization threshold and NO claim of recombination heat closure.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,os
from pathlib import Path

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
NEW_ID="EI-2259"
EXCLUDED={"H05","EI-2058","EI-2072","EI-2074"}
FIT_A=2.4e-13
FIT_EXP=0.70
K_PER_EV=11604.51812155
FIT_SOURCE="Peverall et al J Chem Phys 114 6679 (2001); thermal fit; research extrapolation"
CONTENT="""# EI2259 e + O2+ -> 2 O(3P), dissociative recombination, research-only.
# k(T_e)=2.4e-13*(300[K]/(T_e[eV]*11604.51812155))^0.70 [m3/s].
# Peverall 2001 thermal fit. NOT original HPEM numeric EI2259 cross section.
# Electron and O2+ each -R, O atom +2R. Energy sink -mean_en_solved*R
# represents removed electron kinetic energy only; recombination heat unmodelled.
[FunctorMaterials]
  [ei2259_o2plus_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2p_EI2259
    functor_names = 'log_ni'
    functor_symbols = 'lnci'
    expression = 'exp(lnci)'
    block = plasma
  []
  [ei2259_te]
    type = ADParsedFunctorMaterial
    property_name = Te_EI2259_eV
    functor_names = 'mean_en_solved'
    functor_symbols = 'eps'
    expression = '(2.0/3.0)*eps'
    block = plasma
  []
  [ei2259_progress]
    type = ADParsedFunctorMaterial
    property_name = R_EI2259
    functor_names = 'n_e_physical c_O2p_EI2259 Te_EI2259_eV'
    functor_symbols = 'ne ci te'
    expression = '2.4e-13*(300.0/(te*11604.51812155))^0.70*ne*ci'
    block = plasma
  []
  [ei2259_electron_loss]
    type = ADParsedFunctorMaterial
    property_name = S_e_molar_EI2259
    functor_names = 'R_EI2259'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [ei2259_o2plus_loss]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_molar_EI2259
    functor_names = 'R_EI2259'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [ei2259_o2plus_mass]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_mass_EI2259
    functor_names = 'R_EI2259'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [ei2259_atomic_o_mass]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI2259
    functor_names = 'R_EI2259'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [ei2259_neutral_mass]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI2259
    functor_names = 'R_EI2259'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [ei2259_electron_energy]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI2259
    functor_names = 'mean_en_solved R_EI2259'
    functor_symbols = 'eps R'
    expression = '-eps*R'
    block = plasma
  []
  [ei2259_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_EI2259
    functor_names = 'S_O2p_mass_EI2259 S_O_mass_EI2259'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
  [ei2259_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_EI2259
    functor_names = 'S_e_molar_EI2259 S_O2p_molar_EI2259'
    functor_symbols = 'el ip'
    expression = '-el+ip'
    block = plasma
  []
  [ei2259_neutral_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_closure_EI2259
    functor_names = 'S_O_mass_EI2259 S_neutral_mass_EI2259'
    functor_symbols = 'atom fluid'
    expression = 'atom-fluid'
    block = plasma
  []
[]
[Kernels]
  [ei2259_electron]
    type = FunctorKernel
    variable = log_ne
    functor = S_e_molar_EI2259
    functor_on_rhs = true
    block = plasma
  []
  [ei2259_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI2259
    functor_on_rhs = true
    block = plasma
  []
[]
[FVKernels]
  [ei2259_molecular_ion]
    type = FVCoupledForce
    variable = log_ni
    v = S_O2p_molar_EI2259
    coef = 1.0
    block = plasma
  []
  [ei2259_atomic_oxygen]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI2259
    block = plasma
  []
  [ei2259_neutral_pressure]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI2259
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [ei2259_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI2259
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2259_energy_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_EI2259
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2259_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_mass_closure_EI2259
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2259_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_EI2259
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2259_neutral_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_closure_EI2259
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""
def parent():
    path=Path(os.environ.get("EI935_PARENT",
            "_legacy6_control/.github/scripts/oxygen_legacy8_ei417_ei935_no_hold_100us.py"))
    spec=importlib.util.spec_from_file_location("nohold_ei935_parent",path)
    if spec is None or spec.loader is None:raise FileNotFoundError(path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def overlay(power):return CHEM/f"ei2259_o2plus_dissociative_recomb_{power}w_100us_dt1000ns_overlay.i"
def base_channels(p):return list(p.CHANNELS)
def expected_channels(p):return base_channels(p)+[NEW_ID]
def fit(te_eV):return FIT_A*(300.0/(K_PER_EV*te_eV))**FIT_EXP

def check_source(s):
    for token in (
        "property_name = R_EI2259",
        "functor_names = 'n_e_physical c_O2p_EI2259 Te_EI2259_eV'",
        "expression = '2.4e-13*(300.0/(te*11604.51812155))^0.70*ne*ci'",
        "expression = '(2.0/3.0)*eps'",
        "expression = 'exp(lnci)'",
        "\n    variable = log_ne\n","\n    variable = log_ni\n",
        "\n    variable = log_energy\n","\n    variable = w_O\n","\n    variable = p\n",
        "expression = '-R'","expression = '-0.032*R'",
        "expression = '0.032*R'","expression = '-eps*R'",
        "expression = 'a+b'","expression = '-el+ip'",
        "expression = 'atom-fluid'",
        "source = S_O_mass_EI2259","v = S_O2p_molar_EI2259",
        "functor = S_e_molar_EI2259","functor = S_energy_EI2259",
    ):
        if token not in s:raise ValueError("EI2259 source incomplete: "+token)
    if s.count("property_name = R_EI2259")!=1:
        raise ValueError("EI2259 requires exactly one rate owner")
    if s.count("functor_on_rhs = true")!=2:
        raise ValueError("EI2259 requires electron + electron-energy kernels")
    if any(token in s for token in (
        "private_rates/EI-2259", "rate_table_file",
        "variable = log_nm", "variable = log_nop",
        "functor_symbols = 'e ", "H05_OVERLAY", "EI2072_OVERLAY", "EI2074_OVERLAY"
    )):
        raise ValueError("EI2259 invalid source/duplicate private lookup/held channel")

def verify(power):
    p=parent()
    b8=p.l8();l7=b8.l7();m=l7.legacy6()
    if any(os.environ.get(k)!=v for k,v in (
        ("OXYGEN_RESEARCH_EI2738_FORMULA","1"),
        ("OXYGEN_RESEARCH_FULL24","0"),
        ("OXYGEN_RESEARCH_LUMPED_O2A","0"))):
        raise ValueError("unexpected chemistry runtime flags")
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    b8.overlay_ok(b8.overlay(power).read_text())
    if p.f417(power).read_text()!=p.c417():raise ValueError("EI417 provenance mismatch")
    p.validate_935(p.f935(power).read_text())
    check_source(overlay(power).read_text())
    rate_shas={name:b8.table_ok(CHEM/"private_rates"/name)
        for name in (b8.RATE,p.R417,p.R935)}
    path=m.result(power)/"legacy6_latest_variant.json"
    manifest=json.loads(path.read_text())
    if (manifest.get("chemistry_channels")!=expected_channels(p) or
        EXCLUDED.intersection(manifest.get("chemistry_channels",[]))):
        raise ValueError("expected 11 channels without EI2058 or HOLD three")
    if any((
        manifest.get("variant")!="LEGACY8_EI417_EI935_EI2259_NO_EI2058_NO_HOLD",
        manifest.get("scientific_acceptance")!="HOLD",
        manifest.get("native_initialization")!="fresh_not_restarted",
        manifest.get("physics_source_sha")!="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
        manifest.get("ei2259_rate_mode")!="thermal_formula_Peverall_research",
        manifest.get("ei2259_rate_A_m3_s")!=FIT_A,
        manifest.get("ei2259_rate_exponent")!=FIT_EXP,
        manifest.get("ei2259_energy_mode")!="removed_mean_electron_kinetic_energy_provisional",
        manifest.get("ei407_lookup_sha256")!=rate_shas[b8.RATE],
        manifest.get("ei417_lookup_sha256")!=rate_shas[p.R417],
        manifest.get("ei935_lookup_sha256")!=rate_shas[p.R935],
        any(k.startswith("ei2058_") for k in manifest),
    )):
        raise ValueError("unexpected experiment provenance")
    print("EI2259_NO_EI2058_P0_PASS",power)
    return p,b8,l7,m,manifest

def prepare(power):
    p=parent()
    p.prepare(power) # fresh 10-channel EI935 base, no restart or EI2058
    b8=p.l8();l7=b8.l7();m=l7.legacy6()
    fn=overlay(power)
    if fn.exists():raise ValueError("refuse EI2259 overlay overwrite")
    check_source(CONTENT)
    fn.write_text(CONTENT)
    path=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(path.read_text())
    if j.get("chemistry_channels")!=base_channels(p):
        raise ValueError("EI2259 parent is not exactly 10 channels")
    j.update({
        "variant":"LEGACY8_EI417_EI935_EI2259_NO_EI2058_NO_HOLD",
        "chemistry_channels":expected_channels(p),
        "hold_excluded":sorted(EXCLUDED),
        "ei2259_reaction":"e + O2+ -> O(3P) + O(3P)",
        "ei2259_rate_mode":"thermal_formula_Peverall_research",
        "ei2259_rate_A_m3_s":FIT_A,
        "ei2259_rate_exponent":FIT_EXP,
        "ei2259_rate_reference_T_K":300.0,
        "ei2259_rate_source":FIT_SOURCE,
        "ei2259_reference_applicability":"thermal fit T>200 K; multi-eV EEDF applicability unvalidated",
        "ei2259_temperature_eV_nominal_check_range":[1.0,7.0],
        "ei2259_energy_mode":"removed_mean_electron_kinetic_energy_provisional",
        "ei2259_dissociation_exothermic_heat":"NOT_MODELLED",
        "ei2259_branching":"two O(3P) assumed; excited-atom branching unvalidated",
        "ei2259_numeric_hPEM_cross_section":"NOT_VERIFIED",
        "scientific_acceptance":"HOLD",
    })
    path.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("EI2259_NO_EI2058_PREPARED",power)

def patch(power):
    p,b8,l7,m,j=verify(power)
    path=m.CHEM/"issue397_l1_power_scan_replay.sh"
    old=path.read_text()
    chk=p.OLD_CHECK
    solve=p.OLD_SOLVE
    chk_new=p.NEW_CHECK+" '$EI2259_OVERLAY'"
    solve_new=p.NEW_SOLVE.replace(
        " Outputs/file_base="," '$EI2259_OVERLAY' Outputs/file_base=")
    if old.count(chk)!=1 or old.count(solve)!=1:
        raise ValueError("pinned replay script differs")
    if any(x in old for x in (
        "$EI407_OVERLAY","$EI417_OVERLAY","$EI935_OVERLAY","$EI2058_OVERLAY",
        "$EI2259_OVERLAY","$H05_OVERLAY","$EI2072_OVERLAY","$EI2074_OVERLAY"
    )):
        raise ValueError("replay script already patched")
    new=old.replace(chk,chk_new,1).replace(solve,solve_new,1)
    if new.count(chk_new)!=1 or new.count(solve_new)!=1:
        raise ValueError("failed exact EI2259 argv patch")
    if "$EI2058_OVERLAY" in new:
        raise ValueError("EI2058 must not enter replay argv")
    path.write_text(new)
    (m.result(power)/"ei2259_noei2058_argv_patch.json").write_text(json.dumps({
        "power_W":power,
        "old_sha256":hashlib.sha256(old.encode()).hexdigest(),
        "new_sha256":hashlib.sha256(new.encode()).hexdigest(),
        "overlays":["EI-2738","EI-407","EI-417","EI-935","EI-2259"],
        "hold_excluded":sorted(EXCLUDED),"scientific_acceptance":"HOLD"
    },indent=2)+"\n")
    print("EI2259_NO_EI2058_ARGV_PASS",power)

def archive(power):
    p,b8,l7,m,j=verify(power)
    paths=(l7.overlay_path(m,power),b8.overlay(power),
           p.f417(power),p.f935(power),overlay(power))
    m.PERSIST=tuple(m.PERSIST)+tuple(path.name for path in paths)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if any((
        not saved.get("verified_full_native_100us_checkpoint"),
        saved.get("native_endpoint_s")!=1e-4,
        saved.get("chemistry_channels")!=expected_channels(p),
        saved.get("scientific_acceptance")!="HOLD",
        bool(EXCLUDED.intersection(saved.get("chemistry_channels",[]))),
    )):
        raise ValueError("11ch native completion invalid")
    names=[x["path"] for x in saved["inventory"]["inputs"]]
    for target in paths:
        if not any(n.endswith("/"+target.name) for n in names):
            raise ValueError("missing archived input "+target.name)
    if any("private_rates" in n or
           any(t in n.lower() for t in ("h05_associative","ei2058_o2a","ei2072_o2a","ei2074_o2a"))
           for n in names):
        raise ValueError("private or excluded chemistry in checkpoint")
    saved.update({
        "restart_requires_exact_ei417_ei935_ei2259_noei2058_chemistry":True,
        "restart_requires_exact_legacy6_chemistry":False,
        "hold_excluded":sorted(EXCLUDED),
        "ei2259_rate_mode":j["ei2259_rate_mode"],
        "ei2259_rate_A_m3_s":FIT_A,
        "ei2259_rate_exponent":FIT_EXP,
        "ei2259_energy_mode":j["ei2259_energy_mode"],
        "ei2259_branching":j["ei2259_branching"],
        "ei2259_scientific_status":"HOLD",
    })
    for key,table in (("ei407",b8.RATE),("ei417",p.R417),
                      ("ei935",p.R935)):
        saved[key+"_recovery_private_rate_required"]=table
        saved[key+"_recovery_rate_sha256"]=j[key+"_lookup_sha256"]
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("EI2259_NO_EI2058_NATIVE_100US_PASS",power)

def self_test():
    p=parent()
    p.self_test()
    assert len(expected_channels(p))==11
    assert not EXCLUDED.intersection(expected_channels(p))
    assert "EI-2058" not in expected_channels(p)
    assert abs(-0.032+0.032)<1e-15
    assert abs(-(-1)+(-1))<1e-15
    assert abs(0.032-0.032)<1e-15
    assert 1e-15<fit(4.0)<1e-13
    assert fit(1.0)>fit(7.0)>0
    check_source(CONTENT)
    for corrupt in (
        CONTENT.replace("property_name = R_EI2259","property_name = R_BAD"),
        CONTENT.replace("variable = log_ni","variable = log_nm"),
        CONTENT.replace("variable = w_O","variable = w_O2s"),
        CONTENT.replace("expression = '-el+ip'","expression = 'el+ip'"),
        CONTENT.replace("expression = '-eps*R'","expression = '-17*R'"),
    ):
        try:check_source(corrupt)
        except ValueError:pass
        else:raise AssertionError("bad EI2259 overlay not rejected")
    print("EI2259_NO_EI2058_SELFTEST_PASS")

if __name__=="__main__":
    a=argparse.ArgumentParser()
    g=a.add_mutually_exclusive_group(required=True)
    for k in ("self-test","prepare-variant","verify-eleven","patch-replay-argv","verify-and-archive"):
        g.add_argument("--"+k,action="store_true")
    a.add_argument("--power-w",type=int,choices=[400,1000])
    ns=a.parse_args()
    if ns.self_test:self_test()
    elif ns.power_w is None:a.error("--power-w required")
    elif ns.prepare_variant:prepare(ns.power_w)
    elif ns.verify_eleven:verify(ns.power_w)
    elif ns.patch_replay_argv:patch(ns.power_w)
    else:archive(ns.power_w)
