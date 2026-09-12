#!/usr/bin/env python3
"""Governed bounded final Stage-6 integration acceptance for Issue #27.

This runner owns the first closure-grade one-step production regression that
combines the already accepted conducting-wall, finite-SEE, solved electron-
energy, and Stage-5 volumetric-chemistry contracts.  It does not establish
multi-step A7 anomaly resolution, dynamic dielectric physics, RF/Maxwell
closure, or Integrated Physics Accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue27_surface_reactions import final_stage6
from experiments.Issue27_surface_reactions.controlled_wall import combined, see as a8
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import THERMAL_PP
from experiments.historical_recipe_support import issue26_energy_chain as energy
from physics_harness.execution.cases import stage_case, validate_case_references

ROOT = Path(__file__).resolve().parents[2]
SOURCE = s5r.SOURCE

# No new acceptance envelopes are introduced here.  Reuse the accepted
# Stage-5 coupled-balance and Stage-6 A8 algebraic/runtime surfaces.
COUPLED_BALANCE_REL_TOL = s5r.GENERIC_COUPLED_BALANCE_REL_TOL
RUNTIME_REL_TOL = 1.0e-3
ALGEBRAIC_REL_TOL = 1.0e-10
COMPOSITION_ABS_TOL = 1.0e-8
ELECTRON_DENSITY_FLOOR = -1.0e-12
ELEMENTARY_CHARGE_C = 1.602176634e-19


class Issue27Stage6AcceptanceError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel_defect(measured: float, expected: float, *components: float) -> float:
    scale = max(abs(expected), *(abs(value) for value in components), 1.0e-300)
    return abs(measured - expected) / scale


def _physical(value: float) -> float:
    return abs(float(value))


def _construction() -> tuple[str, dict[str, Any]]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    text, meta = final_stage6.build_stage6_final_input(base)
    audit = final_stage6.audit_stage6_final_input(text)
    if audit["status"] != "PASS":
        raise Issue27Stage6AcceptanceError(
            f"final Stage-6 construction audit failed: {audit['failed_checks']}"
        )
    return text, meta


def _stage(case_dir: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
    text, meta = _construction()
    staged = stage_case(
        SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    s5r._copy_runtime_assets(case_dir)
    references = validate_case_references(case_dir)
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return text, meta, {"staging": staged, "references": references}


def _wall_observables(row: Mapping[str, str]) -> dict[str, Any]:
    neutral = {
        species: _physical(s5r._num(row, combined._neutral_names(species)[3]))
        for species in combined.NEUTRALS
    }
    charged: dict[str, Any] = {}
    finite = True
    for species in combined.CHARGED:
        surface = 0.0
        migration = 0.0
        by_wall: dict[str, Any] = {}
        for wall in combined.PLASMA_WALLS:
            _, _, surface_pp, migration_pp = combined._charged_names(species, wall)
            s = _physical(s5r._num(row, surface_pp))
            m = _physical(s5r._num(row, migration_pp))
            finite = finite and math.isfinite(s) and math.isfinite(m)
            by_wall[wall] = {"surface_mass_rate_kg_s": s, "migration_mass_rate_kg_s": m}
            surface += s
            migration += m
        charged[species] = {
            "surface_mass_rate_kg_s": surface,
            "migration_mass_rate_kg_s": migration,
            "total_mass_rate_kg_s": surface + migration,
            "by_wall": by_wall,
        }
    finite = finite and all(math.isfinite(value) for value in neutral.values())
    return {"neutral_mass_rates_kg_s": neutral, "charged": charged, "finite": finite}


def _runtime_metrics(case_dir: Path, *, input_text: str, meta: Mapping[str, Any]) -> dict[str, Any]:
    csv_path = case_dir / "input_out.csv"
    rows = s5r._read_rows(csv_path)
    if len(rows) < 2:
        raise Issue27Stage6AcceptanceError("need INITIAL and TIMESTEP_END rows")
    initial = rows[0]
    final = rows[-1]
    t0 = s5r._num(initial, "time")
    t1 = s5r._num(final, "time")
    dt = t1 - t0
    if dt <= 0.0:
        raise Issue27Stage6AcceptanceError(f"non-positive runtime dt={dt}")

    volume = s5r._num(final, "domain_volume")
    n_ref = float(meta["electron_reference_density_m3"])
    wall = _wall_observables(final)

    thermal_rate_norm = _physical(s5r._num(final, THERMAL_PP))
    see_rate_norm = _physical(s5r._num(final, a8.SEE_PP))
    thermal_rate = thermal_rate_norm * n_ref
    see_rate = see_rate_norm * n_ref

    electron_accumulation = (
        s5r._num(final, "n_e_inventory") - s5r._num(initial, "n_e_inventory")
    ) / dt
    volumetric_electron_rate = s5r._num(final, "s5r_electron_source_avg") * volume
    expected_electron_rate = volumetric_electron_rate + see_rate - thermal_rate
    electron_defect = _rel_defect(
        electron_accumulation,
        expected_electron_rate,
        volumetric_electron_rate,
        see_rate,
        thermal_rate,
    )

    coefficients = s5r._energy_coefficients(input_text)
    volumetric_energy_norm_rate = s5r._energy_source_density(final, coefficients) * volume
    energy_accum_norm_rate = (
        s5r._num(final, "s5r_n_epsilon_inventory")
        - s5r._num(initial, "s5r_n_epsilon_inventory")
    ) / dt
    energy_scale = n_ref * energy.ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C
    thermal_power = _physical(s5r._num(final, energy.ENERGY_WALL_THERMAL_POWER_PP))
    see_power = _physical(s5r._num(final, energy.SEE_ENERGY_COUPLED_POWER_PP))
    expected_energy_norm_rate = (
        volumetric_energy_norm_rate - thermal_power / energy_scale + see_power / energy_scale
    )
    energy_defect = _rel_defect(
        energy_accum_norm_rate,
        expected_energy_norm_rate,
        volumetric_energy_norm_rate,
        thermal_power / energy_scale,
        see_power / energy_scale,
    )

    expected_see_power = see_rate * ELEMENTARY_CHARGE_C * 4.0
    see_mapping_defect = _rel_defect(see_power, expected_see_power)

    ion_rates: dict[str, float] = {}
    for species, cfg in combined.CHARGED.items():
        ion_rates[species] = (
            combined.AVOGADRO
            * float(wall["charged"][species]["total_mass_rate_kg_s"])
            / float(cfg["molar_mass"])
        )
    positive_ion_charge_delta = -ELEMENTARY_CHARGE_C * (
        ion_rates["O2p"] + ion_rates["Op"]
    ) * dt
    negative_ion_charge_delta = +ELEMENTARY_CHARGE_C * ion_rates["Om"] * dt
    thermal_electron_charge_delta = +ELEMENTARY_CHARGE_C * thermal_rate * dt
    see_electron_charge_delta = -ELEMENTARY_CHARGE_C * see_rate * dt
    expected_charge_delta = (
        positive_ion_charge_delta
        + negative_ion_charge_delta
        + thermal_electron_charge_delta
        + see_electron_charge_delta
    )
    measured_charge_delta = (
        s5r._num(final, "r31_charge_integral")
        - s5r._num(initial, "r31_charge_integral")
    )
    charge_scale = max(
        abs(positive_ion_charge_delta)
        + abs(negative_ion_charge_delta)
        + abs(thermal_electron_charge_delta)
        + abs(see_electron_charge_delta),
        1.0e-300,
    )
    charge_defect = abs(measured_charge_delta - expected_charge_delta) / charge_scale

    gauss = s5r._gauss_evidence(csv_path)
    state = s5r._state_evidence(rows)
    composition_error = max(
        abs(s5r._num(final, "sum_w_min") - 1.0),
        abs(s5r._num(final, "sum_w_max") - 1.0),
    )

    return {
        "dt_s": dt,
        "state": state,
        "gauss": gauss,
        "wall": wall,
        "electron_particle": {
            "accumulation_rate_s-1": electron_accumulation,
            "volumetric_source_rate_s-1": volumetric_electron_rate,
            "thermal_wall_loss_rate_s-1": thermal_rate,
            "see_wall_source_rate_s-1": see_rate,
            "expected_rate_s-1": expected_electron_rate,
            "relative_defect": electron_defect,
        },
        "electron_energy": {
            "accumulation_normalized_rate": energy_accum_norm_rate,
            "volumetric_source_normalized_rate": volumetric_energy_norm_rate,
            "thermal_wall_power_W": thermal_power,
            "see_wall_power_W": see_power,
            "expected_normalized_rate": expected_energy_norm_rate,
            "relative_defect": energy_defect,
        },
        "see_4eV_mapping": {
            "expected_power_W": expected_see_power,
            "measured_power_W": see_power,
            "relative_defect": see_mapping_defect,
        },
        "charge": {
            "ion_incident_particle_rate_s-1": ion_rates,
            "positive_ion_charge_delta_C": positive_ion_charge_delta,
            "negative_ion_charge_delta_C": negative_ion_charge_delta,
            "thermal_electron_charge_delta_C": thermal_electron_charge_delta,
            "see_electron_charge_delta_C": see_electron_charge_delta,
            "expected_delta_C": expected_charge_delta,
            "measured_delta_C": measured_charge_delta,
            "relative_defect_over_boundary_current_scale": charge_defect,
        },
        "composition_max_abs_error": composition_error,
        "n_e_min": s5r._num(final, "n_e_min"),
        "n_epsilon_min": s5r._num(final, "s5r_n_epsilon_min"),
    }


def _evaluate(construction: Mapping[str, Any], metrics: Mapping[str, Any], *, runtime_ok: bool) -> dict[str, Any]:
    state = metrics["state"]
    gauss = metrics["gauss"]
    gates = {
        "F01_construction_contracts": construction["audit"]["status"] == "PASS",
        "F02_stage5_source_and_state_invariants": state.get("hard_pass") is True,
        "F03_wall_runtime_observables": metrics["wall"]["finite"] is True,
        "F04_electron_particle_balance": metrics["electron_particle"]["relative_defect"] <= COUPLED_BALANCE_REL_TOL,
        "F05_electron_energy_balance": metrics["electron_energy"]["relative_defect"] <= COUPLED_BALANCE_REL_TOL,
        "F06_four_ev_see_mapping": metrics["see_4eV_mapping"]["relative_defect"] <= ALGEBRAIC_REL_TOL,
        "F07_boundary_current_charge_closure": metrics["charge"]["relative_defect_over_boundary_current_scale"] <= RUNTIME_REL_TOL,
        "F08_gauss_closure": gauss.get("status") == "MEASURED" and gauss.get("relative_defect", math.inf) <= s5r.MAX_GAUSS_RELATIVE_DEFECT,
        "F09_convergence_positivity": (
            runtime_ok
            and metrics["n_e_min"] >= ELECTRON_DENSITY_FLOOR
            and metrics["n_epsilon_min"] > 0.0
            and metrics["composition_max_abs_error"] <= COMPOSITION_ABS_TOL
        ),
    }
    return {"gates": gates, "scientific_hard_pass": all(gates.values())}


def _synthetic_decision() -> tuple[dict[str, Any], dict[str, Any]]:
    construction = {"audit": {"status": "PASS"}}
    metrics = {
        "state": {"hard_pass": True},
        "gauss": {"status": "MEASURED", "relative_defect": 1.0e-6},
        "wall": {"finite": True},
        "electron_particle": {"relative_defect": 1.0e-6},
        "electron_energy": {"relative_defect": 1.0e-6},
        "see_4eV_mapping": {"relative_defect": 1.0e-12},
        "charge": {"relative_defect_over_boundary_current_scale": 1.0e-6},
        "composition_max_abs_error": 1.0e-12,
        "n_e_min": 1.0,
        "n_epsilon_min": 1.0,
    }
    return construction, metrics


def _self_test() -> int:
    text, meta = _construction()
    assert final_stage6.audit_stage6_final_input(text)["status"] == "PASS"
    assert meta["thermal_particle_mean_energy"] == "mean_en_solved"
    construction, metrics = _synthetic_decision()
    assert _evaluate(construction, metrics, runtime_ok=True)["scientific_hard_pass"] is True
    mutations = (
        ("electron_particle", "relative_defect", 1.0),
        ("electron_energy", "relative_defect", 1.0),
        ("see_4eV_mapping", "relative_defect", 1.0e-3),
        ("charge", "relative_defect_over_boundary_current_scale", 1.0),
    )
    for section, field, bad in mutations:
        mutated = json.loads(json.dumps(metrics))
        mutated[section][field] = bad
        assert _evaluate(construction, mutated, runtime_ok=True)["scientific_hard_pass"] is False
    assert _evaluate(construction, metrics, runtime_ok=False)["scientific_hard_pass"] is False
    print("ISSUE27_STAGE6_FINAL_ACCEPTANCE_SELFTEST_PASS")
    return 0


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue27Stage6AcceptanceError(f"invalid physics-opt: {exe}")

    out = args.results_root.resolve()
    case_dir = out / "case"
    logs = out / "logs"
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    input_text, meta, staging = _stage(case_dir)
    p2 = s5r._p2(exe, case_dir, logs / "stage6_final_p2.log", timeout=args.timeout)
    runtime: dict[str, Any] = {"returncode": None}
    metrics: dict[str, Any] = {"status": "NOT_RUN"}
    decision = {"gates": {}, "scientific_hard_pass": False}

    if p2["returncode"] == 0:
        runtime = s5r._runtime(exe, case_dir, logs / "stage6_final_runtime.log", timeout=args.timeout)
        if runtime.get("returncode") == 0:
            metrics = _runtime_metrics(case_dir, input_text=input_text, meta=meta)
            decision = _evaluate(meta, metrics, runtime_ok=True)

    summary = {
        "schema_version": 1,
        "issue": 27,
        "work_id": "oxygen-icp-stage6-final-integration",
        "stage": "STAGE_6_FINAL_WALL_SEE_ENERGY_CHEMISTRY",
        "repository_head": os.environ.get("GITHUB_SHA"),
        "runtime_authority": "governed_ci_provenance_controlled",
        "physics_opt_realpath": str(exe),
        "physics_opt_sha256": _sha256(exe),
        "tolerances": {
            "coupled_balance_relative": COUPLED_BALANCE_REL_TOL,
            "boundary_current_charge_relative": RUNTIME_REL_TOL,
            "see_energy_mapping_relative": ALGEBRAIC_REL_TOL,
            "gauss_relative": s5r.MAX_GAUSS_RELATIVE_DEFECT,
            "composition_absolute": COMPOSITION_ABS_TOL,
            "electron_density_floor": ELECTRON_DENSITY_FLOOR,
        },
        "claim_boundary": {
            "on_green": "bounded one-step final Stage-6 conducting-wall wall+SEE+energy+chemistry integration accepted",
            "does_not_establish": [
                "multi-step A7 anomaly resolution (#194-#200)",
                "dynamic dielectric sigma_s or dielectric SEE (#3/#4)",
                "RF/Maxwell powered ICP closure (#202-#208)",
                "Integrated Physics Accuracy",
            ],
        },
        "construction": meta,
        "staging": staging,
        "p2": p2,
        "runtime": runtime,
        "metrics": metrics,
        "decision": decision,
        "status": (
            "ISSUE27_STAGE6_FINAL_ACCEPTED"
            if decision.get("scientific_hard_pass") is True
            else "ISSUE27_STAGE6_FINAL_FAIL"
        ),
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / "summary.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path.read_text())
    return 0 if decision.get("scientific_hard_pass") is True else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue27-stage6-final-results"))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    if args.timeout <= 0.0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
