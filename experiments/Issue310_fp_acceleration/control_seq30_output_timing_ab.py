"""Issue #310 Gen30: strict native-timing A/B for FP-anchor diagnostic output.

Both cases use the exact Gen29 10-heavy-cycle scientific/numerical model and
native MOOSE -t timing. The sole input difference is whether fp_anchor_csv is
enabled. Both solver invocations run sequentially in one pinned build container
to minimize runner-to-run timing noise.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g

GENERATED = ROOT / "generated_fp30_output_timing_ab"
RESULTS = ROOT / "results_fp30_output_timing_ab"
MEDIUM_HEAVY_CYCLES = 50
MEDIUM_FINAL_TAU = g.FINAL_TAU * MEDIUM_HEAVY_CYCLES
SPECS = (
    {"name":"output_on_10hc","heavy_cycles":10,"suppress_fp_anchor_output":False,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
    {"name":"output_off_10hc","heavy_cycles":10,"suppress_fp_anchor_output":True,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
)
CASE_NAMES = tuple(x["name"] for x in SPECS)

def bind():
    g.GENERATED = GENERATED; g.RESULTS = RESULTS
    g.SPECS = SPECS; g.CASE_NAMES = CASE_NAMES
    g.seq08.GENERATED = GENERATED; g.seq08.RESULTS = RESULTS
    g.FINAL_TAU = MEDIUM_FINAL_TAU; g.HEAVY_CYCLES = MEDIUM_HEAVY_CYCLES
    g.wall08.FINAL_TAU = MEDIUM_FINAL_TAU
    g.seq08.FINAL_TAU = MEDIUM_FINAL_TAU; g.seq08.HEAVY_CYCLES = MEDIUM_HEAVY_CYCLES
    g.seq08.CASE_NAMES = CASE_NAMES
    g.seq08.SPECS = tuple(g._spec(x) for x in SPECS)

def _accelerate(fast, algorithm):
    anchor = "  fixed_point_algorithm = 'picard'\n"
    if fast.count(anchor) != 1:
        raise RuntimeError("Gen30 fast Executioner fixed-point anchor changed")
    return fast.replace(anchor, f"  fixed_point_algorithm = '{algorithm}'\n  transformed_variables = 'potential_from_poisson'\n", 1)

def _disable_fp_anchor_output(fast):
    anchor = "  [fp_anchor_csv]\n    type = CSV\n"
    if fast.count(anchor) != 1:
        raise RuntimeError("Gen30 fp_anchor_csv output anchor changed")
    return fast.replace(anchor, "  [fp_anchor_csv]\n    type = CSV\n    enable = false\n", 1)

def _bind_case(raw):
    hc = int(raw["heavy_cycles"])
    final_tau = g.FINAL_TAU_BASE * hc if hasattr(g, "FINAL_TAU_BASE") else 400.0 * hc
    g.FINAL_TAU = final_tau; g.HEAVY_CYCLES = hc; g.wall08.FINAL_TAU = final_tau
    g.seq08.FINAL_TAU = final_tau; g.seq08.HEAVY_CYCLES = hc
    return final_tau

def build(clean=True):
    bind()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    out = []
    for raw in SPECS:
        final_tau = _bind_case(raw)
        p = g._params(raw)
        d = GENERATED / raw["name"]; d.mkdir(parents=True, exist_ok=True)
        parent, fast, poisson = g.render(raw, p)
        fast = _accelerate(fast, "steffensen")
        if raw["suppress_fp_anchor_output"]:
            fast = _disable_fp_anchor_output(fast)
        (d/"input.i").write_text(parent)
        (d/"fast_sub.i").write_text(fast)
        (d/"poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d/"electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d/"o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d/"transport_data.txt")
        (d/"case.json").write_text(json.dumps({**p,"fp_algorithm":"steffensen","heavy_cycles":raw["heavy_cycles"],"final_tau":final_tau,"suppress_fp_anchor_output":raw["suppress_fp_anchor_output"]}, indent=2, sort_keys=True)+"\n")
        out.append(p)
    return out

def p0():
    built = build()
    assert len(built) == 2
    assert all(x["heavy_cycles"] == 10 for x in SPECS)
    control = (GENERATED/"output_on_10hc"/"fast_sub.i").read_text()
    trial = (GENERATED/"output_off_10hc"/"fast_sub.i").read_text()
    marker = "    enable = false\n"
    assert trial.count(marker) == 1
    assert trial.replace(marker, "", 1) == control
    metrics = g._projection_metrics(5)
    assert metrics["max_abs_row_sum"] < 1e-12
    for raw in SPECS:
        d = GENERATED/raw["name"]
        fast = (d/"fast_sub.i").read_text()
        poisson = (d/"poisson_sub.i").read_text()
        assert f"fixed_point_algorithm = '{raw['fp_algorithm']}'" in fast
        assert "transformed_variables = 'potential_from_poisson'" in fast
        assert "type = PhysicsFVGummelBandedCorrection" in poisson
        assert "type = PhysicsDeltaPhiMultiAppConvergence" in fast
        assert "delta_phi_abs_tol = 9.9999999999999995e-07" in fast
        assert "no_restore = true" in fast
    print("ISSUE310_GEN30_P0: PASS", json.dumps({"cases":CASE_NAMES,"sole_fast_sub_diff":"fp_anchor_csv enable=false","band5":metrics}, sort_keys=True))

def p1():
    RESULTS.mkdir(parents=True, exist_ok=True)
    exe = REPO/"physics_app"/"physics-opt"
    if not exe.exists():
        raise SystemExit("physics-opt missing before timing qualification")
    cmd = [
        "docker","run","--rm","--entrypoint","/bin/bash","--user","0:0",
        "--workdir","/workspace","-v",f"{REPO}:/workspace:ro",
        g.base.BUILD_BASE_REF,
        "-lc","set -euo pipefail; source /environment; /workspace/physics_app/physics-opt --help",
    ]
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    (RESULTS/"physics_opt_help.txt").write_text(cp.stdout)
    if cp.returncode != 0:
        raise SystemExit(f"INFRASTRUCTURE_HARNESS_FAILURE: containerized physics-opt --help failed with return code {cp.returncode}")
    candidates = [line.strip() for line in cp.stdout.splitlines() if ("perf" in line.lower() or "timing" in line.lower())]
    if not any("--timing" in line or line.lstrip().startswith("-t ") for line in candidates):
        raise SystemExit("INFRASTRUCTURE_HARNESS_FAILURE: executable does not advertise -t/--timing")
    (RESULTS/"native_perf_candidates.json").write_text(json.dumps(candidates, indent=2)+"\n")
    print("ISSUE310_GEN30_P1: PASS", json.dumps(candidates))

def p2():
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for n in CASE_NAMES:
        for f in ("input.i","fast_sub.i","poisson_sub.i"):
            checks.append(f"cd /workspace/{rel}/generated_fp30_output_timing_ab/{n} && /workspace/physics_app/physics-opt --check-input -i {f}")
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE310_GEN30_P2: PASS")

def inner(name):
    bind(); RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED/name
    log = RESULTS/f"{name}_runtime.log"
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as h:
        cp = subprocess.run([str(REPO/"physics_app"/"physics-opt"),"-t","-i","input.i"], cwd=case_dir, stdout=h, stderr=subprocess.STDOUT, check=False)
    elapsed = time.perf_counter() - started
    (RESULTS/f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    (RESULTS/f"{name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    return cp.returncode

def _timing_excerpt(name):
    path = RESULTS/f"{name}_runtime.log"
    if not path.exists():
        return []
    keys = (
        "outputStep","Transient::PicardSolve","FEProblem::solve","execMultiApps",
        "execMultiAppTransfers","computeUserObjects","computeResidualInternal",
        "Finished Setting Up","Finished Executing"
    )
    return [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if any(k in line for k in keys)]

def _decorate(name, raw):
    _bind_case(raw)
    result, code = g.seq08.analyze(name)
    case_dir = GENERATED/name
    csv_files = list(case_dir.rglob("*.csv"))
    csv_bytes = sum(p.stat().st_size for p in csv_files if p.is_file())
    csv_rows = {}
    for p in csv_files:
        try:
            with p.open("r", encoding="utf-8", errors="replace") as h:
                csv_rows[str(p.relative_to(case_dir))] = max(sum(1 for _ in h)-1, 0)
        except OSError:
            pass
    perf_log = RESULTS/f"{name}_runtime.log"
    perf_text = perf_log.read_text(encoding="utf-8", errors="replace") if perf_log.exists() else ""
    result.update(
        sequence=30,
        suppress_fp_anchor_output=bool(raw["suppress_fp_anchor_output"]),
        native_timing_requested=True,
        native_timing_flag="-t",
        native_timing_log_bytes=len(perf_text.encode()),
        profile_heavy_cycles=raw["heavy_cycles"],
        banded_jacobian_width=5,
        outer_relaxation_factor=raw["relaxation_factor"],
        fast_fixed_point_algorithm=raw["fp_algorithm"],
        poisson_fixed_point_algorithm="picard",
        fixed_point_algorithm=raw["fp_algorithm"],
        custom_convergence=True,
        delta_phi_abs_tol=1e-6,
        csv_file_count=len(csv_files),
        csv_total_bytes=csv_bytes,
        csv_rows=csv_rows,
        **g._projection_metrics(5),
        **g._anchor_diagnostic(name),
    )
    (RESULTS/f"{name}_result.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    return result, code

def run_pair():
    bind()
    if not GENERATED.exists():
        build()
    if not (REPO/"physics_app"/"physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control_seq30_output_timing_ab.py --inner-run output_on_10hc; "
        f"python3 /workspace/{rel}/control_seq30_output_timing_ab.py --inner-run output_off_10hc; "
        f"chmod -R a+rwX /workspace/{rel}/results_fp30_output_timing_ab /workspace/{rel}/generated_fp30_output_timing_ab"
    )
    results = {}
    codes = []
    for raw in SPECS:
        result, code = _decorate(raw["name"], raw)
        results[raw["name"]] = result
        codes.append(code)
    control = results["output_on_10hc"]
    trial = results["output_off_10hc"]
    comparison = g.seq08._comparison(control, trial)
    comparison["potential_time_series_parity"] = g.seq08._potential_series_parity(control, trial)
    comparison["same_fixed_point_count"] = control.get("cumulative_fixed_point_iterations") == trial.get("cumulative_fixed_point_iterations")
    comparison["elapsed_seconds_control"] = control.get("elapsed_seconds")
    comparison["elapsed_seconds_trial"] = trial.get("elapsed_seconds")
    comparison["csv_total_bytes_control"] = control.get("csv_total_bytes")
    comparison["csv_total_bytes_trial"] = trial.get("csv_total_bytes")
    comparison["csv_file_count_control"] = control.get("csv_file_count")
    comparison["csv_file_count_trial"] = trial.get("csv_file_count")
    profile = comparison.get("final_profile_parity", {})
    profile_keys = ("electron_density_einf","mean_energy_einf","w_O2p_einf","w_Om_einf","w_Op_einf","net_charge_einf","raw_potential_einf")
    max_profile_error = max((abs(float(profile.get(k, 0.0))) for k in profile_keys), default=0.0)
    potential_series = comparison.get("potential_time_series_parity", {})
    max_series_delta = max((abs(float(v)) for k,v in potential_series.items() if k.endswith("_max_abs_delta") and isinstance(v,(int,float))), default=0.0)
    strict_parity = (
        bool(control.get("evidence_valid")) and bool(trial.get("evidence_valid"))
        and bool(comparison["same_fixed_point_count"])
        and max_profile_error <= 1e-12
        and max_series_delta <= 1e-12
    )
    comparison["max_final_profile_error"] = max_profile_error
    comparison["max_potential_series_abs_delta"] = max_series_delta
    comparison["strict_scientific_parity"] = strict_parity
    pair = {
        "issue":310,
        "sequence":30,
        "case":"output_ab_10hc",
        "classification":"GEN30_OUTPUT_AB_COMPLETE" if strict_parity and not any(codes) else "GEN30_OUTPUT_AB_INVALID",
        "strict_scientific_parity":strict_parity,
        "cases":results,
        "comparison":comparison,
        "guard":"Same runner/container, same frozen Gen29 configuration and -t timing; sole fast_sub.i difference is fp_anchor_csv enable=false in trial.",
    }
    (RESULTS/"output_ab_10hc_pair_result.json").write_text(json.dumps(pair, indent=2, sort_keys=True)+"\n")
    print("ISSUE310_GEN30_PAIR", json.dumps({
        "classification":pair["classification"],
        "strict_scientific_parity":strict_parity,
        "same_fixed_point_count":comparison["same_fixed_point_count"],
        "control_elapsed_seconds":comparison["elapsed_seconds_control"],
        "trial_elapsed_seconds":comparison["elapsed_seconds_trial"],
        "elapsed_speedup":comparison.get("elapsed_speedup_vs_baseline"),
        "control_csv_bytes":comparison["csv_total_bytes_control"],
        "trial_csv_bytes":comparison["csv_total_bytes_trial"],
        "max_final_profile_error":max_profile_error,
        "max_potential_series_abs_delta":max_series_delta,
    }, sort_keys=True))
    for name in CASE_NAMES:
        print(f"ISSUE310_GEN30_TIMING_BEGIN {name}")
        for line in _timing_excerpt(name):
            print(line)
        print(f"ISSUE310_GEN30_TIMING_END {name}")
    if any(codes) or not strict_parity:
        raise SystemExit(2)

def aggregate():
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    pair_files = list(Path(root).rglob("output_ab_10hc_pair_result.json"))
    if not pair_files:
        raise SystemExit("missing Gen30 pair result")
    pair = json.loads(pair_files[0].read_text())
    summary = {
        "issue":310,
        "sequence":30,
        "classification":"GEN30_COMPLETE" if pair.get("strict_scientific_parity") else "GEN30_INVALID",
        "strict_scientific_parity":pair.get("strict_scientific_parity"),
        "comparison":pair.get("comparison"),
        "guard":pair.get("guard"),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"issue310_gen30_output_timing_ab_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n")
    print("ISSUE310_GEN30_AGGREGATE", summary["classification"])
    print(json.dumps(summary, sort_keys=True))
    if not summary["strict_scientific_parity"]:
        raise SystemExit(2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--inner-run", choices=CASE_NAMES)
    ap.add_argument("--pair", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    a = ap.parse_args()
    if a.p0: p0()
    elif a.p1: p1()
    elif a.p2: p2()
    elif a.inner_run: raise SystemExit(inner(a.inner_run))
    elif a.pair: run_pair()
    elif a.aggregate: aggregate()
    else: ap.error("choose one action")

if __name__ == "__main__":
    main()
