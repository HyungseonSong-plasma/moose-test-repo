"""Retirement guard for the legacy PlasmaClosures input Action.

S6-417/941 D stages the SHA-pinned public C decks, rewrites solver state
tokens only in scratch, and adds a DDContinuityEq-only overlay. The old
PlasmaClosures composition Action must not be a dependency of those runs.
This test does not execute a native solver or claim scientific parity.
"""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
DECKS = ROOT / "experiments/Issue493_s6_boltzmann/public_p2_decks.tar.xz.b64"
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
PACK_SHA = "9e801cc6dca3860750b7b97fb6ceca8e6060a3c894dd616cbaf688f529fea240"


@pytest.mark.parametrize("case", ("417", "941"))
def test_canonical_s6_d_public_layers_do_not_use_plasma_closures(case):
    raw = base64.b64decode(DECKS.read_text(encoding="ascii"))
    assert hashlib.sha256(raw).hexdigest() == PACK_SHA
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        assert manifest["science"] == "SCIENCE_HOLD"
        assert manifest["source_sha"] == "29d1acc6ef7969908b86719e4b95c73a1565136d"
        record = manifest["cases"][case]
        assert len(record["input_order"]) == 10
        names = [*record["input_order"], "migrated_continuity.i"]
        for name in names:
            content = archive.extractfile(f"{record['name']}/C/{name}").read()
            assert hashlib.sha256(content).hexdigest() == record["files_sha256"]["C"][name]
            text = content.decode("utf-8")
            assert not re.search(r"(?m)^\s*\[PlasmaClosures\]\s*$", text), (case, name)
            assert not re.search(r"(?m)^\s*\bPlasmaClosuresAction\b", text), (case, name)


def test_d_stages_c_layers_without_composition_overlay():
    script = (PILOT / "run_canonical_s6_p3_once.py").read_text()
    assert 'option.p2.stage(ROOT, historical, case, "C", staged, manifest)' in script
    assert "option.canonicalize_staged_D_inputs" in script
    source = (PILOT / "public_option_s6_p2.py").read_text()
    script_ast = ast.parse(source)
    overlay = next(ast.literal_eval(n.value) for n in script_ast.body
                   if isinstance(n, ast.Assign) and any(
                       isinstance(t, ast.Name) and t.id == "OVERLAY"
                       for t in n.targets))
    assert "[Continuity]" in overlay
    assert "[PlasmaClosures]" not in overlay
    assert "PlasmaClosuresAction" not in overlay
    assert "rf_heating_material" not in overlay


def test_retired_action_is_absent_independent_material_objects_remain():
    app = (APP / "src/base/PhysicsApp.C").read_text()
    assert "PlasmaClosuresAction" not in app
    assert "PlasmaClosures/*" not in app
    assert not (APP / "src/actions/PlasmaClosuresAction.C").exists()
    assert not (APP / "include/actions/PlasmaClosuresAction.h").exists()
    for retired in ("PhysicsElectronKineticsMaterial", "PhysicsHeavyTransportMaterial"):
        assert not (APP / "src/materials" / (retired + ".C")).exists()
        assert not (APP / "include/materials" / (retired + ".h")).exists()
    for material in ("PhysicsElectronMeanEnergyMaterial", "DDMaterial", "PhysicsElectronImpactRateMaterial",
                     "NVMaterial", "PhysicsPlasmaChargeDensityMaterial"):
        source = APP / "src/materials" / (material + ".C")
        header = APP / "include/materials" / (material + ".h")
        assert source.is_file() and header.is_file()
        assert f'registerMooseObject("PhysicsApp", {material});' in source.read_text()
    assert 'registerSyntax("DDContinuityEq",' in app
    assert 'registerSyntax("DDEnergyEq",' in app


def test_existing_native_smoke_uses_direct_materials_without_code_generation():
    fixture = (APP / "ci/plasma_direct_existing_materials_smoke.i").read_text()
    assert "[PlasmaClosures]" not in fixture
    assert "PhysicsElectronKineticsMaterial" not in fixture
    assert "PhysicsHeavyTransportMaterial" not in fixture
    assert fixture.count("type = PhysicsElectronImpactRateMaterial") == 2
    assert "type = NVMaterial" in fixture
    assert "type = DDMaterial" in fixture
    assert "type = PhysicsElectronMeanEnergyMaterial" in fixture
    assert "type = ElectronClosureMaterial" not in fixture
    assert "type = PhysicsPlasmaChargeDensityMaterial" in fixture
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert "python3 physics_app/ci/check_plasma_closures_contract.py" in runner
    assert 'native --check-input -i "physics_app/ci/plasma_direct_existing_materials_smoke.i"' in runner
    assert "make -C physics_app -j2" in runner  # Build existing native binary only.
