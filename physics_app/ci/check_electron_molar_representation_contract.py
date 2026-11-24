#!/usr/bin/env python3
"""Structural regression for the canonical T1/T2 electron molar representation."""
from __future__ import annotations

import argparse
import hashlib
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

RETIRED_STATE_OWNERS = (
    "physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.h",
    "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C",
    "physics_app/ci/electron_grounded_sheath_energy_smoke.i",
)
SMOKE_SHA256 = "1e2d47dce00829d3233459b884d68d5f7198ed42eebea44471769450a061a99a"
ARCHIVE = ROOT / "docs/provenance/issue713_r5a_sheath_energy/"
ARCHIVED = {
    "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C": "0ec3766b00e16cdd24a5e29f355689920bb3178a",
    "physics_app/include/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.h": "ceccdb4e6dcb9f34af90a84b0c655d00d7865b31",
    "physics_app/ci/electron_grounded_sheath_energy_smoke.i": "ac94ef49820f016c94327f61726680da5de859c5",
    "physics_app/ci/check_electron_molar_representation_contract.py": "715f9c064863716e260f25c55029da1645f61a57",
}


def validate_retired_mode(contents: dict[str, str]) -> list[str]:
    failures = []
    for path in RETIRED_STATE_OWNERS:
        if path not in contents:
            failures.append(f"missing retired-mode owner: {path}")
        elif "physical_eV_state" in contents[path]:
            failures.append(f"retired physical_eV_state present: {path}")
    return failures


def validate_archive(root: Path) -> list[str]:
    failures = []
    for path, expected in ARCHIVED.items():
        raw = (root / "docs/provenance/issue713_r5a_sheath_energy/" / (path + ".txt")).read_bytes()
        actual = hashlib.sha1(f"blob {len(raw)}".encode() + bytes(1) + raw).hexdigest()
        if actual != expected:
            failures.append(f"historical blob drift: {path}")
    smoke = root / RETIRED_STATE_OWNERS[-1]
    if hashlib.sha256(smoke.read_bytes()).hexdigest() != SMOKE_SHA256:
        failures.append("qualified molar smoke input drift")
    return failures


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
    return failures + validate_retired_mode(contents)


def load(root: Path) -> dict[str, str]:
    contents: dict[str, str] = {}
    for relpath in set(REQUIRED) | set(RETIRED_STATE_OWNERS):
        path = root / relpath
        if path.is_file():
            contents[relpath] = path.read_text(encoding="utf-8")
    return contents


def self_test() -> int:
    positive = {
        relpath: "\n".join(tokens)
        for relpath, tokens in REQUIRED.items()
    }
    positive[RETIRED_STATE_OWNERS[-1]] = 'molar_energy_state = true'
    assert not validate(positive), validate(positive)
    retired = dict(positive)
    retired[RETIRED_STATE_OWNERS[-1]] += '\nphysical_eV_state = true'
    assert any('retired physical_eV_state present' in item for item in validate(retired))

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

    failures = validate(load(ROOT)) + validate_archive(ROOT)
    if failures:
        print("ELECTRON_MOLAR_REPRESENTATION_CONTRACT=FAIL")
        for failure in failures:
            print(failure)
        return 1

    print("ELECTRON_MOLAR_REPRESENTATION_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
