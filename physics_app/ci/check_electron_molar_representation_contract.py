#!/usr/bin/env python3
"""Structural regression for the canonical T1/T2 electron molar representation."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED: dict[str, tuple[str, ...]] = {
    "physics_app/include/fvkernels/PhysicsFVLogMolarElectronTransport.h": (
        "class PhysicsFVLogMolarElectronTimeDerivative",
        "class PhysicsFVLogMolarElectronDiffusion",
        "class PhysicsFVLogMolarElectrostaticDrift",
        "class PhysicsFVLogMolarElectronReactionSource",
    ),
    "physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C": (
        'registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronTimeDerivative);',
        'registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronDiffusion);',
        'registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectrostaticDrift);',
        'registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronReactionSource);',
        "return (exp(log_c_new) - exp(log_c_old)) / _dt;",
        "const ADReal c_face = exp(_var(transported_face, state));",
        "return -physical_number_source / avogadro_per_mol;",
    ),
    "physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathCollectionBC.h": (
        "const bool _log_molar_state;",
    ),
    "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathCollectionBC.C": (
        '"log_molar_state", false',
        "const ADReal physical_density = avogadro_per_mol * exp(solved_state);",
        "physical_density, mean_energy_eV, effective_drop_V) /",
        "avogadro_per_mol;",
        "if (!_log_molar_state)",
    ),
    "physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.h": (
        "const bool _molar_energy_state;",
    ),
    "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C": (
        '"molar_energy_state",',
        "if (!_molar_energy_state && !parameters.isParamSetByUser",
        "if (_molar_energy_state)",
        "const ADReal primary_particle_flux_molar =",
        "return primary_particle_flux_molar *",
        "PhysicsGroundedElectronSheath::primaryEnergyFluxHat(",
    ),
}


def validate(contents: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for relpath, tokens in REQUIRED.items():
        text = contents.get(relpath)
        if text is None:
            failures.append(f"missing file: {relpath}")
            continue
        for token in tokens:
            if token not in text:
                failures.append(f"{relpath}: missing contract token: {token}")
    return failures


def load(root: Path) -> dict[str, str]:
    contents: dict[str, str] = {}
    for relpath in REQUIRED:
        path = root / relpath
        if path.is_file():
            contents[relpath] = path.read_text(encoding="utf-8")
    return contents


def self_test() -> int:
    positive = {
        relpath: "\n".join(tokens)
        for relpath, tokens in REQUIRED.items()
    }
    assert not validate(positive), validate(positive)

    mutated = dict(positive)
    target = "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C"
    mutated[target] = mutated[target].replace("if (_molar_energy_state)", "")
    failures = validate(mutated)
    assert any("if (_molar_energy_state)" in item for item in failures), failures

    missing = dict(positive)
    missing.pop("physics_app/include/fvkernels/PhysicsFVLogMolarElectronTransport.h")
    failures = validate(missing)
    assert any(item.startswith("missing file:") for item in failures), failures

    print("ELECTRON_MOLAR_REPRESENTATION_P0=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()

    failures = validate(load(ROOT))
    if failures:
        print("ELECTRON_MOLAR_REPRESENTATION_CONTRACT=FAIL")
        for failure in failures:
            print(failure)
        return 1

    print("ELECTRON_MOLAR_REPRESENTATION_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
