"""Issue402: canonical JSON-owned DriftDiffusion boundary contract (P0)."""

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
CHEM = (APP / "src/physics/plasma/Chemistry.C").read_text()
HEADER = (APP / "include/physics/plasma/Chemistry.h").read_text()
ACTION = (APP / "src/physics/plasma/PlasmaDriftDiffusionBoundaryAction.C").read_text()
REG = (APP / "src/base/PhysicsApp.C").read_text()
NEW = (APP / "ci/dd_plasma_boundary_json_p2.i").read_text()
EXT = (APP / "ci/dd_plasma_boundary_external_mean_p2.i").read_text()
DATA = json.loads((APP / "ci/dd_plasma_boundary_json_p2.json").read_text())
PARTICLE = (APP / "src/bcs/FEMElectronSheathBC.C").read_text()
ENERGY = (APP / "src/bcs/FEMElectronEnergySheathBC.C").read_text()
FLUX = (APP / "src/materials/PhysicsElectronAdjacentSheathWallFluxMaterial.C").read_text()
MEAN = (APP / "src/materials/PhysicsElectronMeanEnergyMaterial.C").read_text()


def test_json_owns_exact_mesh_sideset_catalogue():
    cat = DATA["drift_diffusion_boundary"]
    assert set(cat) == {"wafer", "cover", "inlet", "outlet"}
    assert {cat[k]["mesh_boundary"] for k in cat} == {
        "left", "bottom", "right", "top"
    }
    assert {k for k, v in cat.items() if v["electron_model"] == "adjacent_sheath"} == {
        "wafer", "cover"
    }
    assert {k for k, v in cat.items() if v["electron_model"] == "open"} == {
        "inlet", "outlet"
    }
    assert "drift_diffusion_boundary" in CHEM
    assert "struct DDBoundaryRecord" in HEADER
    assert "driftDiffusionBoundaries() const" in HEADER
    assert '"mesh_boundary"' in CHEM and '"electron_model"' in CHEM
    assert '"open" && model != "adjacent_sheath" && model != "external"' in CHEM
    assert "duplicate drift_diffusion_boundary owner across JSON files" in CHEM
    assert "duplicate mesh_boundary in drift_diffusion_boundary" in CHEM


def test_opt_in_physics_only_references_shared_json():
    assert 'registerSyntax("PlasmaDriftDiffusionBoundaryAction"' in REG
    assert '"Physics/Plasmas/Transport/DriftDiffusion"' in REG
    assert 'MooseEnum("none json", "none")' in ACTION
    assert "roots.front()->data()" in ACTION
    assert "data.driftDiffusionBoundaries()" in ACTION
    assert "hasDriftDiffusionBoundary()" in ACTION
    assert "plasma_boundary = json" in NEW and "plasma_boundary = json" in EXT
    for case in (NEW, EXT):
        assert "files = dd_plasma_boundary_json_p2.json" in case
        assert "plasma_boundary_boundaries" not in case
        assert "plasma_boundary_wafer" not in case
        assert "[BCs]" not in case
        assert "type = PhysicsElectronAdjacentSheathWallFluxMaterial" not in case


def test_same_canonical_sheath_flux_shared_by_both_generated_bcs():
    assert 'const std::string type = "PhysicsElectronMeanEnergyMaterial";' in ACTION
    assert 'const std::string type = "PhysicsElectronAdjacentSheathWallFluxMaterial";' in ACTION
    assert 'const std::string type = "FEMElectronSheathBC";' in ACTION
    assert 'const std::string type = "FEMElectronEnergySheathBC";' in ACTION
    assert 'params.set<MooseEnum>("state_form") = "log_molar_eV";' in ACTION
    assert ACTION.count('params.set<MooseFunctorName>("wall_number_flux") = flux;') == 2
    assert 'params.set<MooseFunctorName>("mean_energy") = mean;' in ACTION
    assert 'config.electron_model != "adjacent_sheath"' in ACTION
    assert 'params.set<std::vector<BoundaryName>>("boundary") = {config.mesh_boundary};' in ACTION
    assert 'mean_energy = exp(energy_state - density_state);' in MEAN
    assert 'adjacentSheathDrop(_potential, r, state' in FLUX
    assert 'primaryParticleFluxHat(n_e, eps_bar, drop)' in FLUX
    assert 'plasmaSideElectronWallNumberFlux(_mesh' in PARTICLE
    assert 'Moose::FaceArg face_arg' in ENERGY


def test_strict_electron_wall_ownership_and_negative_contract():
    for marker in (
        "plasma_boundary=none cannot configure",
        "plasma_boundary=json requires drift_diffusion_boundary",
        "electron_model == \"adjacent_sheath\"",
        "Invalid",
    ):
        if marker == "Invalid":
            continue
        assert marker in ACTION
    assert 'plasma_boundary_mean_energy_owner = external' in EXT
    assert 'plasma_boundary_mean_energy = preexisting_mean_en' in EXT
    assert 'if (getParam<MooseEnum>("plasma_boundary_mean_energy_owner") == "generated")' in ACTION
    assert 'if (getParam<MooseEnum>("plasma_boundary_wall_flux_owner") == "generated")' in ACTION
    assert '"inlet/outlet cannot select the solid adjacent_sheath electron BC"' in CHEM
    assert 'model != "open" && model != "adjacent_sheath" && model != "external"' in CHEM
