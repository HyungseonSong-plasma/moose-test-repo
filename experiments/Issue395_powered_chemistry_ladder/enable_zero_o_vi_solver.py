#!/usr/bin/env python3
"""Experimental positivity-constrained VI solve for exactly zero initial atomic O.

Preserve EI20 strict kinetics: do not clamp a negative O concentration or the
electron-impact rate. Change only the solver path by binding the solved FV
w_O mass-fraction variable to a PETSc variational inequality lower bound 0.

This is a NUMERICAL-REGIME DISCRIMINATOR, not a science-equivalent replay until
actual PhysicsApp runtime / charge / conservation and time histories pass.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

BOUND_NAME = "zero_o_vi_lower"
DUMMY = "zero_o_vi_bounds_dummy"
SOLVER = "vinewtonrsls"
AUX_BODY = f"""  [{DUMMY}]
    family = MONOMIAL
    order = CONSTANT
    fv = true
    block = plasma
  []
"""
BOUND_SECTION = f"""[Bounds]
  [{BOUND_NAME}]
    type = ConstantBounds
    variable = {DUMMY}
    bounded_variable = w_O
    bound_type = lower
    bound_value = 0.0
  []
[]
"""
INAME = "petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'"
VALUE = "petsc_options_value = 'preonly lu NONZERO'"
INAME_NEW = "petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type -snes_type'"
VALUE_NEW = "petsc_options_value = 'preonly lu NONZERO vinewtonrsls'"
SECTION = re.compile(r"(?ms)^\[(?P<name>AuxVariables|Executioner)\]\n(?P<body>.*?)^\[\]\n")


def section(text: str, name: str) -> re.Match[str]:
    matches = [m for m in SECTION.finditer(text) if m.group("name") == name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one [{name}], got {len(matches)}")
    return matches[0]


def verify(text: str) -> None:
    if "[Bounds]\n" not in text or text.count(BOUND_SECTION) != 1:
        raise ValueError("O positivity bounds missing or duplicated")
    aux = section(text, "AuxVariables")
    exe = section(text, "Executioner")
    if aux.group("body").count(AUX_BODY) != 1:
        raise ValueError("O positivity dummy variable missing")
    if exe.group("body").count(INAME_NEW) != 1 or exe.group("body").count(VALUE_NEW) != 1:
        raise ValueError("O VI SNES type is not configured")
    if "type = PhysicsElectronImpactRateMaterial" in text:
        raise ValueError("Generated base input unexpectedly includes kinetics overlays")


def apply(original: str) -> str:
    from set_zero_initial_atomic_o import verify_generated_input
    verify_generated_input(original)
    if any(s in original for s in ("[Bounds]\n", DUMMY, BOUND_NAME, SOLVER)):
        raise ValueError("Existing bounds or VI solver configuration detected")
    aux = section(original, "AuxVariables")
    exe = section(original, "Executioner")
    if exe.group("body").count(INAME) != 1 or exe.group("body").count(VALUE) != 1:
        raise ValueError("Unexpected original PETSc solver options")
    if "  solve_type = NEWTON\n" not in exe.group("body"):
        raise ValueError("Unexpected base nonlinear solver")
    if aux.group("body").count("  [") < 1:
        raise ValueError("Missing native D1 auxiliary diagnostics")

    # Precisely two existing option lines, one new Aux block and one Bound section.
    out = original[:exe.start("body")] + exe.group("body").replace(INAME, INAME_NEW).replace(VALUE, VALUE_NEW) + original[exe.end("body"):]
    aux = section(out, "AuxVariables")
    out = out[:aux.end("body")] + AUX_BODY + out[aux.end("body"):]
    exe = section(out, "Executioner")
    out = out[:exe.start()] + BOUND_SECTION + "\n" + out[exe.start():]
    verify(out)
    # The base unperturbed O=0 chemistry constraints are still required.
    verify_generated_input(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    original = args.input.read_text(encoding="utf-8")
    if args.verify:
        verify(original)
        from set_zero_initial_atomic_o import verify_generated_input
        verify_generated_input(original)
        print("ZERO_O_VI_SOLVER_VERIFY_PASS")
    else:
        new = apply(original)
        args.input.write_text(new, encoding="utf-8")
        print("ZERO_O_VI_SOLVER_BUILD_PASS")
        print("numerical_regime=PETSc_SNESVI_nonnegative_atomic_O")
        print("science_status=HOLD_NUMERICAL_SCHEME_AND_RATE_EXTRAPOLATION")


if __name__ == "__main__":
    main()
