"""G6 fail-closed typed registration and bounded 3ns execution contract tests."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import issue652_g6_runtime_gate as g6  # noqa: E402

NATIVE = (ROOT / "experiments/Issue402_plasma_dsl_g1/native/"
          "s6_c0_physics_base_no_d1.i")


def fake_trace():
    lines = ["G6_PRELOAD_READY"]
    for family, items in g6.EXPECTED_OWNERS.items():
        for name, kind in items.items():
            # Populate actual Action-generated naming convention for suffixes.
            full_name = name if family in ("Variable", "FunctorMaterial") else (
                "Poisson" + name
            )
            lines.append(f"G6_OWNER\t{family}\t{full_name}\t{kind}")
    for i in range(8):
        lines.append(f"G6_OWNER\tOther\toriginal_{i}\tNative")
    return ("\n".join(lines) + "\n").encode()


def test_exact_registration_has_15_typed_owners():
    report = g6.registration_receipt(fake_trace())
    assert report["status"] == "EXPECTED_15_GENERATED_OWNERS_TRACE_PASS"
    assert len(report["observed_expected_owners"]) == 15
    assert report["dynamic_functor_value"] == "NOT_TESTED_BY_REGISTRATION"


@pytest.mark.parametrize("mutation,error", [
    (lambda s: s.replace(b"G6_PRELOAD_READY\n", b""), "G6_REGISTRATION_OBSERVER"),
    (lambda s: s.replace(b"ADMatDiffusion", b"Diffusion"), "G6_EXPECTED_SINGLE"),
    (lambda s: s.replace(b"Poisson_diffusion", b"phi_diffusion"),
     "G6_RETIRED_NATIVE_OBJECT"),
    (lambda s: s.replace(b"G6_OWNER\tBC\tPoisson_grounded_potential\tDirichletBC\n", b""),
     "G6_EXPECTED_SINGLE"),
    (lambda s: s.replace(b"G6_OWNER\tVariable\tpotential\tMooseVariable\n",
                         b"G6_OWNER\tVariable\tpotential\tMooseVariable\n" * 2),
     "G6_EXPECTED_SINGLE"),
])
def test_missing_duplicate_and_wrong_typed_owners_fail_closed(mutation, error):
    with pytest.raises(ValueError, match=error):
        g6.registration_receipt(mutation(fake_trace()))


def test_three_ns_changes_only_disposable_runtime_lines():
    before = NATIVE.read_bytes()
    after, receipt = g6.three_ns_input(before)
    assert receipt["input_g5_sha256"] != receipt["output_private_3ns_sha256"]
    old = before.decode()
    new = after.decode()
    assert 'time_sequence = \x27' in old and (
        "    time_sequence = '0 1e-9 2e-9 3e-9'" in new)
    assert new.count("  end_time = 3e-9") == 1
    assert new.count("  checkpoint = false") == 1
    assert old.replace("  end_time = 1e-4", "  end_time = 3e-9").split(
        "    time_sequence = '", 1)[0] == new.split("    time_sequence = '", 1)[0]
    assert "end_time = 1e-4" not in new
    assert receipt["time_sequence_seconds"] == [0, 1e-9, 2e-9, 3e-9]


def test_only_expected_source_and_original_g5_staging_are_reused():
    script = (ROOT / "ci/guards/issue652_g6_runtime_gate.py").read_text()
    assert "G6_EXPECTED_SOURCE_SHA" in script
    assert "G6_G5_SOURCE_PIN_MISMATCH" in script
    assert "G6_G5_LAYER_SHA_MISMATCH" in script
    assert 'dir="/dev/shm"' in script
    assert 'PROTECTED_ARCHIVE_B64' in script
    assert "registration_only" in script
    assert "G6_semantic_parity" in script
    assert 'P4_100us": "NOT_RUN"' in script
    tracer = (ROOT / "ci/guards/issue652_g6_owner_tracer.cc").read_text()
    for name in ("addVariable", "addKernel", "addMaterial", "addFunctorMaterial",
                 "addBoundaryCondition", "addInitialCondition"):
        assert "G6_WRAP(" + name in tracer
    assert "P5X_REGISTER_LOG" not in tracer
