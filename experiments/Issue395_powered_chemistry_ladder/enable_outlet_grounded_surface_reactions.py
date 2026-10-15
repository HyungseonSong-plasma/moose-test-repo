#!/usr/bin/env python3
"""Restore the Issue #395 outlet as a grounded reactive charged boundary.

This controlled discriminator keeps the neutral outlet model unchanged while
requiring the charged subsystem to use the baseline grounded outlet contract:

* potential: outlet remains in the zero-volt Dirichlet boundary set;
* electrons: add outlet to the thermal no-sheath particle wall BC;
* electron energy: add outlet to the thermal no-sheath energy wall BC;
* O2+, O-, O+: require outlet in the existing charged-species wall-reaction BCs.

No explicit sheath suppression factor is introduced.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

BLOCK_RE = re.compile(r"(?ms)^  \[(?P<name>[^\]\n]+)\]\n(?P<body>.*?)^  \[\]\n")
BOUNDARY_RE = re.compile(r"(?m)^(?P<indent>\s*)boundary\s*=\s*'?(?P<items>[^'\n]*)'?\s*$")
VARIABLE_RE = re.compile(r"(?m)^\s*variable\s*=\s*(?P<variable>\S+)\s*$")
TYPE_RE = re.compile(r"(?m)^\s*type\s*=\s*(?P<type>\S+)\s*$")

ELECTRON_TARGETS = {
    "electron_sheath": ("log_ne", "PhysicsFEMLogMolarElectronNoSheathSuppressionBC"),
    "electron_energy_sheath": (
        "log_energy",
        "PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC",
    ),
}
ION_TARGETS = {
    "ion_wall": "log_ni",
    "negative_ion_wall": "log_nm",
    "atomic_positive_ion_wall": "log_nop",
}


def _field(regex: re.Pattern[str], body: str, key: str) -> str:
    match = regex.search(body)
    if match is None:
        raise RuntimeError(f"missing {key}")
    return match.group(key)


def add_outlet(body: str) -> tuple[str, bool]:
    match = BOUNDARY_RE.search(body)
    if match is None:
        raise RuntimeError("missing boundary")
    items = match.group("items").split()
    if "outlet" in items:
        return body, False
    items.append("outlet")
    replacement = f"{match.group('indent')}boundary = '{' '.join(items)}'"
    return body[: match.start()] + replacement + body[match.end() :], True


def transform(text: str) -> tuple[str, list[str]]:
    changed: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group("name")
        body = match.group("body")
        if name not in ELECTRON_TARGETS:
            return match.group(0)

        expected_var, expected_type = ELECTRON_TARGETS[name]
        variable = _field(VARIABLE_RE, body, "variable")
        btype = _field(TYPE_RE, body, "type")
        if variable != expected_var:
            raise RuntimeError(f"{name}: expected variable {expected_var}, found {variable}")
        if btype != expected_type:
            raise RuntimeError(f"{name}: expected type {expected_type}, found {btype}")
        if "sheath_factor" in body:
            raise RuntimeError(f"{name}: unexpected sheath_factor parameter")

        new_body, did_change = add_outlet(body)
        if did_change:
            changed.append(name)
        if not new_body.endswith("\n"):
            new_body += "\n"
        return f"  [{name}]\n{new_body}  []\n"

    return BLOCK_RE.sub(repl, text), changed


def verify(text: str) -> None:
    blocks = {m.group("name"): m.group("body") for m in BLOCK_RE.finditer(text)}

    ground = blocks.get("grounded_potential")
    if ground is None:
        raise RuntimeError("missing grounded_potential block")
    if _field(VARIABLE_RE, ground, "variable") != "potential":
        raise RuntimeError("grounded_potential does not act on potential")
    if "outlet" not in _field(BOUNDARY_RE, ground, "items").split():
        raise RuntimeError("outlet is not grounded")

    for name, (expected_var, expected_type) in ELECTRON_TARGETS.items():
        body = blocks.get(name)
        if body is None:
            raise RuntimeError(f"missing {name}")
        if _field(VARIABLE_RE, body, "variable") != expected_var:
            raise RuntimeError(f"{name}: variable mismatch")
        if _field(TYPE_RE, body, "type") != expected_type:
            raise RuntimeError(f"{name}: type mismatch")
        if "outlet" not in _field(BOUNDARY_RE, body, "items").split():
            raise RuntimeError(f"{name}: outlet missing")
        if "sheath_factor" in body or "SheathFactorBC" in body:
            raise RuntimeError(f"{name}: explicit sheath factor still present")

    for name, expected_var in ION_TARGETS.items():
        body = blocks.get(name)
        if body is None:
            raise RuntimeError(f"missing {name}")
        if _field(VARIABLE_RE, body, "variable") != expected_var:
            raise RuntimeError(f"{name}: variable mismatch")
        if "outlet" not in _field(BOUNDARY_RE, body, "items").split():
            raise RuntimeError(f"{name}: outlet wall reaction missing")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    transformed, changed = transform(text)
    if sorted(changed) != sorted(ELECTRON_TARGETS):
        raise RuntimeError(f"expected to add outlet to both electron BCs; changed={changed}")
    verify(transformed)
    args.input.write_text(transformed, encoding="utf-8")

    print("ISSUE395_OUTLET_GROUNDED_REACTIVE_PASS")
    print("outlet potential = Dirichlet 0 V")
    print("outlet electron particle wall reaction = thermal no-sheath")
    print("outlet electron energy wall reaction = thermal no-sheath")
    print("outlet O2+/O-/O+ wall reactions = restored baseline")
    print("explicit electron sheath factor = absent")
    print("neutral outlet flow/pressure BCs = unchanged")


if __name__ == "__main__":
    main()
