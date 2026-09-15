#!/usr/bin/env python3
"""Live-electron CI with nonlinear-trial positivity protection and 100:1 subcycling.

Schedule:
* heavy/ion parent: dt_h = 1e-7 s, 10 steps, t_end = 1e-6 s;
* electron density + electron energy + Poisson child: dt_e = 1e-9 s;
* 100 electron subcycles follow each heavy step (1000 electron steps total);
* electron particle and energy surface losses remain active.
"""
from __future__ import annotations

import math

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci as live

# Override only the multirate schedule. The underlying live-electron split,
# thermal surface-loss closure, audits, runtime analysis, and staging remain
# owned by run_live_ci.py and read these module globals dynamically.
live.TOTAL_TIME_S = 1.0e-6
live.HEAVY_STEPS = 10
live.HEAVY_DT_S = 1.0e-7
live.ELECTRON_DT_S = 1.0e-9
live.ELECTRON_STEPS_PER_HEAVY = 100

base = live.base
base.DT_H_S = live.HEAVY_DT_S
base.DT_E_SMOKE_S = live.ELECTRON_DT_S

_live_build_child_input = base.build_child_input
_live_self_test = base.self_test

_ZERO_RATE_GUARD_TYPES = (
    "PhysicsElectronImpactRateMaterial",
    "PhysicsElectronImpactIonizationMaterial",
    "PhysicsElectronImpactO2sExcitationMaterial",
)


def _enable_trial_state_guards(text: str) -> str:
    zero_rate_materials: dict[str, list[str]] = {name: [] for name in _ZERO_RATE_GUARD_TYPES}
    mean_energy_materials = []
    for path in base._children(text, "FunctorMaterials"):
        type_name = base.mp.unquote(base.mp.get_parameter(text, path, "type"))
        if type_name in zero_rate_materials:
            text = base.mp.upsert_parameter(
                text, path, "clamp_negative_electron_density", "true"
            )
            zero_rate_materials[type_name].append(path)
        elif type_name == "PhysicsElectronMeanEnergyMaterial":
            energy_ref = base.mp.get_parameter(text, path, "energy_reference_eV")
            if energy_ref is None:
                raise base.Issue236Error(
                    f"mean-energy material lacks energy_reference_eV: {path}"
                )
            text = base.mp.upsert_parameter(
                text, path, "use_trial_state_fallback", "true"
            )
            text = base.mp.upsert_parameter(
                text, path, "trial_fallback_mean_energy_eV", energy_ref
            )
            mean_energy_materials.append(path)

    missing_rate_types = [name for name, paths in zero_rate_materials.items() if not paths]
    if missing_rate_types:
        raise base.Issue236Error(
            f"missing electron-impact rate material types in live child: {missing_rate_types}"
        )
    if not mean_energy_materials:
        raise base.Issue236Error("no PhysicsElectronMeanEnergyMaterial block found in live child")
    return text


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _live_build_child_input(production_text, dt_e=dt_e)
    return _enable_trial_state_guards(text)


def _self_test():
    # Reuse inherited structural checks, but replace all schedule-specific
    # assertions from the older 10:1 smoke contract with the requested 100:1 contract.
    result = _live_self_test()
    checks = result.setdefault("checks", {})
    for obsolete in (
        "heavy_dt_1e_8",
        "ten_electron_steps_per_heavy",
        "hundred_total_electron_steps",
        "smoke_subcycles",
    ):
        checks.pop(obsolete, None)

    _parent, child, meta = base.build_split(dt_e=live.ELECTRON_DT_S)
    checks["heavy_dt_1e_7"] = math.isclose(
        meta["dt_h_s"], 1.0e-7, rel_tol=0.0, abs_tol=0.0
    )
    checks["electron_dt_1e_9"] = math.isclose(
        meta["dt_e_s"], 1.0e-9, rel_tol=0.0, abs_tol=0.0
    )
    checks["ten_heavy_steps"] = meta["heavy_steps"] == 10
    checks["hundred_electron_steps_per_heavy"] = meta["subcycles_per_heavy"] == 100
    checks["thousand_total_electron_steps"] = meta["subcycles_expected"] == 1000
    checks["final_time_1e_6"] = math.isclose(
        meta["total_time_s"], 1.0e-6, rel_tol=0.0, abs_tol=0.0
    )
    checks["multirate_ratio_100"] = math.isclose(
        meta["dt_h_s"] / meta["dt_e_s"], 100.0, rel_tol=0.0, abs_tol=1.0e-12
    )

    for type_name in _ZERO_RATE_GUARD_TYPES:
        paths = [
            path
            for path in base._children(child, "FunctorMaterials")
            if base.mp.unquote(base.mp.get_parameter(child, path, "type")) == type_name
        ]
        checks[f"trial_zero_rate_guard:{type_name}"] = bool(paths) and all(
            (base.mp.unquote(base.mp.get_parameter(child, path, "clamp_negative_electron_density")) or "").lower()
            == "true"
            for path in paths
        )

    mean_paths = [
        path
        for path in base._children(child, "FunctorMaterials")
        if base.mp.unquote(base.mp.get_parameter(child, path, "type"))
        == "PhysicsElectronMeanEnergyMaterial"
    ]
    checks["mean_energy_trial_state_fallback"] = bool(mean_paths) and all(
        (base.mp.unquote(base.mp.get_parameter(child, path, "use_trial_state_fallback")) or "").lower()
        == "true"
        and float(base.mp.get_parameter(child, path, "trial_fallback_mean_energy_eV") or "nan") > 0.0
        for path in mean_paths
    )

    result["failed_checks"] = sorted(key for key, ok in checks.items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


base.build_child_input = _build_child_input
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
