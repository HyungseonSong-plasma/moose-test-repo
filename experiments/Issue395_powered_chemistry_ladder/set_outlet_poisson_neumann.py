#!/usr/bin/env python3
"""Make the Issue #395 outlet a natural boundary for the charged subsystem.

The neutral-gas outlet remains unchanged.  For the charged plasma subsystem this
controlled discriminator removes ``outlet`` from:

* Dirichlet BCs acting on ``potential``.  With the FEM ADDiffusion Poisson weak
  form, no explicit potential BC at the outlet gives the natural homogeneous
  Neumann condition.
* Explicit ion wall-flux BCs acting on ``log_ni`` (O2+), ``log_nm`` (O-), and
  ``log_nop`` (O+).

The generated baseline already has no explicit outlet BC for ``log_ne`` or
``log_energy``; this script verifies that invariant rather than inventing a new
BC for either field.

All solid-wall and dielectric BCs remain unchanged, and other potential
Dirichlet boundaries remain in place so the Poisson problem keeps a voltage
reference/gauge.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


BLOCK_RE = re.compile(r"(?ms)^  \[(?P<name>[^\]\n]+)\]\n(?P<body>.*?)^  \[\]\n")
BOUNDARY_RE = re.compile(r"(?m)^(?P<indent>\s*)boundary\s*=\s*'?(?P<items>[^'\n]*)'?\s*$")
VARIABLE_RE = re.compile(r"(?m)^\s*variable\s*=\s*(?P<variable>\S+)\s*$")
TYPE_RE = re.compile(r"(?m)^\s*type\s*=\s*(?P<type>\S+)\s*$")

ION_VARIABLES = {"log_ni", "log_nm", "log_nop"}
CHARGED_VARIABLES = {"potential", "log_ne", "log_energy", *ION_VARIABLES}


def block_variable(body: str) -> str | None:
    match = VARIABLE_RE.search(body)
    return match.group("variable") if match else None


def block_type(body: str) -> str | None:
    match = TYPE_RE.search(body)
    return match.group("type") if match else None


def is_potential_dirichlet(body: str) -> bool:
    btype = block_type(body) or ""
    return block_variable(body) == "potential" and btype.endswith("DirichletBC")


def remove_outlet_from_boundary(body: str) -> tuple[str, bool, str, str]:
    match = BOUNDARY_RE.search(body)
    if not match:
        return body, False, "", ""

    before_items = match.group("items").split()
    if "outlet" not in before_items:
        return body, False, " ".join(before_items), " ".join(before_items)

    after_items = [item for item in before_items if item != "outlet"]
    if not after_items:
        raise RuntimeError("refusing to create an explicit BC with an empty boundary list")

    before = " ".join(before_items)
    after = " ".join(after_items)
    replacement = f"{match.group('indent')}boundary = '{after}'"
    new_body = body[: match.start()] + replacement + body[match.end() :]
    return new_body, True, before, after


def transform(text: str) -> tuple[str, list[tuple[str, str, str, str]]]:
    changes: list[tuple[str, str, str, str]] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group("name")
        body = match.group("body")
        variable = block_variable(body)

        target = is_potential_dirichlet(body)
        if variable in ION_VARIABLES and BOUNDARY_RE.search(body):
            target = True

        if not target:
            return match.group(0)

        new_body, changed, before, after = remove_outlet_from_boundary(body)
        if changed:
            changes.append((name, variable or "", before, after))
            return f"  [{name}]\n{new_body}  []\n"
        return match.group(0)

    return BLOCK_RE.sub(repl, text), changes


def verify(text: str) -> None:
    potential_dirichlet_count = 0
    outlet_charged_explicit_bc: list[tuple[str, str, str]] = []

    for match in BLOCK_RE.finditer(text):
        name = match.group("name")
        body = match.group("body")
        variable = block_variable(body)
        boundary = BOUNDARY_RE.search(body)

        if is_potential_dirichlet(body):
            potential_dirichlet_count += 1

        if variable not in CHARGED_VARIABLES or not boundary:
            continue
        if "outlet" in boundary.group("items").split():
            outlet_charged_explicit_bc.append((name, variable or "", block_type(body) or ""))

    if potential_dirichlet_count == 0:
        raise RuntimeError("no potential Dirichlet BC remains; Poisson gauge would be unconstrained")

    if outlet_charged_explicit_bc:
        detail = ", ".join(f"{name}:{variable}:{btype}" for name, variable, btype in outlet_charged_explicit_bc)
        raise RuntimeError(f"outlet still has explicit charged-field BC(s): {detail}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    transformed, changes = transform(text)

    potential_changes = [item for item in changes if item[1] == "potential"]
    ion_changes = [item for item in changes if item[1] in ION_VARIABLES]

    if not potential_changes:
        raise RuntimeError("found no potential Dirichlet BC containing outlet")
    if len(ion_changes) != 3:
        raise RuntimeError(
            f"expected outlet removal from exactly three ion BCs (O2+, O-, O+), found {len(ion_changes)}"
        )

    verify(transformed)
    args.input.write_text(transformed, encoding="utf-8")

    print("ISSUE395_OUTLET_POISSON_NEUMANN_PASS")
    print("ISSUE395_OUTLET_CHARGED_NATURAL_BC_PASS")
    print("ISSUE395_OUTLET_CHARGED_OPEN_PASS")
    print("outlet potential: natural homogeneous Neumann (no explicit potential BC)")
    print("outlet electron density: no explicit BC (already true in baseline)")
    print("outlet electron energy: no explicit BC (already true in baseline)")
    print("outlet O2+/O-/O+: explicit ion-wall flux BC removed")
    print("neutral outlet flow/pressure BCs: unchanged")
    for name, variable, before, after in changes:
        print(f"changed block={name} variable={variable}")
        print(f"  before: {before}")
        print(f"  after : {after}")


if __name__ == "__main__":
    main()
