#!/usr/bin/env python3

import csv
import math
from pathlib import Path

CASES = [
    ("phi_ic_000", 0.00),
    ("phi_ic_025", 0.25),
    ("phi_ic_050", 0.50),
    ("phi_ic_075", 0.75),
    ("phi_ic_100", 1.00),
]

BALANCE_TOL = 1.0e-8
POTENTIAL_SPREAD_TOL = 1.0e-8
LEFT_FLUX_TOL = 1.0e-30


def rel_error(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def linear_fit(xs, ys):
    n = len(xs)
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    sxx = sum((x - xbar) ** 2 for x in xs)
    if sxx == 0:
        return float("nan"), float("nan"), float("nan")
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sxx
    intercept = ybar - slope * xbar
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return intercept, slope, r2


def normalized_spread(values):
    return (max(values) - min(values)) / max(max(abs(v) for v in values), 1.0)


def load_case(stem, scale):
    status_path = Path("status") / f"{stem}.status"
    csv_path = Path("generated") / f"{stem}_out.csv"

    solve_rc = None
    if status_path.exists():
        text = status_path.read_text().strip()
        if text:
            solve_rc = int(text)

    if solve_rc is None or solve_rc != 0 or not csv_path.exists():
        return {
            "stem": stem,
            "scale": scale,
            "solve_rc": solve_rc,
            "solved": False,
        }

    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))

    r0 = min(rows, key=lambda r: abs(float(r["time"])))
    positive = [r for r in rows if float(r["time"]) > 0]
    if not positive:
        return {
            "stem": stem,
            "scale": scale,
            "solve_rc": solve_rc,
            "solved": False,
            "reason": "no positive-time row",
        }

    r1 = positive[0]
    dt = float(r1["time"]) - float(r0["time"])
    m0 = float(r0["ion_mass_inventory"])
    m1 = float(r1["ion_mass_inventory"])
    dm = m1 - m0
    left = float(r1["left_migration_mass_loss_rate"])
    right = float(r1["right_migration_mass_loss_rate"])
    total = left + right
    expected_dm = -total * dt
    balance = rel_error(dm, expected_dm)
    inv_rate = -dm / dt
    closure = inv_rate / total if total != 0 else float("nan")

    return {
        "stem": stem,
        "scale": scale,
        "solve_rc": solve_rc,
        "solved": True,
        "dt": dt,
        "dm": dm,
        "inv_rate": inv_rate,
        "left": left,
        "right": right,
        "total": total,
        "closure": closure,
        "balance": balance,
        "phi_min": float(r1["phi_min"]),
        "phi_max": float(r1["phi_max"]),
        "passes": balance < BALANCE_TOL,
    }


def main():
    data = [load_case(stem, scale) for stem, scale in CASES]

    print("scale  solve  -dm/dt         left_mig        right_mig       G_end           C               balance_err      phi_min        phi_max")
    print("-----  -----  --------------  --------------  --------------  --------------  --------------  ---------------  -------------  -------------")
    for d in data:
        if not d["solved"]:
            rc = "?" if d.get("solve_rc") is None else str(d["solve_rc"])
            print(f"{d['scale']:4.2f}   FAIL(rc={rc})")
            continue
        print(
            f"{d['scale']:4.2f}   PASS   "
            f"{d['inv_rate']: .6e}   {d['left']: .6e}   {d['right']: .6e}   "
            f"{d['total']: .6e}   {d['closure']: .6f}   {d['balance']: .6e}   "
            f"{d['phi_min']: .6e}   {d['phi_max']: .6e}"
        )

    print("\nPRE-REGISTERED CLASSIFICATION")

    unsolved = [d for d in data if not d["solved"]]
    if unsolved:
        print("CLASS = SOLVER_BRANCH")
        print("Conclusion: at least one amplitude did not produce an interpretable first positive-time state.")
        print("Next: inspect only the failed-case nonlinear logs before applying the closure decision matrix.")
        return 0

    phi_min_spread = normalized_spread([d["phi_min"] for d in data])
    phi_max_spread = normalized_spread([d["phi_max"] for d in data])
    print(f"phi_min normalized spread = {phi_min_spread:.6e}")
    print(f"phi_max normalized spread = {phi_max_spread:.6e}")

    if max(phi_min_spread, phi_max_spread) > POTENTIAL_SPREAD_TOL:
        print("CLASS = G_FINAL_PHI_DIFFERS")
        print("Conclusion: final electrostatic states are not mutually consistent; wall-path inference is invalid.")
        return 0

    if any(abs(d["left"]) >= LEFT_FLUX_TOL or d["right"] <= 0 for d in data):
        print("CLASS = H_DIRECTIONALITY_BREAKS")
        print("Conclusion: wall normal / FaceArg / directed-field construction must be checked before state hypotheses.")
        return 0

    exact = data[-1]
    if not exact["passes"]:
        print("CLASS = F_EXACT_SWEEP_CASE_FAILS")
        print("Conclusion: the sweep is not equivalent to the known-good exact-IC wall-only baseline.")
        print("Next: diff the sweep exact case against wall_only_exact_phi_ic before interpreting IC causality.")
        return 0

    if all(d["passes"] for d in data):
        print("CLASS = E_ALL_CONSERVE")
        print("Conclusion: this controlled sweep does not reproduce the incident; reconcile runtime/input/source identity.")
        return 0

    if (not data[0]["passes"]) and all(d["passes"] for d in data[1:]):
        print("CLASS = B_ZERO_ONLY_ANOMALY")
        print("Conclusion: special zero-field initialization degeneracy; hard max() alone is already insufficient.")
        return 0

    closures = [d["closure"] for d in data]
    xs = [d["scale"] for d in data]
    intercept, slope, r2 = linear_fit(xs, closures)
    closure_range = max(closures) - min(closures)
    mean_abs_from_one = sum(abs(c - 1.0) for c in closures) / len(closures)
    monotonic = all(closures[i + 1] >= closures[i] - 1.0e-8 for i in range(len(closures) - 1))

    print(f"C(s) intercept = {intercept:.6e}")
    print(f"C(s) slope     = {slope:.6e}")
    print(f"C(s) R^2       = {r2:.6e}")
    print(f"range(C)       = {closure_range:.6e}")
    print(f"mean|C-1|      = {mean_abs_from_one:.6e}")
    print(f"monotonic      = {monotonic}")

    if monotonic and r2 >= 0.95 and abs(slope) >= 0.2 and closure_range >= 0.2:
        print("CLASS = A_STRONG_CONTINUOUS_IC_DEPENDENCE")
        print("Conclusion: first-step wall residual has strong initial/path-state dependence despite common final phi.")
        return 0

    pass_flags = [d["passes"] for d in data]
    transitions = sum(pass_flags[i] != pass_flags[i + 1] for i in range(len(pass_flags) - 1))
    if transitions == 1 and pass_flags[-1] and not pass_flags[0]:
        print("CLASS = C_THRESHOLD_BEHAVIOR")
        print("Conclusion: a threshold/branch mechanism remains; bracket the transition with a finer IC sweep.")
        return 0

    if closure_range <= 0.05 and mean_abs_from_one >= 0.05:
        print("CLASS = D_IC_INDEPENDENT_FAILURE")
        print("Conclusion: initial phi is not causal; inspect wall residual/inventory accounting and boundary face contract.")
        return 0

    print("CLASS = I_MIXED_NON_MONOTONIC")
    print("Conclusion: no pre-registered single-mechanism pattern fits; preserve logs and instrument per-iteration wall flux before physics changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
