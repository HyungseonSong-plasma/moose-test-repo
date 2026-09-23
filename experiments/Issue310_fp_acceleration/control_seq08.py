"""Issue #310 Sequence 08: Poisson MultiApp architecture parity.

This is an architecture-only discriminator. Secant and Steffensen are not used.

Reference:
  FullSolveMultiApp + Steady Poisson + Picard relaxation 2/(1+chi_e)
  keep_solution_during_restore = true
  fast Executioner auto_advance = true

Trial:
  TransientMultiApp + Transient Poisson + Picard relaxation 2/(1+chi_e)
  no_restore = true
  fast fixed-point auto_advance uses the transient default (false)

The Poisson PDE is unchanged in the trial: no TimeDerivative is added. The
Transient Executioner exists only to give the Poisson subapp the same physical
timestep identity as the fast parent.

Common clock:
  chi_e = 100
  chi_h = 400
  heavy/electron dt ratio = 4
  T_final = 1200 tau_epsilon(initial)
  electron steps = 12
  heavy steps = 3

Physics, discretization, nonlinear/fixed-point tolerances, transfers, wall
closures and Picard relaxation are frozen. Runtime convergence and physical
parity are reported separately.
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

GENERATED = ROOT / "generated_fp08"
RESULTS = ROOT / "results_fp08"

CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 1200.0
HEAVY_CYCLES = 3
RATIO = 4
FP_MAX = 3000

ARCHITECTURE_CASES = (
    ("fullsolve_steady_picard2x", "fullsolve_steady"),
    ("transient_timeaware_picard2x", "transient_timeaware"),
)

SPECS = tuple(
    {
        "name": name,
        "architecture": architecture,
        "algorithm": "picard",
        "mode": "thermal",
        "chi": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "ratio": RATIO,
        "fp_max": FP_MAX,
        "relaxation_factor": 2.0 / (1.0 + CHI_E),
    }
    for name, architecture in ARCHITECTURE_CASES
)
CASE_NAMES = tuple(str(spec["name"]) for spec in SPECS)

# wall08._clock uses this module-level value while setting the inherited base clock.
wall08.FINAL_TAU = FINAL_TAU


def _params(spec: dict[str, object]) -> dict[str, object]:
    with wall08._clock(spec):
        p = wall08.wall03._params(spec)
    p["heavy_to_electron_dt_ratio"] = RATIO
    p["architecture"] = str(spec["architecture"])
    p["fixed_point_algorithm"] = "picard"
    p["relaxation_factor"] = float(spec["relaxation_factor"])
    return p


def _render_case(spec: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    with wall08._clock(spec):
        parent = wall08.wall03._parent(p)
        fast = wall08._apply_electron_sheath_factor(wall08.wall03._fast(p))
        poisson = base._poisson_child()

    # The fast plasma fixed-point algorithm is Picard in both architectures.
    fast_anchor = "  fixed_point_min_its = 2\n"
    if fast.count(fast_anchor) != 1:
        raise RuntimeError("fast-child fixed-point executioner anchor changed")
    fast = fast.replace(
        fast_anchor,
        "  fixed_point_algorithm = 'picard'\n" + fast_anchor,
        1,
    )

    architecture = str(spec["architecture"])
    poisson_anchor = "[Executioner]\n  type = Steady\n"
    if poisson.count(poisson_anchor) != 1:
        raise RuntimeError("Poisson executioner anchor changed")

    if architecture == "fullsolve_steady":
        poisson = poisson.replace(
            poisson_anchor,
            poisson_anchor + "  fixed_point_algorithm = 'picard'\n",
            1,
        )
        return parent, fast, poisson

    if architecture != "transient_timeaware":
        raise RuntimeError(f"unknown architecture: {architecture}")

    old_multiapp = """[MultiApps]
  [poisson]
    type = FullSolveMultiApp
    input_files = poisson_sub.i
    execute_on = TIMESTEP_END
    relaxation_factor = {relax:.17g}
    transformed_variables = 'potential_plasma'
    keep_solution_during_restore = true
    update_old_solution_when_keeping_solution_during_restore = false
  []
[]""".format(relax=float(p["relaxation_factor"]))

    new_multiapp = """[MultiApps]
  [poisson]
    type = TransientMultiApp
    input_files = poisson_sub.i
    execute_on = TIMESTEP_END
    relaxation_factor = {relax:.17g}
    transformed_variables = 'potential_plasma'
    no_restore = true
  []
[]""".format(relax=float(p["relaxation_factor"]))

    if fast.count(old_multiapp) != 1:
        raise RuntimeError("fast-child Poisson MultiApp anchor changed")
    fast = fast.replace(old_multiapp, new_multiapp, 1)

    # The default for a transient fixed-point solve is auto_advance=false. This
    # is required so repeated coupling iterations remain on one child timestep.
    auto_anchor = "  auto_advance = true\n"
    if fast.count(auto_anchor) != 1:
        raise RuntimeError("fast-child auto_advance anchor changed")
    fast = fast.replace(auto_anchor, "", 1)

    transient_exec = f"""[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {float(p["dt_e_s"]):.17g}
  dtmin = {float(p["dt_e_s"]):.17g}
  dtmax = {float(p["dt_e_s"]):.17g}
  end_time = {float(p["end_time_s"]):.17g}
  num_steps = {int(p["fast_steps_total"])}
  timestep_tolerance = {max(float(p["dt_e_s"]) * 1.0e-8, 1.0e-30):.17g}
  fixed_point_algorithm = 'picard'
  nl_rel_tol = 1.0e-10
  nl_abs_tol = 1.0e-12
  nl_max_its = 20
  automatic_scaling = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]
"""
    exec_start = poisson.index("[Executioner]\n")
    outputs_start = poisson.index("[Outputs]\n", exec_start)
    poisson = poisson[:exec_start] + transient_exec + "\n" + poisson[outputs_start:]

    if "TimeDerivative" in poisson:
        raise RuntimeError("architecture trial must not add a Poisson time derivative")
    return parent, fast, poisson


def _normalize_fast_architecture(text: str) -> str:
    text = re.sub(
        r"\[MultiApps\][\s\S]*?\n\[Transfers\]",
        "[MultiApps]\n<ARCHITECTURE>\n[Transfers]",
        text,
        count=1,
    )
    text = re.sub(r"^\s*auto_advance\s*=.*\n", "", text, count=1, flags=re.MULTILINE)
    return text


def _normalize_poisson_architecture(text: str) -> str:
    return re.sub(
        r"\[Executioner\][\s\S]*?\n\[Outputs\]",
        "[Executioner]\n<ARCHITECTURE>\n[Outputs]",
        text,
        count=1,
    )

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
                "sequence": 8,
                "objective": "test physical parity between FullSolve/Steady and time-aware TransientMultiApp/Transient Poisson under identical Picard physics",
                "source_physics": "Issue306 Sequence08 thermal-heavy-wall + sheath-suppressed-electron model",
                "chi_e": CHI_E,
                "chi_h": CHI_H,
                "heavy_to_electron_dt_ratio": RATIO,
                "heavy_cycles": HEAVY_CYCLES,
                "total_fast_steps": int(FINAL_TAU / CHI_E),
                "final_tau": FINAL_TAU,
                "architecture_cases": [
                    {"name": name, "architecture": architecture}
                    for name, architecture in ARCHITECTURE_CASES
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
    if len(CASE_NAMES) != 2:
        raise RuntimeError("Sequence08 architecture parity must contain exactly two cases")

    by = {str(p["name"]): p for p in built}
    ref_name = "fullsolve_steady_picard2x"
    trial_name = "transient_timeaware_picard2x"

    ref_dir = GENERATED / ref_name
    trial_dir = GENERATED / trial_name
    ref_parent = (ref_dir / "input.i").read_text(encoding="utf-8")
    trial_parent = (trial_dir / "input.i").read_text(encoding="utf-8")
    ref_fast = (ref_dir / "fast_sub.i").read_text(encoding="utf-8")
    trial_fast = (trial_dir / "fast_sub.i").read_text(encoding="utf-8")
    ref_poisson = (ref_dir / "poisson_sub.i").read_text(encoding="utf-8")
    trial_poisson = (trial_dir / "poisson_sub.i").read_text(encoding="utf-8")

    expected_relax = 2.0 / (1.0 + CHI_E)
    for p in built:
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
        assert p["positive_ion_surface_model"] == "thermal_sticking"
        assert p["negative_ion_surface_model"] == "thermal_sticking"

    # Parent heavy-plasma model is byte-identical.
    assert ref_parent == trial_parent

    # Fast plasma physics/transfers are byte-identical after removing only the
    # Poisson MultiApp architecture and auto-advance policy.
    assert _normalize_fast_architecture(ref_fast) == _normalize_fast_architecture(trial_fast)
    assert "fixed_point_algorithm = 'picard'" in ref_fast
    assert "fixed_point_algorithm = 'picard'" in trial_fast
    assert f"relaxation_factor = {expected_relax:.17g}" in ref_fast
    assert f"relaxation_factor = {expected_relax:.17g}" in trial_fast
    assert "transformed_variables = 'potential_plasma'" in ref_fast
    assert "transformed_variables = 'potential_plasma'" in trial_fast

    assert "type = FullSolveMultiApp" in ref_fast
    assert "keep_solution_during_restore = true" in ref_fast
    assert "update_old_solution_when_keeping_solution_during_restore = false" in ref_fast
    assert "auto_advance = true" in ref_fast

    assert "type = TransientMultiApp" in trial_fast
    assert "no_restore = true" in trial_fast
    assert "keep_solution_during_restore" not in trial_fast
    assert "auto_advance = true" not in trial_fast

    # Poisson equation/BC/material model is byte-identical after normalizing
    # only the Executioner architecture. No transient term is introduced.
    assert _normalize_poisson_architecture(ref_poisson) == _normalize_poisson_architecture(trial_poisson)
    assert "type = Steady" in ref_poisson
    assert "type = Transient" in trial_poisson
    assert "fixed_point_algorithm = 'picard'" in ref_poisson
    assert "fixed_point_algorithm = 'picard'" in trial_poisson
    assert "TimeDerivative" not in ref_poisson
    assert "TimeDerivative" not in trial_poisson

    return {
        "status": "PASS",
        "issue": 310,
        "sequence": 8,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_fast_steps": 12,
        "final_tau": FINAL_TAU,
        "relaxation_factor": expected_relax,
        "reference": by[ref_name],
        "trial": by[trial_name],
        "physics_equation_parity": True,
        "only_architecture_changes": [
            "FullSolveMultiApp -> TransientMultiApp",
            "Steady Poisson Executioner -> Transient Poisson Executioner",
            "keep_solution restore -> no_restore",
            "fast auto_advance true -> transient fixed-point default false",
        ],
    }

def p0() -> None:
    print("ISSUE310_FP08_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{rel}/generated_fp08/{name}/input.i"
        for name in CASE_NAMES
    )
    base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    print("ISSUE310_FP08_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_fp08/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i input.i"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_fp08/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i fast_sub.i"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_fp08/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i poisson_sub.i"
        )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_FP08_P2: PASS")


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
        sequence=8,
        architecture=str(spec["architecture"]),
        fast_fixed_point_algorithm="picard",
        poisson_fixed_point_algorithm="picard",
        fixed_point_algorithm="picard",
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
        f"python3 /workspace/{rel}/control_seq08.py --inner-run {case_name}"
    )
    result, code = analyze(case_name)
    (RESULTS / f"{case_name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_FP08_CASE:", case_name, result["classification"])
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


def _potential_series_parity(reference: dict[str, object], trial: dict[str, object]) -> dict[str, object]:
    a = list(reference.get("potential_time_series", []))
    b = list(trial.get("potential_time_series", []))
    out: dict[str, object] = {
        "reference_points": len(a),
        "trial_points": len(b),
        "same_point_count": len(a) == len(b),
    }
    if len(a) != len(b) or not a:
        return out

    keys = ("phi_avg_V", "phi_min_V", "phi_max_V")
    for key in keys:
        diffs = []
        for ra, rb in zip(a, b, strict=True):
            if key in ra and key in rb:
                diffs.append(abs(float(rb[key]) - float(ra[key])))
        if diffs:
            out[f"{key}_max_abs_delta"] = max(diffs)
    out["time_max_abs_delta_s"] = max(
        abs(float(rb["time_s"]) - float(ra["time_s"]))
        for ra, rb in zip(a, b, strict=True)
    )
    return out


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item

    missing = [name for name in CASE_NAMES if name not in found]
    ref = found.get("fullsolve_steady_picard2x")
    trial = found.get("transient_timeaware_picard2x")

    comparison: dict[str, object] = {}
    if ref is not None and trial is not None:
        comparison = _comparison(ref, trial)
        if bool(ref.get("evidence_valid")) and bool(trial.get("evidence_valid")):
            comparison["potential_time_series_parity"] = _potential_series_parity(ref, trial)

    complete = not missing
    runtime_valid = (
        complete
        and ref is not None
        and trial is not None
        and bool(ref.get("evidence_valid"))
        and bool(trial.get("evidence_valid"))
    )

    return {
        "issue": 310,
        "sequence": 8,
        "classification": (
            "ARCHITECTURE_PARITY_EVIDENCE_COMPLETE"
            if complete
            else "ARCHITECTURE_PARITY_EVIDENCE_PARTIAL"
        ),
        "matrix_evidence_complete": complete,
        "runtime_evidence_valid": runtime_valid,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_fast_steps": 12,
        "final_tau": FINAL_TAU,
        "missing_cases": missing,
        "cases": found,
        "transient_timeaware_vs_fullsolve_steady": comparison,
        "interpretation_guard": (
            "This experiment qualifies architecture parity only. Both cases use Picard 2/(1+chi_e); "
            "no Secant or Steffensen acceleration is present. Runtime completion is not sufficient "
            "for architecture parity: the final profile and potential trajectory must agree."
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
        (RESULTS / "issue310_fp08_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE310_FP08_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
