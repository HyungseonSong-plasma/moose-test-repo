"""Issue #402 canonical FEM electron BCs and source-name retirement guards.

P0 is a source/contract check only. P2 uses real physics-opt --check-input;
neither gate proves time-dependent physics parity.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
CHEM = (APP / "src/physics/plasma/Chemistry.C").read_text()
SYN = (APP / "src/base/PhysicsApp.C").read_text()
DATA = json.loads((APP / "ci/dd_plasma_boundary_json_p2.json").read_text())
NEW = (APP / "ci/dd_plasma_boundary_json_p2.i").read_text()
LEGACY = (APP / "ci/dd_plasma_boundary_legacy_p2.i").read_text()
MEAN = (APP / "src/materials/ElectronEnergyMaterial.C").read_text()
MEAN_H = (APP / "include/materials/ElectronEnergyMaterial.h").read_text()
FLUX = (APP / "src/materials/ESWallFluxMaterial.C").read_text()
TRANSPORT = (APP / "src/materials/DDTransportMaterial.C").read_text()
ENERGY_ACTION = (APP / "src/physics/plasma/DDEnergyEq.C").read_text()


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


def test_boundaries_json_is_literal_one_to_one_bc_relocation():
    catalog = DATA["boundaries"]
    assert set(catalog) == {"left", "bottom", "right", "top"}
    assert all(set(spec) == {"bcs"} for spec in catalog.values())
    assert catalog["right"]["bcs"] == {} and catalog["top"]["bcs"] == {}
    relocated = {
        name: {**bc, "boundary": sideset}
        for sideset, group in catalog.items()
        for name, bc in group["bcs"].items()
    }
    assert relocated == _legacy_bc_definitions(LEGACY)
    assert len(relocated) == 4
    assert {x["variable"] for x in relocated.values()} == {"log_e", "log_e_energy"}
    assert {x["mean_energy"] for x in relocated.values() if "mean_energy" in x} == {"e_energy_eV"}


def test_exact_json_presence_owns_bc_creation():
    assert 'if (_current_task == "add_bc" && _data.hasBoundaries())' in CHEM
    assert "_problem->addBoundaryCondition(bc.type, name, params);" in CHEM
    assert "PlasmaDriftDiffusionBoundaryAction" not in SYN
    assert "PlasmaDriftDiffusionBoundaryAction" not in CHEM
    assert '"plasma_boundary"' not in CHEM
    assert "drift_diffusion_boundary" not in DATA
    assert "[BCs]" not in NEW and "[BCs]" in LEGACY
    assert "files = dd_plasma_boundary_json_p2.json" in NEW
    assert "files = json_surface_rate_p2.json" in LEGACY
    assert "The JSON object key IS the physical mesh sideset name" in CHEM


def test_only_new_energy_material_and_sheath_names_are_registered():
    assert 'registerMooseObject("PhysicsApp", ElectronEnergyMaterial);' in MEAN
    assert 'registerMooseObject("PhysicsApp", ESWallFluxMaterial);' in FLUX
    assert "class ElectronEnergyMaterial : public FunctorMaterial" in MEAN_H
    assert "type = ElectronEnergyMaterial" in NEW and "type = ElectronEnergyMaterial" in LEGACY
    assert "type = ESWallFluxMaterial" in NEW and "type = ESWallFluxMaterial" in LEGACY
    for obsolete in (
        "PhysicsElectronMeanEnergyMaterial", "ElectronWallFluxMaterial",
        "PhysicsElectronAdjacentSheathWallFluxMaterial", "PhysicsElectronWallFluxMaterial"
    ):
        assert not (APP / "src/materials" / (obsolete + ".C")).exists()
        assert not (APP / "include/materials" / (obsolete + ".h")).exists()


def test_single_e_energy_eV_output_rejects_physical_state():
    assert 'MooseEnum("log_molar_eV", "log_molar_eV")' in MEAN
    assert 'addFunctorProperty<ADReal>(\n      "e_energy_eV"' in MEAN
    assert "const ADReal mean_energy = exp(energy_state - density_state);" in MEAN
    assert "energy_state / density_state" not in MEAN
    assert "physical_eV" not in MEAN and "physical_eV" not in MEAN_H
    assert "_log_molar_state" not in MEAN and "_log_molar_state" not in MEAN_H
    assert '"energy_reference_eV"' not in MEAN
    assert "mean_en_solved" not in MEAN and "mean_en_solved" not in MEAN_H
    assert "mean_energy_output" not in MEAN and "mean_energy_output" not in MEAN_H
    assert "mean_energy_output" not in NEW and "mean_energy_output" not in LEGACY
    assert 'getFunctorByName<ADReal>("e_energy_eV")' in TRANSPORT


def test_json_plus_minimal_i_owns_complete_fem_electron_equations_and_sheath():
    auto = (APP / "ci/dd_plasma_boundary_json_physics_auto_p2.i").read_text()
    assert "[FunctorMaterials]" not in auto and "[Kernels]" not in auto
    assert "fem_species = e" in auto
    assert DATA["species"]["e"]["initial_number_density"] == 1e15
    assert "fem_potential = potential" in auto
    assert "initial_molar_energy_density_eV = 8.3e-9" in auto
    electron = DATA["species"]["e"]
    assert "transport_coefficients" not in DATA
    assert electron["transport_coef"] == "constant"
    assert electron["mobility"] == 0.25
    assert electron["diffusivity"] == 0.125
    assert electron["energy_transport_coef"] == "fluid"
    assert '"transport_coef"' in CHEM
    assert '"energy_transport_coef"' in CHEM
    for kernel in ("FEMLogMolarTimeDerivative", "FEMLogMolarDriftDiffusion",
                   "FEMLogMolarElectronJouleHeating"):
        assert kernel in ENERGY_ACTION
    for name in ("ElectronEnergyMaterial", "ESWallFluxMaterial",
                 "ADParsedFunctorMaterial"):
        assert name in ENERGY_ACTION
    assert 'params.set<MooseFunctorName>("electron_density") = "n_e_physical"' not in ENERGY_ACTION
    assert 'wall.set<MooseFunctorName>("electron_density") = "n_e_physical"' in ENERGY_ACTION
    assert 'density.set<std::string>("expression") = "6.02214076e23*exp(c)"' in ENERGY_ACTION
    assert 'registerMooseAction("PhysicsApp", DDEnergyEq, "add_functor_material");' in ENERGY_ACTION


def test_canonical_physics_action_resolves_log_e_energy_not_old_log_energy():
    assert 'return "log_" + species + "_energy";' in ENERGY_ACTION
    assert 'saveSolverVariableName(energyStateName("e"));' in ENERGY_ACTION
    assert "log_e_energy" in ENERGY_ACTION
    assert "log_energy" not in NEW and "log_energy" not in LEGACY
    assert "log_ne" not in NEW and "log_ne" not in LEGACY


def test_fail_closed_catalogue_and_duplicate_operators():
    for fragment in (
        "duplicate boundaries owner across JSON files",
        "invalid or duplicate boundaries mesh sideset",
        "duplicate DriftDiffusion BC operator owner",
        "boundaries BC type is not yet supported",
        "wrong named arguments in boundaries BC",
        "drift_diffusion_boundary is retired; use boundaries",
    ):
        assert fragment in CHEM
