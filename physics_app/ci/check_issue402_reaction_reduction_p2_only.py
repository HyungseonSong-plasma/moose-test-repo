#!/usr/bin/env python3
"""Issue #402: source-bound, syntax-only Native P2 checks for retired EI10/EI16 owners.

This script deliberately never runs a time step. Physical numerical parity,
negative-input fail-fast parity, and science acceptance remain separate gates.
"""
from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
from pathlib import Path

from physics_app.ci import check_r2_o2_ionization_implementation as r2
from physics_app.ci import check_r3_o2s_excitation_implementation as r3
from physics_app.ci import check_e8_ei10_energy_runtime as e10
from physics_app.ci import check_e8_ei16_energy_runtime as e16


def _require_canonical_energy(source: str) -> str:
    """Reject invalid state bindings; do not mutate the generated fixture."""
    expected = """  [flow_log_molar_electron_density]
    type = ADParsedFunctorMaterial
    property_name = flow_log_molar_electron_density
    functor_names = 'n_e'
    functor_symbols = 'ne'
    expression = 'log(ne/6.02214076e23)'
  []
  [flow_log_molar_electron_energy]
    type = ADParsedFunctorMaterial
    property_name = flow_log_molar_electron_energy
    functor_names = 'mean_en'
    functor_symbols = 'energy'
    expression = 'log(energy/6.02214076e23)'
  []
  [mean_energy_bridge]
    type = ElectronEnergyMaterial
    electron_energy_density = flow_log_molar_electron_energy
    electron_density = flow_log_molar_electron_density
    state_form = log_molar_eV
  []"""
    if (source.count(expected) != 1
            or source.count("state_form = log_molar_eV") != 1
            or "physical_eV" in source
            or "[n_e]" not in source or "[mean_en]" not in source):
        raise AssertionError("REACTION_P2_CANONICAL_ENERGY_CONTRACT_CHANGED")
    return source


def _bridge_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="flow-reaction-p2-selftest-") as temp:
        originals = _fixtures(Path(temp))
        assert len(originals) == 4
        for name, path in originals:
            raw = path.read_text()
            converted = _require_canonical_energy(raw)
            assert converted == raw, name
            assert "state_form = log_molar_eV" in converted, name
            assert "state_form = physical_eV" not in converted, name
            for broken in (
                raw.replace("state_form = log_molar_eV", "state_form = physical_eV"),
                raw.replace("electron_density = flow_log_molar_electron_density",
                            "electron_density = missing"),
                raw.replace("log(ne/6.02214076e23)", "ne"),
            ):
                try:
                    _require_canonical_energy(broken)
                except AssertionError:
                    pass
                else:
                    raise AssertionError("REACTION_P2_BRIDGE_MUTATION_NOT_REJECTED:" + name)
        for number_density, energy_density in ((1e15,3e15), (2e19, 8e19)):
            restored = math.exp(
                math.log(energy_density / 6.02214076e23)
                - math.log(number_density / 6.02214076e23)
            )
            assert math.isclose(restored, energy_density / number_density, rel_tol=1e-13)
    print("ISSUE402_REACTION_REDUCTION_P2_BRIDGE_MUTATION_SELF_TEST=PASS")


def _fixtures(root: Path) -> list[tuple[str, Path]]:
    """Materialize only pre-existing approved CI inputs, in isolated directories."""
    cases = []
    r2_dir = root / "r2_ionization"
    r2_dir.mkdir()
    r2._prepare_runtime_fixture(r2_dir)
    r2_input = r2_dir / "r2_o2_ionization_runtime.i"
    _require_canonical_energy(r2_input.read_text())
    cases.append(("R2_EI16", r2_input))

    r3_dir = root / "r3_excitation"
    r3_dir.mkdir()
    r3_input = r3_dir / "r3_o2s_excitation_runtime.i"
    r3_input.write_text(_require_canonical_energy(r3.RUNTIME_INPUT))
    cases.append(("R3_EI10", r3_input))

    e10_dir = root / "e8_ei10"
    e10_dir.mkdir()
    e10_input = e10_dir / "e8_ei10_energy_runtime.i"
    e10_input.write_text(_require_canonical_energy(e10.RUNTIME_INPUT))
    cases.append(("E8_EI10", e10_input))

    e16_dir = root / "e8_ei16"
    e16_dir.mkdir()
    e16_input = e16_dir / "e8_ei16_energy_runtime.i"
    e16_input.write_text(_require_canonical_energy(e16.RUNTIME_INPUT))
    (e16_dir / "e8_ei16_runtime_table.txt").write_text(
        "".join(f"{x:.8g} {y:.17g}\n" for x, y in e16.RATE_TABLE)
    )
    cases.append(("E8_EI16", e16_input))
    return cases


def check_native_p2(executable: Path) -> None:
    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"Missing exact-head physics-opt: {executable}")

    _bridge_self_test()
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
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _bridge_self_test()
    if args.executable:
        check_native_p2(args.executable)
    elif not args.self_test:
        parser.error("--executable is required unless --self-test is selected")


if __name__ == "__main__":
    main()
