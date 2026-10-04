#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
FROZEN = Path(__file__).resolve().parent / "frozen_current"
ICP_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
HEAVY_TRANSPORT = ROOT / "physics_app/ci/plasma_closures_oxygen_transport.txt"


def _set_executioner(text: str, *, dt: float, steps: int) -> str:
    end_time = dt * steps
    for key, value in (
        ("dt", f"{dt:.17g}"),
        ("dtmin", f"{dt:.17g}"),
        ("dtmax", f"{dt:.17g}"),
        ("end_time", f"{end_time:.17g}"),
        ("num_steps", str(steps)),
    ):
        text = mp.upsert_parameter(text, "Executioner", key, value)
    return text


def _remove_parameter_line(text: str, name: str) -> str:
    return re.sub(rf"(?m)^\s*{re.escape(name)}\s*=.*\n", "", text)


def _configure_one_sweep_pseudotime(driver: str) -> str:
    """Use pseudo-time itself as the electron-Poisson coupling iteration.

    Each pseudo step executes the electron MultiApp once at TIMESTEP_BEGIN and
    the Poisson MultiApp once at TIMESTEP_END.  No inner Gummel/fixed-point
    convergence loop is requested from the parent Transient executioner.
    """
    action = "GummelIteration/electron_poisson"
    driver = mp.upsert_parameter(driver, action, "manage_convergence", "false")

    # These parameters belong to the fully converged inner-Gummel formulation.
    # Removing them restores the ordinary one-pass MultiApp execution used by
    # the existing two-subapp smoke case.
    for name in (
        "convergence_name",
        "delta_phi_postprocessor",
        "delta_phi_abs_tol",
        "fixed_point_min_its",
        "fixed_point_max_its",
        "fixed_point_rel_tol",
        "fixed_point_abs_tol",
        "accept_on_max_fixed_point_iteration",
        "fixed_point_algorithm",
        "transformed_variables",
        "multiapp_fixed_point_convergence",
    ):
        driver = _remove_parameter_line(driver, name)

    # Retain the existing pre/post-Poisson potential-change diagnostic, but
    # evaluate it once per pseudo timestep instead of on a fixed-point flag.
    driver = mp.upsert_parameter(
        driver,
        "Postprocessors/fp_delta_phi_max",
        "execute_on",
        "'TIMESTEP_END'",
    )
    return driver


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Stage Issue359 four-input one-sweep electron-Poisson pseudotime with "
            "independent heavy physical time and fast pseudo-time."
        )
    )
    p.add_argument("case", type=Path)
    p.add_argument("--heavy-dt", type=float, default=1.0e-4)
    p.add_argument("--heavy-steps", type=int, default=1)
    p.add_argument("--pseudo-dt", type=float, default=5.6650790022617894e-11)
    p.add_argument("--pseudo-steps", type=int, default=20)
    args = p.parse_args()

    if args.heavy_dt <= 0 or args.pseudo_dt <= 0:
        raise SystemExit("heavy/pseudo dt must be positive")
    if args.heavy_steps <= 0 or args.pseudo_steps <= 0:
        raise SystemExit("heavy/pseudo steps must be positive")

    case = args.case.resolve()
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)

    for name in ("input.i", "gummel_driver.i", "electron_sub.i", "poisson_sub.i", "o2_elastic.txt"):
        shutil.copy2(FROZEN / name, case / name)
    shutil.copy2(ICP_SOURCE / "qvt.msh", case / "qvt.msh")
    shutil.copy2(ICP_SOURCE / "electron_moments.txt", case / "electron_moments.txt")
    shutil.copy2(HEAVY_TRANSPORT, case / "transport_data.txt")

    # OUTER_MAIN owns physical time. FullSolveMultiApp deliberately removes
    # the TransientMultiApp requirement that the fast driver catch up to the
    # parent physical clock. Each heavy step therefore runs one complete,
    # independent fast pseudo-transient solve.
    outer_path = case / "input.i"
    outer = outer_path.read_text()
    outer = mp.upsert_parameter(outer, "MultiApps/gummel_driver", "type", "FullSolveMultiApp")
    outer = _remove_parameter_line(outer, "no_restore")
    outer = _remove_parameter_line(outer, "sub_cycling")
    outer = _set_executioner(outer, dt=args.heavy_dt, steps=args.heavy_steps)

    # Persist evidence at every completed heavy step. Exodus gives a directly
    # inspectable field snapshot; checkpoint gives restart state if the solve
    # step is terminated by the CI step-level timeout.
    outer = mp.upsert_parameter(outer, "Outputs", "exodus", "true")
    outer = mp.upsert_parameter(outer, "Outputs", "checkpoint", "true")
    outer = mp.upsert_parameter(outer, "Outputs", "execute_on", "'INITIAL TIMESTEP_END'")
    outer_path.write_text(outer)

    # The driver owns pseudo-time only.  Pseudo-time itself closes the fast
    # electron-Poisson coupling: one electron solve followed by one Poisson
    # solve per pseudo step, with no nested Gummel fixed-point convergence.
    driver_path = case / "gummel_driver.i"
    driver = driver_path.read_text()
    driver = _set_executioner(driver, dt=args.pseudo_dt, steps=args.pseudo_steps)
    driver = _configure_one_sweep_pseudotime(driver)
    driver_path.write_text(driver)

    # Inner electron and Poisson TransientMultiApps remain synchronized with
    # the driver's pseudo clock, never with the outer heavy clock.
    for name in ("electron_sub.i", "poisson_sub.i"):
        path = case / name
        text = _set_executioner(path.read_text(), dt=args.pseudo_dt, steps=args.pseudo_steps)
        path.write_text(text)

    fixed_point_controls = (
        "fixed_point_min_its",
        "fixed_point_max_its",
        "fixed_point_rel_tol",
        "fixed_point_abs_tol",
        "fixed_point_algorithm",
        "multiapp_fixed_point_convergence",
    )
    checks = {
        "four_input_topology": all((case / n).is_file() for n in ("input.i", "gummel_driver.i", "electron_sub.i", "poisson_sub.i")),
        "outer_uses_full_solve_multiapp": mp.get_parameter(outer, "MultiApps/gummel_driver", "type") == "FullSolveMultiApp",
        "outer_subcycling_removed": "sub_cycling" not in outer,
        "outer_no_restore_removed": "no_restore" not in outer,
        "gummel_action_present": mb.has_block(driver, "GummelIteration/electron_poisson"),
        "inner_gummel_convergence_disabled": mp.get_parameter(driver, "GummelIteration/electron_poisson", "manage_convergence") == "false",
        "inner_fixed_point_controls_removed": all(name not in driver for name in fixed_point_controls),
        "delta_phi_diagnostic_runs_per_pseudo_step": mp.get_parameter(driver, "Postprocessors/fp_delta_phi_max", "execute_on") == "'TIMESTEP_END'",
        "physical_and_pseudo_dt_independent": args.heavy_dt != args.pseudo_dt,
        "heavy_dt_is_physical_1e_4": abs(args.heavy_dt - 1.0e-4) < 1.0e-18,
        "heavy_steps_1": args.heavy_steps == 1,
        "pseudo_dt_is_qualified_seed": abs(args.pseudo_dt - 5.6650790022617894e-11) < 1.0e-24,
        "pseudo_steps_20": args.pseudo_steps == 20,
        "intermediate_exodus_enabled": mp.get_parameter(outer, "Outputs", "exodus") == "true",
        "checkpoint_enabled": mp.get_parameter(outer, "Outputs", "checkpoint") == "true",
        "heavy_step_output_schedule": mp.get_parameter(outer, "Outputs", "execute_on") == "'INITIAL TIMESTEP_END'",
    }
    failed = sorted(k for k, v in checks.items() if not v)
    contract = {
        "architecture": "four-input one-sweep pseudotime; outer physical heavy time + independent fast electron-Poisson pseudo-time",
        "coupling_policy": "one electron solve + one Poisson solve per pseudo step; no inner Gummel fixed-point convergence",
        "heavy_physical_dt_s": args.heavy_dt,
        "heavy_steps": args.heavy_steps,
        "heavy_end_time_s": args.heavy_dt * args.heavy_steps,
        "electron_pseudo_dt_s": args.pseudo_dt,
        "pseudo_steps_per_heavy_step": args.pseudo_steps,
        "pseudo_horizon_per_heavy_step_s": args.pseudo_dt * args.pseudo_steps,
        "outer_multiapp_type": "FullSolveMultiApp",
        "fast_state_restart_policy": "fresh full pseudo solve from staged initial fast state each heavy step",
        "electron_seed_policy": "retain frozen_current seed for architecture isolation",
        "timeout_evidence_policy": "outer Exodus and checkpoint at every completed heavy TIMESTEP_END",
        "checks": checks,
        "failed_checks": failed,
        "status": "PASS" if not failed else "FAIL",
    }
    (case / "pseudo_time_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps(contract, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(f"pseudo-time contract failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
