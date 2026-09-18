#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

NA = 6.02214076e23
RHO = 1.3793506167141378e-5
M_O2P = 0.032

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one occurrence, found {count}")
    return text.replace(old, new)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ne", type=float, required=True)
    ap.add_argument("--dt-e", type=float, required=True)
    ap.add_argument("--steps", type=int, default=20)
    args = ap.parse_args()

    ne = args.ne
    dt_e = args.dt_e
    steps = args.steps
    if ne <= 0:
        raise SystemExit("--ne must be positive")
    if dt_e <= 0:
        raise SystemExit("--dt-e must be positive")
    if steps <= 0:
        raise SystemExit("--steps must be positive")

    target_end = steps * dt_e
    time_tol = max(dt_e * 1.0e-6, 1.0e-30)
    log_ce = math.log(ne / NA)
    w_o2p = ne * M_O2P / (RHO * NA)

    heavy = (ROOT / "heavy_parent.i").read_text()
    electron = (ROOT / "electron_sub.i").read_text()
    poisson = (ROOT / "poisson_sub.i").read_text()

    heavy = replace_once(
        heavy,
        "initial_condition = 0.00038523381586724926",
        f"initial_condition = {w_o2p:.17g}",
        "heavy w_O2p",
    )
    heavy = replace_once(
        heavy,
        "initial_condition = 1.0e17",
        f"initial_condition = {ne:.17g}",
        "heavy electron_density_from_sub",
    )
    heavy = replace_once(
        heavy,
        "input_files = electron_sub.i",
        "input_files = electron_sub_scan.i",
        "heavy electron input",
    )
    heavy = replace_once(
        heavy,
        "  dt = 1.0e-9\n  end_time = 1.0e-9",
        (
            f"  dt = {target_end:.17g}\n"
            f"  dtmin = {target_end:.17g}\n"
            f"  dtmax = {target_end:.17g}\n"
            f"  timestep_tolerance = {time_tol:.17g}\n"
            f"  end_time = {target_end:.17g}\n"
            "  num_steps = 1"
        ),
        "heavy 20-step sync horizon",
    )

    electron = replace_once(
        electron,
        "  dt = 1.0e-10\n  end_time = 1.0e-9",
        (
            f"  dt = {dt_e:.17g}\n"
            f"  dtmin = {dt_e:.17g}\n"
            f"  dtmax = {dt_e:.17g}\n"
            f"  timestep_tolerance = {time_tol:.17g}\n"
            f"  end_time = {target_end:.17g}\n"
            f"  num_steps = {steps}"
        ),
        "electron runtime contract",
    )
    electron = replace_once(
        electron,
        "initial_condition = -15.610953362044896",
        f"initial_condition = {log_ce:.17g}",
        "electron log_e",
    )
    electron = replace_once(
        electron,
        "initial_condition = 0.00038523381586724926",
        f"initial_condition = {w_o2p:.17g}",
        "electron w_O2p_h",
    )
    electron = replace_once(
        electron,
        "initial_condition = 1.0e17",
        f"initial_condition = {ne:.17g}",
        "electron density copy",
    )
    electron = replace_once(
        electron,
        "input_files = poisson_sub.i",
        "input_files = poisson_sub_scan.i",
        "electron poisson input",
    )

    poisson = replace_once(
        poisson,
        "initial_condition = -15.610953362044896",
        f"initial_condition = {log_ce:.17g}",
        "poisson log_e_frozen",
    )
    poisson = replace_once(
        poisson,
        "initial_condition = 0.00038523381586724926",
        f"initial_condition = {w_o2p:.17g}",
        "poisson w_O2p_frozen",
    )

    (ROOT / "heavy_parent_scan.i").write_text(heavy)
    (ROOT / "electron_sub_scan.i").write_text(electron)
    (ROOT / "poisson_sub_scan.i").write_text(poisson)
    parameters = {
        "ne0_m3": ne,
        "log_ce0": log_ce,
        "w_O2p0": w_o2p,
        "requested_dt_e_s": dt_e,
        "expected_electron_steps": steps,
        "expected_end_time_s": target_end,
        "electron_dtmin_s": dt_e,
        "electron_dtmax_s": dt_e,
        "timestep_tolerance_s": time_tol,
        "parent_dt_s": target_end,
        "parent_dtmin_s": target_end,
        "parent_dtmax_s": target_end,
    }
    (ROOT / "density_scan_parameters.json").write_text(
        json.dumps(parameters, indent=2, sort_keys=True) + "\n"
    )

    print(f"ne0={ne:.6e} m^-3")
    print(f"requested_dt_e={dt_e:.16e} s")
    print(f"expected_steps={steps}")
    print(f"expected_end_time={target_end:.16e} s")
    print(f"log_ce0={log_ce:.16e}")
    print(f"w_O2p0={w_o2p:.16e}")


if __name__ == "__main__":
    main()
