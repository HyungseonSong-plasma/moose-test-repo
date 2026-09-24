"""Issue #310 Generation 13: direct 20x20 electron-response basis diagnostic.

Use the accepted end-of-step-1 state from Gen12 run 35975788441 as a
read-only prior-generation operating point.  Disable Poisson re-solution only
inside this diagnostic harness, prescribe the entering potential profile, and
run one electron timestep for a reference plus symmetric +/-1e-4 V cellwise
basis perturbations.  Central differences estimate dn_e/dphi directly.
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
STATE_FILE = ROOT / "gen13_step1_state.json"
GENERATED = ROOT / "generated_fp13_basis"
RESULTS = ROOT / "results_fp13_basis"
NCELL = 20
DELTA_PHI = 1.0e-4
CHI_E = 100.0
CHI_H = 400.0
RATIO = 4
FP_MAX = 3000


def _spec() -> dict[str, object]:
    return {
        "name": "basis_reference",
        "architecture": "transient_timeaware",
        "algorithm": "picard",
        "mode": "thermal",
        "chi": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": 1,
        "ratio": RATIO,
        "fp_max": FP_MAX,
        "relaxation_factor": 2.0 / (1.0 + CHI_E),
    }


def _piecewise(values: list[float]) -> str:
    if len(values) != NCELL:
        raise ValueError("expected 20 cell values")
    dx = 0.01 / NCELL
    expr = f"{values[-1]:.17g}"
    for i in range(NCELL - 2, -1, -1):
        edge = (i + 1) * dx
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


def _standalone_fast(base_fast: str, state: dict[str, object], cell: int | None, sign: int) -> str:
    fast = base_fast
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
  [gen13_log_e_ic]
    type = ParsedFunction
    expression = '{_piecewise([float(v) for v in state["log_e"]])}'
  []
  [gen13_n_epsilon_ic]
    type = ParsedFunction
    expression = '{_piecewise([float(v) for v in state["n_epsilon"]])}'
  []
  [gen13_phi_ic]
    type = ParsedFunction
    expression = '{_piecewise(potential)}'
  []
[]

[ICs]
  [gen13_log_e]
    type = FunctionIC
    variable = log_e
    function = gen13_log_e_ic
  []
  [gen13_n_epsilon]
    type = FunctionIC
    variable = n_epsilon
    function = gen13_n_epsilon_ic
  []
  [gen13_phi]
    type = FunctionIC
    variable = potential_from_poisson
    function = gen13_phi_ic
  []
[]
"""
    fast = fast.replace(problem_anchor, problem_anchor + functions_ics, 1)

    multi_start = fast.index("[MultiApps]\n")
    post_start = fast.index("[Postprocessors]\n", multi_start)
    fast = fast[:multi_start] + fast[post_start:]

    spec = _spec()
    old_final = seq08.FINAL_TAU
    old_cycles = seq08.HEAVY_CYCLES
    try:
        seq08.FINAL_TAU = 400.0
        seq08.HEAVY_CYCLES = 1
        with wall08._clock(spec):
            p = seq08._params(spec)
    finally:
        seq08.FINAL_TAU = old_final
        seq08.HEAVY_CYCLES = old_cycles
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


def _base_fast() -> str:
    spec = _spec()
    old_final = seq08.FINAL_TAU
    old_cycles = seq08.HEAVY_CYCLES
    try:
        seq08.FINAL_TAU = 400.0
        seq08.HEAVY_CYCLES = 1
        with wall08._clock(spec):
            p = seq08._params(spec)
            _, fast, _ = seq08._render_case(spec, p)
    finally:
        seq08.FINAL_TAU = old_final
        seq08.HEAVY_CYCLES = old_cycles
    return fast


def _case_name(cell: int | None, sign: int) -> str:
    if cell is None:
        return "reference"
    return f"cell{cell:02d}_{'plus' if sign > 0 else 'minus'}"


def build(clean: bool = True) -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if state["source_run"] != 35975788441 or state["source_head"] != "3024aaade8e476e2cd40fd1132fc79ae6123c735":
        raise RuntimeError("Gen12 state provenance changed")
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    template = _base_fast()
    cases = [(None, 0)] + [(i, s) for i in range(NCELL) for s in (-1, 1)]
    for cell, sign in cases:
        name = _case_name(cell, sign)
        d = GENERATED / name
        d.mkdir(parents=True, exist_ok=True)
        fast = _standalone_fast(template, state, cell, sign)
        (d / "fast_sub.i").write_text(fast, encoding="utf-8")
        shutil.copy2(base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 310,
                "sequence": 13,
                "diagnostic": "20x20 prescribed-potential central-difference electron response",
                "delta_phi_V": DELTA_PHI,
                "cases": [_case_name(c, s) for c, s in cases],
                "source_state": str(STATE_FILE.relative_to(REPO)),
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def p0() -> None:
    build()
    dirs = [p for p in GENERATED.iterdir() if p.is_dir()]
    assert len(dirs) == 41
    ref = (GENERATED / "reference" / "fast_sub.i").read_text(encoding="utf-8")
    assert "[MultiApps]" not in ref
    assert "[Transfers]" not in ref
    assert "type = FunctionIC" in ref
    assert "gen13_phi_ic" in ref
    assert "num_steps = 1" in ref
    plus = (GENERATED / "cell00_plus" / "fast_sub.i").read_text(encoding="utf-8")
    minus = (GENERATED / "cell00_minus" / "fast_sub.i").read_text(encoding="utf-8")
    assert plus != minus and plus != ref and minus != ref
    print("ISSUE310_GEN13_BASIS_P0: PASS")


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    names = ("reference", "cell00_plus", "cell00_minus", "cell19_plus", "cell19_minus")
    cmds = "; ".join(
        f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp13_basis/{name}/fast_sub.i"
        for name in names
    )
    base._docker("set -euo pipefail; source /environment; export PYTHONPATH=/workspace; " + cmds)
    print("ISSUE310_GEN13_BASIS_P1: PASS")


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    names = ("reference", "cell00_plus", "cell00_minus", "cell19_plus", "cell19_minus")
    checks = "; ".join(
        f"cd /workspace/{rel}/generated_fp13_basis/{name} && /workspace/physics_app/physics-opt --check-input -i fast_sub.i"
        for name in names
    )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + checks
    )
    print("ISSUE310_GEN13_BASIS_P2: PASS")


def _profile(case_dir: Path) -> dict[str, list[float]]:
    files = sorted(case_dir.glob("*energy_profile*.csv"))
    if not files:
        raise RuntimeError(f"missing energy profile in {case_dir}")
    chosen = None
    rows = None
    for path in files:
        with path.open(newline="", encoding="utf-8") as handle:
            rr = list(csv.DictReader(handle))
        if rr and "electron_density_out" in rr[0]:
            chosen = path
            rows = rr
    if chosen is None or rows is None:
        raise RuntimeError(f"no usable energy profile in {case_dir}")
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


def inner_run() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    if not GENERATED.exists():
        build()
    failures = []
    elapsed = {}
    names = ["reference"] + [_case_name(i, s) for i in range(NCELL) for s in (-1, 1)]
    for name in names:
        d = GENERATED / name
        log = RESULTS / f"{name}_runtime.log"
        started = time.perf_counter()
        with log.open("w", encoding="utf-8") as handle:
            cp = subprocess.run(
                [str(REPO / "physics_app" / "physics-opt"), "-i", "fast_sub.i"],
                cwd=d,
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
        elapsed[name] = time.perf_counter() - started
        if cp.returncode != 0:
            failures.append({"case": name, "returncode": cp.returncode})
    (RESULTS / "basis_runtime_status.json").write_text(
        json.dumps({"failures": failures, "elapsed_seconds": elapsed}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 1 if failures else 0


def _rank(a: list[list[float]]) -> tuple[int, list[float]]:
    m = [row[:] for row in a]
    nr = len(m)
    nc = len(m[0])
    scale = max(abs(v) for row in m for v in row)
    tol = max(scale * 1e-10, 1e-300)
    pivots = []
    r = 0
    for c in range(nc):
        p = max(range(r, nr), key=lambda i: abs(m[i][c]), default=r)
        if r >= nr or abs(m[p][c]) <= tol:
            continue
        m[r], m[p] = m[p], m[r]
        pv = m[r][c]
        pivots.append(abs(pv))
        for i in range(r + 1, nr):
            q = m[i][c] / pv
            if q == 0.0:
                continue
            for j in range(c, nc):
                m[i][j] -= q * m[r][j]
        r += 1
        if r == nr:
            break
    return r, pivots


def analyse() -> dict[str, object]:
    ref = _profile(GENERATED / "reference")
    J = [[0.0 for _ in range(NCELL)] for _ in range(NCELL)]
    even_error = []
    for j in range(NCELL):
        plus = _profile(GENERATED / _case_name(j, 1))
        minus = _profile(GENERATED / _case_name(j, -1))
        odd2 = [plus["ne"][i] - minus["ne"][i] for i in range(NCELL)]
        even2 = [plus["ne"][i] + minus["ne"][i] - 2.0 * ref["ne"][i] for i in range(NCELL)]
        for i in range(NCELL):
            J[i][j] = odd2[i] / (2.0 * DELTA_PHI)
        odd_norm = math.sqrt(sum(v * v for v in odd2))
        even_norm = math.sqrt(sum(v * v for v in even2))
        even_error.append(even_norm / max(odd_norm, 1.0))

    rank, pivots = _rank(J)
    norm2 = sum(v * v for row in J for v in row)
    off2 = sum(J[i][j] ** 2 for i in range(NCELL) for j in range(NCELL) if i != j)
    diag = [J[i][i] for i in range(NCELL)]
    a1 = [ref["ne"][i] / max((2.0 / 3.0) * ref["mean_e"][i], 1e-30) for i in range(NCELL)]
    a2 = [ref["ne"][i] * ref["mu"][i] / max(ref["D"][i], 1e-300) for i in range(NCELL)]
    ratio1 = [diag[i] / a1[i] if a1[i] != 0.0 else None for i in range(NCELL)]
    ratio2 = [diag[i] / a2[i] if a2[i] != 0.0 else None for i in range(NCELL)]
    finite1 = sorted(v for v in ratio1 if v is not None and math.isfinite(v))
    finite2 = sorted(v for v in ratio2 if v is not None and math.isfinite(v))
    med = lambda v: (v[len(v)//2] if len(v)%2 else 0.5*(v[len(v)//2-1]+v[len(v)//2])) if v else None
    return {
        "issue": 310,
        "sequence": 13,
        "diagnostic": "direct prescribed-potential central-difference electron response",
        "source_run": 35975788441,
        "source_head": "3024aaade8e476e2cd40fd1132fc79ae6123c735",
        "delta_phi_V": DELTA_PHI,
        "matrix_rank": rank,
        "rank_pivots": pivots,
        "full_rank": rank == NCELL,
        "offdiagonal_frobenius_fraction": math.sqrt(off2 / norm2) if norm2 > 0 else None,
        "max_even_to_odd_fd_ratio": max(even_error),
        "median_even_to_odd_fd_ratio": med(sorted(even_error)),
        "matrix_row_major_m3_per_V": [v for row in J for v in row],
        "matrix_diagonal_m3_per_V": diag,
        "gamma_A1_diagonal": ratio1,
        "gamma_A2_diagonal": ratio2,
        "gamma_A1_diagonal_median": med(finite1),
        "gamma_A2_diagonal_median": med(finite2),
        "reference_profile": ref,
        "guard": "This is a one-electron-timestep diagnostic around a frozen prior-generation operating point; it identifies the discrete electron-map response, not the full coupled Gummel Jacobian."
    }


def run_case() -> None:
    if not GENERATED.exists():
        build()
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq13_basis.py --inner-run; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp13_basis /workspace/{rel}/generated_fp13_basis"
    )
    summary = analyse()
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "basis_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN13_BASIS_RESULT:", out)
    print(json.dumps({
        "rank": summary["matrix_rank"],
        "offdiag": summary["offdiagonal_frobenius_fraction"],
        "max_fd_nonlinearity": summary["max_even_to_odd_fd_ratio"],
        "gamma_A1_median": summary["gamma_A1_diagonal_median"],
        "gamma_A2_median": summary["gamma_A2_diagonal_median"],
    }, sort_keys=True))


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
    found = list(Path(root).rglob("basis_summary.json"))
    if len(found) != 1:
        raise SystemExit(f"expected one basis summary, found {len(found)}")
    summary = json.loads(found[0].read_text(encoding="utf-8"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "issue310_gen13_basis_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE310_GEN13_BASIS_AGGREGATE:", "FULL_RANK" if summary.get("full_rank") else "RANK_DEFICIENT")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--inner-run", action="store_true")
    ap.add_argument("--case", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()
    if args.p0: p0()
    elif args.p1: p1()
    elif args.p2: p2()
    elif args.inner_run: raise SystemExit(inner_run())
    elif args.case: run_case()
    elif args.aggregate: aggregate()
    else: ap.error("choose an action")


if __name__ == "__main__":
    main()
