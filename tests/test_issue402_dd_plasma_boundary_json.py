"""Issue #402: exact FEM [BCs] mapping to JSON without new Physics options.

The legacy .i fixture is the control. Every generated BC's name, MOOSE
class, solver variable, boundary, and Functor wiring must be identical.
"""
import json
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "physics_app"
CHEM = (APP / "src/physics/plasma/Chemistry.C").read_text()
SYN = (APP / "src/base/PhysicsApp.C").read_text()
DATA = json.loads((APP / "ci/dd_plasma_boundary_json_p2.json").read_text())
NEW = (APP / "ci/dd_plasma_boundary_json_p2.i").read_text()
LEGACY = (APP / "ci/dd_plasma_boundary_legacy_p2.i").read_text()
MEAN = (APP / "src/materials/PhysicsElectronMeanEnergyMaterial.C").read_text()
FLUX = (APP / "src/materials/PhysicsElectronAdjacentSheathWallFluxMaterial.C").read_text()


def _legacy_bc_definitions(text):
    section = text.split("\n[BCs]\n", 1)[1].split("\n[Executioner]\n", 1)[0]
    pattern = re.compile(
        r"(?ms)^  \[(?P<name>[^\]\n]+)\]\n(?P<body>.*?)^  \[\]\s*$"
    )
    out = {}
    for m in pattern.finditer(section):
        pairs = {}
        for line in m.group("body").splitlines():
            if "=" not in line:
                continue
            name, value = line.strip().split("=", 1)
            pairs[name.strip()] = value.strip().strip("'")
        out[m.group("name")] = pairs
    return out


def test_json_is_a_literal_registry_of_existing_bc_blocks():
    catalog = DATA["drift_diffusion_boundary"]
    assert set(catalog) == {"wafer", "cover", "inlet", "outlet"}
    assert catalog["inlet"]["bcs"] == {}
    assert catalog["outlet"]["bcs"] == {}
    original = _legacy_bc_definitions(LEGACY)
    relocated = {}
    for spec in catalog.values():
        for name, bc in spec["bcs"].items():
            relocated[name] = {**bc, "boundary": spec["mesh_boundary"]}
    assert relocated == original
    assert len(relocated) == 4


def test_only_json_presence_controls_bc_emission():
    assert "PlasmaDriftDiffusionBoundaryAction" not in SYN
    assert "PlasmaDriftDiffusionBoundaryAction" not in CHEM
    assert 'if (_current_task == "add_bc" && _data.hasDriftDiffusionBoundary())' in CHEM
    assert '_problem->addBoundaryCondition(bc.type, name, params);' in CHEM
    assert "getFactory" not in NEW
    assert "plasma_boundary = " not in NEW
    assert "plasma_boundary = " not in LEGACY
    assert "files = dd_plasma_boundary_json_p2.json" in NEW
    assert "files = json_surface_rate_p2.json" in LEGACY
    assert "[BCs]" not in NEW and "[BCs]" in LEGACY


def test_existing_mean_energy_and_sheath_laws_untouched():
    assert "type = PhysicsElectronMeanEnergyMaterial" in NEW
    assert "type = PhysicsElectronAdjacentSheathWallFluxMaterial" in NEW
    assert "type = PhysicsElectronMeanEnergyMaterial" in LEGACY
    assert "type = PhysicsElectronAdjacentSheathWallFluxMaterial" in LEGACY
    assert "mean_energy = exp(energy_state - density_state);" in MEAN
    assert "primaryParticleFluxHat(n_e, eps_bar, drop)" in FLUX
    assert 'entry.type == "FEMElectronSheathBC"' in CHEM
    assert 'entry.type == "FEMElectronEnergySheathBC"' in CHEM


def test_fail_closed_schema_and_duplicate_owners():
    for fragment in (
        "duplicate drift_diffusion_boundary owner across JSON files",
        "invalid or duplicate mesh_boundary in drift_diffusion_boundary",
        "duplicate DriftDiffusion BC operator owner",
        "drift_diffusion_boundary BC type is not yet supported",
        "wrong named arguments in drift_diffusion_boundary BC",
    ):
        assert fragment in CHEM
    assert "electron_model" not in CHEM
    assert '"plasma_boundary"' not in CHEM
