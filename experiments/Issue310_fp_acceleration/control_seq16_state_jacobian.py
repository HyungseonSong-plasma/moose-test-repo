"""Issue #310 Generation 16A: state-dependent direct basis Jacobian diagnostic.

Run the qualified time-aware Picard-2x control, sample the converged fast-plasma
state after electron steps 1, 2 and 3, then independently evaluate a 20x20
central-difference electron-map Jacobian at each state.

For each state:
  J = d n_e(next electron solve) / d phi
  W = diag(VTe / n_e) J

The experiment compares W(t1), W(t2), W(t3) to test whether the normalized
Jacobian shape is state dependent rather than a fixed matrix with scalar
state rescaling.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq08 as seq08
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08

base = wall08.base
GENERATED = ROOT / "generated_fp16_state_jacobian"
RESULTS = ROOT / "results_fp16_state_jacobian"

NCELL = 20
XMIN = 0.0
XMAX = 0.01
DX = (XMAX - XMIN) / NCELL
DELTA_PHI = 1.0e-4
CHI_E = 100.0
CHI_H = 400.0
RATIO = 4
FP_MAX = 3000
FINAL_TAU = 400.0
HEAVY_CYCLES = 1
BASE_ALPHA = 2.0 / (1.0 + CHI_E)
wall08.FINAL_TAU = FINAL_TAU


def _spec() -> dict[str, object]:
    return {
        "name": "state_control",
        "architecture": "transient_timeaware",
        "algorithm": "picard",
        "mode": "thermal",
        "chi": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "ratio": RATIO,
        "fp_max": FP_MAX,
        "relaxation_factor": BASE_ALPHA,
    }


def _params() -> dict[str, object]:
    spec = _spec()
    with wall08._clock(spec):
        p = wall08.wall03._params(spec)
    p.update(
        heavy_to_electron_dt_ratio=RATIO,
        architecture="transient_timeaware",
        fixed_point_algorithm="picard",
        relaxation_factor=BASE_ALPHA,
    )
    return p


def _render_timeaware() -> tuple[str, str, str]:
    spec = _spec()
    p = _params()
    old_final = seq08.FINAL_TAU
    old_cycles = seq08.HEAVY_CYCLES
    try:
        seq08.FINAL_TAU = FINAL_TAU
        seq08.HEAVY_CYCLES = HEAVY_CYCLES
        with wall08._clock(spec):
            parent, fast, poisson = seq08._render_case(spec, p)
    finally:
        seq08.FINAL_TAU = old_final
        seq08.HEAVY_CYCLES = old_cycles
    return parent, fast, poisson


def _centers() -> list[float]:
    return [XMIN + (i + 0.5) * DX for i in range(NCELL)]


def _instrument_state(fast: str) -> str:
    fp_anchor = """  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
"""
    if fast.count(fp_anchor) != 1:
        raise RuntimeError("fixed-point postprocessor anchor changed")

    pps = []
    for i, x in enumerate(_centers()):
        for key, var in (
            ("log_e", "log_e"),
            ("n_epsilon", "n_epsilon"),
            ("phi", "potential_from_poisson"),
        ):
            pps.append(
                f"""  [state_{key}_{i:02d}]
    type = PointValue
    variable = {var}
    point = '{x:.17g} 0 0'
    execute_on = 'TIMESTEP_END'
  []
"""
            )
    fast = fast.replace(fp_anchor, "".join(pps) + fp_anchor, 1)

    outputs = """[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    new_row_tolerance = 1.0e-30
  []
"""
    if fast.count(outputs) != 1:
        raise RuntimeError("fast output anchor changed")
    fast = fast.replace(
        outputs,
        outputs + """  [state_csv]
    type = CSV
    execute_on = 'TIMESTEP_END'
    execute_postprocessors_on = 'TIMESTEP_END'
    new_row_detection_columns = all
    new_row_tolerance = 1.0e-30
    precision = 17
    scientific_notation = true
  []
""",
        1,
    )
    return fast


def build_control(clean: bool = True) -> None:
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    d = GENERATED / "state_control"
    d.mkdir(parents=True, exist_ok=True)
    parent, fast, poisson = _render_timeaware()
    fast = _instrument_state(fast)
    (d / "input.i").write_text(parent, encoding="utf-8")
    (d / "fast_sub.i").write_text(fast, encoding="utf-8")
    (d / "poisson_sub.i").write_text(poisson, encoding="utf-8")
    shutil.copy2(base.ELECTRON_MOMENTS, d / "electron_moments.txt")
    shutil.copy2(base.ELASTIC_DATA, d / "o2_elastic.txt")
    shutil.copy2(base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")


def _piecewise(values: list[float]) -> str:
    if len(values) != NCELL:
        raise ValueError("expected 20 cell values")
    expr = f"{values[-1]:.17g}"
    for i in range(NCELL - 2, -1, -1):
        edge = (i + 1) * DX
        expr = f"if(x<{edge:.17g},{values[i]:.17g},{expr})"
    return expr


def _replace_initial(text: str, variable: str) -> str:
    pattern = (
        rf"(  \[{re.escape(variable)}\]\n"
        rf"    type = MooseVariableFVReal\n)"
        rf"    initial_condition = [^\n]+\n"
    )
    text, n = re.subn(pattern, r"\1", text, count=1)
    if n != 1:
        raise RuntimeError(f"initial-condition anchor changed for {variable}")
    return text


def _base_fast() -> str:
    _, fast, _ = _render_timeaware()
    return fast


def _standalone_fast(template: str, state: dict[str, object], cell: int | None, sign: int) -> str:
    fast = template
    fast = _replace_initial(fast, "log_e")
    fast = _replace_initial(fast, "n_epsilon")
    fast = _replace_initial(fast, "potential_from_poisson")

    potential = [float(v) for v in state["potential_V"]]
    if cell is not None:
        potential[cell] += sign * DELTA_PHI

    problem_anchor = """[Problem]
  kernel_coverage_check = false
[]
"""
    if fast.count(problem_anchor) != 1:
        raise RuntimeError("Problem anchor changed")

    functions_ics = f"""
[Functions]
  [gen16_log_e_ic]
    type = ParsedFunction
    expression = '{_piecewise([float(v) for v in state["log_e"]])}'
  []
  [gen16_n_epsilon_ic]
    type = ParsedFunction
    expression = '{_piecewise([float(v) for v in state["n_epsilon"]])}'
  []
  [gen16_phi_ic]
    type = ParsedFunction
    expression = '{_piecewise(potential)}'
  []
[]

[ICs]
  [gen16_log_e]
    type = FunctionIC
    variable = log_e
    function = gen16_log_e_ic
  []
  [gen16_n_epsilon]
    type = FunctionIC
    variable = n_epsilon
    function = gen16_n_epsilon_ic
  []
  [gen16_phi]
    type = FunctionIC
    variable = potential_from_poisson
    function = gen16_phi_ic
  []
[]
"""
    fast = fast.replace(problem_anchor, problem_anchor + functions_ics, 1)

    multi_start = fast.index("[MultiApps]\n")
    post_start = fast.index("[Postprocessors]\n", multi_start)
    fast = fast[:multi_start] + fast[post_start:]

    p = _params()
    dt = float(p["dt_e_s"])
    fast, n = re.subn(
        r"  end_time = [^\n]+\n  num_steps = \d+\n",
        f"  end_time = {dt:.17g}\n  num_steps = 1\n",
        fast,
        count=1,
    )
    if n != 1:
        raise RuntimeError("Executioner end-time anchor changed")
    return fast


def _basis_name(cell: int | None, sign: int) -> str:
    if cell is None:
        return "reference"
    return f"cell{cell:02d}_{'plus' if sign > 0 else 'minus'}"


def _build_basis(step: int, state: dict[str, object]) -> Path:
    root = GENERATED / f"basis_step{step}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    template = _base_fast()
    cases = [(None, 0)] + [(i, s) for i in range(NCELL) for s in (-1, 1)]
    for cell, sign in cases:
        name = _basis_name(cell, sign)
        d = root / name
        d.mkdir(parents=True)
        (d / "fast_sub.i").write_text(_standalone_fast(template, state, cell, sign), encoding="utf-8")
        shutil.copy2(base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
    return root


def _extract_states(control_dir: Path) -> list[dict[str, object]]:
    candidates = sorted(control_dir.glob("*state_csv.csv"))
    rows = []
    for path in candidates:
        with path.open(newline="", encoding="utf-8") as handle:
            rr = list(csv.DictReader(handle))
        if rr and "state_log_e_00" in rr[0]:
            rows = rr
    if not rows:
        raise RuntimeError("missing state_csv output")

    positive = []
    seen = set()
    for row in rows:
        t = float(row["time"])
        if t <= 0.0 or t in seen:
            continue
        seen.add(t)
        positive.append(row)
    positive.sort(key=lambda r: float(r["time"]))
    if len(positive) < 3:
        raise RuntimeError(f"expected >=3 positive electron-step states, found {len(positive)}")

    states = []
    for step, row in enumerate(positive[:3], start=1):
        state = {
            "step": step,
            "time_s": float(row["time"]),
            "log_e": [float(row[f"state_log_e_{i:02d}"]) for i in range(NCELL)],
            "n_epsilon": [float(row[f"state_n_epsilon_{i:02d}"]) for i in range(NCELL)],
            "potential_V": [float(row[f"state_phi_{i:02d}"]) for i in range(NCELL)],
        }
        states.append(state)
        (RESULTS / f"step{step}_state.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return states


def _profile(case_dir: Path) -> dict[str, list[float]]:
    files = sorted(case_dir.glob("*energy_profile*.csv"))
    rows = None
    for path in files:
        with path.open(newline="", encoding="utf-8") as handle:
            rr = list(csv.DictReader(handle))
        if rr and "electron_density_out" in rr[0]:
            rows = rr
    if rows is None:
        raise RuntimeError(f"missing usable energy profile in {case_dir}")
    rows.sort(key=lambda r: int(float(r["id"])))
    def col(name: str) -> list[float]:
        return [float(r[name]) for r in rows]
    return {
        "ne": col("electron_density_out"),
        "phi": col("potential_from_poisson"),
        "mean_e": col("mean_energy_out"),
        "mu": col("mobility_out"),
        "D": col("diffusion_out"),
    }


def _rank(a: list[list[float]]) -> int:
    m = [row[:] for row in a]
    nr = len(m)
    nc = len(m[0])
    scale = max(abs(v) for row in m for v in row)
    tol = max(scale * 1e-10, 1e-300)
    r = 0
    for c in range(nc):
        if r >= nr:
            break
        p = max(range(r, nr), key=lambda i: abs(m[i][c]))
        if abs(m[p][c]) <= tol:
            continue
        m[r], m[p] = m[p], m[r]
        pv = m[r][c]
        for i in range(r + 1, nr):
            q = m[i][c] / pv
            if q:
                for j in range(c, nc):
                    m[i][j] -= q * m[r][j]
        r += 1
    return r


def _median(v: list[float]) -> float | None:
    if not v:
        return None
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def _band5_error(W: list[list[float]]) -> float:
    proj = [[0.0 for _ in range(NCELL)] for _ in range(NCELL)]
    for i in range(NCELL):
        for j in range(NCELL):
            if i != j and abs(i - j) <= 5:
                proj[i][j] = W[i][j]
        proj[i][i] = -sum(proj[i][j] for j in range(NCELL) if j != i)
    norm2 = sum(x*x for row in W for x in row)
    err2 = sum((proj[i][j]-W[i][j])**2 for i in range(NCELL) for j in range(NCELL))
    return math.sqrt(err2 / norm2) if norm2 else 0.0


def _analyse_basis(root: Path, step: int, time_s: float) -> dict[str, object]:
    ref = _profile(root / "reference")
    J = [[0.0 for _ in range(NCELL)] for _ in range(NCELL)]
    fd_ratio = []
    for j in range(NCELL):
        plus = _profile(root / _basis_name(j, 1))
        minus = _profile(root / _basis_name(j, -1))
        odd = [plus["ne"][i] - minus["ne"][i] for i in range(NCELL)]
        even = [plus["ne"][i] + minus["ne"][i] - 2.0 * ref["ne"][i] for i in range(NCELL)]
        for i in range(NCELL):
            J[i][j] = odd[i] / (2.0 * DELTA_PHI)
        on = math.sqrt(sum(v*v for v in odd))
        en = math.sqrt(sum(v*v for v in even))
        fd_ratio.append(en / max(on, 1.0))

    a1 = [ref["ne"][i] / max((2.0/3.0) * ref["mean_e"][i], 1e-30) for i in range(NCELL)]
    W = [[J[i][j] / a1[i] for j in range(NCELL)] for i in range(NCELL)]
    norm2 = sum(v*v for row in J for v in row)
    off2 = sum(J[i][j]**2 for i in range(NCELL) for j in range(NCELL) if i != j)
    diag_ratio = [J[i][i] / a1[i] for i in range(NCELL)]
    row_sum_ratio = [
        abs(sum(J[i])) / max(abs(J[i][i]), 1.0) for i in range(NCELL)
    ]
    return {
        "step": step,
        "time_s": time_s,
        "matrix_rank": _rank(J),
        "full_rank": _rank(J) == NCELL,
        "offdiagonal_frobenius_fraction": math.sqrt(off2/norm2) if norm2 else None,
        "max_even_to_odd_fd_ratio": max(fd_ratio),
        "median_diagonal_over_A1": _median(diag_ratio),
        "median_abs_row_sum_over_abs_diagonal": _median(row_sum_ratio),
        "band5_projection_relative_error": _band5_error(W),
        "J_row_major_m3_per_V": [v for row in J for v in row],
        "W_row_major": [v for row in W for v in row],
        "reference_profile": ref,
    }


def _relative_matrix_delta(a: list[float], b: list[float]) -> float:
    den = math.sqrt(sum(x*x for x in a))
    num = math.sqrt(sum((b[i]-a[i])**2 for i in range(len(a))))
    return num / den if den else 0.0


def _run_one(command: list[str], cwd: Path, log: Path) -> int:
    with log.open("w", encoding="utf-8") as handle:
        cp = subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, check=False)
    return cp.returncode


def inner_run() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    if not (GENERATED / "state_control" / "input.i").exists():
        build_control()

    control = GENERATED / "state_control"
    rc = _run_one(
        [str(REPO / "physics_app" / "physics-opt"), "-i", "input.i"],
        control,
        RESULTS / "state_control_runtime.log",
    )
    if rc:
        return rc

    states = _extract_states(control)
    summaries = []
    failures = []
    for state in states:
        step = int(state["step"])
        root = _build_basis(step, state)
        for name in ["reference"] + [_basis_name(i, s) for i in range(NCELL) for s in (-1, 1)]:
            d = root / name
            log = RESULTS / f"step{step}_{name}.log"
            rc = _run_one([str(REPO / "physics_app" / "physics-opt"), "-i", "fast_sub.i"], d, log)
            if rc:
                failures.append({"step": step, "case": name, "returncode": rc})
            else:
                log.unlink(missing_ok=True)
        if failures:
            break
        summaries.append(_analyse_basis(root, step, float(state["time_s"])))

    if failures:
        (RESULTS / "state_jacobian_failures.json").write_text(
            json.dumps(failures, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 1

    by = {int(x["step"]): x for x in summaries}
    cross = {}
    for a, b in ((1,2),(2,3),(1,3)):
        cross[f"W_step{a}_to_step{b}_relative_frobenius_delta"] = _relative_matrix_delta(
            list(by[a]["W_row_major"]), list(by[b]["W_row_major"])
        )
        cross[f"J_step{a}_to_step{b}_relative_frobenius_delta"] = _relative_matrix_delta(
            list(by[a]["J_row_major_m3_per_V"]), list(by[b]["J_row_major_m3_per_V"])
        )

    summary = {
        "issue": 310,
        "sequence": 16,
        "lane": "state_dependent_basis_jacobian",
        "delta_phi_V": DELTA_PHI,
        "control_fp_baseline_expected": [6, 516, 549, 601],
        "states": summaries,
        "cross_state": cross,
        "guard": (
            "Each matrix is the one-electron-step prescribed-potential response around a "
            "converged control state. W normalizes each row by n_e/VTe at that same state."
        ),
    }
    (RESULTS / "state_jacobian_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_GEN16_STATE_JACOBIAN: PASS")
    print(json.dumps(cross, sort_keys=True))
    return 0


def p0() -> None:
    build_control()
    d = GENERATED / "state_control"
    fast = (d / "fast_sub.i").read_text(encoding="utf-8")
    assert fast.count("type = PointValue") >= 3 * NCELL
    assert "state_log_e_00" in fast and "state_n_epsilon_19" in fast and "state_phi_19" in fast
    assert "execute_on = 'TIMESTEP_END'" in fast
    assert "type = TransientMultiApp" in fast
    print("ISSUE310_GEN16_STATE_JACOBIAN_P0: PASS")


def p1() -> None:
    build_control()
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp16_state_jacobian/state_control/input.i"
    )
    print("ISSUE310_GEN16_STATE_JACOBIAN_P1: PASS")


def p2() -> None:
    build_control()
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; "
        f"cd /workspace/{rel}/generated_fp16_state_jacobian/state_control && "
        "/workspace/physics_app/physics-opt --check-input -i input.i && "
        "/workspace/physics_app/physics-opt --check-input -i fast_sub.i && "
        "/workspace/physics_app/physics-opt --check-input -i poisson_sub.i"
    )
    print("ISSUE310_GEN16_STATE_JACOBIAN_P2: PASS")


def run_case() -> None:
    if not GENERATED.exists():
        build_control()
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq16_state_jacobian.py --inner-run; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp16_state_jacobian /workspace/{rel}/generated_fp16_state_jacobian"
    )
    out = RESULTS / "state_jacobian_summary.json"
    if not out.is_file():
        raise SystemExit("state_jacobian_summary.json missing")
    print("ISSUE310_GEN16_STATE_JACOBIAN_CASE:", out)


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
    found = list(Path(root).rglob("state_jacobian_summary.json"))
    if len(found) != 1:
        raise SystemExit(f"expected one state Jacobian summary, found {len(found)}")
    summary = json.loads(found[0].read_text(encoding="utf-8"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "issue310_gen16_state_jacobian_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN16_STATE_JACOBIAN_AGGREGATE: PASS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--inner-run", action="store_true")
    ap.add_argument("--case", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()
    if args.p0:
        p0()
    elif args.p1:
        p1()
    elif args.p2:
        p2()
    elif args.inner_run:
        raise SystemExit(inner_run())
    elif args.case:
        run_case()
    elif args.aggregate:
        aggregate()
    else:
        ap.error("choose an action")


if __name__ == "__main__":
    main()
