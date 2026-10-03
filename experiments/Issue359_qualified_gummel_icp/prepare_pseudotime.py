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


def main() -> int:
    p = argparse.ArgumentParser(description="Stage Issue359 four-input Gummel with independent heavy physical time and electron pseudo-time.")
    p.add_argument("case", type=Path)
    p.add_argument("--heavy-dt", type=float, default=1.0e-4)
    p.add_argument("--heavy-steps", type=int, default=10)
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

    # OUTER_MAIN owns physical time.  FullSolveMultiApp deliberately removes
    # the TransientMultiApp requirement that the Gummel driver catch up to the
    # parent physical clock.  Each heavy step therefore runs one complete,
    # independent pseudo-transient Gummel solve.
    outer_path = case / "input.i"
    outer = outer_path.read_text()
    outer = mp.upsert_parameter(outer, "MultiApps/gummel_driver", "type", "FullSolveMultiApp")
    outer = _remove_parameter_line(outer, "no_restore")
    outer = _remove_parameter_line(outer, "sub_cycling")
    outer = _set_executioner(outer, dt=args.heavy_dt, steps=args.heavy_steps)
    outer = mp.upsert_parameter(outer, "Outputs", "exodus", "true")
    outer_path.write_text(outer)

    # GUMMEL_DRIVER owns pseudo-time only.  Its local problem has solve=false;
    # each pseudo step performs the electron <-> Poisson fixed-point loop.
    driver_path = case / "gummel_driver.i"
    driver = driver_path.read_text()
    driver = _set_executioner(driver, dt=args.pseudo_dt, steps=args.pseudo_steps)
    driver_path.write_text(driver)

    # Inner electron and Poisson TransientMultiApps remain synchronized with
    # the Gummel driver's pseudo clock, never with the outer heavy clock.
    for name in ("electron_sub.i", "poisson_sub.i"):
        path = case / name
        text = _set_executioner(path.read_text(), dt=args.pseudo_dt, steps=args.pseudo_steps)
        path.write_text(text)

    checks = {
        "four_input_topology": all((case / n).is_file() for n in ("input.i", "gummel_driver.i", "electron_sub.i", "poisson_sub.i")),
        "outer_uses_full_solve_multiapp": mp.get_parameter(outer, "MultiApps/gummel_driver", "type") == "FullSolveMultiApp",
        "outer_subcycling_removed": "sub_cycling" not in outer,
        "outer_no_restore_removed": "no_restore" not in outer,
        "gummel_action_present": mb.has_block(driver, "GummelIteration/electron_poisson"),
        "physical_and_pseudo_dt_independent": args.heavy_dt != args.pseudo_dt,
        "heavy_dt_is_physical_1e_4": abs(args.heavy_dt - 1.0e-4) < 1.0e-18,
        "heavy_steps_10": args.heavy_steps == 10,
        "pseudo_dt_is_qualified_seed": abs(args.pseudo_dt - 5.6650790022617894e-11) < 1.0e-24,
        "pseudo_steps_20": args.pseudo_steps == 20,
    }
    failed = sorted(k for k, v in checks.items() if not v)
    contract = {
        "architecture": "four-input Gummel; outer physical heavy time + independent inner electron pseudo-time",
        "heavy_physical_dt_s": args.heavy_dt,
        "heavy_steps": args.heavy_steps,
        "heavy_end_time_s": args.heavy_dt * args.heavy_steps,
        "electron_pseudo_dt_s": args.pseudo_dt,
        "pseudo_steps_per_heavy_step": args.pseudo_steps,
        "pseudo_horizon_per_heavy_step_s": args.pseudo_dt * args.pseudo_steps,
        "outer_multiapp_type": "FullSolveMultiApp",
        "fast_state_restart_policy": "fresh full pseudo solve from staged initial fast state each heavy step",
        "electron_seed_policy": "retain frozen_current seed for architecture isolation",
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
