"""Issue #310 Gen34: paired 20 ns relax_2x reference vs optimized endpoint benchmark."""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq34_relax2x_reference_input as inp

g = inp.g
seq08 = g.seq08
wall08 = g.wall08

GENERATED = inp.GENERATED
RESULTS = inp.RESULTS
REFERENCE = "relax2x_reference_20ns"
OPTIMIZED = "optimized_endpoint_20ns"

PAIR_ORDERS = {
    "pair_ab": (REFERENCE, OPTIMIZED),
    "pair_ba": (OPTIMIZED, REFERENCE),
}
PAIR_NAMES = tuple(PAIR_ORDERS)


def _raw(name: str) -> dict[str, object]:
    return next(x for x in inp.SPECS if x["name"] == name)


def _bind() -> None:
    inp._bind_clock()
    seq08.GENERATED = GENERATED
    seq08.RESULTS = RESULTS
    seq08.FINAL_TAU = inp.FINAL_TAU
    seq08.HEAVY_CYCLES = inp.HEAVY_CYCLES
    seq08.CASE_NAMES = inp.CASE_NAMES
    seq08.SPECS = tuple(g._spec(x) for x in inp.SPECS)
    wall08.FINAL_TAU = inp.FINAL_TAU


def p0() -> None:
    inp.p0()
    contract = json.loads((GENERATED / "comparison_contract.json").read_text())
    assert contract["controlled_reference"]["name"] == REFERENCE
    assert contract["optimized_endpoint"]["name"] == OPTIMIZED
    print("ISSUE310_GEN34_BENCHMARK_P0: PASS")


def p1() -> None:
    exe = REPO / "physics_app" / "physics-opt"
    if not exe.exists():
        raise SystemExit("physics-opt missing before timing qualification")
    cmd = [
        "docker", "run", "--rm", "--entrypoint", "/bin/bash", "--user", "0:0",
        "--workdir", "/workspace", "-v", f"{REPO}:/workspace:ro",
        g.base.BUILD_BASE_REF,
        "-lc", "set -euo pipefail; source /environment; /workspace/physics_app/physics-opt --help",
    ]
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "physics_opt_help.txt").write_text(cp.stdout)
    if cp.returncode != 0:
        raise SystemExit(f"INFRASTRUCTURE_HARNESS_FAILURE: physics-opt --help rc={cp.returncode}")
    if "--timing" not in cp.stdout and "-t " not in cp.stdout:
        raise SystemExit("INFRASTRUCTURE_HARNESS_FAILURE: -t/--timing unsupported")
    print("ISSUE310_GEN34_BENCHMARK_P1: PASS")


def p2() -> None:
    inp.build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for name in inp.CASE_NAMES:
        for fname in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_fp34_relax2x_reference/{name} && "
                f"/workspace/physics_app/physics-opt --check-input -i {fname}"
            )
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_GEN34_BENCHMARK_P2: PASS")


def inner_run(name: str) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED / name
    log = RESULTS / f"{name}_runtime.log"
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        cp = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-t", "-i", "input.i"],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    (RESULTS / f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    (RESULTS / f"{name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    return cp.returncode


def inner_pair(pair_name: str) -> int:
    first_rc = 0
    for name in PAIR_ORDERS[pair_name]:
        rc = inner_run(name)
        if rc != 0 and first_rc == 0:
            first_rc = rc
    return first_rc


def analyze_run(name: str) -> tuple[dict[str, object], int]:
    _bind()
    result, code = seq08.analyze(name)
    raw = _raw(name)
    log_path = RESULTS / f"{name}_runtime.log"
    log = log_path.read_text(encoding="utf-8", errors="replace")
    elapsed = float((RESULTS / f"{name}_elapsed_seconds.txt").read_text().strip())
    case_dir = GENERATED / name
    csv_files = [p for p in case_dir.rglob("*.csv") if p.is_file()]

    result.update(
        issue=310,
        sequence=34,
        role=raw["role"],
        elapsed_seconds=elapsed,
        nominal_target_time_ns=20.0,
        heavy_cycles=inp.HEAVY_CYCLES,
        electron_steps_target=inp.HEAVY_CYCLES * 4,
        relaxation_factor=float(raw["relaxation_factor"]),
        fixed_point_algorithm=str(raw["fp_algorithm"]),
        banded_jacobian_width=int(raw["bandwidth"]),
        custom_convergence=True,
        delta_phi_abs_tol=inp.DELTA_PHI_TOL,
        compute_scaling_once=True,
        suppress_fp_anchor_output=True,
        automatic_scaling_log_count=log.count("Performing automatic scaling calculation"),
        main_app_solve_log_count=log.count("Main app solve:"),
        fixed_point_residual_log_count=log.count(
            "Fixed point residual norm after TIMESTEP_END MultiApps:"
        ),
        csv_file_count=len(csv_files),
        csv_total_bytes=sum(p.stat().st_size for p in csv_files),
    )
    if int(raw["bandwidth"]) > 0:
        result.update(g._projection_metrics(int(raw["bandwidth"])))

    out = RESULTS / f"{name}_result.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result, code


def run_pair(pair_name: str) -> None:
    _bind()
    if not GENERATED.exists():
        inp.build()
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")

    rel = ROOT.relative_to(REPO)
    cmd = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"set +e; python3 /workspace/{rel}/control_seq34_relax2x_reference_benchmark.py "
        f"--inner-pair {pair_name}; rc=$?; set -e; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp34_relax2x_reference "
        f"/workspace/{rel}/generated_fp34_relax2x_reference; exit $rc"
    )
    g.base._docker(cmd)

    runs: dict[str, dict[str, object]] = {}
    codes = []
    for name in PAIR_ORDERS[pair_name]:
        result, code = analyze_run(name)
        runs[name] = result
        codes.append(code)

    ref = runs[REFERENCE]
    opt = runs[OPTIMIZED]
    profile = wall08._comparison(ref, opt)
    trajectory = seq08._potential_series_parity(ref, opt)
    profile_values = [abs(float(v)) for v in profile.values() if isinstance(v, (int, float))]
    traj_values = [
        abs(float(v))
        for k, v in trajectory.items()
        if isinstance(v, (int, float)) and k.endswith("_delta")
    ]
    max_profile = max(profile_values) if profile_values else None
    max_traj = max(traj_values) if traj_values else None

    tr = float(ref["elapsed_seconds"])
    to = float(opt["elapsed_seconds"])
    fp_ref = ref.get("cumulative_fixed_point_iterations")
    fp_opt = opt.get("cumulative_fixed_point_iterations")

    comparison = {
        "reference_elapsed_seconds": tr,
        "optimized_elapsed_seconds": to,
        "wall_speedup_reference_over_optimized": tr / to if to > 0 else None,
        "wall_reduction_fraction": (tr - to) / tr if tr > 0 else None,
        "reference_fp_total": fp_ref,
        "optimized_fp_total": fp_opt,
        "reference_fp_per_step": ref.get("average_fixed_point_iterations_per_observed_step"),
        "optimized_fp_per_step": opt.get("average_fixed_point_iterations_per_observed_step"),
        "fp_reduction_fraction": (
            1.0 - float(fp_opt) / float(fp_ref)
            if isinstance(fp_ref, (int, float)) and isinstance(fp_opt, (int, float)) and fp_ref
            else None
        ),
        "profile_parity": profile,
        "max_profile_metric": max_profile,
        "potential_time_series_parity": trajectory,
        "max_trajectory_abs_delta": max_traj,
        "root_parity_within_1e_9": bool(
            max_profile is not None and max_profile <= 1.0e-9
            and max_traj is not None and max_traj <= 1.0e-9
        ),
    }

    valid = bool(ref.get("evidence_valid")) and bool(opt.get("evidence_valid")) and all(c == 0 for c in codes)
    pair = {
        "issue": 310,
        "sequence": 34,
        "case": pair_name,
        "classification": "GEN34_PAIR_COMPLETE" if valid else "GEN34_PAIR_INVALID",
        "evidence_valid": valid,
        "order": list(PAIR_ORDERS[pair_name]),
        "runs": runs,
        "comparison": comparison,
        "guard": (
            "Reference and optimized endpoint run as separate physics-opt processes on the same "
            "runner. Both use the same 88-HC (~19.94 ns) clock, canonical physics, delta-phi "
            "accuracy criterion, scaling-once policy, and minimal FP output."
        ),
    }
    (RESULTS / f"{pair_name}_result.json").write_text(
        json.dumps(pair, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE310_GEN34_PAIR", pair_name, json.dumps(comparison, sort_keys=True))
    if not valid:
        raise SystemExit(2)


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")

    found = {}
    for path in Path(root).rglob("*_result.json"):
        item = json.loads(path.read_text())
        name = str(item.get("case", ""))
        if name in PAIR_NAMES:
            found[name] = item

    missing = [n for n in PAIR_NAMES if n not in found]
    complete = not missing and all(bool(found[n].get("evidence_valid")) for n in PAIR_NAMES)

    speedups = []
    fp_reductions = []
    for name in PAIR_NAMES:
        if name not in found:
            continue
        comp = found[name]["comparison"]
        s = comp.get("wall_speedup_reference_over_optimized")
        f = comp.get("fp_reduction_fraction")
        if isinstance(s, (int, float)) and s > 0:
            speedups.append(float(s))
        if isinstance(f, (int, float)):
            fp_reductions.append(float(f))

    geo_speedup = (
        math.prod(speedups) ** (1.0 / len(speedups))
        if len(speedups) == len(PAIR_NAMES)
        else None
    )
    summary = {
        "issue": 310,
        "sequence": 34,
        "classification": "GEN34_COMPLETE" if complete else ("GEN34_PARTIAL" if missing else "GEN34_INVALID"),
        "missing_pairs": missing,
        "pairs": found,
        "geometric_mean_wall_speedup": geo_speedup,
        "geometric_mean_wall_reduction_fraction": (
            1.0 - 1.0 / geo_speedup if geo_speedup and geo_speedup > 0 else None
        ),
        "fp_reduction_fractions": fp_reductions,
        "interpretation_guard": (
            "Primary speed estimator is the geometric mean of same-run reference/optimized ratios "
            "from AB and BA. Historical Sequence01 relax_2x runtime is reported separately and is "
            "not substituted for this controlled current-physics comparison."
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "issue310_gen34_relax2x_20ns_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE310_GEN34_AGGREGATE", summary["classification"], json.dumps({
        "geometric_mean_wall_speedup": summary["geometric_mean_wall_speedup"],
        "geometric_mean_wall_reduction_fraction": summary["geometric_mean_wall_reduction_fraction"],
        "fp_reduction_fractions": fp_reductions,
    }, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--inner-run", choices=inp.CASE_NAMES)
    ap.add_argument("--inner-pair", choices=PAIR_NAMES)
    ap.add_argument("--case", choices=PAIR_NAMES)
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()

    if args.p0:
        p0()
    elif args.p1:
        p1()
    elif args.p2:
        p2()
    elif args.inner_run:
        raise SystemExit(inner_run(args.inner_run))
    elif args.inner_pair:
        raise SystemExit(inner_pair(args.inner_pair))
    elif args.case:
        run_pair(args.case)
    elif args.aggregate:
        aggregate()
    else:
        ap.error("choose an action")


if __name__ == "__main__":
    main()
