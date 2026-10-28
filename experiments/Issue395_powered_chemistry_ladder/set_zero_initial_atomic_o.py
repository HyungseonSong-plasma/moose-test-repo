#!/usr/bin/env python3
"""Bounded O(3P) initial-state sensitivity change on generated ICP input only.

This is a one-variable initial composition intervention. No model source,
other input values, mesh, RF, EEDF, timestep, wall or solver is altered.
O2 is the constrained residual mass fraction, so it increases by old w_O.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

ORIGINAL_W_O = 0.10309278350515465
O_MASS_FRACTION = 0.0
IC_BLOCK = re.compile(r"(?ms)^  \[w_O\]\n(?P<body>.*?)^  \[\]\n")
IC_VALUE = re.compile(r"(?m)^(?P<indent>\s*)initial_condition\s*=\s*(?P<value>[^\n#]+)(?P<end>\n)")
CONSTRAINT = (
    "property_name = w_O2_constraint",
    "functor_names = 'w_O2s w_O w_Os'",
    "expression = '1.0-s-o-a'",
)
REQUIRED = ("[log_ne]", "[log_ni]", "[log_energy]", "[w_Os]", "[w_O2s]")


def change_generated_input(original: str) -> str:
    """Alter exactly one generated [w_O] initial_condition line, fail closed."""
    for token in (*CONSTRAINT, *REQUIRED):
        if token not in original:
            raise ValueError(f"required baseline input token missing: {token}")

    blocks = list(IC_BLOCK.finditer(original))
    if len(blocks) != 1:
        raise ValueError(f"expected exactly one top-level w_O variable block; got {len(blocks)}")
    block = blocks[0]
    body = block.group("body")
    matches = list(IC_VALUE.finditer(body))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one w_O initial_condition; got {len(matches)}")
    ic = matches[0]
    try:
        actual = float(ic.group("value").strip())
    except ValueError as exc:
        raise ValueError("non-numeric initial O baseline") from exc
    if not math.isclose(actual, ORIGINAL_W_O, rel_tol=0.0, abs_tol=2e-16):
        raise ValueError(f"unexpected initial O mass fraction {actual}, expected {ORIGINAL_W_O}")

    old_line = ic.group(0)
    new_line = f"{ic.group('indent')}initial_condition = {O_MASS_FRACTION:.1f}\n"
    new_body = body[:ic.start()] + new_line + body[ic.end():]
    result = original[:block.start("body")] + new_body + original[block.end("body"):]
    if result.replace(new_line, old_line, 1) != original:
        raise ValueError("nonlocal input mutation detected")
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out", type=Path, help="Defaults to same generated input")
    args = p.parse_args()
    old = args.input.read_text(encoding="utf-8")
    new = change_generated_input(old)
    dest = args.out or args.input
    dest.write_text(new, encoding="utf-8")
    print("INITIAL_O_ZERO_EXACT_ONE_LINE_PASS")
    print(f"original_w_O={ORIGINAL_W_O:.17g}")
    print("new_w_O=0.0")
    print(f"constrained_w_O2_mass_fraction_delta=+{ORIGINAL_W_O:.17g}")
    print(f"output={dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
