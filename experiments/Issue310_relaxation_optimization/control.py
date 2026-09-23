"""Issue #310 Sequence 01: fixed-point relaxation-factor optimization.

Physics and time integration are frozen to the accepted Issue #306 wall09 model.
Only the fixed-point relaxation factor changes.

Fixed timing:
  chi_e = 100
  chi_h = 400
  heavy/electron dt ratio = 4
  T_final = 80000 tau_epsilon(initial)
  electron steps = 800
  heavy steps = 200

Relaxation sweep:
  1/(1+chi_e)
  2/(1+chi_e)
  5/(1+chi_e)

For chi_e=100 these are approximately 0.00990099, 0.0198020, 0.0495050.
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

from experiments.Issue306_heavy_charge_motion import wall09_control as wall09

base = wall09.base

GENERATED = ROOT / "generated_relaxation01"
RESULTS = ROOT / "results_relaxation01"

CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 80000.0
HEAVY_CYCLES = 200
RATIO = 4
FP_MAX = 3000

RELAXATION_CASES = (
    ("relax_1x", 1.0),
    ("relax_2x", 2.0),
    ("relax_5x", 5.0),
)

SPECS = tuple(
    {
        "name": name,
        "mode": "comsol",
        "chi": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "ratio": RATIO,
        "fp_max": FP_MAX,
        "relaxation_multiplier": multiplier,
        "relaxation_factor": multiplier / (1.0 + CHI_E),
    }
    for name, multiplier in RELAXATION_CASES
)
CASE_NAMES = tuple(str(spec["name"]) for spec in SPECS)

# wall09._clock uses this module-level value while setting the inherited base clock.
wall09.FINAL_TAU = FINAL_TAU


def _params(spec: dict[str, object]) -> dict[str, object]:
    with wall09._clock(spec):
        p = wall09.wall03._params(spec)
    p["heavy_to_electron_dt_ratio"] = RATIO
    p["relaxation_multiplier"] = float(spec["relaxation_multiplier"])
    p["relaxation_factor"] = float(spec["relaxation_factor"])
    return p


def _render_case(spec: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    with wall09._clock(spec):
        parent = wall09.wall03._parent(p)
        fast = wall09._apply_electron_sheath_factor(wall09.wall03._fast(p))
        poisson = base._poisson_child()
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
                "sequence": 1,
                "objective": "reduce fixed-point work without changing the converged plasma solution",
                "source_physics": "Issue306 wall09 Bohm-positive-ion + sheath-suppressed-electron model",
                "chi_e": CHI_E,
                "chi_h": CHI_H,
                "heavy_to_electron_dt_ratio": RATIO,
                "heavy_cycles": HEAVY_CYCLES,
                "total_fast_steps": int(FINAL_TAU / CHI_E),
                "final_tau": FINAL_TAU,
                "relaxation_cases": [
                    {
                        "name": name,
                        "multiplier": multiplier,
                        "factor": multiplier / (1.0 + CHI_E),
                    }
                    for name, multiplier in RELAXATION_CASES
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
    return re.sub(
        r"(^\s*relaxation_factor\s*=\s*).+$",
        r"\1<RELAXATION_FACTOR>",
        text,
        count=1,
        flags=re.MULTILINE,
    )


def static_contract() -> dict[str, object]:
    built = build()
    if tuple(str(p["name"]) for p in built) != CASE_NAMES:
        raise RuntimeError("case ordering mismatch")

    parent_texts: list[str] = []
    poisson_texts: list[str] = []
    normalized_fast: list[str] = []

    for spec, p in zip(SPECS, built, strict=True):
        case_dir = GENERATED / str(p["name"])
        parent = (case_dir / "input.i").read_text(encoding="utf-8")
        fast = (case_dir / "fast_sub.i").read_text(encoding="utf-8")
        poisson = (case_dir / "poisson_sub.i").read_text(encoding="utf-8")

        expected_relax = float(spec["relaxation_multiplier"]) / (1.0 + CHI_E)
        assert math.isclose(float(p["chi_e"]), CHI_E, rel_tol=0.0, abs_tol=0.0)
        assert math.isclose(float(p["chi_h"]), CHI_H, rel_tol=0.0, abs_tol=0.0)
        assert int(p["heavy_cycles"]) == HEAVY_CYCLES
        assert int(p["fast_steps_per_heavy_cycle"]) == RATIO
        assert int(p["fast_steps_total"]) == 800
        assert math.isclose(
            float(p["end_time_tau_epsilon_initial"]), FINAL_TAU, rel_tol=0.0, abs_tol=1e-12
        )
        assert math.isclose(
            float(p["relaxation_factor"]), expected_relax, rel_tol=1e-15, abs_tol=0.0
        )
        assert 0.0 < expected_relax < 1.0
        assert f"num_steps = {HEAVY_CYCLES}" in parent
        assert "fixed_point_max_its = 3000" in fast
        assert f"relaxation_factor = {expected_relax:.17g}" in fast
        assert p["positive_ion_surface_model"] == "bohm"
        assert p["negative_ion_surface_model"] == "thermal_sticking"
        assert "[electron_sheath_factor]" in fast
        assert "PhysicsFVElectronGroundedSheath" not in fast

        parent_texts.append(parent)
        poisson_texts.append(poisson)
        normalized_fast.append(_normalized_fast(fast))

    # Single-axis discriminator: generated parent/Poisson are byte-identical,
    # and fast-child inputs become byte-identical after replacing only relaxation_factor.
    assert len(set(parent_texts)) == 1
    assert len(set(poisson_texts)) == 1
    assert len(set(normalized_fast)) == 1

    return {
        "status": "PASS",
        "issue": 310,
        "sequence": 1,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_fast_steps": 800,
        "final_tau": FINAL_TAU,
        "relaxation_factors": {
            name: multiplier / (1.0 + CHI_E)
            for name, multiplier in RELAXATION_CASES
        },
        "single_axis_relaxation_only": True,
    }


def p0() -> None:
    print("ISSUE310_RELAXATION_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{rel}/generated_relaxation01/{name}/input.i"
        for name in CASE_NAMES
    )
    base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    print("ISSUE310_RELAXATION_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_relaxation01/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i input.i"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_relaxation01/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i fast_sub.i"
        )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_RELAXATION_P2: PASS")


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
        sequence=1,
        relaxation_multiplier=float(spec["relaxation_multiplier"]),
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
        f"python3 /workspace/{rel}/control.py --inner-run {case_name}"
    )
    result, code = analyze(case_name)
    (RESULTS / f"{case_name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_RELAXATION_CASE:", case_name, result["classification"])
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
        out["final_profile_parity"] = wall09._comparison(reference, trial)
    return out


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item

    missing = [name for name in CASE_NAMES if name not in found]
    baseline = found.get("relax_1x")
    comparisons: dict[str, object] = {}
    if baseline is not None:
        for name in ("relax_2x", "relax_5x"):
            if name in found:
                comparisons[f"{name}_vs_relax_1x"] = _comparison(baseline, found[name])

    complete = not missing and all(bool(found[name].get("evidence_valid")) for name in CASE_NAMES)
    return {
        "issue": 310,
        "sequence": 1,
        "classification": "RELAXATION_SWEEP_COMPLETE" if complete else "RELAXATION_SWEEP_PARTIAL",
        "evidence_valid": complete,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_fast_steps": 800,
        "final_tau": FINAL_TAU,
        "relaxation_factors": {
            name: multiplier / (1.0 + CHI_E)
            for name, multiplier in RELAXATION_CASES
        },
        "missing_cases": missing,
        "cases": found,
        "comparisons": comparisons,
        "interpretation_guard": (
            "Physics, dt_e, dt_h, physical horizon, wall ownership, solver tolerances, "
            "and fixed-point stopping criteria are frozen. Only relaxation_factor changes. "
            "Execution speed/convergence is not by itself proof of physical equivalence."
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
        (RESULTS / "issue310_relaxation01_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE310_RELAXATION_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
