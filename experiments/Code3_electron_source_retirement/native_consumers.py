"""Code3 #817: isolated, exact-head H05/R2 Native source A/B.

Output is a sanitized SHA + scalar comparison receipt. Source input/CSV bytes
and protected data are NEVER uploaded; no production generator is modified.
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

from experiments.Code3_electron_source_retirement import consumer_pairs as cp
from experiments.Code3_electron_source_retirement import run as code3
from physics_app.ci import check_r2_o2_ionization_implementation as r2
from physics_app.ci import check_stage5_h05_runtime as h05

ROOT = Path(__file__).resolve().parents[2]
OCI = os.environ.get("OCI", "")
HEAD = os.environ.get("SOURCE_HEAD", "")
REL_TOL = 1e-8
ABS_TOL = 1e-10


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def launch(work: Path, stem: str, *, syntax: bool) -> dict:
    """One same container and binary per source arm, without host Python MOOSE."""
    command = (
        "set -euo pipefail; source /environment; "
        "/workspace/physics_app/physics-opt " +
        ("--check-input " if syntax else "") +
        "-i " + stem + ".i"
    )
    result = subprocess.run(
        ["docker", "run", "--rm", "--platform", "linux/amd64",
         "--entrypoint", "/bin/bash", "--user", "0:0", "--workdir", "/case",
         "-v", str(ROOT) + ":/workspace", "-v", str(work) + ":/case",
         OCI, "-lc", command],
        text=True, capture_output=True, timeout=300, check=False,
    )
    output = result.stdout + result.stderr
    return {
        "returncode": result.returncode,
        "output_sha256": sha(output.encode()),
        "syntax_ok": "Syntax OK" in output if syntax else None,
        "error_tail": output[-1600:] if result.returncode else None,
    }


def compare_csv(a: Path, b: Path) -> dict:
    with a.open(newline="") as stream:
        rows_a = list(csv.DictReader(stream))
    with b.open(newline="") as stream:
        rows_b = list(csv.DictReader(stream))
    if len(rows_a) < 2 or len(rows_b) != len(rows_a):
        raise ValueError("CSV_ROWS_MISSING_OR_DIFFERENT")
    if list(rows_a[0]) != list(rows_b[0]) or "time" not in rows_a[0]:
        raise ValueError("CSV_COLUMNS_CHANGED")
    fields = [x for x in rows_a[0] if x != "time"]
    if not fields:
        raise ValueError("CSV_NO_SCALAR_OBSERVABLES")
    deltas = {}
    for name in ("time", *fields):
        max_relative = 0.
        for ra, rb in zip(rows_a, rows_b):
            x, y = float(ra[name]), float(rb[name])
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError("CSV_NONFINITE_" + name)
            max_relative = max(max_relative,
                               abs(x - y) / max(abs(x), abs(y), 1e-300))
            if not math.isclose(x, y, rel_tol=REL_TOL, abs_tol=ABS_TOL):
                raise ValueError("CSV_BOUNDED_PARITY_FAIL_" + name)
        deltas[name] = max_relative
    return {"rows": len(rows_a), "numeric_fields": len(fields),
            "max_relative_delta_by_field": deltas,
            "original_csv_sha256": sha(a.read_bytes()),
            "candidate_csv_sha256": sha(b.read_bytes()),
            "all_numeric_fields_bounded_equal": True}


def pair_recipe(case: str):
    if case == "H05":
        old, new, info = cp.h05_pair()
        db = str(h05.DATABASE.resolve())
        container_db = "/workspace/physics_app/data/heavy_reactions/stage5_s5e_h05_oxygen_heavy.json"
        if old.count(db) != 1 or new.count(db) != 1:
            raise ValueError("H05_CURRENT_DB_REFERENCE_DRIFT")
        # Relocation is applied identically on both arms: only target block differs.
        return old.replace(db, container_db), new.replace(db, container_db), info
    if case == "R2":
        return cp.r2_pair()
    raise ValueError("UNSUPPORTED_CASE")


def execute() -> dict:
    if not OCI.startswith("ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:"):
        raise ValueError("OCI_DIGEST_MISSING")
    if len(HEAD) != 40 or any(c not in "0123456789abcdef" for c in HEAD):
        raise ValueError("EXACT_HEAD_MISSING")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                     cwd=ROOT, text=True).strip()
    if actual != HEAD:
        raise ValueError("SOURCE_HEAD_CHANGED")
    binary = ROOT / "physics_app/physics-opt"
    if binary.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("NO_EXACT_PHYSICS_ELF")
    result = {
        "schema": "issue817.code3.h05_r2_native_ab.v0.1",
        "source_head": HEAD, "oci": OCI,
        "binary_sha256": sha(binary.read_bytes()),
        "P0": "SOURCE_BOUND", "cases": {},
        "normalized_s5r_p3": "NOT_EXECUTED",
        "full_AD_Jacobian": "NOT_PROVEN",
        "all_current_consumers_migrated": False,
        "physics_cpp_source_cut": False,
        "safe_delete": False,
    }
    evidence = ROOT / "evidence/code3_h05_r2_native_receipt.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    all_good = True
    for case in ("H05", "R2"):
        old, new, meta = pair_recipe(case)
        if code3._outside_target(old, cp.H05_TARGET) != code3._outside_target(new, cp.H05_TARGET):
            raise ValueError("NON_TARGET_INPUT_BYTES_CHANGED")
        record = {
            "source_functor": meta["source_functor"],
            "state_mode": meta["mode"],
            "coef": meta["coefficient"],
            "original_sha256": sha(old.encode()),
            "candidate_sha256": sha(new.encode()),
            "same_non_target_input_bytes": True,
        }
        result["cases"][case] = record
        with tempfile.TemporaryDirectory(prefix="code3-" + case + "-") as temp:
            work = Path(temp)
            (work / "original.i").write_text(old)
            (work / "candidate.i").write_text(new)
            if case == "R2":
                (work / "r2_o2_ionization_runtime_table.txt").write_text(
                    "".join(f"{energy:.8g} {rate:.17g}\n"
                            for energy, rate in r2.RATE_TABLE))
            for arm in ("original", "candidate"):
                record[arm] = {"P2": launch(work, arm, syntax=True)}
            p2pass = all(record[arm]["P2"]["returncode"] == 0
                         and record[arm]["P2"]["syntax_ok"]
                         for arm in ("original", "candidate"))
            record["both_P2_pass"] = p2pass
            if p2pass:
                for arm in ("original", "candidate"):
                    record[arm]["P3"] = launch(work, arm, syntax=False)
                p3pass = all(record[arm]["P3"]["returncode"] == 0
                             for arm in ("original", "candidate"))
                record["both_P3_runs_pass"] = p3pass
                if p3pass:
                    try:
                        record["full_output_observables"] = compare_csv(
                            work / "original_out.csv", work / "candidate_out.csv")
                        # Current domain-owned source-closure validators: independent from A/B numeric equality
                        with (work / "original_out.csv").open(newline="") as stream:
                            rowset = list(csv.DictReader(stream))
                        if case == "H05":
                            h05.validate(rowset)
                        else:
                            r2.validate_runtime_rows(rowset)
                        record["original_domain_source_closure"] = "PASS"
                    except (ValueError, KeyError, AssertionError, OSError) as exc:
                        record["comparison_or_closure_error"] = type(exc).__name__ + ":" + str(exc)[:200]
                        p3pass = False
                record["accepted_bounded_parity"] = (
                    p3pass and record.get("original_domain_source_closure") == "PASS"
                    and record.get("full_output_observables", {}).get(
                        "all_numeric_fields_bounded_equal", False))
            else:
                record["accepted_bounded_parity"] = False
            all_good &= bool(record["accepted_bounded_parity"])
            evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    result["status"] = "PASS_H05_R2_BOUND_NATIVE_NOT_GLOBAL" if all_good else "HOLD_NATIVE_OR_CLOSURE"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("ISSUE817_H05_R2_NATIVE=" + result["status"])
    return result


def main() -> int:
    try:
        result = execute()
    except Exception as exc:
        print("ISSUE817_H05_R2_NATIVE_EXCEPTION:" + type(exc).__name__ + ":" + str(exc)[:400])
        return 1
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
