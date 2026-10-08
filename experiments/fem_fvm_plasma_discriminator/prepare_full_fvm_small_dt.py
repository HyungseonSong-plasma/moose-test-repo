#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import prepare_cases as base

CASES = {
    "dt001": 1.0e-11,
    "dt002": 2.0e-11,
    "dt003": 3.0e-11,
}
NSTEPS = 100


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"expected one {label}, found {count}")
    return new


def build_case(case_id: str) -> str:
    if case_id not in CASES:
        raise ValueError(f"unknown case {case_id}")

    dt = CASES[case_id]
    end_time = dt * NSTEPS
    text = base.fvm()

    text = replace_once(text, r"^  dt = .*?$", f"  dt = {dt:.17g}", "dt")
    text = replace_once(text, r"^  num_steps = .*?$", f"  num_steps = {NSTEPS}", "num_steps")
    text = replace_once(text, r"^  end_time = .*?$", f"  end_time = {end_time:.17g}", "end_time")

    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate full-FVM very-small-dt discriminator cases.")
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()

    dt = CASES[args.case]
    end_time = dt * NSTEPS
    out = Path(base.HERE) / f"full_fvm_{args.case}_100steps.i"
    out.write_text(build_case(args.case), encoding="utf-8")

    print(f"wrote {out}")
    print("discretization: full FVM for log_ne, log_ni, log_energy, potential")
    print(f"dt={dt:.17g} s = {dt*1e9:g} ns")
    print(f"steps={NSTEPS}")
    print(f"end_time={end_time:.17g} s = {end_time*1e9:g} ns")


if __name__ == "__main__":
    main()
