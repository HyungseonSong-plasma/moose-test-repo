#!/usr/bin/env python3
"""Issue #671 D8: bounded, public-only, real Maxwell-child/7-Transfer Native discriminator.

This does NOT run the historical S6 plasma model or authorize scientific P3/P4.
It uses the exact SHA-pinned public S6 child, Maxwell includes, meshes, and
production seven-Transfer definitions with a deliberately reduced 1-step parent.
No private EI rates enter or leave this harness.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile

P3_ZIP_SHA = "592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111"
PARENT_MESH_SHA = "ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc"
CHILD_SHA = "655fa43c4c1083e55ea4e845e0e2947c627aec39bc9dd0d384f52468db512698"
MAXWELL_MESH_SHA = "a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
CHILD = "rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_child.i"
PARENT = "rf_elastic_multiapp_parent_400w_100us_dt1000ns_overlay.i"
TRANSFER_NAMES = (
    "drive_to_maxwell_t6", "ne_to_maxwell_t6", "mean_en_to_maxwell_t6",
    "pressure_to_maxwell_t6", "E_real_from_maxwell_t6",
    "E_imag_from_maxwell_t6", "P_abs_from_maxwell_t6",
)
SRC_STATE = {"electron_density_rf_state_t6": 1.0e15,
             "mean_energy_rf_state_t6": 4.0,
             "pressure_rf_state_t6": 1.3322}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_sha(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"RF_PIN_SHA_MISMATCH {path}: {actual} != {expected}")
    return actual


def stage(artifact, mesh, output):
    require_sha(artifact, P3_ZIP_SHA)
    require_sha(mesh, PARENT_MESH_SHA)
    if output.exists():
        raise ValueError("RF_DISPOSABLE_SCRATCH_EXISTS")
    output.mkdir(parents=True, mode=0o700)
    evidence = {"scope": "PUBLIC_ONLY_REAL_CHILD_1STEP_REDUCED_PARENT",
                "full_S6_solver": "NOT_RUN",
                "science": "SCIENCE_HOLD", "cases": {}}
    with zipfile.ZipFile(artifact) as z:
        if z.testzip() is not None:
            raise ValueError("RF_ZIP_CRC_MISMATCH")
        for case in ("417", "941"):
            prefix = f"cases/{case}/experiments/"
            work = output / case
            work.mkdir(mode=0o700)
            files = 0
            for info in z.infolist():
                if not info.filename.startswith(prefix) or info.is_dir():
                    continue
                rel = Path("experiments") / info.filename[len(prefix):]
                if ".." in rel.parts or info.filename.startswith("/") or \
                   stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    raise ValueError("RF_UNSAFE_ARTIFACT_MEMBER")
                if "private_rates" in rel.parts:
                    raise ValueError("RF_PRIVATE_RATE_FORBIDDEN")
                dest = work / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(info))
                files += 1
            chem = work / CHEM
            target = chem / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
            target.write_bytes(mesh.read_bytes())
            require_sha(target, PARENT_MESH_SHA)
            require_sha(chem / CHILD, CHILD_SHA)
            require_sha(work / "experiments/Issue18_qvt_plasma_mapping/qvt.msh",
                        MAXWELL_MESH_SHA)
            orig = (chem / PARENT).read_text()
            if orig.count("[MultiApps]") != 1 or orig.count("[Transfers]") != 1 \
               or orig.count("[Controls]") != 1:
                raise ValueError("RF_PRODUCTION_PARENT_TRANSFER_BOUNDARIES_BAD")
            tx = "[MultiApps]" + orig.split("[MultiApps]", 1)[1].split("[Controls]", 1)[0]
            seen = re.findall(r"(?m)^  \[([A-Za-z0-9_]+)\]$", tx)
            if seen != ["maxwell_t6", *TRANSFER_NAMES] or tx.count("SAME_AS_MULTIAPP") != 7:
                raise ValueError(f"RF_EXPECTED_SEVEN_TRANSFER_NAMES_MISMATCH {seen}")
            if f"input_files = '{CHILD}'" not in tx or "FullSolveMultiApp" not in tx:
                raise ValueError("RF_CHILD_NOT_REAL_FULL_SOLVE")
            # Only diagnostic output and wrapper path differ from the production
            # transfer block; every actual Transfer definition remains identical.
            tx_diag = tx.replace(f"input_files = '{CHILD}'",
                                 "input_files = 'rf_child_diagnostic.i'")
            tx_diag = tx_diag.replace("Outputs/exodus=false;Outputs/csv=false",
                                      "Outputs/exodus=false;Outputs/csv=true")
            if tx_diag == tx:
                raise ValueError("RF_DIAGNOSTIC_OUTPUT_OVERRIDE_NOT_APPLIED")
            child_extra = f"!include {CHILD}\n\n[Postprocessors]\n"
            for name, variable in [("ne_received_t6","electron_density_state_t6"),
                                    ("mean_en_received_t6","mean_energy_state_t6"),
                                    ("pressure_received_t6","pressure_state_t6")]:
                child_extra += (f"  [{name}]\n    type = ElementAverageValue\n"
                                f"    variable = {variable}\n    block = plasma\n"
                                "    execute_on = 'INITIAL TIMESTEP_END'\n  []\n")
            child_extra += "[]\n"
            (chem / "rf_child_diagnostic.i").write_text(child_extra)
            parent = [
                "# Issue671 RF-only 1-step Transfer smoke: NOT full S6 scientific simulation",
                "[Mesh]", "  coord_type = RZ", "  rz_coord_axis = Y",
                "  [main]", "    type = FileMeshGenerator",
                "    file = 'baseline_plasma_plus_unstructured_cover_plus_wafer.msh'",
                "  []", "[]",
                "[Variables]", "  [rf_probe_u]", "    family = LAGRANGE",
                "    order = FIRST", "  []", "[]",
                "[Kernels]", "  [rf_probe_time]", "    type = TimeDerivative",
                "    variable = rf_probe_u", "  []", "[]",
                "[AuxVariables]",
            ]
            for variable, value in SRC_STATE.items():
                family = "MONOMIAL" if variable == "pressure_rf_state_t6" else "LAGRANGE"
                order = "CONSTANT" if family == "MONOMIAL" else "FIRST"
                parent.extend([f"  [{variable}]", f"    family = {family}",
                               f"    order = {order}", "    block = plasma",
                               f"    initial_condition = {value:.17g}", "  []"])
            for variable in ("E_real_rf_t6","E_imag_rf_t6"):
                parent.extend([f"  [{variable}]", "    family = LAGRANGE",
                               "    order = FIRST", "    block = plasma", "  []"])
            parent.extend(["[]", "[Postprocessors]",
                           "  [rf_drive_scale_t6]", "    type = Receiver",
                           "    default = 1.0", "    execute_on = 'INITIAL TIMESTEP_END'", "  []",
                           "  [P_abs_maxwell_t6]", "    type = Receiver",
                           "    default = -1.0", "    execute_on = 'INITIAL TIMESTEP_BEGIN TIMESTEP_END'", "  []"])
            for name, variable in [("parent_E_real_l2","E_real_rf_t6"),
                                   ("parent_E_imag_l2","E_imag_rf_t6")]:
                parent.extend([f"  [{name}]", "    type = ElementL2Norm",
                               f"    variable = {variable}", "    block = plasma",
                               "    execute_on = 'INITIAL TIMESTEP_END'", "  []"])
            parent.extend(["[]", tx_diag, "[Executioner]", "  type = Transient",
                           "  scheme = implicit-euler", "  solve_type = NEWTON",
                           "  num_steps = 1", "  end_time = 1e-9",
                           "  [TimeStepper]", "    type = ConstantDT",
                           "    dt = 1e-9", "  []", "[]", "[Outputs]",
                           "  csv = true", "  exodus = false",
                           "  file_base = rf_smoke_parent", "  execute_on = 'INITIAL TIMESTEP_END'",
                           "[]"])
            (chem / "rf_transfer_parent_smoke.i").write_text("\n".join(parent)+"\n")
            evidence["cases"][case] = {
                "source_files": files, "input": str(CHEM / "rf_transfer_parent_smoke.i"),
                "production_transfer_sha256": hashlib.sha256(tx.encode()).hexdigest(),
                "exact_real_child_sha256": sha(chem / CHILD),
                "parent_mesh_sha256": sha(target),
                "maxwell_child_mesh_sha256": sha(work / "experiments/Issue18_qvt_plasma_mapping/qvt.msh"),
                "disposable_parent_sha256": sha(chem / "rf_transfer_parent_smoke.i"),
                "extra_child_pp_wrapper_sha256": sha(chem / "rf_child_diagnostic.i"),
                "transfer_names": list(TRANSFER_NAMES),
                "scope": "ACTUAL_MAXWELL_CHILD_REDUCED_PARENT_1_STEP"
            }
    (output / "stage_receipt.json").write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n")
    print("RF_CHILD_AND_SEVEN_PRODUCTION_TRANSFERS_SOURCE_STAGE_PASS")


def last_csv(path):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"RF_CSV_NO_ROWS: {path}")
    return {k: float(v) for k,v in rows[-1].items() if v is not None and v.strip()}


def evaluate(output):
    stage_receipt=json.loads((output/"stage_receipt.json").read_text())
    results={"schema":"issue671.rf_maxwell_7_transfers_smoke.v1",
             "scope":"REAL_CHILD_AND_PRODUCTION_TRANSFERS_REDUCED_1STEP_PARENT",
             "full_S6_417_941_RF_COUPLING":"NOT_TESTED",
             "science":"SCIENCE_HOLD","cases":{}}
    all_ok=True
    for case in ("417","941"):
        wd=output/case/CHEM
        parent=wd/"rf_smoke_parent.csv"
        native_log=output/f"S6-{case}_rf_native.log"
        log=native_log.read_text() if native_log.exists() else ""
        meta=output/f"S6-{case}_rf_exit.json"
        rc=json.loads(meta.read_text())["exit_code"] if meta.exists() else -999
        entries={"exit_code":rc,"native_log_sha256":sha(native_log) if native_log.exists() else None,
                 "observed_csv_files":[],"child_power_W":None,"parent_received_power_W":None,
                 "actual_transfer_numeric_verified":False}
        files=sorted(wd.glob("*.csv"))
        entries["observed_csv_files"]=[{"name":f.name,"sha256":sha(f)} for f in files]
        try:
            p=last_csv(parent)
            entries["parent_columns"]=sorted(p)
            pp=p["P_abs_maxwell_t6"]
            er=p["parent_E_real_l2"]; ei=p["parent_E_imag_l2"]
            child_candidates=[]
            for f in files:
                if f==parent:
                    continue
                c=last_csv(f)
                if "P_abs" in c and "ne_received_t6" in c and "mean_en_received_t6" in c:
                    child_candidates.append((f,c))
            if len(child_candidates)!=1:
                raise ValueError(f"RF_CHILD_CSV_UNOBSERVABLE count={len(child_candidates)}")
            path,c=child_candidates[0]
            entries["child_csv"]=path.name
            checks={
                "real_child_power_positive":c["P_abs"]>0,
                "parent_P_abs_receiver_matches_child":abs(pp-c["P_abs"])<=max(1e-8,abs(c["P_abs"])*1e-6),
                "parent_received_E_real_positive":er>0,
                "parent_received_E_imag_positive":ei>0,
                "child_received_ne":abs(c["ne_received_t6"]-SRC_STATE["electron_density_rf_state_t6"]) <= SRC_STATE["electron_density_rf_state_t6"]*1e-5,
                "child_received_mean_energy":abs(c["mean_en_received_t6"]-SRC_STATE["mean_energy_rf_state_t6"])<=1e-5,
                "child_received_pressure":abs(c["pressure_received_t6"]-SRC_STATE["pressure_rf_state_t6"])<=1e-5,
                "child_received_drive":abs(c["rf_drive_scale_child"]-1.0)<=1e-7,
                "single_parent_step":p.get("time", -1)>0 and p.get("time",1)>-1,
            }
            entries["checks"]=checks
            entries["child_power_W"]=c["P_abs"]
            entries["parent_received_power_W"]=pp
            entries["actual_transfer_numeric_verified"]=rc==0 and all(checks.values())
        except Exception as exc:
            entries["failure_class"]=type(exc).__name__
            entries["failure_detail"]=str(exc)[:250]
        all_ok &= entries["actual_transfer_numeric_verified"]
        results["cases"][case]=entries
    results["RF_BOUND_BIDIRECTIONAL_TRANSFER_SMOKE"]="PASS" if all_ok else "HOLD"
    (output/"rf_transfer_receipt.json").write_text(json.dumps(results,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":results["RF_BOUND_BIDIRECTIONAL_TRANSFER_SMOKE"],
                      "per_case":{c:{"rc":x["exit_code"],"checks":x.get("checks"),
                                      "error":x.get("failure_detail")}
                                  for c,x in results["cases"].items()}},sort_keys=True))
    return 0 if all_ok else 1


def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_subparsers(dest="mode",required=True)
    st=mode.add_parser("stage")
    st.add_argument("--artifact",type=Path,required=True)
    st.add_argument("--mesh",type=Path,required=True)
    st.add_argument("--output",type=Path,required=True)
    ev=mode.add_parser("evaluate")
    ev.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    return stage(args.artifact,args.mesh,args.output) if args.mode=="stage" else evaluate(args.output)


if __name__=="__main__":
    raise SystemExit(main())
