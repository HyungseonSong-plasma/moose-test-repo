#!/usr/bin/env python3
"""13-channel oxygen ICP: Legacy8 + EI417 + EI935 + EI2058 + EI2259 + EI943.

Only newly added reaction: EI-943 e+O(1D) -> e+O(3P).
Always exclude held channels H05, EI-2072, EI-2074.
Native 400W and 1000W fresh 0-100us; research-only scientific HOLD.
Excitation reverse: EI935 -1.967 eV; EI943 superelastic +1.967 eV.
Use original private 100-point EI943_O_1D table, NOT a derived fit.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,shutil
from pathlib import Path

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
RATE="EI-943_O_1D.txt"
LOSS_EV=-1.967
EXCLUDED={"H05","EI-2072","EI-2074"}
NEW_ID="EI-943"
CONTENT="""# Oxygen EI943: e + O(1D) -> e + O(3P), superelastic.
# Source: original private EI-943_O_1D.txt, single native rate owner.
# O(1D) is existing w_Os; O(3P) is existing w_O.
# Energy gain +1.967 eV * R, no net electron particle source.
[FunctorMaterials]
  [ei943_excited_o_target]
    type = ADParsedFunctorMaterial
    property_name = c_Os_EI943
    functor_names = 'rho_neutral w_Os'
    functor_symbols = 'rho wos'
    expression = 'rho*wos/0.016'
    block = plasma
  []
  [ei943_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-943_O_1D.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_Os_EI943
    reaction_progress = R_EI943
    block = plasma
  []
  [ei943_excited_o_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Os_mass_EI943
    functor_names = 'R_EI943'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [ei943_ground_o_birth]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI943
    functor_names = 'R_EI943'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [ei943_electron_energy_gain]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI943
    functor_names = 'R_EI943'
    functor_symbols = 'R'
    expression = '1.967*R'
    block = plasma
  []
  [ei943_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_EI943
    functor_names = 'S_Os_mass_EI943 S_O_mass_EI943'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
[]
[FVKernels]
  [ei943_excited_o]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Os
    source = S_Os_mass_EI943
    block = plasma
  []
  [ei943_ground_o]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI943
    block = plasma
  []
[]
[Kernels]
  [ei943_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI943
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [ei943_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI943
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei943_energy_gain_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_EI943
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei943_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_mass_closure_EI943
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def load_parent():
    path=Path(os.environ.get("EI2259_PARENT",
        "_legacy6_control/.github/scripts/oxygen_legacy8_ei417_ei935_ei2058_ei2259_nohold_100us.py"))
    spec=importlib.util.spec_from_file_location("nohold_ei2259_parent",path)
    if spec is None or spec.loader is None:raise FileNotFoundError(path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rate():return CHEM/"private_rates"/RATE
def overlay(power):return CHEM/f"ei943_atomic_superelastic_{power}w_100us_dt1000ns_overlay.i"
def expected(p):return p.expected_channels(p.parent())+[NEW_ID]

def validate(src):
    for token in (
        "reaction_progress = R_EI943",
        "rate_table_file = 'private_rates/EI-943_O_1D.txt'",
        "target_molar_concentration = c_Os_EI943",
        "functor_names = 'rho_neutral w_Os'",
        "\n    variable = w_Os\n",
        "\n    variable = w_O\n",
        "\n    variable = log_energy\n",
        "expression = '-0.016*R'","expression = '0.016*R'",
        "expression = '1.967*R'","expression = 'a+b'",
        "source = S_Os_mass_EI943","source = S_O_mass_EI943",
        "functor = S_energy_EI943",
    ):
        if token not in src:raise ValueError("EI943 missing expected term: "+token)
    if src.count("reaction_progress = R_EI943")!=1:
        raise ValueError("EI943 rate progress requires exactly one owner")
    if src.count("functor_on_rhs = true")!=1:
        raise ValueError("EI943 must add only one electron-energy kernel")
    if any(x in src for x in (
        "\n    variable = log_ne\n","\n    variable = log_ni\n",
        "\n    variable = log_nop\n","\n    variable = log_nm\n",
        "\n    variable = p\n","functor_symbols = 'e ",
        "R_H05","R_EI2072","R_EI2074"
    )):
        raise ValueError("EI943 cannot create charged sources or held reactions")

def verify(power):
    p=load_parent()   # 12-channel script (includes research-only EI2259)
    p11=p.parent()    # 11-channel script
    b10=p11.load_parent()
    b8=b10.l8()
    l7=b8.l7()
    m=l7.legacy6()
    for key,val in (
        ("OXYGEN_RESEARCH_EI2738_FORMULA","1"),
        ("OXYGEN_RESEARCH_FULL24","0"),
        ("OXYGEN_RESEARCH_LUMPED_O2A","0"),
    ):
        if os.environ.get(key)!=val:raise ValueError("unexpected research flag "+key)
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    b8.overlay_ok(b8.overlay(power).read_text())
    if b10.f417(power).read_text()!=b10.c417():
        raise ValueError("standalone EI417 overlay modified")
    b10.validate_935(b10.f935(power).read_text())
    p11.validate(p11.overlay(power).read_text())
    p.check_source(p.overlay(power).read_text())
    validate(overlay(power).read_text())
    tables=(b8.RATE,b10.R417,b10.R935,p11.EI2058_RATE,RATE)
    digests={name:b8.table_ok(CHEM/"private_rates"/name) for name in tables}
    path=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(path.read_text())
    if j.get("chemistry_channels")!=expected(p) or EXCLUDED.intersection(j.get("chemistry_channels",[])):
        raise ValueError("wrong 13 reaction inventory or held channel active")
    if any((
        j.get("variant")!="LEGACY8_EI417_EI935_EI2058_EI2259_EI943_NO_HOLD",
        j.get("native_initialization")!="fresh_not_restarted",
        j.get("physics_source_sha")!="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
        j.get("scientific_acceptance")!="HOLD",
        j.get("ei943_energy_loss_eV")!=LOSS_EV,
        j.get("ei943_lookup_sha256")!=digests[RATE],
        j.get("ei407_lookup_sha256")!=digests[b8.RATE],
        j.get("ei417_lookup_sha256")!=digests[b10.R417],
        j.get("ei935_lookup_sha256")!=digests[b10.R935],
        j.get("ei2058_lookup_sha256")!=digests[p11.EI2058_RATE],
        j.get("ei2259_rate_mode")!="thermal_formula_Peverall_research",
        j.get("ei2259_energy_mode")!="removed_mean_electron_kinetic_energy_provisional",
    )):
        raise ValueError("13-channel provenance mismatch")
    print("EI943_NO_HOLD_P0_PASS",power,digests[RATE])
    return p,p11,b10,b8,l7,m,j

def prepare(power):
    p=load_parent()
    p.prepare(power)  # fresh 12ch preparation, no cross-chemistry checkpoint
    b8=p.parent().load_parent().l8()
    src=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE
    valid=b8.table_ok(src)
    dst=rate();dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists() and digest(dst)!=valid:
        raise ValueError("existing private EI943 rate differs from original package")
    shutil.copyfile(src,dst)
    f=overlay(power)
    if f.exists():raise ValueError("refuse EI943 overlay overwrite")
    validate(CONTENT)
    f.write_text(CONTENT)
    m=b8.l7().legacy6()
    manifest=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(manifest.read_text())
    if j.get("chemistry_channels")!=p.expected_channels(p.parent()):
        raise ValueError("expected exact 12ch source model before adding EI943")
    j.update({
        "variant":"LEGACY8_EI417_EI935_EI2058_EI2259_EI943_NO_HOLD",
        "chemistry_channels":expected(p),
        "hold_excluded":sorted(EXCLUDED),
        "ei943_reaction":"e + O(1D) -> e + O(3P)",
        "ei943_rate_source":"original private 100-point Oxygen25 HPEM EI943 lookup",
        "ei943_lookup_filename":RATE,
        "ei943_lookup_sha256":valid,
        "ei943_energy_loss_eV":LOSS_EV,
        "ei943_rate_mode":"original_private_EEDF_mean_energy_lookup",
        "ei943_reverse_of":"EI-935",
        "ei943_branching_and_detailed_balance":"science_HOLD",
        "scientific_acceptance":"HOLD",
    })
    manifest.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("EI943_NO_HOLD_PREPARED",power)

def patch(power):
    p,p11,b10,b8,l7,m,j=verify(power)
    file=m.CHEM/"issue397_l1_power_scan_replay.sh"
    before=file.read_text()
    old_check=b10.OLD_CHECK
    old_solve=b10.OLD_SOLVE
    new_check=b10.NEW_CHECK+" '$EI2058_OVERLAY' '$EI2259_OVERLAY' '$EI943_OVERLAY'"
    new_solve=b10.NEW_SOLVE.replace(
        " Outputs/file_base=",
        " '$EI2058_OVERLAY' '$EI2259_OVERLAY' '$EI943_OVERLAY' Outputs/file_base=")
    if before.count(old_check)!=1 or before.count(old_solve)!=1:
        raise ValueError("pinned replay command differs")
    if any(tok in before for tok in (
        "$EI407_OVERLAY","$EI417_OVERLAY","$EI935_OVERLAY",
        "$EI2058_OVERLAY","$EI2259_OVERLAY","$EI943_OVERLAY",
        "$H05_OVERLAY","$EI2072_OVERLAY","$EI2074_OVERLAY"
    )):
        raise ValueError("double-patched or held chemistry in replay script")
    after=before.replace(old_check,new_check,1).replace(old_solve,new_solve,1)
    if after.count(new_check)!=1 or after.count(new_solve)!=1:
        raise ValueError("EI943 replay argv change invalid")
    file.write_text(after)
    (m.result(power)/"ei943_nohold_argv_patch.json").write_text(json.dumps({
        "power_W":power,
        "source_sha256":hashlib.sha256(before.encode()).hexdigest(),
        "patched_sha256":hashlib.sha256(after.encode()).hexdigest(),
        "overlays":["EI-2738","EI-407","EI-417","EI-935","EI-2058","EI-2259","EI-943"],
        "hold_excluded":sorted(EXCLUDED),
        "scientific_acceptance":"HOLD",
    },indent=2)+"\n")
    print("EI943_NO_HOLD_ARGV_PASS",power)

def archive(power):
    p,p11,b10,b8,l7,m,j=verify(power)
    files=(l7.overlay_path(m,power),b8.overlay(power),
           b10.f417(power),b10.f935(power),p11.overlay(power),
           p.overlay(power),overlay(power))
    m.PERSIST=tuple(m.PERSIST)+tuple(f.name for f in files)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if any((
        not saved.get("verified_full_native_100us_checkpoint"),
        saved.get("native_endpoint_s")!=1e-4,
        saved.get("chemistry_channels")!=expected(p),
        saved.get("scientific_acceptance")!="HOLD",
        bool(EXCLUDED.intersection(saved.get("chemistry_channels",[]))),
    )):
        raise ValueError("13ch archived native endpoint not verified")
    inventory=[entry["path"] for entry in saved["inventory"]["inputs"]]
    for f in files:
        if not any(path.endswith("/"+f.name) for path in inventory):
            raise ValueError("missing input overlay in archive "+f.name)
    if any("private_rates" in path or
           any(x in path.lower() for x in ("h05_associative","ei2072_o2a","ei2074_o2a"))
           for path in inventory):
        raise ValueError("archived secret or held reaction input")
    saved.update({
        "restart_requires_exact_ei417_ei935_ei2058_ei2259_ei943_chemistry":True,
        "restart_requires_exact_legacy6_chemistry":False,
        "hold_excluded":sorted(EXCLUDED),
        "ei943_recovery_private_rate_required":RATE,
        "ei943_recovery_rate_sha256":j["ei943_lookup_sha256"],
        "ei943_energy_loss_eV":LOSS_EV,
        "ei943_scientific_status":"HOLD",
    })
    for key,src in (("ei407",b8.RATE),("ei417",b10.R417),("ei935",b10.R935),
                    ("ei2058",p11.EI2058_RATE)):
        saved[key+"_recovery_private_rate_required"]=src
        saved[key+"_recovery_rate_sha256"]=j[key+"_lookup_sha256"]
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("EI943_NO_HOLD_NATIVE_100US_PASS",power)

def self_test():
    p=load_parent()
    p.self_test()
    assert len(expected(p))==13
    assert len(set(expected(p)))==13
    assert not EXCLUDED.intersection(expected(p))
    assert abs(-0.016+0.016)<1e-15
    assert LOSS_EV==-1.967
    validate(CONTENT)
    for corrupt in (
        CONTENT.replace("reaction_progress = R_EI943","reaction_progress = R_WRONG"),
        CONTENT.replace("variable = w_Os","variable = w_O2s"),
        CONTENT.replace("expression = '1.967*R'","expression = '-1.967*R'"),
        CONTENT.replace("expression = 'a+b'","expression = 'a-b'"),
    ):
        try:validate(corrupt)
        except ValueError:pass
        else:raise AssertionError("invalid EI943 mutation not rejected")
    print("EI943_NO_HOLD_SELFTEST_PASS")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    for name in ("self-test","prepare-variant","verify-thirteen","patch-replay-argv",
                 "verify-and-archive"):
        group.add_argument("--"+name,action="store_true")
    parser.add_argument("--power-w",type=int,choices=(400,1000))
    args=parser.parse_args()
    if args.self_test:self_test()
    elif args.power_w is None:parser.error("--power-w is required")
    elif args.prepare_variant:prepare(args.power_w)
    elif args.verify_thirteen:verify(args.power_w)
    elif args.patch_replay_argv:patch(args.power_w)
    else:archive(args.power_w)
