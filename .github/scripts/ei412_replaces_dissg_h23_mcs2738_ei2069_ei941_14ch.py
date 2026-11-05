#!/usr/bin/env python3
"""One-channel controlled replacement: DISS-G -> original HPEM EI-412.

Parent is the 14ch H23+, EI943-, MCS EI2738+, EI2069+, EI941-in/EI20-out
native case at 400W/1000W. Keep all other rates, mesh, RF and EEDF pinned.
EI-412 is a separate native PhysicsElectronImpactRateMaterial using the
original private EI-412_O2_X.txt 100-point table. Do NOT add 411, or run
DISS-G in parallel. Both DISS-G and EI-412 use 6 eV/event energy loss.
No private rate data are published. Research scientific acceptance HOLD.
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
RATE="EI-412_O2_X.txt"
OLD="DISS-G"
NEW="EI-412"
VARIANT="H23_NO943_MCS2738_EI2069_EI941_EI412_REPLACES_DISSG_14CH_HOLD"
FLAG="OXYGEN_RESEARCH_EI412_SWAP"
ENERGY_EV=6.0
AUDIT="ei412_replaces_dissg_audit.json"
LOOKUP_UNITS="m3/(mol s)"

def load(path,label):
    spec=importlib.util.spec_from_file_location(label,path)
    assert spec and spec.loader,path
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def ei941():
    return load(os.environ.get(
        "EI941","_legacy6_control/.github/scripts/ei941_replace_ei20_14ch.py"),
        "ei412_parent_ei941")

def ei2069():
    return load(os.environ.get(
        "EI2069","_legacy6_control/.github/scripts/ei2069_h23_no943_mcs2738_14ch.py"),
        "ei412_parent_ei2069")

def mcs():
    return load(os.environ.get(
        "MCS2738","_legacy6_control/.github/scripts/ei2738_mcs_h23_no_ei943_13ch.py"),
        "ei412_parent_mcs")

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def sha_text(src):
    return hashlib.sha256(src.encode()).hexdigest()

def result(power):
    assert power in (400,1000)
    return CHEM/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"

def original_rate():return Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE
def working_rate():return CHEM/"private_rates"/RATE
def old_overlay(power):return CHEM/f"o2_dissociation_{power}w_100us_dt1000ns_overlay.i"
def new_overlay(power):return CHEM/f"o2_dissociation_ei412_{power}w_100us_dt1000ns_overlay.i"
def audit_path(power):return result(power)/AUDIT
def replay():return CHEM/"issue397_l1_power_scan_replay.sh"

def original_diss_line():
    dollar=chr(36)
    return ('export DISS="$CHEM/o2_dissociation_'+
            dollar+'{POWER_W}w_100us_dt'+dollar+'{DT_NS}ns_overlay.i"')

def replacement_diss_line():
    return original_diss_line().replace("o2_dissociation_","o2_dissociation_ei412_")

def chemistry():
    base=ei941().active()
    assert len(base)==14 and base.count(OLD)==1 and NEW not in base
    active=[NEW if rid==OLD else rid for rid in base]
    assert len(active)==len(set(active))==14
    assert "EI-941" in active and "EI-20" not in active
    assert "EI-2069" in active and "EI-943" not in active
    assert OLD not in active and "EI-411" not in active
    return active

def source_text(legacy):
    """Replace exactly one DISS-G progress owner, retaining identical source kernels."""
    begin=legacy.index("  [diss_electron_temperature]\n")
    end=legacy.index("  [diss_o_mass_source]\n",begin)
    assert legacy.count("  [diss_o2_progress]\n")==1
    assert "type = ADParsedFunctorMaterial" in legacy[begin:end]
    assert "property_name = R_diss_O2" in legacy[begin:end]
    assert "1.41e-15" in legacy[begin:end]
    assert "Te_diss_eV" in legacy[begin:end]
    assert legacy.count("expression = '-6*R'")==1
    owner="""  [diss_o2_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-412_O2_X.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2_diss
    reaction_progress = R_diss_O2
    block = plasma
  []
"""
    new=legacy[:begin]+owner+legacy[end:]
    new=("# Original HPEM EI-412 O2(X) electron-impact dissociation, e + O2 -> e + 2 O(3P).\n"
         "# Exclusive replacement of DISS-G, 6.0 eV/event electron-energy loss.\n"
         "# Rate from original private EI-412_O2_X.txt, same source projections.\n"+
         new[new.index("[FunctorMaterials]\n"):])
    verify_source(new)
    return new

def verify_source(src):
    must=[
        "type = PhysicsElectronImpactRateMaterial",
        "rate_table_file = 'private_rates/EI-412_O2_X.txt'",
        "electron_number_density = n_e_physical",
        "mean_energy = mean_en_solved",
        "target_molar_concentration = c_O2_diss",
        "reaction_progress = R_diss_O2",
        "property_name = S_O_mass_diss",
        "property_name = S_O2_mass_diss_implicit",
        "property_name = S_electron_energy_molar_diss",
        "expression = '-6*R'",
        "variable = w_O",
        "variable = log_energy",
        "source = S_O_mass_diss",
        "functor = S_electron_energy_molar_diss",
        "functor = R_diss_O2",
        "functor = S_heavy_mass_closure_diss",
    ]
    for x in must:assert x in src,x
    assert src.count("reaction_progress = R_diss_O2")==1
    assert src.count("type = PhysicsElectronImpactRateMaterial")==1
    assert src.count("expression = '-6*R'")==1
    for invalid in ("Te_diss_eV","1.41e-15","R_diss_411",
                    "R_diss_412","EI-411_O2_X.txt","diss_electron_temperature"):
        assert invalid not in src,invalid
    assert "variable = log_ne" not in src  # dissociation has no net electrons

def verify_replay(src):
    assert src.count(replacement_diss_line())==1
    assert original_diss_line() not in src
    assert src.count("'$DISS'")==1
    assert "export CHEM_SOURCE_INPUTS=\"'$DISS' '$ION' '$ION_O' '$ATTACH'\"" in src
    assert src.count("'$ION_O'")==1
    assert "'$EI943_OVERLAY'" not in src
    assert src.count("'$EI2069_OVERLAY'")==2

def prepare(power):
    assert os.environ.get("OXYGEN_RESEARCH_EI941_SWAP")=="1"
    assert os.environ.get("OXYGEN_RESEARCH_EI2069_PLUS")=="1"
    assert os.environ.get("OXYGEN_RESEARCH_EI2738_MCS")=="1"
    parent=ei941()
    parent.verify(power)
    manifest=result(power)/"legacy6_latest_variant.json"
    j=json.loads(manifest.read_text())
    assert j["chemistry_channels"]==ei2069().ACTIVE
    assert j["variant"]==ei2069().VARIANT
    assert j["scientific_acceptance"]=="HOLD"

    source=original_rate()
    assert source.is_file()
    rows=ei2069().read_table(source)
    reference=mcs().parse_grid(result(power)/mcs().REFERENCE_GRID)
    assert len(rows)==len(reference)==100
    for (_,expected),(energy,_) in zip(reference,rows):
        assert math.isclose(expected,energy,rel_tol=1e-10,abs_tol=1e-10)
    rate=working_rate()
    assert not rate.exists(),"refuse overwrite of existing EI-412 private working rate"
    shutil.copyfile(source,rate)
    assert sha(source)==sha(rate)

    previous=old_overlay(power)
    replacement=new_overlay(power)
    assert previous.is_file() and not replacement.exists()
    original=previous.read_text()
    changed=source_text(original)
    replacement.write_text(changed)
    replay_script=replay()
    before=replay_script.read_text()
    assert before.count(original_diss_line())==1
    assert replacement_diss_line() not in before
    after=before.replace(original_diss_line(),replacement_diss_line())
    verify_replay(after)
    replay_script.write_text(after)

    # Parent layers audit exact replay hash. This mutation is controlled and
    # must update those attestations without changing their chemistry owners.
    p2069=result(power)/"ei2069_addition_audit.json"
    p941=result(power)/"ei941_replaces_ei20_audit.json"
    a2069=json.loads(p2069.read_text())
    a941=json.loads(p941.read_text())
    assert a2069["native_14ch_replay_sha256"]==sha_text(before)
    assert a941["replaced_14ch_replay_sha256"]==sha_text(before)
    a2069["native_14ch_replay_sha256"]=sha_text(after)
    a941["replaced_14ch_replay_sha256"]=sha_text(after)
    p2069.write_text(json.dumps(a2069,indent=2,sort_keys=True)+"\n")
    p941.write_text(json.dumps(a941,indent=2,sort_keys=True)+"\n")

    a={
      "power_W":power,"replacement":"DISS-G -> EI-412","mode":"EXCLUSIVE_REPLACEMENT",
      "old_channel":OLD,"new_channel":NEW,"electron_energy_loss_eV":ENERGY_EV,
      "reaction":"e + O2(X) -> e + O(3P) + O(3P)",
      "original_private_lookup_file":RATE,
      "original_private_lookup_sha256":sha(rate),
      "original_private_lookup_rows":len(rows),
      "original_private_lookup_units":LOOKUP_UNITS,
      "legacy_diss_g_overlay_sha256":sha(previous),
      "ei412_native_overlay_sha256":sha(replacement),
      "parent_replay_sha256":sha_text(before),
      "ei412_replay_sha256":sha_text(after),
      "parent_chemistry_channels":parent.active(),
      "replaced_chemistry_channels":chemistry(),
      "electron_delta":0,"oxygen_atom_delta":0,"charge_delta":0,
      "scientific_acceptance":"HOLD",
    }
    audit_path(power).write_text(json.dumps(a,indent=2,sort_keys=True)+"\n")
    os.environ[FLAG]="1"
    verify(power)
    print("EI412_REPLACES_DISSG_14CH_PREPARE_PASS",power,flush=True)

def verify(power):
    assert os.environ.get(FLAG)=="1"
    ei941().verify(power)
    a=json.loads(audit_path(power).read_text())
    assert a["mode"]=="EXCLUSIVE_REPLACEMENT"
    assert a["old_channel"]==OLD and a["new_channel"]==NEW
    assert a["replaced_chemistry_channels"]==chemistry()
    assert a["electron_energy_loss_eV"]==6.0
    assert a["scientific_acceptance"]=="HOLD"
    assert a["original_private_lookup_sha256"]==sha(original_rate())==sha(working_rate())
    assert len(ei2069().read_table(working_rate()))==100
    assert sha(old_overlay(power))==a["legacy_diss_g_overlay_sha256"]
    assert sha(new_overlay(power))==a["ei412_native_overlay_sha256"]
    verify_source(new_overlay(power).read_text())
    verify_replay(replay().read_text())
    assert sha(replay())==a["ei412_replay_sha256"]
    assert not (CHEM/"private_rates"/"EI-943_O_1D.txt").exists()
    print("EI412_REPLACES_DISSG_14CH_VERIFIED",power,flush=True)

def archive(power):
    verify(power)
    ei941().archive(power)  # unchanged actual solver/checkpoint and EI941 gates
    res=result(power)
    manifest_path=res/"legacy6_restart_100000ns_manifest.json"
    manifest=json.loads(manifest_path.read_text())
    assert manifest["verified_full_native_100us_checkpoint"]
    assert math.isclose(manifest["native_endpoint_s"],1e-4,rel_tol=0,abs_tol=1e-12)
    assert manifest["chemistry_channels"]==ei941().active()
    old=old_overlay(power).name
    entries=manifest["inventory"]["inputs"]
    assert sum(Path(e["path"]).name==old for e in entries)==1
    inputs=[Path(x["path"]) for x in entries if Path(x["path"]).name!=old]
    replacement=new_overlay(power)
    assert replacement not in inputs
    inputs.append(replacement)
    assert len(inputs)==len(set(inputs))
    assert all(p.is_file() and not p.is_symlink() and "private_rates" not in p.as_posix() for p in inputs)
    assert not any(p.name==old for p in inputs)
    tarpath=res/manifest["archives"]["inputs"]["name"]
    tmp=Path(str(tarpath)+".tmp")
    with tarfile.open(tmp,"w:gz") as tf:
        for p in inputs:tf.add(p,arcname=p.as_posix(),recursive=False)
    tmp.replace(tarpath)
    with tarfile.open(tarpath,"r:gz") as tf: filenames=tf.getnames()
    assert filenames==[p.as_posix() for p in inputs]
    assert all("private_rates" not in name for name in filenames)
    a=json.loads(audit_path(power).read_text())
    manifest["inventory"]["inputs"]=[
        {"path":p.as_posix(),"bytes":p.stat().st_size,"sha256":sha(p)}
        for p in inputs]
    manifest["archives"]["inputs"]={
        "name":tarpath.name,"sha256":sha(tarpath),"bytes":tarpath.stat().st_size}
    manifest.update({
        "variant":VARIANT,"chemistry_channels":chemistry(),
        "ei412_replaces_dissg_audit":a,
        "ei412_recovery_private_rate_required":RATE,
        "ei412_recovery_private_rate_sha256":sha(working_rate()),
        "ei412_energy_loss_eV":ENERGY_EV,
        "dissg_replaced_not_parallel":True,
        "restart_requires_exact_ei412_in_dissg_out":True,
        "scientific_acceptance":"HOLD",
    })
    manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    original_manifest=res/"legacy6_latest_variant.json"
    j=json.loads(original_manifest.read_text())
    j.update({
        "variant":VARIANT,"chemistry_channels":chemistry(),
        "ei412_lookup_filename":RATE,"ei412_lookup_sha256":sha(working_rate()),
        "ei412_replaced_dissg":True,"scientific_acceptance":"HOLD",
    })
    original_manifest.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    assert "DISS-G" not in manifest["chemistry_channels"]
    assert "EI-412" in manifest["chemistry_channels"]
    assert not any(p["path"].endswith("/"+old) for p in manifest["inventory"]["inputs"])
    print("EI412_REPLACES_DISSG_NATIVE_100US_PASS",power,flush=True)

def self_test():
    assert ENERGY_EV==6.0
    assert original_diss_line().count("o2_dissociation_")==1
    assert replacement_diss_line().count("o2_dissociation_ei412_")==1
    delta={"e":0,"O2":-1,"O":2}
    atoms={"e":0,"O2":2,"O":1}
    charge={"e":-1,"O2":0,"O":0}
    mass={"e":0,"O2":0.032,"O":0.016}
    assert sum(delta[k]*atoms[k] for k in delta)==0
    assert sum(delta[k]*charge[k] for k in delta)==0
    assert abs(sum(delta[k]*mass[k] for k in delta))<1e-14
    assert RATE=="EI-412_O2_X.txt"
    print("EI412_REPLACES_DISSG_14CH_SELF_TEST_PASS",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("self-test","prepare","verify","archive"))
    parser.add_argument("--power-w",type=int,choices=(400,1000))
    args=parser.parse_args()
    if args.action=="self-test":self_test()
    else:
        assert args.power_w in (400,1000)
        {"prepare":prepare,"verify":verify,"archive":archive}[args.action](args.power_w)
