"""#817 extended postcut source consumer Native validation: EI16/EI20/EDETACH.

Bounded current New-only smoke, no historical source execution, no global AD
or representative S5-R equivalence claim. Fails closed with sanitised receipts.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from experiments.Code3_electron_source_retirement import native_consumers as driver
from physics_app.ci import check_e8_ei16_energy_runtime as ei16
from physics_app.ci import check_stage5_ei20_runtime as ei20
from physics_app.ci import check_stage5_edetach_runtime as edetach
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(name: str, working: Path) -> tuple[str, str, str]:
    if name == "EI16":
        (working / "e8_ei16_runtime_table.txt").write_text(
            "".join(f"{e:.8g} {r:.17g}\n" for e,r in ei16.RATE_TABLE))
        return ei16.RUNTIME_INPUT, "FVKernels/n_e_source", "electron_ionization_number_source"
    if name == "EI20":
        shutil.copy2(ei20.TABLE, working / ei20.TABLE.name)
        return ei20.runtime_input(), "FVKernels/n_e_source", "electron_ei20_number_source"
    if name == "EDETACH":
        return edetach.text(), "FVKernels/ns", "electron_edetach_number_source"
    raise ValueError("UNKNOWN_TEST_CASE")


def validate_domain(name: str, rows: list[dict]) -> dict:
    if name == "EI16":
        result=ei16.validate_runtime_rows(rows)
    elif name == "EI20":
        result=ei20.validate(rows, ei20.read_table(ei20.TABLE.read_bytes()))
    elif name == "EDETACH":
        result=edetach.val(rows)
    else:
        raise ValueError("UNKNOWN_DOMAIN")
    return {
        "domain_closure": "PASS",
        "validator": {"EI16":"EI16 energy electron heavy charge",
                      "EI20":"EI20 ionization source and energy",
                      "EDETACH":"EDETACH electron heavy charge energy"}[name],
        "proof_field_count": len(result) if isinstance(result,dict) else None,
    }


def execute() -> dict:
    source_head=os.environ.get("SOURCE_HEAD", "")
    oci=os.environ.get("OCI", "")
    if not (len(source_head)==40 and all(c in "0123456789abcdef" for c in source_head)):
        raise ValueError("INVALID_SOURCE_HEAD")
    current=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    if current!=source_head:
        raise ValueError("STAGING_SOURCE_SHA_DRIFT")
    if (ROOT/"physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C").exists():
        raise ValueError("RETIRED_CPP_REINTRODUCED")
    binary=ROOT/"physics_app/physics-opt"
    if binary.read_bytes()[:4]!=b"\x7fELF":
        raise ValueError("NO_PINNED_FRESH_ELF")
    receipt={
      "schema":"issue817.code3.postcut_extended_native.v0.1",
      "source_head":source_head,
      "oci":oci,
      "binary_sha256":sha(binary.read_bytes()),
      "old_cpp_absent":True,
      "full_s5r_or_coupled_AD":"NOT_EVALUATED",
      "external_clients":"NOT_ATTESTED",
      "cases":{},
      "status":"HOLD_PENDING",
    }
    output=ROOT/"evidence/code3_postcut_extended_native.json"
    output.parent.mkdir(exist_ok=True)
    all_good=True
    for name in ("EI16","EI20","EDETACH"):
        row={"status":"HOLD"}
        receipt["cases"][name]=row
        with tempfile.TemporaryDirectory(prefix="issue817-"+name+"-") as dirname:
            work=Path(dirname)
            txt,path,functor=fixture(name,work)
            if mp.get_parameter(txt,path,"type") != "FVCoupledForce":
                raise ValueError(name+":OWNER_NOT_STANDARD")
            if mp.get_parameter(txt,path,"v") != functor:
                raise ValueError(name+":CANONICAL_SIGNED_FUNCTOR_DRIFT")
            if mp.get_parameter(txt,path,"coef") != "1":
                raise ValueError(name+":PHYSICAL_UNIT_COEFFICIENT_DRIFT")
            if mp.get_parameter(txt,path,"number_source") is not None:
                raise ValueError(name+":CUSTOM_PARAMETER_IN_CURRENT_INPUT")
            row.update(input_sha256=sha(txt.encode()),
                       signed_functor=functor, coef=1,
                       source_file_sha=sha(binary.read_bytes()))
            (work/"current.i").write_text(txt)
            row["P2"]=driver.launch(work,"current",syntax=True)
            if not row["P2"]["syntax_ok"] or row["P2"]["returncode"]!=0:
                row["status"]="HOLD_NATIVE_P2"
                all_good=False
            else:
                row["P3"]=driver.launch(work,"current",syntax=False)
                if row["P3"]["returncode"]!=0:
                    row["status"]="HOLD_NATIVE_P3"
                    all_good=False
                else:
                    csv_file=work/"current_out.csv"
                    with csv_file.open(newline="") as f:
                        rows=list(csv.DictReader(f))
                    row["csv_sha256"]=sha(csv_file.read_bytes())
                    row["csv_rows"]=len(rows)
                    try:
                        row.update(validate_domain(name,rows))
                        row["status"]="PASS_SCOPED_NATIVE_AND_DOMAIN"
                    except (AssertionError, KeyError, ValueError, OSError) as exc:
                        row["status"]="HOLD_DOMAIN_CLOSURE"
                        row["domain_error"]=type(exc).__name__+":"+str(exc)[:260]
                        all_good=False
            output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    receipt["status"]="PASS_EXTENDED_CONSUMERS_SCOPED_NATIVE" if all_good else "HOLD_ONE_OR_MORE_EXTENDED_CONSUMERS"
    output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print("ISSUE817_CODE3_EXTENDED_NATIVE="+receipt["status"])
    return receipt


def main() -> int:
    try:
        return 0 if execute()["status"]=="PASS_EXTENDED_CONSUMERS_SCOPED_NATIVE" else 1
    except Exception as exc:
        print("ISSUE817_EXTENDED_NATIVE_EXCEPTION="+type(exc).__name__+":"+str(exc)[:450])
        return 1

if __name__=="__main__":
    raise SystemExit(main())
