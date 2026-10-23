"""Issue 280 boundary guard integration without product-to-CI coupling."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_sol_boundary_mutation_selftest_and_zero_direct_moose_edges():
    result = subprocess.run(
        [sys.executable, "ci/guards/physics_sol_adapter_boundary_guard.py", "--self-test", "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD_SELF_TEST: PASS" in result.stdout
    assert "SEMANTIC_CONTROL_PLANE_DIRECT_MOOSE_EDGE_COUNT=0" in result.stdout
    assert "PHYSICS_LOCAL_ADAPTER_RUNTIME_OWNER_COUNT=0" in result.stdout
