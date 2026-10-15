#!/usr/bin/env python3
"""Replace Issue #395 thermal-only electron wall BCs with explicit sheath-factor BCs.

This discriminator applies the same multiplicative factor to electron particle
and thermal electron-energy wall fluxes. It deliberately does not add a
Delta-phi energy term and does not use the wall Dirichlet potential as a proxy
for the sheath-edge plasma potential.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SHEATH_FACTOR = 0.010378507280576906

BLOCK_RE = re.compile(r"(?ms)^  \[(?P<name>electron_sheath|electron_energy_sheath)\]\n(?P<body>.*?)^  \[\]\n")
TYPE_RE = re.compile(r"(?m)^(?P<indent>\s*)type\s*=\s*(?P<type>\S+)\s*$")

EXPECTED = {
    "electron_sheath": (
        "PhysicsFEMLogMolarElectronNoSheathSuppressionBC",
        "PhysicsFEMLogMolarElectronSheathFactorBC",
    ),
    "electron_energy_sheath": (
        "PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC",
        "PhysicsFEMLogMolarElectronEnergySheathFactorBC",
    ),
}


def transform(text: str) -> tuple[str, list[str]]:
    changed: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group("name")
        body = match.group("body")
        tmatch = TYPE_RE.search(body)
        if tmatch is None:
            raise RuntimeError(f"{name}: missing type")

        old_type, new_type = EXPECTED[name]
        if tmatch.group("type") != old_type:
            raise RuntimeError(
                f"{name}: expected type {old_type}, found {tmatch.group('type')}"
            )

        replacement = f"{tmatch.group('indent')}type = {new_type}"
        body = body[: tmatch.start()] + replacement + body[tmatch.end() :]

        lines = body.splitlines()
        insert_at = 1
        lines.insert(insert_at, f"    sheath_factor = {SHEATH_FACTOR:.17g}")
        body = "\n".join(lines) + ("\n" if match.group("body").endswith("\n") else "")
        changed.append(name)
        return f"  [{name}]\n{body}  []\n"

    out = BLOCK_RE.sub(repl, text)
    return out, changed


def verify(text: str) -> None:
    for name, (_, new_type) in EXPECTED.items():
        m = re.search(
            rf"(?ms)^  \[{re.escape(name)}\]\n(?P<body>.*?)^  \[\]\n", text
        )
        if m is None:
            raise RuntimeError(f"missing {name} after transformation")
        body = m.group("body")
        if re.search(rf"(?m)^\s*type\s*=\s*{re.escape(new_type)}\s*$", body) is None:
            raise RuntimeError(f"{name}: transformed type missing")
        sm = re.search(r"(?m)^\s*sheath_factor\s*=\s*(\S+)\s*$", body)
        if sm is None:
            raise RuntimeError(f"{name}: sheath_factor missing")
        if abs(float(sm.group(1)) - SHEATH_FACTOR) > 1e-15:
            raise RuntimeError(f"{name}: sheath_factor mismatch")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    transformed, changed = transform(text)
    if sorted(changed) != sorted(EXPECTED):
        raise RuntimeError(f"expected to change both electron BCs, changed={changed}")

    verify(transformed)
    args.input.write_text(transformed, encoding="utf-8")

    print("ISSUE395_ELECTRON_SHEATH_FACTOR_PASS")
    print(f"sheath_factor={SHEATH_FACTOR:.17g}")
    print("particle_wall_flux = sheath_factor * thermal_half_Maxwellian_flux")
    print("energy_wall_flux = sheath_factor * thermal_energy_flux")
    print("additive_Delta_phi_energy_term = disabled")


if __name__ == "__main__":
    main()
