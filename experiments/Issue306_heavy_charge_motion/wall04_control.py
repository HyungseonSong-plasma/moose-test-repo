#!/usr/bin/env python3
"""Issue #306 Sequence 04: long heavy-relaxation convergence at fixed chi_e=20.

The accepted Sequence-03 COMSOL/right-wall physics is held fixed:
  * left = 20 sccm pure-O2 inlet;
  * right electron particle wall loss = 0.5*n_e*v_e,th;
  * right electron energy wall loss = (5/6)*v_e,th*n_epsilon;
  * right O2+/O+ surface loss = Bohm;
  * right O- surface loss = thermal sticking;
  * all charged heavy species retain signed one-sided wall migration;
  * volumetric chemistry and RF heating remain OFF.

Only the physical heavy-relaxation horizon changes:
  chi_e = 20
  chi_h = 40
  heavy cycles = 10 / 20 / 30
  T_final/tau_epsilon(initial) = 400 / 800 / 1200

Each horizon starts from the identical initial state.  The aggregate compares
raw potential, offset-removed potential, E field, net charge, and charged-heavy
profiles to determine whether the plasma potential approaches a stable profile.
"""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.Issue306_heavy_charge_motion import control as base
from experiments.Issue306_heavy_charge_motion import wall03_control as wall03

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_wall04"
RESULTS = ROOT / "results_wall04"

CHI_E = 20.0
CHI_H = 40.0
CYCLES = (10, 20, 30)
CASE_NAMES = tuple(f"comsol_cycles{cycles}" for cycles in CYCLES)


@contextmanager
def _base_horizon(cycles: int):
    """Temporarily render/analyze with the requested heavy horizon."""
    old_cycles = base.HEAVY_CYCLES
    old_final_tau = base.FINAL_TAU
    try:
        base.HEAVY_CYCLES = cycles
        base.FINAL_TAU = CHI_H * cycles
        yield
    finally:
        base.HEAVY_CYCLES = old_cycles
        base.FINAL_TAU = old_final_tau


def _params(cycles: int) -> dict[str, object]:
    """Construct the fixed-chi COMSOL case for one heavy-cycle horizon."""
    spec = {
        "name": f"comsol_cycles{cycles}",
        "mode": "comsol",
        "chi": CHI_E,
        "fp_max": 600,
    }
    with _base_horizon(cycles):
        p = wall03._params(spec)
    if int(p["heavy_cycles"]) != cycles:
        raise RuntimeError("heavy-cycle parameter mismatch")
    if int(p["fast_steps_per_heavy_cycle"]) != 2:
        raise RuntimeError("chi_e=20 must give two fast steps per heavy step")
    return p


def _render_case(p: dict[str, object]) -> tuple[str, str, str]:
    """Render parent, fast child, and Poisson child at one horizon."""
    cycles = int(p["heavy_cycles"])
    with _base_horizon(cycles):
        parent = wall03._parent(p)
        fast = wall03._fast(p)
        poisson = base._poisson_child()
    return parent, fast, poisson


def build(clean: bool = True) -> list[dict[str, object]]:
    """Generate the 10/20/30-cycle fixed-chi matrix."""
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    built: list[dict[str, object]] = []
    for cycles in CYCLES:
        p = _params(cycles)
        case_dir = GENERATED / str(p["name"])
        case_dir.mkdir(parents=True, exist_ok=True)

        parent, fast, poisson = _render_case(p)
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
                "issue": 306,
                "sequence": 4,
                "objective": (
                    "observe long-time potential-profile convergence at fixed "
                    "chi_e=20 and COMSOL/right-wall physics"
                ),
                "chi_e": CHI_E,
                "chi_h": CHI_H,
                "heavy_cycles": list(CYCLES),
                "final_tau": [CHI_H * c for c in CYCLES],
                "fast_steps_per_heavy_cycle": 2,
                "boundary_contract": {
                    "left": "20 sccm pure-O2 inlet",
                    "right": (
                        "electron 1/2 thermal wall + 5/6 energy wall + "
                        "O2+/O+ Bohm + O- thermal sticking + signed ion migration"
                    ),
                },
                "cases": built,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    """Verify that heavy horizon is the only case-to-case axis."""
    built = build()
    if tuple(str(x["name"]) for x in built) != CASE_NAMES:
        raise RuntimeError("case ordering mismatch")

    reference_parent_physics: str | None = None
    for cycles, p in zip(CYCLES, built, strict=True):
        case_dir = GENERATED / str(p["name"])
        parent = (case_dir / "input.i").read_text(encoding="utf-8")
        fast = (case_dir / "fast_sub.i").read_text(encoding="utf-8")

        assert float(p["chi_e"]) == CHI_E
        assert float(p["chi_h"]) == CHI_H
        assert int(p["heavy_cycles"]) == cycles
        assert int(p["fast_steps_per_heavy_cycle"]) == 2
        assert int(p["fast_steps_total"]) == 2 * cycles
        assert math.isclose(
            float(p["end_time_tau_epsilon_initial"]),
            CHI_H * cycles,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        assert f"num_steps = {cycles}" in parent
        assert "boundary = left" in parent
        assert "type = WCNSFVMassFluxBC" in parent
        assert "type = INSFVOutletPressureBC" in parent
        assert "boundary = right" in parent
        assert parent.count("bohm_surface_mass_flux_") >= 4
        assert parent.count("boundaries_to_avoid = 'left right'") == 9
        assert "0.5*exp(loge)" in fast
        assert "[right_thermal_surface_loss]" in fast
        assert "[right_energy_surface_loss]" in fast

        # Remove only clock strings before comparing the rendered parent physics.
        normalized = parent
        for value in (
            f"dt = {float(p['dt_h_s']):.17g}",
            f"dtmin = {float(p['dt_h_s']):.17g}",
            f"dtmax = {float(p['dt_h_s']):.17g}",
            f"end_time = {float(p['end_time_s']):.17g}",
            f"num_steps = {cycles}",
        ):
            normalized = normalized.replace(value, "<CLOCK>")
        if reference_parent_physics is None:
            reference_parent_physics = normalized
        elif normalized != reference_parent_physics:
            raise RuntimeError("parent physics changed across heavy-cycle horizons")

    return {
        "status": "PASS",
        "issue": 306,
        "sequence": 4,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": list(CYCLES),
        "final_tau": [CHI_H * c for c in CYCLES],
        "matrix": built,
    }


def p0() -> None:
    summary = static_contract()
    print("ISSUE306_WALL04_P0: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))


def p1() -> None:
    build()
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{ROOT.relative_to(REPO)}/generated_wall04/{name}/input.i"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    base._docker(script)
    print("ISSUE306_WALL04_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_wall04/{name} && "
            f"/workspace/physics_app/physics-opt --check-input -i input.i "
            f"> /workspace/{rel}/results_wall04/{name}_parent_p2.log 2>&1"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_wall04/{name} && "
            f"/workspace/physics_app/physics-opt --check-input -i fast_sub.i "
            f"> /workspace/{rel}/results_wall04/{name}_fast_p2.log 2>&1"
        )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        f"mkdir -p /workspace/{rel}/results_wall04; "
        "make -C /workspace/physics_app -j2; test -x /workspace/physics_app/physics-opt; "
        + "; ".join(checks)
    )
    base._docker(script)
    print("ISSUE306_WALL04_P2: PASS")


def inner_run(case_name: str) -> int:
    """Execute one generated long-horizon case inside the build-base container."""
    if case_name not in CASE_NAMES:
        raise SystemExit(f"unknown case {case_name}")
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
    return 0


def _analyze_case(case_name: str) -> tuple[dict[str, object], int]:
    """Reuse accepted analysis with the case-specific heavy-cycle count."""
    p = json.loads((GENERATED / case_name / "case.json").read_text(encoding="utf-8"))
    cycles = int(p["heavy_cycles"])
    old_generated, old_results = base.GENERATED, base.RESULTS
    try:
        base.GENERATED = GENERATED
        base.RESULTS = RESULTS
        with _base_horizon(cycles):
            result, code = base.analyze_case(case_name)
    finally:
        base.GENERATED = old_generated
        base.RESULTS = old_results

    result["mode"] = p["mode"]
    result["flow_inlet"] = p["flow_inlet"]
    result["wall_boundary"] = p["wall_boundary"]
    result["positive_ion_surface_model"] = p["positive_ion_surface_model"]

    rows = base._rows(GENERATED / case_name / "input_step_csv.csv")
    history: list[dict[str, float]] = []
    for index, row in enumerate(rows):
        history.append(
            {
                "cycle": float(index),
                "time_tau": float(row["time"]) / base.prepare.tau_epsilon(),
                "phi_avg_V": float(row["phi_avg"]),
                "phi_min_V": float(row["phi_min"]),
                "phi_max_V": float(row["phi_max"]),
                "net_charge_integral_C_m2": float(row["net_charge_integral"]),
                "heavy_charge_integral_C_m2": float(row["heavy_charge_integral"]),
            }
        )
    result["history"] = history

    if code == 0 and rows:
        final = rows[-1]
        result["right_wall_rates"] = {
            species: {
                "surface_rate_signed": float(final[f"right_{species}_surface_rate"]),
                "migration_rate_signed": float(final[f"right_{species}_migration_rate"]),
            }
            for species in wall03.ALL_CHARGED
        }

    if code == 0:
        profile = result["final_profile"]
        dx = 0.01 / len(profile)
        eps0 = 8.8541878128e-12
        result["charge_moment_potential_V"] = sum(
            (0.01 - float(row["x"])) * float(row["net_charge_C_m3"]) * dx / eps0
            for row in profile
        )
    return result, code


def run_case(case_name: str) -> None:
    """Run and analyze exactly one matrix horizon."""
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/wall04_control.py --inner-run {case_name}"
    )
    base._docker(script)
    result, code = _analyze_case(case_name)
    (RESULTS / f"{case_name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE306_WALL04_CASE:", case_name, result["classification"])
    if code:
        raise SystemExit(code)


def _comparison(
    reference: dict[str, object], trial: dict[str, object]
) -> dict[str, float]:
    """Compare two final states, preserving raw and offset-free potential metrics."""
    a = reference["final_profile"]
    b = trial["final_profile"]
    return {
        "electron_density_einf": base._profile_error(a, b, "electron_density"),
        "mean_energy_einf": base._profile_error(a, b, "mean_energy_eV"),
        "w_O2p_einf": base._profile_error(a, b, "w_O2p"),
        "w_Om_einf": base._profile_error(a, b, "w_Om"),
        "w_Op_einf": base._profile_error(a, b, "w_Op"),
        "net_charge_einf": base._profile_error(a, b, "net_charge_C_m3"),
        "raw_potential_einf": base._profile_error(a, b, "potential"),
        **base._offset_shape(a, b),
        "phi_avg_change_V": (
            float(trial["final_phi_avg_V"]) - float(reference["final_phi_avg_V"])
        ),
        "net_charge_integral_change_C_m2": (
            float(trial["final_net_charge_integral_C_m2"])
            - float(reference["final_net_charge_integral_C_m2"])
        ),
        "charge_moment_potential_change_V": (
            float(trial["charge_moment_potential_V"])
            - float(reference["charge_moment_potential_V"])
        ),
    }


def aggregate(root: Path) -> dict[str, object]:
    """Aggregate 10/20/30-cycle convergence evidence."""
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [name for name in CASE_NAMES if name not in found]
    if missing:
        raise RuntimeError(f"missing wall04 result(s): {missing}")
    if not all(bool(found[name].get("evidence_valid")) for name in CASE_NAMES):
        return {
            "issue": 306,
            "sequence": 4,
            "classification": "WALL04_INVALID_EVIDENCE",
            "evidence_valid": False,
            "cases": found,
        }

    c10 = found["comsol_cycles10"]
    c20 = found["comsol_cycles20"]
    c30 = found["comsol_cycles30"]
    comparisons = {
        "cycles20_vs_10": _comparison(c10, c20),
        "cycles30_vs_20": _comparison(c20, c30),
        "cycles30_vs_10": _comparison(c10, c30),
    }

    d10_20 = abs(float(comparisons["cycles20_vs_10"]["phi_avg_change_V"]))
    d20_30 = abs(float(comparisons["cycles30_vs_20"]["phi_avg_change_V"]))
    return {
        "issue": 306,
        "sequence": 4,
        "classification": "LONG_HEAVY_RELAXATION_EVIDENCE_COMPLETE",
        "evidence_valid": True,
        "chi_e": CHI_E,
        "chi_h": CHI_H,
        "heavy_cycles": list(CYCLES),
        "final_tau": [CHI_H * c for c in CYCLES],
        "cases": found,
        "comparisons": comparisons,
        "potential_increment_ratio_30_20_over_20_10": (
            d20_30 / max(d10_20, 1.0e-30)
        ),
        "interpretation_guard": (
            "A decreasing 20->30 potential/profile increment relative to 10->20 "
            "supports approach toward a stable heavy-relaxation state; it is not "
            "by itself a proof of asymptotic convergence."
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
        evidence_root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
        if not evidence_root:
            raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
        summary = aggregate(Path(evidence_root))
        (RESULTS / "issue306_wall04_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE306_WALL04_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
