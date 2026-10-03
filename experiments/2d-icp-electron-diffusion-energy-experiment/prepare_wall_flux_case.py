#!/usr/bin/env python3
"""Prepare a controlled electron-energy wall-flux factor case."""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path


def rewrite_scalar(text: str, name: str, value: str) -> str:
    text, count = re.subn(
        rf"(?m)^  {re.escape(name)} = .*$",
        f"  {name} = {value}",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"failed to rewrite {name}: count={count}")
    return text


def rewrite_energy_factor(text: str, factor: float) -> str:
    if not math.isfinite(factor) or factor <= 0.0:
        raise SystemExit(f"energy factor must be finite and positive: {factor}")

    pattern = re.compile(
        r"(?ms)(  \[constants\]\n"
        r"    type = ADGenericFunctorMaterial\n"
        r"    prop_names = 'gas_pressure_Pa gas_temperature_K zero_phi energy_wall_te_factor'\n"
        r"    prop_values = ')[^']+(')"
    )
    replacement = (
        r"\g<1>1.333223684 300.0 0.0 "
        + f"{factor:.17g}"
        + r"\g<2>"
    )
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"failed to rewrite energy_wall_te_factor: count={count}")
    return text


def prepare(text: str, *, energy_factor: float) -> str:
    for name, value in (
        ("dt", "1.0e-9"),
        ("dtmin", "1.0e-9"),
        ("dtmax", "1.0e-9"),
        ("num_steps", "4"),
    ):
        text = rewrite_scalar(text, name, value)
    return rewrite_energy_factor(text, energy_factor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--energy-factor", type=float, required=True)
    args = parser.parse_args()

    text = prepare(args.input.read_text(), energy_factor=args.energy_factor)
    args.input.write_text(text)
    print(
        "WALL_FLUX_CASE_PREPARED "
        f"energy_factor={args.energy_factor:.17g} dt=1e-9 steps=4"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
