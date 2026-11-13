"""Bounded verification of archived S6 retired lower-D D1 diagnostics.

Physical continuity/Poisson/sheath/Wall/RF owners remain intact. The test
checks *only* diagnostic suspension in disposable core-input P2; neither
full diagnostic parity nor Native trajectory science is accepted.
"""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py"
ARCHIVE = ROOT / "experiments/Issue493_s6_boltzmann/public_p2_decks.tar.xz.b64"
HASH = "9e801cc6dca3860750b7b97fb6ceca8e6060a3c894dd616cbaf688f529fea240"
BASE = ("rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_"
        "100us_dt1000ns__C0_chemistry_off.i")
spec = importlib.util.spec_from_file_location("s6_retired_d1", PREP)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

EXPECTED = {**mod._S6_D1_CURRENT_PROBES, **mod._S6_D1_GEOMETRY_PROBES}
assert len(EXPECTED) == 14


def _archive():
    raw = base64.b64decode(ARCHIVE.read_text(), validate=False)
    assert hashlib.sha256(raw).hexdigest() == HASH
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as tar:
        members = tar.getmembers()
        assert len(members) == 45
        assert all(m.isfile() and not m.issym() and not m.islnk()
                   and ".." not in Path(m.name).parts for m in members)
        files = {m.name: tar.extractfile(m).read() for m in members}
    return json.loads(files["manifest.json"]), files


def _layers(case, variant):
    manifest, files = _archive()
    base = f"S6-{case}-407-2069-H25/{variant}/"
    layers = list(manifest["cases"][case]["input_order"])
    if variant == "C":
        layers.append("migrated_continuity.i")
    assert len(layers) == (11 if variant == "C" else 10)
    originals = {}
    for layer in layers:
        blob = files[base + layer]
        assert hashlib.sha256(blob).hexdigest() == (
            manifest["cases"][case]["files_sha256"][variant][layer])
        originals[Path(layer)] = blob.decode("utf-8")
    return originals


@pytest.mark.parametrize("case", ("417", "941"))
@pytest.mark.parametrize("variant", ("B", "C"))
def test_public_immutable_b_c_d1_observations_are_suspended_only_in_core_p2(
        case, variant):
    originals = _layers(case, variant)
    old = {name: text.encode() for name, text in originals.items()}
    out, receipt = mod.suspend_staged_retired_d1_observations(originals)
    assert receipt["status"] == "CORE_P2_ONLY_D1_OBSERVATION_SUSPENDED"
    assert receipt["suspended_auxkernels"] == 14
    assert receipt["suspended_auxvariables"] == 14
    assert receipt["observed_fields"] == sorted(EXPECTED)
    assert len(receipt["original_diagnostic_signatures_sha256"]) == 28
    assert receipt["diagnostic_parity"] == "HOLD"
    assert receipt["full_native_p2"] == "HOLD"
    assert receipt["P3"] == "NOT_RUN"
    assert receipt["science"] == "SCIENCE_HOLD"
    assert all(originals[name].encode() == value for name, value in old.items())
    assert all(text == originals[name] for name, text in out.items()
               if name != Path(BASE))
    text = out[Path(BASE)]
    for name in EXPECTED:
        assert f"  [{name}]\n" not in text
        assert f"  [{name}_kernel]\n" not in text
    assert "PhysicsLowerDSurfaceCurrentProbeAux" not in text
    assert "PhysicsWaferD1GeometryProbeAux" not in text
    assert "type = PhysicsLowerDSurfaceCurrent" in text
    assert "wafer_net_surface_current_density" in text
    assert "type = PhysicsElectronAdjacentSheathWallFluxMaterial" in text
    assert "type = PhysicsIonWallTotalFluxMaterial" in text
    assert "type = PhysicsElectronTransportLookupMaterial" in text
    # Retain the old material and physical equation (staged in later steps).
    # Removal of D1 Aux is an observational loss even if core P2 succeeds.


@pytest.mark.parametrize("owner,before,after", [
    ("wafer_net_current_probe_kernel",
     "    surface_current_density = wafer_net_surface_current_density",
     "    surface_current_density = wrong_current"),
    ("d1_normal_z", "    block = wafer_surface", "    block = plasma"),
    ("d1_normal_z_kernel",
     "    execute_on = 'INITIAL TIMESTEP_END'",
     "    execute_on = 'INITIAL'"),
    ("d1_normal_z", "    order = CONSTANT", "    order = FIRST"),
    ("d1_normal_z_kernel",
     "    type = PhysicsWaferD1GeometryProbeAux",
     "    type = PhysicsOtherGeometryProbe"),
    ("d1_normal_z_kernel", "    component = normal_z", "    component = e_n"),
])
def test_d1_observation_input_mutation_rejected_without_file_change(
        owner, before, after):
    original = _layers("417", "C")
    base = original[Path(BASE)]
    rx = re.compile(r"(?m)^  \[" + re.escape(owner) +
                    r"\]\n(?:^    .*\n)+^  \[\]\n")
    matches = list(rx.finditer(base))
    assert len(matches) == 1
    m = matches[0]
    block = m.group(0)
    assert before in block
    edited = base[:m.start()] + block.replace(before, after, 1) + base[m.end():]
    inputs = {**original, Path(BASE): edited}
    with pytest.raises(ValueError, match="S6_D1_PROBE_"):
        mod.suspend_staged_retired_d1_observations(inputs)
    assert inputs[Path(BASE)] == edited

@pytest.mark.parametrize("hidden", [
    "      unknown = value",
    "    unknown = value",
    "      block = plasma",
    "    unrelated text",
])
def test_hidden_aux_assignment_rejected_before_suspension(hidden):
    layers = _layers("941", "C")
    base = layers[Path(BASE)]
    anchor = "  [d1_normal_z_kernel]\n"
    assert base.count(anchor) == 1
    amended = base.replace(anchor, anchor + hidden + "\n", 1)
    source = {**layers, Path(BASE): amended}
    with pytest.raises(ValueError, match="S6_OWNER_|S6_D1_PROBE_"):
        mod.suspend_staged_retired_d1_observations(source)
    assert source[Path(BASE)] == amended


@pytest.mark.parametrize("change", ["delete_variable", "delete_kernel", "duplicate", "external_use"])
def test_d1_incomplete_duplicate_or_externally_used_probes_fail_closed(change):
    layers = _layers("941", "B")
    base = layers[Path(BASE)]
    if change == "delete_variable":
        match = re.search(r"(?m)^  \[d1_normal_r\]\n(?:^    .*\n)+^  \[\]\n", base)
        assert match
        layers[Path(BASE)] = base[:match.start()] + base[match.end():]
    elif change == "delete_kernel":
        match = re.search(r"(?m)^  \[d1_normal_r_kernel\]\n(?:^    .*\n)+^  \[\]\n", base)
        assert match
        layers[Path(BASE)] = base[:match.start()] + base[match.end():]
    elif change == "duplicate":
        match = re.search(r"(?m)^  \[d1_normal_r_kernel\]\n(?:^    .*\n)+^  \[\]\n", base)
        assert match
        layers[Path(BASE)] = base[:match.end()] + match.group(0) + base[match.end():]
    else:
        layers[Path("external_consumer.i")] = (
            "[Kernels]\n  [feedback]\n    type = FunctorKernel\n"
            "    variable = log_energy\n    functor = d1_normal_r\n  []\n[]\n")
    with pytest.raises(ValueError, match="S6_D1_PROBE_"):
        mod.suspend_staged_retired_d1_observations(layers)


def test_synthetic_test_without_d1_instrumentation_is_explicit_noop():
    inputs = {Path("synthetic.i"): "[AuxVariables]\n[]\n[AuxKernels]\n[]\n"}
    out, report = mod.suspend_staged_retired_d1_observations(inputs)
    assert out == inputs
    assert report["status"] == "NO_D1_OBSERVATION_PROBES"
    assert report["diagnostic_parity"] == "NOT_VERIFIED"


def test_current_cpp_surface_charge_kernel_not_removed():
    current = ROOT / "physics_app/src/kernels/PhysicsLowerDSurfaceCurrent.C"
    code = current.read_text()
    assert "registerMooseObject(" in code
    assert "_surface_current_density(face_arg, determineState())" in code
    assert "return -_test[_i][_qp] * j_to_surface;" in code
    for retired in ("PhysicsLowerDSurfaceCurrentProbeAux",
                    "PhysicsWaferD1GeometryProbeAux"):
        assert not list((ROOT / "physics_app/src/auxkernels").glob(f"{retired}.C"))
