#!/usr/bin/env python3
"""Enable the Issue #395 signed-drift field-limited electron wall closure.

Particle wall flux:
    Gamma_e = n_e * max(vbar_e/4 - mu_e * E_n, 0)
where E_n = E dot n_out and E = -grad(phi).

The same physical number-flux functor is consumed by the electron continuity
BC, electron-energy BC, and dielectric surface-charge ledger.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

BLOCK_RE = re.compile(r"(?ms)^  \[(?P<name>[^\]\n]+)\]\n(?P<body>.*?)^  \[\]\n")
TYPE_RE = re.compile(r"(?m)^\s*type\s*=\s*(?P<value>\S+)\s*$")
VAR_RE = re.compile(r"(?m)^\s*variable\s*=\s*(?P<value>\S+)\s*$")
BOUNDARY_RE = re.compile(r"(?m)^\s*boundary\s*=\s*'?(?P<value>[^'\n]+)'?\s*$")
MEAN_RE = re.compile(r"(?m)^\s*mean_energy\s*=\s*(?P<value>\S+)\s*$")

PARTICLE_OLD = {
    "PhysicsFEMLogMolarElectronNoSheathSuppressionBC",
    "PhysicsFEMLogMolarDielectricFluxBC",
}
ENERGY_OLD = {
    "PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC",
    "PhysicsFEMLogMolarElectronEnergyDielectricBC",
}


def field(regex: re.Pattern[str], body: str, label: str) -> str:
    m = regex.search(body)
    if m is None:
        raise RuntimeError(f"missing {label}")
    return m.group("value").strip()


def transform(text: str) -> tuple[str, int, int, str]:
    blocks = list(BLOCK_RE.finditer(text))
    wall = [m for m in blocks if m.group("name") == "electron_wall_flux"]
    if len(wall) != 1:
        raise RuntimeError(f"expected one electron_wall_flux block, found {len(wall)}")

    wall_body = wall[0].group("body")
    wall_type = field(TYPE_RE, wall_body, "electron_wall_flux type")
    if wall_type != "PhysicsElectronWallFluxMaterial":
        raise RuntimeError(f"unexpected electron_wall_flux type: {wall_type}")
    mean_functor = field(MEAN_RE, wall_body, "electron wall mean_energy functor")

    particle_count = 0
    energy_count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal particle_count, energy_count
        name = m.group("name")
        body = m.group("body")

        if name == "electron_wall_flux":
            body = TYPE_RE.sub(
                "    type = PhysicsElectronFieldLimitedWallFluxMaterial", body, count=1
            )
            if "potential =" in body or "mobility =" in body:
                raise RuntimeError("electron_wall_flux already carries field parameters")
            body = body.rstrip() + "\n    potential = potential\n    mobility = electron_mobility\n    use_element_gradient_for_potential = true\n    wall_velocity_gate_smoothing_width = 0\n"
            return f"  [{name}]\n{body}  []\n"

        tm = TYPE_RE.search(body)
        vm = VAR_RE.search(body)
        if tm is None or vm is None:
            return m.group(0)
        btype = tm.group("value")
        variable = vm.group("value")

        if variable == "log_ne" and btype in PARTICLE_OLD:
            boundary = field(BOUNDARY_RE, body, f"{name} boundary")
            particle_count += 1
            return (
                f"  [{name}]\n"
                "    type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC\n"
                "    variable = log_ne\n"
                "    wall_number_flux = electron_wall_number_flux\n"
                f"    boundary = '{boundary}'\n"
                "  []\n"
            )

        if variable == "log_energy" and btype in ENERGY_OLD:
            boundary = field(BOUNDARY_RE, body, f"{name} boundary")
            energy_count += 1
            return (
                f"  [{name}]\n"
                "    type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC\n"
                "    variable = log_energy\n"
                "    wall_number_flux = electron_wall_number_flux\n"
                f"    mean_energy = {mean_functor}\n"
                f"    boundary = '{boundary}'\n"
                "  []\n"
            )

        return m.group(0)

    out = BLOCK_RE.sub(repl, text)
    return out, particle_count, energy_count, mean_functor


def verify(text: str, particle_count: int, energy_count: int) -> None:
    if particle_count != 4:
        raise RuntimeError(f"expected 4 electron particle wall BCs, converted {particle_count}")
    if energy_count != 4:
        raise RuntimeError(f"expected 4 electron energy wall BCs, converted {energy_count}")
    if "type = PhysicsElectronFieldLimitedWallFluxMaterial" not in text:
        raise RuntimeError("field-limited electron wall material missing")
    if text.count("type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC") != 4:
        raise RuntimeError("field-limited electron particle BC count mismatch")
    if text.count("type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC") != 4:
        raise RuntimeError("field-limited electron energy BC count mismatch")
    for token in (
        "PhysicsFEMLogMolarElectronNoSheathSuppressionBC",
        "PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC",
        "PhysicsFEMLogMolarElectronEnergyDielectricBC",
    ):
        if token in text:
            raise RuntimeError(f"obsolete electron wall path remains: {token}")
    if "potential = potential" not in text or "mobility = electron_mobility" not in text:
        raise RuntimeError("electron wall material is missing potential/mobility coupling")
    if "use_element_gradient_for_potential = true" not in text:
        raise RuntimeError("CG-FEM adjacent-element E-field bridge is missing")

    blocks = {m.group("name"): m.group("body") for m in BLOCK_RE.finditer(text)}
    sheath = blocks.get("electron_sheath", "")
    if "outlet" not in field(BOUNDARY_RE, sheath, "electron_sheath boundary").split():
        raise RuntimeError("grounded outlet electron wall BC was not preserved")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    args = ap.parse_args()

    text = args.input.read_text(encoding="utf-8")
    out, particles, energies, mean_functor = transform(text)
    verify(out, particles, energies)
    args.input.write_text(out, encoding="utf-8")

    print("ISSUE395_ELECTRON_FIELD_LIMITED_WALL_PASS")
    print("Gamma_e = n_e * max(vbar_e/4 - mu_e*E_n, 0)")
    print("E_n = (-grad(phi)) dot n_out from sided adjacent FEM element")
    print("particle_wall_bcs=4 energy_wall_bcs=4")
    print(f"mean_energy_functor={mean_functor}")
    print("dielectric surface-charge ledger consumes the same electron_wall_number_flux")
    print("sheath exponential suppression = absent")


if __name__ == "__main__":
    main()
