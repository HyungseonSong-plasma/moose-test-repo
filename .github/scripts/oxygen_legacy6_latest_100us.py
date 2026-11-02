#!/usr/bin/env python3
"""Research-only Oxygen ICP legacy six-channel chemistry with latest EEDF/inlet.

No full24/Oxygen25 species source overlay. Compatible with the pinned native
Issue397 replay. The first run is fresh, NEVER a 25-reaction restart.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import tarfile
from decimal import Decimal
from pathlib import Path

CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
TABLE = Path("experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt")
EEDF_SHA256 = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
RECIPE_SHA = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
COMPONENTS = {
    "EI-01": "o2_attachment_ei01_{p}w_100us_dt1000ns_overlay.i",
    "EI-02": "o2_elastic_{p}w_100us_dt1000ns_overlay.i",
    "DISS-G": "o2_dissociation_{p}w_100us_dt1000ns_overlay.i",
    "EI-16": "o2_ionization_{p}w_100us_dt1000ns_overlay.i",
    "EI-17": "o_elastic_ei17_{p}w_100us_dt1000ns_overlay.i",
    "EI-20": "o_ionization_ei20_{p}w_100us_dt1000ns_overlay.i",
}
PERSIST = (
    "a0_full_icp.i",
    "baseline_plasma_plus_unstructured_cover_plus_wafer.msh",
    "issue397_maxwell_steady_abs1e11.i",
    "o2_elastic.txt", "o_elastic.txt",
    "o2_ionization.txt", "o_ionization.txt", "o2_attachment.txt",
    "electron_transport_initial_eedf.txt",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def result(power: int) -> Path:
    assert power in (400, 1000)
    return CHEM / ("results_rf_elastic_diss_ion_ei20_ei01_"
                   f"{power}w_adjacent_sheath_wall_closed_100us_dt1000ns")


def input_path(power: int) -> Path:
    return CHEM / ("rf_elastic_diss_ion_ei20_ei01_"
                   f"{power}w_adjacent_sheath_wall_closed_100us_dt1000ns.i")


def expected_grid_ns():
    grid = list(range(101))
    grid += list(range(110,2001,10))
    grid += list(range(2100,10001,100))
    grid += list(range(11000,100001,1000))
    assert len(grid)==461 and grid[-1]==100000
    return grid


def check_input(power: int):
    src=input_path(power).read_text()
    from_re = re.search(r"(?m)^\s*time_sequence\s*=\s*'([^']+)'", src)
    if from_re is None:
        raise ValueError("TimeSequenceStepper time_sequence missing")
    time_ns = [float(s)*1e9 for s in from_re.group(1).split()]
    target = expected_grid_ns()
    if len(time_ns)!=len(target) or any(abs(a-b)>1e-5 for a,b in zip(time_ns,target)):
        raise ValueError("100us exact 460-segment time grid changed")
    if not re.search(r"(?m)^\s*end_time\s*=\s*(?:0\.0001|1(?:\.0+)?e-?4)\s*$",src):
        raise ValueError("100us final time changed")
    if not re.search(r"(?m)^\s*checkpoint\s*=\s*true\s*$",src):
        raise ValueError("Native checkpoint output missing")
    if ("[Problem]" in src or "restart_file_base" in src or
        "full24_" in src or "R_EI415" in src or "chem24_rate_415" in src):
        raise ValueError("Legacy6 fresh input contaminated by Oxygen25/restart")
    # These are the exact latest neutral and charged seed policies.
    import importlib.util
    seed_file=CHEM/"apply_oxygen_24_initial_seeds.py"
    spec=importlib.util.spec_from_file_location("legacy6_seeds",seed_file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify_charged(src)
    module.verify_neutrals(src)
    config=json.loads((CHEM/"oxygen_icp_operating_200sccm_sticking1.json").read_text())
    if (config["inlet"]["Q_sccm"]!=200 or
        config["inlet"]["mole_fractions"]!={"O2_X":.99997,"O2_a1Delta":1e-5,"O_3P":1e-5,"O_1D":1e-5}):
        raise ValueError("current 200sccm inlet configuration changed")
    wall_file=CHEM/"build_oxygen_24_wall_overlay.py"
    wspec=importlib.util.spec_from_file_location("legacy6_wall",wall_file)
    wall=importlib.util.module_from_spec(wspec);wspec.loader.exec_module(wall)
    wall.inspect(src)
    if not all(x in src for x in ("stageb4_O_surface_loss",
                                  "stageb4_O2s_surface_loss",
                                  "stageb4_Os_surface_loss")):
        raise ValueError("latest wall chemistry incomplete")
    if sha(TABLE)!=EEDF_SHA256 or sha(CHEM/"electron_transport_initial_eedf.txt")!=EEDF_SHA256:
        raise ValueError("new EEDF transport lookup differs from 23xsec reference")
    require = {
        "EI-01":["reaction_progress = R_attachment","variable = log_nm","variable = log_ne"],
        "EI-02":["reaction_progress = R_elastic_O2"],
        "DISS-G":["property_name = R_diss_O2","1.41e-15","-0.22"],
        "EI-16":["reaction_progress = R_ion_O2"],
        "EI-17":["reaction_progress = R_elastic_O"],
        "EI-20":["reaction_progress = R_ion_O"],
    }
    for key,name in COMPONENTS.items():
        p=CHEM/name.format(p=power)
        text=p.read_text()
        for fragment in require[key]:
            if fragment not in text:
                raise ValueError(f"Bad/missing {key} chemistry fragment: {fragment}")
    if any((CHEM/f"full24_{power}w_100us_dt1000ns_overlay.i").exists() for _ in (0,)):
        raise ValueError("Oxygen25 overlay unexpectedly present")
    print("OXYGEN_LEGACY6_LATEST_100US_INPUT_P0_PASS",power)


def apply_latest_after_prepare(power: int):
    """Run AFTER legacy prepare; before physical build & solver input check."""
    path = input_path(power)
    old = path.read_text()
    if "checkpoint = true" in old:
        raise ValueError("prepared input already has checkpoint")
    if "restart_file_base" in old:
        raise ValueError("must initialize new chemistry without checkpoint recovery")
    import subprocess,sys
    def transform(script: str, suffix: str):
        tmp=path.with_suffix(f".{suffix}.tmp")
        subprocess.run([sys.executable,str(CHEM/script),
                        "--base-input",str(path),"--output",str(tmp)],check=True)
        tmp.replace(path)
    transform("build_oxygen_icp_200sccm_inlet.py","inlet")
    transform("apply_oxygen_24_initial_seeds.py","seed")
    transform("build_oxygen_24_wall_overlay.py","wall")
    src=path.read_text()
    matches=list(re.finditer(r"(?m)^\[Outputs\]\s*$",src))
    if len(matches)!=1:
        raise ValueError("expected one output section")
    head=matches[0]
    src=src[:head.end()]+"\n  checkpoint = true"+src[head.end():]
    path.write_text(src)
    shutil.copyfile(TABLE,CHEM/"electron_transport_initial_eedf.txt")
    check_input(power)
    r=result(power)
    r.mkdir(parents=True,exist_ok=True)
    provenance={
        "schema":1,"variant":"LEGACY6_with_latest_Oxygen25_operating_settings",
        "power_W":power,"end_time_us":100,
        "physics_source_sha":RECIPE_SHA,
        "transport_kind":"initial_neutral_23xsec_EEDF",
        "transport_table_sha256":EEDF_SHA256,
        "chemistry_channels":list(COMPONENTS),
        "rate_origin":"original public 100-point EI lookup + original DISS-G formula",
        "neutral_inlet_sccm":200,
        "neutral_initial_mole_fractions":{"O2":.99997,"O2a":1e-5,"O":1e-5,"Os":1e-5},
        "wall_sticking":1.0,"native_initialization":"fresh_not_restarted",
        "time_steps":460,"scientific_acceptance":"HOLD"
    }
    (r/"legacy6_latest_variant.json").write_text(json.dumps(provenance,indent=2)+"\n")
    print("OXYGEN_LEGACY6_LATEST_100US_PREPARED",power)


def verify_and_archive(power: int):
    """Requires a native final 100us solver state; no dummy/artificial artifacts."""
    check_input(power)
    r=result(power);run=r/"run";csv=run/"plasma.csv"
    import csv as libcsv
    import math
    with csv.open() as stream:
        rows=list(libcsv.DictReader(stream))
    if len(rows)<2:
        raise ValueError("Native plasma.csv insufficient")
    end=float(rows[-1]["time"])
    if not math.isclose(end,1e-4,rel_tol=0,abs_tol=1e-12):
        raise ValueError(f"NOT COMPLETE: native solver stopped at {end} not 100us")
    native_e=run/"plasma.e"
    if not native_e.is_file() or native_e.stat().st_size==0:
        raise ValueError("native Exodus output missing")
    import re
    log=(r/"runtime.log").read_text()
    points=re.findall(r"(?m)^Time Step\s+(\d+),\s*time\s*=\s*([0-9.eE+-]+)",log)
    if not points:raise ValueError("No solver Time Step evidence")
    step=int(points[-1][0]);t=float(points[-1][1])
    if not math.isclose(t,1e-4,rel_tol=0,abs_tol=1e-12):
        raise ValueError("Native log final time not 100us")
    prefix=run/"plasma_cp"/f"{step:04d}"
    for suffix in ("-restart-0.rd/data","-restart-0.rd/header","-mesh.cpa.gz/1/header.gz"):
        p=Path(str(prefix)+suffix)
        if not p.is_file() or p.stat().st_size==0:
            raise ValueError(f"Missing complete 100us native checkpoint: {p}")
    required_inputs=[input_path(power),TABLE]
    required_inputs += [CHEM/name.format(p=power) for name in COMPONENTS.values()]
    required_inputs += [CHEM/f"rf_elastic_multiapp_parent_{power}w_100us_dt1000ns_overlay.i",
                        CHEM/f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_overlay.i",
                        CHEM/f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_child.i"]
    required_inputs += [CHEM/name for name in PERSIST]
    required_inputs=list(dict.fromkeys(required_inputs))
    required_run=sorted(p for p in run.rglob("*") if p.is_file())
    for p in required_run+required_inputs:
        if not p.is_file() or p.is_symlink():
            raise ValueError(f"Required native restart input missing: {p}")
        if "private_rates" in p.as_posix():
            raise ValueError("No private chemistry files may be archived")
    archives={}
    inventory={}
    for kind,members in (("run",required_run),("inputs",required_inputs)):
        dest=r/f"legacy6_restart_{kind}_100000ns.tar.gz"
        with tarfile.open(dest,"w:gz") as archive:
            for p in members:archive.add(p,arcname=p.as_posix(),recursive=False)
        archives[kind]={"name":dest.name,"sha256":sha(dest),"bytes":dest.stat().st_size}
        inventory[kind]=[
            {"path":p.as_posix(),"bytes":p.stat().st_size,"sha256":sha(p)}
            for p in members]
    manifest=json.loads((r/"legacy6_latest_variant.json").read_text())
    manifest.update({
        "native_endpoint_s":end,"actual_moose_step":step,
        "native_checkpoint_prefix":prefix.as_posix(),
        "archives":archives,"inventory":inventory,
        "last_electron_density_avg_m3":float(rows[-1].get("ne_avg","nan")),
        "last_rf_power_W":float(rows[-1]["P_rf_raw_W_t6"]),
        "restart_requires_exact_legacy6_chemistry":True,
        "verified_full_native_100us_checkpoint":True,
    })
    outfile=r/"legacy6_restart_100000ns_manifest.json"
    outfile.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print("OXYGEN_LEGACY6_LATEST_100US_NATIVE_CHECKPOINT_PASS",power,step,manifest["last_rf_power_W"])


def self_test():
    times=expected_grid_ns()
    assert len(times)==461 and times[0]==0 and times[100]==100 and times[290]==2000
    assert times[370]==10000 and times[460]==100000
    assert set(COMPONENTS)=={"EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20"}
    assert "full24" not in repr(COMPONENTS)
    assert EEDF_SHA256 and len(EEDF_SHA256)==64
    print("OXYGEN_LEGACY6_LATEST_SELF_TEST_PASS")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test",action="store_true")
    group.add_argument("--prepare",action="store_true")
    group.add_argument("--verify-input",action="store_true")
    group.add_argument("--verify-and-archive",action="store_true")
    parser.add_argument("--power-w",type=int,choices=(400,1000))
    args=parser.parse_args()
    if args.self_test:self_test()
    elif args.power_w is None:parser.error("--power-w required")
    elif args.prepare:apply_latest_after_prepare(args.power_w)
    elif args.verify_input:check_input(args.power_w)
    elif args.verify_and_archive:verify_and_archive(args.power_w)
