#!/usr/bin/env python3
"""Legacy8 + H05 + EI417 + EI2072 + EI2074: run-ready, not dispatched, science HOLD."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

ROOT = Path("experiments/Issue395_powered_chemistry_ladder")
TABLE = "EI-2074_O2_a1Delta.txt"
CHANNEL = "EI-2074"
ENERGY_LOSS_EV = 16.023
PARENT_CHANNELS = ("EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20",
                   "EI-2738","EI-407","H05","EI-417","EI-2072")
TWELVE = list(PARENT_CHANNELS) + [CHANNEL]
SOURCE = Path(os.environ.get(
    "EI2074_SOURCE", "_legacy6_control/.github/oxygen25_ei2074/ei2074_only_overlay.i"))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def parent_module():
    source = Path(os.environ.get(
        "EI2072", "_legacy6_control/.github/scripts/oxygen_legacy8_h05_ei417_ei2072_100us.py"))
    spec = importlib.util.spec_from_file_location("ei2072_control_for_ei2074", source)
    if spec is None or spec.loader is None:
        raise ValueError("EI2072 parent script missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def overlay(power):
    if power not in (400, 1000):
        raise ValueError("unsupported RF power")
    return ROOT / f"ei2074_o2a_dissociative_ionization_{power}w_100us_dt1000ns_overlay.i"

def rate():
    return ROOT / "private_rates" / TABLE

def overlay_ok(src):
    required = (
        "rate_table_file = 'private_rates/EI-2074_O2_a1Delta.txt'",
        "reaction_progress = R_EI2074",
        "electron_number_density = n_e_physical",
        "target_molar_concentration = c_O2a_EI2074",
        "functor_names = 'rho_neutral w_O2s'",
        "expression = '-0.032*R'",
        "expression = '0.016*R'",
        "expression = '-0.016*R'",
        "expression = '-16.023*R'",
        "functor = S_e_molar_EI2074",
        "functor = S_energy_EI2074",
        "source = S_O2a_mass_EI2074",
        "source = S_O_mass_EI2074",
        "v = S_Op_molar_EI2074",
        "v = S_neutral_mass_EI2074",
        "expression = 'a+b+c'",
        "expression = 'a+b-c'",
        "expression = 'ion-el'",
    )
    if any(x not in src for x in required):
        raise ValueError("EI2074 missing reaction/source/energy/closure fields")
    if src.count("reaction_progress = R_EI2074") != 1:
        raise ValueError("EI2074 progress must have exactly one owner")
    if src.count("functor_on_rhs = true") != 2:
        raise ValueError("electron and electron-energy kernels must be unique")
    variables = [x.strip() for x in src.splitlines() if x.strip().startswith("variable = ")]
    if sorted(variables) != sorted([
        "variable = log_ne", "variable = log_energy",
        "variable = w_O2s", "variable = w_O",
        "variable = log_nop", "variable = p"
    ]):
        raise ValueError("EI2074 added/lost a solver variable")
    for bad in (
        "reaction_progress = R_EI2072",
        "reaction_progress = R_EI417",
        "reaction_progress = R_EI2067",
        "functor_symbols = 'e ",
    ):
        if bad in src:
            raise ValueError("EI2074 attempted to change inherited chemistry")
    return True

def verify(power):
    parent = parent_module()
    ei417 = parent.ei417()
    h05 = ei417.h05()
    l8 = h05.load_legacy8()
    l7 = l8.l7()
    m = l7.legacy6()
    if (os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA") != "1" or
        os.environ.get("OXYGEN_RESEARCH_FULL24") != "0" or
        os.environ.get("OXYGEN_RESEARCH_LUMPED_O2A") != "0"):
        raise ValueError("incompatible legacy control flags")
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    l8.overlay_ok(l8.overlay(power).read_text())
    h05.overlay_ok(h05.overlay(power).read_text())
    ei417.overlay_ok(ei417.overlay(power).read_text())
    parent.overlay_ok(parent.overlay(power).read_text())
    overlay_ok(overlay(power).read_text())
    h05.reference_ok()
    for table in (l8.rate(), ei417.private_table(), parent.private_table(), rate()):
        l8.table_ok(table)
    saved = json.loads((m.result(power)/"legacy6_latest_variant.json").read_text())
    if (saved.get("variant") != "LEGACY8_H05_EI417_EI2072_EI2074_from_EI2072" or
        saved.get("chemistry_channels") != TWELVE or
        saved.get("ei407_lookup_sha256") != digest(l8.rate()) or
        saved.get("ei417_lookup_sha256") != digest(ei417.private_table()) or
        saved.get("ei2072_lookup_sha256") != digest(parent.private_table()) or
        saved.get("ei2074_lookup_sha256") != digest(rate()) or
        saved.get("ei2074_energy_loss_eV") != ENERGY_LOSS_EV or
        saved.get("h05_rate_particle_m3_s") != h05.A_PARTICLE or
        saved.get("h05_electron_energy_source") != "none_unresolved" or
        saved.get("scientific_acceptance") != "HOLD" or
        saved.get("native_initialization") != "fresh_not_restarted" or
        saved.get("physics_source_sha") != m.RECIPE_SHA):
        raise ValueError("EI2074 12-channel provenance incorrect")
    print("LEGACY8_H05_EI417_EI2072_EI2074_P0_PASS", power)
    return parent,ei417,h05,l8,l7,m,saved

def prepare(power):
    parent = parent_module()
    parent.prepare(power)
    l8 = parent.ei417().h05().load_legacy8()
    source = Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/TABLE
    private_sha = l8.table_ok(source)
    dest = rate()
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and digest(dest) != private_sha:
        raise ValueError("EI2074 private rate checksum conflict")
    shutil.copyfile(source,dest)
    overlay_ok(SOURCE.read_text())
    if overlay(power).exists():
        raise ValueError("EI2074 overlay already exists")
    shutil.copyfile(SOURCE,overlay(power))
    m = l8.l7().legacy6()
    manifest = m.result(power)/"legacy6_latest_variant.json"
    record = json.loads(manifest.read_text())
    if record.get("chemistry_channels") != list(PARENT_CHANNELS):
        raise ValueError("EI2072 parent must contain exactly eleven channels")
    record.update({
        "variant":"LEGACY8_H05_EI417_EI2072_EI2074_from_EI2072",
        "chemistry_channels":TWELVE,
        "ei2074_reaction":"e + O2(a1Delta) -> O+ + O + 2e",
        "ei2074_target_species":"O2s",
        "ei2074_lookup_filename":TABLE,
        "ei2074_lookup_sha256":private_sha,
        "ei2074_energy_loss_eV":ENERGY_LOSS_EV,
        "ei2074_electron_source_per_event":1,
        "ei2074_lookup_origin":"HPEM O2ex.dat Process 18, not independently measured/validated",
        "scientific_acceptance":"HOLD",
    })
    manifest.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("LEGACY8_H05_EI417_EI2072_EI2074_PREPARED",power)

def patch(power):
    parent,ei417,h05,l8,l7,m,record = verify(power)
    path = m.CHEM/"issue397_l1_power_scan_replay.sh"
    before = path.read_text()
    check_old = ei417.CHECK_OLD
    solve_old = ei417.SOLVE_OLD
    check_new = ei417.CHECK_NEW + " '$EI2072_OVERLAY' '$EI2074_OVERLAY'"
    solve_new = ei417.SOLVE_NEW.replace(
        " Outputs/file_base="," '$EI2072_OVERLAY' '$EI2074_OVERLAY' Outputs/file_base=")
    if (before.count(check_old)!=1 or before.count(solve_old)!=1 or
        any(x in before for x in ("'$EI407_OVERLAY'","'$H05_OVERLAY'",
            "'$EI417_OVERLAY'","'$EI2072_OVERLAY'","'$EI2074_OVERLAY'"))):
        raise ValueError("pinned replay changed; refuse unguarded mutation")
    after = before.replace(check_old,check_new,1).replace(solve_old,solve_new,1)
    if after.count(check_new)!=1 or after.count(solve_new)!=1:
        raise ValueError("EI2074 argv injection failed")
    path.write_text(after)
    (m.result(power)/"legacy8_h05_ei417_ei2072_ei2074_argv_patch.json").write_text(
        json.dumps({
            "power_W":power,
            "original_sha256":hashlib.sha256(before.encode()).hexdigest(),
            "new_sha256":hashlib.sha256(after.encode()).hexdigest(),
            "new_channel":CHANNEL,
            "private_lookup_sha256":record["ei2074_lookup_sha256"],
            "scientific_acceptance":"HOLD"
        },indent=2)+"\n")
    print("LEGACY8_H05_EI417_EI2072_EI2074_ARGV_PASS",power)

def archive(power):
    parent,ei417,h05,l8,l7,m,record = verify(power)
    covers = (l7.overlay_path(m,power),l8.overlay(power),h05.overlay(power),
              ei417.overlay(power),parent.overlay(power),overlay(power))
    m.PERSIST = tuple(m.PERSIST)+tuple(p.name for p in covers)
    m.verify_and_archive(power)
    path = m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved = json.loads(path.read_text())
    if (saved["native_endpoint_s"]!=1e-4 or
        not saved["verified_full_native_100us_checkpoint"] or
        saved["chemistry_channels"]!=TWELVE or
        saved["scientific_acceptance"]!="HOLD"):
        raise ValueError("EI2074 full 100us checkpoint not verified")
    files = [x["path"] for x in saved["inventory"]["inputs"]]
    for p in covers:
        if not any(x.endswith("/"+p.name) for x in files):
            raise ValueError("missing replay overlay in native restart inventory")
    if any("private_rates" in x for x in files):
        raise ValueError("private rate included in public artifact")
    saved.update({
        "restart_requires_exact_legacy6_chemistry":False,
        "restart_requires_exact_legacy8_h05_ei417_ei2072_ei2074_chemistry":True,
        "h05_energy_incomplete":True,
    })
    for id,file in (("407",l8.RATE),("417",ei417.TABLE),
                    ("2072",parent.TABLE),("2074",TABLE)):
        saved["ei"+id+"_recovery_private_rate_required"]=file
        saved["ei"+id+"_recovery_rate_sha256"]=record["ei"+id+"_lookup_sha256"]
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("LEGACY8_H05_EI417_EI2072_EI2074_NATIVE_100US_PASS",power)

def self_test():
    assert len(TWELVE)==12 and len(set(TWELVE))==12
    assert TWELVE[-2:]==["EI-2072","EI-2074"]
    assert abs(-0.032+0.016+0.016)<1e-14
    assert abs(-0.032+0.016-(-0.016))<1e-14
    assert abs(1-1)<1e-14
    src=SOURCE.read_text()
    overlay_ok(src)
    for bad in (
        src.replace("reaction_progress = R_EI2074","reaction_progress = R_BAD"),
        src.replace("variable = log_nop","variable = log_ni"),
        src.replace("variable = w_O\n","variable = w_Os\n"),
        src.replace("expression = 'ion-el'","expression = 'ion+el'"),
    ):
        try:
            overlay_ok(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("EI2074 mutation must fail")
    print("LEGACY8_H05_EI417_EI2072_EI2074_SELFTEST_PASS")

def main():
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    for opt in ("self-test","prepare-variant","verify-twelve",
                "patch-replay-argv","verify-and-archive"):
        g.add_argument("--"+opt,action="store_true")
    p.add_argument("--power-w",type=int,choices=(400,1000))
    a=p.parse_args()
    if a.self_test: self_test()
    elif a.power_w is None:p.error("--power-w required")
    elif a.prepare_variant: prepare(a.power_w)
    elif a.verify_twelve: verify(a.power_w)
    elif a.patch_replay_argv: patch(a.power_w)
    else: archive(a.power_w)

if __name__=="__main__":
    main()
