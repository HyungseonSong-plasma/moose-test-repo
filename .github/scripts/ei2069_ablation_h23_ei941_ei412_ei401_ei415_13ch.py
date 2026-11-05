#!/usr/bin/env python3
"""Ablate only EI-2069 from the latest 14-channel oxygen ICP research parent.

Parent: EI-415 in/EI-16 out; EI-401 in/EI-01 out; EI-412 in/DISS-G
out; EI-941 in/EI-20 out; EI-2069 in and EI-943 out; H23/MCS2738 in.
Starting from parent-verified physical inputs, remove the EI-2069 overlay
from *both* native check and solve argv, delete working overlay and private
rate, and keep all other rate materials/meshes/RF/EEDF identical. Archive
the true native 100us checkpoint without copying an inactive overlay,
inactive rate, or any private lookup into public artifacts. Science HOLD.
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
REMOVED="EI-2069"
RATE="EI-2069_O2_a1Delta.txt"
ENERGY_EV=5.02
FLAG="OXYGEN_RESEARCH_NO_EI2069"
VARIANT="H23_NO943_MCS2738_EI941_EI412_EI401_EI415_NO_EI2069_13CH_ABLATION_HOLD"
AUDIT="no_ei2069_ablation_audit.json"
ARGV_AUDIT="no_ei2069_argv_patch.json"
PINNED="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
EEDF="35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"

def import_module(path,label):
    spec=importlib.util.spec_from_file_location(label,path)
    assert spec and spec.loader,path
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def ei415():
    return import_module(os.environ.get(
       "EI415","_legacy6_control/.github/scripts/ei415_replaces_ei16_h23_ei401_ei412_ei941_14ch.py"),
       "no2069_ei415_parent")

def ei2069():
    return import_module(os.environ.get(
       "EI2069","_legacy6_control/.github/scripts/ei2069_h23_no943_mcs2738_14ch.py"),
       "no2069_parent_ei2069")

def mcs():
    return import_module(os.environ.get(
       "MCS2738","_legacy6_control/.github/scripts/ei2738_mcs_h23_no_ei943_13ch.py"),
       "no2069_parent_mcs")

def base_and_modules():
    return ei2069().parent().modules()

def hash_file(path):
    obj=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):obj.update(block)
    return obj.hexdigest()

def hash_text(s):return hashlib.sha256(s.encode()).hexdigest()

def result(power):
    assert power in (400,1000)
    return CHEM/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"

def audit_path(power):return result(power)/AUDIT
def argv_audit_path(power):return result(power)/ARGV_AUDIT
def replay():return CHEM/"issue397_l1_power_scan_replay.sh"
def overlay(power):return ei2069().overlay(power)
def working_rate():return CHEM/"private_rates"/RATE
def original_rate():return Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE

def active():
    parent=ei415().chemistry()
    assert len(parent)==14 and parent.count(REMOVED)==1
    target=[rid for rid in parent if rid!=REMOVED]
    assert len(target)==len(set(target))==13
    assert target==[
        "EI-401","EI-02","EI-412","EI-415","EI-17",
        "EI-941","EI-2738","EI-407","EI-417","EI-935",
        "H24","H25","H23",
    ]
    assert "EI-943" not in target and "DISS-G" not in target
    return target

def validate_replay(script):
    assert "'$EI2069_OVERLAY'" not in script
    assert script.count(" '$H23_OVERLAY'")==2
    for token in ("EI407_OVERLAY","EI417_OVERLAY","EI935_OVERLAY",
                  "H24_OVERLAY","H25_OVERLAY","H23_OVERLAY"):
        assert script.count("'$"+token+"'")==2,token
    assert script.count(chr(36)+"{EI2738_EXTRA_INPUT}")==2
    assert "'$EI943_OVERLAY'" not in script
    assert "$EI2259_OVERLAY" not in script
    assert "$EI2058_OVERLAY" not in script
    assert script.count("export CHEM_SOURCE_INPUTS=\"'$DISS' '$ION' '$ION_O' '$ATTACH'\"")==1
    assert "export ION=\"$CHEM/o2_ionization_ei415_" in script
    assert "export ION_O=\"$CHEM/o_ionization_ei941_" in script
    assert "export DISS=\"$CHEM/o2_dissociation_ei412_" in script
    assert "export ATTACH=\"$CHEM/o2_attachment_ei401_" in script
    assert script.count("'$ION'")==1
    assert script.count("'$ION_O'")==1
    assert script.count("'$ATTACH'")==1
    assert script.count("'$DISS'")==1
    assert "Outputs/file_base='$RESULT/run/plasma'" in script

def active_overlays(power):
    # All active owner layers except the six source-installed legacy
    # transport/elastic base overlays, which base archival captures itself.
    h23,h25,h24,ei943,ei935,b8,l7,base=base_and_modules()
    active_files=[
      l7.overlay_path(base,power),
      b8.overlay(power),ei935.f417(power),ei935.f935(power),
      h24.overlay(power),h25.overlay(power),h23.overlay(power),
      CHEM/f"o_ionization_ei941_{power}w_100us_dt1000ns_overlay.i",
      CHEM/f"o2_dissociation_ei412_{power}w_100us_dt1000ns_overlay.i",
      CHEM/f"o2_attachment_ei401_{power}w_100us_dt1000ns_overlay.i",
      CHEM/f"o2_ionization_ei415_{power}w_100us_dt1000ns_overlay.i",
    ]
    assert len(active_files)==len(set(active_files))
    for p in active_files:
        assert p.is_file() and not p.is_symlink(),p
        src=p.read_text()
        assert "R_EI2069" not in src,p
        assert "EI-2069_O2_a1Delta" not in src,p
    return active_files

def excluded_legacy_names(power):
    # The pinned legacy baseline must exist for source tests, but its
    # replaced source/rate owners must not be presented as active
    # restart inputs in the archived bundle.
    return {
        overlay(power).name,
        f"o2_attachment_ei01_{power}w_100us_dt1000ns_overlay.i",
        f"o2_dissociation_{power}w_100us_dt1000ns_overlay.i",
        f"o2_ionization_{power}w_100us_dt1000ns_overlay.i",
        f"o_ionization_ei20_{power}w_100us_dt1000ns_overlay.i",
        "o2_attachment.txt","o2_ionization.txt","o_ionization.txt",
    }

def self_test():
    parent=ei415().chemistry()
    assert len(parent)==14 and parent.count(REMOVED)==1
    assert active()==[x for x in parent if x!=REMOVED]
    assert REMOVED not in active() and "EI-2069" not in active()
    assert ENERGY_EV==5.02
    assert len(excluded_legacy_names(400))==8
    delta={"e":0,"O2a":-1,"O":2}
    mass={"e":0.0,"O2a":.032,"O":.016}
    atoms={"e":0,"O2a":2,"O":1}
    charge={"e":-1,"O2a":0,"O":0}
    assert sum(delta[x]*atoms[x] for x in delta)==0
    assert sum(delta[x]*charge[x] for x in delta)==0
    assert abs(sum(delta[x]*mass[x] for x in delta))<1e-14
    print("EI2069_13CH_ABLATION_SELF_TEST_PASS",flush=True)

def prepare(power):
    # Parent has been fully prepared and verified, including exclusive
    # EI415/EI401/EI412/EI941 swaps, BEFORE stripping EI2069.
    for flag in ("OXYGEN_RESEARCH_EI2738_MCS","OXYGEN_RESEARCH_EI2069_PLUS",
                 "OXYGEN_RESEARCH_EI941_SWAP","OXYGEN_RESEARCH_EI412_SWAP",
                 "OXYGEN_RESEARCH_EI401_SWAP","OXYGEN_RESEARCH_EI415_SWAP"):
        assert os.environ.get(flag)=="1",flag
    par=ei415()
    par.verify(power)
    state_path=result(power)/"legacy6_latest_variant.json"
    state=json.loads(state_path.read_text())
    assert state["chemistry_channels"]==ei2069().ACTIVE
    assert state["scientific_acceptance"]=="HOLD"
    assert state["physics_source_sha"]==PINNED
    assert state["transport_table_sha256"]==EEDF
    assert state["native_initialization"]=="fresh_not_restarted"
    assert state["power_W"]==power
    expected_parent=par.chemistry()
    assert len(expected_parent)==14 and expected_parent[-1]==REMOVED
    before=replay().read_text()
    assert before.count(" '$EI2069_OVERLAY'")==2
    assert len(ei2069().read_table(working_rate()))==100
    assert hash_file(original_rate())==hash_file(working_rate())==state["ei2069_lookup_sha256"]
    old_rate_sha=hash_file(working_rate())
    old_overlay_sha=hash_file(overlay(power))
    old_state_sha=hash_file(state_path)

    # Remove TWO argv entries, not zero the rate or simply relabel metadata.
    changed=before.replace(" '$EI2069_OVERLAY'","")
    assert changed!=before
    validate_replay(changed)
    replay().write_text(changed)
    overlay(power).unlink()
    working_rate().unlink()
    assert not overlay(power).exists() and not working_rate().exists()

    # Prior parent audits are frozen as pre-ablation evidence (their hashes
    # describe the original parent replay). A new exact patched argv SHA
    # independently attests to the real ablated check/solve source.
    a={
      "power_W":power,"mode":"EXACT_REACTION_ABLATION",
      "removed_channel":REMOVED,"removed_reaction":"e + O2(a1Delta) -> e + 2 O(3P)",
      "removed_energy_loss_eV_per_event":ENERGY_EV,
      "parent_chemistry_channels":expected_parent,
      "active_chemistry_channels":active(),
      "parent_14ch_replay_sha256":hash_text(before),
      "ablated_13ch_replay_sha256":hash_text(changed),
      "parent_14ch_variant_sha256":old_state_sha,
      "removed_original_private_rate_name":RATE,
      "removed_original_private_rate_sha256":old_rate_sha,
      "removed_original_private_rate_rows":100,
      "removed_overlay_sha256":old_overlay_sha,
      "ei2069_overlay_removed_from_working_tree":True,
      "ei2069_rate_removed_from_working_tree":True,
      "ei2069_check_solve_argv_occurrences":0,
      "other_reaction_rate_owners_unchanged":True,
      "removed_rate_energy_mass_owners_absent":True,
      "native_initialization":"fresh_not_restarted",
      "scientific_acceptance":"HOLD",
    }
    audit_path(power).write_text(json.dumps(a,indent=2,sort_keys=True)+"\n")
    argv_audit_path(power).write_text(json.dumps({
      "power_W":power,"parent_14ch_replay_sha256":a["parent_14ch_replay_sha256"],
      "ablated_13ch_replay_sha256":a["ablated_13ch_replay_sha256"],
      "check_argv_ei2069_count":0,"solve_argv_ei2069_count":0,
      "intentionally_omitted_overlay":REMOVED,
      "native_input_chemistry_channels":active(),
      "scientific_acceptance":"HOLD",
    },indent=2,sort_keys=True)+"\n")

    # EI2069's historical 'in' provenance must never be mistaken for
    # active or restart-required chemistry in the new control.
    state={k:v for k,v in state.items() if not k.startswith("ei2069_")}
    state.update({
      "variant":VARIANT,"chemistry_channels":active(),
      "hold_excluded":sorted(set(state.get("hold_excluded",[]))|{REMOVED}),
      "ei2069_ablation":"FULLY_EXCLUDED_FROM_NATIVE_CHECK_AND_SOLVE_ARGV",
      "ei2069_recovery_private_rate_required":False,
      "ei2069_recovery_overlay_required":False,
      "ei2069_scientific_status":"ABLATION_UNDER_TEST",
      "restart_requires_exact_13ch_no_ei2069_with_ei415_ei401_ei412_ei941":True,
      "scientific_acceptance":"HOLD",
    })
    state_path.write_text(json.dumps(state,indent=2,sort_keys=True)+"\n")
    os.environ[FLAG]="1"
    verify(power)
    print("EI2069_13CH_ABLATION_PREPARE_PASS",power,flush=True)

def verify(power):
    assert os.environ.get(FLAG)=="1","EI2069 ablation must run in this process"
    manifest=json.loads((result(power)/"legacy6_latest_variant.json").read_text())
    a=json.loads(audit_path(power).read_text())
    argv=json.loads(argv_audit_path(power).read_text())
    assert manifest["variant"]==VARIANT and manifest["chemistry_channels"]==active()
    assert manifest["scientific_acceptance"]=="HOLD"
    assert manifest["native_initialization"]=="fresh_not_restarted"
    assert manifest["physics_source_sha"]==PINNED
    assert manifest["transport_table_sha256"]==EEDF
    assert manifest["ei2069_ablation"]=="FULLY_EXCLUDED_FROM_NATIVE_CHECK_AND_SOLVE_ARGV"
    assert manifest["ei2069_recovery_private_rate_required"] is False
    assert manifest["ei2069_recovery_overlay_required"] is False
    assert REMOVED not in manifest["chemistry_channels"]
    assert not overlay(power).exists() and not working_rate().exists()
    assert hash_file(original_rate())==a["removed_original_private_rate_sha256"]
    assert a["active_chemistry_channels"]==active()
    assert a["parent_chemistry_channels"]==ei415().chemistry()
    assert a["mode"]=="EXACT_REACTION_ABLATION"
    assert a["ei2069_check_solve_argv_occurrences"]==0
    assert a["removed_rate_energy_mass_owners_absent"] is True
    assert a["scientific_acceptance"]=="HOLD"
    src=replay().read_text()
    validate_replay(src)
    assert hash_file(replay())==a["ablated_13ch_replay_sha256"]
    assert argv["ablated_13ch_replay_sha256"]==a["ablated_13ch_replay_sha256"]
    assert argv["check_argv_ei2069_count"]==argv["solve_argv_ei2069_count"]==0
    assert argv["native_input_chemistry_channels"]==active()
    active_overlays(power)
    assert not (CHEM/"private_rates"/"EI-943_O_1D.txt").exists()
    print("EI2069_13CH_ABLATION_EXACT_CHECK_SOLVE_VERIFY_PASS",power,flush=True)

def archive(power):
    verify(power)
    h23,h25,h24,ei943,ei935,b8,l7,base=base_and_modules()
    res=result(power)
    present=active_overlays(power)
    # Call the genuine canonical checkpoint verifier, but do NOT call the
    # 14ch parent archive, whose post-solve validation requires EI2069 in argv.
    # An independent post-filter ensures only actually active replacement
    # overlays are represented as restart inputs.
    base.PERSIST=tuple(base.PERSIST)+tuple(p.name for p in present)+(
      replay().name,
    )
    assert len(base.PERSIST)==len(set(base.PERSIST))
    base.verify_and_archive(power)
    mpath=res/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(mpath.read_text())
    assert saved["verified_full_native_100us_checkpoint"]
    assert math.isclose(saved["native_endpoint_s"],1e-4,abs_tol=1e-12)
    assert saved["chemistry_channels"]==active() and saved["variant"]==VARIANT
    before=saved["inventory"]["inputs"]
    drop=excluded_legacy_names(power)
    inventory_names={Path(x["path"]).name for x in before}
    assert drop.issubset(inventory_names),sorted(drop-inventory_names)
    inputs=[Path(x["path"]) for x in before
            if Path(x["path"]).name not in drop]
    assert all(p.name not in drop for p in inputs)
    assert set(present).issubset(set(inputs))
    assert replay() in inputs
    assert len(inputs)==len(set(inputs))
    assert all(p.is_file() and not p.is_symlink() and
               "private_rates" not in p.as_posix() for p in inputs)
    assert not any("ei2069" in p.as_posix().lower() for p in inputs)
    assert not any("ei943" in p.as_posix().lower() for p in inputs)
    tarpath=res/saved["archives"]["inputs"]["name"]
    temp=Path(str(tarpath)+".tmp")
    with tarfile.open(temp,"w:gz") as tf:
        for p in inputs:tf.add(p,arcname=p.as_posix(),recursive=False)
    temp.replace(tarpath)
    with tarfile.open(tarpath,"r:gz") as tf:
        archived=tf.getnames()
    assert archived==[p.as_posix() for p in inputs]
    assert all("private_rates" not in path and "ei2069" not in path.lower()
               for path in archived)
    saved["inventory"]["inputs"]=[
      {"path":p.as_posix(),"bytes":p.stat().st_size,"sha256":hash_file(p)}
      for p in inputs]
    saved["archives"]["inputs"]={
      "name":tarpath.name,"sha256":hash_file(tarpath),
      "bytes":tarpath.stat().st_size}
    # Preserve the public MCS-derived reference rate; original source private
    # rates for other ACTIVE reaction channels remain secret recovery inputs.
    m=mcs()
    source=CHEM/"private_rates"/m.EI2738_LOOKUP
    derived=res/m.SAFE_LOOKUP
    assert source.is_file() and not derived.exists()
    shutil.copyfile(source,derived)
    assert hash_file(derived)==hash_file(source)
    a=json.loads(audit_path(power).read_text())
    state=json.loads((res/"legacy6_latest_variant.json").read_text())
    for key,name in (("ei407","EI-407_O2_X.txt"),
                     ("ei417","EI-417_O2_X.txt"),
                     ("ei935","EI-935_O_3P.txt"),
                     ("ei941","EI-941_O_3P.txt"),
                     ("ei412","EI-412_O2_X.txt"),
                     ("ei401","EI-401_O2_X.txt"),
                     ("ei415","EI-415_O2_X.txt")):
        src=CHEM/"private_rates"/name
        assert src.is_file()
        assert state[key+"_lookup_sha256"]==hash_file(src),(key,name)
        saved[key+"_recovery_private_rate_required"]=name
        saved[key+"_recovery_rate_sha256"]=hash_file(src)
    for tag,file in (
       ("ei941_replaces_ei20_audit","ei941_replaces_ei20_audit.json"),
       ("ei412_replaces_dissg_audit","ei412_replaces_dissg_audit.json"),
       ("ei401_replaces_ei01_audit","ei401_replaces_ei01_audit.json"),
       ("ei415_replaces_ei16_audit","ei415_replaces_ei16_audit.json"),
    ):
        audit=json.loads((res/file).read_text())
        assert audit["scientific_acceptance"]=="HOLD"
        saved[tag]=audit
    saved.update({
       "variant":VARIANT,"chemistry_channels":active(),
       "no_ei2069_ablation_audit":a,
       "no_ei2069_argv_patch":json.loads(argv_audit_path(power).read_text()),
       "ei2069_recovery_private_rate_required":False,
       "ei2069_recovery_overlay_required":False,
       "ei2069_ablation":"FULLY_EXCLUDED_FROM_NATIVE_CHECK_AND_SOLVE_ARGV",
       "ei2069_scientific_status":"ABLATION_UNDER_TEST",
       "restart_requires_exact_legacy6_chemistry":False,
       "restart_requires_exact_13ch_no_ei2069_with_ei415_ei401_ei412_ei941":True,
       "ei2738_mcs_swap_audit":json.loads((res/m.AUDIT_NAME).read_text()),
       "ei2738_mcs_derived_rate_sha256":hash_file(derived),
       "ei2738_mcs_derived_rate_recovery_artifact":m.SAFE_LOOKUP,
       "ei2738_rate_origin":m.ORIGIN,
       "h23_recovery_k_m3_s":h23.K_M3_S,
       "h24_recovery_k_m3_s":h24.K_M3_S,
       "h25_recovery_k_m3_s_at_300K":h25.K_M3_S_AT_300K,
       "h23_scientific_status":"HOLD",
       "h24_scientific_status":"HOLD",
       "h25_scientific_status":"HOLD",
       "ei943_recovery_rate_required":False,
       "ei943_recovery_overlay_required":False,
       "ei943_scientific_status":"IMPACT_ABLATION_UNDER_TEST",
       "scientific_acceptance":"HOLD",
    })
    assert "ei2069_lookup_sha256" not in saved
    assert not any(x.startswith("ei2069_recovery_rate") for x in saved)
    assert "EI-2069" not in saved["chemistry_channels"]
    mpath.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("EI2069_13CH_ABLATION_NATIVE_100US_CHECKPOINT_PASS",power,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("self-test","prepare","verify","archive"))
    p.add_argument("--power-w",type=int,choices=(400,1000))
    args=p.parse_args()
    if args.action=="self-test":self_test()
    else:
        assert args.power_w in (400,1000)
        {"prepare":prepare,"verify":verify,"archive":archive}[args.action](args.power_w)
