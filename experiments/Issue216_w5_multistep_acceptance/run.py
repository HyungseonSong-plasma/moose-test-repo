#!/usr/bin/env python3
"""Issue #216 W5 bounded multi-step conducting-wall acceptance.

This runner extends the accepted Issue-217 grounded-sheath particle/energy
composition in physical time without changing production physics. It records
per-step particle, energy, wall-current, volume-charge, Gauss, positivity, and
solver evidence for baseline, half-timestep, and uniformly refined-mesh cases.
Endpoint sensitivities are reported without inventing a new numerical
convergence threshold; terminal W5 closure remains a Validator decision.
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
from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue27_surface_reactions.controlled_wall import combined, see as a8
from experiments.historical_recipe_support import issue26_energy_chain as energy
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.nonlinear_solver import runtime_core_facts
from physics_harness.execution.cases import stage_case, validate_case_references

ROOT = Path(__file__).resolve().parents[2]
SOURCE = s5r.SOURCE
BASELINE_DT_S = 1.0e-10
HALF_DT_S = 5.0e-11
END_TIME_S = 5.0e-10
UNIFORM_REFINE_LEVEL = 1
CASE_SPECS = (
    ("baseline", BASELINE_DT_S, 0),
    ("half_dt", HALF_DT_S, 0),
    ("refined_mesh", BASELINE_DT_S, UNIFORM_REFINE_LEVEL),
)
ELEMENTARY_CHARGE_C = w45.ELEMENTARY_CHARGE_C
AVOGADRO = w45.AVOGADRO


class Issue216Error(RuntimeError):
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


def _symmetric_relative(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def _build_case(*, dt_s: float, uniform_refine: int) -> tuple[str, dict[str, Any]]:
    text, meta = w45.build_issue217_input()
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{dt_s:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{END_TIME_S:.17g}")
    if uniform_refine:
        text = mp.upsert_parameter(text, "Mesh", "uniform_refine", str(uniform_refine))
    return text, {
        **meta,
        "issue": 216,
        "predecessor_issue": 217,
        "claim": "bounded_multistep_conducting_wall_current_charge_gauss_acceptance",
        "timestep_s": dt_s,
        "end_time_s": END_TIME_S,
        "expected_steps": int(round(END_TIME_S / dt_s)),
        "uniform_refine": uniform_refine,
    }


def _stage(
    case_dir: Path, *, dt_s: float, uniform_refine: int
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    text, meta = _build_case(dt_s=dt_s, uniform_refine=uniform_refine)
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


def _physical_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if s5r._num(row, "time") > 1.0e-15]


def _gauss_at_row(row: Mapping[str, str]) -> dict[str, float]:
    q_volume = s5r._num(row, "r31_charge_integral")
    q_flux = s5r._num(row, "r31_gauss_flux_charge")
    scale = max(abs(q_volume), abs(q_flux), 1.0e-300)
    return {
        "volume_charge_C": q_volume,
        "boundary_displacement_flux_C": q_flux,
        "signed_defect_C": q_flux - q_volume,
        "relative_defect": abs(q_flux - q_volume) / scale,
    }


def _wall_currents(row: Mapping[str, str], *, n_ref: float) -> dict[str, Any]:
    wall = w45._wall_observables(row)
    ion_rates: dict[str, float] = {}
    for species, cfg in combined.CHARGED.items():
        ion_rates[species] = (
            AVOGADRO
            * float(wall["charged"][species]["total_mass_rate_kg_s"])
            / float(cfg["molar_mass"])
        )
    primary_rate = abs(s5r._num(row, w45.PARTICLE_PP)) * n_ref
    see_rate = abs(s5r._num(row, a8.SEE_PP)) * n_ref
    currents = {
        "O2p_A": +ELEMENTARY_CHARGE_C * ion_rates["O2p"],
        "Op_A": +ELEMENTARY_CHARGE_C * ion_rates["Op"],
        "Om_A": -ELEMENTARY_CHARGE_C * ion_rates["Om"],
        "primary_electron_A": -ELEMENTARY_CHARGE_C * primary_rate,
        "see_electron_A": +ELEMENTARY_CHARGE_C * see_rate,
    }
    net_outward = sum(currents.values())
    return {
        "wall": wall,
        "ion_incident_particle_rate_s-1": ion_rates,
        "primary_electron_particle_rate_s-1": primary_rate,
        "see_electron_particle_rate_s-1": see_rate,
        "components": currents,
        "net_outward_wall_current_A": net_outward,
        "predicted_dQdt_C_s": -net_outward,
    }


def _step_evidence(
    previous: Mapping[str, str],
    current: Mapping[str, str],
    *,
    input_text: str,
    meta: Mapping[str, Any],
) -> dict[str, Any]:
    t0 = s5r._num(previous, "time")
    t1 = s5r._num(current, "time")
    dt = t1 - t0
    if dt <= 0.0:
        raise Issue216Error(f"non-positive step dt={dt}")
    volume = s5r._num(current, "domain_volume")
    if volume <= 0.0:
        raise Issue216Error(f"non-positive domain volume={volume}")

    n_ref = float(meta["electron_reference_density_m3"])
    currents = _wall_currents(current, n_ref=n_ref)
    primary_rate = float(currents["primary_electron_particle_rate_s-1"])
    see_rate = float(currents["see_electron_particle_rate_s-1"])

    electron_accum = (
        s5r._num(current, "n_e_inventory") - s5r._num(previous, "n_e_inventory")
    ) / dt
    electron_volume = s5r._num(current, "s5r_electron_source_avg") * volume
    electron_expected = electron_volume + see_rate - primary_rate
    particle_defect = _rel_defect(
        electron_accum, electron_expected, electron_volume, see_rate, primary_rate
    )

    coeff = s5r._energy_coefficients(input_text)
    energy_volume = s5r._energy_source_density(current, coeff) * volume
    energy_accum = (
        s5r._num(current, "s5r_n_epsilon_inventory")
        - s5r._num(previous, "s5r_n_epsilon_inventory")
    ) / dt
    energy_scale = n_ref * w45.ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C
    primary_power = abs(s5r._num(current, w45.ENERGY_POWER_PP))
    see_power = abs(s5r._num(current, energy.SEE_ENERGY_COUPLED_POWER_PP))
    energy_expected = energy_volume - primary_power / energy_scale + see_power / energy_scale
    energy_defect = _rel_defect(
        energy_accum,
        energy_expected,
        energy_volume,
        primary_power / energy_scale,
        see_power / energy_scale,
    )
    expected_see_power = see_rate * ELEMENTARY_CHARGE_C * 4.0
    see_mapping_defect = _rel_defect(see_power, expected_see_power)

    measured_delta_q = (
        s5r._num(current, "r31_charge_integral")
        - s5r._num(previous, "r31_charge_integral")
    )
    expected_delta_q = float(currents["predicted_dQdt_C_s"]) * dt
    charge_components = tuple(abs(float(v)) * dt for v in currents["components"].values())
    charge_scale = max(sum(charge_components), 1.0e-300)
    charge_defect = abs(measured_delta_q - expected_delta_q) / charge_scale

    gauss = _gauss_at_row(current)
    composition_error = max(
        abs(s5r._num(current, "sum_w_min") - 1.0),
        abs(s5r._num(current, "sum_w_max") - 1.0),
    )
    n_e_min = s5r._num(current, "n_e_min")
    n_epsilon_min = s5r._num(current, "s5r_n_epsilon_min")
    mean_energy_min = s5r._num(current, "s5r_mean_en_min")
    mean_energy_avg = s5r._num(current, "s5r_mean_en_avg")
    finite_values = (
        n_e_min,
        n_epsilon_min,
        mean_energy_min,
        mean_energy_avg,
        s5r._num(current, w45.PHI_MIN_PP),
        s5r._num(current, w45.PHI_MAX_PP),
        s5r._num(current, w45.RHO_MIN_PP),
        s5r._num(current, w45.RHO_MAX_PP),
        measured_delta_q,
        expected_delta_q,
        primary_power,
        see_power,
    )
    gates = {
        "finite": all(math.isfinite(value) for value in finite_values),
        "electron_particle_balance": particle_defect <= s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "electron_energy_balance": energy_defect <= s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "see_4eV_mapping": see_mapping_defect <= w45.ALGEBRAIC_REL_TOL,
        "current_charge_closure": charge_defect <= w45.RUNTIME_REL_TOL,
        "gauss_closure": gauss["relative_defect"] <= s5r.MAX_GAUSS_RELATIVE_DEFECT,
        "electron_density_positive": n_e_min >= w45.ELECTRON_DENSITY_FLOOR,
        "electron_energy_positive": n_epsilon_min > 0.0 and mean_energy_min > 0.0,
        "composition": composition_error <= w45.COMPOSITION_ABS_TOL,
        "primary_energy_owner_active": primary_power > 0.0,
    }
    return {
        "time_initial_s": t0,
        "time_final_s": t1,
        "dt_s": dt,
        "electron_particle": {
            "accumulation_rate_s-1": electron_accum,
            "volumetric_source_rate_s-1": electron_volume,
            "primary_wall_loss_rate_s-1": primary_rate,
            "see_wall_source_rate_s-1": see_rate,
            "expected_rate_s-1": electron_expected,
            "relative_defect": particle_defect,
        },
        "electron_energy": {
            "accumulation_normalized_rate": energy_accum,
            "volumetric_source_normalized_rate": energy_volume,
            "primary_wall_power_W": primary_power,
            "see_wall_power_W": see_power,
            "expected_normalized_rate": energy_expected,
            "relative_defect": energy_defect,
            "see_4eV_mapping_relative_defect": see_mapping_defect,
        },
        "wall_current": currents,
        "charge": {
            "predicted_delta_C": expected_delta_q,
            "measured_delta_C": measured_delta_q,
            "relative_defect_over_boundary_current_scale": charge_defect,
        },
        "gauss": gauss,
        "state": {
            "n_e_min_m3": n_e_min,
            "n_e_inventory": s5r._num(current, "n_e_inventory"),
            "n_epsilon_min": n_epsilon_min,
            "n_epsilon_inventory": s5r._num(current, "s5r_n_epsilon_inventory"),
            "mean_energy_min_eV": mean_energy_min,
            "mean_energy_avg_eV": mean_energy_avg,
            "rho_q_min_C_m3": s5r._num(current, w45.RHO_MIN_PP),
            "rho_q_max_C_m3": s5r._num(current, w45.RHO_MAX_PP),
            "volume_charge_C": s5r._num(current, "r31_charge_integral"),
            "phi_min_V": s5r._num(current, w45.PHI_MIN_PP),
            "phi_max_V": s5r._num(current, w45.PHI_MAX_PP),
            "composition_max_abs_error": composition_error,
        },
        "gates": gates,
        "hard_pass": all(gates.values()),
    }


def _endpoint(rows: list[dict[str, str]], *, meta: Mapping[str, Any]) -> dict[str, float]:
    row = rows[-1]
    currents = _wall_currents(row, n_ref=float(meta["electron_reference_density_m3"]))
    return {
        "n_e_min_m3": s5r._num(row, "n_e_min"),
        "n_e_inventory": s5r._num(row, "n_e_inventory"),
        "n_epsilon_min": s5r._num(row, "s5r_n_epsilon_min"),
        "n_epsilon_inventory": s5r._num(row, "s5r_n_epsilon_inventory"),
        "mean_energy_avg_eV": s5r._num(row, "s5r_mean_en_avg"),
        "volume_charge_C": s5r._num(row, "r31_charge_integral"),
        "phi_min_V": s5r._num(row, w45.PHI_MIN_PP),
        "phi_max_V": s5r._num(row, w45.PHI_MAX_PP),
        "rho_q_min_C_m3": s5r._num(row, w45.RHO_MIN_PP),
        "rho_q_max_C_m3": s5r._num(row, w45.RHO_MAX_PP),
        "primary_electron_particle_rate_s-1": float(
            currents["primary_electron_particle_rate_s-1"]
        ),
        "primary_energy_power_W": abs(s5r._num(row, w45.ENERGY_POWER_PP)),
        "see_electron_particle_rate_s-1": float(currents["see_electron_particle_rate_s-1"]),
        "net_outward_wall_current_A": float(currents["net_outward_wall_current_A"]),
    }


def _solver_evidence(log_path: Path, *, returncode: int) -> dict[str, Any]:
    if not log_path.is_file():
        return {"status": "MISSING"}
    text = log_path.read_text(errors="replace")
    facts = runtime_core_facts(
        text,
        returncode=returncode,
        coupled_scaling_variables=("n_e", "n_epsilon"),
    )
    healthy = (
        returncode == 0
        and facts["linear_reason"] is None
        and facts["nonlinear_reason"] is None
        and not facts["nonfinite_residuals"]
        and not facts["scaling_invalid"]
    )
    return {"status": "MEASURED", "healthy": healthy, "facts": facts}


def _analyze_case(
    case_dir: Path,
    *,
    input_text: str,
    meta: Mapping[str, Any],
    runtime_log: Path,
    runtime_returncode: int,
) -> dict[str, Any]:
    rows = s5r._read_rows(case_dir / "input_out.csv")
    if len(rows) < 2:
        raise Issue216Error("need INITIAL plus at least one TIMESTEP_END row")
    physical = _physical_rows(rows)
    if not physical:
        raise Issue216Error("no physical TIMESTEP_END rows")
    steps = [
        _step_evidence(previous, current, input_text=input_text, meta=meta)
        for previous, current in zip(rows[:-1], rows[1:])
    ]
    final_time = s5r._num(physical[-1], "time")
    expected_steps = int(meta["expected_steps"])
    solver = _solver_evidence(runtime_log, returncode=runtime_returncode)
    state = s5r._state_evidence(physical)
    gates = {
        "runtime_complete": runtime_returncode == 0
        and math.isclose(final_time, END_TIME_S, rel_tol=0.0, abs_tol=1.0e-18),
        "expected_step_count": len(steps) == expected_steps,
        "all_step_ledgers": bool(steps) and all(step["hard_pass"] for step in steps),
        "state_invariants": state.get("hard_pass") is True,
        "solver_evidence": solver.get("healthy") is True,
    }
    return {
        "final_time_s": final_time,
        "expected_steps": expected_steps,
        "measured_steps": len(steps),
        "state": state,
        "solver": solver,
        "steps": steps,
        "endpoint": _endpoint(physical, meta=meta),
        "max_defects": {
            "electron_particle": max(step["electron_particle"]["relative_defect"] for step in steps),
            "electron_energy": max(step["electron_energy"]["relative_defect"] for step in steps),
            "current_charge": max(
                step["charge"]["relative_defect_over_boundary_current_scale"] for step in steps
            ),
            "gauss": max(step["gauss"]["relative_defect"] for step in steps),
            "see_4eV": max(
                step["electron_energy"]["see_4eV_mapping_relative_defect"] for step in steps
            ),
        },
        "gates": gates,
        "hard_pass": all(gates.values()),
    }


def _sensitivity(
    reference: Mapping[str, float],
    comparison: Mapping[str, float],
    *,
    comparison_name: str,
) -> dict[str, Any]:
    values = {
        key: {
            "reference": float(reference[key]),
            "comparison": float(comparison[key]),
            "symmetric_relative_difference": _symmetric_relative(
                float(reference[key]), float(comparison[key])
            ),
        }
        for key in reference
    }
    return {
        "status": "MEASURED_UNTHRESHOLDED",
        "comparison": comparison_name,
        "reason": (
            "W5 EVR-1 reports endpoint sensitivity against the accepted invariant "
            "surface without inventing a new numerical convergence threshold."
        ),
        "values": values,
        "max_symmetric_relative_difference": max(
            item["symmetric_relative_difference"] for item in values.values()
        ),
    }


def _charge_relation_gate(
    *, measured_delta_C: float, predicted_delta_C: float, current_scale_C: float
) -> bool:
    scale = max(abs(current_scale_C), 1.0e-300)
    return abs(measured_delta_C - predicted_delta_C) / scale <= w45.RUNTIME_REL_TOL


def self_test() -> dict[str, Any]:
    predecessor = w45.self_test()
    baseline_text, baseline_meta = _build_case(dt_s=BASELINE_DT_S, uniform_refine=0)
    half_text, half_meta = _build_case(dt_s=HALF_DT_S, uniform_refine=0)
    refined_text, refined_meta = _build_case(
        dt_s=BASELINE_DT_S, uniform_refine=UNIFORM_REFINE_LEVEL
    )
    exact = _charge_relation_gate(
        measured_delta_C=2.0e-9, predicted_delta_C=2.0e-9, current_scale_C=2.0e-9
    )
    wrong_sign = _charge_relation_gate(
        measured_delta_C=2.0e-9, predicted_delta_C=-2.0e-9, current_scale_C=2.0e-9
    )
    broken_magnitude = _charge_relation_gate(
        measured_delta_C=2.0e-9, predicted_delta_C=1.0e-9, current_scale_C=2.0e-9
    )
    checks = {
        "issue217_predecessor": predecessor["status"] == "PASS",
        "baseline_dt": math.isclose(
            float(mp.get_parameter(baseline_text, "Executioner", "dt") or "nan"),
            BASELINE_DT_S,
            rel_tol=0.0,
            abs_tol=0.0,
        ),
        "baseline_end": math.isclose(
            float(mp.get_parameter(baseline_text, "Executioner", "end_time") or "nan"),
            END_TIME_S,
            rel_tol=0.0,
            abs_tol=0.0,
        ),
        "half_dt": math.isclose(
            float(mp.get_parameter(half_text, "Executioner", "dt") or "nan"),
            HALF_DT_S,
            rel_tol=0.0,
            abs_tol=0.0,
        ),
        "half_end": math.isclose(
            float(mp.get_parameter(half_text, "Executioner", "end_time") or "nan"),
            END_TIME_S,
            rel_tol=0.0,
            abs_tol=0.0,
        ),
        "refined_mesh_level": mp.get_parameter(refined_text, "Mesh", "uniform_refine")
        == str(UNIFORM_REFINE_LEVEL),
        "baseline_unmodified_mesh": mp.get_parameter(baseline_text, "Mesh", "uniform_refine")
        in (None, "0"),
        "baseline_expected_steps": baseline_meta["expected_steps"] == 5,
        "half_expected_steps": half_meta["expected_steps"] == 10,
        "refined_expected_steps": refined_meta["expected_steps"] == 5,
        "charge_positive_control": exact,
        "wrong_sign_negative_control": not wrong_sign,
        "broken_magnitude_negative_control": not broken_magnitude,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "negative_controls": {
            "exact_relation_passes": exact,
            "wrong_sign_rejected": not wrong_sign,
            "broken_magnitude_rejected": not broken_magnitude,
        },
    }


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue216Error(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue216Error(f"W5 P0 self-test failed: {p0}")

    out = args.results_root.resolve()
    cases_root = out / "cases"
    logs = out / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 216,
        "parent_controller": 211,
        "predecessor_issue": 217,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "runtime_authority": "governed_ci_provenance_controlled",
        "physics_opt_realpath": str(exe),
        "physics_opt_sha256": _sha256(exe),
        "bounded_horizon_s": END_TIME_S,
        "p0": p0,
        "cases": {},
        "sensitivity": {},
        "decision": {},
        "claim_boundary": {
            "on_green": (
                "bounded multi-step grounded conducting-wall particle/energy/current/"
                "charge/Gauss evidence ready for terminal W5 review"
            ),
            "does_not_establish": [
                "A7 user-local acceptance",
                "long-time powered ICP correctness",
                "floating conductor closure",
                "dielectric sigma_s",
                "inverse/SCL/electron-attracting sheath branches",
                "RF/Maxwell powered ICP closure",
            ],
        },
    }

    case_inputs: dict[str, str] = {}
    case_meta: dict[str, dict[str, Any]] = {}
    for name, dt_s, uniform_refine in CASE_SPECS:
        case_dir = cases_root / name
        text, meta, staging = _stage(case_dir, dt_s=dt_s, uniform_refine=uniform_refine)
        case_inputs[name] = text
        case_meta[name] = meta
        summary["cases"][name] = {
            "dt_s": dt_s,
            "end_time_s": END_TIME_S,
            "uniform_refine": uniform_refine,
            "staging": staging,
            "p2": {},
            "runtime": {},
            "evidence": {},
        }

    all_p2 = True
    for name, _, _ in CASE_SPECS:
        case_dir = cases_root / name
        p2 = s5r._p2(exe, case_dir, logs / f"{name}_p2.log", timeout=args.timeout)
        summary["cases"][name]["p2"] = p2
        all_p2 = all_p2 and p2["returncode"] == 0
    if not all_p2:
        summary["decision"] = {
            "core_hard_pass": False,
            "closure_ready": False,
            "reason": "P2_CHECK_INPUT_FAILURE",
        }
        summary["status"] = "W5_P2_FAIL"
        out.mkdir(parents=True, exist_ok=True)
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 2

    case_hard_pass = True
    for name, _, _ in CASE_SPECS:
        case_dir = cases_root / name
        runtime_log = logs / f"{name}_runtime.log"
        runtime = s5r._runtime(exe, case_dir, runtime_log, timeout=args.timeout)
        summary["cases"][name]["runtime"] = runtime
        try:
            evidence = _analyze_case(
                case_dir,
                input_text=case_inputs[name],
                meta=case_meta[name],
                runtime_log=runtime_log,
                runtime_returncode=int(runtime.get("returncode", 1)),
            )
        except (Issue216Error, KeyError, ValueError, AssertionError) as exc:
            evidence = {"hard_pass": False, "analysis_error": str(exc)}
        summary["cases"][name]["evidence"] = evidence
        case_hard_pass = case_hard_pass and evidence.get("hard_pass") is True

    if all(
        summary["cases"][name]["evidence"].get("hard_pass") is True
        for name in ("baseline", "half_dt", "refined_mesh")
    ):
        baseline_endpoint = summary["cases"]["baseline"]["evidence"]["endpoint"]
        half_endpoint = summary["cases"]["half_dt"]["evidence"]["endpoint"]
        refined_endpoint = summary["cases"]["refined_mesh"]["evidence"]["endpoint"]
        summary["sensitivity"]["timestep"] = _sensitivity(
            baseline_endpoint,
            half_endpoint,
            comparison_name="baseline_dt_vs_half_dt_equal_physical_time",
        )
        summary["sensitivity"]["mesh"] = _sensitivity(
            baseline_endpoint,
            refined_endpoint,
            comparison_name="baseline_mesh_vs_uniform_refine_1_equal_physical_time",
        )
    else:
        summary["sensitivity"] = {"status": "NOT_EVALUATED_CASE_FAILURE"}

    summary["decision"] = {
        "core_hard_pass": case_hard_pass,
        "closure_ready": False,
        "validator_review_required": True,
        "sensitivity_threshold": None,
        "reason": (
            "W5 EVR-1 hard invariant surface passes; timestep and mesh endpoint "
            "sensitivity require terminal Validator review without an invented threshold."
            if case_hard_pass
            else "one or more W5 runtime/invariant cases failed"
        ),
    }
    summary["status"] = (
        "W5_EVIDENCE_READY_FOR_VALIDATOR_REVIEW"
        if case_hard_pass
        else "W5_RUNTIME_OR_INVARIANT_FAIL"
    )
    out.mkdir(parents=True, exist_ok=True)
    path = out / "summary.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path.read_text(encoding="utf-8"))
    return 0 if case_hard_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument(
        "--results-root", type=Path, default=Path("issue216-w5-multistep-results")
    )
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    if args.timeout <= 0.0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
