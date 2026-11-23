"""G8 same-ELF real-S6 Poisson ownership gate: narrow P0 negative controls."""
from pathlib import Path
import importlib.util
import json
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN_SOURCE = os.environ.get("G8_NATIVE_SOURCE_ROOT")
if FROZEN_SOURCE:
    frozen_guards = Path(FROZEN_SOURCE).resolve()/"ci/guards"
    if frozen_guards.is_dir():
        sys.path.insert(0, str(frozen_guards))
# The analysis-only module is loaded by exact file path; its historical G5
# dependencies come strictly from the same pinned source as the Physics ELF.
sys.path.append(str(ROOT/"ci/guards"))
SPEC = importlib.util.spec_from_file_location(
    "issue652_g8_matched_stage", ROOT/"ci/guards/issue652_g8_matched_stage.py")
assert SPEC and SPEC.loader
g8 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g8)


def test_old_json_deletes_only_new_poisson_selector():
    source = g8.CHEM / "unified_s6_417_newonly.json"
    raw = source.read_bytes()
    old = g8.old_poisson_json(raw)
    assert g8.verify_semantic_json(old, raw)
    old_parsed = json.loads(old)
    new_parsed = json.loads(raw)
    assert "poisson" not in old_parsed and "poisson" in new_parsed
    assert old_parsed == {k: v for k, v in new_parsed.items() if k != "poisson"}
    assert b'"poisson"' not in old


@pytest.mark.parametrize("tamper", [
    lambda d: d.update({"poisson": {"danger": True}}),
    lambda d: d["species"]["e"].update({"charge_number": -5}),
    lambda d: d.pop("reactions"),
])
def test_old_new_mechanism_drift_is_rejected(tamper):
    raw = (g8.CHEM/"unified_s6_941_newonly.json").read_bytes()
    old = json.loads(g8.old_poisson_json(raw))
    tamper(old)
    with pytest.raises(g8.MatchedHold):
        g8.verify_semantic_json(json.dumps(old).encode(), raw)


def test_exact_only_three_approved_input_file_differences():
    root = g8.CHEM_RELATIVE
    allowed = {
        (root/g8.C0).as_posix(),
        (root/"migrated_continuity.i").as_posix(),
        (root/"chemistry/unified_s6_417_newonly.json").as_posix(),
    }
    before = {p: "b"*64 for p in allowed}
    before["public_mesh.msh"] = "a"*64
    after = {p: "c"*64 for p in allowed}
    after["public_mesh.msh"] = before["public_mesh.msh"]
    result = g8.diff_allowed(before, after, "417")
    assert set(result["allowed_changed_paths"]) == allowed
    assert result["unchanged_file_count"] == 1
    after["public_mesh.msh"] = "d"*64
    with pytest.raises(g8.MatchedHold, match="UNAUTHORIZED"):
        g8.diff_allowed(before, after, "417")


def test_missing_or_extra_input_file_must_hold():
    before = {"mesh.msh": "a", "layer.i": "b"}
    after = {"mesh.msh": "a", "extra.in": "b"}
    with pytest.raises(g8.MatchedHold, match="INVENTORY"):
        g8.diff_allowed(before, after, "417")


def test_single_elf_and_exact_original_lookup_are_nonnegotiable():
    assert g8.SOURCE_SHA == "26e84a4a33cf93d9e278a4f0b2d78c53cae2d6ce"
    assert g8.PUBLIC_D_100_SHA256 == "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
    assert g8.OLD_C0_SHA != g8.G5_OUTPUT_C0_SHA
    assert len(g8.TARGET_SHA) == 15
    assert set(g8.CASES) == {"417", "941"}


def test_directory_symlink_is_not_considered_authoritative(tmp_path):
    directory = tmp_path/"case"
    directory.mkdir()
    (directory/"real").write_bytes(b"abc")
    (directory/"shortcut").symlink_to(directory/"real")
    with pytest.raises(g8.MatchedHold, match="SYMLINK"):
        g8.files_under(directory)


def test_no_mutation_of_same_old_new_root_and_no_implicit_run(tmp_path, monkeypatch):
    monkeypatch.setattr(g8, "checkout_sha", lambda: g8.SOURCE_SHA)
    with pytest.raises(g8.MatchedHold, match="INDEPENDENT"):
        g8.stage_pair(before_g5=tmp_path, after_g5=tmp_path,
                      g5_receipt=tmp_path/"receipt.json",
                      output=tmp_path/"report.json")
    assert not (tmp_path/"report.json").exists()
