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

# Nine predeclared perturbations spanning truncation- and rounding-dominated regimes.
FD_STEPS = (1e-5, 1e-6, 1e-7, 1e-8, 1e-9, 1e-10, 1e-11, 1e-12, 1e-13)
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
    without_charge = original.replace(CHARGE_KERNEL, "")
    # Without charge all variables are initially at their Dirichlet values:
    # SNES converges without ever forming a Jacobian. Perturb only the
    # potential initial state (linear diffusion Jacobian is state independent)
    # to force the exact same PETSc comparison path.
    old = "  [potential]" + chr(10) + "    initial_condition = 0.0"
    if without_charge.count(old) != 1:
        raise SweepHold("POTENTIAL_INITIAL_STATE_NOT_UNIQUE")
    return without_charge.replace(old, old.replace("0.0", "0.1"))


def command(source: Path, workspace: Path, fd_step: float, *, view: bool) -> list[str]:
    if fd_step not in FD_STEPS:
        raise SweepHold("FD_STEP_NOT_PREDECLARED")
    argv = docker_command(source, workspace, check=False)
    argv[-1] += " -snes_test_err {:.0e}".format(fd_step)
    if view:
        argv[-1] += " -snes_test_jacobian_view"
    return argv


def matrix_summary(log: str) -> dict:
    """Localize PETSc's *directly printed* J-Jfd matrix entries.

    MatView often rounds large J and Jfd entries to ~6 printed digits.
    Subtracting those rounded matrices destroys a small, genuine residual.
    Never compute the physics comparison from that rounded subtraction.
    PETSc presents successive (J, Jfd, J-Jfd) triplets at different SNES
    iterates. Variable/DOF ownership is NOT inferred from raw indices.
    """
    begins = list(MATRIX.finditer(log))
    blocks = []
    for k, start in enumerate(begins):
        end = begins[k + 1].start() if k + 1 < len(begins) else len(log)
        entries = {}
        active = None
        for line in log[start.end():end].splitlines():
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
                numeric = float(value)
                if not math.isfinite(numeric):
                    raise SweepHold("NONFINITE_MATVIEW_ENTRY")
                entries[(active, int(column))] = numeric
        if entries:
            blocks.append(entries)
    results = []
    for i in range(len(blocks) // 3):
        assembled, fd, diff = blocks[3*i:3*i+3]
        norm_j = math.sqrt(sum(value*value for value in assembled.values()))
        norm_difference = math.sqrt(sum(value*value for value in diff.values()))
        if norm_j == 0:
            continue
        rounded_disagreement = max(
            (abs(difference-(assembled.get(key, 0.)-fd.get(key, 0.)))
             for key, difference in diff.items()), default=None
        )
        top = sorted(diff.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]
        results.append({
            "group_index": i,
            "relative_difference_direct_from_matview": norm_difference / norm_j,
            "matrix_difference_norm_from_matview": norm_difference,
            "printed_assembled_entries": len(assembled),
            "printed_fd_entries": len(fd),
            "printed_difference_entries": len(diff),
            "largest_rounding_disagreement_if_subtracted": rounded_disagreement,
            "top_matrix_differences_unmapped": [
                {"row": key[0], "column": key[1], "jac_minus_fd": value}
                for key, value in top
            ],
        })
    largest = max(results,
                  key=lambda entry: entry["relative_difference_direct_from_matview"],
                  default=None)
    return {
        "view_blocks_with_numeric_rows": len(blocks),
        "view_triplet_count": len(results),
        "view_group_ratios": [
            {"group_index": item["group_index"],
             "relative_difference_direct_from_matview":
                 item["relative_difference_direct_from_matview"]}
            for item in results
        ],
        "selected_group_index": largest["group_index"] if largest else None,
        "relative_difference_direct_from_matview": (
            largest["relative_difference_direct_from_matview"] if largest else None
        ),
        "largest_rounding_disagreement_if_subtracted": (
            largest["largest_rounding_disagreement_if_subtracted"] if largest else None
        ),
        "top_matrix_differences_unmapped": (
            largest["top_matrix_differences_unmapped"] if largest else []
        ),
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
        "control_potential_initial_excitation": 0.1,
        "control_interpretation": "charge_kernel_removed_and_linear_potential_initial_state_perturbed",
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
                    if view:
                        mat = one.get("matrix_view", {})
                        print("G7_MATVIEW_NUMERIC_JSON=" + json.dumps({
                            "view_blocks": mat.get("view_blocks_with_numeric_rows"),
                            "direct_matview_relative": mat.get("relative_difference_direct_from_matview"),
                            "all_group_ratios": mat.get("view_group_ratios"),
                            "print_rounding_disagreement": mat.get("largest_rounding_disagreement_if_subtracted"),
                            "top_diffs": mat.get("top_matrix_differences_unmapped", [])[:5],
                            "variable_block_mapping": mat.get("block_mapping"),
                        }, separators=(",", ":"), allow_nan=False), flush=True)
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
