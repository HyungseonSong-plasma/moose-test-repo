"""Code3 #817 normalized single-cell nonlinear source A/B Native oracle.

This is NOT S5-R representative chemistry, nor complete AD Jacobian parity.
It isolates normalized signed source coupling without legacy Thermal objects.
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

from experiments.Code3_electron_source_retirement import run as code3
from experiments.Code3_electron_source_retirement import native_consumers as native
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
TARGET = code3.TARGET
N_REF = 1.298e18
DT = 0.1
Q0 = 1.0


def old_input(sign: int) -> str:
    if sign not in (-1, 1):
        raise ValueError("BAD_SOURCE_SIGN")
    factor = "" if sign == 1 else "-"
    return f"""[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 1
  []
[]
[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1
  []
[]
[FunctorMaterials]
  [source]
    type = ADParsedFunctorMaterial
    property_name = S_e_s5r
    functor_names = 'n_e'
    functor_symbols = 'q'
    expression = '{factor}{N_REF:.17g}*(0.4+0.1*q)'
  []
[]
[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
  []
  [s5r_electron_source]
    type = PhysicsFVElectronReactionSource
    variable = n_e
    number_source = S_e_s5r
    n_ref = {N_REF:.17g}
  []
[]
[Postprocessors]
  [n_e_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [S_e_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_e_s5r
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  dt = {DT:.17g}
  end_time = {DT:.17g}
  solve_type = NEWTON
[]
[Outputs]
  csv = true
  exodus = false
[]
"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_final(sign: int) -> float:
    # Implicit Euler: (q_1-q_0)/dt = sign*(0.4+0.1*q_1).
    return (Q0 + sign * DT * 0.4) / (1.0 - sign * DT * 0.1)


def final_observable(csv_path: Path) -> dict:
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 2 or "n_e_avg" not in rows[-1] or "S_e_avg" not in rows[-1]:
        raise ValueError("EXPECTED_TWO_ROW_NUMERIC_CSV")
    values = {k: float(rows[-1][k]) for k in ("time", "n_e_avg", "S_e_avg")}
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError("NONFINITE_MICRO_ORACLE")
    if not math.isclose(values["time"], DT, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError("WRONG_FINAL_TIME")
    return {**values, "rows": len(rows), "sha256": sha(csv_path.read_bytes())}


def execute() -> dict:
    head = os.environ["SOURCE_HEAD"]
    oci = os.environ["OCI"]
    if len(head) != 40 or any(x not in "0123456789abcdef" for x in head):
        raise ValueError("INVALID_SOURCE_HEAD")
    if (subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                text=True).strip() != head):
        raise ValueError("HEAD_CHANGED")
    binary = ROOT / "physics_app/physics-opt"
    if binary.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("NO_PHYSICS_ELF")
    record = {
        "schema": "issue817.code3.normalized_nonlinear_micro.v0.1",
        "source_head": head, "oci": oci,
        "elf_sha256": sha(binary.read_bytes()),
        "old_factory_kept": True, "current_s5r_representative_p3": "NOT_RUN",
        "full_ad_jacobian": "NOT_VERIFIED",
        "active_consumers_migrated": False,
        "safe_delete": False,
        "cases": {},
    }
    result_path = ROOT / "evidence/code3_normalized_nonlinear_micro.json"
    result_path.parent.mkdir(exist_ok=True)
    all_ok = True
    for sign in (1, -1):
        old = old_input(sign)
        new, meta = code3.replace_electron_only(old, path=TARGET)
        if code3._outside_target(old, TARGET) != code3._outside_target(new, TARGET):
            raise ValueError("NON_SOURCE_TEXT_CHANGED")
        if (meta["mode"] != "normalized" or meta["source_functor"] != "S_e_s5r"
                or not math.isclose(meta["coefficient"], 1.0 / N_REF, rel_tol=1e-15)):
            raise ValueError("NORMALIZED_CONTRACT_CHANGED")
        wrong = mp.upsert_parameter(new, TARGET, "coef",
                                     format(-meta["coefficient"], ".17g"))
        receipts = {"sign": sign, "n_ref": N_REF,
                    "coefficient": meta["coefficient"],
                    "old_sha256": sha(old.encode()),
                    "candidate_sha256": sha(new.encode()),
                    "flipped_coef_sha256": sha(wrong.encode()),
                    "single_source_block_changed": True,
                    "analytical_one_cell_q_final": expected_final(sign),
                    "arms": {}}
        record["cases"][str(sign)] = receipts
        with tempfile.TemporaryDirectory(prefix="code3-norm-micro-") as temp:
            work = Path(temp)
            for name, content in (("original", old), ("candidate", new), ("flipped", wrong)):
                (work / (name + ".i")).write_text(content)
                receipts["arms"][name] = {"P2": native.launch(work,name,syntax=True)}
            p2 = all(x["P2"]["returncode"] == 0 and x["P2"]["syntax_ok"]
                     for x in receipts["arms"].values())
            receipts["P2_all_three_accepted"] = p2
            if p2:
                for name in receipts["arms"]:
                    receipts["arms"][name]["P3"] = native.launch(work, name, syntax=False)
                p3 = all(x["P3"]["returncode"] == 0
                         for x in receipts["arms"].values())
                receipts["P3_all_three_runs"] = p3
                if p3:
                    try:
                        observed = {name:final_observable(work / (name + "_out.csv"))
                                    for name in receipts["arms"]}
                        receipts["observables"] = observed
                        original = observed["original"]["n_e_avg"]
                        candidate = observed["candidate"]["n_e_avg"]
                        wrong_sign = observed["flipped"]["n_e_avg"]
                        receipts["old_new_same"] = math.isclose(
                            original,candidate,rel_tol=1e-9,abs_tol=1e-11)
                        receipts["analytic_source_response"] = math.isclose(
                            original,expected_final(sign),rel_tol=1e-6,abs_tol=1e-8)
                        receipts["wrong_coef_rejected_by_discriminator"] = (
                            abs(original - wrong_sign) > 0.04)
                    except (ValueError, OSError, KeyError) as exc:
                        receipts["comparison_error"] = type(exc).__name__+":"+str(exc)[:240]
            receipts["accepted"] = all(receipts.get(x,False) for x in (
                "old_new_same", "analytic_source_response",
                "wrong_coef_rejected_by_discriminator"))
            all_ok &= receipts["accepted"]
            result_path.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    record["status"] = ("PASS_BOUNDED_NORMALIZED_NONLINEAR_MICRO"
                        if all_ok else "HOLD_NORMALIZED_MICRO_P2_P3")
    result_path.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    print("ISSUE817_CODE3_NORMALIZED_MICRO="+record["status"])
    return record


def main() -> int:
    try:
        result = execute()
    except Exception as exc:
        print("ISSUE817_CODE3_NORMALIZED_MICRO_EXCEPTION="+
              type(exc).__name__+":"+str(exc)[:400])
        return 1
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
