"""G5 exact Native-owner retirement: source and strict negative safeguards only.

No solver execution in this test module. Full real 11-layer evidence is
separately required from the GitHub Actions Native P2 gate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHEM = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"
PILOT = CHEM.parent
sys.path.insert(0, str(CHEM))

import retire_s6_poisson_charge_owners as g5  # noqa: E402
from retire_s6_ion_fv_owners import CutoverError  # noqa: E402


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


@pytest.mark.parametrize("case", ("417", "941"))
def test_real_source_overlay_has_single_scratch_poisson_action(case):
    template = (PILOT / f"issue633_newonly_s6_{case}_continuity.template.i").read_bytes()
    assert sha(template) == g5.TEMPLATE_SHA[case]
    rendered = g5.render_g5_poisson_overlay(template, case)
    assert sha(rendered) == g5.G5_OVERLAY_SHA[case]
    before = template.decode()
    after = rendered.decode()
    assert "[Poisson]" not in before
    assert after.count("[Poisson]") == 1
    assert after.count("fem_potential = potential") == 3
    assert after.count(f"files = 'chemistry/unified_s6_{case}_newonly.json'") == 1
    assert "    [Poisson]\n      fem_potential = potential\n    []\n  []\n[]\n" in after
    assert "charge_source_functor" not in after
    assert "diffusivity_material" not in after
    assert "source_block" not in after


@pytest.mark.parametrize("case", ("417", "941"))
def test_mutated_source_overlay_fails_closed(case):
    template = (PILOT / f"issue633_newonly_s6_{case}_continuity.template.i").read_bytes()
    for mutated in (
        template.replace(b"fem_potential = potential", b"fem_potential = wrong", 1),
        template + b"\n# extra\n",
        template.replace(b"[Energy]", b"[Poisson]", 1),
    ):
        with pytest.raises(CutoverError, match="G5_ORIGINAL_OVERLAY_"):
            g5.render_g5_poisson_overlay(mutated, case)


def test_fifteen_exact_object_sha_and_expected_generated_parity():
    assert len(g5.TARGET_SHA) == 15
    assert {key[0] for key in g5.TARGET_SHA} == {
        "Variables", "FunctorMaterials", "Materials", "Kernels", "BCs"
    }
    assert {x[1] for x in g5.TARGET_SHA if x[0] == "FunctorMaterials"} == {
        "charge_number_density", "charge_density", "poisson_source"
    }
    assert len([x for x in g5.TARGET_SHA if x[0] != "FunctorMaterials"]) == 12
    assert g5.P4_C0_SHA == "2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490"
    assert g5.G5_OUTPUT_C0_SHA == "10f036ec8e6f1438c5dd854eea10f4680c970d56cb7a478766989a74f767e3e9"
    assert "sigma_s" not in g5.TARGET_NAMES
    assert "sigma_wafer" not in g5.TARGET_NAMES
    assert "sigma_focus_ring" not in g5.TARGET_NAMES


def source_fixture(monkeypatch, case="417"):
    """Tiny synthetic full-input fixture; production source SHA stays hard-pinned."""
    # Reuse the archived native owner blocks, but not its unrelated workflow
    # metadata. This tests the algorithm while the real C0 SHA is separately
    # required for all productive stage calls.
    original = (PILOT / "native/s6_c0_physics_base_no_d1.i").read_text()
    parts = []
    for section in ("Variables", "FunctorMaterials", "Materials", "Kernels", "BCs"):
        chunks = []
        for target_section, obj in g5.objects(original):
            if target_section == section and (section, obj["name"]) in g5.TARGET_SHA:
                chunks.append(obj.group(0))
        if section == "Variables":
            for sigma in g5.SURFACE_SIGMA:
                blocks = [obj.group(0) for sec, obj in g5.objects(original)
                          if sec == "Variables" and obj["name"] == sigma]
                assert len(blocks) == 1
                chunks.extend(blocks)
        parts.append(f"[{section}]\n" + "".join(chunks) + "[]\n")
    # Required references are part of the preserved remainder contract.
    parts.append("# n_i_physical n_m_physical n_op_physical n_e_physical carrier_one\n")
    c0_text = "".join(parts)
    for section, obj in g5.objects(c0_text):
        if (section, obj["name"]) in g5.TARGET_SHA:
            assert sha(obj.group(0).encode()) == g5.TARGET_SHA[(section, obj["name"])]
    after = c0_text
    found = [obj for section, obj in g5.objects(c0_text)
             if (section, obj["name"]) in g5.TARGET_SHA]
    assert len(found) == 15
    for match in reversed(found):
        after = after[:match.start()] + after[match.end():]
    monkeypatch.setattr(g5, "P4_C0_SHA", sha(c0_text.encode()))
    monkeypatch.setattr(g5, "G5_OUTPUT_C0_SHA", sha(after.encode()))
    names = [g5.C0] + [f"layer_{i}.i" for i in range(1, 10)] + ["migrated_continuity.i"]
    template = (PILOT / f"issue633_newonly_s6_{case}_continuity.template.i").read_bytes()
    layer = {x: b"[Kernels]\n[]\n" for x in names}
    layer[g5.C0] = c0_text.encode()
    layer["migrated_continuity.i"] = template
    expected = {k: sha(v) for k, v in layer.items()}
    mechanism = json.loads((CHEM / f"unified_s6_{case}_newonly.json").read_text())
    return layer, names, mechanism, expected, template


def test_exact_fifteen_delete_and_only_overlay_added(monkeypatch):
    layers, names, mechanism, shas, template = source_fixture(monkeypatch)
    c0, overlay, receipt = g5.plan_g5_poisson_charge_retirement(
        layers, names, mechanism, post_p4_layer_sha=shas,
        original_overlay=template, variant="417"
    )
    assert sha(c0) == g5.G5_OUTPUT_C0_SHA
    assert sha(overlay) == g5.G5_OVERLAY_SHA["417"]
    assert receipt["retired_poisson_owners"] == 12
    assert receipt["retired_charge_owners"] == 3
    assert len(receipt["retired_owners"]) == 15
    assert all(name in c0.decode() for name in g5.SURFACE_SIGMA)
    assert "n_e_physical" in c0.decode()
    for key in g5.TARGET_SHA:
        assert key not in {(section, obj["name"]) for section, obj in g5.objects(c0.decode())}


@pytest.mark.parametrize("mutation,error", [
    ("bad_sha", "G5_INPUT_LAYER_SHA_CHANGED"),
    ("wrong_object", "G5_EXACT_OWNER_BYTES_CHANGED"),
    ("extra_owner", "G5_UNEXPECTED_OWNER_SECTION_OR_LAYER"),
    ("missing_sigma", "G5_INPUT_LAYER_SHA_CHANGED"),
    ("wrong_json", "G5_POISSON_JSON_CONTRACT_INVALID"),
])
def test_all_invalid_cases_fail_before_output(monkeypatch, mutation, error):
    layers, names, mechanism, shas, template = source_fixture(monkeypatch)
    if mutation == "bad_sha":
        layers[g5.C0] += b"# drift\n"
    elif mutation == "wrong_object":
        layers[g5.C0] = layers[g5.C0].replace(
            b"prop_names = 'relative_permittivity'",
            b"prop_names = 'unexpected'",
            1,
        )
        shas[g5.C0] = sha(layers[g5.C0])
        monkeypatch.setattr(g5, "P4_C0_SHA", shas[g5.C0])
    elif mutation == "extra_owner":
        layers["layer_1.i"] = (
            b"[Kernels]\n  [phi_source]\n    type = FunctorKernel\n    variable = potential\n  []\n[]\n"
        )
        shas["layer_1.i"] = sha(layers["layer_1.i"])
    elif mutation == "missing_sigma":
        layers[g5.C0] = layers[g5.C0].replace(b"  [sigma_s]\n", b"  [lost_sigma]\n", 1)
    elif mutation == "wrong_json":
        mechanism["poisson"]["relative_permittivity"]["cover"] = -3.6
    with pytest.raises(CutoverError, match=error):
        g5.plan_g5_poisson_charge_retirement(
            layers, names, mechanism, post_p4_layer_sha=shas,
            original_overlay=template, variant="417",
        )


def test_real_stage_wires_g5_after_p4_and_keeps_template_sha():
    source = (CHEM / "prepare_s6_newonly.py").read_text()
    assert source.index("p4_owners = retire_p4_duplicate_owners(") < source.index(
        "g5_owners = retire_g5_in_disposable_scratch("
    )
    assert 'post_p4_sha[P4_C0] = p4_owners["output_c0_sha256"]' in source
    assert 'g5_owners["retired_poisson_owners"] != 12' in source
    assert 'g5_owners["retired_charge_owners"] != 3' in source
    assert 'after[P4_C0] != g5_owners["output_c0_sha256"]' in source
    assert 'after["migrated_continuity.i"] != g5_owners["output_overlay_sha256"]' in source
    assert 'newonly_overlay_template_sha256' in source
    assert 'newonly_overlay_sha256' in source
    assert 'PIN_HEAD = "9c15a4f0e2cf8042cb0d4b2f18af31511021d168"' in source
