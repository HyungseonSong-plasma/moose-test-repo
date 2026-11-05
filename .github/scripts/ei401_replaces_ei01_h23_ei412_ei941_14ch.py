#!/usr/bin/env python3
"""Replace EI-01 by original HPEM EI-401 in the controlled 14ch oxygen ICP case.

Parent: EI941-for-EI20, EI412-for-DISS-G, EI2069+, EI943-, MCS2738, H23.
Exactly one dissociative-attachment rate owner; the original EI-401_O2_X.txt
100-point private lookup replaces public o2_attachment.txt. The original EI01
electron, negative-ion, O, neutral pressure mass and closure projections are
retained under EI401 identifiers. Both models have zero explicit electron
energy-loss source. No private rates enter public artifacts.
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
RATE="EI-401_O2_X.txt"
OLD="EI-01"
NEW="EI-401"
ENERGY_EV=0.0
FLAG="OXYGEN_RESEARCH_EI401_SWAP"
VARIANT="H23_NO943_MCS2738_EI2069_EI941_EI412_EI401_REPLACES_EI01_14CH_HOLD"
AUDIT="ei401_replaces_ei01_audit.json"
LOOKUP_UNITS="m3/(mol s)"

def module(path,label):
    spec=importlib.util.spec_from_file_location(label,path)
    assert spec and spec.loader,path
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def ei412():
    return module(os.environ.get("EI412",
        "_legacy6_control/.github/scripts/ei412_replaces_dissg_h23_mcs2738_ei2069_ei941_14ch.py"),
        "ei401_parent_ei412")

def ei2069():
    return module(os.environ.get("EI2069",
        "_legacy6_control/.github/scripts/ei2069_h23_no943_mcs2738_14ch.py"),
        "ei401_parent_ei2069")

def mcs():
    return module(os.environ.get("MCS2738",
        "_legacy6_control/.github/scripts/ei2738_mcs_h23_no_ei943_13ch.py"),
        "ei401_parent_mcs")

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):digest.update(part)
    return digest.hexdigest()

def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

def output(power):
    assert power in (400,1000)
    return CHEM/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"

def original_rate():return Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE
def working_rate():return CHEM/"private_rates"/RATE
def old_overlay(power):return CHEM/f"o2_attachment_ei01_{power}w_100us_dt1000ns_overlay.i"
def new_overlay(power):return CHEM/f"o2_attachment_ei401_{power}w_100us_dt1000ns_overlay.i"
def replay():return CHEM/"issue397_l1_power_scan_replay.sh"
def audit_path(power):return output(power)/AUDIT

def old_attach_line():
    dollar=chr(36)
    return ('export ATTACH="$CHEM/o2_attachment_ei01_'+
            dollar+'{POWER_W}w_100us_dt'+dollar+'{DT_NS}ns_overlay.i"')
def new_attach_line():return old_attach_line().replace("attachment_ei01_","attachment_ei401_")

def chemistry():
    current=ei412().chemistry()
    assert current.count(OLD)==1 and NEW not in current
    changed=[NEW if rid==OLD else rid for rid in current]
    assert len(changed)==len(set(changed))==14
    assert "EI-412" in changed and "DISS-G" not in changed
    assert "EI-941" in changed and "EI-20" not in changed
    assert "EI-2069" in changed and "EI-943" not in changed
    assert OLD not in changed
    return changed

def verify_overlay(source):
    required=(
        "type = PhysicsElectronImpactRateMaterial",
        "rate_table_file = 'private_rates/EI-401_O2_X.txt'",
        "mean_energy = mean_en_solved",
        "electron_number_density = n_e_physical",
        "target_molar_concentration = c_O2_EI401",
        "reaction_progress = R_EI401",
        "property_name = S_electron_molar_EI401",
        "property_name = S_Om_molar_EI401",
        "property_name = S_O_mass_EI401",
        "property_name = S_Om_mass_EI401",
        "property_name = S_neutral_mass_EI401",
        "property_name = S_heavy_mass_closure_EI401",
        "property_name = S_charge_molar_closure_EI401",
        "variable = log_ne",
        "variable = log_nm",
        "variable = w_O",
        "variable = p",
        "functor = S_electron_molar_EI401",
        "source = S_O_mass_EI401",
        "v = S_Om_molar_EI401",
        "v = S_neutral_mass_EI401",
    )
    for x in required:assert x in source,x
    assert source.count("reaction_progress = R_EI401")==1
    assert source.count("type = PhysicsElectronImpactRateMaterial")==1
    assert "R_attachment" not in source
    assert "EI01" not in source and "ei01" not in source
    assert "o2_attachment.txt" not in source
    assert "variable = log_energy" not in source
    assert "S_electron_energy" not in source
    assert "electron-energy loss" in source
    assert source.count("variable = log_nm")==1
    assert source.count("variable = log_ne")==1

def transform(source):
    assert source.count("rate_table_file = o2_attachment.txt")==1
    assert source.count("reaction_progress = R_attachment")==1
    assert "0 eV explicit electron-energy loss" in source
    assert "type = PhysicsElectronImpactRateMaterial" in source
    new=source.replace("EI01","EI401").replace("ei01","ei401")
    new=new.replace("R_attachment","R_EI401")
    new=new.replace("rate_table_file = o2_attachment.txt",
                    "rate_table_file = 'private_rates/EI-401_O2_X.txt'")
    new=("# Original EI-401 e + O2(X) -> O- + O; exclusive replacement of EI-01.\n"
         "# Original HPEM mean-energy rate table, 0.0 eV explicit energy loss.\n"
         +new)
    verify_overlay(new)
    return new

def verify_replay(source):
    assert source.count(new_attach_line())==1
    assert old_attach_line() not in source
    assert source.count("'$ATTACH'")==1
    assert "export CHEM_SOURCE_INPUTS=\"'$DISS' '$ION' '$ION_O' '$ATTACH'\"" in source
    assert source.count("'$DISS'")==1
    assert source.count("'$ION_O'")==1
    assert source.count("'$EI2069_OVERLAY'")==2
    assert "'$EI943_OVERLAY'" not in source

def prepare(power):
    assert os.environ.get("OXYGEN_RESEARCH_EI412_SWAP")=="1"
    assert os.environ.get("OXYGEN_RESEARCH_EI941_SWAP")=="1"
    assert os.environ.get("OXYGEN_RESEARCH_EI2069_PLUS")=="1"
    assert os.environ.get("OXYGEN_RESEARCH_EI2738_MCS")=="1"
    parent=ei412()
    parent.verify(power)
    manifest_path=output(power)/"legacy6_latest_variant.json"
    manifest=json.loads(manifest_path.read_text())
    assert manifest["chemistry_channels"]==ei2069().ACTIVE
    assert manifest["variant"]==ei2069().VARIANT
    assert manifest["scientific_acceptance"]=="HOLD"

    rate_src=original_rate()
    assert rate_src.is_file()
    points=ei2069().read_table(rate_src)
    grid=mcs().parse_grid(output(power)/mcs().REFERENCE_GRID)
    assert len(points)==len(grid)==100
    for (_,reference_energy),(actual_energy,_) in zip(grid,points):
        assert math.isclose(reference_energy,actual_energy,rel_tol=1e-10,abs_tol=1e-10)
    target_rate=working_rate()
    assert not target_rate.exists(),"existing EI401 private working lookup"
    shutil.copyfile(rate_src,target_rate)
    assert sha(rate_src)==sha(target_rate)

    previous=old_overlay(power)
    replacement=new_overlay(power)
    assert previous.is_file() and not replacement.exists()
    replacement.write_text(transform(previous.read_text()))
    r=replay()
    before=r.read_text()
    assert before.count(old_attach_line())==1 and new_attach_line() not in before
    after=before.replace(old_attach_line(),new_attach_line())
    verify_replay(after)
    r.write_text(after)

    # These parents verify a byte-exact replay script. Update only those SHA
    # fields as a controlled, audited change in the canonical ATTACH path.
    hashes=(
      ("ei2069_addition_audit.json","native_14ch_replay_sha256"),
      ("ei941_replaces_ei20_audit.json","replaced_14ch_replay_sha256"),
      ("ei412_replaces_dissg_audit.json","ei412_replay_sha256"),
    )
    for name,key in hashes:
        file=output(power)/name
        audit=json.loads(file.read_text())
        assert audit[key]==sha_text(before),(name,key)
        audit[key]=sha_text(after)
        file.write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")

    audit={
      "power_W":power,
      "mode":"EXCLUSIVE_REPLACEMENT",
      "old_channel":OLD,
      "new_channel":NEW,
      "reaction":"e + O2(X) -> O- + O",
      "electron_energy_loss_eV":ENERGY_EV,
      "original_private_lookup_file":RATE,
      "original_private_lookup_sha256":sha(target_rate),
      "original_private_lookup_rows":len(points),
      "original_private_lookup_units":LOOKUP_UNITS,
      "legacy_ei01_overlay_sha256":sha(previous),
      "ei401_overlay_sha256":sha(replacement),
      "parent_replay_sha256":sha_text(before),
      "ei401_replay_sha256":sha_text(after),
      "parent_chemistry_channels":parent.chemistry(),
      "replacement_chemistry_channels":chemistry(),
      "charge_mass_atom_closure":"PASS",
      "electron_energy_loss_sink":"NO_EXPLICIT_SOURCE_0EV",
      "scientific_acceptance":"HOLD",
    }
    audit_path(power).write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    os.environ[FLAG]="1"
    verify(power)
    print("EI401_REPLACES_EI01_14CH_PREPARE_PASS",power,flush=True)

def verify(power):
    assert os.environ.get(FLAG)=="1"
    ei412().verify(power)
    audit=json.loads(audit_path(power).read_text())
    assert audit["old_channel"]==OLD and audit["new_channel"]==NEW
    assert audit["mode"]=="EXCLUSIVE_REPLACEMENT"
    assert audit["original_private_lookup_sha256"]==sha(original_rate())==sha(working_rate())
    assert len(ei2069().read_table(working_rate()))==100
    assert audit["replacement_chemistry_channels"]==chemistry()
    assert audit["scientific_acceptance"]=="HOLD"
    assert audit["electron_energy_loss_eV"]==0.0
    assert audit["charge_mass_atom_closure"]=="PASS"
    assert sha(old_overlay(power))==audit["legacy_ei01_overlay_sha256"]
    assert sha(new_overlay(power))==audit["ei401_overlay_sha256"]
    verify_overlay(new_overlay(power).read_text())
    verify_replay(replay().read_text())
    assert sha(replay())==audit["ei401_replay_sha256"]
    assert not (CHEM/"private_rates"/"EI-943_O_1D.txt").exists()
    print("EI401_REPLACES_EI01_14CH_VERIFIED",power,flush=True)

def archive(power):
    verify(power)
    ei412().archive(power)  # genuine native 100us checkpoint via parent gates
    res=output(power)
    manifest_path=res/"legacy6_restart_100000ns_manifest.json"
    m=json.loads(manifest_path.read_text())
    assert m["verified_full_native_100us_checkpoint"]
    assert math.isclose(m["native_endpoint_s"],1e-4,rel_tol=0,abs_tol=1e-12)
    assert m["chemistry_channels"]==ei412().chemistry()
    legacy=old_overlay(power).name
    excluded={legacy,"o2_attachment.txt"}
    items=m["inventory"]["inputs"]
    names={Path(x["path"]).name for x in items}
    assert excluded.issubset(names)
    inputs=[Path(x["path"]) for x in items
            if Path(x["path"]).name not in excluded]
    new=new_overlay(power)
    assert new not in inputs
    inputs.append(new)
    assert len(inputs)==len(set(inputs))
    assert all(p.is_file() and not p.is_symlink() and "private_rates" not in p.as_posix() for p in inputs)
    assert not any(p.name in excluded for p in inputs)
    tarpath=res/m["archives"]["inputs"]["name"]
    temp=Path(str(tarpath)+".tmp")
    with tarfile.open(temp,"w:gz") as f:
        for p in inputs:f.add(p,arcname=p.as_posix(),recursive=False)
    temp.replace(tarpath)
    with tarfile.open(tarpath,"r:gz") as f:
        archived=f.getnames()
    assert archived==[p.as_posix() for p in inputs]
    assert not any(Path(name).name in excluded or "private_rates" in name for name in archived)
    audit=json.loads(audit_path(power).read_text())
    m["inventory"]["inputs"]=[
        {"path":p.as_posix(),"bytes":p.stat().st_size,"sha256":sha(p)}
        for p in inputs
    ]
    m["archives"]["inputs"]={
        "name":tarpath.name,"sha256":sha(tarpath),"bytes":tarpath.stat().st_size
    }
    m.update({
        "variant":VARIANT,"chemistry_channels":chemistry(),
        "ei401_replaces_ei01_audit":audit,
        "ei401_recovery_private_rate_required":RATE,
        "ei401_recovery_private_rate_sha256":sha(working_rate()),
        "ei401_energy_loss_eV":ENERGY_EV,
        "ei01_replaced_not_parallel":True,
        "restart_requires_exact_ei401_in_ei01_out":True,
        "scientific_acceptance":"HOLD",
    })
    manifest_path.write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    latest=res/"legacy6_latest_variant.json"
    j=json.loads(latest.read_text())
    j.update({
        "variant":VARIANT,"chemistry_channels":chemistry(),
        "ei401_lookup_filename":RATE,"ei401_lookup_sha256":sha(working_rate()),
        "ei401_replaced_ei01":True,"scientific_acceptance":"HOLD",
    })
    latest.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    assert OLD not in m["chemistry_channels"] and NEW in m["chemistry_channels"]
    assert "EI-401" in j["chemistry_channels"] and "EI-01" not in j["chemistry_channels"]
    print("EI401_REPLACES_EI01_NATIVE_100US_PASS",power,flush=True)

def self_test():
    delta={"e":-1,"O2":-1,"O":1,"Om":1}
    mass={"e":0,"O2":0.032,"O":0.016,"Om":0.016}
    atoms={"e":0,"O2":2,"O":1,"Om":1}
    charge={"e":-1,"O2":0,"O":0,"Om":-1}
    assert sum(delta[k]*mass[k] for k in delta)==0
    assert sum(delta[k]*atoms[k] for k in delta)==0
    assert sum(delta[k]*charge[k] for k in delta)==0
    assert RATE=="EI-401_O2_X.txt" and ENERGY_EV==0
    assert old_attach_line()!=new_attach_line()
    print("EI401_REPLACES_EI01_SELF_TEST_PASS",flush=True)

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("action",choices=("self-test","prepare","verify","archive"))
    cli.add_argument("--power-w",type=int,choices=(400,1000))
    args=cli.parse_args()
    if args.action=="self-test":self_test()
    else:
        assert args.power_w in (400,1000)
        {"prepare":prepare,"verify":verify,"archive":archive}[args.action](args.power_w)
