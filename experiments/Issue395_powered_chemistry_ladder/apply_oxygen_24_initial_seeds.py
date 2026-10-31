#!/usr/bin/env python3
"""Set exact charged density seeds and minority-neutral NUMBER fractions for O2 ICP.

Electron/O2+ start at 1e15 m^-3, O+/O- at 1e12 m^-3.
O2(a1Delta), O(3P), and O(1D) each start at x=1e-5 (number/mole fraction).
O2(X) is the residual x=0.99997, NOT another 1e-5 species.
The tracked neutral Variables are mass fractions; charged log states are
ln(c_molar [mol/m^3]). This patch only changes their initial_condition values.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

N_A = 6.02214076e23
SEEDS_M3 = {"log_ne": 1e15, "log_ni": 1e15, "log_nop": 1e12, "log_nm": 1e12}
MINOR_NUMBER_FRACTIONS = {"w_O2s": 1e-5, "w_O": 1e-5, "w_Os": 1e-5}
MOLAR_MASSES = {"O2_X": 0.032, "w_O2s": 0.032, "w_O": 0.016, "w_Os": 0.016}
X_O2_X = 1.0 - sum(MINOR_NUMBER_FRACTIONS.values())
MEAN_MOLAR_MASS = (X_O2_X * MOLAR_MASSES["O2_X"]
                   + sum(x * MOLAR_MASSES[k] for k, x in MINOR_NUMBER_FRACTIONS.items()))
NEUTRAL_MASS_FRACTIONS = {
    k: x * MOLAR_MASSES[k] / MEAN_MOLAR_MASS
    for k, x in MINOR_NUMBER_FRACTIONS.items()
}

CHARGED_BLOCK = re.compile(
    r"(?ms)^  \[(?P<name>log_ne|log_ni|log_nop|log_nm)\][ \t]*\n"
    r"(?P<body>.*?)^  \[\][ \t]*(?=\r?$)"
)
NEUTRAL_BLOCK = re.compile(
    r"(?ms)^  \[(?P<name>w_O2s|w_O|w_Os)\][ \t]*\n"
    r"(?P<body>.*?)^  \[\][ \t]*(?=\r?$)"
)
INITIAL = re.compile(
    r"(?m)^(?P<indent>[ \t]*)initial_condition[ \t]*=[ \t]*"
    r"(?P<value>[^\r\n#]+)(?P<comment>[ \t]*(?:#[^\r\n]*)?)$"
)


def _matches(text: str, pattern: re.Pattern, expected: dict) -> list:
    matches = list(pattern.finditer(text))
    present = [m.group("name") for m in matches]
    if set(present) != set(expected) or len(present) != len(expected):
        raise ValueError(f"missing or duplicate variable blocks: {present}")
    for match in matches:
        if len(list(INITIAL.finditer(match.group("body")))) != 1:
            raise ValueError(f"{match.group('name')}: require exactly one initial_condition")
    return matches


def _patch(text: str, pattern: re.Pattern, values: dict[str, float]) -> str:
    _matches(text, pattern, values)

    def sub(m: re.Match) -> str:
        body = m.group("body")
        value = values[m.group("name")]
        updated = INITIAL.sub(
            lambda q: f"{q.group('indent')}initial_condition = {value:.17g}{q.group('comment')}",
            body, count=1
        )
        return f"  [{m.group('name')}]\n{updated}  []"

    return pattern.sub(sub, text)


def verify_neutrals(text: str) -> dict[str, float]:
    """P0: validate all three neutral ICs as number fractions, not mass fractions."""
    matches = _matches(text, NEUTRAL_BLOCK, MINOR_NUMBER_FRACTIONS)
    mass = {}
    for match in matches:
        name = match.group("name")
        value = float(next(INITIAL.finditer(match.group("body"))).group("value").strip())
        if not math.isfinite(value) or not (0.0 < value < 1.0):
            raise ValueError(f"{name}: invalid neutral mass fraction {value}")
        mass[name] = value
    mass_o2 = 1.0 - sum(mass.values())
    if not 0.0 < mass_o2 < 1.0:
        raise ValueError(f"O2(X): invalid constrained remainder {mass_o2}")
    denom = mass_o2 / MOLAR_MASSES["O2_X"] + sum(
        mass[k] / MOLAR_MASSES[k] for k in MINOR_NUMBER_FRACTIONS
    )
    inferred = {k: (mass[k] / MOLAR_MASSES[k]) / denom for k in mass}
    inferred["O2_X"] = (mass_o2 / MOLAR_MASSES["O2_X"]) / denom
    for name, target in MINOR_NUMBER_FRACTIONS.items():
        if not math.isclose(inferred[name], target, rel_tol=1e-10, abs_tol=1e-14):
            raise ValueError(f"{name}: P0 number fraction mismatch: {inferred[name]} != {target}")
    if not math.isclose(inferred["O2_X"], X_O2_X, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("O2(X): constrained number fraction mismatch")
    return inferred


def verify_charged(text: str) -> None:
    for match in _matches(text, CHARGED_BLOCK, SEEDS_M3):
        value = float(next(INITIAL.finditer(match.group("body"))).group("value").strip())
        n = math.exp(value) * N_A
        target = SEEDS_M3[match.group("name")]
        if not math.isclose(n, target, rel_tol=1e-12):
            raise ValueError(f"{match.group('name')}: P0 charged seed mismatch")


def apply(text: str) -> str:
    out = _patch(text, CHARGED_BLOCK, {
        name: math.log(n / N_A) for name, n in SEEDS_M3.items()
    })
    out = _patch(out, NEUTRAL_BLOCK, NEUTRAL_MASS_FRACTIONS)
    verify_charged(out)
    verify_neutrals(out)
    return out


def self_test() -> None:
    names = list(SEEDS_M3) + list(MINOR_NUMBER_FRACTIONS)
    inp = "[Variables]\n" + "".join(
        f"  [{name}]\n    type = MooseVariableFVReal\n"
        f"    initial_condition = 0.25\n    block = plasma\n  []\n" for name in names
    ) + "[]\n"
    out = apply(inp)
    verify_charged(out)
    verify_neutrals(out)
    if apply(out) != out:
        raise AssertionError("neutral-seed transformation not idempotent")
    bad = out.replace(
        f"initial_condition = {NEUTRAL_MASS_FRACTIONS['w_O']:.17g}",
        "initial_condition = 0.10309278350515465", 1
    )
    try:
        verify_neutrals(bad)
    except ValueError as exc:
        if "P0 number fraction mismatch" not in str(exc):
            raise
    else:
        raise AssertionError("P0 failed to reject old inherited atomic O density")
    for name in MINOR_NUMBER_FRACTIONS:
        missing = out.replace(f"  [{name}]\n", "  [removed]\n", 1)
        try:
            verify_neutrals(missing)
        except ValueError:
            continue
        raise AssertionError(f"P0 failed to reject missing {name}")
    print("OXYGEN24_NEUTRAL_SEED_P0_SELFTEST_PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--base-input", type=Path)
    group.add_argument("--check-input", type=Path)
    group.add_argument("--self-test", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.check_input is not None:
        if args.output:
            p.error("--output not accepted with --check-input")
        text = args.check_input.read_text(encoding="utf-8")
        verify_charged(text)
        result = verify_neutrals(text)
        print("OXYGEN24_INITIAL_SEED_P0_PASS", result)
        return
    if args.output is None:
        p.error("--output required with --base-input")
    if args.base_input.resolve() == args.output.resolve():
        raise ValueError("do not overwrite prior reference input")
    out = apply(args.base_input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out, encoding="utf-8")
    print("OXYGEN24_INITIAL_SEEDS_APPLIED: charged=(1e15,1e15,1e12,1e12) m-3;"
          " x_O2a=x_O3P=x_O1D=1e-5; x_O2X=0.99997")


if __name__ == "__main__":
    main()
