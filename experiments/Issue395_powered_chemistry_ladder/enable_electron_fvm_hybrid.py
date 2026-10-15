#!/usr/bin/env python3
"""Convert Issue #395 electron number and energy transport from FEM to FV.

The discriminator preserves the grounded reactive outlet and the existing
thermal no-sheath wall law. Potential remains continuous FEM; heavy charged
species remain on their existing FV path.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

WALLS = "outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring"
AVOID = "inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring"
BLOCK_RE = re.compile(r"(?ms)^  \[(?P<name>[^\]\n]+)\]\n(?P<body>.*?)^  \[\]\n")


def rewrite_named(text: str, name: str, fn) -> str:
    count = 0
    def repl(m: re.Match[str]) -> str:
        nonlocal count
        if m.group("name") != name:
            return m.group(0)
        count += 1
        return fn(m.group("body"))
    out = BLOCK_RE.sub(repl, text)
    if count != 1:
        raise RuntimeError(f"{name}: expected exactly one block, found {count}")
    return out


def fv_variable(name: str, body: str) -> str:
    if "family = LAGRANGE" not in body or "order = FIRST" not in body:
        raise RuntimeError(f"{name}: expected FIRST LAGRANGE FEM variable")
    lines = [
        ln for ln in body.splitlines()
        if "family = LAGRANGE" not in ln and "order = FIRST" not in ln
    ]
    lines.insert(0, "    type = MooseVariableFVReal")
    return f"  [{name}]\n" + "\n".join(lines) + "\n  []\n"


def transform(text: str) -> str:
    for name in ("log_ne", "log_energy"):
        text = rewrite_named(text, name, lambda body, n=name: fv_variable(n, body))

    for name in ("ne_time", "ne_transport", "energy_time", "energy_transport", "energy_joule"):
        text = rewrite_named(text, name, lambda _body: "")

    electron_bcs = (
        "electron_sheath",
        "electron_cover_dielectric",
        "electron_wafer_dielectric",
        "electron_focus_ring_dielectric",
        "electron_energy_sheath",
        "electron_energy_cover",
        "electron_energy_wafer",
        "electron_energy_focus_ring",
    )
    for name in electron_bcs:
        text = rewrite_named(text, name, lambda _body: "")

    fv_kernels = f"""  [ne_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ne
    block = plasma
  []
  [ne_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ne
    coeff = electron_diffusion
    block = plasma
  []
  [ne_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_ne
    potential = potential
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    use_element_gradient_for_potential = true
    boundaries_to_avoid = '{AVOID}'
    block = plasma
  []
  [energy_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_energy
    block = plasma
  []
  [energy_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_energy
    coeff = electron_energy_diffusion
    block = plasma
  []
  [energy_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_energy
    potential = potential
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    use_element_gradient_for_potential = true
    boundaries_to_avoid = '{AVOID}'
    block = plasma
  []
  [energy_joule]
    type = PhysicsFVElectronEnergyJouleHeating
    variable = log_energy
    electron_density = electron_molar_density
    potential = potential
    mobility = electron_mobility
    diffusion = electron_diffusion
    state_form = molar_eV
    block = plasma
  []
"""
    if text.count("[FVKernels]\n") < 1:
        raise RuntimeError("missing FVKernels section")
    text = text.replace("[FVKernels]\n", "[FVKernels]\n" + fv_kernels, 1)

    fv_bcs = f"""  [electron_wall]
    type = PhysicsFVLogMolarElectronNoSheathSuppressionBC
    variable = log_ne
    electron_density = electron_molar_density
    mean_electron_energy = mean_en_solved
    boundary = '{WALLS}'
  []
  [electron_energy_wall]
    type = PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC
    variable = log_energy
    electron_density = electron_molar_density
    mean_electron_energy = mean_en_solved
    boundary = '{WALLS}'
  []
"""
    if text.count("[FVBCs]\n") < 1:
        raise RuntimeError("missing FVBCs section")
    text = text.replace("[FVBCs]\n", "[FVBCs]\n" + fv_bcs, 1)
    return text


def verify(text: str) -> None:
    if text.count("type = MooseVariableFVReal\n    initial_condition") < 5:
        raise RuntimeError("expected electron and charged-heavy FV variables")
    for token in (
        "type = PhysicsFVLogMolarElectronTimeDerivative",
        "type = PhysicsFVLogMolarElectronDiffusion",
        "type = PhysicsFVLogMolarElectrostaticDrift",
        "type = PhysicsFVElectronEnergyJouleHeating",
        "state_form = molar_eV",
        "type = PhysicsFVLogMolarElectronNoSheathSuppressionBC",
        "type = PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC",
        "type = DirichletBC\n    variable = potential",
    ):
        if token not in text:
            raise RuntimeError(f"hybrid contract missing token: {token}")
    for token in (
        "type = PhysicsFEMLogMolarElectronNoSheathSuppressionBC",
        "type = PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC",
        "type = PhysicsFEMLogMolarElectronEnergyDielectricBC",
        "variable = log_ne\n    potential = potential\n    mobility = electron_mobility\n    diffusion = electron_diffusion",
    ):
        if token in text:
            raise RuntimeError(f"obsolete FEM electron path remains: {token}")
    m = re.search(r"(?ms)^  \[grounded_potential\]\n(?P<body>.*?)^  \[\]\n", text)
    if m is None or "outlet" not in m.group("body"):
        raise RuntimeError("outlet potential ground was not preserved")
    if "sheath_factor" in text or "SheathFactorBC" in text:
        raise RuntimeError("explicit sheath factor leaked into hybrid input")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    a = p.parse_args()
    text = a.input.read_text(encoding="utf-8")
    out = transform(text)
    verify(out)
    a.input.write_text(out, encoding="utf-8")
    print("ISSUE395_ELECTRON_FVM_HYBRID_PASS")
    print("log_ne = FV conservative log-molar")
    print("log_energy = FV conservative log-molar-eV")
    print("potential = FEM continuous")
    print("electron drift = upwind; FEM-potential element-gradient mode")
    print("electron wall closure = thermal no-sheath on grounded/reactive outlet + walls")


if __name__ == "__main__":
    main()
