#!/usr/bin/env python3
"""Structural regression for canonical electron molar transport and sheath realization."""
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
    "physics_app/include/fvbcs/PhysicsFVCellFunctorNeumannBC.h": (
        "class PhysicsFVCellFunctorNeumannBC",
        "const Moose::Functor<ADReal> & _functor;",
        "const Moose::Functor<ADReal> & _factor;",
    ),
    "physics_app/src/fvbcs/PhysicsFVCellFunctorNeumannBC.C": (
        'registerMooseObject("PhysicsApp", PhysicsFVCellFunctorNeumannBC);',
        'getFunctor<ADReal>("functor")',
        'getFunctor<ADReal>("factor")',
        "elemArg()",
        "neighborArg()",
        "return -_factor(cell, state) * _functor(cell, state);",
    ),
    "physics_app/ci/electron_sheath_collection_smoke.i": (
        "type = ADParsedFunctorMaterial",
        "property_name = cell_drop_particle_flux",
        "functor_names = 'n_cell_drop mean_en potential_cell'",
        "type = PhysicsFVCellFunctorNeumannBC",
        "functor = cell_drop_particle_flux",
        "factor = -1.0",
    ),
    "physics_app/ci/electron_grounded_sheath_energy_smoke.i": (
        "property_name = cell_drop_particle_flux",
        "property_name = cell_drop_energy_flux",
        "functor_names = 'cell_drop_particle_flux mean_en potential_cell'",
        "type = PhysicsFVCellFunctorNeumannBC",
        "functor = cell_drop_energy_flux",
        "factor = -1.0",
    ),
}


FORBIDDEN: dict[str, tuple[str, ...]] = {
    "physics_app/src/fvbcs/PhysicsFVCellFunctorNeumannBC.C": (
        "singleSidedFaceArg",
        "Boltzmann",
        "electronTemperature",
        "primaryParticleFlux",
        "primaryEnergyFlux",
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
        for token in FORBIDDEN.get(relpath, ()):
            if token in text:
                failures.append(f"{relpath}: forbidden sheath-specific/face token: {token}")
    return failures


def load(root: Path) -> dict[str, str]:
    contents: dict[str, str] = {}
    for relpath in REQUIRED:
        path = root / relpath
        if path.is_file():
            contents[relpath] = path.read_text(encoding="utf-8")
    return contents


def self_test() -> int:
    positive = {relpath: "\n".join(tokens) for relpath, tokens in REQUIRED.items()}
    assert not validate(positive), validate(positive)

    mutated = dict(positive)
    target = "physics_app/src/fvbcs/PhysicsFVCellFunctorNeumannBC.C"
    mutated[target] = mutated[target].replace("elemArg()", "")
    failures = validate(mutated)
    assert any("elemArg()" in item for item in failures), failures

    forbidden = dict(positive)
    forbidden[target] += "\nsingleSidedFaceArg"
    failures = validate(forbidden)
    assert any("singleSidedFaceArg" in item for item in failures), failures

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
