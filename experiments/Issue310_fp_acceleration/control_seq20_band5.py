"""Issue #310 Gen20: band5 alpha 0.45/0.50/0.55 requalification at delta-phi 1e-6.

Reuses the Gen18 measured band5 iteration operator without changing physics.
Gen19 established delta-phi 1e-6 as the corrected coupled-reference criterion.
"""
from __future__ import annotations
import argparse, json, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g
GENERATED = ROOT / "generated_fp20_band5"
RESULTS = ROOT / "results_fp20_band5"
SPECS = tuple({
    "name": f"band5_a{int(a*100):03d}_dphi1e6",
    "bandwidth": 5,
    "relaxation_factor": a,
    "custom_convergence": True,
    "delta_phi_abs_tol": 1.0e-6,
} for a in (0.45, 0.50, 0.55))
CASE_NAMES = tuple(x["name"] for x in SPECS)

def bind():
    g.GENERATED = GENERATED; g.RESULTS = RESULTS
    g.SPECS = SPECS; g.CASE_NAMES = CASE_NAMES
    # Preserve the complete Gen18 runtime binding contract. seq08.analyze()
    # reads these module globals when validating heavy-step history, so only
    # rebinding generated/results/specs is insufficient for a 1-heavy-cycle
    # Gen20 discriminator.
    g.seq08.GENERATED = GENERATED; g.seq08.RESULTS = RESULTS
    g.seq08.FINAL_TAU = g.FINAL_TAU; g.seq08.HEAVY_CYCLES = g.HEAVY_CYCLES
    g.seq08.CASE_NAMES = CASE_NAMES
    g.seq08.SPECS = tuple(g._spec(x) for x in SPECS)
    g.wall08.FINAL_TAU = g.FINAL_TAU

def build(clean=True):
    bind()
    if clean and GENERATED.exists(): shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    out=[]
    for raw in SPECS:
        p=g._params(raw); d=GENERATED/raw["name"]; d.mkdir(parents=True, exist_ok=True)
        parent,fast,poisson=g.render(raw,p)
        (d/"input.i").write_text(parent); (d/"fast_sub.i").write_text(fast); (d/"poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS,d/"electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA,d/"o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA,d/"transport_data.txt")
        (d/"case.json").write_text(json.dumps(p,indent=2,sort_keys=True)+"\n")
        out.append(p)
    return out

def p0():
    built=build(); assert len(built)==3
    metrics=g._projection_metrics(5); assert metrics["max_abs_row_sum"] < 1e-12
    for raw in SPECS:
        d=GENERATED/raw["name"]; fast=(d/"fast_sub.i").read_text(); poisson=(d/"poisson_sub.i").read_text()
        assert "type = FVElectronResponseBandedCorrection" in poisson
        assert "type = DeltaPhiMultiAppConvergence" in fast
        assert "delta_phi_abs_tol = 9.9999999999999995e-07" in fast
        assert "no_restore = true" in fast
    print("ISSUE310_GEN20_P0: PASS", json.dumps({"cases":CASE_NAMES,"band5":metrics},sort_keys=True))

def p1():
    build(); rel=ROOT.relative_to(REPO)
    cmds="; ".join(f"python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_fp20_band5/{n}/input.i" for n in CASE_NAMES)
    g.base._docker("set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "+cmds)
    print("ISSUE310_GEN20_P1: PASS")

def p2():
    build(); rel=ROOT.relative_to(REPO); checks=[]
    for n in CASE_NAMES:
        for f in ("input.i","fast_sub.i","poisson_sub.i"):
            checks.append(f"cd /workspace/{rel}/generated_fp20_band5/{n} && /workspace/physics_app/physics-opt --check-input -i {f}")
    g.base._docker("set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; make -C /workspace/physics_app -j2; "+"; ".join(checks))
    print("ISSUE310_GEN20_P2: PASS")

def inner(name):
    bind(); RESULTS.mkdir(parents=True,exist_ok=True); return g.seq08.inner_run(name)

def run_case(name):
    bind()
    if not GENERATED.exists(): build()
    if not (REPO/"physics_app"/"physics-opt").exists(): raise SystemExit("physics-opt missing")
    rel=ROOT.relative_to(REPO)
    g.base._docker("set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt PYTHONPATH=/workspace; "+f"python3 /workspace/{rel}/control_seq20_band5.py --inner-run {name}; chmod -R a+rwX /workspace/{rel}/results_fp20_band5 /workspace/{rel}/generated_fp20_band5")
    result,code=g.seq08.analyze(name); raw=next(x for x in SPECS if x["name"]==name)
    result.update(sequence=20,banded_jacobian_width=5,outer_relaxation_factor=raw["relaxation_factor"],custom_convergence=True,delta_phi_abs_tol=1e-6,gen19_reference_phi_avg_V=3.9792365725690155,**g._projection_metrics(5),**g._anchor_diagnostic(name))
    RESULTS.mkdir(parents=True,exist_ok=True); (RESULTS/f"{name}_result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ISSUE310_GEN20_CASE",name,result["classification"])
    if code: raise SystemExit(code)

def aggregate():
    root=os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT");
    if not root: raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    found={}
    for p in Path(root).rglob("*_result.json"):
        item=json.loads(p.read_text()); name=str(item.get("case",""))
        if name in CASE_NAMES: found[name]=item
    missing=[n for n in CASE_NAMES if n not in found]
    cases={}
    for n,item in found.items():
        cases[n]={k:item.get(k) for k in ("classification","evidence_valid","elapsed_seconds","cumulative_fixed_point_iterations","average_fixed_point_iterations_per_observed_step","final_phi_avg_V","final_electron_density_avg","final_mean_electron_energy_avg")}
    summary={"issue":310,"sequence":20,"classification":"GEN20_COMPLETE" if not missing else "GEN20_PARTIAL","missing_cases":missing,"cases":cases,"reference":{"gen19_run":35996399004,"head":"d2d9958735d6afe4c6a23d47880477772a998d78","delta_phi_abs_tol":1e-6,"phi_avg_V":3.9792365725690155},"guard":"Iteration-only band5 correction; frozen physics/no_restore; promotion requires corrected-root parity plus lower FP work and wall time."}
    RESULTS.mkdir(parents=True,exist_ok=True); (RESULTS/"issue310_gen20_band5_summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("ISSUE310_GEN20_AGGREGATE",summary["classification"])

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
