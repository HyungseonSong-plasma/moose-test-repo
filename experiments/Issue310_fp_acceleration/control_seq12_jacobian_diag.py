"""Issue #310 Generation 12: trajectory electron-potential Jacobian diagnostic.

Diagnostic only. Preserve the qualified Gen11/Sequence08 Picard-2x physics and
sample the 20-cell electron state after every successful MultiApp fixed-point
iteration. Consecutive iterates provide an observed discrete secant response
of electron density to potential. A 20x20 least-squares secant matrix is only
called identified when the observed potential-update directions have full rank.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq11_screened as gen11

GENERATED = ROOT / "generated_fp12_jacobian"
RESULTS = ROOT / "results_fp12_jacobian"
CASE = "picard2x_control"
NCELL = 20
XMIN = 0.0
XMAX = 0.01
POINT_FIELDS = (
    ("log_e", "log_e"),
    ("ne", "electron_density_out"),
    ("phi", "potential_from_poisson"),
    ("n_epsilon", "n_epsilon"),
    ("mean_e", "mean_energy_out"),
    ("mu", "mobility_out"),
    ("D", "diffusion_out"),
)


def _cell_centers() -> list[float]:
    dx = (XMAX - XMIN) / NCELL
    return [XMIN + (i + 0.5) * dx for i in range(NCELL)]


def _instrument_fast(text: str) -> str:
    fp_anchor = """  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
"""
    if text.count(fp_anchor) != 1:
        raise RuntimeError("fixed-point postprocessor anchor changed")

    point_blocks: list[str] = []
    for i, x in enumerate(_cell_centers()):
        for key, variable in POINT_FIELDS:
            point_blocks.append(
                f"""  [fp_{key}_{i:02d}]
    type = PointValue
    variable = {variable}
    point = '{x:.17g} 0 0'
    execute_on = 'TIMESTEP_END'
  []
"""
            )
    text = text.replace(fp_anchor, "".join(point_blocks) + fp_anchor, 1)

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
    assert "MULTIAPP_FIXED_POINT_CONVERGENCE" not in fast
    assert "new_row_detection_columns = all" in fast
    assert fast.count("type = PointValue") == NCELL * len(POINT_FIELDS)
    for key, variable in POINT_FIELDS:
        assert f"[fp_{key}_00]" in fast
        assert f"[fp_{key}_{NCELL - 1:02d}]" in fast
        assert f"variable = {variable}" in fast
    assert "gummel_screen_beta" not in (d / "poisson_sub.i").read_text(encoding="utf-8")
    assert "no_restore = true" in fast
    print("ISSUE310_GEN12_JACOBIAN_P0: PASS")


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    gen11.base._docker("set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
                       f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp12_jacobian/{CASE}/input.i")
    print("ISSUE310_GEN12_JACOBIAN_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = "; ".join(f"cd /workspace/{rel}/generated_fp12_jacobian/{CASE} && /workspace/physics_app/physics-opt --check-input -i {f}"
                       for f in ("input.i", "fast_sub.i", "poisson_sub.i"))
    gen11.base._docker("set -euo pipefail; source /environment; "
                       "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
                       "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
                       "make -C /workspace/physics_app -j2; " + checks)
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


def _sample_from_row(row: dict[str, str]) -> dict[str, list[float]]:
    def col(key: str) -> list[float]:
        return [float(row[f"fp_{key}_{i:02d}"]) for i in range(NCELL)]

    return {
        "id": [float(i) for i in range(NCELL)],
        "x": _cell_centers(),
        "log_e": col("log_e"),
        "ne": col("ne"),
        "phi": col("phi"),
        "n_epsilon": col("n_epsilon"),
        "mean_e": col("mean_e"),
        "mu": col("mu"),
        "D": col("D"),
    }


def _stats(values: list[float]) -> dict[str, float | None]:
    v = sorted(x for x in values if math.isfinite(x))
    if not v:
        return {"min": None, "median": None, "max": None, "mean": None}
    mid = len(v) // 2
    med = v[mid] if len(v) % 2 else 0.5 * (v[mid - 1] + v[mid])
    return {"min": v[0], "median": med, "max": v[-1], "mean": sum(v) / len(v)}


def _rank(a: list[list[float]]) -> tuple[int, list[float]]:
    m = [row[:] for row in a]
    n = len(m)
    scale = max((abs(x) for row in m for x in row), default=0.0)
    tol = max(scale * 1e-11, 1e-300)
    pivots: list[float] = []
    r = 0
    for c in range(n):
        pivot = max(range(r, n), key=lambda i: abs(m[i][c]), default=r)
        if r >= n or abs(m[pivot][c]) <= tol:
            continue
        m[r], m[pivot] = m[pivot], m[r]
        pv = m[r][c]
        pivots.append(abs(pv))
        for i in range(r + 1, n):
            q = m[i][c] / pv
            if q == 0.0:
                continue
            for j in range(c, n):
                m[i][j] -= q * m[r][j]
        r += 1
        if r == n:
            break
    return r, pivots


def _solve(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    n = len(a)
    nrhs = len(b[0])
    aug = [a[i][:] + b[i][:] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda i: abs(aug[i][c]))
        if abs(aug[p][c]) < 1e-300:
            raise RuntimeError("singular regularized normal matrix")
        aug[c], aug[p] = aug[p], aug[c]
        pv = aug[c][c]
        for j in range(c, n + nrhs):
            aug[c][j] /= pv
        for i in range(n):
            if i == c:
                continue
            q = aug[i][c]
            if q == 0.0:
                continue
            for j in range(c, n + nrhs):
                aug[i][j] -= q * aug[c][j]
    return [row[n:] for row in aug]


def _matrix_fit(x: list[list[float]], y: list[list[float]]) -> dict[str, object]:
    m, n = len(x), len(x[0])
    gram = [[sum(x[k][i] * x[k][j] for k in range(m)) for j in range(n)] for i in range(n)]
    rhs = [[sum(x[k][i] * y[k][j] for k in range(m)) for j in range(n)] for i in range(n)]
    rank, pivots = _rank(gram)
    maxdiag = max((abs(gram[i][i]) for i in range(n)), default=1.0)
    ridge = max(maxdiag * 1e-12, 1e-300)
    reg = [row[:] for row in gram]
    for i in range(n):
        reg[i][i] += ridge
    c = _solve(reg, rhs)
    bmat = [[c[j][i] for j in range(n)] for i in range(n)]
    pred = [[sum(x[k][i] * c[i][j] for i in range(n)) for j in range(n)] for k in range(m)]
    ynorm2 = sum(v * v for row in y for v in row)
    err2 = sum((y[k][j] - pred[k][j]) ** 2 for k in range(m) for j in range(n))
    bnorm2 = sum(v * v for row in bmat for v in row)
    off2 = sum(bmat[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
    return {"rank": rank, "rank_pivots": pivots, "ridge": ridge, "B": bmat,
            "relative_fit_error": math.sqrt(err2 / ynorm2) if ynorm2 > 0 else None,
            "offdiag_fraction": math.sqrt(off2 / bnorm2) if bnorm2 > 0 else None}


def _analyse_step(samples: list[dict[str, list[float]]], time_s: float) -> dict[str, object]:
    # At fixed-point iteration end, n_k is the electron solve using the entering
    # potential phi_{k-1}, while phi_k is the subsequently returned Poisson state.
    # Therefore the direct electron-map secant uses lagged pairs:
    #   Delta phi_k = phi_k - phi_{k-1}
    #   Delta n_{k+1} = n_{k+1} - n_k.
    # Same-index Delta n_k / Delta phi_k would mix electron and Poisson map stages.
    if len(samples) < 3:
        return {"time_s": time_s, "profiles": len(samples), "status": "INSUFFICIENT_PROFILES"}

    ncell = len(samples[0]["phi"])
    x = []
    y = []
    a1_rows = []
    a2_rows = []
    for k in range(1, len(samples) - 1):
        prev = samples[k - 1]
        cur = samples[k]
        nxt = samples[k + 1]
        x.append([cur["phi"][i] - prev["phi"][i] for i in range(ncell)])
        y.append([nxt["ne"][i] - cur["ne"][i] for i in range(ncell)])

        # Compare the measured secant with the local surrogate at the electron
        # state that was produced from the left endpoint of this potential secant.
        a1_rows.append([
            cur["ne"][i] / max((2.0 / 3.0) * cur["mean_e"][i], 1e-30)
            for i in range(ncell)
        ])
        a2_rows.append([
            cur["ne"][i] * cur["mu"][i] / max(cur["D"][i], 1e-300)
            for i in range(ncell)
        ])

    local = []
    a1 = []
    a2 = []
    for i in range(ncell):
        den = sum(row[i] ** 2 for row in x)
        num = sum(x[k][i] * y[k][i] for k in range(len(x)))
        local.append(num / den if den > 1e-40 else math.nan)
        w = [row[i] ** 2 for row in x]
        sw = sum(w)
        if sw > 0:
            a1.append(sum(w[k] * a1_rows[k][i] for k in range(len(w))) / sw)
            a2.append(sum(w[k] * a2_rows[k][i] for k in range(len(w))) / sw)
        else:
            a1.append(math.nan)
            a2.append(math.nan)

    g1 = [local[i] / a1[i] if math.isfinite(local[i]) and math.isfinite(a1[i]) and a1[i] != 0 else math.nan for i in range(ncell)]
    g2 = [local[i] / a2[i] if math.isfinite(local[i]) and math.isfinite(a2[i]) and a2[i] != 0 else math.nan for i in range(ncell)]
    fit = _matrix_fit(x, y)
    bmat = fit.pop("B")
    diag = [bmat[i][i] for i in range(ncell)]

    # Primary-state reconstruction checks guard against stale AuxVariable copies.
    ne_reconstructed = [6.02214076e23 * math.exp(v) for v in samples[-1]["log_e"]]
    mean_e_reconstructed = [
        5.73276 * samples[-1]["n_epsilon"][i] / max(ne_reconstructed[i] / 1.0e16, 1e-300)
        for i in range(ncell)
    ]
    ne_aux_rel = max(
        abs(samples[-1]["ne"][i] - ne_reconstructed[i]) / max(abs(ne_reconstructed[i]), 1.0)
        for i in range(ncell)
    )
    mean_aux_rel = max(
        abs(samples[-1]["mean_e"][i] - mean_e_reconstructed[i]) / max(abs(mean_e_reconstructed[i]), 1.0e-300)
        for i in range(ncell)
    )

    return {"time_s": time_s, "profiles": len(samples), "lagged_secant_pairs": len(x), "cells": ncell,
            "potential_update_rank": fit["rank"], "full_matrix_identified": fit["rank"] == ncell,
            "least_squares_relative_fit_error": fit["relative_fit_error"],
            "least_squares_offdiagonal_frobenius_fraction": fit["offdiag_fraction"],
            "rank_pivots": fit["rank_pivots"], "ridge": fit["ridge"],
            "directional_local_dn_dphi_m3_per_V": [None if not math.isfinite(v) else v for v in local],
            "a1_ne_over_VTe_m3_per_V": [None if not math.isfinite(v) else v for v in a1],
            "a2_ne_mu_over_D_m3_per_V": [None if not math.isfinite(v) else v for v in a2],
            "gamma_A1_directional": [None if not math.isfinite(v) else v for v in g1],
            "gamma_A2_directional": [None if not math.isfinite(v) else v for v in g2],
            "local_sensitivity_stats": _stats(local), "gamma_A1_stats": _stats(g1), "gamma_A2_stats": _stats(g2),
            "matrix_diagonal_m3_per_V": diag,
            "matrix_flat_row_major_m3_per_V": [v for row in bmat for v in row],
            "aux_reconstruction_check": {
                "electron_density_max_relative_error": ne_aux_rel,
                "mean_energy_max_relative_error": mean_aux_rel,
            },
            "interpretation": "FULL_RANK_LAGGED_TRAJECTORY_SECANT" if fit["rank"] == ncell else
            "LOW_RANK_LAGGED_DIRECTIONAL_SECANT_ONLY; basis perturbations are required before calling this an exact 20x20 Jacobian"}

def analyse() -> dict[str, object]:
    d = GENERATED / CASE
    scalar = d / "input_out_electron0_fp_iter_csv.csv"
    if not scalar.is_file():
        raise RuntimeError(f"missing fixed-point scalar CSV: {scalar}")
    rows = _read_csv(scalar)
    if not rows:
        raise RuntimeError("fixed-point scalar CSV is empty")

    expected = {f"fp_{key}_{i:02d}" for key, _ in POINT_FIELDS for i in range(NCELL)}
    missing = sorted(expected.difference(rows[0]))
    if missing:
        raise RuntimeError(f"missing fixed-point point-sample columns: {missing[:8]}")

    records = [(float(row["time"]), _sample_from_row(row)) for row in rows]
    times: list[float] = []
    for t, _ in records:
        if t > 0 and not any(math.isclose(t, q, rel_tol=0.0, abs_tol=1e-30) for q in times):
            times.append(t)

    steps = []
    for t in times[:2]:
        samples = [p for tr, p in records if math.isclose(tr, t, rel_tol=0.0, abs_tol=1e-30)]
        steps.append(_analyse_step(samples, t))

    comp = {}
    if len(steps) >= 2:
        comp = {
            "step1_gamma_A1_median": steps[0]["gamma_A1_stats"]["median"],
            "step2_gamma_A1_median": steps[1]["gamma_A1_stats"]["median"],
            "step1_gamma_A2_median": steps[0]["gamma_A2_stats"]["median"],
            "step2_gamma_A2_median": steps[1]["gamma_A2_stats"]["median"],
            "step2_full_matrix_identified": steps[1]["full_matrix_identified"],
        }

    return {
        "issue": 310,
        "generation": 12,
        "diagnostic": "trajectory discrete secant electron response to potential",
        "case": CASE,
        "physics_changed": False,
        "fixed_point_output_rows": len(rows),
        "cell_point_samples_per_row": NCELL * len(POINT_FIELDS),
        "physical_times_observed": times,
        "steps": steps,
        "comparison": comp,
        "guard": (
            "Observed Gummel-trajectory secant response only. A full-rank fit may be treated "
            "as a 20x20 discrete secant Jacobian; otherwise use directional/local estimates "
            "and run basis perturbations before claiming an exact Jacobian."
        ),
    }


def run_case() -> None:
    _bind()
    if not GENERATED.exists():
        build()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    gen11.base._docker("set -euo pipefail; source /environment; "
                       "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
                       "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt PYTHONPATH=/workspace; "
                       f"python3 /workspace/{rel}/control_seq12_jacobian_diag.py --inner-run")
    summary = analyse()
    out = RESULTS / "jacobian_trajectory_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN12_JACOBIAN_RESULT:", out)
    print(json.dumps(summary["comparison"], sort_keys=True))


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
    candidates = sorted(Path(root).rglob("jacobian_trajectory_summary.json"))
    if len(candidates) != 1:
        raise SystemExit(f"expected exactly one jacobian summary, found {len(candidates)}")
    summary = json.loads(candidates[0].read_text(encoding="utf-8"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "issue310_gen12_jacobian_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN12_AGGREGATE:", out)
    print(json.dumps(summary.get("comparison", {}), sort_keys=True))


def main() -> None:
    if "--p0" in sys.argv: p0(); return
    if "--p1" in sys.argv: p1(); return
    if "--p2" in sys.argv: p2(); return
    if "--inner-run" in sys.argv: raise SystemExit(inner_run())
    if "--case" in sys.argv: run_case(); return
    if "--aggregate" in sys.argv: aggregate(); return
    raise SystemExit("choose --p0/--p1/--p2/--case/--aggregate")


if __name__ == "__main__":
    main()
