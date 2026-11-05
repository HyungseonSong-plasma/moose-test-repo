#!/usr/bin/env python3
"""Exclusive EI-415-for-EI-16 rate substitution in pinned oxygen 14ch.

Parent 14ch: EI401-in/EI01-out, EI412-in/DISS-G-out,
EI941-in/EI20-out, EI2069-in, EI943-out, H23+ and MCS EI2738.
Replace exactly one O2(X) ionization owner, keeping existing net electron
(+1), O2+ (+1), neutral O2 (-1) and energy (-12.06 eV/event) projections.
Uses original HPEM 100-pt EI-415_O2_X.txt (secret; never uploaded).
Native 400/1000 W 0-100us research; scientific acceptance HOLD.
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
import tarfile

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
RATE="EI-415_O2_X.txt"
OLD="EI-16"
NEW="EI-415"
ENERGY_EV=12.06
FLAG="OXYGEN_RESEARCH_EI415_SWAP"
VARIANT="H23_NO943_MCS2738_EI2069_EI941_EI412_EI401_EI415_REPLACES_EI16_14CH_HOLD"
AUDIT="ei415_replaces_ei16_audit.json"
LOOKUP_UNITS="m3/(mol s)"

def import_module(path,label):
    spec=importlib.util.spec_from_file_location(label,path)
    assert spec and spec.loader,path
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def parent():
    return import_module(os.environ.get(
        "EI401","_legacy6_control/.github/scripts/ei401_replaces_ei01_h23_ei412_ei941_14ch.py"),
        "ei415_parent_ei401")

def ei2069():
    return import_module(os.environ.get(
        "EI2069","_legacy6_control/.github/scripts/ei2069_h23_no943_mcs2738_14ch.py"),
        "ei415_parent_ei2069")

def mcs():
    return import_module(os.environ.get(
        "MCS2738","_legacy6_control/.github/scripts/ei2738_mcs_h23_no_ei943_13ch.py"),
        "ei415_parent_mcs")

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def digest_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

def output(power):
    assert power in (400,1000)
    return CHEM/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"

def original_rate():return Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE
def working_rate():return CHEM/"private_rates"/RATE
def old_overlay(power):return CHEM/f"o2_ionization_{power}w_100us_dt1000ns_overlay.i"
def new_overlay(power):return CHEM/f"o2_ionization_ei415_{power}w_100us_dt1000ns_overlay.i"
def replay():return CHEM/"issue397_l1_power_scan_replay.sh"
def audit_path(power):return output(power)/AUDIT

def old_ion_line():
    dollar=chr(36)
    return ('export ION="$CHEM/o2_ionization_'+dollar+
            '{POWER_W}w_100us_dt'+dollar+'{DT_NS}ns_overlay.i"')
def new_ion_line():
    return old_ion_line().replace("o2_ionization_","o2_ionization_ei415_")

def chemistry():
    current=parent().chemistry()
    assert current.count(OLD)==1 and NEW not in current
    updated=[NEW if x==OLD else x for x in current]
    assert len(updated)==len(set(updated))==14
    assert "EI-401" in updated and "EI-01" not in updated
    assert "EI-412" in updated and "DISS-G" not in updated
    assert "EI-941" in updated and "EI-20" not in updated
    assert "EI-2069" in updated and "EI-943" not in updated
    assert OLD not in updated
    return updated

def transform(legacy):
    assert legacy.count("type = PhysicsElectronImpactIonizationMaterial")==1
    assert legacy.count("rate_table_file = o2_ionization.txt")==1
    assert legacy.count("o2_molar_concentration = c_O2_EI16")==1
    assert "expression = '-12.06*R'" in legacy
    assert "functor_names = 'R_ion_O2'" in legacy
    new=legacy.replace("EI16","EI415").replace("ei16","ei415")
    new=new.replace("type = PhysicsElectronImpactIonizationMaterial",
                    "type = PhysicsElectronImpactRateMaterial")
    new=new.replace("o2_molar_concentration = c_O2_EI415",
                    "target_molar_concentration = c_O2_EI415\n    reaction_progress = R_ion_O2")
    new=new.replace("rate_table_file = o2_ionization.txt",
                    "rate_table_file = 'private_rates/EI-415_O2_X.txt'")
    new=("# Original EI-415 e + O2(X) -> O2+ + 2e; EI-16 is excluded.\n"
         "# Original HPEM rate with 12.06 eV electron energy loss per event.\n"
         "# Native generic PhysicsElectronImpactRateMaterial owns R_ion_O2 exactly once.\n"+new)
    verify_overlay(new)
    return new

def verify_overlay(source):
    required=(
        "type = PhysicsElectronImpactRateMaterial",
        "rate_table_file = 'private_rates/EI-415_O2_X.txt'",
        "mean_energy = mean_en_solved",
        "electron_number_density = n_e_physical",
        "target_molar_concentration = c_O2_EI415",
        "reaction_progress = R_ion_O2",
        "property_name = S_electron_molar_EI415",
        "property_name = S_O2p_molar_EI415",
        "property_name = S_neutral_mass_EI415",
        "property_name = S_O2p_mass_EI415",
        "property_name = S_electron_energy_molar_EI415",
        "property_name = S_heavy_mass_closure_EI415",
        "property_name = S_charge_molar_closure_EI415",
        "expression = '-12.06*R'",
        "variable = log_ne","variable = log_ni",
        "variable = log_energy","variable = p",
        "functor = S_electron_molar_EI415",
        "functor = S_electron_energy_molar_EI415",
        "v = S_O2p_molar_EI415",
        "v = S_neutral_mass_EI415",
    )
    for x in required:assert x in source,x
    assert source.count("reaction_progress = R_ion_O2")==1
    assert source.count("type = PhysicsElectronImpactRateMaterial")==1
    assert source.count("expression = '-12.06*R'")==1
    assert source.count("variable = log_energy")==1
    assert source.count("variable = log_ne")==1
    assert source.count("variable = log_ni")==1
    for forbidden in ("PhysicsElectronImpactIonizationMaterial",
                      "o2_ionization.txt","o2_molar_concentration =",
                      "EI16","ei16","R_EI415", "EI-411_O2_X.txt"):
        assert forbidden not in source,forbidden

def verify_replay(source):
    assert source.count(new_ion_line())==1
    assert old_ion_line() not in source
    assert source.count("'$ION'")==1
    assert "export CHEM_SOURCE_INPUTS=\"'$DISS' '$ION' '$ION_O' '$ATTACH'\"" in source
    assert source.count("'$DISS'")==1
    assert source.count("'$ATTACH'")==1
    assert source.count("'$ION_O'")==1
    assert source.count("'$EI2069_OVERLAY'")==2
    assert "'$EI943_OVERLAY'" not in source

def prepare(power):
    for name in ("OXYGEN_RESEARCH_EI401_SWAP",
                 "OXYGEN_RESEARCH_EI412_SWAP",
                 "OXYGEN_RESEARCH_EI941_SWAP",
                 "OXYGEN_RESEARCH_EI2069_PLUS",
                 "OXYGEN_RESEARCH_EI2738_MCS"):
        assert os.environ.get(name)=="1",name
    par=parent()
    par.verify(power)
    state=json.loads((output(power)/"legacy6_latest_variant.json").read_text())
    assert state["chemistry_channels"]==ei2069().ACTIVE
    assert state["scientific_acceptance"]=="HOLD"

    source=original_rate()
    assert source.is_file()
    points=ei2069().read_table(source)
    grid=mcs().parse_grid(output(power)/mcs().REFERENCE_GRID)
    assert len(points)==len(grid)==100
    for (_,reference),(energy,_) in zip(grid,points):
        assert math.isclose(reference,energy,rel_tol=1e-10,abs_tol=1e-10)
    target_rate=working_rate()
    assert not target_rate.exists(),"refuse pre-existing EI415 working lookup"
    shutil.copyfile(source,target_rate)
    assert digest(source)==digest(target_rate)

    previous=old_overlay(power)
    replacement=new_overlay(power)
    assert previous.is_file() and not replacement.exists()
    replacement.write_text(transform(previous.read_text()))
    shell=replay()
    before=shell.read_text()
    assert before.count(old_ion_line())==1 and new_ion_line() not in before
    after=before.replace(old_ion_line(),new_ion_line())
    verify_replay(after)
    shell.write_text(after)

    hashes=(
      ("ei2069_addition_audit.json","native_14ch_replay_sha256"),
      ("ei941_replaces_ei20_audit.json","replaced_14ch_replay_sha256"),
      ("ei412_replaces_dissg_audit.json","ei412_replay_sha256"),
      ("ei401_replaces_ei01_audit.json","ei401_replay_sha256"),
    )
    for filename,key in hashes:
        file=output(power)/filename
        previous_audit=json.loads(file.read_text())
        assert previous_audit[key]==digest_text(before),(filename,key)
        previous_audit[key]=digest_text(after)
        file.write_text(json.dumps(previous_audit,indent=2,sort_keys=True)+"\n")

    a={
      "power_W":power,"mode":"EXCLUSIVE_REPLACEMENT",
      "old_channel":OLD,"new_channel":NEW,
      "reaction":"e + O2(X) -> O2+ + 2e",
      "electron_energy_loss_eV":ENERGY_EV,
      "original_private_lookup_file":RATE,
      "original_private_lookup_sha256":digest(target_rate),
      "original_private_lookup_rows":len(points),
      "original_private_lookup_units":"m3/(mol s)",
      "old_specialized_EI16_ionization_overlay_sha256":digest(previous),
      "new_generic_EI415_ionization_overlay_sha256":digest(replacement),
      "parent_replay_sha256":digest_text(before),
      "ei415_replay_sha256":digest_text(after),
      "parent_chemistry_channels":par.chemistry(),
      "replacement_chemistry_channels":chemistry(),
      "atom_charge_mass_closure":"PASS",
      "scientific_acceptance":"HOLD",
    }
    audit_path(power).write_text(json.dumps(a,indent=2,sort_keys=True)+"\n")
    os.environ[FLAG]="1"
    verify(power)
    print("EI415_REPLACES_EI16_14CH_PREPARE_PASS",power,flush=True)

def verify(power):
    assert os.environ.get(FLAG)=="1"
    parent().verify(power)
    a=json.loads(audit_path(power).read_text())
    assert a["mode"]=="EXCLUSIVE_REPLACEMENT"
    assert a["old_channel"]==OLD and a["new_channel"]==NEW
    assert a["replacement_chemistry_channels"]==chemistry()
    assert a["electron_energy_loss_eV"]==12.06
    assert a["atom_charge_mass_closure"]=="PASS"
    assert a["scientific_acceptance"]=="HOLD"
    assert a["original_private_lookup_sha256"]==digest(original_rate())==digest(working_rate())
    assert len(ei2069().read_table(working_rate()))==100
    assert digest(old_overlay(power))==a["old_specialized_EI16_ionization_overlay_sha256"]
    assert digest(new_overlay(power))==a["new_generic_EI415_ionization_overlay_sha256"]
    verify_overlay(new_overlay(power).read_text())
    verify_replay(replay().read_text())
    assert digest(replay())==a["ei415_replay_sha256"]
    assert not (CHEM/"private_rates"/"EI-943_O_1D.txt").exists()
    print("EI415_REPLACES_EI16_14CH_VERIFIED",power,flush=True)

def archive(power):
    verify(power)
    parent().archive(power)  # actual native solver, final 100us checkpoint
    res=output(power)
    mpath=res/"legacy6_restart_100000ns_manifest.json"
    manifest=json.loads(mpath.read_text())
    assert manifest["verified_full_native_100us_checkpoint"]
    assert math.isclose(manifest["native_endpoint_s"],1e-4,rel_tol=0,abs_tol=1e-12)
    assert manifest["chemistry_channels"]==parent().chemistry()
    legacy=old_overlay(power).name
    drop={legacy,"o2_ionization.txt"}
    records=manifest["inventory"]["inputs"]
    names={Path(x["path"]).name for x in records}
    assert drop.issubset(names),names
    inputs=[Path(x["path"]) for x in records
            if Path(x["path"]).name not in drop]
    target=new_overlay(power)
    assert target not in inputs
    inputs.append(target)
    assert len(inputs)==len(set(inputs))
    assert all(p.is_file() and not p.is_symlink() and
               "private_rates" not in p.as_posix() for p in inputs)
    assert all(p.name not in drop for p in inputs)
    archive_path=res/manifest["archives"]["inputs"]["name"]
    temp=Path(str(archive_path)+".tmp")
    with tarfile.open(temp,"w:gz") as f:
        for p in inputs:f.add(p,arcname=p.as_posix(),recursive=False)
    temp.replace(archive_path)
    with tarfile.open(archive_path,"r:gz") as f:
        names=f.getnames()
    assert names==[p.as_posix() for p in inputs]
    assert not any(Path(x).name in drop or "private_rates" in x for x in names)
    a=json.loads(audit_path(power).read_text())
    manifest["inventory"]["inputs"]=[
        {"path":p.as_posix(),"bytes":p.stat().st_size,"sha256":digest(p)}
        for p in inputs]
    manifest["archives"]["inputs"]={
        "name":archive_path.name,"sha256":digest(archive_path),
        "bytes":archive_path.stat().st_size}
    manifest.update({
        "variant":VARIANT,"chemistry_channels":chemistry(),
        "ei415_replaces_ei16_audit":a,
        "ei415_recovery_private_rate_required":RATE,
        "ei415_recovery_private_rate_sha256":digest(working_rate()),
        "ei415_energy_loss_eV":ENERGY_EV,
        "ei16_replaced_not_parallel":True,
        "restart_requires_exact_ei415_in_ei16_out":True,
        "scientific_acceptance":"HOLD",
    })
    mpath.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    variant=res/"legacy6_latest_variant.json"
    j=json.loads(variant.read_text())
    j.update({
        "variant":VARIANT,"chemistry_channels":chemistry(),
        "ei415_lookup_filename":RATE,"ei415_lookup_sha256":digest(working_rate()),
        "ei415_replaced_ei16":True,"scientific_acceptance":"HOLD",
    })
    variant.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    assert NEW in manifest["chemistry_channels"] and OLD not in manifest["chemistry_channels"]
    print("EI415_REPLACES_EI16_NATIVE_100US_PASS",power,flush=True)

def self_test():
    delta={"e":1,"O2":-1,"O2p":1}
    atoms={"e":0,"O2":2,"O2p":2}
    charges={"e":-1,"O2":0,"O2p":1}
    masses={"e":0,"O2":.032,"O2p":.032}
    assert sum(delta[s]*atoms[s] for s in delta)==0
    assert sum(delta[s]*charges[s] for s in delta)==0
    assert abs(sum(delta[s]*masses[s] for s in delta))<1e-14
    assert OLD!=NEW and RATE=="EI-415_O2_X.txt"
    assert ENERGY_EV==12.06
    assert old_ion_line()!=new_ion_line()
    print("EI415_REPLACES_EI16_14CH_SELF_TEST_PASS",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("self-test","prepare","verify","archive"))
    parser.add_argument("--power-w",type=int,choices=(400,1000))
    args=parser.parse_args()
    if args.action=="self-test":self_test()
    else:
        assert args.power_w in (400,1000)
        {"prepare":prepare,"verify":verify,"archive":archive}[args.action](args.power_w)
