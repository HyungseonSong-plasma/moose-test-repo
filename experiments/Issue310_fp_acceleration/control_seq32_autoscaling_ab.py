"""Issue #310 Gen32: automatic-scaling policy A/B under minimal output.

Both 10-heavy-cycle cases preserve the qualified Gen31/Gen30 physics, band5
correction, Steffensen coupling, custom delta-phi convergence, timesteps, and
fp_anchor_csv suppression. The sole policy change is compute_scaling_once:
false (refresh scaling) versus true (reuse scaling) in the parent and electron
Executioners. Poisson input remains byte-identical. Native MOOSE -t timing is
retained and scientific parity gates any performance interpretation.
"""
from __future__ import annotations
import argparse, json, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g
GENERATED = ROOT / "generated_fp32_autoscaling_ab"
RESULTS = ROOT / "results_fp32_autoscaling_ab"
MEDIUM_HEAVY_CYCLES = 50
MEDIUM_FINAL_TAU = g.FINAL_TAU * MEDIUM_HEAVY_CYCLES
SPECS = (
    {"name":"scaling_refresh_10hc","heavy_cycles":10,"suppress_fp_anchor_output":True,"compute_scaling_once":False,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
    {"name":"scaling_once_10hc","heavy_cycles":10,"suppress_fp_anchor_output":True,"compute_scaling_once":True,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
)
CASE_NAMES = tuple(x["name"] for x in SPECS)

def bind():
    g.GENERATED = GENERATED; g.RESULTS = RESULTS
    g.SPECS = SPECS; g.CASE_NAMES = CASE_NAMES
    # Preserve the complete Gen18 runtime binding contract. seq08.analyze()
    # reads these module globals when validating heavy-step history, so only
    # rebinding generated/results/specs is insufficient for a 1-heavy-cycle
    # Gen21 discriminator.
    g.seq08.GENERATED = GENERATED; g.seq08.RESULTS = RESULTS
    g.FINAL_TAU = MEDIUM_FINAL_TAU; g.HEAVY_CYCLES = MEDIUM_HEAVY_CYCLES
    g.wall08.FINAL_TAU = MEDIUM_FINAL_TAU
    g.seq08.FINAL_TAU = MEDIUM_FINAL_TAU; g.seq08.HEAVY_CYCLES = MEDIUM_HEAVY_CYCLES
    g.seq08.CASE_NAMES = CASE_NAMES
    g.seq08.SPECS = tuple(g._spec(x) for x in SPECS)
    g.wall08.FINAL_TAU = MEDIUM_FINAL_TAU

def _accelerate(fast, algorithm):
    anchor = "  fixed_point_algorithm = 'picard'\n"
    if fast.count(anchor) != 1:
        raise RuntimeError("Gen23 fast Executioner fixed-point anchor changed")
    return fast.replace(anchor, f"  fixed_point_algorithm = '{algorithm}'\n  transformed_variables = 'potential_from_poisson'\n", 1)

def _bind_case(raw):
    hc=int(raw["heavy_cycles"]); final_tau=g.FINAL_TAU_BASE * hc if hasattr(g,"FINAL_TAU_BASE") else 400.0*hc
    g.FINAL_TAU=final_tau; g.HEAVY_CYCLES=hc; g.wall08.FINAL_TAU=final_tau
    g.seq08.FINAL_TAU=final_tau; g.seq08.HEAVY_CYCLES=hc
    return final_tau

def build(clean=True):
    bind()
    if clean and GENERATED.exists(): shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    out=[]
    for raw in SPECS:
        final_tau=_bind_case(raw)
        p=g._params(raw); d=GENERATED/raw["name"]; d.mkdir(parents=True, exist_ok=True)
        parent,fast,poisson=g.render(raw,p); fast=_accelerate(fast,"steffensen")
        if raw["suppress_fp_anchor_output"]:
            anchor = "  [fp_anchor_csv]\n"
            if fast.count(anchor) != 1:
                raise RuntimeError("fp_anchor_csv output block missing or ambiguous")
            fast = fast.replace(anchor, anchor + "    enable = false\n", 1)
        scaling_anchor = "  compute_scaling_once = false\n"
        if parent.count(scaling_anchor) != 1 or fast.count(scaling_anchor) != 1:
            raise RuntimeError("compute_scaling_once=false anchor changed in parent/fast Executioner")
        if bool(raw["compute_scaling_once"]):
            parent = parent.replace(scaling_anchor, "  compute_scaling_once = true\n", 1)
            fast = fast.replace(scaling_anchor, "  compute_scaling_once = true\n", 1)
        (d/"input.i").write_text(parent); (d/"fast_sub.i").write_text(fast); (d/"poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS,d/"electron_moments.txt"); shutil.copy2(g.base.ELASTIC_DATA,d/"o2_elastic.txt"); shutil.copy2(g.base.HEAVY_TRANSPORT_DATA,d/"transport_data.txt")
        (d/"case.json").write_text(json.dumps({**p,"fp_algorithm":"steffensen","heavy_cycles":raw["heavy_cycles"],"final_tau":final_tau,"suppress_fp_anchor_output":True,"compute_scaling_once":bool(raw["compute_scaling_once"])},indent=2,sort_keys=True)+"\n")
        out.append(p)
    return out

def p0():
    built=build(); assert len(built)==2
    assert all(x["heavy_cycles"] == 10 for x in SPECS)
    assert all(x["suppress_fp_anchor_output"] is True for x in SPECS)
    a=GENERATED/"scaling_refresh_10hc"
    b=GENERATED/"scaling_once_10hc"
    for d in (a,b):
        fast=(d/"fast_sub.i").read_text()
        assert "  [fp_anchor_csv]\n    enable = false\n" in fast
        assert "fixed_point_algorithm = 'steffensen'" in fast
        assert "transformed_variables = 'potential_from_poisson'" in fast
        assert "type = DeltaPhiMultiAppConvergence" in fast
        assert "delta_phi_abs_tol = 9.9999999999999995e-07" in fast
        assert "no_restore = true" in fast
        assert "type = FVElectronResponseBandedCorrection" in (d/"poisson_sub.i").read_text()
    parent_a=(a/"input.i").read_text(); parent_b=(b/"input.i").read_text()
    fast_a=(a/"fast_sub.i").read_text(); fast_b=(b/"fast_sub.i").read_text()
    poisson_a=(a/"poisson_sub.i").read_bytes(); poisson_b=(b/"poisson_sub.i").read_bytes()
    assert parent_a.count("  compute_scaling_once = false\n") == 1
    assert parent_b.count("  compute_scaling_once = true\n") == 1
    assert fast_a.count("  compute_scaling_once = false\n") == 1
    assert fast_b.count("  compute_scaling_once = true\n") == 1
    # Strict policy A/B: normalizing the two parent+electron policy lines makes
    # the scientific inputs byte-identical. Poisson is untouched.
    assert parent_b.replace("  compute_scaling_once = true\n","  compute_scaling_once = false\n",1) == parent_a
    assert fast_b.replace("  compute_scaling_once = true\n","  compute_scaling_once = false\n",1) == fast_a
    assert poisson_a == poisson_b
    metrics=g._projection_metrics(5); assert metrics["max_abs_row_sum"] < 1e-12
    print("ISSUE310_GEN32_P0: PASS", json.dumps({
        "cases":CASE_NAMES,
        "strict_ab_only_difference":"compute_scaling_once false->true in parent and electron Executioners",
        "fp_anchor_csv_enabled":False,
        "band5":metrics
    },sort_keys=True))

def p1():
    import subprocess
    # Read-only capability probe: consume the executable qualified by the prior
    # prepare stage. The binary is linked against the pinned build-container
    # runtime, so interrogate it in that same runtime instead of on the host
    # GitHub runner, where missing MOOSE/libMesh libraries can masquerade as a
    # missing timing capability.
    RESULTS.mkdir(parents=True,exist_ok=True)
    exe=REPO/"physics_app"/"physics-opt"
    if not exe.exists(): raise SystemExit("physics-opt missing before profiler qualification")
    cmd=[
        "docker","run","--rm","--entrypoint","/bin/bash","--user","0:0",
        "--workdir","/workspace","-v",f"{REPO}:/workspace:ro",
        g.base.BUILD_BASE_REF,
        "-lc","set -euo pipefail; source /environment; /workspace/physics_app/physics-opt --help",
    ]
    cp=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=False)
    (RESULTS/"physics_opt_help.txt").write_text(cp.stdout)
    if cp.returncode != 0:
        raise SystemExit(
            f"INFRASTRUCTURE_HARNESS_FAILURE: containerized physics-opt --help failed "
            f"with return code {cp.returncode}"
        )
    candidates=[line.strip() for line in cp.stdout.splitlines() if ("perf" in line.lower() or "timing" in line.lower())]
    (RESULTS/"native_perf_candidates.json").write_text(json.dumps(candidates,indent=2)+"\n")
    if not candidates:
        raise SystemExit("INFRASTRUCTURE_HARNESS_FAILURE: executable advertises no perf/timing option in --help")
    timing_supported = any("--timing" in line or line.lstrip().startswith("-t ") for line in candidates)
    if not timing_supported:
        raise SystemExit("INFRASTRUCTURE_HARNESS_FAILURE: executable does not advertise -t/--timing")
    print("ISSUE310_GEN32_P1: PASS", json.dumps(candidates))

def p2():
    build(); rel=ROOT.relative_to(REPO); checks=[]
    for n in CASE_NAMES:
        for f in ("input.i","fast_sub.i","poisson_sub.i"):
            checks.append(f"cd /workspace/{rel}/generated_fp32_autoscaling_ab/{n} && /workspace/physics_app/physics-opt --check-input -i {f}")
    g.base._docker("set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; make -C /workspace/physics_app -j2; "+"; ".join(checks))
    print("ISSUE310_GEN32_P2: PASS")

def inner(name):
    import subprocess,time
    bind(); RESULTS.mkdir(parents=True,exist_ok=True)
    case_dir=GENERATED/name; log=RESULTS/f"{name}_runtime.log"; started=time.perf_counter()
    with log.open("w",encoding="utf-8") as h:
        cp=subprocess.run([str(REPO/"physics_app"/"physics-opt"),"-t","-i","input.i"],cwd=case_dir,stdout=h,stderr=subprocess.STDOUT,check=False)
    elapsed=time.perf_counter()-started
    (RESULTS/f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    (RESULTS/f"{name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    # Preserve the full native timing report; do not discard it as seq08 normally does.
    return cp.returncode

def run_case(name):
    bind()
    raw=next(x for x in SPECS if x["name"]==name); final_tau=_bind_case(raw)
    if not GENERATED.exists(): build()
    if not (REPO/"physics_app"/"physics-opt").exists(): raise SystemExit("physics-opt missing")
    rel=ROOT.relative_to(REPO)
    g.base._docker("set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt PYTHONPATH=/workspace; "+f"python3 /workspace/{rel}/control_seq32_autoscaling_ab.py --inner-run {name}; chmod -R a+rwX /workspace/{rel}/results_fp32_autoscaling_ab /workspace/{rel}/generated_fp32_autoscaling_ab")
    result,code=g.seq08.analyze(name)
    case_dir=GENERATED/name
    csv_files=list(case_dir.rglob("*.csv"))
    csv_bytes=sum(p.stat().st_size for p in csv_files if p.is_file())
    csv_rows={}
    for p in csv_files:
        try:
            with p.open("r",encoding="utf-8",errors="replace") as h: csv_rows[str(p.relative_to(case_dir))]=max(sum(1 for _ in h)-1,0)
        except OSError: pass
    perf_log=RESULTS/f"{name}_runtime.log"
    perf_text=perf_log.read_text(encoding="utf-8",errors="replace") if perf_log.exists() else ""
    result.update(
        sequence=32,
        native_perfgraph_requested=False,
        native_timing_requested=True,
        native_timing_flag="-t",
        native_timing_log_bytes=len(perf_text.encode()),
        suppress_fp_anchor_output=bool(raw["suppress_fp_anchor_output"]),
        compute_scaling_once=bool(raw["compute_scaling_once"]),
        automatic_scaling_log_count=perf_text.count("Performing automatic scaling calculation"),
        main_app_solve_log_count=perf_text.count("Main app solve:"),
        fixed_point_residual_log_count=perf_text.count("Fixed point residual norm after TIMESTEP_END MultiApps:"),
        profile_heavy_cycles=raw["heavy_cycles"],
        profile_final_tau=final_tau,
        csv_file_count=len(csv_files),
        csv_total_bytes=csv_bytes,
        csv_rows=csv_rows,
        banded_jacobian_width=5,
        outer_relaxation_factor=raw["relaxation_factor"],
        fast_fixed_point_algorithm=raw["fp_algorithm"],
        poisson_fixed_point_algorithm="picard",
        fixed_point_algorithm=raw["fp_algorithm"],
        custom_convergence=True,
        delta_phi_abs_tol=1e-6,
        gen19_reference_phi_avg_V=3.9792365725690155,
        **g._projection_metrics(5),
        **g._anchor_diagnostic(name),
    )
    RESULTS.mkdir(parents=True,exist_ok=True); (RESULTS/f"{name}_result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ISSUE310_GEN32_CASE",name,result["classification"])
    if code: raise SystemExit(code)

def aggregate():
    root=os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    found={}
    for p in Path(root).rglob("*_result.json"):
        item=json.loads(p.read_text())
        name=str(item.get("case",""))
        if name in CASE_NAMES:
            found[name]=item
    missing=[n for n in CASE_NAMES if n not in found]
    cases={}
    for n,item in found.items():
        cases[n]={k:item.get(k) for k in (
            "classification","evidence_valid","elapsed_seconds",
            "cumulative_fixed_point_iterations",
            "average_fixed_point_iterations_per_observed_step",
            "final_phi_avg_V","final_electron_density_avg",
            "final_mean_electron_energy_avg",
            "automatic_scaling_log_count","main_app_solve_log_count",
            "fixed_point_residual_log_count","compute_scaling_once",
            "csv_file_count","csv_total_bytes"
        )}
    comparison={}
    gate=False
    if not missing:
        a=found["scaling_refresh_10hc"]
        b=found["scaling_once_10hc"]
        valid=bool(a.get("evidence_valid")) and bool(b.get("evidence_valid"))
        fp_equal=(
            a.get("cumulative_fixed_point_iterations") == b.get("cumulative_fixed_point_iterations")
            and a.get("average_fixed_point_iterations_per_observed_step") == b.get("average_fixed_point_iterations_per_observed_step")
        )
        profile=g.wall08._comparison(a,b) if valid else {}
        trajectory=g.seq08._potential_series_parity(a,b) if valid else {}
        numeric_profile=[abs(float(v)) for v in profile.values() if isinstance(v,(int,float))]
        max_profile=max(numeric_profile) if numeric_profile else None
        traj_numeric=[abs(float(v)) for k,v in trajectory.items() if k.endswith("_delta") and isinstance(v,(int,float))]
        max_traj=max(traj_numeric) if traj_numeric else None
        ea=float(a.get("elapsed_seconds",0.0)); eb=float(b.get("elapsed_seconds",0.0))
        comparison={
            "evidence_valid_both":valid,
            "fixed_point_work_equal":fp_equal,
            "profile_parity":profile,
            "max_profile_metric":max_profile,
            "potential_time_series_parity":trajectory,
            "max_trajectory_abs_delta":max_traj,
            "scaling_log_count_refresh":a.get("automatic_scaling_log_count"),
            "scaling_log_count_once":b.get("automatic_scaling_log_count"),
            "scaling_log_count_reduction":(
                int(a.get("automatic_scaling_log_count",0))-int(b.get("automatic_scaling_log_count",0))
            ),
            "elapsed_seconds_refresh":ea,
            "elapsed_seconds_once":eb,
            "elapsed_speedup_refresh_over_once":(ea/eb if eb>0 else None),
            "elapsed_reduction_fraction":((ea-eb)/ea if ea>0 else None),
        }
        # Use a round-off-scale scientific guard that is strict relative to the
        # 1e-6 V convergence tolerance but avoids Gen30's demonstrated 1e-12
        # false-negative threshold on independent runners.
        gate=bool(valid and fp_equal and max_profile is not None and max_profile <= 1.0e-10
                  and max_traj is not None and max_traj <= 1.0e-10)
    summary={
        "issue":310,
        "sequence":32,
        "classification":"GEN32_COMPLETE" if not missing else "GEN32_PARTIAL",
        "missing_cases":missing,
        "cases":cases,
        "comparison":comparison,
        "scientific_parity_gate_pass":gate,
        "guard":"Strict 10HC minimal-output A/B. Only compute_scaling_once changes from false to true in parent and electron Executioners; Poisson, physics, band5, alpha, Steffensen, timestep, delta-phi convergence, fp_anchor_csv suppression and native -t timing are frozen. Performance interpretation requires scientific parity."
    }
    RESULTS.mkdir(parents=True,exist_ok=True)
    (RESULTS/"issue310_gen32_autoscaling_ab_summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("ISSUE310_GEN32_AGGREGATE",summary["classification"],"scientific_parity_gate_pass=",gate,json.dumps(comparison,sort_keys=True))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--p0",action="store_true"); ap.add_argument("--p1",action="store_true"); ap.add_argument("--p2",action="store_true"); ap.add_argument("--inner-run",choices=CASE_NAMES); ap.add_argument("--case",choices=CASE_NAMES); ap.add_argument("--aggregate",action="store_true"); a=ap.parse_args()
    if a.p0:p0()
    elif a.p1:p1()
    elif a.p2:p2()
    elif a.inner_run:raise SystemExit(inner(a.inner_run))
    elif a.case:run_case(a.case)
    elif a.aggregate:aggregate()
    else:ap.error("choose one action")
if __name__=="__main__": main()
