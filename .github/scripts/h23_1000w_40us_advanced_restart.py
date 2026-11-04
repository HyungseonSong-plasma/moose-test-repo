#!/usr/bin/env python3
"""H23 1000W verified 40us native checkpoint -> 100us advanced restart.
Research-only: scientific acceptance remains HOLD.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, re, subprocess, tarfile
from pathlib import Path
from scipy.io import netcdf_file

ROOT = Path.cwd()
CHEM = Path(os.environ["CHEM"])
RESULT = Path(os.environ["RESULT"])
SOURCE = os.environ["CHATGPT_WORK_BASE_SHA"]
UPSTREAM = Path("_h23_40us")
MANIFEST = UPSTREAM / "legacy6_restart_40000ns_manifest.json"
RUN_ARCHIVE = UPSTREAM / "legacy6_restart_run_40000ns.tar.gz"
EXPECTED = ["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20",
            "EI-2738","EI-407","EI-417","EI-935","EI-943","H24","H25","H23"]


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def read_origin() -> dict:
    j=json.loads(MANIFEST.read_text())
    chem=json.loads((RESULT/"legacy6_latest_variant.json").read_text())
    assert j["end_ns"]==40000 and j["power_w"]==1000
    assert j["scientific_acceptance"]=="HOLD"
    assert j["physics_source_sha"]==SOURCE
    assert j["workflow_head_sha"]=="5117c23168d0fc0e4b97777ca17851a38b540dfc"
    assert j["chemistry_channels"]==chem["chemistry_channels"]==EXPECTED
    assert j["transport_table_sha256"]==chem["transport_table_sha256"]
    assert RUN_ARCHIVE.stat().st_size>1_000_000
    return j


def prepare() -> None:
    j=read_origin()
    with tarfile.open(RUN_ARCHIVE,"r:gz") as tf:
        for member in tf.getmembers():
            n=Path(member.name)
            assert not n.is_absolute() and ".." not in n.parts
            assert str(n)==str(RESULT/"run") or str(n).startswith(str(RESULT/"run")+"/")
        tf.extractall(ROOT,filter="data")
    run=RESULT/"run"
    assert sha(run/"plasma.csv")==j["plasma_csv_sha256"]
    assert sha(run/"plasma.e")==j["plasma_e_sha256"]
    prefix=Path(j["checkpoint_prefix"])
    assert (Path(str(prefix)+"-restart-0.rd")/"data").stat().st_size>0
    assert (Path(str(prefix)+"-restart-0.rd")/"header").stat().st_size>0
    assert (Path(str(prefix)+"-mesh.cpa.gz")/"1/header.gz").stat().st_size>0

    p=os.environ["POWER_W"]
    inp=CHEM/f"rf_elastic_diss_ion_ei20_ei01_{p}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
    parent=CHEM/f"rf_elastic_multiapp_parent_{p}w_100us_dt1000ns_overlay.i"
    child=CHEM/f"rf_elastic_multiapp_maxwell_{p}w_100us_dt1000ns_overlay.i"

    s=inp.read_text()
    s,n=re.subn(r"(?m)^\s*initial_condition\s*=\s*[^\n]+\n","",s)
    assert n==15, f"changed parent seed IC count {n}"
    ts=re.compile(r"(?ms)^  \[TimeStepper\]\n.*?^  \[\]\s*$")
    replacement=("  [TimeStepper]\n"
                 "    type = IterationAdaptiveDT\n"
                 "    dt = 1e-6\n"
                 "    growth_factor = 1.0\n"
                 "    reset_dt = true\n"
                 "  []")
    s,n=ts.subn(replacement,s)
    assert n==1 and "end_time = 1e-4" in s
    # MOOSE Transient owns dtmin; IterationAdaptiveDT does not.
    # Keep the original restart dt floor (10 ns) without an unused parameter.
    # Keep the original minimum step (10 ns), but place it on Executioner.
    # Scope the edit to this section; do not rely on escaped regex tokens.
    before, sep, after = s.partition("[Executioner]\n")
    assert sep, "missing parent Executioner"
    executioner_head, sep, tail = after.partition("  [TimeStepper]\n")
    assert sep, "missing parent TimeStepper"
    end_time_line = "  end_time = 1e-4\n"
    assert executioner_head.count(end_time_line) == 1
    assert "dtmin" not in executioner_head
    executioner_head = executioner_head.replace(
        end_time_line, end_time_line + "  dtmin = 1e-8\n", 1
    )
    s = before + "[Executioner]\n" + executioner_head + sep + tail
    assert s.count("  dtmin = 1e-8\n") == 1
    ts_section = s.split("  [TimeStepper]\n", 1)[1].split("  []", 1)[0]
    assert "dtmin" not in ts_section
    assert "TimeSequenceStepper" not in s
    inp.write_text(s)

    s=parent.read_text()
    s,n=re.subn(r"(?m)^(\s*no_restore\s*=\s*)true(\s*)$",r"\g<1>false\g<2>",s)
    assert n==1
    parent.write_text(s)

    s=child.read_text()
    s,n=re.subn(r"(?m)^\s*initial_condition\s*=\s*[^\n]+\n","",s)
    assert n==3, f"changed Maxwell seed IC count {n}"
    child.write_text(s)

    rp=CHEM/"issue397_l1_power_scan_replay.sh"
    s=rp.read_text()
    old="Outputs/file_base='$RESULT/run/plasma'"
    new=("Outputs/file_base='$RESULT/run/plasma_restart_40to100' "
         "MultiApps/maxwell_t6/no_restore=false "
         "Problem/restart_file_base='/workspace/$RECOVER_PREFIX'")
    assert s.count(old)==1
    rp.write_text(s.replace(old,new))
    (RESULT/"recovery_prefix.txt").write_text(str(prefix)+"\n")
    (RESULT/"restart_input_audit.json").write_text(json.dumps({
      "start_us":40,"end_us":100,"parent_seed_ic_removed":15,
      "child_seed_ic_removed":3,"time_stepper":"IterationAdaptiveDT",
      "dt_max_s":1e-6,"dtmin_s":1e-8,
      "dtmin_owner":"Executioner","Maxwell_no_restore":False,
      "upstream_40us_plasma_sha":j["plasma_e_sha256"],
      "scientific_acceptance":"HOLD"
    },indent=2)+"\n")
    print("H23_1000W_40US_RESTORED_NATIVE_CHECKPOINT_PASS",prefix,flush=True)


def verify() -> None:
    j=read_origin()
    run=RESULT/"run"
    with (run/"plasma_restart_40to100.csv").open(newline="") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)>10
    assert math.isclose(float(rows[-1]["time"]),1e-4,rel_tol=0,abs_tol=1e-13)
    assert float(rows[0]["time"])>=3.999e-5
    exo=run/"plasma_restart_40to100.e"
    with netcdf_file(str(exo),"r",mmap=False) as ds:
        assert math.isclose(float(ds.variables["time_whole"].data[-1]),1e-4,rel_tol=0,abs_tol=1e-13)
    assert sha(run/"plasma.csv")==j["plasma_csv_sha256"]
    assert sha(run/"plasma.e")==j["plasma_e_sha256"]
    cp=run/"plasma_restart_40to100_cp"
    items=sorted(cp.glob("*-restart-0.rd/data"))
    assert items
    stem=items[-1].parent.name.replace("-restart-0.rd","")
    assert (cp/(stem+"-mesh.cpa.gz/1/header.gz")).stat().st_size>0
    manifest={
      "power_w":1000,"start_ns":40000,"end_ns":100000,
      "checkpoint_step":stem,
      "chemistry_channels":EXPECTED,
      "physics_source_sha":SOURCE,
      "upstream_40us_exodus_sha256":j["plasma_e_sha256"],
      "scientific_acceptance":"HOLD"
    }
    (RESULT/"legacy6_restart_100000ns_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    with tarfile.open(RESULT/"legacy6_restart_run_100000ns.tar.gz","w:gz") as tf:
        tf.add(run,arcname=str(run))
    p=os.environ["POWER_W"]
    safe=[CHEM/f"rf_elastic_diss_ion_ei20_ei01_{p}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"]
    for key in ("H23_OVERLAY","H24_OVERLAY","H25_OVERLAY",
                "EI943_OVERLAY","EI935_OVERLAY","EI417_OVERLAY","EI407_OVERLAY"):
        safe.append(Path(os.environ[key]))
    with tarfile.open(RESULT/"legacy6_restart_inputs_100000ns.tar.gz","w:gz") as tf:
        for q in safe:
            assert "private_rates" not in str(q)
            tf.add(q,arcname=str(q))
    print("H23_1000W_GENUINE_RESTART_100US_PASS",stem,len(rows),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=("prepare","verify"))
    args=parser.parse_args()
    {"prepare":prepare,"verify":verify}[args.command]()
