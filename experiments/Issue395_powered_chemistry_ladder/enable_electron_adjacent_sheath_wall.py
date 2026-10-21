#!/usr/bin/env python3
"""Enable the Issue #395 adjacent-cell sheath-suppressed electron wall closure.

Particle wall flux on solid walls:
    Delta_phi = max(E_n * d_perp, 0)
    Gamma_e = n_e * vbar_e/4 * exp(-Delta_phi/T_e)
where E_n = E dot n_out, E=-grad(phi), and d_perp is the normal distance
from the wall-face centroid to the plasma-side adjacent-element centroid.

Inlet/outlet are expected to have been opened first for charged particles and
electron energy. The same corrected physical electron number-flux functor is
consumed by the electron continuity BC, electron-energy BC, and dielectric
surface-charge ledger.
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
OPEN_BOUNDARIES = {"inlet", "outlet"}


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
                "    type = PhysicsElectronAdjacentSheathWallFluxMaterial", body, count=1
            )
            if "potential =" in body:
                raise RuntimeError("electron_wall_flux already carries a potential parameter")
            body = body.rstrip() + (
                "\n    potential = potential"
                "\n    use_element_gradient_for_potential = true\n"
            )
            return f"  [{name}]\n{body}  []\n"

        tm = TYPE_RE.search(body)
        vm = VAR_RE.search(body)
        if tm is None or vm is None:
            return m.group(0)
        btype = tm.group("value")
        variable = vm.group("value")

        if variable == "log_ne" and btype in PARTICLE_OLD:
            boundary = field(BOUNDARY_RE, body, f"{name} boundary")
            bad = OPEN_BOUNDARIES & set(boundary.split())
            if bad:
                raise RuntimeError(f"{name} still contains open boundary names: {sorted(bad)}")
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
            bad = OPEN_BOUNDARIES & set(boundary.split())
            if bad:
                raise RuntimeError(f"{name} still contains open boundary names: {sorted(bad)}")
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
        raise RuntimeError(f"expected 4 solid electron particle wall BCs, converted {particle_count}")
    if energy_count != 4:
        raise RuntimeError(f"expected 4 solid electron energy wall BCs, converted {energy_count}")
    if "type = PhysicsElectronAdjacentSheathWallFluxMaterial" not in text:
        raise RuntimeError("adjacent-sheath electron wall material missing")
    if text.count("type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC") != 4:
        raise RuntimeError("electron particle wall BC count mismatch")
    if text.count("type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC") != 4:
        raise RuntimeError("electron energy wall BC count mismatch")
    for token in (
        "PhysicsFEMLogMolarElectronNoSheathSuppressionBC",
        "PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC",
        "PhysicsFEMLogMolarElectronEnergyDielectricBC",
    ):
        if token in text:
            raise RuntimeError(f"obsolete electron wall path remains: {token}")
    if "potential = potential" not in text:
        raise RuntimeError("electron wall material is missing potential coupling")
    if "use_element_gradient_for_potential = true" not in text:
        raise RuntimeError("CG-FEM adjacent-element E-field bridge is missing")

    for m in BLOCK_RE.finditer(text):
        body = m.group("body")
        tm = TYPE_RE.search(body)
        if tm is None or tm.group("value") not in {
            "PhysicsFEMLogMolarElectronFieldLimitedFluxBC",
            "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC",
        }:
            continue
        boundary = set(field(BOUNDARY_RE, body, f"{m.group('name')} boundary").split())
        bad = boundary & OPEN_BOUNDARIES
        if bad:
            raise RuntimeError(f"open boundary leaked back into solid electron BC: {sorted(bad)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    args = ap.parse_args()

    text = args.input.read_text(encoding="utf-8")
    out, particles, energies, mean_functor = transform(text)
    verify(out, particles, energies)
    args.input.write_text(out, encoding="utf-8")

    print("ISSUE395_ELECTRON_ADJACENT_SHEATH_WALL_PASS")
    print("Delta_phi = smooth_positive(E_n*d_perp)")
    print("Gamma_e = n_e*vbar_e/4*exp(-Delta_phi/T_e)")
    print("T_e = 2/3 mean_energy_eV")
    print("d_perp = wall-face centroid to plasma-side adjacent-element centroid normal distance")
    print("E_n = (-grad(phi)) dot n_out from sided adjacent FEM element")
    print("particle_wall_bcs=4 energy_wall_bcs=4")
    print(f"mean_energy_functor={mean_functor}")
    print("inlet/outlet charged particle and energy boundaries = open")
    print("energy closure = corrected particle flux * (5/2 T_e), no explicit +Delta_phi term")
    print("dielectric surface-charge ledger consumes the same corrected electron_wall_number_flux")


if __name__ == "__main__":
    main()
