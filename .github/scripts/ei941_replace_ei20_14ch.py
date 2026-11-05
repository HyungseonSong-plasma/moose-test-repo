#!/usr/bin/env python3
"""Original EI-941 replacement for EI-20 on 14ch H23/MCS2738/EI2069 research run.

Preserves pinned original physics, same RF, fresh 0-100us; scientific status HOLD.
No private reaction-rate table is checked in or included in archived inputs.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import tarfile
from pathlib import Path

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
RATE="EI-941_O_3P.txt"
VARIANT="H23_NO943_MCS2738_EI2069_EI941_IN_EI20_OUT_14CH_HOLD"
FLAG="OXYGEN_RESEARCH_EI941_SWAP"
AUDIT="ei941_replaces_ei20_audit.json"
ENERGY_EV=13.62

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def parent():
    return load(os.environ.get("EI2069","_legacy6_control/.github/scripts/ei2069_h23_no943_mcs2738_14ch.py"),"ei941_parent")

def mcs():
    return load(os.environ.get("MCS2738","_legacy6_control/.github/scripts/ei2738_mcs_h23_no_ei943_13ch.py"),"ei941_mcs")

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def digest_text(s):return hashlib.sha256(s.encode()).hexdigest()

def output(p):return CHEM/f"results_rf_elastic_diss_ion_ei20_ei01_{p}w_adjacent_sheath_wall_closed_100us_dt1000ns"

def old_overlay(p):return CHEM/f"o_ionization_ei20_{p}w_100us_dt1000ns_overlay.i"

def new_overlay(p):return CHEM/f"o_ionization_ei941_{p}w_100us_dt1000ns_overlay.i"

def original():return Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE

def private():return CHEM/"private_rates"/RATE

def replay():return CHEM/"issue397_l1_power_scan_replay.sh"

def audit(p):return output(p)/AUDIT

def active():
    before=parent().ACTIVE
    assert before.count("EI-20")==1 and "EI-941" not in before
    after=["EI-941" if i=="EI-20" else i for i in before]
    assert len(after)==14==len(set(after))
    assert "EI-943" not in after and "EI-20" not in after
    return after

def verify_overlay(s):
    required=[
       "type = PhysicsElectronImpactRateMaterial",
       "rate_table_file = 'private_rates/EI-941_O_3P.txt'",
       "target_molar_concentration = c_O_EI941",
       "reaction_progress = R_EI941",
       "expression = '-13.62*R'",
       "variable = log_ne","variable = log_nop",
       "variable = w_O","variable = log_energy",
       "property_name = S_electron_molar_EI941",
       "property_name = S_Op_molar_EI941",
       "property_name = S_O_mass_EI941",
    ]
    assert all(x in s for x in required),[x for x in required if x not in s]
    assert s.count("reaction_progress = R_EI941")==1
    assert "R_ion_O" not in s and "EI20" not in s and "ei20" not in s
    assert "o_ionization.txt" not in s

def render_overlay(source):
    assert source.count("rate_table_file = o_ionization.txt")==1
    assert source.count("reaction_progress = R_ion_O")==1
    assert source.count("13.618")==2
    s=source.replace("EI20","EI941").replace("ei20","ei941")
    s=s.replace("R_ion_O","R_EI941")
    s=s.replace("rate_table_file = o_ionization.txt",
                "rate_table_file = 'private_rates/EI-941_O_3P.txt'")
    s=s.replace("13.618","13.62")
    verify_overlay(s)
    return s

def old_ion_line():
    var=chr(36)+"{POWER_W}"
    dt=chr(36)+"{DT_NS}"
    return 'export ION_O="$CHEM/o_ionization_ei20_'+var+'w_100us_dt'+dt+'ns_overlay.i"'

def new_ion_line():return old_ion_line().replace("ei20","ei941")

def verify_replay(t):
    assert t.count(new_ion_line())==1 and old_ion_line() not in t
    assert t.count("'$ION_O'")==2, "both check and solve must use new ion overlay"
    assert t.count("'$EI2069_OVERLAY'")==2
    assert "'$EI943_OVERLAY'" not in t

def prepare(p):
    assert os.environ.get("OXYGEN_RESEARCH_EI2069_PLUS")=="1"
    assert os.environ.get("OXYGEN_RESEARCH_EI2738_MCS")=="1"
    par=parent();par.verify(p)
    j=json.loads((output(p)/"legacy6_latest_variant.json").read_text())
    assert j["chemistry_channels"]==par.ACTIVE
    rows=par.read_table(original())
    grid=mcs().parse_grid(output(p)/mcs().REFERENCE_GRID)
    assert len(rows)==len(grid)==100
    for (_,e),(energy,_) in zip(grid,rows):
        assert math.isclose(e,energy,rel_tol=1e-10,abs_tol=1e-10)
    assert not private().exists()
    shutil.copyfile(original(),private())
    assert digest(original())==digest(private())
    assert old_overlay(p).is_file() and not new_overlay(p).exists()
    new_overlay(p).write_text(render_overlay(old_overlay(p).read_text()))
    before=replay().read_text()
    assert before.count(old_ion_line())==1 and new_ion_line() not in before
    assert before.count("'$ION_O'")==2
    after=before.replace(old_ion_line(),new_ion_line())
    verify_replay(after);replay().write_text(after)
    audit2069=output(p)/"ei2069_addition_audit.json"
    a2069=json.loads(audit2069.read_text())
    assert a2069["native_14ch_replay_sha256"]==digest_text(before)
    a2069["native_14ch_replay_sha256"]=digest_text(after)
    audit2069.write_text(json.dumps(a2069,indent=2,sort_keys=True)+"\n")
    a={
       "power_W":p,"source_channel":"EI-20","replacement_channel":"EI-941",
       "mode":"EXCLUSIVE_REPLACEMENT","energy_loss_eV":ENERGY_EV,
       "reaction":"e + O(3P) -> O+ + 2e",
       "source_rate_filename":RATE,"source_rate_sha256":digest(original()),
       "source_rate_rows":100,"source_rate_units":"m3/(mol s)",
       "parent_14ch_replay_sha256":digest_text(before),
       "replaced_14ch_replay_sha256":digest_text(after),
       "original_ei20_overlay_sha256":digest(old_overlay(p)),
       "ei941_overlay_sha256":digest(new_overlay(p)),
       "original_channels":par.ACTIVE,"replacement_channels":active(),
       "mass_charge_atom_closure":"PASS","scientific_acceptance":"HOLD",
    }
    audit(p).write_text(json.dumps(a,indent=2,sort_keys=True)+"\n")
    os.environ[FLAG]="1"
    verify(p)
    print("EI941_REPLACES_EI20_PREPARE_PASS",p,flush=True)

def verify(p):
    assert os.environ.get(FLAG)=="1"
    par=parent();par.verify(p)
    j=json.loads((output(p)/"legacy6_latest_variant.json").read_text())
    assert j["chemistry_channels"]==par.ACTIVE
    a=json.loads(audit(p).read_text())
    assert a["replacement_channels"]==active()
    assert a["source_rate_sha256"]==digest(original())==digest(private())
    assert len(par.read_table(private()))==100
    assert digest(old_overlay(p))==a["original_ei20_overlay_sha256"]
    assert digest(new_overlay(p))==a["ei941_overlay_sha256"]
    verify_overlay(new_overlay(p).read_text())
    verify_replay(replay().read_text())
    assert digest(replay())==a["replaced_14ch_replay_sha256"]
    assert not (CHEM/"private_rates"/"EI-943_O_1D.txt").exists()
    print("EI941_REPLACES_EI20_VERIFIED",p,flush=True)

def archive(p):
    verify(p)
    par=parent()
    par.archive(p)  # 100us native CSV, Exodus and complete restart state verified here
    res=output(p)
    mpath=res/"legacy6_restart_100000ns_manifest.json"
    m=json.loads(mpath.read_text())
    assert m["verified_full_native_100us_checkpoint"]
    assert math.isclose(m["native_endpoint_s"],1e-4,rel_tol=0,abs_tol=1e-12)
    assert m["chemistry_channels"]==par.ACTIVE
    old=old_overlay(p).name
    excluded={old,"o_ionization.txt"}
    entries=m["inventory"]["inputs"]
    assert {Path(x["path"]).name for x in entries}.issuperset(excluded)
    inputs=[Path(x["path"]) for x in entries if Path(x["path"]).name not in excluded]
    inputs.append(new_overlay(p))
    assert len(inputs)==len(set(inputs))
    assert all(x.is_file() and not x.is_symlink() and "private_rates" not in x.as_posix() for x in inputs)
    archive=res/m["archives"]["inputs"]["name"]
    temp=Path(str(archive)+".tmp")
    with tarfile.open(temp,"w:gz") as tf:
        for f in inputs:tf.add(f,arcname=f.as_posix(),recursive=False)
    temp.replace(archive)
    with tarfile.open(archive,"r:gz") as tf:
        names=tf.getnames()
    assert names==[i.as_posix() for i in inputs]
    assert not any(Path(x).name in excluded for x in names)
    a=json.loads(audit(p).read_text())
    m["inventory"]["inputs"]=[{"path":v.as_posix(),"bytes":v.stat().st_size,
                              "sha256":digest(v)} for v in inputs]
    m["archives"]["inputs"]={"name":archive.name,"sha256":digest(archive),
                              "bytes":archive.stat().st_size}
    m.update({"variant":VARIANT,"chemistry_channels":active(),
              "ei941_replaces_ei20_audit":a,
              "ei941_recovery_private_rate_required":RATE,
              "ei941_recovery_private_rate_sha256":digest(private()),
              "ei941_energy_loss_eV":ENERGY_EV,
              "ei20_replaced_not_parallel":True,
              "restart_requires_exact_ei941_in_ei20_out":True,
              "scientific_acceptance":"HOLD"})
    mpath.write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    variant=res/"legacy6_latest_variant.json"
    j=json.loads(variant.read_text())
    j.update({"variant":VARIANT,"chemistry_channels":active(),
              "ei941_lookup_filename":RATE,"ei941_lookup_sha256":digest(private()),
              "ei941_replaced_ei20":True,"scientific_acceptance":"HOLD"})
    variant.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    assert "EI-20" not in m["chemistry_channels"]
    assert "EI-941" in m["chemistry_channels"]
    print("EI941_REPLACES_EI20_NATIVE_100US_PASS",p,flush=True)

def self_test():
    delta={"e":1,"O":-1,"Op":1}
    atoms={"e":0,"O":1,"Op":1}
    charge={"e":-1,"O":0,"Op":1}
    mass={"e":0,"O":0.016,"Op":0.016}
    assert sum(delta[x]*atoms[x] for x in delta)==0
    assert sum(delta[x]*charge[x] for x in delta)==0
    assert abs(sum(delta[x]*mass[x] for x in delta))<1e-14
    assert "ei20" in old_ion_line() and "ei941" in new_ion_line()
    assert ENERGY_EV==13.62
    print("EI941_REPLACES_EI20_SELF_TEST_PASS",flush=True)

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("action",choices=("self-test","prepare","verify","archive"))
    cli.add_argument("--power-w",type=int)
    args=cli.parse_args()
    if args.action=="self-test": self_test()
    else:
        assert args.power_w in (400,1000)
        {"prepare":prepare,"verify":verify,"archive":archive}[args.action](args.power_w)
