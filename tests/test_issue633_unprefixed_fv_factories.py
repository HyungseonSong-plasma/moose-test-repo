"""P10-P13 structural staging controls for unprefixed PhysicsApp FV factories.

These tests prove source registration and donor parity only. A real OCI build,
check-input and dynamic warehouse integrity check remain separate obligations.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_species_neutral_fv_transport_factories_are_registered():
    header = source("physics_app/include/fvkernels/FVLogMolarTransport.h")
    impl = source("physics_app/src/fvkernels/FVLogMolarTransport.C")
    assert '#include "FVLogMolarTransport.h"' in impl
    for name in (
        "FVLogMolarTimeDerivative",
        "FVLogMolarDiffusion",
        "FVLogMolarElectrostaticDrift",
    ):
        assert f"class {name} :" in header
        assert f'registerMooseObject("PhysicsApp", {name});' in impl
        assert f"{name}::computeQpResidual()" in impl
    assert "PhysicsFVLogMolarElectronReactionSource" not in impl


def test_unprefixed_ion_wall_and_dielectric_bc_are_registered():
    for dirname, stem in (
        ("functormaterials", "IonWallFluxMaterial"),
        ("fvbcs", "FVLogMolarDielectricFluxBC"),
    ):
        source_path = f"physics_app/src/{dirname}/{stem}.C"
        header_path = f"physics_app/include/{dirname}/{stem}.h"
        code, header = source(source_path), source(header_path)
        assert f'#include "{stem}.h"' in code
        assert f"class {stem} :" in header
        assert f'registerMooseObject("PhysicsApp", {stem});' in code
    assert "return gamma_signed / PHYSICS_CONSTANTS::N_A;" in source(
        "physics_app/src/fvbcs/FVLogMolarDielectricFluxBC.C"
    )


def test_historical_factory_objects_not_deleted_before_cutover():
    legacy = source("physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C")
    assert 'registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronTimeDerivative);' in legacy
    assert 'registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronReactionSource);' in legacy
    # Both types are staged on a draft branch. Old owners must only be removed
    # after exact-head Native/historical callers and CI migration are resolved.
