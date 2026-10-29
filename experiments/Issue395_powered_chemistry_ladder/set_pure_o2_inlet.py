#!/usr/bin/env python3
"""Issue395 pure O2(X) inlet, mass conserving and exact-input guarded.

O2(X) is the residual mass fraction; its bookkeeping receiver is total inflow,
while O2(a), O(3P), O(1D) scalar-flux receivers become zero.
Do not alter the initial mixture or total mass flow.
"""
import argparse
import math
import re
from pathlib import Path

TOTAL_MDOT = 1.9395986970295842e-06
BASE = {
    "neutral_inlet_mdot": TOTAL_MDOT,
    "neutral_inlet_mdot_O2": 1.3997103999182566e-06,
    "neutral_inlet_mdot_O2s": 9.9979314279875487e-08,
    "neutral_inlet_mdot_O": 1.9995862855975097e-07,
    "neutral_inlet_mdot_Os": 2.3995035427170116e-07,
}
PURE = {
    "neutral_inlet_mdot": TOTAL_MDOT,
    "neutral_inlet_mdot_O2": TOTAL_MDOT,
    "neutral_inlet_mdot_O2s": 0.0,
    "neutral_inlet_mdot_O": 0.0,
    "neutral_inlet_mdot_Os": 0.0,
}
RECEIVER = re.compile(
    r"(?ms)^  \[(?P<name>neutral_inlet_mdot(?:_O2s|_O2|_Os|_O)?)\]\n(?P<body>.*?)^  \[\]\n")
DEFAULT = re.compile(r"(?m)^(?P<indent>[ \t]*)default[ \t]*=[ \t]*(?P<value>[^\s#]+)")
BC = re.compile(r"(?ms)^  \[(?P<name>neutral_inlet_(?:O2s|O|Os))\]\n(?P<body>.*?)^  \[\]\n")


def receiver_values(source):
    found = {}
    matches = list(RECEIVER.finditer(source))
    if len(matches) != len(BASE):
        raise ValueError("Missing or duplicated inlet Receiver blocks")
    for m in matches:
        name, body = m.group("name"), m.group("body")
        if name in found or name not in BASE:
            raise ValueError("Duplicate/unexpected inlet Receiver: " + name)
        if len(re.findall(r"(?m)^\s*type\s*=\s*Receiver\s*$", body)) != 1:
            raise ValueError("Receiver type mismatch: " + name)
        fields = list(DEFAULT.finditer(body))
        if len(fields) != 1:
            raise ValueError("Receiver default is not unique: " + name)
        v = float(fields[0].group("value"))
        if not math.isfinite(v) or v < 0:
            raise ValueError("Invalid inlet mass flow: " + name)
        found[name] = v
    if set(found) != set(BASE):
        raise ValueError("Inlet Receiver keys changed")
    return found


def verify_bc(source):
    expected = {
        "neutral_inlet_O2s": ("w_O2s", "neutral_inlet_mdot_O2s"),
        "neutral_inlet_O": ("w_O", "neutral_inlet_mdot_O"),
        "neutral_inlet_Os": ("w_Os", "neutral_inlet_mdot_Os"),
    }
    found = list(BC.finditer(source))
    if len(found) != 3 or set(m.group("name") for m in found) != set(expected):
        raise ValueError("Neutral inlet scalar BC ownership mismatch")
    for m in found:
        var, mdot = expected[m.group("name")]
        tokens = ("type = WCNSFVScalarFluxBC", f"variable = {var}",
                  f"passive_scalar = {var}", "boundary = inlet", f"scalar_flux_pp = {mdot}")
        for token in tokens:
            if len(re.findall(r"(?m)^\s*" + re.escape(token) + r"\s*$", m.group("body"))) != 1:
                raise ValueError(f"{m.group('name')} BC contract missing: {token}")
    if "property_name = w_O2_constraint" not in source or "expression = '1.0-s-o-a'" not in source:
        raise ValueError("Constrained O2(X) closure absent")
    if "  [neutral_inlet_O2]\n" in source:
        raise ValueError("Unexpected explicit O2(X) inlet scalar flux")
    mass = re.findall(r"(?ms)^  \[neutral_inlet_mass\]\n(.*?)^  \[\]\n", source)
    if len(mass) != 1 or "mdot_pp = neutral_inlet_mdot" not in mass[0]:
        raise ValueError("Total inlet mass BC changed")


def verify(source, required):
    verify_bc(source)
    actual = receiver_values(source)
    for name, ref in required.items():
        if not math.isclose(actual[name], ref, rel_tol=2e-14, abs_tol=1e-21):
            raise ValueError(f"Inlet mass flux mismatch: {name}: {actual[name]} vs {ref}")
    if not math.isclose(
        sum(v for k,v in actual.items() if k != "neutral_inlet_mdot"),
        actual["neutral_inlet_mdot"], rel_tol=2e-13, abs_tol=1e-21
    ):
        raise ValueError("Inlet total != sum species fluxes")


def apply(original):
    verify(original, BASE)
    output = original
    for name, value in PURE.items():
        if name == "neutral_inlet_mdot":
            continue
        m = [x for x in RECEIVER.finditer(output) if x.group("name") == name]
        if len(m) != 1:
            raise ValueError("Nonunique receiver " + name)
        d = list(DEFAULT.finditer(m[0].group("body")))
        if len(d) != 1:
            raise ValueError("Nonunique receiver default " + name)
        a = m[0].start("body") + d[0].start("value")
        b = m[0].start("body") + d[0].end("value")
        output = output[:a] + format(value, ".17g") + output[b:]
    verify(output, PURE)
    if output == original:
        raise ValueError("No modification")
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    source = a.input.read_text(encoding="utf-8")
    if a.verify:
        verify(source, PURE)
        print("ISSUE395_PURE_O2_INLET_VERIFY_PASS")
    else:
        modified = apply(source)
        a.input.write_text(modified, encoding="utf-8")
        print("ISSUE395_PURE_O2_INLET_EXACT_RECEIVERS_PASS")
        print("inlet_mass_fractions O2(X)=1 O2(a)=0 O(3P)=0 O(1D)=0")
        print(f"total_inlet_kg_s={TOTAL_MDOT:.17g}")


if __name__ == "__main__":
    main()
