#!/usr/bin/env python3
"""G7 PETSc finite-difference perturbation sweep and difference-matrix localization.

This is a diagnostic, NOT a way to post-hoc relax the predeclared 1e-8
Jacobian tolerance. Synthetic 3x3 case only; full 417/941 remains unverified.
Reuses exact G6B PhysicsApp ELF and pinned OCI. No protected chemistry data.

PETSc SNESComputeJacobianDefault documents -snes_test_err as the sqrt of
estimated function evaluation error controlling its FD perturbation.
The specified sweep is fixed in source and is not calibrated to force PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

from issue652_g7_native_ad_jacobian import (
    SOURCE, OCI, RELATIVE_JAC_TOL, NativeJacobianHold,
    docker_command, generated_input, private_workspace, sha256,
    verify_binary_and_source,
)
from physics_harness.adapters.petsc.jacobian import parse_comparisons

# Five predeclared perturbations around PETSc's ~1e-8 default.
FD_STEPS = (1e-5, 1e-6, 1e-7, 1e-8, 1e-9)
CONTROL_STEPS = (1e-6, 1e-8)
MAX_TOTAL_SECONDS = 540
MAX_PER_INVOCATION_SECONDS = 75
MAX_LOG_CHARS = 8_000_000
VALUE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
PAIR = re.compile(r"\((\d+)\s*,\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\)")
ROW = re.compile(r"^\s*row\s+(\d+)\s*:\s*(.*)$", re.IGNORECASE)
MATRIX = re.compile(r"^\s*Mat Object:.*$", re.IGNORECASE | re.MULTILINE)

CHARGE_KERNEL = """  [poisson_charge_source]
    type = FunctorKernel
    variable = potential
    functor = poisson_source
    functor_on_rhs = true
  []
"""


class SweepHold(ValueError):
    pass


def charge_disabled_input() -> str:
    original = generated_input()
    if original.count(CHARGE_KERNEL) != 1:
        raise SweepHold("FIXTURE_CHARGE_KERNEL_NOT_UNIQUE")
    return original.replace(CHARGE_KERNEL, "")


def command(source: Path, workspace: Path, fd_step: float, *, view: bool) -> list[str]:
    if fd_step not in FD_STEPS:
        raise SweepHold("FD_STEP_NOT_PREDECLARED")
    argv = docker_command(source, workspace, check=False)
    argv[-1] += " -snes_test_err {:.0e}".format(fd_step)
    if view:
        argv[-1] += " -snes_test_jacobian_view"
    return argv


def matrix_summary(log: str) -> dict:
    """Read small PETSc ASCII MatView blocks without saving matrices or raw logs.

    PETSc's documented presentation order is assembled, finite-difference, diff.
    We report numerical matrix indices only (variable DOF ownership unproven).
    """
    begins = list(MATRIX.finditer(log))
    blocks = []
    for k, start in enumerate(begins):
        end = begins[k+1].start() if k+1 < len(begins) else len(log)
        region = log[start.end():end]
        entries = {}
        active = None
        for line in region.splitlines():
            match = ROW.match(line)
            if match:
                active = int(match.group(1))
                tail = match.group(2)
            elif active is not None and line.startswith(" " * 4):
                tail = line.strip()
            else:
                active = None
                continue
            for column, value in PAIR.findall(tail):
                item = float(value)
                if not math.isfinite(item):
                    raise SweepHold("NONFINITE_VIEW_ENTRY")
                entries[(active, int(column))] = item
        if entries:
            blocks.append(entries)
    if len(blocks) < 3:
        return {
            "view_blocks_with_numeric_rows": len(blocks),
            "comparison_matrix_entries": "NOT_EXTRACTED",
            "block_mapping": "UNVERIFIED",
        }
    assembly, fd, difference = blocks[:3]
    coordinates = set(assembly) | set(fd)
    calculated = {key: assembly.get(key, 0.) - fd.get(key, 0.) for key in coordinates}
    err = math.sqrt(sum(v*v for v in calculated.values()))
    norm = math.sqrt(sum(v*v for v in assembly.values()))
    top = sorted(calculated.items(), key=lambda kv: abs(kv[1]), reverse=True)[:12]
    # The third MatView is a cross-check only. Do not assume exact alignment
    # unless its printed entries overlap the recomputed difference.
    common = set(difference) & set(calculated)
    consistency = (
        max((abs(difference[k]-calculated[k]) for k in common), default=None)
    )
    return {
        "view_blocks_with_numeric_rows": len(blocks),
        "assembled_nonzero_printed": len(assembly),
        "fd_nonzero_printed": len(fd),
        "difference_nonzero_printed": len(difference),
        "relative_difference_recomputed_from_view": err / norm if norm else None,
        "diff_norm_from_view": err,
        "max_third_view_entry_consistency_error": consistency,
        "third_view_overlapping_entries": len(common),
        "top_matrix_differences_unmapped": [
            {"row": key[0], "column": key[1], "assembled_minus_fd": value,
             "assembled": assembly.get(key, 0.), "finite_difference": fd.get(key, 0.)}
            for key, value in top
        ],
        "block_mapping": "UNVERIFIED_NO_DOF_VARIABLE_INDEX_MAP",
    }


def classify(log: str, *, returncode: int, timed_out: bool,
             fd_step: float, view: bool) -> dict:
    checks = parse_comparisons(log)
    norm_values = [item["relative_frobenius_error"] for item in checks]
    valid = (
        not timed_out and returncode == 0 and bool(checks)
        and all(math.isfinite(x) and x >= 0 for x in norm_values)
    )
    result = {
        "fd_step": fd_step, "returncode": returncode, "timed_out": timed_out,
        "comparison_count": len(checks),
        "worst_relative_frobenius_error": max(norm_values) if valid else None,
        "strict_predeclared_tolerance": RELATIVE_JAC_TOL,
        "numerically_within_strict_tolerance": (
            max(norm_values) <= RELATIVE_JAC_TOL if valid else False
        ),
        "native_status": "COMPARED" if valid else "HOLD",
        "log_sha256": hashlib.sha256(log.encode()).hexdigest(),
    }
    if view:
        result["matrix_view"] = matrix_summary(log)
    return result


def invoke(argv: list[str], *, timeout: int) -> tuple[int, str, bool]:
    try:
        completed = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            timeout=timeout, check=False,
            env={key: value for key, value in os.environ.items()
                 if key != "PROTECTED_ARCHIVE_B64"},
        )
    except subprocess.TimeoutExpired:
        return 124, "", True
    log = completed.stdout or ""
    if len(log) > MAX_LOG_CHARS:
        raise SweepHold("SYNTHETIC_PETSC_MATVIEW_LOG_BUDGET")
    return completed.returncode, log, False


def sweep(*, source: Path, manifest: Path, output: Path, authorize: bool) -> dict:
    if not authorize:
        raise SweepHold("NATIVE_EXPLICIT_AUTHORIZATION_REQUIRED")
    if output.exists() or output.is_symlink():
        raise SweepHold("REPORT_OVERWRITE_DENIED")
    identity = verify_binary_and_source(source, manifest)
    report = {
        "schema": "issue652.g7.fd_step_diagnostic.v1",
        **identity,
        "prior_default_fd_relative_frobenius_error": 7.08621e-5,
        "predeclared_relative_tolerance": RELATIVE_JAC_TOL,
        "fd_step_values": list(FD_STEPS),
        "control_fd_step_values": list(CONTROL_STEPS),
        "snes_test_err_definition": "sqrt_estimated_residual_error",
        "fixture": "3x3_synthetic_charge_functor_poisson",
        "sweep": [],
        "charge_free_control": [],
        "component_jacobian_strict_status": "HOLD_PENDING_REVIEW",
        "actual_s6_coupled_ad_jacobian": "UNVERIFIED",
        "old_new_poisson_parity": "UNVERIFIED",
        "science": "SCIENCE_HOLD",
    }
    started = time.monotonic()
    try:
        with private_workspace() as folder:
            fixture = folder / "g7_micro_poisson.i"
            fixture.write_text(generated_input(), encoding="utf-8")
            report["charge_on_fixture_sha256"] = sha256(fixture)
            for mode, steps in (("sweep", FD_STEPS),
                                ("charge_free_control", CONTROL_STEPS)):
                if mode == "charge_free_control":
                    fixture.write_text(charge_disabled_input(), encoding="utf-8")
                    report["charge_free_fixture_sha256"] = sha256(fixture)
                p2 = docker_command(source, folder, check=True)
                rc_check, log_check, timed = invoke(p2, timeout=MAX_PER_INVOCATION_SECONDS)
                report[mode + "_p2"] = (
                    "PASS" if rc_check == 0 and "Syntax OK" in log_check and not timed
                    else "HOLD"
                )
                if report[mode + "_p2"] != "PASS":
                    report[mode + "_p2_rc"] = rc_check
                    break
                for value in steps:
                    if time.monotonic() - started >= MAX_TOTAL_SECONDS:
                        report["sweep_timeout"] = True
                        break
                    view = mode == "sweep" and value == 1e-7
                    rc, log, timeout = invoke(
                        command(source, folder, value, view=view),
                        timeout=MAX_PER_INVOCATION_SECONDS,
                    )
                    one = classify(log, returncode=rc, timed_out=timeout,
                                   fd_step=value, view=view)
                    report[mode].append(one)
                    print("G7_FD_STEP", mode, f"{value:.0e}",
                          "RC", rc, "REL", one["worst_relative_frobenius_error"],
                          "STATUS", one["native_status"], flush=True)
                if report.get("sweep_timeout"):
                    break
            on = report["sweep"]
            off = report["charge_free_control"]
            complete = (
                len(on) == len(FD_STEPS) and len(off) == len(CONTROL_STEPS)
                and all(row["native_status"] == "COMPARED" for row in on + off)
                and report.get("sweep_p2") == "PASS"
                and report.get("charge_free_control_p2") == "PASS"
            )
            report["diagnostic_status"] = ("PASS_SWEEP_EVIDENCE_ONLY" if complete
                                           else "HOLD_INCOMPLETE_DIAGNOSTIC")
            report["lowest_observed_charge_on_relative_error"] = min(
                (v["worst_relative_frobenius_error"] for v in on
                 if v["worst_relative_frobenius_error"] is not None), default=None)
            # Even a small FD norm is not sufficient to assign offdiagonal
            # ownership or accept a different test tolerance post hoc.
            report["component_jacobian_strict_status"] = "HOLD_CAUSE_NOT_FULLY_ATTRIBUTED"
            report["elapsed_seconds"] = round(time.monotonic()-started, 2)
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True,
                                     allow_nan=False) + "\n", encoding="utf-8")
    print("G7_FD_SWEEP_STATUS", report.get("diagnostic_status"),
          "STRICT_GATE", report["component_jacobian_strict_status"],
          "SCIENCE_HOLD", flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-native", action="store_true")
    args = parser.parse_args()
    try:
        evidence = sweep(source=args.source, manifest=args.manifest,
                         output=args.output, authorize=args.authorize_native)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("G7_FD_SWEEP_HOLD", type(exc).__name__, flush=True)
        return 2
    return 0 if evidence.get("diagnostic_status") == "PASS_SWEEP_EVIDENCE_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
