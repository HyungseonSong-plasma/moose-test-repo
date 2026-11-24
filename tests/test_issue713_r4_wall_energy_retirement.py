"""R4 exact evidence and historical source preservation (P0, no native claim)."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/provenance/issue713_r4_wall_energy/"
D4 = ROOT / "experiments/Issue3_dielectric_surface_charge/"
ARCHIVED = {
    "physics_app/src/fvbcs/PhysicsFVElectronEnergyWallFluxBC.C": "d8c4298353ab14186a9f3a270a22f9f5742621f9",
    "physics_app/include/fvbcs/PhysicsFVElectronEnergyWallFluxBC.h": "196090e997a4648a7df2b98ca113ff8fa037648a",
    "experiments/Issue3_dielectric_surface_charge/prepare_d4.py": "ffc8f9468edae4a085e2d9dfa17c07680bbff87d",
    "experiments/Issue3_dielectric_surface_charge/prepare_d4_lowerd.py": "13f049226468a919e44ec2771d2872f3ef5042b1",
    "physics_app/ci/electron_energy_wall_smoke.i": "ef23344beeabe85e6740638e220c5e79c7be844f",
    "experiments/Issue3_dielectric_surface_charge/prepare_d4_see_energy.py": "fcfdcb94d0902e2d8d3e7a7145b103b0308d1a29",
    "experiments/Issue3_dielectric_surface_charge/analyze_d4_see_energy.py": "021b75f884d09912739e017154b00da7bf93319e",
    "experiments/Issue3_dielectric_surface_charge/test.json": "5d379e9d1c17b33128d53f2047672b17eb880da2",
}
REMOVED = (
    "physics_app/src/fvbcs/PhysicsFVElectronEnergyWallFluxBC.C",
    "physics_app/include/fvbcs/PhysicsFVElectronEnergyWallFluxBC.h",
    "experiments/Issue3_dielectric_surface_charge/prepare_d4.py",
    "experiments/Issue3_dielectric_surface_charge/prepare_d4_lowerd.py",
)
ORIGINAL_COMMENT = "# This discriminator isolates PhysicsFVElectronEnergyWallFluxBC from charge bookkeeping."
CURRENT_COMMENT = "# This discriminator isolates the log-molar wall-energy balance from charge bookkeeping."
EXPECTED = {
    "see_off": "8c7995e65b1298c159f2cc836962cca7a48ea59b7efa27090b05aa6c20a62f57",
    "see_on": "c444fb4f94e845b04713e3b7fa7d83e9d3d91fc878d2bd9b83c110c7bd015fc0",
}


def test_r4_archived_bytes_and_removed_paths():
    for path, expected in ARCHIVED.items():
        raw = (ARCHIVE / (path + ".txt")).read_bytes()
        assert hashlib.sha1(f"blob {len(raw)}".encode() + bytes(1) + raw).hexdigest() == expected
    for path in REMOVED:
        assert not (ROOT / path).exists()


def test_r4_exact_qualified_smoke_and_generated_decks():
    smoke = ROOT / "physics_app/ci/electron_energy_wall_smoke.i"
    assert hashlib.sha256(smoke.read_bytes()).hexdigest() == "b9f0032a7b4d6a35baa42d6c283a5254d591d282db8ec31775f48ca50fd6dabf"
    spec = importlib.util.spec_from_file_location("r4_see_gen", D4 / "prepare_d4_see_energy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.CASES) == set(EXPECTED)
    for name, gs in mod.CASES.items():
        current = mod.build(gs)
        assert current.count(CURRENT_COMMENT) == 1
        assert "PhysicsFVElectronEnergyWallFluxBC" not in current
        assert "state_form = physical_eV" not in current
        # Only the comment describing the former object differs from the
        # exact candidate input emitted by run 45424801571.
        evidence_deck = current.replace(CURRENT_COMMENT, ORIGINAL_COMMENT)
        assert hashlib.sha256(evidence_deck.encode()).hexdigest() == EXPECTED[name]


def test_r4_d6_metadata_only_removes_noninstantiated_energy_bc():
    old = json.loads((ARCHIVE / "experiments/Issue3_dielectric_surface_charge/test.json.txt").read_text())
    old["production_mechanisms"].remove("PhysicsFVElectronEnergyWallFluxBC")
    assert json.loads((D4 / "test.json").read_text()) == old
    assert "PhysicsFVElectronEnergyWallFluxBC" not in (D4 / old["input"]).read_text()


def test_r4_oracle_unchanged_except_scope_label():
    path = "experiments/Issue3_dielectric_surface_charge/analyze_d4_see_energy.py"
    old = (ARCHIVE / (path + ".txt")).read_text()
    new = (ROOT / path).read_text()
    assert new.replace(
        "isolated log-molar wall-energy equation; reconstructed physical inventory; SEE emitted energy fixed at 4 eV",
        "isolated physical_eV wall-energy equation; SEE emitted energy fixed by PhysicsFVElectronEnergyWallFluxBC at 4 eV",
    ) == old
