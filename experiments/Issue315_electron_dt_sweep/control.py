#!/usr/bin/env python3
"""Issue #315 Sequence 01: electron timestep cost/parity sweep.

Source physics is the accepted Issue #306 wall09 model.

Fixed:
  chi_h = 400
  heavy cycles = 200
  T_final = 80000 tau_epsilon(initial)
  relaxation_factor = 1/(1+100) = 1/101
  physics, wall ownership, mesh, nonlinear/fixed-point tolerances

Single discriminator:
  chi_e = 100 / 200 / 400

Therefore:
  dt_h/dt_e = 4 / 2 / 1
  electron steps = 800 / 400 / 200
  heavy steps = 200 for every case
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import deque
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue306_heavy_charge_motion import wall09_control as wall09

base = wall09.base

GENERATED = ROOT / "generated_dt01"
RESULTS = ROOT / "results_dt01"

CHI_H = 400.0
FINAL_TAU = 80000.0
HEAVY_CYCLES = 200
FP_MAX = 3000
RELAXATION_FACTOR = 1.0 / 101.0
ELECTRON_CHIS = (100.0, 200.0, 400.0)

SPECS = tuple(
    {
        "name": f"dt_e_{int(chi_e)}",
        "mode": "comsol",
        "chi": chi_e,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "ratio": int(CHI_H / chi_e),
        "fp_max": FP_MAX,
    }
    for chi_e in ELECTRON_CHIS
)
CASE_NAMES = tuple(str(spec["name"]) for spec in SPECS)

# wall09._clock reads its own module-level FINAL_TAU.
wall09.FINAL_TAU = FINAL_TAU


def _params(spec: dict[str, object]) -> dict[str, object]:
    with wall09._clock(spec):
        p = wall09.wall03._params(spec)
    p["heavy_to_electron_dt_ratio"] = int(spec["ratio"])
    # Hold relaxation fixed at the chi_e=100 baseline so dt is the discriminator.
    p["relaxation_factor"] = RELAXATION_FACTOR
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
                "issue": 315,
                "sequence": 1,
                "objective": (
                    "reduce electron-step count by increasing electron dt while "
                    "holding heavy dt, physical horizon, relaxation, and plasma physics fixed"
                ),
                "source_physics": "Issue306 wall09 Bohm-positive-ion + sheath-suppressed-electron model",
                "chi_h": CHI_H,
                "heavy_cycles": HEAVY_CYCLES,
                "final_tau": FINAL_TAU,
                "relaxation_factor": RELAXATION_FACTOR,
                "electron_chi_cases": [
                    {
                        "name": str(spec["name"]),
                        "chi_e": float(spec["chi"]),
                        "ratio": int(spec["ratio"]),
                        "electron_steps": int(FINAL_TAU / float(spec["chi"])),
                    }
                    for spec in SPECS
                ],
                "cases": built,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    built = build()
    if tuple(str(p["name"]) for p in built) != CASE_NAMES:
        raise RuntimeError("case ordering mismatch")

    poisson_texts: list[str] = []
    for spec, p in zip(SPECS, built, strict=True):
        chi_e = float(spec["chi"])
        ratio = int(spec["ratio"])
        expected_steps = int(FINAL_TAU / chi_e)
        case_dir = GENERATED / str(p["name"])
        parent = (case_dir / "input.i").read_text(encoding="utf-8")
        fast = (case_dir / "fast_sub.i").read_text(encoding="utf-8")
        poisson = (case_dir / "poisson_sub.i").read_text(encoding="utf-8")

        assert math.isclose(float(p["chi_e"]), chi_e, rel_tol=0.0, abs_tol=0.0)
        assert math.isclose(float(p["chi_h"]), CHI_H, rel_tol=0.0, abs_tol=0.0)
        assert int(p["heavy_cycles"]) == HEAVY_CYCLES
        assert int(p["fast_steps_per_heavy_cycle"]) == ratio
        assert int(p["fast_steps_total"]) == expected_steps
        assert math.isclose(
            float(p["end_time_tau_epsilon_initial"]),
            FINAL_TAU,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        assert math.isclose(
            float(p["relaxation_factor"]),
            RELAXATION_FACTOR,
            rel_tol=1e-15,
            abs_tol=0.0,
        )
        assert f"num_steps = {HEAVY_CYCLES}" in parent
        assert "fixed_point_max_its = 3000" in fast
        assert f"relaxation_factor = {RELAXATION_FACTOR:.17g}" in fast
        assert p["positive_ion_surface_model"] == "bohm"
        assert p["negative_ion_surface_model"] == "thermal_sticking"
        assert "[electron_sheath_factor]" in fast
        assert "PhysicsFVElectronGroundedSheath" not in fast
        poisson_texts.append(poisson)

    # Poisson physics must be byte-identical; dt changes only time integration/cadence.
    assert len(set(poisson_texts)) == 1

    return {
        "status": "PASS",
        "issue": 315,
        "sequence": 1,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "final_tau": FINAL_TAU,
        "relaxation_factor": RELAXATION_FACTOR,
        "cases": {
            str(spec["name"]): {
                "chi_e": float(spec["chi"]),
                "ratio": int(spec["ratio"]),
                "electron_steps": int(FINAL_TAU / float(spec["chi"])),
            }
            for spec in SPECS
        },
        "single_axis_electron_dt": True,
    }


def p0() -> None:
    print("ISSUE315_DT_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{rel}/generated_dt01/{name}/input.i"
        for name in CASE_NAMES
    )
    base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    print("ISSUE315_DT_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_dt01/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i input.i"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_dt01/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i fast_sub.i"
        )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE315_DT_P2: PASS")


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

    physical: list[dict[str, float]] = []
    for row in parent_rows:
        t = _maybe_float(row, "time")
        if t is None:
            continue
        entry: dict[str, float] = {"time_s": t}
        for source, target in (
            ("phi_avg", "phi_avg_V"),
            ("phi_min", "phi_min_V"),
            ("phi_max", "phi_max_V"),
            ("mean_energy_avg", "mean_energy_avg_eV"),
        ):
            value = _maybe_float(row, source)
            if value is not None:
                entry[target] = value
        physical.append(entry)

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

    positive = [x for x in fp if x["time_s"] > 0.0]
    cumulative = None
    for entry in reversed(fp):
        if "cumulative_fixed_point_iterations" in entry:
            cumulative = float(entry["cumulative_fixed_point_iterations"])
            break
    if cumulative is None and positive:
        cumulative = sum(float(x["fixed_point_iterations"]) for x in positive)

    return {
        "physical_time_series": physical,
        "fixed_point_time_series": fp,
        "fast_steps_observed": len(positive),
        "cumulative_fixed_point_iterations": cumulative,
        "average_fixed_point_iterations_per_observed_step": (
            cumulative / len(positive) if cumulative is not None and positive else None
        ),
        "max_fixed_point_iterations_per_observed_step": (
            max(float(x["fixed_point_iterations"]) for x in positive) if positive else None
        ),
    }


def _spec_for_name(case_name: str) -> dict[str, object]:
    return next(spec for spec in SPECS if spec["name"] == case_name)


def analyze(case_name: str) -> tuple[dict[str, object], int]:
    spec = _spec_for_name(case_name)
    old_generated, old_results = base.GENERATED, base.RESULTS
    try:
        base.GENERATED = GENERATED
        base.RESULTS = RESULTS
        with wall09._clock(spec):
            result, code = base.analyze_case(case_name)
    finally:
        base.GENERATED = old_generated
        base.RESULTS = old_results

    p = json.loads((GENERATED / case_name / "case.json").read_text(encoding="utf-8"))
    result.update(
        issue=315,
        sequence=1,
        electron_chi=float(p["chi_e"]),
        heavy_chi=float(p["chi_h"]),
        heavy_to_electron_dt_ratio=int(p["heavy_to_electron_dt_ratio"]),
        relaxation_factor=float(p["relaxation_factor"]),
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
    print("ISSUE315_DT_CASE:", case_name, result["classification"])
    if code:
        raise SystemExit(code)


def _comparison(reference: dict[str, object], trial: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {
        "elapsed_seconds": float(trial["elapsed_seconds"]),
        "elapsed_speedup_vs_reference": (
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
        out["fixed_point_reduction_fraction_vs_reference"] = (
            1.0 - float(trial_fp) / float(ref_fp)
        )
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
    ref = found.get("dt_e_100")
    comparisons: dict[str, object] = {}
    if ref is not None:
        for name in ("dt_e_200", "dt_e_400"):
            if name in found:
                comparisons[f"{name}_vs_dt_e_100"] = _comparison(ref, found[name])
    if "dt_e_200" in found and "dt_e_400" in found:
        comparisons["dt_e_400_vs_dt_e_200"] = _comparison(
            found["dt_e_200"], found["dt_e_400"]
        )

    complete = not missing and all(bool(found[name].get("evidence_valid")) for name in CASE_NAMES)
    return {
        "issue": 315,
        "sequence": 1,
        "classification": "ELECTRON_DT_SWEEP_COMPLETE" if complete else "ELECTRON_DT_SWEEP_PARTIAL",
        "evidence_valid": complete,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "final_tau": FINAL_TAU,
        "relaxation_factor": RELAXATION_FACTOR,
        "electron_chi": list(ELECTRON_CHIS),
        "electron_steps": {
            f"dt_e_{int(chi)}": int(FINAL_TAU / chi) for chi in ELECTRON_CHIS
        },
        "missing_cases": missing,
        "cases": found,
        "comparisons": comparisons,
        "interpretation_guard": (
            "The heavy timestep, physical horizon, relaxation factor, physics, wall ownership, "
            "and solver tolerances are frozen. Only the electron timestep and consequent fast-step "
            "count/cadence change. Runtime improvement is not proof of numerical parity."
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
        (RESULTS / "issue315_dt01_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE315_DT_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
