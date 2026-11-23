"""Fixed step and matrix-view diagnostics do not grant post-hoc Jacobian PASS."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
FILE = ROOT / "ci/guards/issue652_g7_fd_step_sweep.py"
SPEC = importlib.util.spec_from_file_location("issue652_g7_fd_step_sweep", FILE)
assert SPEC is not None and SPEC.loader is not None
sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep)


def test_predeclared_step_sweep_does_not_change_strict_gate():
    assert sweep.FD_STEPS == (1e-5, 1e-6, 1e-7, 1e-8, 1e-9, 1e-10, 1e-11, 1e-12, 1e-13)
    assert sweep.CONTROL_STEPS == (1e-6, 1e-8)
    assert sweep.RELATIVE_JAC_TOL == 1e-8
    cmd = sweep.command(Path("/tmp/source"), Path("/tmp/private"), 1e-6, view=True)
    assert cmd[-1].endswith("-snes_test_err 1e-06 -snes_test_jacobian_view")
    assert " -snes_test_jacobian -snes_converged_reason" in cmd[-1]
    assert "--network" in cmd and "none" in cmd
    with pytest.raises(sweep.SweepHold, match="NOT_PREDECLARED"):
        sweep.command(Path("/tmp/source"), Path("/tmp/private"), 1e-4, view=False)


def test_charge_disabled_fixture_is_only_poisson_source_kernel_removal():
    original = sweep.generated_input()
    control = sweep.charge_disabled_input()
    assert original.count(sweep.CHARGE_KERNEL) == 1
    assert len(original) - len(control) == len(sweep.CHARGE_KERNEL)
    assert "expression = 'ni+nop-ne-nm'" in control
    assert "type = ADMatDiffusion" in control
    assert "[o2p_diffusion]" in control
    assert "[poisson_charge_source]" not in control
    assert "  [potential]\\n    initial_condition = 0.1".replace("\\\\n", "\\n") in control


def test_missing_or_bad_native_norm_never_becomes_pass():
    empty = sweep.classify("", returncode=0, timed_out=False, fd_step=1e-8, view=True)
    assert empty["native_status"] == "HOLD"
    assert empty["worst_relative_frobenius_error"] is None
    assert empty["matrix_view"]["block_mapping"] == "UNVERIFIED"

    log = "||J - Jfd||_F/||J||_F = 7.08621e-05, ||J - Jfd||_F = 1.12e-02"
    data = sweep.classify(log, returncode=0, timed_out=False, fd_step=1e-8, view=False)
    assert data["native_status"] == "COMPARED"
    assert data["numerically_within_strict_tolerance"] is False
    assert data["strict_predeclared_tolerance"] == 1e-8
    assert data["worst_relative_frobenius_error"] == pytest.approx(7.08621e-5)
    for rc, timeout in ((1, False), (0, True)):
        fail = sweep.classify(log, returncode=rc, timed_out=timeout,
                              fd_step=1e-8, view=False)
        assert fail["native_status"] == "HOLD"
        assert fail["worst_relative_frobenius_error"] is None


def test_synthetic_matrix_view_localizes_numeric_entries_only():
    log = """Mat Object: 1 MPI process
  type: seqaij
row 0: (0, 10.) (1, 2.)
row 1: (1, 5.)
Mat Object: 1 MPI process
  type: seqaij
row 0: (0, 9.5) (1, 2.)
row 1: (1, 5.)
Mat Object: 1 MPI process
  type: seqaij
row 0: (0, 0.5)
"""
    result = sweep.matrix_summary(log)
    assert result["view_blocks_with_numeric_rows"] == 3
    assert result["relative_difference_recomputed_from_view"] == pytest.approx(
        0.5 / (10**2 + 2**2 + 5**2)**0.5)
    assert result["third_view_overlapping_entries"] == 1
    assert result["max_third_view_entry_consistency_error"] == pytest.approx(0.)
    assert result["top_matrix_differences_unmapped"][0]["row"] == 0
    assert result["top_matrix_differences_unmapped"][0]["column"] == 0
    assert result["block_mapping"] == "UNVERIFIED_NO_DOF_VARIABLE_INDEX_MAP"


def test_no_implicit_expensive_native_execution(tmp_path: Path):
    with pytest.raises(sweep.SweepHold, match="AUTHORIZATION"):
        sweep.sweep(source=tmp_path, manifest=tmp_path / "manifest",
                    output=tmp_path / "report.json", authorize=False)
    assert not (tmp_path / "report.json").exists()
