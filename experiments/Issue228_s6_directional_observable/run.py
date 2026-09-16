#!/usr/bin/env python3
"""Issue #228 S6-A: qualify a framework-consistent wall-normal electrostatic observable.

This stage does not change the physics model. It replaces the frozen-Poisson
FVDiffusion object by a diagnostic subclass whose residual is exactly the
parent FVDiffusion residual and records grad(phi).n from gradUDotNormal().

The observable is not promoted until reference/diagnostic solution equivalence,
all-wall face matching, and independent geometric-normal checks pass.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from experiments.Issue228_d1_s2 import run as d1s2
from experiments.Issue228_d1_s3 import run as s3
from experiments.Issue228_pgw_parallel import run as pgw

PHYSICAL_WALLS = tuple(d1s2.PHYSICAL_WALLS)
DIFF_PREFIX = "ISSUE228_DIFF"


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if not np.isfinite(n) or n <= 0.0:
        raise ValueError("zero/nonfinite vector")
    return v / n


def _inward_normal(p1: np.ndarray, p2: np.ndarray, centroid: np.ndarray) -> np.ndarray:
    """Unit face normal whose sign points from the face into the owning cell."""
    tangent = p2 - p1
    mid = 0.5 * (p1 + p2)
    candidate = _unit(np.asarray([-tangent[1], tangent[0]], dtype=float))
    if float(np.dot(candidate, centroid - mid)) < 0.0:
        candidate *= -1.0
    return candidate


def _angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    c = float(np.clip(np.dot(_unit(a), _unit(b)), -1.0, 1.0))
    return float(math.degrees(math.acos(c)))


def self_test() -> int:
    # Straight horizontal wall, cell above it: inward is +y.
    n = _inward_normal(np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.5, 1.0]))
    assert np.allclose(n, [0.0, 1.0], atol=1e-14)

    # The same construction rotated 37 degrees must rotate covariantly.
    th = math.radians(37.0)
    R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    p1 = R @ np.array([0.0, 0.0])
    p2 = R @ np.array([1.0, 0.0])
    c = R @ np.array([0.5, 1.0])
    nr = _inward_normal(p1, p2, c)
    assert _angle_deg(nr, R @ np.array([0.0, 1.0])) < 1e-10

    # A tangential topological proxy must not masquerade as a normal proxy.
    assert _angle_deg(np.array([1.0, 0.0]), np.array([0.0, 1.0])) > 89.999999

    # A valid inward proxy remains valid after rotation.
    assert _angle_deg(R @ np.array([0.0, 2.0]), R @ np.array([0.0, 1.0])) < 1e-10
    print("S6-A geometry self-test PASS")
    return 0


def _physical_face_records(snapshot: Path):
    coords, conn, emap, vals, _t, sidesets = pgw._load_snapshot(snapshot, 10)
    tri = coords[conn - 1]
    centroids = tri.mean(axis=1)
    side_nodes = {1: (0, 1), 2: (1, 2), 3: (2, 0)}

    records: list[dict[str, Any]] = []
    for name, elems, sides in sidesets:
        if name not in PHYSICAL_WALLS:
            continue
        for e, side in zip(elems, sides):
            i = int(e - 1)
            ia, ib = side_nodes[int(side)]
            p1 = tri[i, ia].astype(float)
            p2 = tri[i, ib].astype(float)
            mid = 0.5 * (p1 + p2)
            nin = _inward_normal(p1, p2, centroids[i])
            records.append({
                "wall": str(name),
                "cell_index": i,
                "element_id": int(emap[i]),
                "side": int(side),
                "face_x": float(mid[0]),
                "face_y": float(mid[1]),
                "inward_normal_x": float(nin[0]),
                "inward_normal_y": float(nin[1]),
            })

    # Historical H/reference support is classified, not promoted to a primary
    # directional observable.
    wall, neigh = pgw._wall_cells_and_neighbors(conn, sidesets)
    for rec in records:
        i = int(rec["cell_index"])
        js = sorted(set(neigh.get(i, set())) - wall)
        if not js:
            js = sorted(neigh.get(i, set()))
        rec["topological_reference_element_ids"] = [int(emap[j]) for j in js]
        if js:
            support = np.mean(centroids[js], axis=0)
            d = support - centroids[i]
            nin = np.array([rec["inward_normal_x"], rec["inward_normal_y"]])
            theta = _angle_deg(d, nin)
            dperp = float(np.dot(d, nin))
            dpar = float(np.linalg.norm(d - dperp * nin))
            rec.update({
                "topological_reference_angle_deg": theta,
                "topological_reference_d_perp_m": dperp,
                "topological_reference_d_parallel_m": dpar,
                "topological_reference_class": (
                    "GEOMETRICALLY_VALID_DIRECTIONAL_PROXY" if theta <= 15.0 and dperp > 0.0
                    else "SUPPORTING_ONLY" if theta <= 30.0 and dperp > 0.0
                    else "INVALID_FOR_DIRECTIONAL_CLAIM"
                ),
            })
        else:
            rec.update({
                "topological_reference_angle_deg": None,
                "topological_reference_d_perp_m": None,
                "topological_reference_d_parallel_m": None,
                "topological_reference_class": "INVALID_FOR_DIRECTIONAL_CLAIM",
            })
    return records, coords, conn, emap, vals, sidesets


def _diagnostic_input(base_text: str, diagnostic_eids: list[int]) -> str:
    old = """  [diffusion]\n    type = FVDiffusion\n    variable = phi\n    coeff = 1\n    block = plasma\n  []"""
    ids = " ".join(str(x) for x in sorted(set(diagnostic_eids)))
    new = f"""  [diffusion]\n    type = PhysicsFVDiffusionDiagnostic\n    variable = phi\n    coeff = 1\n    block = plasma\n    diagnostic_element_ids = '{ids}'\n    diagnostic_boundary_faces = true\n  []"""
    if base_text.count(old) != 1:
        raise RuntimeError("expected exactly one frozen-Poisson FVDiffusion block")
    return base_text.replace(old, new)


def _parse_diag(log_path: Path) -> list[dict[str, Any]]:
    """Return the last nonlinear-state record for each geometric boundary face."""
    unique: dict[tuple[int, float, float], dict[str, Any]] = {}
    if not log_path.exists():
        return []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(DIFF_PREFIX):
            continue
        fields: dict[str, str] = {}
        for token in line.split()[1:]:
            if "=" in token:
                k, v = token.split("=", 1)
                fields[k] = v
        if fields.get("face_type") != "boundary":
            continue
        try:
            rec = {
                "element_id": int(fields["elem"]),
                "boundary_ids": fields.get("boundary_ids", ""),
                "face_x": float(fields["face_x"]),
                "face_y": float(fields["face_y"]),
                "moose_outward_normal_x": float(fields["normal_x"]),
                "moose_outward_normal_y": float(fields["normal_y"]),
                "dcn_mag_m": float(fields["dcn_mag"]),
                "ecn_dot_normal": float(fields["ecn_dot_normal"]),
                "phi_elem_V": float(fields["u_elem"]),
                "grad_phi_dot_n_out_V_m": float(fields["actual_dudn"]),
                "E_dot_n_out_V_m": -float(fields["actual_dudn"]),
                "diffusion_residual": float(fields["residual"]),
            }
        except (KeyError, ValueError) as exc:
            raise RuntimeError(f"malformed diagnostic line: {line}") from exc
        key = (int(rec["element_id"]), float(rec["face_x"]), float(rec["face_y"]))
        unique[key] = rec
    return list(unique.values())


def _match_physical_faces(
    physical: list[dict[str, Any]], observed: list[dict[str, Any]], tol: float = 1.0e-10
):
    matched: list[dict[str, Any]] = []
    used: set[int] = set()
    for rec in physical:
        candidates = []
        for j, obs in enumerate(observed):
            if j in used or int(obs["element_id"]) != int(rec["element_id"]):
                continue
            dr = math.hypot(float(obs["face_x"]) - float(rec["face_x"]),
                            float(obs["face_y"]) - float(rec["face_y"]))
            if dr <= tol:
                candidates.append((dr, j, obs))
        if len(candidates) != 1:
            raise RuntimeError(
                f"face match for {rec['wall']} element {rec['element_id']} has {len(candidates)} candidates")
        dr, j, obs = candidates[0]
        used.add(j)
        nin = np.array([rec["inward_normal_x"], rec["inward_normal_y"]], dtype=float)
        nout_geom = -nin
        nout_moose = np.array([obs["moose_outward_normal_x"], obs["moose_outward_normal_y"]], dtype=float)
        normal_angle = _angle_deg(nout_geom, nout_moose)
        row = dict(rec)
        row.update(obs)
        row["face_match_distance_m"] = float(dr)
        row["moose_vs_geometric_outward_normal_angle_deg"] = normal_angle
        row["grad_phi_dot_n_in_V_m"] = -float(obs["grad_phi_dot_n_out_V_m"])
        row["E_dot_n_in_V_m"] = -float(obs["E_dot_n_out_V_m"])
        matched.append(row)
    return matched, len(observed) - len(used)


def _solve(exe: Path, case: Path, text: str, timeout: int):
    case.mkdir(parents=True, exist_ok=True)
    (case / "input.i").write_text(text, encoding="utf-8")
    logs = case / "logs"
    logs.mkdir(exist_ok=True)
    p2 = d1s2._run([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 180)
    if p2["returncode"] != 0:
        return p2, None, None
    rt = d1s2._run([str(exe), "-i", "input.i"], case, logs / "runtime.log", timeout)
    if rt["returncode"] != 0 or rt["timed_out"]:
        return p2, rt, None
    exo = sorted(case.glob("*_out.e"))
    if len(exo) != 1:
        raise RuntimeError(f"expected one output exodus in {case}, got {exo}")
    _conn, emap, phi, _sidesets = d1s2._read_phi(exo[0])
    return p2, rt, (emap, phi)


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    snapshot = args.snapshot_root.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    summary: dict[str, Any] = {
        "status": "RUNNING",
        "claim": "framework_boundary_normal_gradient_observable_is_residual_equivalent_and_geometrically_qualified",
        "diagnostic_only": True,
        "physics_axis_changed": False,
        "primary_observable_candidate": "FVDiffusion::gradUDotNormal for potential phi on physical boundary faces",
    }

    try:
        physical, *_ = _physical_face_records(snapshot)
        expected_faces = len(physical)
        if expected_faces != 87:
            return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL",
                              f"expected 87 physical wall faces, got {expected_faces}")
        eids = sorted({int(x["element_id"]) for x in physical})

        ref_case = out / "reference"
        diag_case = out / "diagnostic"
        ref_case.mkdir(parents=True, exist_ok=True)
        prep = s3._prepare_source(snapshot, ref_case)
        # The source field is byte-identical for both solves.
        diag_case.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ref_case / "source.e", diag_case / "source.e")
        wall_values = s3._wall_values("current_balance", prep)
        initial_phi = float(np.mean(list(wall_values.values())))
        base_text = s3._s3_input("current_balance", wall_values, initial_phi)
        diag_text = _diagnostic_input(base_text, eids)

        p2_ref, rt_ref, sol_ref = _solve(exe, ref_case, base_text, args.timeout)
        p2_diag, rt_diag, sol_diag = _solve(exe, diag_case, diag_text, args.timeout)
        summary.update({
            "p2_reference": p2_ref,
            "p2_diagnostic": p2_diag,
            "runtime_reference": rt_ref,
            "runtime_diagnostic": rt_diag,
            "preparation": prep,
            "physical_wall_face_count": expected_faces,
            "diagnostic_element_ids": eids,
        })
        if p2_ref["returncode"] != 0 or p2_diag["returncode"] != 0:
            return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL", "P2 input validation failed")
        if rt_ref is None or rt_diag is None or sol_ref is None or sol_diag is None:
            return _hard_fail(out, summary, "SOLVER_CONVERGENCE_FAIL", "reference or diagnostic solve failed")

        emap_ref, phi_ref = sol_ref
        emap_diag, phi_diag = sol_diag
        if not np.array_equal(emap_ref, emap_diag):
            return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL", "element map changed")
        delta = np.asarray(phi_diag) - np.asarray(phi_ref)
        max_abs_delta = float(np.max(np.abs(delta)))
        rms_delta = float(np.sqrt(np.mean(delta * delta)))

        observed = _parse_diag(diag_case / "logs" / "runtime.log")
        matched, unmatched_observed = _match_physical_faces(physical, observed)
        finite = all(np.isfinite(float(r["grad_phi_dot_n_out_V_m"])) for r in matched)
        max_normal_angle = max(float(r["moose_vs_geometric_outward_normal_angle_deg"]) for r in matched)
        _write(out / "wall_face_observables.json", matched)

        class_counts: dict[str, int] = {}
        for r in matched:
            key = str(r["topological_reference_class"])
            class_counts[key] = class_counts.get(key, 0) + 1
        target_rows = [r for r in matched if int(r["element_id"]) == 2401]
        target = target_rows[0] if len(target_rows) == 1 else None

        gates = {
            "reference_diagnostic_solution_equivalent": max_abs_delta <= 1.0e-10,
            "all_87_physical_faces_matched": len(matched) == 87,
            "framework_normals_match_geometry": max_normal_angle <= 1.0e-6,
            "all_framework_gradients_finite": finite,
            "target_2401_unique": target is not None,
        }
        qualified = all(gates.values())
        summary.update({
            "reference_diagnostic_phi_max_abs_delta_V": max_abs_delta,
            "reference_diagnostic_phi_rms_delta_V": rms_delta,
            "observed_selected_boundary_face_count": len(observed),
            "matched_physical_face_count": len(matched),
            "extra_selected_boundary_face_count": unmatched_observed,
            "max_moose_vs_geometric_outward_normal_angle_deg": max_normal_angle,
            "topological_reference_class_counts": class_counts,
            "target_2401": target,
            "qualification_gates": gates,
            "evidence_valid": True,
            "ci_status": "success",
            "scientific_outcome": "OBSERVABLE_QUALIFIED" if qualified else "OBSERVABLE_NOT_QUALIFIED",
            "status": "BATCH_PASS",
        })
        _write(out / "summary.json", summary)
        # Scientific non-qualification is valid evidence, therefore CI remains green.
        return 0
    except Exception as exc:
        return _hard_fail(out, summary, "ANALYSIS_FAIL", f"{type(exc).__name__}: {exc}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--snapshot-root", type=Path)
    p.add_argument("--physics-opt", type=Path)
    p.add_argument("--results-root", type=Path)
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.snapshot_root is None or args.physics_opt is None or args.results_root is None:
        p.error("--snapshot-root, --physics-opt, and --results-root are required unless --self-test")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
