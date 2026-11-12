"""Issue #402 B: audit Joule/RF energy ownership in published S6 input decks.

Checks ONLY public frozen S6-417/941 C layers, which canonical D stages
before scratch-only state-token rewrites and its independently pinned Physics
overlay. No private data, Docker, native transient solve or science acceptance.
"""
from __future__ import annotations

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
PUBLIC = ROOT / "experiments/Issue493_s6_boltzmann"
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
PACK = PUBLIC / "public_p2_decks.tar.xz.b64"
PACK_SHA = "9e801cc6dca3860750b7b97fb6ceca8e6060a3c894dd616cbaf688f529fea240"


def _canonical_d_source_layers(case: str) -> list[str]:
    """Read exactly the public C layers that the D-only P3 stages."""
    raw = base64.b64decode(PACK.read_text(encoding="ascii"))
    assert hashlib.sha256(raw).hexdigest() == PACK_SHA
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        assert manifest["science"] == "SCIENCE_HOLD"
        record = manifest["cases"][case]
        assert len(record["input_order"]) == 10
        prefix = record["name"] + "/C/"
        names = [*record["input_order"], "migrated_continuity.i"]
        result = []
        for name in names:
            data = archive.extractfile(prefix + name).read()
            assert hashlib.sha256(data).hexdigest() == record["files_sha256"]["C"][name]
            result.append(data.decode("utf-8"))
    return result


def _blocks(source: str, name: str) -> list[str]:
    """Read exact two-space MOOSE child blocks, never substring matches."""
    pattern = re.compile(
        r"(?ms)^  \[" + re.escape(name) + r"\][ \t]*\n(.*?)^  \[\][ \t]*$"
    )
    return pattern.findall(source)


def _typed_blocks(source: str, type_name: str) -> list[str]:
    blocks = re.findall(
        r"(?ms)^  \[[^\]\n]+\][ \t]*\n(.*?)^  \[\][ \t]*$", source
    )
    return [block for block in blocks if re.search(
        r"(?m)^[ \t]*type[ \t]*=[ \t]*" + re.escape(type_name) + r"[ \t]*$", block
    )]


@pytest.mark.parametrize("case", ("417", "941"))
def test_archived_s6_d_electron_joule_and_rf_owners_are_distinct(case):
    layers = _canonical_d_source_layers(case)
    assert len(layers) == 11
    log_joule = [b for layer in layers for b in
                 _typed_blocks(layer, "PhysicsFEMLogMolarElectronJouleHeating")]
    physical_joule = [b for layer in layers for b in
                      _typed_blocks(layer, "PhysicsFEMElectronJouleHeating")]
    rf = [b for layer in layers for b in _blocks(layer, "rf_heating_t6")]
    assert len(log_joule) == 1, "Expected one log-molar electrostatic Joule residual"
    assert len(physical_joule) == 0, "Do not mix physical-state and log-molar Joule models"
    assert "variable = log_energy" in log_joule[0]
    assert "electron_log_density = log_ne" in log_joule[0]
    assert len(rf) == 1, "Expected one Maxwell RF deposition residual"
    assert "type = MatBodyForce" in rf[0]
    assert "variable = log_energy" in rf[0]
    assert "material_property = q_rf_eV_mol_t6" in rf[0]
    assert sum(len(_blocks(layer, "q_rf_eV_mol_t6")) for layer in layers) == 1
    assert sum("source_enable_t6 = 1.0" in layer for layer in layers) == 1
    assert sum("rf_heating_material =" in layer for layer in layers) == 0


def test_canonical_d_overlay_does_not_add_a_second_energy_owner():
    module = ast.parse((PILOT / "public_option_s6_p2.py").read_text())
    overlay = next(ast.literal_eval(node.value) for node in module.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(t, ast.Name) and t.id == "OVERLAY"
                       for t in node.targets))
    assert "fem_potential = potential" in overlay
    assert "[Energy]" not in overlay
    assert "rf_heating_material" not in overlay
    assert "JouleHeating" not in overlay
    assert "MatBodyForce" not in overlay
    runner = (PILOT / "run_canonical_s6_p3_once.py").read_text()
    assert 'option.p2.stage(ROOT, historical, case, "C", staged, manifest)' in runner
    assert "option.canonicalize_staged_D_inputs" in runner
    assert "sidecar.write_text(option.OVERLAY" in runner


def test_joule_residual_and_rf_material_have_distinct_sign_and_units():
    transport = (ROOT / "physics_app/src/kernels/PhysicsFEMPlasmaTransport.C").read_text()
    assert "PhysicsFEMLogMolarElectronJouleHeating::computeQpResidual()" in transport
    body = transport.split(
        "PhysicsFEMLogMolarElectronJouleHeating::computeQpResidual()", 1
    )[1]
    assert "const ADReal c_e = exp(_log_electron_density[_qp]);" in body
    assert "const ADRealVectorValue electric_field = -_grad_potential[_qp];" in body
    assert "mu * c_e * _grad_potential[_qp] - D * grad_c_e" in body
    assert "return _test[_i][_qp] * (electric_field * electron_flux);" in body
    rf_src = (
        ROOT / "experiments/Issue376_maxwell_plasma_rf_transfer/build_t6_overlays.py"
    ).read_text()
    assert "faraday_t6 = 96485.33212331001" in rf_src
    assert "enabled*scale*0.5*sigma_real_rf_t6*(E_real_rf_t6^2 + E_imag_rf_t6^2)/F" in rf_src
    assert "type = MatBodyForce" in rf_src
    assert "material_property = q_rf_eV_mol_t6" in rf_src
    action = (ROOT / "physics_app/src/physics/plasma/EnergyPhysics.C").read_text()
    assert 'if (!isParamValid("rf_heating_material"))' in action
    assert 'requireUniqueFEKernel("MatBodyForce"' in action


def test_retired_physical_state_joule_cpp_is_absent_but_log_molar_stays():
    """Remove only the unused physical-state B implementation and registration.

    Electrostatic log-molar electron heating and RF MatBodyForce remain active.
    A drift-kernel removal was merged separately in PR #513.
    """
    transport = (ROOT / "physics_app/src/kernels/PhysicsFEMPlasmaTransport.C").read_text()
    header = (ROOT / "physics_app/include/kernels/PhysicsFEMPlasmaTransport.h").read_text()
    for text in (transport, header):
        assert "PhysicsFEMElectronJouleHeating" not in text
        assert "PhysicsFEMLogMolarElectronJouleHeating" in text
        assert "PhysicsFEMPlasmaDriftDiffusion" not in text
    assert 'registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronJouleHeating);' in transport
    assert "PhysicsFEMLogMolarElectronJouleHeating::computeQpResidual()" in transport
    assert 'registerMooseObject("PhysicsApp", PhysicsFEMLogMolarDriftDiffusion);' in transport
