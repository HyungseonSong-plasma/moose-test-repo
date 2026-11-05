#!/usr/bin/env python3
"""Controlled EI-2069 additive channel on H23+no-EI943+MCS-EI2738 13ch.

Full24 pinned inventory defines:
  EI-2069 e- + O2(a1Delta) -> e- + O(3P) + O(3P);
  electron-energy loss 5.02 eV (effective model).
Use the exact existing original EI-2069_O2_a1Delta.txt private table in
PhysicsElectronImpactRateMaterial. Source units and owner are unchanged:
original private table is raw m3/(mol*s), material scales ne/N_A internally.

No changes to previous 13ch simulation, EEDF, Physics source, other chemistry
or rate lookups. One new R_2069 and its three projected source kernels.
Private kinetic table remains in runner workspace and NEVER in published
artifacts. All numeric and scientific acceptance status remain HOLD.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
NAME="EI-2069"
RATE="EI-2069_O2_a1Delta.txt"
N_A=6.02214076e23
ENERGY_EV=5.02
VARIANT="H23_NO_EI943_EI2738_MCS_EI2069_14CH_HOLD"
FLAG="OXYGEN_RESEARCH_EI2069_PLUS"
MCS_FLAG="OXYGEN_RESEARCH_EI2738_MCS"
PARENT_IDS=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20",
            "EI-2738","EI-407","EI-417","EI-935","H24","H25","H23"]
ACTIVE=PARENT_IDS+[NAME]
EXCLUDED={"EI-943","EI-2259","EI-2058","H05","EI-2072","EI-2074"}

CONTENT="""# EI-2069 e + O2(a1Delta) -> e + 2 O(3P)
# Original pinned Full24 registry: loss 5.02 eV/event; no net electrons.
# Single lookup owner, R_2069 [mol/(m3 s)]; O2a sink -0.032 R, O +0.032 R.
# Neutral heavy mass and charge both conserved (no pressure source).
[FunctorMaterials]
  [ei2069_o2a_molar_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2a_EI2069
    functor_names = 'rho_neutral w_O2s'
    functor_symbols = 'rho wa'
    expression = 'rho*wa/0.032'
    block = plasma
  []
  [ei2069_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-2069_O2_a1Delta.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2a_EI2069
    reaction_progress = R_EI2069
    block = plasma
  []
  [ei2069_o2a_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2a_mass_EI2069
    functor_names = 'R_EI2069'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [ei2069_atomic_oxygen_birth]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI2069
    functor_names = 'R_EI2069'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [ei2069_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI2069
    functor_names = 'R_EI2069'
    functor_symbols = 'R'
    expression = '-5.02*R'
    block = plasma
  []
  [ei2069_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EI2069
    functor_names = 'S_O2a_mass_EI2069 S_O_mass_EI2069'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
[]
[FVKernels]
  [ei2069_o2a_loss]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2s
    source = S_O2a_mass_EI2069
    block = plasma
  []
  [ei2069_o_birth]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI2069
    block = plasma
  []
[]
[Kernels]
  [ei2069_electron_energy_sink]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI2069
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [ei2069_progress_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI2069
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2069_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_EI2069
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""


def load(name,default):
    path=Path(os.environ.get(name,default))
    spec=importlib.util.spec_from_file_location("ei2069_"+name,path)
    if spec is None or spec.loader is None:raise FileNotFoundError(path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parent():
    return load("ABLATE","_legacy6_control/.github/scripts/oxygen_h23_no_ei943_13ch_100us.py")


def mcs():
    return load("MCS2738","_legacy6_control/.github/scripts/ei2738_mcs_h23_no_ei943_13ch.py")


def output(power):
    assert power in (400,1000)
    return CHEM/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"


def overlay(power):
    assert power in (400,1000)
    return CHEM/f"ei2069_o2a_dissociation_{power}w_100us_dt1000ns_overlay.i"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rate_path():
    return CHEM/"private_rates"/RATE


def src_rate():
    return Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE


def read_table(path):
    rows=[]
    for line in Path(path).read_text().splitlines():
        line=line.split("#",1)[0].strip()
        if not line: continue
        fields=line.split()
        assert len(fields)==2
        x,k=map(float,fields)
        assert math.isfinite(x) and math.isfinite(k) and x>0 and k>=0
        if rows: assert x>rows[-1][0]
        rows.append((x,k))
    assert len(rows)==100, f"Expected 100 original EI2069 lookup nodes; got {len(rows)}"
    return rows


def validate_text(src):
    required=(
        "type = PhysicsElectronImpactRateMaterial",
        "rate_table_file = 'private_rates/EI-2069_O2_a1Delta.txt'",
        "electron_number_density = n_e_physical",
        "mean_energy = mean_en_solved",
        "target_molar_concentration = c_O2a_EI2069",
        "reaction_progress = R_EI2069",
        "functor_names = 'rho_neutral w_O2s'",
        "expression = 'rho*wa/0.032'",
        "expression = '-0.032*R'",
        "expression = '0.032*R'",
        "expression = '-5.02*R'",
        "expression = 'a+b'",
        "variable = w_O2s",
        "variable = w_O",
        "variable = log_energy",
        "execute_on = 'INITIAL TIMESTEP_END'",
    )
    for x in required:
        assert x in src, f"missing EI2069 source projection {x}"
    assert src.count("reaction_progress = R_EI2069")==1
    assert src.count("type = PhysicsFVSpeciesReactionSource")==2
    assert src.count("functor_on_rhs = true")==1
    assert src.count("source = S_O2a_mass_EI2069")==1
    assert src.count("source = S_O_mass_EI2069")==1
    assert "variable = log_ne" not in src
    assert not any(x in src for x in ("R_EI943","R_EI2259","R_EI2058","R_H05","R_EI2072","R_EI2074"))


def verify_chemical_closure():
    delta={"e":0,"O2a":-1,"O":2}
    charges={"e":-1,"O2a":0,"O":0}
    atoms={"e":0,"O2a":2,"O":1}
    molar_mass={"e":0,"O2a":.032,"O":.016}
    assert sum(delta[x]*charges[x] for x in delta)==0
    assert sum(delta[x]*atoms[x] for x in delta)==0
    assert abs(sum(delta[x]*molar_mass[x] for x in delta))<1e-14


def assert_argv(txt):
    assert txt.count("'$EI2069_OVERLAY'")==2
    for name in ("'$H23_OVERLAY'","'$EI407_OVERLAY'","'$EI417_OVERLAY'",
                 "'$EI935_OVERLAY'","'$H24_OVERLAY'","'$H25_OVERLAY'"):
        assert txt.count(name)==2,f"original parent overlay missing: {name}"
    assert "'$EI943_OVERLAY'" not in txt
    assert "$EI2259_OVERLAY" not in txt and "$EI2058_OVERLAY" not in txt
    assert txt.count("Outputs/file_base='$RESULT/run/plasma'")==1
    assert txt.count(chr(36)+"{EI2738_EXTRA_INPUT}")==2


def prepare(power):
    assert os.environ.get(MCS_FLAG)=="1", "prepare MCS EI2738 before adding EI2069"
    par=parent()
    mom=mcs()
    par.verify(power)
    mom.verify(power)
    res=output(power)
    jpath=res/"legacy6_latest_variant.json"
    j=json.loads(jpath.read_text())
    assert j["chemistry_channels"]==PARENT_IDS
    assert j["variant"]==par.VARIANT
    assert j["ei2738_rate_origin"]==mom.ORIGIN
    assert j["scientific_acceptance"]=="HOLD"
    assert j["physics_source_sha"]=="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
    assert j["transport_table_sha256"]=="35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
    assert j["ei943_ablation"]=="FULLY_EXCLUDED_FROM_CHECK_AND_SOLVE_ARGV_NOT_ZERO_RATE"

    original=src_rate()
    assert original.is_file(),"missing verified original EI-2069 private table"
    table=read_table(original)
    assert read_table(original)==table
    # Compare all exact mean-energy nodes to the original EI943 100-node
    # reference grid saved before EI943 was ablated.
    grid=mom.parse_grid(res/mom.REFERENCE_GRID)
    assert len(grid)==len(table)==100
    for (_,x), (x2069,_) in zip(grid,table):
        assert math.isclose(x,x2069,rel_tol=1e-10,abs_tol=1e-10), "EI2069 grid mismatch"
    private=rate_path()
    assert not private.exists(), "refuse pre-existing EI2069 working lookup"
    shutil.copyfile(original,private)
    assert sha(original)==sha(private)
    text=CONTENT
    validate_text(text)
    target=overlay(power)
    assert not target.exists(),"refuse overwriting EI2069 overlay"
    target.write_text(text)
    replay=par.replay()
    before=replay.read_text()
    assert before.count(" '$H23_OVERLAY'")==2
    assert "'$EI2069_OVERLAY'" not in before
    after=before.replace(" '$H23_OVERLAY'"," '$H23_OVERLAY' '$EI2069_OVERLAY'")
    assert_argv(after)
    replay.write_text(after)
    audit={
        "power_W":power,
        "source":"Original pinned Full24 EI-2069 O2(a1Delta) private rate",
        "private_rate_file":RATE,
        "private_rate_sha256":sha(private),
        "private_rate_rows":100,
        "private_rate_units":"m3/(mol s), consumed by native PhysicsElectronImpactRateMaterial",
        "parent_mcs2738_lookup_sha256":j["ei2738_mcs_lookup_sha256"],
        "parent_mcs2738_origin":j["ei2738_rate_origin"],
        "parent_13ch_variant":par.VARIANT,
        "parent_13ch_manifest_sha256":sha(jpath),
        "parent_13ch_replay_sha256":sha_bytes(before.encode()),
        "native_14ch_replay_sha256":sha_bytes(after.encode()),
        "overlay_sha256":sha(target),
        "new_reaction":"e + O2(a1Delta) -> e + O(3P) + O(3P)",
        "electron_energy_loss_eV":ENERGY_EV,
        "mass_charge_atom_closure":"PASS",
        "neutral_mass_change_per_mol_kg":0,
        "excluded":sorted(EXCLUDED),
        "scientific_acceptance":"HOLD",
    }
    (res/"ei2069_addition_audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    j.update({
        "variant":VARIANT,
        "chemistry_channels":ACTIVE,
        "ei2069_lookup_filename":RATE,
        "ei2069_lookup_sha256":sha(private),
        "ei2069_electron_energy_loss_eV":ENERGY_EV,
        "ei2069_parent":par.VARIANT,
        "ei2069_source":"original private energy-rate table, stoichiometry Full24 pinned",
        "scientific_acceptance":"HOLD",
    })
    jpath.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    os.environ[FLAG]="1"
    verify(power)
    print("H23_NO943_MCS2738_PLUS_EI2069_14CH_PREPARE_PASS",power,flush=True)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def verify(power):
    assert os.environ.get(FLAG)=="1"
    j=json.loads((output(power)/"legacy6_latest_variant.json").read_text())
    audit=json.loads((output(power)/"ei2069_addition_audit.json").read_text())
    assert j["variant"]==VARIANT and j["chemistry_channels"]==ACTIVE
    assert not EXCLUDED.intersection(ACTIVE)
    assert j["scientific_acceptance"]=="HOLD"
    assert j["native_initialization"]=="fresh_not_restarted"
    assert j["power_W"]==power
    assert j["physics_source_sha"]=="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
    assert j["transport_table_sha256"]=="35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
    assert j["ei943_ablation"]=="FULLY_EXCLUDED_FROM_CHECK_AND_SOLVE_ARGV_NOT_ZERO_RATE"
    assert j["ei2738_rate_origin"]==mcs().ORIGIN
    assert j["ei2738_mcs_lookup_sha256"]==audit["parent_mcs2738_lookup_sha256"]
    assert j["ei2069_lookup_sha256"]==audit["private_rate_sha256"]==sha(rate_path())==sha(src_rate())
    assert audit["private_rate_rows"]==100 and len(read_table(rate_path()))==100
    assert audit["electron_energy_loss_eV"]==5.02
    assert audit["mass_charge_atom_closure"]=="PASS"
    assert audit["excluded"]==sorted(EXCLUDED)
    assert audit["scientific_acceptance"]=="HOLD"
    assert mcs().digest(CHEM/"private_rates"/mcs().EI2738_LOOKUP)==j["ei2738_mcs_lookup_sha256"]
    assert not (CHEM/"private_rates"/"EI-943_O_1D.txt").exists()
    assert not (CHEM/f"ei943_atomic_superelastic_{power}w_100us_dt1000ns_overlay.i").exists()
    assert "EI-943" not in j["chemistry_channels"]
    assert_argv(parent().replay().read_text())
    assert sha(parent().replay())==audit["native_14ch_replay_sha256"]
    source=overlay(power).read_text()
    validate_text(source)
    assert sha(overlay(power))==audit["overlay_sha256"]
    # Parent reactions retain exactly the original names and rate owners.
    assert j["h23_k_m3_s"]==1e-13
    assert j["h24_k_m3_s"]==1e-13
    assert j["h25_k_m3_s_at_300K"]==2e-17
    assert j["ei935_energy_loss_eV"]==1.967
    print("H23_NO943_MCS2738_PLUS_EI2069_14CH_VERIFIED",power,flush=True)


def archive(power):
    verify(power)
    par=parent()
    h23,h25,h24,ei943,ei935,b8,l7,base=par.modules()
    files=(l7.overlay_path(base,power),b8.overlay(power),ei935.f417(power),
           ei935.f935(power),h24.overlay(power),h25.overlay(power),h23.overlay(power),
           overlay(power))
    assert len(files)==len(set(p.name for p in files))==8
    for p in files:
        assert p.exists() and "ei943" not in p.name.lower(),p
    base.PERSIST=tuple(base.PERSIST)+tuple(p.name for p in files)
    base.verify_and_archive(power)
    res=output(power)
    manifest=res/"legacy6_restart_100000ns_manifest.json"
    j=json.loads(manifest.read_text())
    assert j["verified_full_native_100us_checkpoint"] and math.isclose(j["native_endpoint_s"],1e-4,abs_tol=1e-12)
    assert j["chemistry_channels"]==ACTIVE and j["variant"]==VARIANT
    assert j["scientific_acceptance"]=="HOLD"
    inventory=[v["path"] for v in j["inventory"]["inputs"]]
    for f in files:
        assert any(s.endswith("/"+f.name) for s in inventory),f
    assert not any("private_rates" in path for path in inventory)
    assert not any("ei943" in path.lower() for path in inventory)
    # Preserve the novel *nonprivate*, derived MCS lookup for reproducible restart.
    src=CHEM/"private_rates"/mcs().EI2738_LOOKUP
    derived=res/mcs().SAFE_LOOKUP
    assert not derived.exists()
    shutil.copyfile(src,derived)
    assert sha(derived)==j["ei2738_mcs_lookup_sha256"]
    j.update({
        "ei2069_addition_audit":json.loads((res/"ei2069_addition_audit.json").read_text()),
        "ei2069_recovery_private_rate_required":RATE,
        "ei2069_recovery_private_rate_sha256":sha(rate_path()),
        "ei2069_energy_loss_eV":ENERGY_EV,
        "h23_recovery_k_m3_s":h23.K_M3_S,
        "h24_recovery_k_m3_s":h24.K_M3_S,
        "h25_recovery_k_m3_s_at_300K":h25.K_M3_S_AT_300K,
        "h23_scientific_status":"HOLD",
        "h24_scientific_status":"HOLD",
        "h25_scientific_status":"HOLD",
        "ei943_scientific_status":"IMPACT_ABLATION_UNDER_TEST",
        "no_ei943_ablation_audit":json.loads((res/"no_ei943_ablation_audit.json").read_text()),
        "ei2738_mcs_derived_rate_sha256":sha(derived),
        "ei2738_mcs_derived_rate_recovery_artifact":mcs().SAFE_LOOKUP,
        "ei2738_mcs_swap_audit":json.loads((res/mcs().AUDIT_NAME).read_text()),
        "ei943_recovery_rate_required":False,
        "ei943_recovery_overlay_required":False,
        "restart_requires_exact_legacy6_chemistry":False,
        "restart_requires_exact_14ch_h23_in_ei943_out_ei2069_in_mcs2738":True,
        "scientific_acceptance":"HOLD",
    })
    # Preserve original non-EI943 private rate recovery proofs without archiving rates.
    latest=json.loads((res/"legacy6_latest_variant.json").read_text())
    for rate_key,rate_name in par.RATE_MAP.items():
        assert latest[rate_key+"_lookup_sha256"]==sha(CHEM/"private_rates"/rate_name)
        j[rate_key+"_recovery_private_rate_required"]=rate_name
        j[rate_key+"_recovery_rate_sha256"]=latest[rate_key+"_lookup_sha256"]
    assert j["ei2069_lookup_sha256"]==j["ei2069_recovery_private_rate_sha256"]
    assert j["h23_recovery_k_m3_s"]==latest["h23_k_m3_s"]
    assert j["h24_recovery_k_m3_s"]==latest["h24_k_m3_s"]
    assert j["h25_recovery_k_m3_s_at_300K"]==latest["h25_k_m3_s_at_300K"]
    manifest.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    print("H23_NO943_MCS2738_PLUS_EI2069_14CH_NATIVE_100US_PASS",power,flush=True)


def self_test():
    validate_text(CONTENT)
    verify_chemical_closure()
    assert len(ACTIVE)==14==len(set(ACTIVE))
    assert "EI-2069" in ACTIVE and "EI-943" not in ACTIVE
    assert "H23" in ACTIVE and "EI-2738" in ACTIVE
    assert len(EXCLUDED)==6
    assert ENERGY_EV==5.02
    print("H23_NO943_EI2069_14CH_STOICHIOMETRY_SELFTEST_PASS",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["self-test","prepare","verify","archive"])
    p.add_argument("--power-w",type=int)
    args=p.parse_args()
    if args.action=="self-test":self_test()
    else:
        assert args.power_w in (400,1000)
        {"prepare":prepare,"verify":verify,"archive":archive}[args.action](args.power_w)
