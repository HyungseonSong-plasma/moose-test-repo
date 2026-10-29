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
IC_VALUE = re.compile(r"(?m)^(?P<indent>[ \t]*)initial_condition[ \t]*=[ \t]*(?P<value>[^\n#]+)(?P<end>\n)")
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

    if len(re.findall(r"(?m)^  \[w_O\][ \t]*$", original)) != 1:
        raise ValueError("duplicate or absent w_O block headings")
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
    # Verify the inverse at the exact w_O line offset: other species may
    # legitimately contain identical initial_condition = 0.0 text earlier.
    at = block.start("body") + ic.start()
    if result[:at] + old_line + result[at + len(new_line):] != original:
        raise ValueError("nonlocal input mutation detected")
    return result


def verify_generated_input(text: str) -> None:
    if any(token not in text for token in (*CONSTRAINT, *REQUIRED)):
        raise ValueError("zero-O input lost baseline chemistry or state")
    if len(re.findall(r"(?m)^  \[w_O\][ \t]*$", text)) != 1:
        raise ValueError("zero-O input has duplicate or absent w_O block headings")
    blocks = list(IC_BLOCK.finditer(text))
    if len(blocks) != 1:
        raise ValueError("zero-O input must have exactly one w_O block")
    values = list(IC_VALUE.finditer(blocks[0].group("body")))
    if len(values) != 1 or values[0].group("value").strip() != "0.0":
        raise ValueError("zero-O input must have exact initial_condition = 0.0")



# Exact model: initial uniform pressure, constant gas temperature and
# constrained neutral oxygen mixture.  w_Os is already a separately solved
# O(1D) mass fraction.  No boundary inlet condition is changed.
AVOGADRO = 6.02214076e23
R_GAS_MODEL = 8.31446
M_O_KG_MOL = 0.016
M_O2_KG_MOL = 0.032
EXPECTED_O1D_INITIAL = 0.12371134020618557
EXPECTED_O2S_INITIAL = 0.051546391752577324

def _baseline_number_density_constants(text: str) -> tuple[float, float, float]:
    """Extract exact p, T and excited-O fraction; audit model mixture law."""
    import re
    required = (
        "expression = '1.0-s-o-a'",
        "expression = '1.0/(m0/0.032+m1/0.032+m2/0.016+m3/0.016)'",
        "expression = 'prs*mol/(8.31446*tmp)'",
        "functor_names = 'p Mn_neutral T_g_fixed'",
        "prop_names = 'p_fixed T_g_fixed ion_mobility ion_diffusion",
    )
    for token in required:
        if token not in text:
            raise ValueError("initial-density conversion model contract missing: " + token)
    const = re.search(
        r"(?ms)^  \[constants\]\n(?P<body>.*?)^  \[\]\n", text)
    if const is None:
        raise ValueError("missing model constants block")
    vals = re.search(r"(?m)^\s*prop_values\s*=\s*'([^']+)'", const.group("body"))
    if vals is None:
        raise ValueError("missing pressure and temperature constants")
    p, tg = [float(v) for v in vals.group(1).split()[:2]]
    if not (math.isfinite(p) and p > 0 and math.isfinite(tg) and tg > 0):
        raise ValueError("invalid neutral pressure or temperature")
    def species_ic(name: str) -> float:
        blocks = list(re.finditer(r"(?ms)^  \["+re.escape(name)+r"\]\n(.*?)^  \[\]\n", text))
        if len(blocks) != 1:
            raise ValueError(f"missing/duplicate {name} species initial block")
        ic = IC_VALUE.findall(blocks[0].group(1))
        if len(ic) != 1:
            raise ValueError(f"missing/duplicate {name} initial condition")
        return float(ic[0][1].strip())
    os_fraction, o2s_fraction = species_ic("w_Os"), species_ic("w_O2s")
    if not math.isclose(os_fraction, EXPECTED_O1D_INITIAL, rel_tol=0.0, abs_tol=2e-16):
        raise ValueError("O(1D) initial fraction changed from baseline")
    if not math.isclose(o2s_fraction, EXPECTED_O2S_INITIAL, rel_tol=0.0, abs_tol=2e-16):
        raise ValueError("O2(a1Delta) initial fraction changed from baseline")
    return p, tg, os_fraction


def initial_o_number_density_from_fraction(w: float, *, p: float, tg: float, os_fraction: float) -> float:
    """Evaluate the actual mixture EOS, not fixed-rho approximation."""
    if not (0 <= w < 1 - os_fraction - EXPECTED_O2S_INITIAL):
        raise ValueError("invalid initial O fraction")
    o2s_fraction = EXPECTED_O2S_INITIAL
    o2_fraction = 1 - os_fraction - o2s_fraction - w
    Mn = 1 / (o2_fraction/M_O2_KG_MOL +
              o2s_fraction/M_O2_KG_MOL + w/M_O_KG_MOL + os_fraction/M_O_KG_MOL)
    rho = p * Mn / (R_GAS_MODEL * tg)
    return rho * w * AVOGADRO / M_O_KG_MOL


def target_o_mass_fraction(target_n_m3: float, *, p: float, tg: float, os_fraction: float) -> float:
    """Analytical inversion of rho(w)*w*N_A/M_O = target_n_m3."""
    if not math.isfinite(target_n_m3) or target_n_m3 <= 0:
        raise ValueError("initial target density must be strictly positive")
    n_scale = (2 * p * AVOGADRO) / (R_GAS_MODEL * tg)
    if target_n_m3 >= n_scale:
        raise ValueError("target O density exceeds admissible mixture EOS")
    w = target_n_m3 * (1 + os_fraction) / (n_scale - target_n_m3)
    check = initial_o_number_density_from_fraction(
        w, p=p, tg=tg, os_fraction=os_fraction)
    if not math.isclose(check, target_n_m3, rel_tol=2e-14, abs_tol=0):
        raise ValueError("mixture EOS inversion failed")
    return w


def change_to_target_number_density(original: str, target_n_m3: float) -> str:
    p, tg, os_fraction = _baseline_number_density_constants(original)
    w = target_o_mass_fraction(target_n_m3, p=p, tg=tg, os_fraction=os_fraction)
    new = change_generated_input(original)
    block = list(IC_BLOCK.finditer(new))[0]
    ic = list(IC_VALUE.finditer(block.group("body")))[0]
    old_line = ic.group(0)
    new_line = f"{ic.group('indent')}initial_condition = {w:.17g}\n"
    at = block.start("body") + ic.start()
    changed = new[:at] + new_line + new[at+len(old_line):]
    verify_target_number_density(changed, target_n_m3)
    return changed


def verify_target_number_density(text: str, target_n_m3: float) -> None:
    p, tg, os_fraction = _baseline_number_density_constants(text)
    block = list(IC_BLOCK.finditer(text))
    if len(block) != 1:
        raise ValueError("not exactly one O3P variable")
    ic = list(IC_VALUE.finditer(block[0].group("body")))
    if len(ic) != 1:
        raise ValueError("not exactly one initial O3P fraction")
    w = float(ic[0].group("value"))
    check = initial_o_number_density_from_fraction(
        w, p=p, tg=tg, os_fraction=os_fraction)
    if not math.isclose(check, target_n_m3, rel_tol=2e-14, abs_tol=0):
        raise ValueError(f"initial O3P number density mismatch: {check}, wanted {target_n_m3}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out", type=Path, help="Defaults to same generated input")
    p.add_argument("--verify", action="store_true", help="Read-only zero-state check")
    p.add_argument("--target-number-density", type=float, default=None,
                   help="Set/verify O(3P) number density [m^-3], preserving all other ICs")
    args = p.parse_args()
    old = args.input.read_text(encoding="utf-8")
    if args.target_number_density is not None:
        target = args.target_number_density
        if args.verify:
            verify_target_number_density(old, target)
            print("INITIAL_O_TARGET_DENSITY_VERIFICATION_PASS")
            return 0
        updated = change_to_target_number_density(old, target)
        dest = args.out or args.input
        dest.write_text(updated, encoding="utf-8")
        p_value, tg, os = _baseline_number_density_constants(updated)
        w = target_o_mass_fraction(target, p=p_value, tg=tg, os_fraction=os)
        print("INITIAL_O_TARGET_DENSITY_EXACT_ONE_LINE_PASS")
        print(f"initial_O3P_number_density_m3={target:.17g}")
        print(f"initial_w_O={w:.17g}")
        print(f"output={dest}")
        return 0
    if args.verify:
        verify_generated_input(old)
        print("INITIAL_O_ZERO_VERIFICATION_PASS")
        return 0
    new = change_generated_input(old)
    verify_generated_input(new)
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
