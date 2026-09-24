"""Issue #310 Generation 12: trajectory-based electron-potential Jacobian diagnostic.

Diagnostic only: preserve the qualified Gen11/Sequence08 physics and collect the
20-cell electron state at every successful MultiApp fixed-point iteration. The
analysis estimates the directional discrete response dn_e/dphi from consecutive
Gummel iterates and, when the observed update directions have sufficient rank,
a least-squares 20x20 secant sensitivity matrix.

This is deliberately not called an exact Jacobian unless the excitation rank is
full. Its role is to decide whether A1 n_e/VTe or A2 n_e*mu/D is the better
local surrogate before another screened-Poisson parameter experiment.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq11_screened as gen11

GENERATED = ROOT / "generated_fp12_jacobian"
RESULTS = ROOT / "results_fp12_jacobian"
CASE = "picard2x_control"


def _instrument_fast(text: str) -> str:
    profile = """  [energy_profile]
    type = ElementValueSampler
    variable = 'electron_density_out potential_from_poisson n_epsilon mean_energy_out mobility_out diffusion_out elastic_loss_candidate_out'
    sort_by = id
    execute_on = 'FINAL'
  []
"""
    replacement = profile.replace("execute_on = 'FINAL'", "execute_on = 'TIMESTEP_END'")
    if text.count(profile) != 1:
        raise RuntimeError("fast energy_profile anchor changed")
    text = text.replace(profile, replacement, 1)

    outputs = """[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    new_row_tolerance = 1.0e-30
  []
"""
    extra = outputs + """  [fp_iter_csv]
    type = CSV
    execute_on = 'MULTIAPP_FIXED_POINT_ITERATION_END'
    new_row_detection_columns = all
    new_row_tolerance = 1.0e-30
    precision = 17
    scientific_notation = true
  []
"""
    if text.count(outputs) != 1:
        raise RuntimeError("fast Outputs/step_csv anchor changed")
    return text.replace(outputs, extra, 1)


def build(clean: bool = True) -> None:
    import shutil
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    raw = {"name": CASE, "screened": False}
    p = gen11._params(raw)
    parent, fast, poisson = gen11.render(raw, p)
    fast = _instrument_fast(fast)
    d = GENERATED / CASE
    d.mkdir(parents=True, exist_ok=True)
    (d / "input.i").write_text(parent, encoding="utf-8")
    (d / "fast_sub.i").write_text(fast, encoding="utf-8")
    (d / "poisson_sub.i").write_text(poisson, encoding="utf-8")
    shutil.copy2(gen11.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
    shutil.copy2(gen11.base.ELASTIC_DATA, d / "o2_elastic.txt")
    shutil.copy2(gen11.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
    (d / "case.json").write_text(json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def p0() -> None:
    build()
    d = GENERATED / CASE
    fast = (d / "fast_sub.i").read_text(encoding="utf-8")
    assert "execute_on = 'MULTIAPP_FIXED_POINT_ITERATION_END'" in fast
    assert "new_row_detection_columns = all" in fast
    assert fast.count("[energy_profile]") == 1
    assert "execute_on = 'TIMESTEP_END'" in fast
    assert "gummel_screen_beta" not in (d / "poisson_sub.i").read_text(encoding="utf-8")
    assert "no_restore = true" in fast
    print("ISSUE310_GEN12_JACOBIAN_P0: PASS")


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    gen11.base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp12_jacobian/{CASE}/input.i"
    )
    print("ISSUE310_GEN12_JACOBIAN_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = "; ".join(
        f"cd /workspace/{rel}/generated_fp12_jacobian/{CASE} && /workspace/physics_app/physics-opt --check-input -i {f}"
        for f in ("input.i", "fast_sub.i", "poisson_sub.i")
    )
    gen11.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + checks
    )
    print("ISSUE310_GEN12_JACOBIAN_P2: PASS")


def _bind() -> None:
    gen11.GENERATED = GENERATED
    gen11.RESULTS = RESULTS
    gen11.seq08.GENERATED = GENERATED
    gen11.seq08.RESULTS = RESULTS
    gen11.seq08.FINAL_TAU = gen11.FINAL_TAU
    gen11.seq08.HEAVY_CYCLES = gen11.HEAVY_CYCLES
    gen11.seq08.CASE_NAMES = (CASE,)
    gen11.seq08.SPECS = (gen11._spec({"name": CASE, "screened": False}),)


def inner_run() -> int:
    _bind()
    RESULTS.mkdir(parents=True, exist_ok=True)
    return gen11.seq08.inner_run(CASE)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _profile(path: Path) -> dict[str, np.ndarray]:
    rows = _read_csv(path)
    rows.sort(key=lambda r: int(float(r["id"])))
    def col(name: str) -> np.ndarray:
        return np.asarray([float(r[name]) for r in rows], dtype=float)
    return {
        "id": col("id"),
        "x": col("x"),
        "ne": col("electron_density_out"),
        "phi": col("potential_from_poisson"),
        "mean_e": col("mean_energy_out"),
        "mu": col("mobility_out"),
        "D": col("diffusion_out"),
    }


def _safe_stats(values: np.ndarray) -> dict[str, float | None]:
    good = values[np.isfinite(values)]
    if good.size == 0:
        return {"min": None, "median": None, "max": None, "mean": None}
    return {
        "min": float(np.min(good)),
        "median": float(np.median(good)),
        "max": float(np.max(good)),
        "mean": float(np.mean(good)),
    }


def _analyse_step(samples: list[dict[str, np.ndarray]], time_s: float) -> dict[str, object]:
    if len(samples) < 2:
        return {"time_s": time_s, "profiles": len(samples), "status": "INSUFFICIENT_PROFILES"}

    dphi = np.stack([b["phi"] - a["phi"] for a, b in zip(samples[:-1], samples[1:])])
    dne = np.stack([b["ne"] - a["ne"] for a, b in zip(samples[:-1], samples[1:])])
    denom = np.sum(dphi * dphi, axis=0)
    numer = np.sum(dphi * dne, axis=0)
    local = np.full(denom.shape, np.nan)
    mask = denom > max(float(np.max(denom)) * 1.0e-18, 1.0e-40)
    local[mask] = numer[mask] / denom[mask]

    ref = samples[0]
    vte = (2.0 / 3.0) * ref["mean_e"]
    a1 = ref["ne"] / np.maximum(vte, 1.0e-30)
    a2 = ref["ne"] * ref["mu"] / np.maximum(ref["D"], 1.0e-300)
    gamma_a1 = np.divide(local, a1, out=np.full_like(local, np.nan), where=np.abs(a1) > 0)
    gamma_a2 = np.divide(local, a2, out=np.full_like(local, np.nan), where=np.abs(a2) > 0)

    _, svals, _ = np.linalg.svd(dphi, full_matrices=False)
    tol = (svals[0] if svals.size else 0.0) * max(dphi.shape) * np.finfo(float).eps
    rank = int(np.sum(svals > tol))
    C, _, _, _ = np.linalg.lstsq(dphi, dne, rcond=None)
    B = C.T
    diag = np.diag(B)
    off = B - np.diag(diag)
    bnorm = float(np.linalg.norm(B))
    off_fraction = float(np.linalg.norm(off) / bnorm) if bnorm > 0 else None
    fit = dphi @ C
    data_norm = float(np.linalg.norm(dne))
    rel_fit_error = float(np.linalg.norm(dne - fit) / data_norm) if data_norm > 0 else None

    return {
        "time_s": time_s,
        "profiles": len(samples),
        "increments": int(dphi.shape[0]),
        "cells": int(dphi.shape[1]),
        "potential_update_rank": rank,
        "full_matrix_identified": rank == dphi.shape[1],
        "singular_values": [float(x) for x in svals],
        "least_squares_relative_fit_error": rel_fit_error,
        "least_squares_offdiagonal_frobenius_fraction": off_fraction,
        "directional_local_dn_dphi_m3_per_V": [None if not math.isfinite(x) else float(x) for x in local],
        "a1_ne_over_VTe_m3_per_V": [float(x) for x in a1],
        "a2_ne_mu_over_D_m3_per_V": [float(x) for x in a2],
        "gamma_A1_directional": [None if not math.isfinite(x) else float(x) for x in gamma_a1],
        "gamma_A2_directional": [None if not math.isfinite(x) else float(x) for x in gamma_a2],
        "local_sensitivity_stats": _safe_stats(local),
        "gamma_A1_stats": _safe_stats(gamma_a1),
        "gamma_A2_stats": _safe_stats(gamma_a2),
        "matrix_diagonal_m3_per_V": [float(x) for x in diag],
        "matrix_flat_row_major_m3_per_V": [float(x) for x in B.ravel()],
        "interpretation": (
            "FULL_RANK_TRAJECTORY_SECANT"
            if rank == dphi.shape[1]
            else "LOW_RANK_DIRECTIONAL_SECANT_ONLY; basis perturbations are required before calling this an exact 20x20 Jacobian"
        ),
    }


def analyse() -> dict[str, object]:
    case_dir = GENERATED / CASE
    scalar = case_dir / "input_out_electron0_fp_iter_csv.csv"
    profiles = sorted(case_dir.glob("input_out_electron0_fp_iter_csv_energy_profile_*.csv"))
    if not scalar.is_file():
        raise RuntimeError(f"missing fixed-point scalar CSV: {scalar}")
    rows = _read_csv(scalar)
    if not rows or not profiles:
        raise RuntimeError("fixed-point diagnostic output is empty")
    if len(rows) != len(profiles):
        raise RuntimeError(f"scalar/profile count mismatch: {len(rows)} != {len(profiles)}")

    records: list[tuple[float, dict[str, np.ndarray]]] = []
    for row, path in zip(rows, profiles, strict=True):
        records.append((float(row["time"]), _profile(path)))

    times: list[float] = []
    for t, _ in records:
        if t > 0.0 and (not times or not math.isclose(t, times[-1], rel_tol=0.0, abs_tol=1.0e-30)):
            times.append(t)
    steps = []
    for t in times[:2]:
        samples = [p for tr, p in records if math.isclose(tr, t, rel_tol=0.0, abs_tol=1.0e-30)]
        steps.append(_analyse_step(samples, t))

    comparison = {}
    if len(steps) >= 2:
        comparison = {
            "step1_gamma_A1_median": steps[0].get("gamma_A1_stats", {}).get("median"),
            "step2_gamma_A1_median": steps[1].get("gamma_A1_stats", {}).get("median"),
            "step1_gamma_A2_median": steps[0].get("gamma_A2_stats", {}).get("median"),
            "step2_gamma_A2_median": steps[1].get("gamma_A2_stats", {}).get("median"),
            "step2_full_matrix_identified": steps[1].get("full_matrix_identified"),
        }

    return {
        "issue": 310,
        "generation": 12,
        "diagnostic": "trajectory discrete secant electron response to potential",
        "case": CASE,
        "source_head_role": "Gen11 qualified-control physics plus diagnostic-only output instrumentation",
        "physics_changed": False,
        "fixed_point_output_rows": len(rows),
        "profile_files": len(profiles),
        "physical_times_observed": times,
        "steps": steps,
        "comparison": comparison,
        "guard": "This is an observed Gummel-trajectory secant response. Only a full-rank fit may be treated as a 20x20 discrete secant Jacobian; otherwise use the directional/local estimates and run basis perturbations before claiming an exact Jacobian.",
    }


def run_case() -> None:
    _bind()
    if not GENERATED.exists():
        build()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    gen11.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq12_jacobian_diag.py --inner-run"
    )
    summary = analyse()
    out = RESULTS / "jacobian_trajectory_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN12_JACOBIAN_RESULT:", out)
    print(json.dumps(summary["comparison"], sort_keys=True))


def main() -> None:
    if "--p0" in sys.argv:
        p0(); return
    if "--p1" in sys.argv:
        p1(); return
    if "--p2" in sys.argv:
        p2(); return
    if "--inner-run" in sys.argv:
        raise SystemExit(inner_run())
    if "--case" in sys.argv:
        run_case(); return
    raise SystemExit("choose --p0/--p1/--p2/--case")


if __name__ == "__main__":
    main()
