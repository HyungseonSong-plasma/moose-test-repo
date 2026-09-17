#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    args = ap.parse_args()
    ne = args.ne
    if ne <= 0:
        raise SystemExit("--ne must be positive")

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
    (ROOT / "density_scan_parameters.json").write_text(
        "{\n"
        f'  "ne0_m3": {ne:.17g},\n'
        f'  "log_ce0": {log_ce:.17g},\n'
        f'  "w_O2p0": {w_o2p:.17g}\n'
        "}\n"
    )
    print(f"ne0={ne:.6e} m^-3")
    print(f"log_ce0={log_ce:.16e}")
    print(f"w_O2p0={w_o2p:.16e}")

if __name__ == "__main__":
    main()
