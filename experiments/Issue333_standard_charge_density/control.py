#!/usr/bin/env python3
"""Issue #333 R1: replace PhysicsPlasmaChargeDensityMaterial with Standard MOOSE algebra.

Short discriminator only:
  - 1 heavy cycle / 4 electron steps
  - qualified Gen34 optimized coupling retained
  - custom charge material versus ADParsedFunctorMaterial chain
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from experiments.Issue310_fp_acceleration import control_seq34_relax2x_reference_input as gen34
from experiments.Issue310_fp_acceleration import control_seq18_deltaphi as g
from experiments.Issue310_fp_acceleration import control_seq08 as seq08
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_r1"
RESULTS = ROOT / "results_r1"

HEAVY_CYCLES = 1
FINAL_TAU = 400.0
CASE_NAMES = ("custom_charge", "standard_charge")

_BASE_SPEC = {
    "bandwidth": 5,
    "relaxation_factor": 0.45,
    "custom_convergence": True,
    "delta_phi_abs_tol": 1.0e-6,
    "fp_algorithm": "steffensen",
    "compute_scaling_once": True,
    "suppress_fp_anchor_output": True,
    "vector_profiles_final_only": True,
}

CUSTOM_BLOCK = """  [plasma_charge]
    type = PhysicsPlasmaChargeDensityMaterial
    density = rho_const
    electron_density = electron_density_m3
    ion_ids = 'O2p Om Op'
    ion_mass_fractions = 'w_O2p_frozen w_Om_frozen w_Op_frozen'
    ion_molar_masses = '0.032 0.016 0.016'
    ion_charges = '1 -1 1'
  []
"""

STANDARD_BLOCK = """  [charge_number_density_standard]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'electron_density_m3 rho_const w_O2p_frozen w_Om_frozen w_Op_frozen'
    functor_symbols = 'ne rho o2p om op'
    expression = '-ne+rho*6.02214076e23*(o2p/0.032-om/0.016+op/0.016)'
  []
  [charge_density_standard]
    type = ADParsedFunctorMaterial
    property_name = charge_density
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '1.602176634e-19*nq'
  []
  [poisson_charge_source_standard]
    type = ADParsedFunctorMaterial
    property_name = poisson_charge_source
    functor_names = 'charge_number_density'
    functor_symbols = 'nq'
    expression = '(1.602176634e-19/8.8541878128e-12)*nq'
  []
"""

def _bind_clock() -> None:
    gen34.HEAVY_CYCLES = HEAVY_CYCLES
    gen34.FINAL_TAU = FINAL_TAU
    gen34._bind_clock()

def _raw(name: str) -> dict[str, object]:
    return {"name": name, "role": "optimized", **_BASE_SPEC}

def build(clean: bool = True) -> None:
    _bind_clock()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    for name in CASE_NAMES:
        raw = _raw(name)
        parent, fast, poisson, p = gen34._optimized_inputs(raw)
        if poisson.count(CUSTOM_BLOCK) != 1:
            raise RuntimeError("qualified plasma_charge block changed")
        if name == "standard_charge":
            poisson = poisson.replace(CUSTOM_BLOCK, STANDARD_BLOCK, 1)
        d = GENERATED / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(parent)
        (d / "fast_sub.i").write_text(fast)
        (d / "poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(json.dumps({**p, "r1_variant": name}, indent=2, sort_keys=True) + "\n")

def p0() -> None:
    build()
    a = GENERATED / "custom_charge"
    b = GENERATED / "standard_charge"
    assert (a / "input.i").read_text() == (b / "input.i").read_text()
    assert (a / "fast_sub.i").read_text() == (b / "fast_sub.i").read_text()
    pa = (a / "poisson_sub.i").read_text()
    pb = (b / "poisson_sub.i").read_text()
    assert "type = PhysicsPlasmaChargeDensityMaterial" in pa
    assert "type = PhysicsPlasmaChargeDensityMaterial" not in pb
    assert pb.count("type = ADParsedFunctorMaterial") >= pa.count("type = ADParsedFunctorMaterial") + 3
    for token in ("charge_number_density", "charge_density", "poisson_charge_source"):
        assert token in pa and token in pb
    assert "type = PhysicsFVGummelBandedCorrection" in pa
    assert "type = PhysicsFVGummelBandedCorrection" in pb
    print("ISSUE333_R1_P0: PASS")

def p2() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    checks = []
    for name in CASE_NAMES:
        for fname in ("input.i", "fast_sub.i", "poisson_sub.i"):
            checks.append(
                f"cd /workspace/{rel}/generated_r1/{name} && "
                f"/workspace/physics_app/physics-opt --check-input -i {fname}"
            )
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE333_R1_P2: PASS")

def _bind_analysis() -> None:
    _bind_clock()
    seq08.GENERATED = GENERATED
    seq08.RESULTS = RESULTS
    seq08.FINAL_TAU = FINAL_TAU
    seq08.HEAVY_CYCLES = HEAVY_CYCLES
    seq08.CASE_NAMES = CASE_NAMES
    seq08.SPECS = tuple(g._spec(_raw(n)) for n in CASE_NAMES)
    wall08.FINAL_TAU = FINAL_TAU

def _inner_run(name: str) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    log = RESULTS / f"{name}_runtime.log"
    t0 = time.perf_counter()
    with log.open("w") as h:
        cp = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-t", "-i", "input.i"],
            cwd=GENERATED / name, stdout=h, stderr=subprocess.STDOUT, check=False
        )
    (RESULTS / f"{name}_elapsed_seconds.txt").write_text(f"{time.perf_counter()-t0:.9f}\n")
    (RESULTS / f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    return cp.returncode

def _inner_pair() -> int:
    first = 0
    for name in CASE_NAMES:
        rc = _inner_run(name)
        if rc and not first:
            first = rc
    return first

def _analyze(name: str) -> tuple[dict[str, object], int]:
    _bind_analysis()
    result, code = seq08.analyze(name)
    result["elapsed_seconds"] = float((RESULTS / f"{name}_elapsed_seconds.txt").read_text())
    result["r1_variant"] = name
    (RESULTS / f"{name}_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result, code

def run_case() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    g.base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"set +e; python3 /workspace/{rel}/control.py --inner-pair; rc=$?; set -e; "
        f"chmod -R a+rwX /workspace/{rel}/results_r1 /workspace/{rel}/generated_r1; exit $rc"
    )
    runs = {}
    codes = []
    for name in CASE_NAMES:
        r, c = _analyze(name)
        runs[name] = r
        codes.append(c)
    a, b = runs[CASE_NAMES[0]], runs[CASE_NAMES[1]]
    profile = wall08._comparison(a, b)
    trajectory = seq08._potential_series_parity(a, b)
    fp_a = [x["fixed_point_iterations"] for x in a.get("fixed_point_time_series", []) if x.get("time_s", 0) > 0]
    fp_b = [x["fixed_point_iterations"] for x in b.get("fixed_point_time_series", []) if x.get("time_s", 0) > 0]
    metrics = [abs(float(v)) for v in profile.values() if isinstance(v, (int, float))]
    comparison = {
        "fp_history_custom": fp_a,
        "fp_history_standard": fp_b,
        "fp_history_equal": fp_a == fp_b,
        "profile_parity": profile,
        "max_profile_metric": max(metrics) if metrics else None,
        "potential_time_series_parity": trajectory,
        "custom_elapsed_seconds": a["elapsed_seconds"],
        "standard_elapsed_seconds": b["elapsed_seconds"],
        "runtime_ratio_standard_over_custom": b["elapsed_seconds"]/a["elapsed_seconds"],
    }
    valid = all(c == 0 for c in codes) and bool(a.get("evidence_valid")) and bool(b.get("evidence_valid"))
    out = {
        "issue": 333,
        "case": "short_ab",
        "classification": "R1_SHORT_COMPLETE" if valid else "R1_SHORT_INVALID",
        "evidence_valid": valid,
        "runs": runs,
        "comparison": comparison,
    }
    (RESULTS / "short_ab_result.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("ISSUE333_R1_SHORT", json.dumps(comparison, sort_keys=True))
    if not valid:
        raise SystemExit(2)

def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    matches = list(Path(root).rglob("short_ab_result.json"))
    if not matches:
        raise SystemExit("missing R1 result")
    result = json.loads(matches[-1].read_text())
    comp = result["comparison"]
    qualified = bool(result.get("evidence_valid")) and bool(comp.get("fp_history_equal"))
    if comp.get("max_profile_metric") is not None:
        qualified = qualified and float(comp["max_profile_metric"]) <= 1.0e-7
    result["terminal_short_classification"] = (
        "STANDARD_REPLACEMENT_SHORT_GATE_PASS" if qualified else "R1_SHORT_GATE_FAIL"
    )
    (Path("r1_aggregate.json")).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("ISSUE333_R1_AGGREGATE", result["terminal_short_classification"])
    if not qualified:
        raise SystemExit(3)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--case")
    ap.add_argument("--inner-pair", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    a = ap.parse_args()
    if a.p0: p0()
    elif a.p2: p2()
    elif a.inner_pair: raise SystemExit(_inner_pair())
    elif a.case == "short_ab": run_case()
    elif a.aggregate: aggregate()
    else: ap.error("choose an action")

if __name__ == "__main__":
    main()
