#!/usr/bin/env python3
"""Live-electron CI with nonlinear-trial positivity protection for reaction rates."""
from __future__ import annotations

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci as live

base = live.base
_live_build_child_input = base.build_child_input
_live_self_test = base.self_test


def _enable_trial_density_clamp(text: str) -> str:
    rate_materials = []
    for path in base._children(text, "FunctorMaterials"):
        type_name = base.mp.unquote(base.mp.get_parameter(text, path, "type"))
        if type_name == "PhysicsElectronImpactRateMaterial":
            text = base.mp.upsert_parameter(
                text, path, "clamp_negative_electron_density", "true"
            )
            rate_materials.append(path)
    if not rate_materials:
        raise base.Issue236Error("no PhysicsElectronImpactRateMaterial blocks found in live child")
    return text


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _live_build_child_input(production_text, dt_e=dt_e)
    return _enable_trial_density_clamp(text)


def _self_test():
    result = _live_self_test()
    if result.get("status") != "PASS":
        return result
    _parent, child, _meta = base.build_split(dt_e=live.ELECTRON_DT_S)
    rate_paths = [
        path
        for path in base._children(child, "FunctorMaterials")
        if base.mp.unquote(base.mp.get_parameter(child, path, "type"))
        == "PhysicsElectronImpactRateMaterial"
    ]
    clamp_enabled = bool(rate_paths) and all(
        (base.mp.unquote(base.mp.get_parameter(child, path, "clamp_negative_electron_density")) or "").lower()
        == "true"
        for path in rate_paths
    )
    result["checks"]["electron_impact_trial_density_clamp"] = clamp_enabled
    result["failed_checks"] = sorted(
        key for key, ok in result["checks"].items() if not ok
    )
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


base.build_child_input = _build_child_input
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
