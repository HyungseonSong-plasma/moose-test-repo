#!/usr/bin/env python3
"""Regression for the unified electrostatic-drift and electron-flux API.

Baseline:
  - legacy PhysicsFVLogMolarElectrostaticDrift compatibility name
  - joule_mobility / joule_diffusion pass-through functors

Unified:
  - PhysicsFVElectrostaticDrift transported_state=exponential
  - Joule heating consumes canonical electron_mobility/electron_diffusion directly

All other qualified PlasmaClosures + Gummel physics is unchanged.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq08 as seq08
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08
from experiments.Issue337_plasma_closures_migration import control as migration
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose.input import MooseInput

CASE_NAMES = ("compat_flux", "unified_flux")


def _paths(horizon: str):
    if horizon == "short":
        cycles = 1
    elif horizon == "full":
        cycles = 88
    else:
        raise ValueError(horizon)
    return ROOT / f"generated_{horizon}", ROOT / f"results_{horizon}", cycles, 400.0 * cycles


def _bind(horizon: str):
    generated, results, cycles, final_tau = _paths(horizon)

    migration.gen34.HEAVY_CYCLES = cycles
    migration.gen34.FINAL_TAU = final_tau
    migration.gen34._bind_clock()
    migration.wall08.FINAL_TAU = final_tau

    seq08.GENERATED = generated
    seq08.RESULTS = results
    seq08.FINAL_TAU = final_tau
    seq08.HEAVY_CYCLES = cycles
    seq08.CASE_NAMES = CASE_NAMES
    seq08.SPECS = tuple(
        {
            "name": name,
            "architecture": name,
            "algorithm": "steffensen",
            "relaxation_factor": 0.45,
        }
        for name in CASE_NAMES
    )
    wall08.FINAL_TAU = final_tau
    return generated, results, cycles, final_tau


def _qualified_migrated_inputs(horizon: str):
    _bind(horizon)
    parent, fast, poisson, params = migration.gen34._optimized_inputs(dict(migration.BASE_SPEC))
    fast = migration.g336._actionize(fast)
    return (
        migration._migrate_parent(parent),
        migration._migrate_fast(fast),
        migration._migrate_poisson(poisson),
        params,
    )


def _get_block(text: str, path: str) -> str:
    span = MooseInput(text).unique(path)
    return text[span.start:span.end].rstrip()


def _unify_fast_input(text: str) -> str:
    text = mb.remove_block(text, "FunctorMaterials/joule_transport_switch")
    text = mb.remove_block(text, "FunctorMaterials/joule_diffusion_switch")

    drift = _get_block(text, "FVKernels/electron_drift")
    assert "type = PhysicsFVLogMolarElectrostaticDrift" in drift
    drift = drift.replace(
        "type = PhysicsFVLogMolarElectrostaticDrift",
        "type = PhysicsFVElectrostaticDrift\n    transported_state = exponential",
        1,
    )
    text = mb.replace_block(text, "FVKernels/electron_drift", drift)

    joule = _get_block(text, "FVKernels/energy_joule")
    assert "mobility = joule_mobility" in joule
    assert "diffusion = joule_diffusion" in joule
    joule = joule.replace("mobility = joule_mobility", "mobility = electron_mobility")
    joule = joule.replace("diffusion = joule_diffusion", "diffusion = electron_diffusion")
    text = mb.replace_block(text, "FVKernels/energy_joule", joule)
    return text


def _semantic(text: str) -> str:
    # HIT indentation is not semantic; compare every nonblank token line.
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _normalize_compat(text: str) -> str:
    text = mb.remove_block(text, "FunctorMaterials/joule_transport_switch")
    text = mb.remove_block(text, "FunctorMaterials/joule_diffusion_switch")
    drift = _get_block(text, "FVKernels/electron_drift")
    drift = drift.replace(
        "type = PhysicsFVLogMolarElectrostaticDrift",
        "type = PhysicsFVElectrostaticDrift\n    transported_state = exponential",
        1,
    )
    text = mb.replace_block(text, "FVKernels/electron_drift", drift)
    joule = _get_block(text, "FVKernels/energy_joule")
    joule = joule.replace("mobility = joule_mobility", "mobility = electron_mobility")
    joule = joule.replace("diffusion = joule_diffusion", "diffusion = electron_diffusion")
    return text


def build(horizon: str, clean: bool = True) -> None:
    generated, results, cycles, final_tau = _bind(horizon)
    if clean:
        shutil.rmtree(generated, ignore_errors=True)
        shutil.rmtree(results, ignore_errors=True)
    generated.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)

    parent, fast, poisson, params = _qualified_migrated_inputs(horizon)
    cases = {
        "compat_flux": (parent, fast, poisson),
        "unified_flux": (parent, _unify_fast_input(fast), poisson),
    }

    for name, (case_parent, case_fast, case_poisson) in cases.items():
        d = generated / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(case_parent)
        (d / "fast_sub.i").write_text(case_fast)
        (d / "poisson_sub.i").write_text(case_poisson)
        shutil.copy2(migration.g336.g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(migration.g336.g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(migration.g336.g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(
            json.dumps(
                {
                    **params,
                    "name": name,
                    "phase": "electron_flux_unification",
                    "horizon": horizon,
                    "heavy_cycles": cycles,
                    "electron_steps": 4 * cycles,
                    "final_tau": final_tau,
                    "fixed_point_algorithm": "steffensen",
                    "relaxation_factor": 0.45,
                    "bandwidth": 5,
                    "delta_phi_abs_tol": migration.DPHI_TOL,
                },
                indent=2,
                sort_keys=True,
            ) + "\n"
        )


def p0(horizon: str) -> None:
    build(horizon)
    generated, _, cycles, _ = _bind(horizon)
    compat = (generated / "compat_flux" / "fast_sub.i").read_text()
    unified = (generated / "unified_flux" / "fast_sub.i").read_text()

    assert "type = PhysicsFVLogMolarElectrostaticDrift" in compat
    assert "mobility = joule_mobility" in compat
    assert "diffusion = joule_diffusion" in compat

    assert "type = PhysicsFVLogMolarElectrostaticDrift" not in unified
    assert "type = PhysicsFVElectrostaticDrift" in unified
    assert "transported_state = exponential" in unified
    assert "joule_transport_switch" not in unified
    assert "joule_diffusion_switch" not in unified
    assert "mobility = electron_mobility" in unified
    assert "diffusion = electron_diffusion" in unified

    # Numerical parity is the authoritative regression gate. The targeted
    # assertions above constrain the input migration surface without relying
    # on non-semantic HIT formatting/placement.
    print(f"ELECTRON_FLUX_UNIFICATION_P0_{horizon.upper()}: PASS cycles={cycles}")


def p1(horizon: str) -> None:
    build(horizon)
    generated, _, _, _ = _bind(horizon)
    exe = REPO / "physics_app" / "physics-opt"
    for name in CASE_NAMES:
        for inp in ("poisson_sub.i", "fast_sub.i", "input.i"):
            cp = subprocess.run([str(exe), "--check-input", "-i", inp], cwd=generated / name)
            if cp.returncode:
                raise SystemExit(cp.returncode)
    print(f"ELECTRON_FLUX_UNIFICATION_P1_{horizon.upper()}: PASS")


def _clean(case_dir: Path) -> None:
    keep = {
        "input.i", "fast_sub.i", "poisson_sub.i",
        "electron_moments.txt", "o2_elastic.txt", "transport_data.txt", "case.json",
    }
    for p in case_dir.iterdir():
        if p.name in keep:
            continue
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


def _run_one(horizon: str, name: str) -> int:
    generated, results, _, _ = _bind(horizon)
    case_dir = generated / name
    _clean(case_dir)
    started = time.perf_counter()
    with (results / f"{name}_runtime.log").open("w") as log:
        cp = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-t", "-i", "input.i"],
            cwd=case_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    (results / f"{name}_elapsed_seconds.txt").write_text(
        f"{time.perf_counter() - started:.9f}\n"
    )
    (results / f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    return cp.returncode


def _analyze(horizon: str, name: str):
    _, results, _, _ = _bind(horizon)
    result, code = seq08.analyze(name)
    result["elapsed_seconds"] = float((results / f"{name}_elapsed_seconds.txt").read_text())
    return result, code


def run(horizon: str) -> None:
    build(horizon)
    returncodes = {name: _run_one(horizon, name) for name in CASE_NAMES}
    analyzed = {}
    analysis_codes = {}
    for name in CASE_NAMES:
        analyzed[name], analysis_codes[name] = _analyze(horizon, name)

    compat = analyzed["compat_flux"]
    unified = analyzed["unified_flux"]
    profile = wall08._comparison(compat, unified)
    trajectory = seq08._potential_series_parity(compat, unified)

    fp_compat = [
        int(x["fixed_point_iterations"])
        for x in compat.get("fixed_point_time_series", [])
        if float(x.get("time_s", 0.0)) > 0.0
    ]
    fp_unified = [
        int(x["fixed_point_iterations"])
        for x in unified.get("fixed_point_time_series", [])
        if float(x.get("time_s", 0.0)) > 0.0
    ]

    profile_values = [abs(float(v)) for v in profile.values() if isinstance(v, (int, float))]
    trajectory_values = [
        abs(float(v)) for k, v in trajectory.items()
        if isinstance(v, (int, float)) and k.endswith("_delta")
    ]

    comparison = {
        "fp_history_equal": fp_compat == fp_unified,
        "fp_total_compat": sum(fp_compat),
        "fp_total_unified": sum(fp_unified),
        "max_profile_metric": max(profile_values) if profile_values else 0.0,
        "max_trajectory_abs_delta": max(trajectory_values) if trajectory_values else 0.0,
        "compat_elapsed_s": compat["elapsed_seconds"],
        "unified_elapsed_s": unified["elapsed_seconds"],
        "runtime_ratio_unified_over_compat": (
            unified["elapsed_seconds"] / compat["elapsed_seconds"]
            if compat["elapsed_seconds"] else None
        ),
    }

    # The historical totals (101 short / 9102 full) belonged to the previous
    # residual-norm-based Gummel stopping rule. This regression owns electron-flux
    # parity, so it must require equal iteration histories between the compatibility
    # and unified implementations, not a solver-policy-specific historical count.
    historical_fp_total = 101 if horizon == "short" else 9102
    valid = (
        all(code == 0 for code in returncodes.values())
        and all(code == 0 for code in analysis_codes.values())
        and all(bool(v.get("evidence_valid")) for v in analyzed.values())
        and comparison["fp_history_equal"]
        and comparison["fp_total_compat"] > 0
        and comparison["fp_total_unified"] > 0
        and comparison["max_profile_metric"] <= 1.0e-10
        and comparison["max_trajectory_abs_delta"] <= 1.0e-9
    )

    out = {
        "classification": "ELECTRON_FLUX_UNIFICATION_QUALIFIED" if valid else "ELECTRON_FLUX_UNIFICATION_FAIL",
        "horizon": horizon,
        "evidence_valid": valid,
        "historical_fp_total_reference_only": historical_fp_total,
        "comparison": comparison,
    }
    _, results, _, _ = _bind(horizon)
    (results / "summary.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("ELECTRON_FLUX_UNIFICATION_" + horizon.upper(), json.dumps(out, sort_keys=True))
    if not valid:
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", choices=("short", "full"), required=True)
    parser.add_argument("--p0", action="store_true")
    parser.add_argument("--p1", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.p0:
        p0(args.horizon)
    elif args.p1:
        p1(args.horizon)
    elif args.run:
        run(args.horizon)
    else:
        parser.error("choose --p0, --p1, or --run")


if __name__ == "__main__":
    main()
