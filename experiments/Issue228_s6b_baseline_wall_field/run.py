#!/usr/bin/env python3
"""Issue #228 S6-B: terminal wall-normal field classification on the raw grounded baseline.

S6-A qualified PhysicsFVDiffusionDiagnostic as residual-equivalent and geometry-consistent.
S6-B applies that observable to the governed step-10 raw charge field with physical sheath
walls grounded at 0 V, inlet/outlet grounded at 0 V, and the axis left natural. No sheath
ownership correction or new physical closure is introduced.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import netcdf_file

from experiments.Issue228_d1_s2 import run as d1s2
from experiments.Issue228_d1_s3 import run as s3
from experiments.Issue228_pgw_parallel import run as pgw
from experiments.Issue228_s6_directional_observable import run as s6a

PHYSICAL_WALLS = tuple(s6a.PHYSICAL_WALLS)
E_TOL_V_M = 1.0e-9
SNAPSHOT_REPRO_TOL_V = 1.0e-6


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hard_fail(out: Path, summary: dict[str, Any], status: str, error: str) -> int:
    summary.update({
        "status": status,
        "ci_status": "failure",
        "evidence_valid": False,
        "scientific_outcome": "NOT_EVALUATED",
        "error": error,
    })
    _write(out / "summary.json", summary)
    return 1


def self_test() -> int:
    assert E_TOL_V_M > 0.0
    assert SNAPSHOT_REPRO_TOL_V > 0.0
    assert set(PHYSICAL_WALLS) == {
        "plasma_electrode", "plasma_metal", "plasma_right",
        "plasma_cover", "plasma_wafer", "plasma_focus_ring",
    }
    print("S6-B self-test PASS")
    return 0


def _prepare_raw_source(snapshot: Path, work: Path) -> dict[str, Any]:
    coords, conn, emap, vals, time_s, _sidesets = pgw._load_snapshot(snapshot, 10)
    rho_raw = pgw._charge_density(vals)
    _tri, _area, _rcent, vol = pgw._geom(coords, conn)

    src_e = work / "source.e"
    shutil.copy2(snapshot / "case" / "input_out.e", src_e)
    f = netcdf_file(str(src_e), "a", mmap=False)
    names = d1s2._decode_names(f.variables["name_elem_var"].data.copy())
    iv = names.index("potential_plasma") + 1
    var = f.variables[f"vals_elem_var{iv}eb1"]
    data = var.data.copy()
    data[:] = (rho_raw / pgw.EPS0)[np.newaxis, :]
    var[:] = data
    f.flush()
    f.close()

    return {
        "time_s": float(time_s),
        "raw_volume_charge_C": float(np.dot(rho_raw, vol)),
        "rho_q_min_C_m3": float(np.min(rho_raw)),
        "rho_q_max_C_m3": float(np.max(rho_raw)),
        "source_correction_applied": False,
        "physical_wall_value_V": 0.0,
        "inlet_outlet_value_V": 0.0,
        "axis_semantics": "natural/symmetry; no Dirichlet grounding",
        "element_count": int(len(conn)),
        "element_map_min": int(np.min(emap)),
        "element_map_max": int(np.max(emap)),
    }


def _wall_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for wall in PHYSICAL_WALLS:
        subset = [r for r in rows if r["wall"] == wall]
        vals = [float(r["E_dot_n_out_V_m"]) for r in subset]
        out[wall] = {
            "face_count": len(subset),
            "positive_count": sum(v > E_TOL_V_M for v in vals),
            "near_zero_count": sum(abs(v) <= E_TOL_V_M for v in vals),
            "negative_count": sum(v < -E_TOL_V_M for v in vals),
            "min_E_out_V_m": min(vals) if vals else None,
            "max_E_out_V_m": max(vals) if vals else None,
        }
    return out


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    snapshot = args.snapshot_root.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    summary: dict[str, Any] = {
        "status": "RUNNING",
        "claim": "original_raw_grounded_baseline_wall_normal_field_is_classified_with_the_S6A_qualified_framework_observable",
        "diagnostic_only": True,
        "physics_axis_changed": False,
        "source_mode": "raw governed step-10 charge; no W3/S3 excess correction",
        "boundary_mode": "physical walls 0 V; inlet/outlet 0 V; axis natural",
        "primary_observable": "E_out = -FVDiffusion::gradUDotNormal(phi) relative to plasma-outward face normal",
        "sign_semantics": "E_out >= 0 is non-reversing for a grounded ion-sheath-like wall; E_out < 0 is local reversal",
        "sign_tolerance_V_m": E_TOL_V_M,
        "snapshot_reproduction_tolerance_V": SNAPSHOT_REPRO_TOL_V,
    }

    try:
        physical, *_ = s6a._physical_face_records(snapshot)
        if len(physical) != 87:
            return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL",
                              f"expected 87 physical wall faces, got {len(physical)}")
        eids = sorted({int(r["element_id"]) for r in physical})

        _coords, _conn, emap_snapshot, vals_snapshot, _time, _sidesets = pgw._load_snapshot(snapshot, 10)
        phi_snapshot = np.asarray(vals_snapshot["potential_plasma"], dtype=float)

        ref_case = out / "reference"
        diag_case = out / "diagnostic"
        ref_case.mkdir(parents=True, exist_ok=True)
        diag_case.mkdir(parents=True, exist_ok=True)
        prep = _prepare_raw_source(snapshot, ref_case)
        shutil.copy2(ref_case / "source.e", diag_case / "source.e")

        wall_values = {w: 0.0 for w in PHYSICAL_WALLS}
        base_text = s3._s3_input("control_zero", wall_values, 0.0)
        diag_text = s6a._diagnostic_input(base_text, eids)

        p2_ref, rt_ref, sol_ref = s6a._solve(exe, ref_case, base_text, args.timeout)
        p2_diag, rt_diag, sol_diag = s6a._solve(exe, diag_case, diag_text, args.timeout)
        summary.update({
            "preparation": prep,
            "p2_reference": p2_ref,
            "p2_diagnostic": p2_diag,
            "runtime_reference": rt_ref,
            "runtime_diagnostic": rt_diag,
        })
        if p2_ref["returncode"] != 0 or p2_diag["returncode"] != 0:
            return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL", "P2 input validation failed")
        if rt_ref is None or rt_diag is None or sol_ref is None or sol_diag is None:
            return _hard_fail(out, summary, "SOLVER_CONVERGENCE_FAIL", "reference or diagnostic solve failed")

        emap_ref, phi_ref = sol_ref
        emap_diag, phi_diag = sol_diag
        if not np.array_equal(emap_ref, emap_diag):
            return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL", "reference/diagnostic element map changed")
        if not np.array_equal(emap_ref, emap_snapshot):
            return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL", "frozen/snapshot element map changed")

        diag_delta = np.asarray(phi_diag) - np.asarray(phi_ref)
        max_abs_diag_delta = float(np.max(np.abs(diag_delta)))
        rms_diag_delta = float(np.sqrt(np.mean(diag_delta * diag_delta)))

        snapshot_delta = np.asarray(phi_ref) - phi_snapshot
        max_abs_snapshot_delta = float(np.max(np.abs(snapshot_delta)))
        rms_snapshot_delta = float(np.sqrt(np.mean(snapshot_delta * snapshot_delta)))

        observed = s6a._parse_diag(diag_case / "logs" / "runtime.log")
        matched, unmatched = s6a._match_physical_faces(physical, observed)
        if not matched:
            return _hard_fail(out, summary, "ANALYSIS_FAIL", "no physical wall faces matched")

        finite = all(np.isfinite(float(r["E_dot_n_out_V_m"])) for r in matched)
        max_normal_angle = max(float(r["moose_vs_geometric_outward_normal_angle_deg"]) for r in matched)
        eout = np.asarray([float(r["E_dot_n_out_V_m"]) for r in matched], dtype=float)
        reversed_rows = [r for r in matched if float(r["E_dot_n_out_V_m"]) < -E_TOL_V_M]
        near_zero_rows = [r for r in matched if abs(float(r["E_dot_n_out_V_m"])) <= E_TOL_V_M]
        target_rows = [r for r in matched if int(r["element_id"]) == 2401]
        target = target_rows[0] if len(target_rows) == 1 else None

        qualification_gates = {
            "reference_diagnostic_solution_equivalent": max_abs_diag_delta <= 1.0e-10,
            "raw_frozen_poisson_reproduces_governed_snapshot": max_abs_snapshot_delta <= SNAPSHOT_REPRO_TOL_V,
            "all_87_physical_faces_matched": len(matched) == 87,
            "no_extra_selected_boundary_faces": unmatched == 0,
            "framework_normals_match_geometry": max_normal_angle <= 1.0e-6,
            "all_framework_fields_finite": finite,
            "target_2401_unique": target is not None,
        }
        observable_qualified = all(qualification_gates.values())
        nonreversing_all = len(reversed_rows) == 0

        if observable_qualified and nonreversing_all:
            outcome = "ORIGINAL_GROUNDED_WALL_NORMAL_ORDERING_CONFIRMED"
        elif observable_qualified:
            outcome = "ORIGINAL_WALL_NORMAL_REVERSAL_CONFIRMED"
        else:
            outcome = "OBSERVABLE_NOT_QUALIFIED"

        _write(out / "wall_face_observables.json", matched)
        _write(out / "reversed_wall_faces.json", reversed_rows)
        summary.update({
            "reference_diagnostic_phi_max_abs_delta_V": max_abs_diag_delta,
            "reference_diagnostic_phi_rms_delta_V": rms_diag_delta,
            "frozen_reference_vs_governed_snapshot_phi_max_abs_delta_V": max_abs_snapshot_delta,
            "frozen_reference_vs_governed_snapshot_phi_rms_delta_V": rms_snapshot_delta,
            "observed_selected_boundary_face_count": len(observed),
            "matched_physical_face_count": len(matched),
            "extra_selected_boundary_face_count": unmatched,
            "max_moose_vs_geometric_outward_normal_angle_deg": max_normal_angle,
            "E_out_min_V_m": float(np.min(eout)),
            "E_out_max_V_m": float(np.max(eout)),
            "reversed_face_count": len(reversed_rows),
            "near_zero_face_count": len(near_zero_rows),
            "wall_statistics": _wall_stats(matched),
            "target_2401": target,
            "qualification_gates": qualification_gates,
            "observable_qualified": observable_qualified,
            "all_grounded_physical_faces_nonreversing": nonreversing_all,
            # A completed non-qualification is valid scientific evidence, not a CI failure.
            "evidence_valid": True,
            "ci_status": "success",
            "scientific_outcome": outcome,
            "status": "BATCH_PASS",
        })
        _write(out / "summary.json", summary)
        return 0
    except Exception as exc:
        return _hard_fail(out, summary, "ANALYSIS_FAIL", f"{type(exc).__name__}: {exc}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--snapshot-root", type=Path)
    p.add_argument("--physics-opt", type=Path)
    p.add_argument("--results-root", type=Path)
    p.add_argument("--timeout", type=int, default=900)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.snapshot_root is None or args.physics_opt is None or args.results_root is None:
        p.error("--snapshot-root, --physics-opt, and --results-root are required unless --self-test")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
