"""Issue #310 Gen31: 50-heavy-cycle output-off horizon discriminator.

Extends the qualified Gen30 output-off configuration from 10 to 50 heavy cycles
without changing physics, timesteps, fixed-point acceleration, or convergence.
Native MOOSE -t timing is retained. The discriminator tests whether suppressing
the per-fixed-point fp_anchor_csv diagnostic removes the historical long-horizon
wall-cost growth while preserving the known 50HC fixed-point trajectory/root.
"""
from __future__ import annotations
import argparse, json, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g
GENERATED = ROOT / "generated_fp31_50hc_output_off"
RESULTS = ROOT / "results_fp31_50hc_output_off"
MEDIUM_HEAVY_CYCLES = 50
MEDIUM_FINAL_TAU = g.FINAL_TAU * MEDIUM_HEAVY_CYCLES
SPECS = (
    {"name":"output_off_50hc","heavy_cycles":50,"suppress_fp_anchor_output":True,"bandwidth":5,"relaxation_factor":0.45,"custom_convergence":True,"delta_phi_abs_tol":1.0e-6,"fp_algorithm":"steffensen"},
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
        (d/"input.i").write_text(parent); (d/"fast_sub.i").write_text(fast); (d/"poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS,d/"electron_moments.txt"); shutil.copy2(g.base.ELASTIC_DATA,d/"o2_elastic.txt"); shutil.copy2(g.base.HEAVY_TRANSPORT_DATA,d/"transport_data.txt")
        (d/"case.json").write_text(json.dumps({**p,"fp_algorithm":"steffensen","heavy_cycles":raw["heavy_cycles"],"final_tau":final_tau},indent=2,sort_keys=True)+"\n")
        out.append(p)
    return out

def p0():
    built=build(); assert len(built)==1
    raw=SPECS[0]
    assert raw["heavy_cycles"] == 50
    assert raw["suppress_fp_anchor_output"] is True
    d=GENERATED/raw["name"]
    fast=(d/"fast_sub.i").read_text()
    poisson=(d/"poisson_sub.i").read_text()
    parent=(d/"input.i").read_text()
    marker="  [fp_anchor_csv]\n    enable = false\n"
    assert marker in fast
    assert fast.count("    enable = false\n") == 1
    assert f"fixed_point_algorithm = '{raw['fp_algorithm']}'" in fast
    assert "transformed_variables = 'potential_from_poisson'" in fast
    assert "type = PhysicsFVGummelBandedCorrection" in poisson
    assert "type = PhysicsDeltaPhiMultiAppConvergence" in fast
    assert "delta_phi_abs_tol = 9.9999999999999995e-07" in fast
    assert "no_restore = true" in fast
    # Long-horizon guard: Gen31 changes horizon from the qualified Gen30 B case,
    # not the scientific or convergence model.
    assert "type = TransientMultiApp" in parent
    metrics=g._projection_metrics(5); assert metrics["max_abs_row_sum"] < 1e-12
    print("ISSUE310_GEN31_P0: PASS", json.dumps({
        "case":raw["name"],
        "heavy_cycles":50,
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
    print("ISSUE310_GEN31_P1: PASS", json.dumps(candidates))

def p2():
    build(); rel=ROOT.relative_to(REPO); checks=[]
    for n in CASE_NAMES:
        for f in ("input.i","fast_sub.i","poisson_sub.i"):
            checks.append(f"cd /workspace/{rel}/generated_fp31_50hc_output_off/{n} && /workspace/physics_app/physics-opt --check-input -i {f}")
    g.base._docker("set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; make -C /workspace/physics_app -j2; "+"; ".join(checks))
    print("ISSUE310_GEN31_P2: PASS")

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
    g.base._docker("set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt PYTHONPATH=/workspace; "+f"python3 /workspace/{rel}/control_seq31_50hc_output_off.py --inner-run {name}; chmod -R a+rwX /workspace/{rel}/results_fp31_50hc_output_off /workspace/{rel}/generated_fp31_50hc_output_off")
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
        sequence=31,
        native_perfgraph_requested=False,
        native_timing_requested=True,
        native_timing_flag="-t",
        native_timing_log_bytes=len(perf_text.encode()),
        suppress_fp_anchor_output=bool(raw["suppress_fp_anchor_output"]),
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
    RESULTS.mkdir(parents=True,exist_ok=True)
    (RESULTS/f"{name}_result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    timing_tail="\n".join(perf_text.splitlines()[-700:])
    (RESULTS/f"{name}_timing_tail.txt").write_text(timing_tail+"\n")
    print("ISSUE310_GEN31_RESULT", json.dumps({
        "classification":result.get("classification"),
        "evidence_valid":result.get("evidence_valid"),
        "elapsed_seconds":result.get("elapsed_seconds"),
        "cumulative_fixed_point_iterations":result.get("cumulative_fixed_point_iterations"),
        "average_fixed_point_iterations_per_observed_step":result.get("average_fixed_point_iterations_per_observed_step"),
        "final_phi_avg_V":result.get("final_phi_avg_V"),
        "final_electron_density_avg":result.get("final_electron_density_avg"),
        "final_mean_electron_energy_avg":result.get("final_mean_electron_energy_avg"),
        "csv_file_count":result.get("csv_file_count"),
        "csv_total_bytes":result.get("csv_total_bytes"),
    },sort_keys=True))
    print("ISSUE310_GEN31_CASE",name,result["classification"])
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
    item=found.get("output_off_50hc")
    historical={
        "gen27_run":36021175641,
        "historical_output_on_50hc_elapsed_seconds":642.806550386,
        "historical_cumulative_fixed_point_iterations":5278,
        "historical_average_fixed_point_iterations_per_step":26.39,
        "historical_final_phi_avg_V":13.922355433540698,
    }
    comparison={}
    valid=False
    if item is not None:
        elapsed=float(item.get("elapsed_seconds",0.0))
        fp=item.get("cumulative_fixed_point_iterations")
        fpavg=item.get("average_fixed_point_iterations_per_observed_step")
        phi=float(item.get("final_phi_avg_V",0.0))
        valid=bool(item.get("evidence_valid"))
        comparison={
            "evidence_valid":valid,
            "fixed_point_total_matches_historical":fp == historical["historical_cumulative_fixed_point_iterations"],
            "fixed_point_average_delta":(
                float(fpavg)-historical["historical_average_fixed_point_iterations_per_step"]
                if isinstance(fpavg,(int,float)) else None
            ),
            "final_phi_avg_delta_V":phi-historical["historical_final_phi_avg_V"],
            "elapsed_seconds_output_off_50hc":elapsed,
            "historical_output_on_50hc_elapsed_seconds":historical["historical_output_on_50hc_elapsed_seconds"],
            "indicative_speedup_vs_gen27":(
                historical["historical_output_on_50hc_elapsed_seconds"]/elapsed if elapsed>0 else None
            ),
            "indicative_elapsed_reduction_fraction_vs_gen27":(
                (historical["historical_output_on_50hc_elapsed_seconds"]-elapsed)
                /historical["historical_output_on_50hc_elapsed_seconds"]
                if elapsed>0 else None
            ),
            "csv_file_count":item.get("csv_file_count"),
            "csv_total_bytes":item.get("csv_total_bytes"),
        }
    complete=not missing
    summary={
        "issue":310,
        "sequence":31,
        "classification":"GEN31_COMPLETE" if complete and valid else ("GEN31_PARTIAL" if missing else "GEN31_INVALID"),
        "missing_cases":missing,
        "case":item,
        "historical_reference":historical,
        "comparison":comparison,
        "guard":"Single 50HC horizon discriminator. Gen30 output-off physics/numerics are frozen; only the simulated horizon increases from 10HC to 50HC. Historical Gen27 elapsed comparison is indicative because runners differ; fixed-point work and native timing decomposition are the primary evidence."
    }
    RESULTS.mkdir(parents=True,exist_ok=True)
    (RESULTS/"issue310_gen31_50hc_output_off_summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("ISSUE310_GEN31_AGGREGATE",summary["classification"],json.dumps(comparison,sort_keys=True))

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
