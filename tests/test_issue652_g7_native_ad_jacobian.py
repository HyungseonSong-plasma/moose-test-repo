"""G7 PETSc Native micro-mesh contract, no binary/secret required in P0."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "ci/guards/issue652_g7_native_ad_jacobian.py"
SPEC = importlib.util.spec_from_file_location("g7_native", FILE)
assert SPEC is not None and SPEC.loader is not None
g7 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g7)


def test_exact_g3_ad_chain_has_named_variables_and_charge_sign():
    fixture = g7.generated_input()
    assert fixture.count("[Mesh]") == 1
    assert "nx = 3" in fixture and "ny = 3" in fixture
    assert fixture.count("type = ADParsedFunctorMaterial") == 7
    assert "expression = 'ni+nop-ne-nm'" in fixture
    assert "expression = '1.602176634e-19*nq'" in fixture
    assert "expression = '1.8095128179727827e-08*nq'" in fixture
    assert "type = ADMatDiffusion" in fixture
    assert "type = FunctorKernel" in fixture
    assert "functor_on_rhs = true" in fixture
    assert "exodus = false" in fixture and "checkpoint = false" in fixture


def test_synthetic_component_never_claims_full_s6_semantic_parity():
    text = (
        "||J - Jfd||_F/||J||_F = 2.0e-9, "
        "||J - Jfd||_F = 4.0e-7"
    )
    result = g7.interpret(text, check_rc=0, solve_rc=0, timeout=False)
    assert result["component_jacobian"] == "PASS_SYNTHETIC_AD_COMPONENT"
    assert result["actual_s6_coupled_ad_jacobian"] == "UNVERIFIED"
    assert result["old_new_poisson_parity"] == "UNVERIFIED"
    assert result["science"] == "SCIENCE_HOLD"


@pytest.mark.parametrize("log,check,code,timeout", [
    ("", 0, 0, False),
    ("garbage", 0, 0, False),
    ("||J - Jfd||_F/||J||_F = 3.0e-5, ||J - Jfd||_F = 1", 0, 0, False),
    ("||J - Jfd||_F/||J||_F = nan, ||J - Jfd||_F = 1", 0, 0, False),
    ("||J - Jfd||_F/||J||_F = 1e-12, ||J - Jfd||_F = 1", 1, 0, False),
    ("||J - Jfd||_F/||J||_F = 1e-12, ||J - Jfd||_F = 1", 0, 1, False),
    ("||J - Jfd||_F/||J||_F = 1e-12, ||J - Jfd||_F = 1", 0, 0, True),
])
def test_missing_finite_comparison_or_bad_run_is_hold(log, check, code, timeout):
    result = g7.interpret(log, check_rc=check, solve_rc=code, timeout=timeout)
    assert result["component_jacobian"] == "HOLD"


def test_only_exact_oci_and_pinned_source_in_docker_call(tmp_path: Path):
    command = g7.docker_command(tmp_path, tmp_path, check=False)
    assert command[:3] == ["docker", "run", "--rm"]
    assert "--network" in command and "none" in command
    assert "-snes_test_jacobian" in command[-1]
    assert command[-2] == "-lc"
    assert g7.OCI in command
    assert "--check-input" in g7.docker_command(tmp_path, tmp_path, check=True)[-1]


def test_no_native_without_authorization(tmp_path: Path):
    with pytest.raises(g7.NativeJacobianHold, match="AUTHORIZATION"):
        g7.run(source=tmp_path, manifest=tmp_path / "manifest.json",
               output=tmp_path / "receipt.json", timeout=1, authorize=False)
