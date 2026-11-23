"""#817 Code3 post-cut exact-head current New-only Native acceptance.

Runs ONLY registered standard FVCoupledForce inputs: EI01/H05/R2 physical
and a ± signed normalized nonlinear micro with deliberately wrong coef controls.
No retired PhysicsFVElectronReactionSource is ever executed in this binary.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from experiments.Code3_electron_source_retirement import native_consumers as ab
from experiments.Code3_electron_source_retirement import normalized_micro_native as micro
from experiments.Code3_electron_source_retirement import run as historical
from physics_app.ci import check_stage5_h05_runtime as h05
from physics_app.ci import check_r2_o2_ionization_implementation as r2
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
SOURCE_C = ROOT / "physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C"
SOURCE_H = ROOT / "physics_app/include/fvkernels/PhysicsFVElectronReactionSource.h"


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def read_csv(file: Path) -> tuple[list[dict], dict]:
    with file.open(newline="") as inp:
        rows = list(csv.DictReader(inp))
    if len(rows) < 2 or "time" not in rows[-1]:
        raise ValueError("RUNTIME_CSV_NOT_TIME_RESOLVED")
    vals = {}
    for key in rows[-1]:
        if key == "time" or key.endswith("_avg"):
            x = float(rows[-1][key])
            if not math.isfinite(x):
                raise ValueError("NONFINITE_RUNTIME_OUTPUT:" + key)
            vals[key] = x
    if not vals:
        raise ValueError("NO_NUMERIC_OUTPUT")
    return rows, {"rows": len(rows), "columns": list(vals),
                  "sha256": sha(file.read_bytes())}


def assert_source(text: str, path: str, functor: str, coef: float) -> None:
    if mp.get_parameter(text,path,"type") != "FVCoupledForce":
        raise ValueError("STANDARD_SOURCE_TYPE_DRIFT")
    if mp.get_parameter(text,path,"v") != functor:
        raise ValueError("SIGNED_SOURCE_FUNCTOR_DRIFT")
    raw = mp.get_parameter(text,path,"coef")
    if raw is None or not math.isclose(float(raw),coef,rel_tol=1e-14,abs_tol=0):
        raise ValueError("SOURCE_COEFFICIENT_DRIFT")
    if any(mp.get_parameter(text,path,p) is not None
           for p in ("number_source","state_form","n_ref")):
        raise ValueError("OLD_TYPE_PARAMETERS_REINTRODUCED")


def run_current(work: Path, label: str, source: str) -> dict:
    (work / (label+".i")).write_text(source)
    result = {"input_sha256":sha(source.encode())}
    result["P2"] = ab.launch(work,label,syntax=True)
    if result["P2"]["returncode"] or not result["P2"]["syntax_ok"]:
        raise ValueError("POSTCUT_NATIVE_P2_FAILED:"+label+":"+str(result["P2"])[:180])
    result["P3"] = ab.launch(work,label,syntax=False)
    if result["P3"]["returncode"]:
        raise ValueError("POSTCUT_NATIVE_P3_FAILED:"+label+":"+str(result["P3"])[:180])
    rows, summary=read_csv(work/(label+"_out.csv"))
    result["csv"] = summary
    return result


def execute() -> dict:
    head=os.environ["SOURCE_HEAD"]
    oci=os.environ["OCI"]
    if len(head)!=40 or any(c not in "0123456789abcdef" for c in head):
        raise ValueError("BAD_EXACT_SOURCE_HEAD")
    actual=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    if actual!=head:
        raise ValueError("HEAD_NOT_PINNED")
    if SOURCE_C.exists() or SOURCE_H.exists():
        raise ValueError("LEGACY_C_H_REINTRODUCED")
    binary=ROOT/"physics_app/physics-opt"
    if binary.read_bytes()[:4]!=b"\x7fELF":
        raise ValueError("NEW_PHYSICS_BINARY_NOT_ELF")
    report={
        "schema":"issue817.code3.postcut.native.v0.1",
        "source_head":head,
        "pinned_oci":oci,
        "binary_sha256":sha(binary.read_bytes()),
        "legacy_c_h_absent":True,
        "main_integration":"NOT_EXECUTED",
        "full_s5r_p3":"NOT_EXECUTED_HISTORIC_THERMAL_BLOCKER",
        "full_coupled_AD_jacobian":"NOT_MEASURED",
        "external_consumers":"NOT_CLOSED",
        "cases":{},
        "status":"HOLD",
    }
    output=ROOT/"evidence/code3_postcut_native_receipt.json"
    output.parent.mkdir(exist_ok=True)
    try:
        for label in ("EI01","H05","R2"):
            if label=="EI01":
                current=(ROOT/"physics_app/ci/ei01_attachment_runtime_smoke.i").read_text()
                path="FVKernels/ei01_electron_source"
                signed="ei01_electron_number_source"
            else:
                _,current,_=ab.pair_recipe(label)
                path="FVKernels/n_e_source"
                signed=("S_e_h05" if label=="H05"
                        else "electron_ionization_number_source")
            assert_source(current,path,signed,1.0)
            with tempfile.TemporaryDirectory(prefix="issue817-postcut-"+label+"-") as folder:
                work=Path(folder)
                if label=="R2":
                    (work/"r2_o2_ionization_runtime_table.txt").write_text(
                        "".join(f"{e:.8g} {k:.17g}\n" for e,k in r2.RATE_TABLE))
                receipt=run_current(work,"candidate",current)
                rows,_=read_csv(work/"candidate_out.csv")
                if label=="H05":
                    h05.validate(rows)
                if label=="R2":
                    r2.validate_runtime_rows(rows)
                receipt["original_domain_closure"]="PASS" if label!="EI01" else "NOT_A_DOMAIN_OWNER"
                report["cases"][label]=receipt
                output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        for sign in (1,-1):
            legacy=micro.old_input(sign)  # historical text only; never run old Factory
            current,meta=historical.replace_electron_only(legacy)
            if (historical._outside_target(legacy) !=
                    historical._outside_target(current)):
                raise ValueError("NORMALIZED_NON_TARGET_DRIFT")
            assert_source(current,historical.TARGET,"S_e_s5r",1.0/micro.N_REF)
            wrong=mp.upsert_parameter(current,historical.TARGET,"coef",
                                      format(-meta["coefficient"],".17g"))
            with tempfile.TemporaryDirectory(prefix="issue817-postcut-norm-") as folder:
                work=Path(folder)
                correct=run_current(work,"current",current)
                flipped=run_current(work,"flipped",wrong)
                with (work/"current_out.csv").open(newline="") as inp:
                    final=list(csv.DictReader(inp))[-1]
                with (work/"flipped_out.csv").open(newline="") as inp:
                    wrong_final=list(csv.DictReader(inp))[-1]
                q=float(final["n_e_avg"])
                w=float(wrong_final["n_e_avg"])
                if not math.isclose(q,micro.expected_final(sign),
                                    rel_tol=1e-6,abs_tol=1e-8):
                    raise ValueError("NORMALIZED_NEW_BINARY_ANALYTICAL_MISMATCH")
                if abs(q-w)<=0.04:
                    raise ValueError("NORMALIZED_WRONG_COEF_NOT_DISCRIMINATED")
                report["cases"]["normalized_"+str(sign)]={
                    "current":correct,"wrong_coefficient":flipped,
                    "final_n_e_avg":q,"wrong_final_n_e_avg":w,
                    "analytic_final_n_e_avg":micro.expected_final(sign),
                    "coefficient_inverse_positive":True,
                    "wrong_sign_discriminated":True,
                }
                output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        report["status"]="PASS_SCOPED_NEWONLY_POSTCUT_NATIVE"
    except Exception as exc:
        report["status"]="HOLD_POSTCUT_NATIVE"
        report["error"]=type(exc).__name__+":"+str(exc)[:550]
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("ISSUE817_CODE3_POSTCUT_NATIVE="+report["status"])
    return report


def main() -> int:
    try:
        r=execute()
        return 0 if r["status"]=="PASS_SCOPED_NEWONLY_POSTCUT_NATIVE" else 1
    except Exception as exc:
        print("ISSUE817_CODE3_POSTCUT_NATIVE_EXCEPTION="+type(exc).__name__+":"+str(exc)[:550])
        return 1


if __name__=="__main__":
    raise SystemExit(main())
