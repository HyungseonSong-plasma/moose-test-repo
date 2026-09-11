#!/usr/bin/env python3
"""Governed bounded Stage-6 A8 finite-SEE particle acceptance for issue #193.

A green run establishes only the conducting-wall finite-SEE particle/current/
charge contract at the frozen one-step A8 discriminator horizon. It does not
establish Stage-6 final integration, dielectric SEE/surface charge, RF/Maxwell
closure, or Integrated Physics Accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue27_surface_reactions.controlled_wall import see as a8
from experiments.Issue27_surface_reactions.controlled_wall.combined import (
    CHARGED,
    M_O2_KG_PER_MOL,
    M_O_KG_PER_MOL,
    PLASMA_WALLS,
    _charged_names,
)
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import (
    THERMAL_BC,
    THERMAL_PP,
)
from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.historical_recipe_support.issue192_s5r import (
    _promote_current_physics_object_types,
)
from physics_harness.application.experiment_spec import load_experiment_spec
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
A8_SPEC = ROOT / "experiments" / "Issue27_surface_reactions" / "A8_finite_see" / "experiment.json"
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

# B0 tolerance freeze, established before the first #193 governed result.
# Runtime conservation envelope is inherited from the accepted Issue-27 A2
# charge/Gauss evidence (1.102e-4 and 4.73e-4 respectively), rounded upward
# to one predeclared 1e-3 acceptance surface.
ALGEBRAIC_REL_TOL = 1.0e-10
RUNTIME_REL_TOL = 1.0e-3
COMPOSITION_ABS_TOL = 1.0e-8
ZERO_ABS_TOL = 1.0e-12
ELECTRON_DENSITY_FLOOR = -1.0e-12

AVOGADRO = a8.AVOGADRO
ELEMENTARY_CHARGE_C = a8.ELEMENTARY_CHARGE_C
CASE_MODES = ("see_off", "see_on")


class Issue193AcceptanceError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-300)


def _factor(text: str, path: str) -> float:
    return float(mp.get_parameter(text, path, "factor") or "nan")


def _promote_current_acceptance_types(text: str) -> tuple[str, dict[str, Any]]:
    """Promote a historical R4/A8 construction to the current Physics namespace.

    Historical source assets and characterization fixtures deliberately retain
    their old object names. Current governed execution must instead use the
    current registered Physics objects. Reuse the already accepted Stage-5
    promotion map, then promote the A6 ion-wall materials that are added after
    the inherited R4 topology is built.
    """
    promoted = _promote_current_physics_object_types(text)
    wall_promotions: dict[str, Any] = {}
    for species in CHARGED:
        path = f"FunctorMaterials/issue27_a6_{species}_wall_flux"
        if not mb.has_block(promoted, path):
            raise Issue193AcceptanceError(
                f"missing A6 ion-wall material required for current Physics promotion: {path}"
            )
        previous = mp.get_parameter(promoted, path, "type")
        promoted = mp.upsert_parameter(
            promoted, path, "type", "PhysicsIonWallFluxMaterial"
        )
        wall_promotions[species] = {
            "path": path,
            "from": previous,
            "to": "PhysicsIonWallFluxMaterial",
        }

    remaining_qpx_types = re.findall(
        r"(?m)^\s*type\s*=\s*(QPX[A-Za-z0-9_]+)\s*$", promoted
    )
    if remaining_qpx_types:
        raise Issue193AcceptanceError(
            "current #193 staged input still contains retired QPX object types: "
            + ", ".join(sorted(set(remaining_qpx_types)))
        )
    return promoted, {
        "inherited_stage5_promotion": True,
        "ion_wall_promotions": wall_promotions,
        "remaining_qpx_object_types": remaining_qpx_types,
    }


def _construction_audit(parameters: Mapping[str, Any]) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    texts: dict[str, str] = {}
    promoted_texts: dict[str, str] = {}
    promotion_meta: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    for mode in CASE_MODES:
        text, item = a8._build_a8_case_input(base, parameters=parameters, mode=mode)
        promoted, promotion = _promote_current_acceptance_types(text)
        texts[mode] = text
        promoted_texts[mode] = promoted
        promotion_meta[mode] = promotion
        meta[mode] = item

    on = texts["see_on"]
    off = texts["see_off"]
    promoted_on = promoted_texts["see_on"]
    promoted_off = promoted_texts["see_off"]
    functors = mp.words(
        mp.get_parameter(on, f"FunctorMaterials/{a8.SEE_MATERIAL}", "functor_names")
    )
    expression = mp.get_parameter(on, f"FunctorMaterials/{a8.SEE_MATERIAL}", "expression") or ""
    frozen = a8._validated_parameters(parameters)
    n_ref = float(meta["see_on"]["electron_reference_density_m3"])
    measured_energy_scale = float(
        mp.get_parameter(on, f"Postprocessors/{a8.SEE_ENERGY_PP}", "scaling_factor") or "nan"
    )
    expected_energy_scale = n_ref * ELEMENTARY_CHARGE_C * 4.0

    current_ion_types = {
        species: mp.get_parameter(
            promoted_on,
            f"FunctorMaterials/issue27_a6_{species}_wall_flux",
            "type",
        )
        for species in CHARGED
    }
    checks = {
        "gamma_O2p_exact": frozen["O2p_secondary_emission_coefficient"] == 0.05,
        "gamma_Op_exact": frozen["Op_secondary_emission_coefficient"] == 0.05,
        "energy_4eV_exact": frozen["secondary_electron_mean_energy_eV"] == 4.0,
        "wall_set_exact": tuple(frozen["wall_boundaries"]) == tuple(PLASMA_WALLS),
        "excluded_boundaries_exact": frozen["excluded_boundaries"] == ["inlet", "outlet"],
        "thermal_factor_minus_one_on": _factor(on, f"FVBCs/{THERMAL_BC}") == -1.0,
        "thermal_factor_minus_one_off": _factor(off, f"FVBCs/{THERMAL_BC}") == -1.0,
        "see_factor_plus_one": _factor(on, f"FVBCs/{a8.SEE_BC}") == 1.0,
        "see_factor_zero_control": _factor(off, f"FVBCs/{a8.SEE_BC}") == 0.0,
        "see_variable_ne": mp.get_parameter(on, f"FVBCs/{a8.SEE_BC}", "variable") == "n_e",
        "see_boundaries_exact": tuple(
            mp.words(mp.get_parameter(on, f"FVBCs/{a8.SEE_BC}", "boundary"))
        ) == tuple(PLASMA_WALLS),
        "O2p_surface_once": functors.count("ion_surface_mass_flux_O2p") == 1,
        "O2p_migration_once": functors.count("ion_migration_mass_flux_O2p") == 1,
        "Op_surface_once": functors.count("ion_surface_mass_flux_Op") == 1,
        "Op_migration_once": functors.count("ion_migration_mass_flux_Op") == 1,
        "Om_absent_from_functors": not any("Om" in name or name.endswith("_Om") for name in functors),
        "Om_absent_from_expression": "om" not in expression.lower(),
        "energy_scale_4eV": math.isclose(
            measured_energy_scale, expected_energy_scale, rel_tol=1.0e-14, abs_tol=0.0
        ),
        "bounded_dt_exact": float(mp.get_parameter(on, "Executioner", "dt") or "nan") == 1.0e-10,
        "bounded_end_exact": float(mp.get_parameter(on, "Executioner", "end_time") or "nan") == 1.0e-10,
        "current_object_namespace_clean_on": "type = QPX" not in promoted_on,
        "current_object_namespace_clean_off": "type = QPX" not in promoted_off,
        "current_ion_wall_types": all(
            value == "PhysicsIonWallFluxMaterial" for value in current_ion_types.values()
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "functor_names": functors,
        "expression": expression,
        "n_ref_m3": n_ref,
        "expected_energy_scale": expected_energy_scale,
        "measured_energy_scale": measured_energy_scale,
        "current_ion_wall_types": current_ion_types,
        "promotion": promotion_meta,
    }


def _species_mass_rate(state: Mapping[str, Any], species: str) -> float:
    total = 0.0
    for wall in PLASMA_WALLS:
        _, _, surface_pp, migration_pp = _charged_names(species, wall)
        total += abs(float(state[surface_pp]))
        total += abs(float(state[migration_pp]))
    return total


def _species_particle_rate(state: Mapping[str, Any], species: str) -> float:
    molar_mass = M_O2_KG_PER_MOL if species == "O2p" else M_O_KG_PER_MOL
    return AVOGADRO * _species_mass_rate(state, species) / molar_mass


def _case_metrics(
    state: Mapping[str, Any],
    *,
    n_ref_m3: float,
    see_enabled: bool,
) -> dict[str, Any]:
    if state.get("status") != "MEASURED":
        return {"status": "MISSING", "error": state.get("error", "state not measured")}
    initial = state["initial"]
    final = state["final"]
    dt = float(final["time"]) - float(initial["time"])
    if dt <= 0.0:
        return {"status": "INVALID", "error": f"non-positive dt={dt}"}

    ion_rates = {species: _species_particle_rate(final, species) for species in ("O2p", "Op", "Om")}
    see_components = {
        "O2p": 0.05 * ion_rates["O2p"] if see_enabled else 0.0,
        "Op": 0.05 * ion_rates["Op"] if see_enabled else 0.0,
        "Om": 0.0,
    }
    expected_see_rate = see_components["O2p"] + see_components["Op"]
    see_pp_signed = float(final[a8.SEE_PP])
    measured_see_rate = abs(see_pp_signed) * n_ref_m3
    thermal_pp_signed = float(final[THERMAL_PP])
    thermal_loss = abs(thermal_pp_signed) * n_ref_m3 * dt
    see_gain = measured_see_rate * dt
    expected_electron_delta = see_gain - thermal_loss
    measured_electron_delta = float(final["n_e_inventory"]) - float(initial["n_e_inventory"])

    positive_ion_charge_delta = -ELEMENTARY_CHARGE_C * (
        ion_rates["O2p"] + ion_rates["Op"]
    ) * dt
    negative_ion_charge_delta = +ELEMENTARY_CHARGE_C * ion_rates["Om"] * dt
    thermal_electron_charge_delta = +ELEMENTARY_CHARGE_C * thermal_loss
    see_electron_charge_delta = -ELEMENTARY_CHARGE_C * see_gain
    expected_charge_delta = (
        positive_ion_charge_delta
        + negative_ion_charge_delta
        + thermal_electron_charge_delta
        + see_electron_charge_delta
    )
    measured_charge_delta = (
        float(final["r31_charge_integral"]) - float(initial["r31_charge_integral"])
    )
    charge_scale = max(
        abs(positive_ion_charge_delta)
        + abs(negative_ion_charge_delta)
        + abs(thermal_electron_charge_delta)
        + abs(see_electron_charge_delta),
        1.0e-300,
    )
    gauss_delta = (
        (float(final["r31_gauss_flux_charge"]) - float(final["r31_charge_integral"]))
        - (float(initial["r31_gauss_flux_charge"]) - float(initial["r31_charge_integral"]))
    )
    expected_power = expected_see_rate * ELEMENTARY_CHARGE_C * 4.0
    measured_power_signed = float(final[a8.SEE_ENERGY_PP])
    measured_power = abs(measured_power_signed)
    composition_error = max(
        abs(float(final["sum_w_min"]) - 1.0),
        abs(float(final["sum_w_max"]) - 1.0),
    )

    return {
        "status": "MEASURED",
        "dt_s": dt,
        "ion_incident_particle_rate_s-1": ion_rates,
        "see_component_expected_s-1": see_components,
        "see_particle_rate_signed_postprocessor": see_pp_signed,
        "expected_see_particle_rate_s-1": expected_see_rate,
        "measured_see_particle_rate_s-1": measured_see_rate,
        "see_particle_rate_relative_defect": (
            _rel_defect(measured_see_rate, expected_see_rate)
            if expected_see_rate != 0.0
            else abs(measured_see_rate)
        ),
        "thermal_particle_rate_signed_postprocessor": thermal_pp_signed,
        "thermal_electron_loss": thermal_loss,
        "see_electron_gain": see_gain,
        "expected_electron_inventory_delta": expected_electron_delta,
        "measured_electron_inventory_delta": measured_electron_delta,
        "electron_inventory_relative_defect": _rel_defect(
            measured_electron_delta, expected_electron_delta
        ),
        "positive_ion_charge_delta_C": positive_ion_charge_delta,
        "negative_ion_charge_delta_C": negative_ion_charge_delta,
        "thermal_electron_charge_delta_C": thermal_electron_charge_delta,
        "see_electron_charge_delta_C": see_electron_charge_delta,
        "expected_net_charge_delta_C": expected_charge_delta,
        "measured_net_charge_delta_C": measured_charge_delta,
        "net_charge_abs_defect_over_current_scale": abs(
            measured_charge_delta - expected_charge_delta
        ) / charge_scale,
        "gauss_residual_delta_C": gauss_delta,
        "gauss_abs_defect_over_current_scale": abs(gauss_delta) / charge_scale,
        "expected_see_energy_power_W": expected_power,
        "measured_see_energy_power_signed_W": measured_power_signed,
        "measured_see_energy_power_W": measured_power,
        "see_energy_power_relative_defect": (
            _rel_defect(measured_power, expected_power)
            if expected_power != 0.0
            else abs(measured_power)
        ),
        "composition_max_abs_error": composition_error,
        "n_e_min": float(final["n_e_min"]),
        "nonnegative_electron_density": float(final["n_e_min"]) >= ELECTRON_DENSITY_FLOOR,
    }


def _evaluate_gates(
    construction: Mapping[str, Any],
    metrics: Mapping[str, Mapping[str, Any]],
    *,
    runtime_ok: bool,
) -> dict[str, Any]:
    off = metrics["see_off"]
    on = metrics["see_on"]
    c = construction["checks"]

    off_zero = (
        off["measured_see_particle_rate_s-1"] <= ZERO_ABS_TOL
        and off["measured_see_energy_power_W"] <= ZERO_ABS_TOL
        and off["electron_inventory_relative_defect"] <= RUNTIME_REL_TOL
    )
    source_increment_expected = (
        on["expected_electron_inventory_delta"] - off["expected_electron_inventory_delta"]
    )
    source_increment_measured = (
        on["measured_electron_inventory_delta"] - off["measured_electron_inventory_delta"]
    )
    source_direction = (
        c["see_factor_plus_one"]
        and on["see_electron_gain"] > 0.0
        and source_increment_expected > 0.0
        and source_increment_measured > 0.0
    )

    gates = {
        "G01_zero_see_baseline": off_zero and c["see_factor_zero_control"],
        "G02_see_source_direction": source_direction,
        "G03_see_total_magnitude": on["see_particle_rate_relative_defect"] <= ALGEBRAIC_REL_TOL,
        "G04_O2p_exactly_once": (
            c["O2p_surface_once"]
            and c["O2p_migration_once"]
            and on["ion_incident_particle_rate_s-1"]["O2p"] > 0.0
            and on["see_component_expected_s-1"]["O2p"] > 0.0
        ),
        "G05_Op_exactly_once": (
            c["Op_surface_once"]
            and c["Op_migration_once"]
            and on["ion_incident_particle_rate_s-1"]["Op"] > 0.0
            and on["see_component_expected_s-1"]["Op"] > 0.0
        ),
        "G06_Om_zero_see": (
            c["Om_absent_from_functors"]
            and c["Om_absent_from_expression"]
            and on["see_component_expected_s-1"]["Om"] == 0.0
        ),
        "G07_electron_inventory": (
            off["electron_inventory_relative_defect"] <= RUNTIME_REL_TOL
            and on["electron_inventory_relative_defect"] <= RUNTIME_REL_TOL
        ),
        "G08_wall_current_sign_and_charge": (
            on["positive_ion_charge_delta_C"] <= 0.0
            and on["negative_ion_charge_delta_C"] >= 0.0
            and on["thermal_electron_charge_delta_C"] >= 0.0
            and on["see_electron_charge_delta_C"] <= 0.0
            and on["net_charge_abs_defect_over_current_scale"] <= RUNTIME_REL_TOL
        ),
        "G09_charge_gauss": (
            on["net_charge_abs_defect_over_current_scale"] <= RUNTIME_REL_TOL
            and on["gauss_abs_defect_over_current_scale"] <= RUNTIME_REL_TOL
        ),
        "G10_four_ev_mapping": on["see_energy_power_relative_defect"] <= ALGEBRAIC_REL_TOL,
        "G11_convergence_positivity": (
            runtime_ok
            and off["nonnegative_electron_density"]
            and on["nonnegative_electron_density"]
            and off["composition_max_abs_error"] <= COMPOSITION_ABS_TOL
            and on["composition_max_abs_error"] <= COMPOSITION_ABS_TOL
        ),
    }
    return {
        "gates": gates,
        "scientific_hard_pass": all(gates.values()),
        "source_increment_expected": source_increment_expected,
        "source_increment_measured": source_increment_measured,
    }


def _synthetic_metrics() -> dict[str, Any]:
    common = {
        "status": "MEASURED",
        "ion_incident_particle_rate_s-1": {"O2p": 1000.0, "Op": 500.0, "Om": 100.0},
        "composition_max_abs_error": 1.0e-12,
        "n_e_min": 1.0,
        "nonnegative_electron_density": True,
        "net_charge_abs_defect_over_current_scale": 1.0e-6,
        "gauss_abs_defect_over_current_scale": 1.0e-6,
        "positive_ion_charge_delta_C": -1.0,
        "negative_ion_charge_delta_C": 0.1,
        "thermal_electron_charge_delta_C": 0.5,
        "see_electron_charge_delta_C": -0.05,
    }
    off = dict(common)
    off.update({
        "see_component_expected_s-1": {"O2p": 0.0, "Op": 0.0, "Om": 0.0},
        "measured_see_particle_rate_s-1": 0.0,
        "measured_see_energy_power_W": 0.0,
        "electron_inventory_relative_defect": 1.0e-6,
        "expected_electron_inventory_delta": -10.0,
        "measured_electron_inventory_delta": -10.0,
        "see_electron_gain": 0.0,
        "see_particle_rate_relative_defect": 0.0,
        "see_energy_power_relative_defect": 0.0,
    })
    on = dict(common)
    on.update({
        "see_component_expected_s-1": {"O2p": 50.0, "Op": 25.0, "Om": 0.0},
        "measured_see_particle_rate_s-1": 75.0,
        "measured_see_energy_power_W": 75.0 * ELEMENTARY_CHARGE_C * 4.0,
        "electron_inventory_relative_defect": 1.0e-6,
        "expected_electron_inventory_delta": -5.0,
        "measured_electron_inventory_delta": -5.0,
        "see_electron_gain": 5.0,
        "see_particle_rate_relative_defect": 1.0e-12,
        "see_energy_power_relative_defect": 1.0e-12,
    })
    return {"see_off": off, "see_on": on}


def _self_test() -> int:
    spec = load_experiment_spec(A8_SPEC)
    construction = _construction_audit(spec.parameters)
    assert construction["status"] == "PASS"
    assert construction["checks"]["current_object_namespace_clean_on"] is True
    assert construction["checks"]["current_object_namespace_clean_off"] is True
    assert construction["checks"]["current_ion_wall_types"] is True
    metrics = _synthetic_metrics()
    decision = _evaluate_gates(construction, metrics, runtime_ok=True)
    assert decision["scientific_hard_pass"] is True

    mutations = [
        ("G03_see_total_magnitude", ("see_on", "see_particle_rate_relative_defect"), 1.0e-2),
        ("G07_electron_inventory", ("see_on", "electron_inventory_relative_defect"), 1.0e-2),
        ("G09_charge_gauss", ("see_on", "gauss_abs_defect_over_current_scale"), 1.0e-2),
        ("G10_four_ev_mapping", ("see_on", "see_energy_power_relative_defect"), 1.0e-2),
    ]
    for gate, (case, field), bad in mutations:
        mutated = json.loads(json.dumps(metrics))
        mutated[case][field] = bad
        assert _evaluate_gates(construction, mutated, runtime_ok=True)["gates"][gate] is False

    bad_direction = json.loads(json.dumps(metrics))
    bad_direction["see_on"]["measured_electron_inventory_delta"] = -20.0
    assert _evaluate_gates(construction, bad_direction, runtime_ok=True)["gates"][
        "G02_see_source_direction"
    ] is False

    for check, gate in (
        ("O2p_surface_once", "G04_O2p_exactly_once"),
        ("Op_migration_once", "G05_Op_exactly_once"),
        ("Om_absent_from_expression", "G06_Om_zero_see"),
    ):
        bad_construction = json.loads(json.dumps(construction))
        bad_construction["checks"][check] = False
        assert _evaluate_gates(bad_construction, metrics, runtime_ok=True)["gates"][gate] is False

    bad_zero = json.loads(json.dumps(metrics))
    bad_zero["see_off"]["measured_see_particle_rate_s-1"] = 1.0
    assert _evaluate_gates(construction, bad_zero, runtime_ok=True)["gates"][
        "G01_zero_see_baseline"
    ] is False

    assert _evaluate_gates(construction, metrics, runtime_ok=False)["gates"][
        "G11_convergence_positivity"
    ] is False
    print("ISSUE193_A8_ACCEPTANCE_SELFTEST_PASS")
    return 0


def _run_case(
    exe: Path,
    out: Path,
    mode: str,
    parameters: Mapping[str, Any],
    timeout: float,
) -> dict[str, Any]:
    case_dir = out / "cases" / mode
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    staging = a8._stage_case(case_dir, parameters=parameters, mode=mode)

    input_path = case_dir / "input.i"
    promoted_text, promotion = _promote_current_acceptance_types(
        input_path.read_text(encoding="utf-8")
    )
    input_path.write_text(promoted_text, encoding="utf-8")
    staging["current_physics_object_promotion"] = promotion

    p2 = q0_run._p2(exe, case_dir, logs / f"{mode}_p2.log", timeout)
    runtime: dict[str, Any] = {"returncode": None}
    state: dict[str, Any] = {"status": "NOT_RUN"}
    if p2["returncode"] == 0:
        runtime = q0_run._runtime(exe, case_dir, logs / f"{mode}_runtime.log", timeout)
        state = a8._read_state(case_dir / "input_out.csv")
    return {
        "staging": staging,
        "p2": p2,
        "runtime": runtime,
        "state": state,
    }


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue193AcceptanceError(f"invalid physics-opt: {exe}")
    spec = load_experiment_spec(A8_SPEC)
    construction = _construction_audit(spec.parameters)
    if construction["status"] != "PASS":
        raise Issue193AcceptanceError("A8 construction audit failed")

    out = args.results_root.resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 193,
        "work_id": "oxygen-icp-stage6-a8-see-acceptance",
        "stage": "STAGE_6_A8_BOUNDED_FINITE_SEE",
        "repository_head": os.environ.get("GITHUB_SHA"),
        "runtime_authority": "governed_ci_provenance_controlled",
        "physics_opt_realpath": str(exe),
        "physics_opt_sha256": _sha256(exe),
        "historical_fixture": str(A8_SPEC.relative_to(ROOT)),
        "tolerances": {
            "algebraic_relative": ALGEBRAIC_REL_TOL,
            "runtime_conservation_relative": RUNTIME_REL_TOL,
            "composition_absolute": COMPOSITION_ABS_TOL,
            "zero_absolute": ZERO_ABS_TOL,
            "electron_density_floor": ELECTRON_DENSITY_FLOOR,
            "runtime_anchor": "Issue-27 A2 accepted charge/Gauss defects 1.102e-4 / 4.73e-4",
        },
        "claim_boundary": {
            "on_green": (
                "bounded one-step conducting-wall finite-SEE particle/current/charge "
                "acceptance with frozen O2+/O+ gamma=0.05 and 4 eV mapping"
            ),
            "does_not_establish": [
                "Stage-6 final wall+SEE+energy+chemistry integration",
                "dynamic dielectric SEE",
                "dynamic dielectric sigma_s",
                "RF/Maxwell powered ICP closure",
                "resolution of the separate #194 multi-step A7 anomaly",
                "Integrated Physics Accuracy",
            ],
        },
        "construction_audit": construction,
        "cases": {},
        "metrics": {},
        "decision": {},
        "status": "NOT_RUN",
    }

    runtime_ok = True
    n_ref = float(construction["n_ref_m3"])
    for mode in CASE_MODES:
        result = _run_case(exe, out, mode, spec.parameters, args.timeout)
        summary["cases"][mode] = result
        runtime_ok = runtime_ok and result["p2"]["returncode"] == 0
        runtime_ok = runtime_ok and result["runtime"].get("returncode") == 0
        if result["state"].get("status") == "MEASURED":
            summary["metrics"][mode] = _case_metrics(
                result["state"], n_ref_m3=n_ref, see_enabled=(mode == "see_on")
            )
        else:
            summary["metrics"][mode] = {
                "status": "MISSING",
                "error": result["state"].get("error", "runtime state unavailable"),
            }

    measurable = all(
        summary["metrics"].get(mode, {}).get("status") == "MEASURED" for mode in CASE_MODES
    )
    if measurable:
        summary["decision"] = _evaluate_gates(
            construction, summary["metrics"], runtime_ok=runtime_ok
        )
        passed = summary["decision"]["scientific_hard_pass"] is True
        summary["status"] = (
            "ISSUE193_A8_FINITE_SEE_ACCEPTED"
            if passed
            else "ISSUE193_A8_FINITE_SEE_FAIL"
        )
    else:
        passed = False
        summary["decision"] = {
            "gates": {},
            "scientific_hard_pass": False,
            "classification": "P2_OR_RUNTIME_EVIDENCE_INCOMPLETE",
        }
        summary["status"] = "ISSUE193_A8_RUNTIME_OR_EVIDENCE_FAIL"

    path = out / "summary.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path.read_text(encoding="utf-8"))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument(
        "--results-root", type=Path, default=Path("issue193-a8-see-results")
    )
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
