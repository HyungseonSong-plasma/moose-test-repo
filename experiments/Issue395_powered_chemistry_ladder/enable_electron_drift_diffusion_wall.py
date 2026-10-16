#!/usr/bin/env python3
"""Enable Issue #395 electron wall flux corrected by normal drift and diffusion.

Solid-wall particle flux:
    Gamma_e = n_e * max(vbar_e/4 - mu_e*E_n - D_e*grad(log_ne).n_out, 0)
where E_n = (-grad(phi)).n_out.

The same physical number-flux functor is consumed by the electron continuity
BC, electron-energy BC, and dielectric surface-charge ledger. Inlet/outlet are
expected to have been opened before this transform and must remain absent from
all charged particle/energy wall BCs.
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
                "    type = PhysicsElectronDriftDiffusionLimitedWallFluxMaterial", body, count=1
            )
            for token in ("potential =", "mobility =", "diffusion =", "log_density ="):
                if token in body:
                    raise RuntimeError(f"electron_wall_flux already carries {token}")
            body = body.rstrip() + (
                "\n    log_density = log_ne\n"
                "    potential = potential\n"
                "    mobility = electron_mobility\n"
                "    diffusion = electron_diffusion\n"
                "    use_element_gradient_for_potential = true\n"
                "    use_element_gradient_for_log_density = true\n"
                "    wall_velocity_gate_smoothing_width = 0\n"
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
                raise RuntimeError(f"{name}: inlet/outlet must be open before wall conversion: {sorted(bad)}")
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
                raise RuntimeError(f"{name}: inlet/outlet must be open before wall conversion: {sorted(bad)}")
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
    if "type = PhysicsElectronDriftDiffusionLimitedWallFluxMaterial" not in text:
        raise RuntimeError("drift-diffusion electron wall material missing")
    if text.count("type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC") != 4:
        raise RuntimeError("electron particle BC count mismatch")
    if text.count("type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC") != 4:
        raise RuntimeError("electron energy BC count mismatch")
    for token in (
        "PhysicsFEMLogMolarElectronNoSheathSuppressionBC",
        "PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC",
        "PhysicsFEMLogMolarElectronEnergyDielectricBC",
    ):
        if token in text:
            raise RuntimeError(f"obsolete electron wall path remains: {token}")
    for token in (
        "log_density = log_ne",
        "potential = potential",
        "mobility = electron_mobility",
        "diffusion = electron_diffusion",
        "use_element_gradient_for_potential = true",
        "use_element_gradient_for_log_density = true",
    ):
        if token not in text:
            raise RuntimeError(f"electron wall material missing token: {token}")

    for m in BLOCK_RE.finditer(text):
        body = m.group("body")
        vm = VAR_RE.search(body)
        bm = BOUNDARY_RE.search(body)
        if vm is None or bm is None:
            continue
        if vm.group("value") in {"log_ne", "log_energy", "log_ni", "log_nm", "log_nop"}:
            bad = OPEN_BOUNDARIES & set(bm.group("value").split())
            if bad:
                raise RuntimeError(
                    f"{m.group('name')}: open boundary leaked into charged wall BC: {sorted(bad)}"
                )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    args = ap.parse_args()

    text = args.input.read_text(encoding="utf-8")
    out, particles, energies, mean_functor = transform(text)
    verify(out, particles, energies)
    args.input.write_text(out, encoding="utf-8")

    print("ISSUE395_ELECTRON_DRIFT_DIFFUSION_WALL_PASS")
    print("Gamma_e = n_e * max(vbar_e/4 - mu_e*E_n - D_e*grad(log_ne).n_out, 0)")
    print("E_n = (-grad(phi)) dot n_out from sided adjacent FEM element")
    print("grad(log_ne).n_out = sided adjacent FEM gradient")
    print("particle_wall_bcs=4 energy_wall_bcs=4")
    print(f"mean_energy_functor={mean_functor}")
    print("inlet/outlet charged particle and energy boundaries = open")
    print("dielectric surface-charge ledger consumes the same corrected electron_wall_number_flux")
    print("sheath exponential suppression = absent")


if __name__ == "__main__":
    main()
