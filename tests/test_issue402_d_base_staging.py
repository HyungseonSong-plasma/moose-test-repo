"""One-time D-only input source fixture and direct staging contract.

No runtime D1 injection, stripping, probe scanning or diagnostic parity gate.
The original S6 B/C archive and historical reproduction path stay untouched.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (ROOT / "experiments/Issue402_plasma_dsl_g1/native/"
           "s6_c0_physics_base_no_d1.i")
FIXTURE_SHA = "c9686adb669cc115556860c00438fcfdd93a438751e9f99825b4ddb6ebf65088"
MODULE = ROOT / "experiments/Issue493_s6_boltzmann/public_p2_check.py"
spec = importlib.util.spec_from_file_location("issue402_public_s6_stage", MODULE)
assert spec and spec.loader
p2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2)


def test_canonical_d_source_file_has_pinned_one_time_content():
    # Integrity pin only: the debug-free source has already been accepted.
    # Do not repeat searches for deleted debug objects on every run.
    assert FIXTURE.is_file()
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA


@pytest.mark.parametrize("case", ("417", "941"))
def test_target_d_stage_directly_uses_prebuilt_base_not_archived_input(tmp_path, case):
    control, historical = tmp_path / "control", tmp_path / "historical"
    (historical / p2.CHEM).mkdir(parents=True)
    (historical / p2.CHEM /
     "baseline_plasma_plus_unstructured_cover_plus_wafer.msh").write_text("mesh")
    ordered = ["original_base.i"] + [f"overlay_{n}.i" for n in range(2, 11)]
    rec = {"name": f"S6-{case}-fixture", "input_order": ordered, "active": ["public.txt"]}
    deck = control / p2.DECKS / rec["name"] / "C"
    deck.mkdir(parents=True)
    for name in ordered + ["migrated_continuity.i"]:
        (deck / name).write_text(f"archive input {name}\n")
    rates = control / p2.RATES
    rates.mkdir(parents=True)
    (rates / "public.txt").write_text("0.1 2.0\n")
    dest = tmp_path / "staged_d"
    result = p2.stage(control, historical, case, "C", dest,
                      {"cases": {case: rec}}, d_base_source=FIXTURE)
    staged = dest / p2.CHEM
    assert len(result) == 11
    assert (staged / ordered[0]).read_bytes() == FIXTURE.read_bytes()
    assert (staged / ordered[1]).read_text() == f"archive input {ordered[1]}\n"
    assert (staged / "migrated_continuity.i").read_text() == (
        "archive input migrated_continuity.i\n")
    assert (staged / "private_rates/public.txt").read_text() == "0.1 2.0\n"

    # B/C historical staging with no override is unchanged.
    historic = tmp_path / "staged_original"
    prior = p2.stage(control, historical, case, "C", historic,
                     {"cases": {case: rec}})
    assert len(prior) == 11
    assert (historic / p2.CHEM / ordered[0]).read_text() == (
        "archive input original_base.i\n")


def test_canonical_d_source_cannot_be_injected_into_b_archive(tmp_path):
    control, historical = tmp_path / "control", tmp_path / "historical"
    (historical / p2.CHEM).mkdir(parents=True)
    (historical / p2.CHEM /
     "baseline_plasma_plus_unstructured_cover_plus_wafer.msh").write_text("mesh")
    rec = {"name": "B-case", "input_order": ["original_base.i"], "active": []}
    with pytest.raises(ValueError, match="Only the staged D input"):
        p2.stage(control, historical, "417", "B", tmp_path / "wrong",
                 {"cases": {"417": rec}}, d_base_source=FIXTURE)



def test_both_d_entrypoints_use_prebuilt_source_without_debug_postprocessing():
    pilot = ROOT / "experiments/Issue402_plasma_dsl_g1"
    chemistry = (pilot / "run_chemistry_s6_p2_only.py").read_text()
    option = (pilot / "public_option_s6_p2.py").read_text()
    public_chemistry = (pilot / "public_chemistry_s6_p2.py").read_text()
    canonical_p3 = (pilot / "run_canonical_s6_p3_once.py").read_text()
    preparer = (pilot / "chemistry/prepare_s6_run_input.py").read_text()
    assert "d_base_source=D_BASE" in chemistry
    assert "d_base_source=d_base" in option
    assert "d_base_source=d_base" in public_chemistry
    assert "d_base_source=d_base" in canonical_p3
    assert 'if variant == "D" else None' in option
    for runtime in (chemistry, option, public_chemistry, canonical_p3, preparer):
        assert "suspend_staged_retired_d1_observations" not in runtime
        assert "audit_final_native_d1_debug_absence" not in runtime
    assert "scratch_d1_observation_scope" not in preparer
