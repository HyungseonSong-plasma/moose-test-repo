#!/usr/bin/env python3
"""Make the Issue #395 outlet electrostatic boundary homogeneous Neumann.

The powered-chemistry input uses a FEM Poisson equation with an ADDiffusion term.
For that weak form, omitting an explicit potential BC on a boundary gives the
natural homogeneous Neumann condition.  This discriminator therefore removes
only the token ``outlet`` from Dirichlet BCs acting on ``potential``.

No species, electron-energy, flow, surface-charge, or wall-flux boundary is
changed.  Other potential Dirichlet boundaries remain in place, so the
Poisson problem retains its voltage reference/gauge.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


BLOCK_RE = re.compile(r"(?ms)^  \[(?P<name>[^\]\n]+)\]\n(?P<body>.*?)^  \[\]\n")
BOUNDARY_RE = re.compile(r"(?m)^(?P<indent>\s*)boundary\s*=\s*'(?P<items>[^']*)'\s*$")


def is_potential_dirichlet(body: str) -> bool:
    return (
        re.search(r"(?m)^\s*variable\s*=\s*potential\s*$", body) is not None
        and re.search(r"(?m)^\s*type\s*=\s*\S*DirichletBC\s*$", body) is not None
    )


def remove_outlet_from_boundary(body: str) -> tuple[str, bool, str, str]:
    match = BOUNDARY_RE.search(body)
    if not match:
        return body, False, "", ""

    before_items = match.group("items").split()
    if "outlet" not in before_items:
        return body, False, " ".join(before_items), " ".join(before_items)

    after_items = [item for item in before_items if item != "outlet"]
    if not after_items:
        raise RuntimeError("refusing to remove the only Dirichlet potential boundary")

    before = " ".join(before_items)
    after = " ".join(after_items)
    replacement = f"{match.group('indent')}boundary = '{after}'"
    new_body = body[: match.start()] + replacement + body[match.end() :]
    return new_body, True, before, after


def transform(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    changes: list[tuple[str, str, str]] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group("name")
        body = match.group("body")
        if not is_potential_dirichlet(body):
            return match.group(0)

        new_body, changed, before, after = remove_outlet_from_boundary(body)
        if changed:
            changes.append((name, before, after))
            return f"  [{name}]\n{new_body}  []\n"
        return match.group(0)

    out = BLOCK_RE.sub(repl, text)
    return out, changes


def verify(text: str) -> None:
    potential_dirichlet_count = 0
    outlet_dirichlet_count = 0

    for match in BLOCK_RE.finditer(text):
        body = match.group("body")
        if not is_potential_dirichlet(body):
            continue
        potential_dirichlet_count += 1
        boundary = BOUNDARY_RE.search(body)
        if boundary and "outlet" in boundary.group("items").split():
            outlet_dirichlet_count += 1

    if potential_dirichlet_count == 0:
        raise RuntimeError("no potential Dirichlet BC remains; Poisson gauge would be unconstrained")
    if outlet_dirichlet_count != 0:
        raise RuntimeError(
            f"outlet is still present in {outlet_dirichlet_count} potential Dirichlet BC(s)"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    transformed, changes = transform(text)

    if not changes:
        raise RuntimeError("found no potential Dirichlet BC containing outlet")

    verify(transformed)
    args.input.write_text(transformed, encoding="utf-8")

    print("ISSUE395_OUTLET_POISSON_NEUMANN_PASS")
    print("outlet potential BC: natural homogeneous Neumann (no explicit potential BC)")
    for name, before, after in changes:
        print(f"changed block={name}")
        print(f"  before: {before}")
        print(f"  after : {after}")


if __name__ == "__main__":
    main()
