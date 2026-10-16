#!/usr/bin/env python3
"""Make inlet/outlet open for charged species and electron energy only.

This Issue #395 discriminator intentionally leaves electrostatic potential and
neutral-flow boundary conditions unchanged. For the charged transport system,
"open" means that no explicit wall/Dirichlet BC is attached to inlet or outlet;
the transport operator therefore uses its natural boundary behavior there.

Variables opened on inlet/outlet:
  * log_ne      (electrons)
  * log_energy  (electron energy / mean-energy state)
  * log_ni      (O2+)
  * log_nm      (O-)
  * log_nop     (O+)

All solid-wall BCs remain unchanged.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

BLOCK_RE = re.compile(r"(?ms)^  \[(?P<name>[^\]\n]+)\]\n(?P<body>.*?)^  \[\]\n")
BOUNDARY_RE = re.compile(r"(?m)^(?P<indent>\s*)boundary\s*=\s*'?(?P<items>[^'\n]*)'?\s*$")
VARIABLE_RE = re.compile(r"(?m)^\s*variable\s*=\s*(?P<variable>\S+)\s*$")

OPEN_VARS = {"log_ne", "log_energy", "log_ni", "log_nm", "log_nop"}
OPEN_BOUNDARIES = {"inlet", "outlet"}


def _variable(body: str) -> str | None:
    m = VARIABLE_RE.search(body)
    return None if m is None else m.group("variable")


def _remove_open_boundaries(body: str) -> tuple[str, list[str]]:
    m = BOUNDARY_RE.search(body)
    if m is None:
        return body, []
    items = m.group("items").split()
    removed = [item for item in items if item in OPEN_BOUNDARIES]
    if not removed:
        return body, []
    kept = [item for item in items if item not in OPEN_BOUNDARIES]
    if not kept:
        raise RuntimeError("charged BC would have an empty boundary set after opening inlet/outlet")
    replacement = f"{m.group('indent')}boundary = '{' '.join(kept)}'"
    return body[: m.start()] + replacement + body[m.end() :], removed


def transform(text: str) -> tuple[str, dict[str, list[str]]]:
    changed: dict[str, list[str]] = {}

    def repl(m: re.Match[str]) -> str:
        name = m.group("name")
        body = m.group("body")
        variable = _variable(body)
        if variable not in OPEN_VARS:
            return m.group(0)
        new_body, removed = _remove_open_boundaries(body)
        if removed:
            changed[name] = removed
        if not new_body.endswith("\n"):
            new_body += "\n"
        return f"  [{name}]\n{new_body}  []\n"

    return BLOCK_RE.sub(repl, text), changed


def verify(text: str) -> None:
    blocks = {m.group("name"): m.group("body") for m in BLOCK_RE.finditer(text)}

    ground = blocks.get("grounded_potential")
    if ground is None:
        raise RuntimeError("missing grounded_potential block")
    gm = BOUNDARY_RE.search(ground)
    if gm is None:
        raise RuntimeError("grounded_potential missing boundary")
    grounded = set(gm.group("items").split())
    if not OPEN_BOUNDARIES.issubset(grounded):
        raise RuntimeError(
            f"potential discriminator changed unexpectedly; grounded boundaries={sorted(grounded)}"
        )

    seen = set()
    offenders = []
    for m in BLOCK_RE.finditer(text):
        name = m.group("name")
        body = m.group("body")
        variable = _variable(body)
        if variable not in OPEN_VARS:
            continue
        seen.add(variable)
        bm = BOUNDARY_RE.search(body)
        if bm is None:
            continue
        items = set(bm.group("items").split())
        bad = sorted(items & OPEN_BOUNDARIES)
        if bad:
            offenders.append((name, variable, bad))

    missing = OPEN_VARS - seen
    if missing:
        raise RuntimeError(f"charged variables not found in BC blocks: {sorted(missing)}")
    if offenders:
        raise RuntimeError(f"inlet/outlet still present on charged BCs: {offenders}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    args = ap.parse_args()

    text = args.input.read_text(encoding="utf-8")
    transformed, changed = transform(text)
    verify(transformed)
    args.input.write_text(transformed, encoding="utf-8")

    print("ISSUE395_INLET_OUTLET_CHARGED_OPEN_PASS")
    print("open variables = log_ne log_energy log_ni log_nm log_nop")
    print("inlet/outlet explicit charged wall BCs = absent")
    print("inlet/outlet potential = unchanged grounded Dirichlet")
    print("neutral inlet/outlet flow/pressure BCs = unchanged")
    print("changed blocks:")
    for name in sorted(changed):
        print(f"  {name}: removed {' '.join(changed[name])}")


if __name__ == "__main__":
    main()
