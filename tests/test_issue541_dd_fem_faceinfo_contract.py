"""Fail-closed P0 for DD FEM electron/energy FaceInfo bootstrap (no solver).

The flux remains plasma-side FaceArg; this test rejects shortcuts that silence
the boundary failure by omitting flux, using ElemQpArg, or weakening energy.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PARTICLE = ROOT / "physics_app/src/bcs/FEMElectronSheathBC.C"
ENERGY = ROOT / "physics_app/src/bcs/FEMElectronEnergySheathBC.C"


def _check(source: str, name: str, *, energy: bool) -> None:
    marker = f"{name}::\n{name}(const InputParameters & parameters)"
    if source.count(marker) != 1:
        raise ValueError("DD_FEM_CONSTRUCTOR_IDENTITY")
    constructor = source.split(marker, 1)[1].split(f"{name}::computeQpResidual()", 1)[0]
    if constructor.count("_subproblem.needFV();") != 1 or source.count("_subproblem.needFV();") != 1:
        raise ValueError("DD_FEM_FACEINFO_BOOTSTRAP_MISSING_OR_LATE")
    if "computeQpResidual()" not in source or "_mesh.buildFiniteVolumeInfo();" in source:
        raise ValueError("DD_FEM_FACEINFO_UNSAFE_LATE_BUILD")
    if ("const FaceInfo * const fi =" not in source or
            "if (!fi)" not in source or "mooseError(" not in source):
        raise ValueError("DD_FEM_FACEINFO_MISSING_FAIL_CLOSED_CHECK")
    if "Moose::FaceArg face_arg" not in source or "Moose::ElemQpArg" in source:
        raise ValueError("DD_FEM_FACE_FLUX_CHANGED_TO_QP_FALLBACK")
    if "hasFaceSide(*fi, true)" not in source or "hasFaceSide(*fi, false)" not in source:
        raise ValueError("DD_FEM_PLASMA_FACE_OWNERSHIP_LOST")
    if "plasma_side != " not in source or "Moose::currentState()" not in source:
        raise ValueError("DD_FEM_FACE_OWNERSHIP_OR_CURRENT_STATE_LOST")
    if energy:
        for token in ("_wall_number_flux(face_arg, Moose::currentState())",
                      "_mean_energy(face_arg, Moose::currentState())",
                      "PHYSICS_CONSTANTS::N_A", "(2.5 * Te)",
                      "mean_energy > 0 eV"):
            if token not in source:
                raise ValueError("DD_FEM_ENERGY_WALL_PHYSICS_CHANGED")
    else:
        for token in ("plasmaSideElectronWallNumberFlux(",
                      "flux(face_arg, Moose::currentState())",
                      "/ PHYSICS_CONSTANTS::N_A"):
            if token not in source:
                raise ValueError("DD_FEM_PARTICLE_WALL_PHYSICS_CHANGED")


def test_two_faceinfo_consumers_register_in_constructor_before_threaded_residual():
    _check(PARTICLE.read_text(), "FEMElectronSheathBC", energy=False)
    _check(ENERGY.read_text(), "FEMElectronEnergySheathBC", energy=True)


@pytest.mark.parametrize("name,energy,file", [
    ("FEMElectronSheathBC", False, PARTICLE),
    ("FEMElectronEnergySheathBC", True, ENERGY),
])
def test_missing_faceinfo_registration_is_rejected(name, energy, file):
    source = file.read_text()
    for mutation in (
        source.replace("_subproblem.needFV();", ""),
        source.replace("_subproblem.needFV();", "_mesh.buildFiniteVolumeInfo();"),
        source.replace("Moose::FaceArg face_arg", "Moose::ElemQpArg face_arg"),
        source.replace("hasFaceSide(*fi, true)", "false"),
        source.replace("hasFaceSide(*fi, false)", "false"),
        source.replace("if (!fi)", "if (false)"),
    ):
        with pytest.raises(ValueError):
            _check(mutation, name, energy=energy)


def test_particle_and_energy_flux_identity_mutations_are_rejected():
    particle = PARTICLE.read_text()
    energy = ENERGY.read_text()
    for bad in (
        particle.replace("/ PHYSICS_CONSTANTS::N_A", ""),
        particle.replace("flux(face_arg, Moose::currentState())", "ADReal(0.0)"),
    ):
        with pytest.raises(ValueError):
            _check(bad, "FEMElectronSheathBC", energy=False)
    for bad in (
        energy.replace("(2.5 * Te)", "(1.0 * Te)"),
        energy.replace("_mean_energy(face_arg, Moose::currentState())", "ADReal(1.0)"),
    ):
        with pytest.raises(ValueError):
            _check(bad, "FEMElectronEnergySheathBC", energy=True)


def test_dd_two_step_input_contract_unchanged():
    deck = (ROOT / "physics_app/ci/dd_plasma_boundary_json_p3_smoke.i").read_text()
    assert "dt = 1e-10" in deck
    assert "num_steps = 2" in deck
    assert "exodus = true" in deck and "csv = true" in deck
    assert "solve = false" not in deck

