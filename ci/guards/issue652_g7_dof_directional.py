#!/usr/bin/env python3
"""G7 synthetic Poisson/Charge DOF mapping and independent directional derivative.

Sources:
  - Exact source-bound ELF from full100 G6-B build.
  - MOOSE DOFMap output (true global DOF -> named variable).
  - PETSc SNESTestJacobian's assembled Jacobian matrix.
  - Independent Q1 finite-element integral for 3x3 GeneratedMesh and
    independent central perturbation of the continuous Poisson charge residual.
All outputs diagnostic. This does not imply full S6 Old/New parity or P4.
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
    OCI, SOURCE, NativeJacobianHold, docker_command, generated_input,
    private_workspace, sha256, verify_binary_and_source,
)
from issue652_g7_fd_step_sweep import (
    MATRIX, PAIR, ROW, invoke,
)

VARIABLES = ("potential", "log_O2p", "log_Op", "log_e", "log_Om")
CHARGED = ("log_O2p", "log_Op", "log_e", "log_Om")
STATES = {"log_O2p": -15.0, "log_Op": -16.5,
          "log_e": -16.0, "log_Om": -17.0}
SIGNS = {"log_O2p": +1.0, "log_Op": +1.0,
         "log_e": -1.0, "log_Om": -1.0}
NA = 6.02214076e23
E_OVER_EPS = 1.8095128179727827e-8
# Since Q1 on a regular 3x3 mesh has four interior nodes:
# each interior test basis integrates to 1/9 and the total is 4/9.
INTERIOR_TEST_SUM = 4.0 / 9.0
FD_DIRECTION_STEPS = (1e-3, 1e-4, 1e-5)
PREFERRED_STEP = 1e-4
MAX_MATRIX_DOFS = 512
MAX_LOG_CHARS = 8_000_000
MAX_DURATION_SECONDS = 300
# Independent block magnitude tolerance: MatView is ASCII-rounded, and
# this test checks separately assembled charge coupling, not PETSc J-Jfd.
ANALYTIC_BLOCK_REL_TOL = 1e-4
DIRECTIONAL_FD_REL_TOL = 5e-7


class BlockHold(ValueError):
    pass


def fixture() -> str:
    base = generated_input()
    before = "  checkpoint = false\n[]"
    after = """  checkpoint = false
  [g7_dofmap]
    type = DOFMap
    execute_on = 'initial'
    output_file = false
    output_screen = true
  []
[]"""
    if base.count(before) != 1:
        raise BlockHold("DOFMAP_INSERTION_ANCHOR_MISSING")
    return base.replace(before, after)


def parse_dofmap(log: str) -> dict:
    decoder = json.JSONDecoder()
    candidates = []
    for found in re.finditer(r'\{"ndof"\s*:', log):
        try:
            data, _ = decoder.raw_decode(log[found.start():])
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and "vars" in data:
            candidates.append(data)
    if len(candidates) != 1:
        raise BlockHold("ONE_MOOSE_DOFMAP_JSON_REQUIRED")
    obj = candidates[0]
    total = obj.get("ndof")
    if type(total) is not int or not 0 < total <= MAX_MATRIX_DOFS:
        raise BlockHold("INVALID_NONLINEAR_DOF_COUNT")
    variables = {}
    inverse = {}
    raw_vars = obj.get("vars", [])
    if not isinstance(raw_vars, list) or len(raw_vars) != len(VARIABLES):
        raise BlockHold("DOFMAP_VARIABLE_CARDINALITY")
    for entry in raw_vars:
        name = entry.get("name") if isinstance(entry, dict) else None
        if name not in VARIABLES or name in variables:
            raise BlockHold("DOFMAP_UNKNOWN_OR_DUPLICATE_VARIABLE")
        subs = entry.get("subdomains", [])
        if not isinstance(subs, list) or not subs:
            raise BlockHold("DOFMAP_SUBDOMAINS_MISSING")
        dofs = set()
        for sub in subs:
            if not isinstance(sub, dict) or not isinstance(sub.get("dofs"), list):
                raise BlockHold("DOFMAP_DOFS_NOT_LIST")
            for raw in sub["dofs"]:
                if type(raw) is not int or not 0 <= raw < total:
                    raise BlockHold("DOFMAP_DOF_OUT_OF_RANGE")
                dofs.add(raw)
        if not dofs:
            raise BlockHold("DOFMAP_VARIABLE_HAS_NO_DOFS")
        for dof in dofs:
            if dof in inverse:
                raise BlockHold("DOFMAP_DOF_ASSIGNED_TO_MULTIPLE_VARIABLES")
            inverse[dof] = name
        variables[name] = sorted(dofs)
    if set(variables) != set(VARIABLES) or set(inverse) != set(range(total)):
        raise BlockHold("DOFMAP_NOT_FULL_NONLINEAR_PARTITION")
    return {"ndof": total, "variables": variables, "owners": inverse}


def read_petsc_matrices(log: str, ndof: int) -> list[dict]:
    starts = list(MATRIX.finditer(log))
    numeric_blocks = []
    for index, marker in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(log)
        block = {}
        active_row = None
        for line in log[marker.end():end].splitlines():
            match = ROW.match(line)
            if match:
                active_row = int(match.group(1))
                data = match.group(2)
            elif active_row is not None and line.startswith("    "):
                data = line.strip()
            else:
                active_row = None
                continue
            if not 0 <= active_row < ndof:
                raise BlockHold("MATVIEW_ROW_OUTSIDE_NONLINEAR_DOFMAP")
            for col, item in PAIR.findall(data):
                j, val = int(col), float(item)
                if not 0 <= j < ndof or not math.isfinite(val):
                    raise BlockHold("MATVIEW_COLUMN_OR_VALUE_INVALID")
                block[(active_row, j)] = val
        if block:
            numeric_blocks.append(block)
    if len(numeric_blocks) < 3 or len(numeric_blocks) % 3:
        raise BlockHold("PETSC_J_JFD_DIFF_TRIPLETS_MISSING")
    return [
        {"assembled": numeric_blocks[i],
         "finite_difference": numeric_blocks[i + 1],
         "direct_difference": numeric_blocks[i + 2]}
        for i in range(0, len(numeric_blocks), 3)
    ]


def source_directional(phi_test_integral: float, states: dict, var: str,
                       perturb: float) -> float:
    """Independent Poisson RHS residual tested against global log-state shift."""
    if var not in CHARGED or perturb <= 0:
        raise BlockHold("INVALID_DIRECTIONAL_PERTURBATION")
    def total(delta):
        terms = sum(SIGNS[key] * NA * math.exp(
            states[key] + (delta if key == var else 0.)) for key in CHARGED)
        return -E_OVER_EPS * phi_test_integral * terms
    return (total(perturb) - total(-perturb)) / (2.0 * perturb)


def predicted_block_sum(var: str) -> float:
    """Exact Q1 mass-basis integrated derivative over all interior phi rows."""
    return (-E_OVER_EPS * SIGNS[var] * NA
            * math.exp(STATES[var]) * INTERIOR_TEST_SUM)


def analyze_jacobian(assembled: dict, map_: dict) -> dict:
    owners = map_["owners"]
    phi = set(map_["variables"]["potential"])
    records = {}
    for species in CHARGED:
        cols = set(map_["variables"][species])
        entries = [(i, j, value) for (i, j), value in assembled.items()
                   if i in phi and j in cols and value != 0.]
        active_rows = {i for i, _, _ in entries}
        if len(active_rows) != 4 or any(owners.get(i) != "potential"
                                         for i in active_rows):
            raise BlockHold("EXPECTED_FOUR_INTERIOR_PHI_ROWS_NOT_FOUND:" + species)
        observed = sum(value for _, _, value in entries)
        analytic = predicted_block_sum(species)
        relative = abs(observed - analytic) / abs(analytic)
        directionals = {}
        for h in FD_DIRECTION_STEPS:
            fd = source_directional(INTERIOR_TEST_SUM, STATES, species, h)
            directionals[f"{h:.0e}"] = {
                "residual_central_fd_directional": fd,
                "relative_to_analytic": abs(fd - analytic) / abs(analytic),
                "relative_to_assembled_block_sum":
                    abs(fd - observed) / abs(analytic),
            }
        preferred = directionals[f"{PREFERRED_STEP:.0e}"]
        passed = (
            relative <= ANALYTIC_BLOCK_REL_TOL
            and preferred["relative_to_analytic"] <= DIRECTIONAL_FD_REL_TOL
            and preferred["relative_to_assembled_block_sum"]
            <= ANALYTIC_BLOCK_REL_TOL + DIRECTIONAL_FD_REL_TOL
        )
        records[species] = {
            "matrix_block": "potential_row_by_" + species + "_column",
            "mapped_matrix_nonzeros": len(entries),
            "active_phi_rows": sorted(active_rows),
            "assembled_block_signed_sum": observed,
            "analytic_Q1_FE_block_signed_sum": analytic,
            "relative_to_independent_FE": relative,
            "predeclared_block_tolerance": ANALYTIC_BLOCK_REL_TOL,
            "predeclared_fd_tolerance": DIRECTIONAL_FD_REL_TOL,
            "independent_directional_residual_fd": directionals,
            "block_status": "PASS" if passed else "HOLD",
        }
    return records


def analyze(*, source: Path, manifest: Path, output: Path,
            authorize: bool) -> dict:
    if not authorize:
        raise BlockHold("EXPLICIT_NATIVE_AUTHORIZATION_REQUIRED")
    if output.exists() or output.is_symlink():
        raise BlockHold("REPORT_OVERWRITE_DENIED")
    identity = verify_binary_and_source(source, manifest)
    report = {
        "schema": "issue652.g7.dof_directional.v1", **identity,
        "fixture": "3x3_Q1_generated_mesh_same_G3_charge_functors",
        "strict_global_jacobian_tolerance": 1e-8,
        "dof_map_status": "HOLD", "block_directional_status": "HOLD",
        "actual_s6_coupled_ad_jacobian": "UNVERIFIED",
        "old_new_fieldwise_parity": "UNVERIFIED",
        "science": "SCIENCE_HOLD",
    }
    started = time.monotonic()
    try:
        with private_workspace() as temp:
            case = temp / "g7_micro_poisson.i"
            case.write_text(fixture(), encoding="utf-8")
            report["fixture_sha256"] = sha256(case)
            rc, log, timed_out = invoke(
                docker_command(source, temp, check=True), timeout=60)
            report["native_p2_rc"] = rc
            if rc == 0 and not timed_out and "Syntax OK" in log:
                rc, log, timed_out = invoke(
                    _view_command(source, temp), timeout=120
                )
                report["native_run_rc"] = rc
                report["native_timeout"] = timed_out
                report["native_log_sha256"] = hashlib.sha256(log.encode()).hexdigest()
                if rc == 0 and not timed_out:
                    mapping = parse_dofmap(log)
                    report["ndof"] = mapping["ndof"]
                    report["dof_map_status"] = "PASS_EXACT_MOOSE_DOFMAP"
                    report["variables"] = mapping["variables"]
                    triplets = read_petsc_matrices(log, mapping["ndof"])
                    candidates = []
                    for k, item in enumerate(triplets):
                        try:
                            blocks = analyze_jacobian(item["assembled"], mapping)
                        except BlockHold as exc:
                            candidates.append({"group": k, "block_status": "HOLD",
                                               "reason": str(exc)[:96]})
                            continue
                        candidates.append({
                            "group": k,
                            "block_status": ("PASS" if all(
                                b["block_status"] == "PASS" for b in blocks.values()
                                ) else "HOLD"),
                            "blocks": blocks,
                        })
                    report["matrix_triplet_count"] = len(triplets)
                    report["jacobian_groups"] = candidates
                    report["block_directional_status"] = (
                        "PASS_SYNTHETIC_Q1_CHARGE_BLOCK_DERIVATIVE"
                        if candidates and all(x["block_status"] == "PASS"
                                              for x in candidates)
                        else "HOLD"
                    )
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, sort_keys=True, indent=2,
                                     allow_nan=False) + "\n", encoding="utf-8")
    for entry in report.get("jacobian_groups", []):
        print("G7_BLOCK_GROUP", entry["group"], entry["block_status"],
              json.dumps({species: round(block["relative_to_independent_FE"], 7)
                          for species, block in entry.get("blocks", {}).items()},
                         sort_keys=True), flush=True)
    print("G7_DOF_DIRECTIONAL_STATUS", report["dof_map_status"],
          report["block_directional_status"],
          "FULL_S6_UNVERIFIED SCIENCE_HOLD", flush=True)
    return report


def _view_command(source: Path, work: Path) -> list[str]:
    command = docker_command(source, work, check=False)
    command[-1] += " -snes_test_err 1e-09 -snes_test_jacobian_view"
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-native", action="store_true")
    args = parser.parse_args()
    try:
        result = analyze(source=args.source, manifest=args.manifest,
                         output=args.output, authorize=args.authorize_native)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("G7_BLOCK_DIRECTIONAL_HOLD", type(exc).__name__,
              str(exc)[:160], flush=True)
        return 2
    return 0 if result["block_directional_status"].startswith("PASS") else 3


if __name__ == "__main__":
    raise SystemExit(main())
