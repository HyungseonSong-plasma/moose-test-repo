#!/usr/bin/env python3
"""Issue-236 dielectric-relaxation-resolved live-electron discriminator.

Coupling per heavy interval:

1. hold the heavy state fixed;
2. solve n_e, n_epsilon, and potential_plasma together for 100 fast substeps;
3. transfer the relaxed electron/energy/Poisson state back to the parent;
4. advance the heavy system once.

Schedule:
* electron + Poisson dt_e = 1e-10 s;
* 100 fast substeps per heavy step;
* heavy dt_h = 1e-8 s;
* 2 heavy steps;
* total time = 2e-8 s;
* 200 electron/Poisson steps total.

The production strict electron-impact lookup policy remains enabled.  This test
therefore checks whether resolving the fast dielectric response removes the
out-of-range nonlinear excursion seen at dt_e = 1e-9 s rather than hiding it
with a kinetic-table clamp.
"""
from __future__ import annotations

import math

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_pos as pos

live = pos.live
base = pos.base

live.TOTAL_TIME_S = 2.0e-8
live.HEAVY_STEPS = 2
live.HEAVY_DT_S = 1.0e-8
live.ELECTRON_DT_S = 1.0e-10
live.ELECTRON_STEPS_PER_HEAVY = 100

base.DT_H_S = live.HEAVY_DT_S
base.DT_E_SMOKE_S = live.ELECTRON_DT_S

_pos_self_test = base.self_test


def _self_test():
    result = _pos_self_test()
    checks = result.setdefault("checks", {})

    # Remove schedule assertions inherited from the older 1e-7/1e-9 run.
    for obsolete in (
        "smoke_subcycles",
        "heavy_dt_1e_8",
        "heavy_dt_1e_7",
        "electron_dt_1e_9",
        "ten_heavy_steps",
        "ten_electron_steps_per_heavy",
        "hundred_total_electron_steps",
        "hundred_electron_steps_per_heavy",
        "thousand_total_electron_steps",
        "final_time_1e_6",
        "multirate_ratio_100",
    ):
        checks.pop(obsolete, None)

    parent, child, meta = base.build_split(dt_e=live.ELECTRON_DT_S)

    checks["heavy_dt_1e_8"] = math.isclose(
        meta["dt_h_s"], 1.0e-8, rel_tol=0.0, abs_tol=0.0
    )
    checks["electron_poisson_dt_1e_10"] = math.isclose(
        meta["dt_e_s"], 1.0e-10, rel_tol=0.0, abs_tol=0.0
    )
    checks["two_heavy_steps"] = meta["heavy_steps"] == 2
    checks["hundred_fast_steps_per_heavy"] = meta["subcycles_per_heavy"] == 100
    checks["two_hundred_fast_steps_total"] = meta["subcycles_expected"] == 200
    checks["final_time_2e_8"] = math.isclose(
        meta["total_time_s"], 2.0e-8, rel_tol=0.0, abs_tol=0.0
    )
    checks["multirate_ratio_100"] = math.isclose(
        meta["dt_h_s"] / meta["dt_e_s"], 100.0, rel_tol=0.0, abs_tol=1.0e-12
    )

    checks["electron_poisson_coupled_fast_system"] = (
        all(
            base.mb.has_block(child, f"Variables/{name}")
            for name in ("n_e", "n_epsilon", "potential_plasma")
        )
        and base.mb.has_block(child, "FVKernels/r31_phi_diffusion")
        and base.mb.has_block(child, "FVKernels/r31_phi_charge_source")
    )
    checks["heavy_parent_has_no_poisson"] = (
        not base.mb.has_block(parent, "Variables/potential_plasma")
        and not base.mb.has_block(parent, "FVKernels/r31_phi_diffusion")
        and not base.mb.has_block(parent, "FVKernels/r31_phi_charge_source")
    )
    checks["electron_first_execute_point"] = (
        base.mp.unquote(base.mp.get_parameter(parent, "MultiApps/electron", "execute_on"))
        == "TIMESTEP_BEGIN"
    )
    checks["single_fast_multiapp"] = set(base._children(parent, "MultiApps")) == {
        "MultiApps/electron"
    }
    checks["strict_lookup_policy_retained"] = all(
        base.mp.get_parameter(child, path, "clamp_mean_energy_to_table") is None
        for path in base._children(child, "FunctorMaterials")
    )

    result["failed_checks"] = sorted(key for key, ok in checks.items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
