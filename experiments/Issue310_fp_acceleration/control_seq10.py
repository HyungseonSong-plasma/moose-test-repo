"""Issue #310 Sequence 10: patched secondary Secant history-seed discriminator.

Sequence09 showed that time-aware native Secant completes electron step 1 but
fails on electron step 2 after a residual jump of about 0.013 -> 36.

This discriminator applies an experimental framework patch in CI only:
on a new secondary accelerated timestep, seed the entering solution into the
accelerated history before the first solve. Picard is unchanged.

Cases:
  picard_2x_seedpatch
  secant_seed_0p005
  secant_seed_0p010
  secant_seed_0p020

Clock: chi_e=100, chi_h=400, ratio4, one heavy cycle / four electron steps,
T_final=400 tau_epsilon(initial).

Primary discriminator: whether the step-2 Secant blow-up disappears.
Scientific parity versus the same patched-binary Picard reference is required.
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

GENERATED = ROOT / "generated_fp10"
RESULTS = ROOT / "results_fp10"
PATCH_FILE = ROOT / "patches" / "secondary_secant_history_seed.patch"
PATCHED_RUNTIME = ROOT / "patched_runtime_fp10"
STAGING_SPEC = ROOT / "artifact_staging_seq10.json"
MOOSE_SHA = "9f388366ccf38b9c34542ec5561198249fde0ac9"
OPERATION_SHA = "a81ffc7af265a5d6be357483dbd39ca147224e2c"

CHI_E = 100.0
CHI_H = 400.0
FINAL_TAU = 400.0
HEAVY_CYCLES = 1
RATIO = 4
FP_MAX = 3000

ALGORITHM_CASES = (
    ("picard_2x_seedpatch", "picard", 2.0 / (1.0 + CHI_E)),
    ("secant_seed_0p005", "secant", 0.005),
    ("secant_seed_0p010", "secant", 0.010),
    ("secant_seed_0p020", "secant", 0.020),
)

SPECS = tuple(
    {
        "name": name,
        "architecture": "transient_timeaware",
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
    p["architecture"] = "transient_timeaware"
    p["fixed_point_algorithm"] = str(spec["algorithm"])
    p["relaxation_factor"] = float(spec["relaxation_factor"])
    return p


def _render_case(spec: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    with wall08._clock(spec):
        parent = wall08.wall03._parent(p)
        fast = wall08._apply_electron_sheath_factor(wall08.wall03._fast(p))
        poisson = base._poisson_child()

    fast_anchor = "  fixed_point_min_its = 2\n"
    if fast.count(fast_anchor) != 1:
        raise RuntimeError("fast-child fixed-point executioner anchor changed")
    fast = fast.replace(
        fast_anchor,
        "  fixed_point_algorithm = 'picard'\n" + fast_anchor,
        1,
    )

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

    auto_anchor = "  auto_advance = true\n"
    if fast.count(auto_anchor) != 1:
        raise RuntimeError("fast-child auto_advance anchor changed")
    fast = fast.replace(auto_anchor, "", 1)

    poisson_anchor = "[Executioner]\n  type = Steady\n"
    if poisson.count(poisson_anchor) != 1:
        raise RuntimeError("Poisson executioner anchor changed")

    poisson_algorithm = str(spec["algorithm"])
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
  fixed_point_algorithm = '{poisson_algorithm}'
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
        raise RuntimeError("time-aware Poisson must not add a time derivative")
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
                "sequence": 10,
                "objective": "test per-timestep secondary Secant history seeding against the Sequence09 step-2 blow-up",
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
                        "poisson_fixed_point_algorithm": algorithm,
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
    if len(CASE_NAMES) != 4:
        raise RuntimeError("Sequence10 patch discriminator must contain exactly four cases")
    if not PATCH_FILE.is_file():
        raise RuntimeError(f"missing framework patch: {PATCH_FILE}")

    patch_text = PATCH_FILE.read_text(encoding="utf-8")
    staging = json.loads(STAGING_SPEC.read_text(encoding="utf-8"))
    assert staging["schema_version"] == 1
    assert len(staging["entries"]) == 1
    staging_entry = staging["entries"][0]
    assert staging_entry["source"] == "/opt/physics_vendor/moose/framework/libmoose-opt.so.0"
    assert "*" not in staging_entry["source"] and "?" not in staging_entry["source"]
    assert staging_entry["destination"] == (
        "experiments/Issue310_fp_acceleration/patched_runtime_fp10/libmoose-opt.so.0"
    )
    assert staging_entry["producer"]
    assert staging_entry["location_evidence"]
    assert "_main_fixed_point_it = 0;" in patch_text
    assert "saveVariableValues(/*is parent app of this iteration=*/false);" in patch_text
    assert "!dynamic_cast<PicardSolve *>(this)" in patch_text

    parent_texts: list[str] = []
    normalized_fast: list[str] = []
    normalized_poisson: list[str] = []

    for spec, p in zip(SPECS, built, strict=True):
        case_dir = GENERATED / str(p["name"])
        parent = (case_dir / "input.i").read_text(encoding="utf-8")
        fast = (case_dir / "fast_sub.i").read_text(encoding="utf-8")
        poisson = (case_dir / "poisson_sub.i").read_text(encoding="utf-8")
        expected_algorithm = str(spec["algorithm"])
        expected_relax = float(spec["relaxation_factor"])

        assert p["architecture"] == "transient_timeaware"
        assert math.isclose(float(p["chi_e"]), CHI_E, rel_tol=0.0, abs_tol=0.0)
        assert math.isclose(float(p["chi_h"]), CHI_H, rel_tol=0.0, abs_tol=0.0)
        assert int(p["heavy_cycles"]) == 1
        assert int(p["fast_steps_per_heavy_cycle"]) == 4
        assert int(p["fast_steps_total"]) == 4
        assert math.isclose(float(p["end_time_tau_epsilon_initial"]), 400.0, rel_tol=0.0, abs_tol=1e-12)
        assert math.isclose(float(p["relaxation_factor"]), expected_relax, rel_tol=1e-15, abs_tol=0.0)
        assert p["positive_ion_surface_model"] == "thermal_sticking"
        assert p["negative_ion_surface_model"] == "thermal_sticking"

        assert "fixed_point_algorithm = 'picard'" in fast
        assert "type = TransientMultiApp" in fast
        assert "no_restore = true" in fast
        assert "keep_solution_during_restore" not in fast
        assert "auto_advance = true" not in fast
        assert f"relaxation_factor = {expected_relax:.17g}" in fast
        assert "transformed_variables = 'potential_plasma'" in fast

        assert "type = Transient" in poisson
        assert f"fixed_point_algorithm = '{expected_algorithm}'" in poisson
        assert "TimeDerivative" not in poisson

        parent_texts.append(parent)
        normalized_fast.append(_normalized_fast(fast))
        normalized_poisson.append(_normalized_poisson(poisson))

    assert len(set(parent_texts)) == 1
    assert len(set(normalized_fast)) == 1
    assert len(set(normalized_poisson)) == 1

    return {
        "status": "PASS",
        "issue": 310,
        "sequence": 10,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": 1,
        "total_fast_steps": 4,
        "final_tau": 400.0,
        "architecture": "TransientMultiApp + Transient Poisson; no TimeDerivative; no_restore=true",
        "framework_patch": str(PATCH_FILE.relative_to(REPO)),
        "framework_base_sha": MOOSE_SHA,
        "operation_sha": OPERATION_SHA,
        "artifact_staging_spec": str(STAGING_SPEC.relative_to(REPO)),
        "patch_scope": "seed secondary accelerated history on new physical timestep; Picard no-op",
        "cases": built,
    }


def p0() -> None:
    print("ISSUE310_FP10_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{rel}/generated_fp10/{name}/input.i"
        for name in CASE_NAMES
    )
    base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    print("ISSUE310_FP10_P1: PASS")


def _docker_with_operation(script: str) -> None:
    operation_root_raw = os.environ.get("CHATGPT_OPERATION_ROOT")
    operation_sha = os.environ.get("CHATGPT_OPERATION_SHA")
    if not operation_root_raw or not operation_sha:
        raise RuntimeError("exact chatgpt-operation checkout is required for artifact staging")
    if operation_sha != OPERATION_SHA:
        raise RuntimeError(
            f"operation SHA mismatch: workflow={operation_sha} expected={OPERATION_SHA}"
        )
    operation_root = Path(operation_root_raw).resolve()
    if not operation_root.is_dir():
        raise RuntimeError(f"operation checkout missing: {operation_root}")
    actual_sha = subprocess.check_output(
        ["git", "-C", str(operation_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_sha != OPERATION_SHA:
        raise RuntimeError(
            f"operation checkout mismatch: actual={actual_sha} expected={OPERATION_SHA}"
        )
    base._run(["docker", "pull", base.BUILD_BASE_REF])
    base._run([
        "docker", "run", "--rm", "--entrypoint", "/bin/bash", "--user", "0:0",
        "--workdir", "/workspace",
        "-v", f"{REPO}:/workspace",
        "-v", f"{operation_root}:/chatgpt-operation:ro",
        base.BUILD_BASE_REF,
        "-lc", script,
    ])


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_fp10/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i input.i"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_fp10/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i fast_sub.i"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_fp10/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i poisson_sub.i"
        )

    patch_rel = PATCH_FILE.relative_to(REPO)
    staging_rel = STAGING_SPEC.relative_to(REPO)
    runtime_rel = PATCHED_RUNTIME.relative_to(REPO)
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        f"test \"$(git -C /opt/physics_vendor/moose rev-parse HEAD)\" = \"{MOOSE_SHA}\"; "
        "git -C /opt/physics_vendor/moose diff --quiet; "
        f"git -C /opt/physics_vendor/moose apply --check /workspace/{patch_rel}; "
        f"git -C /opt/physics_vendor/moose apply /workspace/{patch_rel}; "
        "git -C /opt/physics_vendor/moose diff --check; "
        "grep -q 'saveVariableValues(/\\*is parent app of this iteration=\\*/false);' "
        "/opt/physics_vendor/moose/framework/src/executioners/FixedPointSolve.C; "
        "make -C /workspace/physics_app -j2; "
        f"rm -rf /workspace/{runtime_rel}; mkdir -p /workspace/{runtime_rel}; "
        "PYTHONPATH=/chatgpt-operation/src python3 -m chatgpt_operation.artifact_staging stage "
        f"--spec /workspace/{staging_rel} --workspace /workspace "
        f"--evidence /workspace/{runtime_rel}/STAGING_EVIDENCE.json; "
        f"test -f /workspace/{runtime_rel}/libmoose-opt.so.0; "
        f"printf 'MOOSE_BASE_SHA={MOOSE_SHA}\\nPATCH={patch_rel}\\nOPERATION_SHA={OPERATION_SHA}\\n' "
        f"> /workspace/{runtime_rel}/PATCH_PROVENANCE.txt; "
        f"export LD_LIBRARY_PATH=/workspace/{runtime_rel}:\$LD_LIBRARY_PATH; "
        f"ldd /workspace/physics_app/physics-opt | grep '/workspace/{runtime_rel}/libmoose-opt.so.0' "
        f"> /workspace/{runtime_rel}/LDD_PROOF.txt; "
        + "; ".join(checks)
    )
    _docker_with_operation(script)
    print("ISSUE310_FP10_P2: PASS")


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
        sequence=10,
        architecture="transient_timeaware",
        framework_patch="secondary_secant_history_seed",
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
    if not PATCHED_RUNTIME.exists():
        raise SystemExit("patched runtime missing: P2 bundle is required")
    rel = ROOT.relative_to(REPO)
    runtime_rel = PATCHED_RUNTIME.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"export LD_LIBRARY_PATH=/workspace/{runtime_rel}:\$LD_LIBRARY_PATH; "
        f"ldd /workspace/physics_app/physics-opt | grep '/workspace/{runtime_rel}/libmoose-opt'; "
        f"python3 /workspace/{rel}/control_seq10.py --inner-run {case_name}"
    )
    result, code = analyze(case_name)
    (RESULTS / f"{case_name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE310_FP10_CASE:", case_name, result["classification"])
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
    runtime_converged = [name for name in CASE_NAMES if name in found and bool(found[name].get("evidence_valid"))]
    runtime_failed = [name for name in CASE_NAMES if name in found and not bool(found[name].get("evidence_valid"))]

    reference = found.get("picard_2x_seedpatch")
    comparisons: dict[str, object] = {}
    if reference is not None and bool(reference.get("evidence_valid")):
        for name in CASE_NAMES:
            if name == "picard_2x_seedpatch" or name not in found:
                continue
            trial = found[name]
            cmp = _comparison(reference, trial)
            if bool(trial.get("evidence_valid")):
                cmp["potential_time_series_parity"] = _potential_series_parity(reference, trial)
            comparisons[f"{name}_vs_picard_2x_seedpatch"] = cmp

    ranking: list[dict[str, object]] = []
    for name in runtime_converged:
        item = found[name]
        ranking.append({
            "case": name,
            "poisson_algorithm": item.get("poisson_fixed_point_algorithm"),
            "damping": item.get("relaxation_factor"),
            "elapsed_seconds": item.get("elapsed_seconds"),
            "cumulative_fixed_point_iterations": item.get("cumulative_fixed_point_iterations"),
            "average_fixed_point_iterations_per_observed_step": item.get("average_fixed_point_iterations_per_observed_step"),
            "fixed_point_time_series": item.get("fixed_point_time_series"),
        })
    ranking.sort(key=lambda x: (
        float(x["average_fixed_point_iterations_per_observed_step"])
        if isinstance(x.get("average_fixed_point_iterations_per_observed_step"), (int, float))
        else float("inf"),
        float(x["elapsed_seconds"]) if isinstance(x.get("elapsed_seconds"), (int, float)) else float("inf"),
    ))

    complete = not missing
    return {
        "issue": 310,
        "sequence": 10,
        "classification": "SECANT_HISTORY_SEED_DISCRIMINATOR_COMPLETE" if complete else "SECANT_HISTORY_SEED_DISCRIMINATOR_PARTIAL",
        "matrix_evidence_complete": complete,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_fast_steps": 4,
        "final_tau": FINAL_TAU,
        "architecture": "transient_timeaware",
        "framework_patch": "secondary_secant_history_seed",
        "runtime_converged_cases": runtime_converged,
        "runtime_failed_cases": runtime_failed,
        "missing_cases": missing,
        "cases": found,
        "comparisons_vs_picard_2x_seedpatch": comparisons,
        "runtime_ranking_by_fp_work": ranking,
        "target": {"desired_fp_per_step": "O(10)", "continue_threshold_fp_per_step": 50},
        "interpretation_guard": (
            "Runtime convergence is not scientific qualification. A Secant case must preserve the "
            "same-run patched-binary Picard-2x trajectory/profile, charge and potential. The architecture "
            "is frozen to TransientMultiApp + Transient Poisson with no TimeDerivative."
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
        (RESULTS / "issue310_fp10_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE310_FP10_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
