"""Issue #310 Gen33: same-run paired AB/BA automatic-scaling benchmark.

Two governed matrix jobs each run both policies sequentially on the same runner:
  pair_ab: refresh(false) -> once(true)
  pair_ba: once(true) -> refresh(false)

The reverse order controls first/second-run cache and process-order effects. Physics,
band5 correction, alpha, Steffensen coupling, delta-phi convergence, timesteps,
minimal output, executable, and native -t timing remain frozen. Performance is
reported primarily as within-run refresh/once ratios and their geometric mean.
"""
from __future__ import annotations

import argparse
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

from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g

GENERATED = ROOT / "generated_fp33_autoscaling_paired"
RESULTS = ROOT / "results_fp33_autoscaling_paired"

HEAVY_CYCLES = 10
FINAL_TAU = g.FINAL_TAU_BASE * HEAVY_CYCLES if hasattr(g, "FINAL_TAU_BASE") else 400.0 * HEAVY_CYCLES

RUN_SPECS = (
    {"name":"ab_refresh_10hc","heavy_cycles":10,"suppress_fp_anchor_output":True,"compute_scaling_once":False,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
    {"name":"ab_once_10hc","heavy_cycles":10,"suppress_fp_anchor_output":True,"compute_scaling_once":True,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
    {"name":"ba_once_10hc","heavy_cycles":10,"suppress_fp_anchor_output":True,"compute_scaling_once":True,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
    {"name":"ba_refresh_10hc","heavy_cycles":10,"suppress_fp_anchor_output":True,"compute_scaling_once":False,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
)
RUN_NAMES = tuple(x["name"] for x in RUN_SPECS)
PAIR_ORDERS = {
    "pair_ab": ("ab_refresh_10hc", "ab_once_10hc"),
    "pair_ba": ("ba_once_10hc", "ba_refresh_10hc"),
}
CASE_NAMES = tuple(PAIR_ORDERS)


def _run_spec(name: str) -> dict[str, object]:
    return next(x for x in RUN_SPECS if x["name"] == name)


def _bind() -> None:
    g.GENERATED = GENERATED
    g.RESULTS = RESULTS
    g.SPECS = RUN_SPECS
    g.CASE_NAMES = RUN_NAMES
    g.FINAL_TAU = FINAL_TAU
    g.HEAVY_CYCLES = HEAVY_CYCLES
    g.wall08.FINAL_TAU = FINAL_TAU

    g.seq08.GENERATED = GENERATED
    g.seq08.RESULTS = RESULTS
    g.seq08.FINAL_TAU = FINAL_TAU
    g.seq08.HEAVY_CYCLES = HEAVY_CYCLES
    g.seq08.CASE_NAMES = RUN_NAMES
    g.seq08.SPECS = tuple(g._spec(x) for x in RUN_SPECS)


def _accelerate(fast: str) -> str:
    anchor = "  fixed_point_algorithm = 'picard'\n"
    if fast.count(anchor) != 1:
        raise RuntimeError("fast fixed-point algorithm anchor changed")
    return fast.replace(
        anchor,
        "  fixed_point_algorithm = 'steffensen'\n"
        "  transformed_variables = 'potential_from_poisson'\n",
        1,
    )


def build(clean: bool = True) -> list[dict[str, object]]:
    _bind()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    built = []

    for raw in RUN_SPECS:
        p = g._params(raw)
        d = GENERATED / str(raw["name"])
        d.mkdir(parents=True, exist_ok=True)
        parent, fast, poisson = g.render(raw, p)
        fast = _accelerate(fast)

        output_anchor = "  [fp_anchor_csv]\n"
        if fast.count(output_anchor) != 1:
            raise RuntimeError("fp_anchor_csv output anchor changed")
        fast = fast.replace(output_anchor, output_anchor + "    enable = false\n", 1)

        scaling_anchor = "  compute_scaling_once = false\n"
        if parent.count(scaling_anchor) != 1 or fast.count(scaling_anchor) != 1:
            raise RuntimeError("compute_scaling_once=false anchor changed")
        if bool(raw["compute_scaling_once"]):
            parent = parent.replace(scaling_anchor, "  compute_scaling_once = true\n", 1)
            fast = fast.replace(scaling_anchor, "  compute_scaling_once = true\n", 1)

        (d / "input.i").write_text(parent)
        (d / "fast_sub.i").write_text(fast)
        (d / "poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(
            json.dumps(
                {
                    **p,
                    "fp_algorithm": "steffensen",
                    "heavy_cycles": HEAVY_CYCLES,
                    "final_tau": FINAL_TAU,
                    "suppress_fp_anchor_output": True,
                    "compute_scaling_once": bool(raw["compute_scaling_once"]),
                },
                indent=2,
                sort_keys=True,
            ) + "\n"
        )
        built.append(p)
    return built


def _normalise_scaling(text: str) -> str:
    return text.replace("  compute_scaling_once = true\n", "  compute_scaling_once = false\n")


def p0() -> None:
    built = build()
    assert len(built) == 4
    assert set(PAIR_ORDERS["pair_ab"]) == {"ab_refresh_10hc", "ab_once_10hc"}
    assert set(PAIR_ORDERS["pair_ba"]) == {"ba_refresh_10hc", "ba_once_10hc"}

    dirs = {n: GENERATED / n for n in RUN_NAMES}
    for n, d in dirs.items():
        fast = (d / "fast_sub.i").read_text()
        assert "  [fp_anchor_csv]\n    enable = false\n" in fast
        assert "fixed_point_algorithm = 'steffensen'" in fast
        assert "transformed_variables = 'potential_from_poisson'" in fast
        assert "type = PhysicsDeltaPhiMultiAppConvergence" in fast
        assert "delta_phi_abs_tol = 9.9999999999999995e-07" in fast
        assert "no_restore = true" in fast
        assert "type = PhysicsFVGummelBandedCorrection" in (d / "poisson_sub.i").read_text()

    # Same-policy replicas across AB/BA must be byte-identical.
    for fname in ("input.i", "fast_sub.i", "poisson_sub.i"):
        assert (dirs["ab_refresh_10hc"] / fname).read_bytes() == (dirs["ba_refresh_10hc"] / fname).read_bytes()
        assert (dirs["ab_once_10hc"] / fname).read_bytes() == (dirs["ba_once_10hc"] / fname).read_bytes()

    # Across policies, only parent/electron compute_scaling_once may differ.
    refresh_parent = (dirs["ab_refresh_10hc"] / "input.i").read_text()
    once_parent = (dirs["ab_once_10hc"] / "input.i").read_text()
    refresh_fast = (dirs["ab_refresh_10hc"] / "fast_sub.i").read_text()
    once_fast = (dirs["ab_once_10hc"] / "fast_sub.i").read_text()
    assert _normalise_scaling(once_parent) == refresh_parent
    assert _normalise_scaling(once_fast) == refresh_fast
    assert (dirs["ab_refresh_10hc"] / "poisson_sub.i").read_bytes() == (dirs["ab_once_10hc"] / "poisson_sub.i").read_bytes()

    metrics = g._projection_metrics(5)
    assert metrics["max_abs_row_sum"] < 1e-12
    print("ISSUE310_GEN33_P0: PASS", json.dumps({
        "pair_orders": PAIR_ORDERS,
        "same_policy_replicas_byte_identical": True,
        "strict_policy_difference": "compute_scaling_once false/true in parent and electron Executioners only",
        "fp_anchor_csv_enabled": False,
        "band5": metrics,
    }, sort_keys=True))


def p1() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
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
    (RESULTS / "physics_opt_help.txt").write_text(cp.stdout)
    if cp.returncode != 0:
        raise SystemExit(f"INFRASTRUCTURE_HARNESS_FAILURE: physics-opt --help rc={cp.returncode}")
    candidates = [line.strip() for line in cp.stdout.splitlines() if ("perf" in line.lower() or "timing" in line.lower())]
    if not any("--timing" in line or line.lstrip().startswith("-t ") for line in candidates):
        raise SystemExit("INFRASTRUCTURE_HARNESS_FAILURE: -t/--timing unsupported")
    print("ISSUE310_GEN33_P1: PASS", json.dumps(candidates))


def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for n in RUN_NAMES:
        for f in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_fp33_autoscaling_paired/{n} && "
                f"/workspace/physics_app/physics-opt --check-input -i {f}"
            )
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_GEN33_P2: PASS")


def inner(run_name: str) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED / run_name
    log = RESULTS / f"{run_name}_runtime.log"
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as h:
        cp = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-t", "-i", "input.i"],
            cwd=case_dir,
            stdout=h,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    (RESULTS / f"{run_name}_returncode.txt").write_text(f"{cp.returncode}\n")
    (RESULTS / f"{run_name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    return cp.returncode


def inner_pair(pair_name: str) -> int:
    rc = 0
    for run_name in PAIR_ORDERS[pair_name]:
        this_rc = inner(run_name)
        if this_rc != 0 and rc == 0:
            rc = this_rc
    return rc


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _table_rows(text: str, electron: bool) -> list[dict[str, object]]:
    rows = []
    for raw in text.splitlines():
        line = _ANSI.sub("", raw)
        if electron:
            if not line.startswith("electron0: |"):
                continue
            line = line[len("electron0: "):]
        else:
            if not line.startswith("|"):
                continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 9:
            continue
        try:
            calls = int(parts[2])
            self_seconds = float(parts[3])
            total_seconds = float(parts[7])
        except (ValueError, IndexError):
            continue
        rows.append({
            "name": parts[1],
            "calls": calls,
            "self_seconds": self_seconds,
            "total_seconds": total_seconds,
        })
    return rows


def _pick(rows: list[dict[str, object]], name: str, max_calls: bool = True):
    hits = [r for r in rows if r["name"] == name]
    if not hits:
        return None
    return max(hits, key=lambda r: int(r["calls"])) if max_calls else hits[0]


def _timing_summary(text: str) -> dict[str, object]:
    clean = _ANSI.sub("", text)
    electron = _table_rows(clean, True)
    main = _table_rows(clean, False)

    def bracket_seconds(label: str):
        m = re.search(re.escape(label) + r".*?\[\s*([0-9.]+)\s*s\]", clean)
        return float(m.group(1)) if m else None

    e_jac = [r for r in electron if r["name"] == "FEProblem::computeJacobianInternal"]
    m_jac = [r for r in main if r["name"] == "FEProblem::computeJacobianInternal"]
    return {
        "finished_instantiating_subapps_seconds": bracket_seconds("Finished Instantiating Sub-Apps"),
        "finished_executing_seconds": bracket_seconds("Finished Executing"),
        "electron_root": _pick(electron, "PhysicsTestApp (electron0)"),
        "electron_picard": _pick(electron, "Transient::PicardSolve"),
        "electron_solve": _pick(electron, "FEProblem::solve"),
        "electron_exec_multiapps": _pick(electron, "FEProblem::execMultiApps"),
        "electron_userobjects": _pick(electron, "FEProblem::computeUserObjects"),
        "electron_jacobians": sorted(e_jac, key=lambda r: int(r["calls"])),
        "main_picard": _pick(main, "Transient::PicardSolve"),
        "main_solve": _pick(main, "FEProblem::solve"),
        "main_exec_multiapps": _pick(main, "FEProblem::execMultiApps"),
        "main_jacobians": sorted(m_jac, key=lambda r: int(r["calls"])),
    }


def analyze_run(run_name: str) -> tuple[dict[str, object], int]:
    _bind()
    raw = _run_spec(run_name)
    result, code = g.seq08.analyze(run_name)
    log_path = RESULTS / f"{run_name}_runtime.log"
    perf_text = log_path.read_text(encoding="utf-8", errors="replace")
    elapsed = float((RESULTS / f"{run_name}_elapsed_seconds.txt").read_text().strip())

    case_dir = GENERATED / run_name
    csv_files = [p for p in case_dir.rglob("*.csv") if p.is_file()]
    result.update(
        sequence=33,
        paired_run_name=run_name,
        compute_scaling_once=bool(raw["compute_scaling_once"]),
        suppress_fp_anchor_output=True,
        native_timing_requested=True,
        native_timing_flag="-t",
        elapsed_seconds=elapsed,
        automatic_scaling_log_count=perf_text.count("Performing automatic scaling calculation"),
        main_app_solve_log_count=perf_text.count("Main app solve:"),
        fixed_point_residual_log_count=perf_text.count("Fixed point residual norm after TIMESTEP_END MultiApps:"),
        csv_file_count=len(csv_files),
        csv_total_bytes=sum(p.stat().st_size for p in csv_files),
        fast_fixed_point_algorithm="steffensen",
        poisson_fixed_point_algorithm="picard",
        fixed_point_algorithm="steffensen",
        banded_jacobian_width=5,
        outer_relaxation_factor=0.45,
        custom_convergence=True,
        delta_phi_abs_tol=1e-6,
        timing_summary=_timing_summary(perf_text),
        **g._projection_metrics(5),
        **g._anchor_diagnostic(run_name),
    )
    (RESULTS / f"{run_name}_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result, code


def run_pair(pair_name: str) -> None:
    _bind()
    if not GENERATED.exists():
        build()
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")

    rel = ROOT.relative_to(REPO)
    cmd = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"set +e; python3 /workspace/{rel}/control_seq33_autoscaling_paired.py --inner-pair {pair_name}; "
        "rc=$?; set -e; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp33_autoscaling_paired "
        f"/workspace/{rel}/generated_fp33_autoscaling_paired; exit $rc"
    )
    g.base._docker(cmd)

    runs = {}
    codes = []
    for run_name in PAIR_ORDERS[pair_name]:
        result, code = analyze_run(run_name)
        runs[run_name] = result
        codes.append(code)

    refresh_name = next(n for n in PAIR_ORDERS[pair_name] if not bool(_run_spec(n)["compute_scaling_once"]))
    once_name = next(n for n in PAIR_ORDERS[pair_name] if bool(_run_spec(n)["compute_scaling_once"]))
    refresh = runs[refresh_name]
    once = runs[once_name]

    profile = g.wall08._comparison(refresh, once)
    trajectory = g.seq08._potential_series_parity(refresh, once)
    numeric_profile = [abs(float(v)) for v in profile.values() if isinstance(v, (int, float))]
    traj_numeric = [abs(float(v)) for k, v in trajectory.items() if k.endswith("_delta") and isinstance(v, (int, float))]
    max_profile = max(numeric_profile) if numeric_profile else None
    max_traj = max(traj_numeric) if traj_numeric else None
    er = float(refresh["elapsed_seconds"])
    eo = float(once["elapsed_seconds"])

    pair = {
        "issue": 310,
        "sequence": 33,
        "case": pair_name,
        "classification": "GEN33_PAIR_COMPLETE" if all(c == 0 for c in codes) else "GEN33_PAIR_INVALID",
        "evidence_valid": bool(refresh.get("evidence_valid")) and bool(once.get("evidence_valid")) and all(c == 0 for c in codes),
        "order": list(PAIR_ORDERS[pair_name]),
        "refresh_run": refresh_name,
        "once_run": once_name,
        "runs": runs,
        "comparison": {
            "refresh_elapsed_seconds": er,
            "once_elapsed_seconds": eo,
            "refresh_over_once_speedup": er / eo if eo > 0 else None,
            "once_elapsed_reduction_fraction": (er - eo) / er if er > 0 else None,
            "refresh_fp_total": refresh.get("cumulative_fixed_point_iterations"),
            "once_fp_total": once.get("cumulative_fixed_point_iterations"),
            "refresh_fp_per_step": refresh.get("average_fixed_point_iterations_per_observed_step"),
            "once_fp_per_step": once.get("average_fixed_point_iterations_per_observed_step"),
            "refresh_scaling_log_count": refresh.get("automatic_scaling_log_count"),
            "once_scaling_log_count": once.get("automatic_scaling_log_count"),
            "profile_parity": profile,
            "max_profile_metric": max_profile,
            "potential_time_series_parity": trajectory,
            "max_trajectory_abs_delta": max_traj,
            "root_parity_within_1e_10": bool(
                max_profile is not None and max_profile <= 1.0e-10
                and max_traj is not None and max_traj <= 1.0e-10
            ),
        },
        "guard": "Within-run paired benchmark; both policies execute sequentially in separate physics-opt processes on the same runner. AB/BA reverse order controls order/cache bias. Physics and minimal-output configuration are frozen.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{pair_name}_result.json").write_text(json.dumps(pair, indent=2, sort_keys=True) + "\n")
    print("ISSUE310_GEN33_PAIR", pair_name, json.dumps(pair["comparison"], sort_keys=True))
    if not pair["evidence_valid"]:
        raise SystemExit(2)


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    found = {}
    for p in Path(root).rglob("*_result.json"):
        item = json.loads(p.read_text())
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [n for n in CASE_NAMES if n not in found]

    complete = not missing and all(bool(found[n].get("evidence_valid")) for n in CASE_NAMES)
    ratios = []
    for n in CASE_NAMES:
        if n in found:
            r = found[n].get("comparison", {}).get("refresh_over_once_speedup")
            if isinstance(r, (int, float)) and r > 0:
                ratios.append(float(r))

    geometric_mean = math.prod(ratios) ** (1.0 / len(ratios)) if len(ratios) == len(CASE_NAMES) else None
    reduction = (1.0 - 1.0 / geometric_mean) if geometric_mean and geometric_mean > 0 else None

    summary = {
        "issue": 310,
        "sequence": 33,
        "classification": "GEN33_COMPLETE" if complete else ("GEN33_PARTIAL" if missing else "GEN33_INVALID"),
        "missing_cases": missing,
        "pairs": found,
        "paired_speedup_ratios_refresh_over_once": ratios,
        "geometric_mean_refresh_over_once_speedup": geometric_mean,
        "geometric_mean_once_elapsed_reduction_fraction": reduction,
        "interpretation_guard": "Primary timing estimator is the geometric mean of within-run refresh/once ratios from AB and BA orders. Do not compare absolute elapsed times across the two matrix runners.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "issue310_gen33_autoscaling_paired_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE310_GEN33_AGGREGATE", summary["classification"], json.dumps({
        "ratios": ratios,
        "geometric_mean_speedup": geometric_mean,
        "geometric_mean_reduction_fraction": reduction,
    }, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--inner-run", choices=RUN_NAMES)
    ap.add_argument("--inner-pair", choices=CASE_NAMES)
    ap.add_argument("--case", choices=CASE_NAMES)
    ap.add_argument("--aggregate", action="store_true")
    a = ap.parse_args()

    if a.p0:
        p0()
    elif a.p1:
        p1()
    elif a.p2:
        p2()
    elif a.inner_run:
        raise SystemExit(inner(a.inner_run))
    elif a.inner_pair:
        raise SystemExit(inner_pair(a.inner_pair))
    elif a.case:
        run_pair(a.case)
    elif a.aggregate:
        aggregate()
    else:
        ap.error("choose one action")


if __name__ == "__main__":
    main()
