#!/usr/bin/env python3
"""code6 H05 old-vs-conservative conditional Native A/B pilot.

--prepare is P0 input characterization, with NO Native physics execution.
--native invokes an explicitly supplied, immutable local Physics executable.
No mode confers scientific parity, source retirement, or SAFE_DELETE.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
H05 = ROOT / "physics_app/ci/check_stage5_h05_runtime.py"
H05_BLOB = "30253b314e88e9e7779d3a2790f6efdf8be9998a"
INCUMBENT = "PhysicsFVMassFractionTimeDerivative"
CANDIDATE = "PhysicsFVConservativeMassFractionTimeDerivative"
LEGACY_LINE = "type = " + INCUMBENT
CANDIDATE_LINE = "type = " + CANDIDATE
REQUIRED_BLOCKS = ("w_O_time", "w_Om_time")
SOURCE_MODES = {"prepare", "native"}
CSV_NAME = "stage5_h05_runtime_out.csv"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> str:
    command = subprocess.run(["git", "-C", str(root), *args], text=True,
                             capture_output=True, check=True)
    return command.stdout.strip()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def source_module():
    raw = H05.read_bytes()
    if git_blob(raw) != H05_BLOB:
        raise ValueError("CODE6_H05_SOURCE_CHANGED_REVIEW_REQUIRED")
    spec = importlib.util.spec_from_file_location("code6_h05_reference", H05)
    if spec is None or spec.loader is None:
        raise ValueError("CODE6_H05_IMPORT_UNAVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, raw


def pair_inputs(text: str) -> tuple[str, str]:
    """Only replace the two explicit time-kernel type declarations."""
    if text.count(LEGACY_LINE) != 2:
        raise ValueError("CODE6_H05_EXPECTED_TWO_OLD_TIME_KERNELS")
    for block, variable in (("w_O_time", "w_O"), ("w_Om_time", "w_Om")):
        contract = ("[" + block + "]\n    " + LEGACY_LINE +
                    "\n    variable = " + variable + "\n    rho = rho_const")
        if contract not in text:
            raise ValueError("CODE6_H05_BLOCK_BINDING_CHANGED:" + block)
    if "prop_names = 'rho_const T_g'" not in text:
        raise ValueError("CODE6_H05_DENSITY_NAME_CHANGED")
    old, new = text, text.replace(LEGACY_LINE, CANDIDATE_LINE)
    if new.count(CANDIDATE_LINE) != 2 or new.replace(CANDIDATE_LINE, LEGACY_LINE) != old:
        raise ValueError("CODE6_H05_NON_TYPE_CHANGE")
    return old, new


def be_residual_difference(rho_n: float, rho_old: float, w_old: float, dt: float) -> float:
    """Candidate-minus-incumbent under INDEPENDENTLY PROVEN common BE only."""
    if dt <= 0:
        raise ValueError("CODE6_INVALID_DT")
    return (rho_n - rho_old) * w_old / dt


def self_test() -> None:
    minimal = """[FVKernels]
  [w_O_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_O
    rho = rho_const
  []
  [w_Om_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_Om
    rho = rho_const
  []
[]
[FunctorMaterials]
  [const]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const T_g'
  []
[]
"""
    old, new = pair_inputs(minimal)
    assert old.count(LEGACY_LINE) == 2
    assert new.count(CANDIDATE_LINE) == 2
    assert be_residual_difference(2, 2, 0.3, 0.1) == 0
    assert math.isclose(be_residual_difference(3, 2, 0.3, 0.1), 3.0)
    for broken in (minimal.replace("rho = rho_const", "rho = different", 1),
                   minimal.replace("[w_Om_time]", "[other_time]"),
                   minimal.replace(LEGACY_LINE, "type = Unknown", 1)):
        try:
            pair_inputs(broken)
        except ValueError:
            pass
        else:
            raise AssertionError("CODE6_H05_NEGATIVE_MUTATION_NOT_REJECTED")
    try:
        be_residual_difference(2, 2, 1, 0)
    except ValueError:
        pass
    else:
        raise AssertionError("CODE6_ZERO_DT_NOT_REJECTED")
    print("CODE6_AB_PILOT_SELF_TEST=PASS")


def prepare(root: Path, out: Path, head: str) -> dict:
    if git(root, "rev-parse", "HEAD") != head:
        raise ValueError("CODE6_AB_EXACT_HEAD_MISMATCH")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("CODE6_AB_TRACKED_WORKTREE_DIRTY")
    mod, raw = source_module()
    if git_blob(mod.DATABASE.read_bytes()) != "0cc183129408d00ce20dff39719f18486ae6b3dc":
        raise ValueError("CODE6_H05_CHEMISTRY_DRIFT")
    mod.static_gate()
    for relpath, expected in (
        ("physics_app/src/fvkernels/PhysicsFVMassFractionTimeDerivative.C",
         "09b0f60eb6473ac295a690e463198c370fc2870b"),
        ("physics_app/src/fvkernels/PhysicsFVConservativeMassFractionTimeDerivative.C",
         "177a8d74bf9806cf9000f710b6583847ae6c0c58"),
    ):
        if git_blob((root / relpath).read_bytes()) != expected:
            raise ValueError("CODE6_AB_KERNEL_SOURCE_DRIFT:" + relpath)
    old, new = pair_inputs(mod.runtime_input())
    if "state_form = physical_eV" in old or old.count("state_form = log_molar_eV") != 1:
        raise ValueError("CODE6_H05_ELECTRON_STATE_NOT_CANONICAL")
    if not hasattr(mod, "RHO") or not math.isfinite(mod.RHO) or mod.RHO <= 0:
        raise ValueError("CODE6_H05_INVALID_DECLARED_RHO")
    # H05 declares a single literal-valued ADGenericFunctorMaterial, NOT a
    # measured runtime-effective Functor; numerical constancy remains conditional.
    if "type = ADGenericFunctorMaterial" not in old or "prop_values = '" not in old:
        raise ValueError("CODE6_H05_DENSITY_DECLARATION_NOT_VERIFIED")
    out.mkdir(parents=True, exist_ok=True)
    sources = {}
    for label, body in (("incumbent", old), ("candidate", new)):
        work = out / label
        work.mkdir(exist_ok=True)
        path = work / "stage5_h05_runtime.i"
        path.write_text(body, encoding="utf-8")
        sources[label] = {
            "input_path": str(path),
            "input_sha256": sha256_bytes(body.encode("utf-8")),
            "kernel_type": INCUMBENT if label == "incumbent" else CANDIDATE,
            "kernel_blocks": list(REQUIRED_BLOCKS),
        }
    receipt = {
        "schema": "code6.h05_ab_pilot.v0.2",
        "repository_head": head,
        "h05_source_blob": git_blob(raw),
        "chemistry_blob": git_blob(mod.DATABASE.read_bytes()),
        "historical_failed_run": 44546729279,
        "historical_failure_artifact": 14544066987,
        "representation_change": "ACCEPTED_H05_GENERATOR_REBASELINE_NOT_A_B_DELTA",
        "incumbent_source_blob": "09b0f60eb6473ac295a690e463198c370fc2870b",
        "candidate_source_blob": "177a8d74bf9806cf9000f710b6583847ae6c0c58",
        "source_scope": "TWO_H05_DECLARED_TIME_KERNELS",
        "density": {"declared_name": "rho_const",
                    "declared_constant_value": mod.RHO,
                    "effective_runtime_provider": "UNKNOWN"},
        "inputs": sources,
        "input_pair_comparison": "ONLY_TWO_KERNEL_TYPE_LINES_CHANGED",
        "time_integrator": "NOT_SOURCE_PINNED",
        "variable_density_counterexample": "ANALYTICAL_BE_CONDITIONAL_ONLY",
        "native_status": "NOT_RUN",
        "residual_jacobian_parity": "NOT_PROVEN",
        "mass_inventory_parity": "NOT_PROVEN",
        "approved_acceptance_tolerance": "OWNER_UNSPECIFIED",
        "safe_delete": "HOLD",
    }
    return receipt


def read_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) < 2:
        raise ValueError("CODE6_AB_EXPECTED_INITIAL_AND_FINAL_ROWS")
    required = ("time", "w_O_avg", "w_Om_avg", "w_O2_avg")
    if any(key not in rows[0] for key in required):
        raise ValueError("CODE6_AB_MISSING_SPECIES_OBSERVABLE")
    parsed = [{key: float(value) for key, value in row.items() if value not in ("", None)}
              for row in rows]
    if any(not math.isfinite(value) for row in parsed for value in row.values()):
        raise ValueError("CODE6_AB_NONFINITE_OUTPUT")
    return parsed


def compare_rows(old: list[dict], new: list[dict]) -> dict:
    if len(old) != len(new) or [sorted(r) for r in old] != [sorted(r) for r in new]:
        raise ValueError("CODE6_AB_OUTPUT_SHAPE_MISMATCH")
    differences = {}
    if [r["time"] for r in old] != [r["time"] for r in new]:
        raise ValueError("CODE6_AB_TIME_GRID_MISMATCH")
    if [r["time"] for r in old] != [0.0, 1e-7]:
        raise ValueError("CODE6_AB_UNEXPECTED_H05_TIME_GRID")
    for field in sorted(old[0]):
        differences[field] = {
            "max_abs": max(abs(a[field] - b[field]) for a, b in zip(old, new)),
            "max_rel": max(abs(a[field] - b[field]) /
                           max(abs(a[field]), abs(b[field]), 1e-30)
                           for a, b in zip(old, new)),
        }
    evolving = any(abs(old[-1][field] - old[0][field]) > 1e-14
                   for field in ("w_O_avg", "w_Om_avg"))
    if not evolving:
        raise ValueError("CODE6_AB_ZERO_EVOLUTION_NOT_DISCRIMINATING")
    return {"row_count": len(old), "observed_csv_differences": differences,
            "nontrivial_species_evolution": evolving,
            "scientific_acceptance": "NOT_EVALUATED_UNAPPROVED_TOLERANCE"}


def run_native(root: Path, out: Path, executable: Path, receipt: dict,
               build_base_ref: str) -> dict:
    if not executable.is_file():
        raise ValueError("CODE6_AB_EXECUTABLE_NOT_FOUND")
    execution = {"executable_sha256": sha256_bytes(executable.read_bytes()),
                 "build_base_ref": build_base_ref,
                 "cases": {}, "native_status": "RUNNING_NOT_YET_VERIFIED"}
    receipt["native_evidence"] = execution
    receipt["native_status"] = "RUNNING_NOT_YET_VERIFIED"
    module, _ = source_module()
    outputs = {}
    for label in ("incumbent", "candidate"):
        work = out / label
        execution["cases"][label] = {"p2": "NOT_RUN", "p3": "NOT_RUN"}
        path = work / "stage5_h05_runtime.i"
        if sha256_bytes(path.read_bytes()) != receipt["inputs"][label]["input_sha256"]:
            raise ValueError("CODE6_AB_INPUT_DRIFT")
        module.preflight(path)
        for task, cmd in (
            ("p2_check_input", [str(executable), "--check-input", "-i", "stage5_h05_runtime.i"]),
            ("p3_run", [str(executable), "-i", "stage5_h05_runtime.i"]),
        ):
            proc = subprocess.run(cmd, cwd=work, text=True, capture_output=True)
            (work / (task + ".stdout.log")).write_text(proc.stdout, encoding="utf-8")
            (work / (task + ".stderr.log")).write_text(proc.stderr, encoding="utf-8")
            execution["cases"][label]["p2" if task == "p2_check_input" else "p3"] = (
                "PASS" if proc.returncode == 0 else "FAIL")
            if proc.returncode:
                execution["native_status"] = "FAILED_AT_" + label.upper() + "_" + task.upper()
                receipt["native_status"] = execution["native_status"]
                raise ValueError(f"CODE6_AB_{label}_{task}_FAILED:{proc.returncode}")
        path = work / CSV_NAME
        records = read_csv(path)
        # The pre-existing H05 reference oracle is a limited reaction/species
        # result check, NOT an independent AD Jacobian or parity acceptance.
        module.validate([{key: str(value) for key, value in row.items()} for row in records])
        execution["cases"][label].update({
            "csv_sha256": sha256_bytes(path.read_bytes()),
            "rows": len(records),
            "h05_reference_checker": "PASSED_LIMITED_MODEL_SCOPE"})
        outputs[label] = records
    execution["trajectory_comparison"] = compare_rows(outputs["incumbent"], outputs["candidate"])
    execution["native_status"] = "EXPLORATORY_P2_P3_RUNS_COMPLETED"
    receipt["native_status"] = execution["native_status"]
    execution["effective_time_integrator"] = "NOT_INDEPENDENTLY_PINNED"
    execution["independent_ad_jacobian_parity"] = "NOT_EVALUATED"
    execution["variable_density_native_counterexample"] = "NOT_RUN"
    execution["scientific_acceptance"] = "HOLD"
    return receipt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--mode", choices=("prepare", "native"))
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--expected-head")
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--executable", type=Path)
    p.add_argument("--build-base-ref", default="UNKNOWN")
    args = p.parse_args()
    receipt = None
    try:
        if args.self_test:
            self_test()
            if args.mode is None:
                return 0
        if args.mode is None or args.expected_head is None or args.output_dir is None:
            p.error("--mode, --expected-head and --output-dir are required")
        if args.mode == "native" and args.executable is None:
            p.error("--native mode requires --executable")
        root = args.root.resolve()
        if root != ROOT.resolve():
            raise ValueError("CODE6_AB_ROOT_MUST_MATCH_PINNED_SOURCE_TREE")
        out = args.output_dir.resolve()
        receipt = prepare(root, out, args.expected_head)
        if args.mode == "native":
            receipt = run_native(root, out, args.executable.resolve(), receipt,
                                 args.build_base_ref)
        (out / "code6-h05-ab-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("CODE6_AB_PREPARE=PASS")
        print("CODE6_AB_NATIVE=" + receipt["native_status"])
        print("CODE6_SAFE_DELETE=HOLD")
        return 0
    except (OSError, ValueError, KeyError, AssertionError,
            subprocess.CalledProcessError) as exc:
        if receipt is not None and args.output_dir is not None:
            receipt["native_status"] = "FAILED_OR_INCOMPLETE"
            receipt["native_error"] = str(exc)
            receipt["safe_delete"] = "HOLD"
            out = args.output_dir.resolve()
            out.mkdir(parents=True, exist_ok=True)
            (out / "code6-h05-ab-receipt.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("CODE6_AB_PILOT=FAIL:" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
