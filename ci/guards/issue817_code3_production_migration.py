#!/usr/bin/env python3
"""#817 post-migration Code3 retirement: active New-only production contract.

This gate never claims global external caller zero or full AD Jacobian.
An archived frozen ownership document is not executable production input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
TARGET = "PhysicsFVElectronReactionSource"
SOURCE = ROOT / "physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C"
HEADER = ROOT / "physics_app/include/fvkernels/PhysicsFVElectronReactionSource.h"
SOURCE_GIT_BLOB = "35ded0eab65ad7bed85baa0104261c90bc26bf3d"
HEADER_GIT_BLOB = "5250b3500d6694481158e2abb896c7e1c6f349e9"
SOURCE_PATH = SOURCE.relative_to(ROOT).as_posix()
HEADER_PATH = HEADER.relative_to(ROOT).as_posix()
SCHEMA = "issue817.code3.current_newonly_postcut.v0.1"
PHYSICAL = (
    ("EI01", "physics_app/ci/ei01_attachment_runtime_smoke.i",
     "FVKernels/ei01_electron_source", "ei01_electron_number_source"),
    ("H05", "physics_app/ci/check_stage5_h05_runtime.py",
     "FVKernels/n_e_source", "S_e_h05"),
    ("R2", "physics_app/ci/check_r2_o2_ionization_implementation.py",
     "FVKernels/n_e_source", "electron_ionization_number_source"),
    ("EI16", "physics_app/ci/check_e8_ei16_energy_runtime.py",
     "FVKernels/n_e_source", "electron_ionization_number_source"),
    ("EI16_STANDARD", "physics_app/ci/check_standard_moose_energy_projection.py",
     "FVKernels/n_e_source", "electron_ionization_number_source"),
    ("EI20", "physics_app/ci/check_stage5_ei20_runtime.py",
     "FVKernels/n_e_source", "electron_ei20_number_source"),
    ("EDETACH", "physics_app/ci/check_stage5_edetach_runtime.py",
     "FVKernels/ns", "electron_edetach_number_source"),
)


def fail(code: str) -> None:
    raise ValueError("ISSUE817_MIGRATION_" + code)


def raw_identity(path: Path) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "hash-object", str(path)],
                       check=True, capture_output=True, text=True)
    return r.stdout.strip()


def exact_head(expected: str) -> str:
    if not re.fullmatch("[0-9a-f]{40}", expected):
        fail("EXPECTED_HEAD_INVALID")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                     cwd=ROOT, text=True).strip()
    if actual != expected:
        fail("EXACT_HEAD_CHANGED")
    return actual


def frozen_source(phase: str) -> None:
    if phase == "migrate":
        if not SOURCE.is_file() or not HEADER.is_file():
            fail("PREDELETE_SOURCE_MISSING")
        if raw_identity(SOURCE) != SOURCE_GIT_BLOB or raw_identity(HEADER) != HEADER_GIT_BLOB:
            fail("PREDELETE_SOURCE_DRIFT")
    elif phase == "postcut":
        if SOURCE.exists() or HEADER.exists():
            fail("C_H_STILL_REGISTERED")
        for p in (SOURCE_PATH, HEADER_PATH):
            if subprocess.run(["git", "ls-files", "--error-unmatch", p],
                              cwd=ROOT, capture_output=True, check=False).returncode == 0:
                fail("C_H_TRACKED_AFTER_CUT")
    else:
        fail("BAD_PHASE")


def check_owner(text: str, path: str, functor: str, coef: float) -> dict:
    if mp.get_parameter(text, path, "type") != "FVCoupledForce":
        fail("WRONG_OWNER:" + path)
    if mp.get_parameter(text, path, "variable") != "n_e":
        fail("WRONG_VARIABLE:" + path)
    if mp.get_parameter(text, path, "v") != functor:
        fail("WRONG_SIGNED_FUNCTOR:" + path)
    raw = mp.get_parameter(text, path, "coef")
    if raw is None:
        fail("MISSING_EXPLICIT_COEF:" + path)
    try:
        actual = float(raw)
    except ValueError:
        fail("NONNUMERIC_COEF:" + path)
    if not math.isfinite(actual) or actual <= 0 or not math.isclose(
            actual, coef, rel_tol=1e-14, abs_tol=0):
        fail("COEFFICIENT_DRIFT:" + path)
    for forbidden in ("number_source", "state_form", "n_ref"):
        if mp.get_parameter(text, path, forbidden) is not None:
            fail("DEPRECATED_PARAMETER:" + path)
    return {"kernel": path, "type": "FVCoupledForce", "v": functor,
            "coefficient": actual}


def active_inputs() -> list[dict]:
    from physics_app.ci import check_stage5_h05_runtime as h05
    from physics_app.ci import check_stage5_ei20_runtime as ei20
    from physics_app.ci import check_stage5_edetach_runtime as edetach
    from physics_app.ci import check_r2_o2_ionization_implementation as r2
    from physics_app.ci import check_e8_ei16_energy_runtime as ei16
    from physics_app.ci import check_standard_moose_energy_projection as standard
    from experiments.historical_recipe_support.issue192_s5r import (
        audit_s5r_input, build_s5r_input,
    )
    samples = {
        "EI01": (ROOT / PHYSICAL[0][1]).read_text(),
        "H05": h05.runtime_input(),
        "R2": r2.RUNTIME_INPUT,
        "EI16": ei16.RUNTIME_INPUT,
        "EI16_STANDARD": standard.EI16_INPUT,
        "EI20": ei20.runtime_input(),
        "EDETACH": edetach.text(),
    }
    records = []
    for name, path, target, functor in PHYSICAL:
        original = samples[name]
        # Known active input, not documentation. Do not allow old Factory type.
        if re.search(r"\b" + TARGET + r"\b", original):
            fail("ACTIVE_LEGACY_FACTORY_REFERENCE:" + name)
        item = check_owner(original, target, functor, 1.0)
        item.update(case=name, tracked_consumer=path,
                    input_sha256=hashlib.sha256(original.encode()).hexdigest())
        records.append(item)
    base_path = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
    assembled, meta = build_s5r_input(base_path.read_text())
    if audit_s5r_input(assembled)["status"] != "PASS" or meta["audit"]["status"] != "PASS":
        fail("S5R_CHEMISTRY_AUDIT")
    if TARGET in assembled:
        fail("S5R_ACTIVE_INPUT_LEGACY_FACTORY")
    nref = float(meta["electron_reference_density_m3"])
    if not math.isfinite(nref) or nref <= 0:
        fail("S5R_BAD_NREF")
    item = check_owner(assembled, "FVKernels/s5r_electron_source",
                       "S_e_s5r", 1.0/nref)
    item.update(case="S5R", tracked_consumer="experiments/historical_recipe_support/issue192_s5r.py",
                input_sha256=hashlib.sha256(assembled.encode()).hexdigest(),
                n_ref=nref, full_current_native="BLOCKED_BY_HISTORIC_THERMAL_OWNER")
    records.append(item)
    return records


def check_static_current_source_references() -> dict:
    # Legacy source-read guards were once deliberately active CI. Deleting
    # the C++ source is invalid if any current source attestation still reads it.
    paths = [
        "physics_app/ci/check_r2_o2_ionization_implementation.py",
        "physics_app/ci/check_stage5_h05_runtime.py",
        "physics_app/ci/check_stage5_ei20_runtime.py",
        "physics_app/ci/check_issue402_json_rate_native_p2.py",
    ]
    for path in paths:
        content = (ROOT/path).read_text()
        if "PhysicsFVElectronReactionSource.C" in content:
            fail("ACTIVE_CPP_SOURCE_ATTACHED:" + path)
    return {"active_cpp_source_reads": 0,
            "historical_frozen_docs_mutated": False}


def audit(expected: str, phase: str) -> dict:
    head = exact_head(expected)
    frozen_source(phase)
    inputs = active_inputs()
    guard = check_static_current_source_references()
    if len(inputs) != 8:
        fail("ACTIVE_CONSUMER_COUNT")
    return {
        "schema": SCHEMA, "source_head": head, "phase": phase,
        "current_consumer_count": len(inputs),
        "consumers": inputs, "source_guard": guard,
        "physics_Factory_C_H_deleted": phase == "postcut",
        "P0": "PASS_MIGRATION_CONTRACT",
        "existing_old_new_science_runs": [45230510538, 45234619718, 45239977824],
        "postcut_native_P1_P2_P3": "NOT_ESTABLISHED_BY_THIS_P0",
        "full_coupled_AD_Jacobian": "NOT_PROVEN",
        "legacy_S5R_thermal_registration": "UNRESOLVED",
        "external_dynamic_consumers": "NOT_CLOSED",
        "main_merge_authorized": False,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expected-head", required=True)
    p.add_argument("--phase", choices=("migrate", "postcut"), default="migrate")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        report = audit(args.expected_head, args.phase)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    except (ValueError, AssertionError, OSError) as exc:
        print("ISSUE817_CODE3_CURRENT_CONSUMER_P0_FAIL:" + str(exc)[:450])
        return 1
    print("ISSUE817_CODE3_CURRENT_CONSUMER_P0_PASS head="+report["source_head"]+
          " phase="+report["phase"]+" cases="+str(report["current_consumer_count"]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
