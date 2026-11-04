#!/usr/bin/env python3
"""Controlled ablation: retain exact 13-channel reference except EI-943 disabled.

Original, pinned Physics source is never modified in Git.
Prepare the audited parent 13-channel case first, use its existing complete
H25 replay-injection method, then remove the entire EI943 overlay from BOTH
check-input and solve argv. No zero-rate stand-in and no EI943 energy kernel.
Preserve identical 400/1000 W operation, inlet, EEDF, and 100us target.
SCIENCE_HOLD; A/B against 13-channel Run 41804294918.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
EXPECTED=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20","EI-2738",
          "EI-407","EI-417","EI-935","H24","H25"]
EXCLUDED={"EI-943","EI-2259","EI-2058","H05","EI-2072","EI-2074"}
VARIANT="LEGACY8_EI417_EI935_H24_H25_NO_EI943_IMPACT_ABLATION_HOLD"
SOURCE_SHA="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
TRANSPORT_SHA="35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
BASELINE_SHA="722979bda5620befbdb50060706c3d8fdce8a711"
RATE_MAP={"ei407":"EI-407_O2_X.txt","ei417":"EI-417_O2_X.txt",
          "ei935":"EI-935_O_3P.txt"}
ARGV_OVERLAYS=["EI-2738","EI-407","EI-417","EI-935","H24","H25"]
TOKENS=("$EI407_OVERLAY","$EI417_OVERLAY","$EI935_OVERLAY","$H24_OVERLAY","$H25_OVERLAY")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_h25():
    path=Path(os.environ.get("H25","_legacy6_control/.github/scripts/oxygen_legacy8_ei417_ei935_ei943_h24_h25_noei2259_noei2058_100us.py"))
    spec=importlib.util.spec_from_file_location("parent_h25_for_ablation",path)
    if not spec or not spec.loader: raise FileNotFoundError(path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def modules():
    h25=load_h25()
    h24=h25.load_parent()
    ei943=h24.load_parent()
    ei935=ei943.load_parent()
    b8=ei935.l8()
    l7=b8.l7()
    base=l7.legacy6()
    return h25,h24,ei943,ei935,b8,l7,base


def outcome(base,power):
    assert power in (400,1000)
    return base.result(power)


def replay():
    return CHEM/"issue397_l1_power_scan_replay.sh"


def audit_file(result):
    return result/"no_ei943_ablation_audit.json"


def argv_audit_file(result):
    return result/"no_ei943_argv_patch.json"


def assert_flags():
    assert os.environ["OXYGEN_RESEARCH_EI2738_FORMULA"]=="1"
    assert os.environ["OXYGEN_RESEARCH_FULL24"]=="0"
    assert os.environ["OXYGEN_RESEARCH_LUMPED_O2A"]=="0"


def verify_active_files(power,h25,h24,ei935,b8,l7,base):
    """Real 12ch source inputs must be the expected original 13ch parents minus EI943."""
    base.check_input(power)
    l7.validate_overlay(l7.overlay_path(base,power).read_text())
    b8.overlay_ok(b8.overlay(power).read_text())
    assert ei935.f417(power).read_text()==ei935.c417()
    ei935.validate_935(ei935.f935(power).read_text())
    h24.validate(h24.overlay(power).read_text())
    h25.validate(h25.overlay(power).read_text())
    for p in (l7.overlay_path(base,power),b8.overlay(power),
              ei935.f417(power),ei935.f935(power),
              h24.overlay(power),h25.overlay(power)):
        assert "R_EI943" not in p.read_text(), f"EI943 contaminates {p}"
    assert not (CHEM/f"ei943_atomic_superelastic_{power}w_100us_dt1000ns_overlay.i").exists()
    assert not (CHEM/"private_rates"/"EI-943_O_1D.txt").exists()


def assert_script():
    txt=replay().read_text()
    assert "'$EI943_OVERLAY'" not in txt
    assert "$EI943_OVERLAY" not in txt
    for overlay in TOKENS:
        assert txt.count("'"+overlay+"'")==2, f"missing/duplicate injected overlay {overlay}"
    assert txt.count(chr(36)+"{EI2738_EXTRA_INPUT}")==2, "EI2738 original formula incorrectly removed"
    assert "Outputs/file_base='$RESULT/run/plasma'" in txt
    assert "$EI2058_OVERLAY" not in txt and "$EI2259_OVERLAY" not in txt
    return sha(replay())


def self_test():
    assert len(EXPECTED)==12 and len(set(EXPECTED))==12
    assert len(set(ARGV_OVERLAYS))==6 and "EI-943" not in ARGV_OVERLAYS
    assert "EI-943" not in EXPECTED
    assert len(EXCLUDED)==6
    assert SOURCE_SHA=="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
    print("OXYGEN_NO_EI943_12CH_ABLATION_SELF_TEST_PASS",flush=True)


def prepare(power):
    self_test()
    assert_flags()
    h25,h24,ei943,ei935,b8,l7,base=modules()
    # The parent is the source-verified, already prepared exact 13ch input.
    h25.verify(power)
    res=outcome(base,power)
    parent=json.loads((res/"legacy6_latest_variant.json").read_text())
    assert parent["chemistry_channels"]==EXPECTED[:10]+["EI-943","H24","H25"]
    assert parent["variant"]==h25.VARIANT
    assert parent["physics_source_sha"]==SOURCE_SHA
    assert parent["transport_table_sha256"]==TRANSPORT_SHA
    assert parent["scientific_acceptance"]=="HOLD"
    parent_sha=sha(res/"legacy6_latest_variant.json")
    ei943_path=ei943.overlay(power)
    assert ei943_path.read_text()==ei943.CONTENT
    assert ei943_path.exists()
    ei943_rate=CHEM/"private_rates"/ei943.RATE
    assert ei943_rate.exists() and sha(ei943_rate)==parent["ei943_lookup_sha256"]
    original_ei943_overlay_sha=sha(ei943_path)
    original_ei943_rate_sha=sha(ei943_rate)
    original_other_rates={}
    for k,name in RATE_MAP.items():
        p=CHEM/"private_rates"/name
        assert p.exists()
        assert sha(p)==parent[k+"_lookup_sha256"], "original other rate differs"
        original_other_rates[k]=sha(p)
    # Reuse exact parent checked argv injection, THEN remove EI943 *only*.
    h25.patch(power)  # must run BEFORE modifying any 13ch provenance.
    source=replay().read_text()
    assert source.count(" '$EI943_OVERLAY'")==2
    patched=source.replace(" '$EI943_OVERLAY'","")
    assert patched.count(" '$EI943_OVERLAY'")==0
    assert patched!=source
    replay().write_text(patched)
    patched_sha=assert_script()
    old_argv=res/"h25_argv_patch.json"
    old_argv_json=json.loads(old_argv.read_text())
    assert old_argv_json["overlays"]==ARGV_OVERLAYS[:4]+["EI-943"]+ARGV_OVERLAYS[4:]
    original_argv_sha=sha(old_argv)
    old_argv.unlink()  # never archive an audit that incorrectly claims EI943 is active.
    argv_audit={
        "power_W":power,"source_13ch_patch_sha256":sha_bytes(source.encode()),
        "patched_12ch_argv_sha256":patched_sha,
        "source_parent_argv_audit_sha256":original_argv_sha,
        "overlays":ARGV_OVERLAYS,"excluded":sorted(EXCLUDED),
        "intentionally_omitted_overlay":"EI-943",
        "scientific_acceptance":"HOLD",
        "native_initialization":"fresh_not_restarted",
    }
    argv_audit_file(res).write_text(json.dumps(argv_audit,indent=2,sort_keys=True)+"\n")
    # Remove the actual reaction, its energy and species source kernels, and
    # the *working-copy* private lookup. Original secret bundle is unchanged.
    ei943_path.unlink()
    ei943_rate.unlink()
    assert not ei943_path.exists() and not ei943_rate.exists()
    # EI943 is not active: don't leave metadata that claims active rate ownership.
    parent={k:v for k,v in parent.items() if not k.startswith("ei943_")}
    parent.update({
        "variant":VARIANT,
        "chemistry_channels":EXPECTED,
        "hold_excluded":sorted(EXCLUDED),
        "scientific_acceptance":"HOLD",
        "ei943_ablation":"FULLY_EXCLUDED_FROM_CHECK_AND_SOLVE_ARGV_NOT_ZERO_RATE",
        "ei943_ablation_parent_baseline_run_id":41804294918,
        "ei943_ablation_parent_baseline_sha":BASELINE_SHA,
        "ei943_ablation_parent_manifest_sha256":parent_sha,
        "ei943_ablation_parent_overlay_sha256":original_ei943_overlay_sha,
        "ei943_ablation_parent_private_rate_sha256":original_ei943_rate_sha,
        "ei943_ablation_argv_sha256":patched_sha,
        "ei943_ablation_effect_assessment":"unmeasured_await_native_100us_A_B",
    })
    manifest_path=res/"legacy6_latest_variant.json"
    manifest_path.write_text(json.dumps(parent,indent=2,sort_keys=True)+"\n")
    audit={
        "power_W":power,
        "experiment":"12ch_EI943_ablated_400W_1000W_100us",
        "reference_run_id":41804294918,
        "reference_sha":BASELINE_SHA,
        "pinned_physics_sha":SOURCE_SHA,
        "transport_table_sha256":TRANSPORT_SHA,
        "active_chemistry_channels":EXPECTED,
        "excluded_channels":sorted(EXCLUDED),
        "ei943_overlay_removed":True,
        "ei943_lookup_removed_from_working_copy":True,
        "ei943_source_particle_and_energy_terms_absent":True,
        "other_original_rate_sha256":original_other_rates,
        "exact_argv_sha256":patched_sha,
        "scientific_acceptance":"HOLD",
    }
    audit_file(res).write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("OXYGEN_NO_EI943_12CH_P0_ABLATION_PASS",power,flush=True)


def sha_bytes(s):
    return hashlib.sha256(s).hexdigest()


def verify(power):
    assert_flags()
    h25,h24,ei943,ei935,b8,l7,base=modules()
    res=outcome(base,power)
    j=json.loads((res/"legacy6_latest_variant.json").read_text())
    audit=json.loads(audit_file(res).read_text())
    argv=json.loads(argv_audit_file(res).read_text())
    assert j["variant"]==VARIANT
    assert j["chemistry_channels"]==EXPECTED
    assert not EXCLUDED.intersection(j["chemistry_channels"])
    assert j["physics_source_sha"]==SOURCE_SHA
    assert j["transport_table_sha256"]==TRANSPORT_SHA
    assert j["scientific_acceptance"]=="HOLD"
    assert j["native_initialization"]=="fresh_not_restarted"
    assert j["neutral_inlet_sccm"]==200 and j["power_W"]==power
    assert j["ei935_energy_loss_eV"]==1.967
    assert j["h24_k_m3_s"]==1e-13
    assert j["h25_k_m3_s_at_300K"]==2e-17
    assert j["h25_tgas_K"]==300
    assert j["ei943_ablation"]=="FULLY_EXCLUDED_FROM_CHECK_AND_SOLVE_ARGV_NOT_ZERO_RATE"
    assert not any(k in j for k in ("ei943_lookup_sha256","ei943_rate_mode","ei943_rate_source"))
    assert audit["active_chemistry_channels"]==EXPECTED
    assert argv["overlays"]==ARGV_OVERLAYS
    assert argv["excluded"]==sorted(EXCLUDED)
    assert audit["exact_argv_sha256"]==j["ei943_ablation_argv_sha256"]==argv["patched_12ch_argv_sha256"]==assert_script()
    assert audit["transport_table_sha256"]==TRANSPORT_SHA
    assert (res/"h25_argv_patch.json").exists() is False
    verify_active_files(power,h25,h24,ei935,b8,l7,base)
    for k,name in RATE_MAP.items():
        active=CHEM/"private_rates"/name
        src=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/name
        assert sha(active)==sha(src)==audit["other_original_rate_sha256"][k]==j[k+"_lookup_sha256"]
    assert "EI-943" not in audit["active_chemistry_channels"]
    print("OXYGEN_NO_EI943_12CH_EXACT_INPUTS_AND_AVG_PROVENANCE_PASS",power,flush=True)


def archive(power):
    verify(power)
    h25,h24,ei943,ei935,b8,l7,base=modules()
    res=outcome(base,power)
    files=(l7.overlay_path(base,power),b8.overlay(power),ei935.f417(power),
           ei935.f935(power),h24.overlay(power),h25.overlay(power))
    assert len(files)==6 and len({p.name for p in files})==6
    assert all("943" not in p.name and p.exists() for p in files)
    base.PERSIST=tuple(base.PERSIST)+tuple(p.name for p in files)
    base.verify_and_archive(power)
    manifest=res/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(manifest.read_text())
    assert saved["verified_full_native_100us_checkpoint"]
    assert saved["native_endpoint_s"]==1e-4
    assert saved["variant"]==VARIANT
    assert saved["chemistry_channels"]==EXPECTED
    assert saved["scientific_acceptance"]=="HOLD"
    inventory=[x["path"] for x in saved["inventory"]["inputs"]]
    assert all(any(p.endswith("/"+file.name) for p in inventory) for file in files)
    assert all("ei943" not in s.lower() and "private_rates" not in s for s in inventory)
    assert not EXCLUDED.intersection(saved["chemistry_channels"])
    saved.update({
        "restart_requires_exact_legacy6_chemistry":False,
        "restart_requires_exact_12ch_no_ei943_h24_h25_chemistry":True,
        "h24_recovery_k_m3_s":h24.K_M3_S,
        "h25_recovery_k_m3_s_at_300K":h25.K_M3_S_AT_300K,
        "h24_scientific_status":"HOLD","h25_scientific_status":"HOLD",
        "ei943_recovery_rate_required":False,
        "ei943_recovery_overlay_required":False,
        "ei943_scientific_status":"IMPACT_ABLATION_UNDER_TEST",
        "no_ei943_ablation_audit":json.loads(audit_file(res).read_text()),
    })
    j=json.loads((res/"legacy6_latest_variant.json").read_text())
    for key,name in RATE_MAP.items():
        saved[key+"_recovery_private_rate_required"]=name
        saved[key+"_recovery_rate_sha256"]=j[key+"_lookup_sha256"]
    manifest.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("OXYGEN_NO_EI943_12CH_NATIVE_100US_CHECKPOINT_PASS",power,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["self-test","prepare","verify","archive"])
    p.add_argument("--power-w",type=int)
    args=p.parse_args()
    if args.action=="self-test": self_test()
    else:
        assert args.power_w in (400,1000)
        {"prepare":prepare,"verify":verify,"archive":archive}[args.action](args.power_w)
