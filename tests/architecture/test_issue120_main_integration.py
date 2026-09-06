from __future__ import annotations

from pathlib import Path

from qpx_harness.cli.app import CANONICAL_COMMANDS, COMMANDS, INTERNAL_TARGETS, main
from qpx_harness.execution.status import ExecutionState
from qpx_harness.validation import ValidationKind, ValidationSurface, validate_command_surface

ROOT = Path(__file__).resolve().parents[2]


def test_cli_contract_and_internal_gateway_surface() -> None:
    assert validate_command_surface(COMMANDS, INTERNAL_TARGETS, CANONICAL_COMMANDS) == []
    assert main(["-i", "not-a-target"]) == 2
    assert main(["--help"]) == 0


def test_execution_terminal_state_is_mechanical_not_scientific_pass_fail() -> None:
    assert "PASS" not in ExecutionState.__members__
    assert "FAIL" not in ExecutionState.__members__
    assert ExecutionState.SUCCEEDED.value == "SUCCEEDED"
    assert ExecutionState.FAILED.value == "FAILED"


def test_validation_taxonomy_distinguishes_internal_from_scientific() -> None:
    internal = ValidationSurface(kind=ValidationKind.REGRESSION_CONTRACT)
    science = ValidationSurface(
        kind=ValidationKind.SCIENTIFIC_ACCEPTANCE,
        requires_solver=True,
        depends_on_scientific_thresholds=True,
        ci_suitable=False,
    )
    assert internal.is_infrastructure_validation is True
    assert internal.is_scientific_protocol is False
    assert science.is_scientific_protocol is True
    assert science.is_infrastructure_validation is False


def test_canonical_experiment_gateway_has_no_protocol_registry() -> None:
    application = ROOT / "qpx_harness" / "application"
    cli = (ROOT / "qpx_harness/cli/app.py").read_text()
    assert not (application / "experiment_registry.py").exists()
    assert not (application / "experiment_service.py").exists()
    assert not (application / "protocols").exists()
    assert "compile" in CANONICAL_COMMANDS
    assert "plan" in CANONICAL_COMMANDS
    assert "lower" in CANONICAL_COMMANDS
    assert "run" in CANONICAL_COMMANDS
    assert "run_experiment(" not in cli
    assert main(["-e", "historical.json"]) == 2


def test_green_gauss_formula_owner_is_analysis_but_application_owner_is_generic() -> None:
    evidence_text = (ROOT / "qpx_harness/evidence/transform.py").read_text()
    analysis_text = (ROOT / "qpx_harness/analysis/green_gauss.py").read_text()
    application_text = (ROOT / "qpx_harness/application/gradient_reconstruction.py").read_text()
    operations_text = (ROOT / "qpx_harness/application/operations.py").read_text()

    assert "def normalize_face_evidence" in evidence_text
    assert "qpx_harness.analysis.green_gauss" not in evidence_text
    assert "reconstructed_surface_x" not in evidence_text
    assert "reconstructed_surface_x" in analysis_text
    assert "def derive_cell_quantities" in analysis_text
    assert "from qpx_harness.analysis.green_gauss import" in application_text
    assert "method: str" in application_text
    assert "analyze_gradient_reconstruction" in operations_text
    assert "analyze_green_gauss" not in operations_text
    assert not (ROOT / "qpx_harness/application/green_gauss_workflow.py").exists()


def test_repository_root_launcher_delegates_to_single_canonical_qpx_entrypoint() -> None:
    launcher = ROOT / "qpx"
    canonical = ROOT / "bin/qpx.py"
    assert launcher.is_file()
    assert canonical.is_file()
    launcher_text = launcher.read_text()
    canonical_text = canonical.read_text()
    assert '"bin" / "qpx.py"' in launcher_text
    assert "qpx_harness.cli" in canonical_text
