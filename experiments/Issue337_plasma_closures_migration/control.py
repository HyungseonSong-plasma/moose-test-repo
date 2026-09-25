#!/usr/bin/env python3
"""Closure migration parity for the qualified Gen34 plasma case.

Controlled change:
  A: legacy individual closure Material blocks
  B: user-facing [PlasmaClosures] composition blocks

Both lanes use the already-qualified GummelIterationAction. Physics kernels,
BCs, solver settings, clocks, electron-response correction, transfers, and
output policy are otherwise unchanged.
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

from experiments.Issue310_fp_acceleration import control_seq34_relax2x_reference_input as gen34
from experiments.Issue310_fp_acceleration import control_seq08 as seq08
from experiments.Issue306_heavy_charge_motion import wall08_control as wall08
from experiments.Issue336_gummel_action_parity import control as g336
from physics_harness.adapters.moose import blocks as mb

CASE_NAMES = ("legacy_closures", "plasma_closures")
PAIR_ORDERS = {
    "pair_ab": CASE_NAMES,
    "pair_ba": tuple(reversed(CASE_NAMES)),
}
DPHI_TOL = 1.0e-6

BASE_SPEC = {
    "name": "plasma_closures_migration",
    "role": "optimized",
    "bandwidth": 5,
    "relaxation_factor": 0.45,
    "custom_convergence": True,
    "delta_phi_abs_tol": DPHI_TOL,
    "fp_algorithm": "steffensen",
    "compute_scaling_once": True,
    "suppress_fp_anchor_output": True,
    "vector_profiles_final_only": True,
}


def _paths(horizon: str) -> tuple[Path, Path, int, float]:
    if horizon == "short":
        cycles = 1
    elif horizon == "full":
        cycles = 88
    else:
        raise ValueError(horizon)
    return (
        ROOT / f"generated_{horizon}",
        ROOT / f"results_{horizon}",
        cycles,
        400.0 * cycles,
    )


def _bind(horizon: str) -> tuple[Path, Path, int, float]:
    generated, results, cycles, final_tau = _paths(horizon)

    gen34.HEAVY_CYCLES = cycles
    gen34.FINAL_TAU = final_tau
    gen34._bind_clock()

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


def _electron_closure_block() -> str:
    return """[PlasmaClosures]
  [electron]
    create_electron_closure = true
    create_electron_kinetics = true
    create_heavy_transport = false
    create_charge_density = false

    normalized_electron_density = electron_density_hat
    normalized_electron_energy_density = n_epsilon
    electron_energy_reference_eV = 5.73276

    gas_pressure = p_gas
    gas_temperature = T_g
    electron_transport_table_file = electron_moments.txt
    electron_transport_bounds_policy = error

    electron_mean_energy_output = mean_en_solved
    electron_temperature_output = electron_temperature_K
    neutral_number_density_output = neutral_number_density
    electron_reduced_mobility_output = electron_reduced_mobility
    electron_reduced_diffusion_output = electron_reduced_diffusion
    electron_mobility_output = electron_mobility
    electron_diffusion_output = electron_diffusion
    electron_energy_mobility_output = electron_energy_mobility
    electron_energy_diffusion_output = electron_energy_diffusion

    electron_number_density = electron_density_m3
    electron_impact_rate_table_files = 'o2_elastic.txt'
    electron_impact_target_molar_concentrations = 'c_O2'
    electron_impact_reaction_progress_names = 'R_elastic_O2'
  []
[]"""


def _heavy_closure_block() -> str:
    return """[PlasmaClosures]
  [heavy]
    create_electron_closure = false
    create_electron_kinetics = false
    create_heavy_transport = true
    create_charge_density = false

    heavy_species_temperature = T_g
    heavy_species_pressure = p_gas
    electron_temperature = electron_temperature_K
    electron_number_density = electron_density_fast

    heavy_transport_data_file = transport_data.txt
    heavy_species = 'O2 O2s O2p O Om Op Os'
    heavy_mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'

    heavy_mixture_diffusion_names =
      'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    heavy_thermal_diffusion_names =
      'D_T_O2 D_T_O2s D_T_O2p D_T_O D_T_Om D_T_Op D_T_Os'
    heavy_thermal_diffusion_ratio_names =
      'kT_O2 kT_O2s kT_O2p kT_O kT_Om kT_Op kT_Os'
  []
[]"""


def _charge_closure_block() -> str:
    return """[PlasmaClosures]
  [charge]
    create_electron_closure = false
    create_electron_kinetics = false
    create_heavy_transport = false
    create_charge_density = true

    mixture_density = rho_const
    electron_number_density = electron_density_m3

    charged_species_ids = 'O2p Om Op'
    charged_species_mass_fractions = 'w_O2p_frozen w_Om_frozen w_Op_frozen'
    charged_species_molar_masses = '0.032 0.016 0.016'
    charged_species_charge_numbers = '1 -1 1'
  []
[]"""


def _migrate_fast(text: str) -> str:
    for path in (
        "FunctorMaterials/mean_energy_bridge",
        "FunctorMaterials/electron_transport",
        "FunctorMaterials/elastic_o2_rate",
    ):
        text = mb.remove_block(text, path)
    return mb.append_top_level_block(text, _electron_closure_block())


def _migrate_parent(text: str) -> str:
    text = mb.remove_block(text, "FunctorMaterials/heavy_transport")
    return mb.append_top_level_block(text, _heavy_closure_block())


def _migrate_poisson(text: str) -> str:
    text = mb.remove_block(text, "FunctorMaterials/plasma_charge")
    return mb.append_top_level_block(text, _charge_closure_block())


def _strip_legacy_fast(text: str) -> str:
    for path in (
        "FunctorMaterials/mean_energy_bridge",
        "FunctorMaterials/electron_transport",
        "FunctorMaterials/elastic_o2_rate",
    ):
        text = mb.remove_block(text, path)
    return text.strip()


def _strip_legacy_parent(text: str) -> str:
    return mb.remove_block(text, "FunctorMaterials/heavy_transport").strip()


def _strip_legacy_poisson(text: str) -> str:
    return mb.remove_block(text, "FunctorMaterials/plasma_charge").strip()


def _strip_migrated(text: str, child: str) -> str:
    return mb.remove_block(text, f"PlasmaClosures/{child}").strip()


def build(horizon: str, clean: bool = True) -> None:
    generated, results, cycles, final_tau = _bind(horizon)
    if clean:
        shutil.rmtree(generated, ignore_errors=True)
        shutil.rmtree(results, ignore_errors=True)
    generated.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)

    parent, fast, poisson, params = gen34._optimized_inputs(dict(BASE_SPEC))
    # Use the already-qualified Gummel Action in both migration lanes.
    fast = g336._actionize(fast)

    migrated_parent = _migrate_parent(parent)
    migrated_fast = _migrate_fast(fast)
    migrated_poisson = _migrate_poisson(poisson)

    cases = {
        "legacy_closures": (parent, fast, poisson),
        "plasma_closures": (migrated_parent, migrated_fast, migrated_poisson),
    }

    for name, (case_parent, case_fast, case_poisson) in cases.items():
        d = generated / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.i").write_text(case_parent, encoding="utf-8")
        (d / "fast_sub.i").write_text(case_fast, encoding="utf-8")
        (d / "poisson_sub.i").write_text(case_poisson, encoding="utf-8")
        shutil.copy2(g336.g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g336.g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g336.g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(
            json.dumps(
                {
                    **params,
                    "name": name,
                    "phase": "plasma_closures_migration",
                    "horizon": horizon,
                    "heavy_cycles": cycles,
                    "electron_steps": 4 * cycles,
                    "final_tau": final_tau,
                    "closure_architecture": name,
                    "gummel_architecture": "GummelIterationAction",
                    "fixed_point_algorithm": "steffensen",
                    "relaxation_factor": 0.45,
                    "bandwidth": 5,
                    "delta_phi_abs_tol": DPHI_TOL,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def p0(horizon: str) -> None:
    build(horizon)
    generated, _, cycles, _ = _bind(horizon)

    legacy = generated / "legacy_closures"
    migrated = generated / "plasma_closures"

    legacy_parent = (legacy / "input.i").read_text()
    migrated_parent = (migrated / "input.i").read_text()
    legacy_fast = (legacy / "fast_sub.i").read_text()
    migrated_fast = (migrated / "fast_sub.i").read_text()
    legacy_poisson = (legacy / "poisson_sub.i").read_text()
    migrated_poisson = (migrated / "poisson_sub.i").read_text()

    # Remove only the closure-construction surface; all remaining input text
    # must remain structurally identical.
    assert _strip_legacy_parent(legacy_parent) == _strip_migrated(migrated_parent, "heavy")
    assert _strip_legacy_fast(legacy_fast) == _strip_migrated(migrated_fast, "electron")
    assert _strip_legacy_poisson(legacy_poisson) == _strip_migrated(migrated_poisson, "charge")

    # Electron closure migration.
    assert "type = PhysicsElectronMeanEnergyMaterial" in legacy_fast
    assert "type = PhysicsElectronTransportLookupMaterial" in legacy_fast
    assert "type = PhysicsElectronImpactRateMaterial" in legacy_fast
    assert "type = PhysicsElectronMeanEnergyMaterial" not in migrated_fast
    assert "type = PhysicsElectronTransportLookupMaterial" not in migrated_fast
    assert "type = PhysicsElectronImpactRateMaterial" not in migrated_fast
    assert "[PlasmaClosures]" in migrated_fast
    assert "electron_mean_energy_output = mean_en_solved" in migrated_fast
    assert "electron_impact_reaction_progress_names = 'R_elastic_O2'" in migrated_fast

    # Heavy transport migration.
    assert "type = PhysicsThermalDiffusionMaterial" in legacy_parent
    assert "type = PhysicsThermalDiffusionMaterial" not in migrated_parent
    assert "create_heavy_transport = true" in migrated_parent
    assert "heavy_species = 'O2 O2s O2p O Om Op Os'" in migrated_parent

    # Charge closure migration.
    assert "type = PhysicsPlasmaChargeDensityMaterial" in legacy_poisson
    assert "type = PhysicsPlasmaChargeDensityMaterial" not in migrated_poisson
    assert "create_charge_density = true" in migrated_poisson
    assert "charged_species_ids = 'O2p Om Op'" in migrated_poisson

    # Both lanes retain the same qualified Gummel coupling and banded Poisson response.
    for fast_text in (legacy_fast, migrated_fast):
        assert "[GummelIteration]" in fast_text
        assert "fixed_point_algorithm = 'steffensen'" in fast_text
        assert "multiapp_fixed_point_convergence = gummel_delta_phi" in fast_text
    for poisson_text in (legacy_poisson, migrated_poisson):
        assert "type = FVElectronResponseBandedCorrection" in poisson_text
        assert "bandwidth = 5" in poisson_text

    print(f"PLASMA_CLOSURES_MIGRATION_P0_{horizon.upper()}: PASS cycles={cycles}")


def p1(horizon: str) -> None:
    build(horizon)
    generated, _, _, _ = _bind(horizon)
    exe = REPO / "physics_app" / "physics-opt"
    if not exe.exists():
        raise SystemExit("physics-opt missing")

    for name in CASE_NAMES:
        for input_name in ("poisson_sub.i", "fast_sub.i", "input.i"):
            cp = subprocess.run(
                [str(exe), "--check-input", "-i", input_name],
                cwd=generated / name,
                check=False,
            )
            if cp.returncode:
                raise SystemExit(cp.returncode)

    print(f"PLASMA_CLOSURES_MIGRATION_P1_{horizon.upper()}: PASS")


def _clean_runtime_outputs(case_dir: Path) -> None:
    keep = {
        "input.i",
        "fast_sub.i",
        "poisson_sub.i",
        "electron_moments.txt",
        "o2_elastic.txt",
        "transport_data.txt",
        "case.json",
    }
    for item in case_dir.iterdir():
        if item.name in keep:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _run_one(horizon: str, name: str) -> int:
    generated, results, _, _ = _bind(horizon)
    case_dir = generated / name
    _clean_runtime_outputs(case_dir)
    log = results / f"{name}_runtime.log"

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

    (results / f"{name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    (results / f"{name}_returncode.txt").write_text(f"{cp.returncode}\n")
    return cp.returncode


def _analyze(horizon: str, name: str) -> tuple[dict[str, object], int]:
    _, results, _, _ = _bind(horizon)
    result, code = seq08.analyze(name)
    result["phase"] = "plasma_closures_migration"
    result["horizon"] = horizon
    result["closure_architecture"] = name
    result["elapsed_seconds"] = float(
        (results / f"{name}_elapsed_seconds.txt").read_text()
    )
    return result, code


def _compare(legacy: dict[str, object], migrated: dict[str, object]) -> dict[str, object]:
    profile = wall08._comparison(legacy, migrated)
    trajectory = seq08._potential_series_parity(legacy, migrated)

    fp_legacy = [
        int(x["fixed_point_iterations"])
        for x in legacy.get("fixed_point_time_series", [])
        if float(x.get("time_s", 0.0)) > 0.0
    ]
    fp_migrated = [
        int(x["fixed_point_iterations"])
        for x in migrated.get("fixed_point_time_series", [])
        if float(x.get("time_s", 0.0)) > 0.0
    ]

    profile_metrics = [
        abs(float(v)) for v in profile.values() if isinstance(v, (int, float))
    ]
    trajectory_metrics = [
        abs(float(v))
        for key, v in trajectory.items()
        if isinstance(v, (int, float)) and key.endswith("_delta")
    ]

    legacy_time = float(legacy["elapsed_seconds"])
    migrated_time = float(migrated["elapsed_seconds"])

    return {
        "fp_history_legacy": fp_legacy,
        "fp_history_migrated": fp_migrated,
        "fp_history_equal": fp_legacy == fp_migrated,
        "fp_total_legacy": sum(fp_legacy),
        "fp_total_migrated": sum(fp_migrated),
        "max_profile_metric": max(profile_metrics) if profile_metrics else 0.0,
        "max_trajectory_abs_delta": max(trajectory_metrics) if trajectory_metrics else 0.0,
        "profile": profile,
        "trajectory": trajectory,
        "legacy_elapsed_s": legacy_time,
        "migrated_elapsed_s": migrated_time,
        "runtime_ratio_migrated_over_legacy": (
            migrated_time / legacy_time if legacy_time else None
        ),
    }


def run_pair(horizon: str, pair: str) -> dict[str, object]:
    generated, results, cycles, final_tau = _bind(horizon)
    if not generated.exists():
        build(horizon)

    return_codes: dict[str, int] = {}
    for name in PAIR_ORDERS[pair]:
        return_codes[name] = _run_one(horizon, name)

    runs: dict[str, dict[str, object]] = {}
    analysis_codes: dict[str, int] = {}
    for name in CASE_NAMES:
        runs[name], analysis_codes[name] = _analyze(horizon, name)

    comparison = _compare(runs["legacy_closures"], runs["plasma_closures"])

    valid = (
        all(code == 0 for code in return_codes.values())
        and all(code == 0 for code in analysis_codes.values())
        and all(bool(result.get("evidence_valid")) for result in runs.values())
        and bool(comparison["fp_history_equal"])
        and float(comparison["max_profile_metric"]) <= 1.0e-10
        and float(comparison["max_trajectory_abs_delta"]) <= 1.0e-9
    )

    out = {
        "phase": "plasma_closures_migration",
        "horizon": horizon,
        "pair": pair,
        "heavy_cycles": cycles,
        "final_tau": final_tau,
        "classification": (
            "PLASMA_CLOSURES_SCIENTIFIC_PARITY_PASS"
            if valid
            else "PLASMA_CLOSURES_PARITY_FAIL"
        ),
        "evidence_valid": valid,
        "comparison": comparison,
        "runs": runs,
    }

    (results / f"{pair}_result.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print(
        f"PLASMA_CLOSURES_MIGRATION_{horizon.upper()}_{pair.upper()}",
        json.dumps(comparison, sort_keys=True),
    )

    if not valid:
        raise SystemExit(2)

    return out


def run(horizon: str) -> None:
    build(horizon)

    if horizon == "short":
        run_pair(horizon, "pair_ab")
        return

    pairs = [run_pair(horizon, "pair_ab"), run_pair(horizon, "pair_ba")]
    ratios = [
        float(pair["comparison"]["runtime_ratio_migrated_over_legacy"])
        for pair in pairs
    ]
    geometric_mean_ratio = (ratios[0] * ratios[1]) ** 0.5
    exact_fp = all(bool(pair["comparison"]["fp_history_equal"]) for pair in pairs)
    valid = all(bool(pair["evidence_valid"]) for pair in pairs)

    summary = {
        "phase": "plasma_closures_migration",
        "horizon": "full",
        "classification": (
            "PLASMA_CLOSURES_FULL_QUALIFIED"
            if valid and exact_fp
            else "PLASMA_CLOSURES_FULL_FAIL"
        ),
        "evidence_valid": valid,
        "exact_fp_history_both_orders": exact_fp,
        "geometric_mean_runtime_ratio_migrated_over_legacy": geometric_mean_ratio,
        "runtime_regression_fraction": geometric_mean_ratio - 1.0,
        "pairs": {pair["pair"]: pair for pair in pairs},
    }

    (_, results, _, _) = _bind("full")
    (results / "full_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )

    print(
        "PLASMA_CLOSURES_MIGRATION_FULL_SUMMARY",
        json.dumps(summary, sort_keys=True),
    )

    if summary["classification"] != "PLASMA_CLOSURES_FULL_QUALIFIED":
        raise SystemExit(3)


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
