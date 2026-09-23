"""Issue #310 Sequence 07: Secant-only refinement with correct ownership.

Sequence06 showed that native Secant can reduce fixed-point work, but the
0.02 case did not preserve the Picard-2x physical trajectory. Steffensen is
deferred because its stock two-evaluation initialization reaches the unstable
raw-Picard branch before damping is applied.

This discriminator keeps the fast-app Executioner on Picard and changes only
the Poisson subapp fixed-point algorithm for Secant cases.

Cases:
  picard_2x    : Picard, relaxation = 2/(1+chi_e)
  secant_0p005 : Secant damping = 0.005
  secant_0p010 : Secant damping = 0.010
  secant_0p015 : Secant damping = 0.015
  secant_0p020 : Secant damping = 0.020

Common clock:
  chi_e = 100
  chi_h = 400
  heavy/electron dt ratio = 4
  T_final = 1200 tau_epsilon(initial)
  electron steps = 12
  heavy steps = 3

Physics, timestep, discretization, nonlinear/fixed-point tolerances, transfer
ownership, and transformed variable potential_plasma remain frozen.
Runtime convergence and physical parity versus picard_2x are recorded
separately.
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
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue306_heavy_charge_motion import wall08_control as wall08

base = wall08.base

GENERATED = ROOT / "generated_fp07"
RESULTS = ROOT / "results_fp07"

CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 1200.0
HEAVY_CYCLES = 3
RATIO = 4
FP_MAX = 3000

ALGORITHM_CASES = (
    ("picard_2x", "picard", 2.0 / (1.0 + CHI_E)),
    ("secant_0p005", "secant", 0.005),
    ("secant_0p010", "secant", 0.010),
    ("secant_0p015", "secant", 0.015),
    ("secant_0p020", "secant", 0.020),
)

SPECS = tuple(
    {
        "name": name,
        "algorithm": algorithm,
        "mode": "thermal",
        "chi": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "ratio": RATIO,
        "fp_max": FP_MAX,
        "relaxation_factor": relaxation,
    }
    for name, algorithm, relaxation in ALGORITHM_CASES
)
CASE_NAMES = tuple(str(spec["name"]) for spec in SPECS)

# wall08._clock uses this module-level value while setting the inherited base clock.
wall08.FINAL_TAU = FINAL_TAU


def _params(spec: dict[str, object]) -> dict[str, object]:
    with wall08._clock(spec):
        p = wall08.wall03._params(spec)
    p["heavy_to_electron_dt_ratio"] = RATIO
    p["fixed_point_algorithm"] = str(spec["algorithm"])
    p["relaxation_factor"] = float(spec["relaxation_factor"])
    return p


def _render_case(spec: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    with wall08._clock(spec):
        parent = wall08.wall03._parent(p)
        fast = wall08._apply_electron_sheath_factor(wall08.wall03._fast(p))
        poisson = base._poisson_child()

    poisson_algorithm = str(spec["algorithm"])

    fast_anchor = "  fixed_point_min_its = 2\n"
    if fast.count(fast_anchor) != 1:
        raise RuntimeError("fast-child fixed-point executioner anchor changed")
    fast = fast.replace(
        fast_anchor,
        "  fixed_point_algorithm = 'picard'\n" + fast_anchor,
        1,
    )

    poisson_anchor = "[Executioner]\n  type = Steady\n"
    if poisson.count(poisson_anchor) != 1:
        raise RuntimeError("Poisson executioner anchor changed")
    poisson = poisson.replace(
        poisson_anchor,
        poisson_anchor + f"  fixed_point_algorithm = '{poisson_algorithm}'\n",
        1,
    )
    return parent, fast, poisson

def build(clean: bool = True) -> list[dict[str, object]]:
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    built: list[dict[str, object]] = []

    for spec in SPECS:
        p = _params(spec)
        case_dir = GENERATED / str(p["name"])
        case_dir.mkdir(parents=True, exist_ok=True)
        parent, fast, poisson = _render_case(spec, p)

        (case_dir / "input.i").write_text(parent, encoding="utf-8")
        (case_dir / "fast_sub.i").write_text(fast, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(base.ELECTRON_MOMENTS, case_dir / "electron_moments.txt")
        shutil.copy2(base.ELASTIC_DATA, case_dir / "o2_elastic.txt")
        shutil.copy2(base.HEAVY_TRANSPORT_DATA, case_dir / "transport_data.txt")
        (case_dir / "case.json").write_text(
            json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        built.append(p)

    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 310,
                "sequence": 7,
                "objective": "refine native Secant damping with fast Picard fixed and verify physical parity against Picard-2x",
                "source_physics": "Issue306 Sequence08 thermal-heavy-wall + sheath-suppressed-electron model",
                "chi_e": CHI_E,
                "chi_h": CHI_H,
                "heavy_to_electron_dt_ratio": RATIO,
                "heavy_cycles": HEAVY_CYCLES,
                "total_fast_steps": int(FINAL_TAU / CHI_E),
                "final_tau": FINAL_TAU,
                "algorithm_cases": [
                    {
                        "name": name,
                        "algorithm": algorithm,
                        "relaxation_factor": relaxation,
                    }
                    for name, algorithm, relaxation in ALGORITHM_CASES
                ],
                "cases": built,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return built


def _normalized_fast(text: str) -> str:
    text = re.sub(
        r"(^\s*relaxation_factor\s*=\s*).+$",
        r"\1<RELAXATION_FACTOR>",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    return re.sub(
        r"(^\s*fixed_point_algorithm\s*=\s*).+$",
        r"\1<FIXED_POINT_ALGORITHM>",
        text,
        count=1,
        flags=re.MULTILINE,
    )


def _normalized_poisson(text: str) -> str:
    return re.sub(
        r"(^\s*fixed_point_algorithm\s*=\s*).+$",
        r"\1<FIXED_POINT_ALGORITHM>",
        text,
        count=1,
        flags=re.MULTILINE,
    )


def static_contract() -> dict[str, object]:
    built = build()
    if tuple(str(p["name"]) for p in built) != CASE_NAMES:
        raise RuntimeError("case ordering mismatch")
    if len(CASE_NAMES) != 5:
        raise RuntimeError("Sequence07 must contain exactly five cases")

    parent_texts: list[str] = []
    normalized_poisson: list[str] = []
    normalized_fast: list[str] = []

    for spec, p in zip(SPECS, built, strict=True):
        case_dir = GENERATED / str(p["name"])
        parent = (case_dir / "input.i").read_text(encoding="utf-8")
        fast = (case_dir / "fast_sub.i").read_text(encoding="utf-8")
        poisson = (case_dir / "poisson_sub.i").read_text(encoding="utf-8")

        expected_relax = float(spec["relaxation_factor"])
        assert math.isclose(float(p["chi_e"]), CHI_E, rel_tol=0.0, abs_tol=0.0)
        assert math.isclose(float(p["chi_h"]), CHI_H, rel_tol=0.0, abs_tol=0.0)
        assert int(p["heavy_cycles"]) == HEAVY_CYCLES
        assert int(p["fast_steps_per_heavy_cycle"]) == RATIO
        assert int(p["fast_steps_total"]) == 12
        assert math.isclose(
            float(p["end_time_tau_epsilon_initial"]), FINAL_TAU, rel_tol=0.0, abs_tol=1e-12
        )
        assert math.isclose(
            float(p["relaxation_factor"]), expected_relax, rel_tol=1e-15, abs_tol=0.0
        )
        assert 0.0 < expected_relax <= 1.0
        assert f"num_steps = {HEAVY_CYCLES}" in parent
        assert "fixed_point_max_its = 3000" in fast
        assert "fixed_point_algorithm = 'picard'" in fast
        assert f"fixed_point_algorithm = '{spec['algorithm']}'" in poisson
        assert f"relaxation_factor = {expected_relax:.17g}" in fast
        assert "transformed_variables = 'potential_plasma'" in fast
        assert p["positive_ion_surface_model"] == "thermal_sticking"
        assert p["negative_ion_surface_model"] == "thermal_sticking"
        assert "[electron_sheath_factor]" in fast
        assert "PhysicsFVElectronGroundedSheath" not in fast

        parent_texts.append(parent)
        normalized_poisson.append(_normalized_poisson(poisson))
        normalized_fast.append(_normalized_fast(fast))

    # Ownership discriminator: generated parent inputs are identical; Poisson inputs differ only by algorithm, and
    # fast-child inputs become byte-identical after normalizing only the MultiApp damping/relaxation factor.
    assert len(set(parent_texts)) == 1
    assert len(set(normalized_poisson)) == 1
    assert len(set(normalized_fast)) == 1

    return {
        "status": "PASS",
        "issue": 310,
        "sequence": 7,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_fast_steps": 12,
        "final_tau": FINAL_TAU,
        "algorithms": {
            name: {
                "algorithm": algorithm,
                "relaxation_factor": relaxation,
            }
            for name, algorithm, relaxation in ALGORITHM_CASES
        },
        "fast_fixed_point_algorithm": "picard",
        "single_axis_poisson_algorithm_and_damping": True,
    }


def p0() -> None:
    print("ISSUE310_FP07_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{rel}/generated_fp07/{name}/input.i"
        for name in CASE_NAMES
    )
    base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    print("ISSUE310_FP07_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_fp07/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i input.i"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_fp07/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i fast_sub.i"
        )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_FP07_P2: PASS")


def inner_run(case_name: str) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED / case_name
    log = RESULTS / f"{case_name}_runtime.log"
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-i", "input.i"],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    (RESULTS / f"{case_name}_returncode.txt").write_text(
        f"{completed.returncode}\n", encoding="utf-8"
    )
    (RESULTS / f"{case_name}_elapsed_seconds.txt").write_text(
        f"{elapsed:.9f}\n", encoding="utf-8"
    )
    with log.open("r", encoding="utf-8", errors="replace") as handle:
        tail = deque(handle, maxlen=400)
    (RESULTS / f"{case_name}_runtime_tail.log").write_text(
        "".join(tail), encoding="utf-8"
    )
    log.unlink(missing_ok=True)
    return 0


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _maybe_float(row: dict[str, str], key: str) -> float | None:
    raw = row.get(key)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _time_series(case_name: str) -> dict[str, object]:
    case_dir = GENERATED / case_name
    parent_rows = _rows(case_dir / "input_step_csv.csv")
    fast_rows = _rows(case_dir / "input_out_electron0_step_csv.csv")

    potential: list[dict[str, float]] = []
    for row in parent_rows:
        t = _maybe_float(row, "time")
        phi = _maybe_float(row, "phi_avg")
        if t is None or phi is None:
            continue
        entry = {"time_s": t, "phi_avg_V": phi}
        phi_min = _maybe_float(row, "phi_min")
        phi_max = _maybe_float(row, "phi_max")
        if phi_min is not None:
            entry["phi_min_V"] = phi_min
        if phi_max is not None:
            entry["phi_max_V"] = phi_max
        potential.append(entry)

    fp: list[dict[str, float]] = []
    for row in fast_rows:
        t = _maybe_float(row, "time")
        its = _maybe_float(row, "fixed_point_iterations")
        cumulative = _maybe_float(row, "cumulative_fixed_point_iterations")
        if t is None or its is None:
            continue
        entry = {"time_s": t, "fixed_point_iterations": its}
        if cumulative is not None:
            entry["cumulative_fixed_point_iterations"] = cumulative
        fp.append(entry)

    positive_step_rows = [x for x in fp if x["time_s"] > 0.0]
    cumulative = None
    for entry in reversed(fp):
        if "cumulative_fixed_point_iterations" in entry:
            cumulative = float(entry["cumulative_fixed_point_iterations"])
            break
    if cumulative is None and positive_step_rows:
        cumulative = sum(float(x["fixed_point_iterations"]) for x in positive_step_rows)

    return {
        "potential_time_series": potential,
        "fixed_point_time_series": fp,
        "fast_steps_observed": len(positive_step_rows),
        "cumulative_fixed_point_iterations": cumulative,
        "average_fixed_point_iterations_per_observed_step": (
            cumulative / len(positive_step_rows)
            if cumulative is not None and positive_step_rows
            else None
        ),
        "max_fixed_point_iterations_per_observed_step": (
            max(float(x["fixed_point_iterations"]) for x in positive_step_rows)
            if positive_step_rows
            else None
        ),
    }


def analyze(case_name: str) -> tuple[dict[str, object], int]:
    spec = next(spec for spec in SPECS if spec["name"] == case_name)
    old_generated = base.GENERATED
    old_results = base.RESULTS
    old_cycles = base.HEAVY_CYCLES
    old_final_tau = base.FINAL_TAU
    try:
        base.GENERATED = GENERATED
        base.RESULTS = RESULTS
        base.HEAVY_CYCLES = HEAVY_CYCLES
        base.FINAL_TAU = FINAL_TAU
        result, code = base.analyze_case(case_name)
    finally:
        base.GENERATED = old_generated
        base.RESULTS = old_results
        base.HEAVY_CYCLES = old_cycles
        base.FINAL_TAU = old_final_tau

    result.update(
        issue=310,
        sequence=7,
        fast_fixed_point_algorithm="picard",
        poisson_fixed_point_algorithm=str(spec["algorithm"]),
        fixed_point_algorithm=str(spec["algorithm"]),
        relaxation_factor=float(spec["relaxation_factor"]),
        **_time_series(case_name),
    )
    return result, code


def run_case(case_name: str) -> None:
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq07.py --inner-run {case_name}"
    )
    result, code = analyze(case_name)
    (RESULTS / f"{case_name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_FP07_CASE:", case_name, result["classification"])
    if code:
        raise SystemExit(code)


def _comparison(reference: dict[str, object], trial: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {
        "elapsed_seconds": float(trial["elapsed_seconds"]),
        "elapsed_speedup_vs_baseline": (
            float(reference["elapsed_seconds"]) / float(trial["elapsed_seconds"])
            if float(trial["elapsed_seconds"]) > 0.0
            else None
        ),
        "cumulative_fixed_point_iterations": trial.get("cumulative_fixed_point_iterations"),
        "average_fixed_point_iterations_per_observed_step": trial.get(
            "average_fixed_point_iterations_per_observed_step"
        ),
    }
    ref_fp = reference.get("cumulative_fixed_point_iterations")
    trial_fp = trial.get("cumulative_fixed_point_iterations")
    if isinstance(ref_fp, (int, float)) and isinstance(trial_fp, (int, float)) and ref_fp:
        out["fixed_point_reduction_fraction_vs_baseline"] = 1.0 - float(trial_fp) / float(ref_fp)

    if bool(reference.get("evidence_valid")) and bool(trial.get("evidence_valid")):
        out["final_profile_parity"] = wall08._comparison(reference, trial)
    return out


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item

    missing = [name for name in CASE_NAMES if name not in found]
    runtime_converged = [
        name for name in CASE_NAMES
        if name in found and bool(found[name].get("evidence_valid"))
    ]
    runtime_failed = [
        name for name in CASE_NAMES
        if name in found and not bool(found[name].get("evidence_valid"))
    ]

    reference = found.get("picard_2x")
    comparisons: dict[str, object] = {}
    if reference is not None and bool(reference.get("evidence_valid")):
        for name in CASE_NAMES:
            if name == "picard_2x" or name not in found:
                continue
            comparisons[f"{name}_vs_picard_2x"] = _comparison(reference, found[name])

    ranking: list[dict[str, object]] = []
    for name in runtime_converged:
        item = found[name]
        ranking.append({
            "case": name,
            "poisson_algorithm": item.get("poisson_fixed_point_algorithm"),
            "damping": item.get("relaxation_factor"),
            "elapsed_seconds": item.get("elapsed_seconds"),
            "cumulative_fixed_point_iterations": item.get("cumulative_fixed_point_iterations"),
            "average_fixed_point_iterations_per_observed_step": item.get(
                "average_fixed_point_iterations_per_observed_step"
            ),
        })
    ranking.sort(
        key=lambda x: (
            float(x["average_fixed_point_iterations_per_observed_step"])
            if isinstance(x.get("average_fixed_point_iterations_per_observed_step"), (int, float))
            else float("inf"),
            float(x["elapsed_seconds"])
            if isinstance(x.get("elapsed_seconds"), (int, float))
            else float("inf"),
        )
    )

    complete = not missing
    return {
        "issue": 310,
        "sequence": 7,
        "classification": (
            "SECANT_REFINEMENT_MATRIX_COMPLETE" if complete else "SECANT_REFINEMENT_MATRIX_PARTIAL"
        ),
        "matrix_evidence_complete": complete,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_fast_steps": 12,
        "final_tau": FINAL_TAU,
        "runtime_converged_cases": runtime_converged,
        "runtime_failed_cases": runtime_failed,
        "missing_cases": missing,
        "cases": found,
        "comparisons_vs_picard_2x": comparisons,
        "runtime_ranking_by_fp_work": ranking,
        "target": {
            "desired_fp_per_step": "O(10)",
            "continue_threshold_fp_per_step": 50,
        },
        "interpretation_guard": (
            "Runtime convergence is not scientific qualification. Secant candidates must also "
            "preserve Picard-2x trajectory/profile, charge and potential. Fast Executioner is "
            "fixed to Picard in every case; only the Poisson subapp algorithm and its MultiApp "
            "damping differ."
        ),
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2"))
    parser.add_argument("--case", choices=CASE_NAMES)
    parser.add_argument("--inner-run", choices=CASE_NAMES)
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    if args.inner_run:
        return inner_run(args.inner_run)
    if args.case:
        run_case(args.case)
        return 0
    if args.aggregate:
        root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
        if not root:
            raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
        summary = aggregate(Path(root))
        (RESULTS / "issue310_fp07_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE310_FP07_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
