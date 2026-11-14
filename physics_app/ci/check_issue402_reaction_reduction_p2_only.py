#!/usr/bin/env python3
"""Issue #402: source-bound, syntax-only Native P2 checks for retired EI10/EI16 owners.

This script deliberately never runs a time step. Physical numerical parity,
negative-input fail-fast parity, and science acceptance remain separate gates.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from physics_app.ci import check_r2_o2_ionization_implementation as r2
from physics_app.ci import check_r3_o2s_excitation_implementation as r3
from physics_app.ci import check_e8_ei10_energy_runtime as e10
from physics_app.ci import check_e8_ei16_energy_runtime as e16


# These four old runtime fixtures deliberately solve the *linear physical*
# FV states n_e [particles/m^3] and mean_en [eV/m^3]. Retain all source
# terms/variables unmodified. Adapt only a disposable --check-input copy to
# the newer log-molar-only ElectronEnergyMaterial input convention:
#
# exp(log(mean_en / N_A) - log(n_e / N_A)) == mean_en / n_e  [eV]
#
# There is no floor, clamp, source change or compatibility alias. This is
# a P2 syntax/ownership bridge, not a P3 physical/numerical parity claim.
_N_A = 6.02214076e23
_LEGACY_MEAN_BRIDGE = """  [mean_energy_bridge]
    type = ElectronEnergyMaterial
    electron_energy_density = mean_en
    electron_density = n_e
    state_form = physical_eV
  []"""
_CANONICAL_P2_MEAN_BRIDGE = """  [p2_log_molar_electron_density]
    type = ADParsedFunctorMaterial
    property_name = issue402_p2_log_molar_e
    functor_names = 'n_e'
    functor_symbols = 'ne'
    expression = 'log(ne/6.02214076e23)'
  []
  [p2_log_molar_electron_energy_density]
    type = ADParsedFunctorMaterial
    property_name = issue402_p2_log_molar_energy
    functor_names = 'mean_en'
    functor_symbols = 'energy'
    expression = 'log(energy/6.02214076e23)'
  []
  [mean_energy_bridge]
    type = ElectronEnergyMaterial
    electron_energy_density = issue402_p2_log_molar_energy
    electron_density = issue402_p2_log_molar_e
    state_form = log_molar_eV
  []"""


def _adapt_physical_mean_energy_for_p2(source: str) -> str:
    """Adapt one exact legacy bridge in scratch only; reject unknown inputs."""
    if source.count(_LEGACY_MEAN_BRIDGE) != 1 or source.count("type = ElectronEnergyMaterial") != 1:
        raise ValueError("P2 adapter requires exactly one known historical physical_eV mean bridge")
    if "issue402_p2_log_molar_" in source:
        raise ValueError("P2 adapter cannot overwrite an existing log-molar owner")
    return source.replace(_LEGACY_MEAN_BRIDGE, _CANONICAL_P2_MEAN_BRIDGE)


def _fixtures(root: Path) -> list[tuple[str, Path]]:
    """Materialize only pre-existing approved CI inputs, in isolated directories."""
    cases = []
    r2_dir = root / "r2_ionization"
    r2_dir.mkdir()
    r2._prepare_runtime_fixture(r2_dir)
    r2_input = r2_dir / "r2_o2_ionization_runtime.i"
    r2_input.write_text(_adapt_physical_mean_energy_for_p2(r2_input.read_text()))
    cases.append(("R2_EI16", r2_input)

    r3_dir = root / "r3_excitation"
    r3_dir.mkdir()
    r3_input = r3_dir / "r3_o2s_excitation_runtime.i"
    r3_input.write_text(_adapt_physical_mean_energy_for_p2(r3.RUNTIME_INPUT))
    cases.append(("R3_EI10", r3_input))

    e10_dir = root / "e8_ei10"
    e10_dir.mkdir()
    e10_input = e10_dir / "e8_ei10_energy_runtime.i"
    e10_input.write_text(_adapt_physical_mean_energy_for_p2(e10.RUNTIME_INPUT))
    cases.append(("E8_EI10", e10_input))

    e16_dir = root / "e8_ei16"
    e16_dir.mkdir()
    e16_input = e16_dir / "e8_ei16_energy_runtime.i"
    e16_input.write_text(_adapt_physical_mean_energy_for_p2(e16.RUNTIME_INPUT))
    (e16_dir / "e8_ei16_runtime_table.txt").write_text(
        "".join(f"{x:.8g} {y:.17g}\n" for x, y in e16.RATE_TABLE)
    )
    cases.append(("E8_EI16", e16_input))
    return cases


def check_native_p2(executable: Path) -> None:
    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"Missing exact-head physics-opt: {executable}")

    with tempfile.TemporaryDirectory(prefix="issue402-reaction-p2-") as tmp:
        for label, path in _fixtures(Path(tmp)):
            # CRITICAL: --check-input is mandatory; no --executable runtime tests,
            # no transient solving, no P3/P4 in this source migration gate.
            command = [str(executable), "--check-input", "-i", path.name]
            run = subprocess.run(
                command,
                cwd=path.parent,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
            log = (run.stdout or "") + (run.stderr or "")
            if run.returncode != 0 or "Syntax OK" not in log:
                raise AssertionError(
                    f"{label} Native P2 failed (exit {run.returncode}):\n{log[-5000:]}"
                )
            print(f"ISSUE402_REACTION_REDUCTION_{label}_NATIVE_P2_PASS")
    print("ISSUE402_REACTION_REDUCTION_NATIVE_P2_ONLY_PASS; P3=NOT_RUN; SCIENCE_HOLD")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    check_native_p2(args.executable)


if __name__ == "__main__":
    main()
