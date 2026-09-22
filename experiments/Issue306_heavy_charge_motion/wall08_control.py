#!/usr/bin/env python3
"""Issue #306 Sequence 08: thermal-heavy-wall timestep-ratio study with sheath-suppressed electron wall loss.

Physics held fixed:
  * electron chi_e = 100
  * right wall = thermal charged-heavy loss + signed migration
  * electron wall = right-only 1/2 particle and 5/6 energy closure multiplied by a Boltzmann sheath factor
  * left = 20 sccm pure-O2 inlet
  * chemistry OFF, RF heating OFF

Only heavy timestep changes while the final physical horizon is fixed:
  heavy/electron dt ratio = 2 / 4 / 8
  chi_h = 200 / 400 / 800
  heavy cycles = 300 / 150 / 75
  fast steps per heavy cycle = 2 / 4 / 8
  total fast steps = 600 for every case
  T_final = 60000 tau_epsilon(initial)

This isolates heavy-update cadence while testing whether a sheath-suppressed electron wall prevents the long-time charge/energy drift seen in Sequence 07.
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
GENERATED = ROOT / "generated_wall08"
RESULTS = ROOT / "results_wall08"

CHI_E = 100.0
FINAL_TAU = 60000.0
RATIOS = (2, 4, 8)
SPECS = tuple(
    {
        "name": f"sheath_ratio{ratio}",
        "mode": "thermal",
        "chi": CHI_E,
        "chi_h": CHI_E * ratio,
        "heavy_cycles": int(FINAL_TAU / (CHI_E * ratio)),
        "ratio": ratio,
        "fp_max": 3000,
    }
    for ratio in RATIOS
)
CASE_NAMES = tuple(str(x["name"]) for x in SPECS)


@contextmanager
def _clock(spec: dict[str, object]):
    old_chi_h = base.CHI_H
    old_cycles = base.HEAVY_CYCLES
    old_final_tau = base.FINAL_TAU
    try:
        base.CHI_H = float(spec["chi_h"])
        base.HEAVY_CYCLES = int(spec["heavy_cycles"])
        base.FINAL_TAU = FINAL_TAU
        yield
    finally:
        base.CHI_H = old_chi_h
        base.HEAVY_CYCLES = old_cycles
        base.FINAL_TAU = old_final_tau


def _params(spec: dict[str, object]) -> dict[str, object]:
    with _clock(spec):
        p = wall03._params(spec)
    p["heavy_to_electron_dt_ratio"] = int(spec["ratio"])
    return p


def _apply_electron_sheath_factor(text: str) -> str:
    """Replace only the electron wall owners using standard MOOSE input objects.

    Sequence 07 baseline:
      Gamma_e,out = 0.5*c_e*vbar
      Gamma_eps,out = (5/6)*n_epsilon*vbar

    Sequence 08:
      both fluxes are multiplied by
        exp(-max(phi_plasma-phi_wall, 0)/T_e),  phi_wall = 0,
      with T_e[eV] = (2/3)*mean_energy[eV].

    max(phi,0) is represented as 0.5*(phi+abs(phi)) so the closure stays
    entirely inside ADParsedFunctorMaterial + FVFunctorNeumannBC.
    """
    old_particle_material = """  [thermal_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = thermal_flux_molar_outward
    functor_names = 'log_e mean_en_solved'
    functor_symbols = 'loge mean_ev'
    expression = '0.5*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))'
  []
"""
    new_materials = """  [electron_sheath_factor]
    type = ADParsedFunctorMaterial
    property_name = electron_sheath_factor
    functor_names = 'potential_from_poisson mean_en_solved'
    functor_symbols = 'phi mean_ev'
    expression = 'exp(-(0.5*(phi+abs(phi)))/((2.0/3.0)*mean_ev))'
  []
  [thermal_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = thermal_flux_molar_outward
    functor_names = 'log_e mean_en_solved electron_sheath_factor'
    functor_symbols = 'loge mean_ev sheath'
    expression = '0.5*exp(loge)*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))*sheath'
  []
  [sheath_energy_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = sheath_energy_flux_outward
    functor_names = 'n_epsilon mean_en_solved electron_sheath_factor'
    functor_symbols = 'eps_hat mean_ev sheath'
    expression = '0.83333333333333333*eps_hat*sqrt(16.0*1.602176634e-19*mean_ev/(3.0*pi*9.1093837139e-31))*sheath'
  []
"""
    if text.count(old_particle_material) != 1:
        raise RuntimeError("Sequence-07 electron particle wall material anchor changed")
    text = text.replace(old_particle_material, new_materials, 1)

    old_energy_bc = """  [right_energy_surface_loss]
    type = PhysicsFVElectronEnergyWallFluxBC
    variable = n_epsilon
    boundary = right
    electron_energy_density = n_epsilon
    mean_electron_energy = mean_en_solved
    see_number_flux = zero_flux
    energy_reference_eV = 5.73276
  []
"""
    new_energy_bc = """  [right_energy_surface_loss]
    type = FVFunctorNeumannBC
    variable = n_epsilon
    boundary = right
    functor = sheath_energy_flux_outward
    factor = -1.0
  []
"""
    if text.count(old_energy_bc) != 1:
        raise RuntimeError("Sequence-07 electron energy wall BC anchor changed")
    return text.replace(old_energy_bc, new_energy_bc, 1)


def _render_case(spec: dict[str, object], p: dict[str, object]) -> tuple[str, str, str]:
    with _clock(spec):
        parent = wall03._parent(p)
        fast = _apply_electron_sheath_factor(wall03._fast(p))
        poisson = base._poisson_child()
    return parent, fast, poisson


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
                "issue": 306,
                "sequence": 8,
                "objective": "sheath-suppressed electron-wall heavy timestep sensitivity at equal physical time",
                "chi_e": CHI_E,
                "ratios": list(RATIOS),
                "chi_h": [CHI_E * r for r in RATIOS],
                "heavy_cycles": [int(FINAL_TAU / (CHI_E * r)) for r in RATIOS],
                "total_fast_steps": 600,
                "final_tau": FINAL_TAU,
                "wall_model": "thermal charged-heavy wall loss + signed migration; standard-MOOSE electron sheath suppression",
                "cases": built,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    built = build()
    if tuple(str(x["name"]) for x in built) != CASE_NAMES:
        raise RuntimeError("case ordering mismatch")

    for spec, p in zip(SPECS, built, strict=True):
        ratio = int(spec["ratio"])
        cycles = int(spec["heavy_cycles"])
        case_dir = GENERATED / str(p["name"])
        parent = (case_dir / "input.i").read_text(encoding="utf-8")
        fast = (case_dir / "fast_sub.i").read_text(encoding="utf-8")

        assert float(p["chi_e"]) == CHI_E
        assert float(p["chi_h"]) == CHI_E * ratio
        assert int(p["heavy_cycles"]) == cycles
        assert int(p["fast_steps_per_heavy_cycle"]) == ratio
        assert int(p["fast_steps_total"]) == 600
        assert math.isclose(
            float(p["end_time_tau_epsilon_initial"]),
            FINAL_TAU,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        assert p["positive_ion_surface_model"] == "thermal_sticking"
        assert p["negative_ion_surface_model"] == "thermal_sticking"
        assert f"num_steps = {cycles}" in parent
        assert parent.count("type = PhysicsIonWallFluxMaterial") == 3
        assert parent.count("sticking = 1.0") == 3
        assert "bohm_surface_mass_flux_" not in parent
        assert parent.count("boundaries_to_avoid = 'left right'") == 9
        assert "[electron_sheath_factor]" in fast
        assert "exp(-(0.5*(phi+abs(phi)))/((2.0/3.0)*mean_ev))" in fast
        assert "0.5*exp(loge)" in fast and "*sheath" in fast
        assert "[sheath_energy_surface_flux]" in fast
        assert "0.83333333333333333*eps_hat" in fast
        assert "[right_thermal_surface_loss]" in fast
        assert "[right_energy_surface_loss]" in fast
        assert fast.count("type = FVFunctorNeumannBC") >= 2
        assert "PhysicsFVElectronGroundedSheath" not in fast
        assert "PhysicsFVElectronEnergyWallFluxBC" not in fast

    return {
        "status": "PASS",
        "issue": 306,
        "sequence": 8,
        "chi_e": CHI_E,
        "ratios": list(RATIOS),
        "chi_h": [CHI_E * r for r in RATIOS],
        "heavy_cycles": [int(FINAL_TAU / (CHI_E * r)) for r in RATIOS],
        "total_fast_steps": 600,
        "final_tau": FINAL_TAU,
        "matrix": built,
    }


def p0() -> None:
    print("ISSUE306_WALL08_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{rel}/generated_wall08/{name}/input.i"
        for name in CASE_NAMES
    )
    base._docker(
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    print("ISSUE306_WALL08_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks: list[str] = []
    for name in CASE_NAMES:
        checks.append(
            f"cd /workspace/{rel}/generated_wall08/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i input.i"
        )
        checks.append(
            f"cd /workspace/{rel}/generated_wall08/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i fast_sub.i"
        )
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt; make -C /workspace/physics_app -j2; " + "; ".join(checks)
    )
    print("ISSUE306_WALL08_P2: PASS")


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
    from collections import deque
    with log.open("r", encoding="utf-8", errors="replace") as handle:
        tail = deque(handle, maxlen=400)
    (RESULTS / f"{case_name}_runtime_tail.log").write_text(
        "".join(tail), encoding="utf-8"
    )
    log.unlink(missing_ok=True)
    return 0


def _spec_for_name(case_name: str) -> dict[str, object]:
    return next(spec for spec in SPECS if spec["name"] == case_name)


def analyze(case_name: str) -> tuple[dict[str, object], int]:
    spec = _spec_for_name(case_name)
    p = json.loads((GENERATED / case_name / "case.json").read_text(encoding="utf-8"))
    old_generated, old_results = base.GENERATED, base.RESULTS
    try:
        base.GENERATED = GENERATED
        base.RESULTS = RESULTS
        with _clock(spec):
            result, code = base.analyze_case(case_name)
    finally:
        base.GENERATED = old_generated
        base.RESULTS = old_results

    result.update(
        mode=p["mode"],
        flow_inlet=p["flow_inlet"],
        wall_boundary=p["wall_boundary"],
        positive_ion_surface_model=p["positive_ion_surface_model"],
        heavy_to_electron_dt_ratio=p["heavy_to_electron_dt_ratio"],
        electron_wall_model="standard_moose_half_thermal_times_boltzmann_sheath_factor",
        electron_particle_prefactor=0.5,
        electron_energy_prefactor=5.0 / 6.0,
    )
    return result, code


def run_case(case_name: str) -> None:
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    base._docker(
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos "
        "METHOD=opt PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/wall08_control.py --inner-run {case_name}"
    )
    result, code = analyze(case_name)
    (RESULTS / f"{case_name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE306_WALL08_CASE:", case_name, result["classification"])
    if code:
        raise SystemExit(code)


def _comparison(reference: dict[str, object], trial: dict[str, object]) -> dict[str, float]:
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
    }


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [name for name in CASE_NAMES if name not in found]
    if missing:
        raise RuntimeError(f"missing wall08 result(s): {missing}")

    valid = all(bool(found[name].get("evidence_valid")) for name in CASE_NAMES)
    if not valid:
        return {
            "issue": 306,
            "sequence": 8,
            "classification": "WALL08_INVALID_EVIDENCE",
            "evidence_valid": False,
            "cases": found,
        }

    ref = found["sheath_ratio2"]
    comparisons = {
        "ratio4_vs_ratio2": _comparison(ref, found["sheath_ratio4"]),
        "ratio8_vs_ratio2": _comparison(ref, found["sheath_ratio8"]),
        "ratio8_vs_ratio4": _comparison(
            found["sheath_ratio4"], found["sheath_ratio8"]
        ),
    }
    return {
        "issue": 306,
        "sequence": 8,
        "classification": "SHEATH_THERMAL_HEAVY_DT_RATIO_EVIDENCE_COMPLETE",
        "evidence_valid": True,
        "chi_e": CHI_E,
        "ratios": list(RATIOS),
        "chi_h": [CHI_E * r for r in RATIOS],
        "heavy_cycles": [int(FINAL_TAU / (CHI_E * r)) for r in RATIOS],
        "final_tau": FINAL_TAU,
        "cases": found,
        "comparisons": comparisons,
        "interpretation_guard": (
            "All cases use the same thermal heavy-wall physics, the same sheath-suppressed electron wall, and the same final physical "
            "time. Differences therefore diagnose heavy-update timestep sensitivity."
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
        (RESULTS / "issue306_wall08_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("ISSUE306_WALL08_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
