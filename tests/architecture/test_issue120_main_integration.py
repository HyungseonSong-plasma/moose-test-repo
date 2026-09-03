from __future__ import annotations

from pathlib import Path

from qpx_harness.application import load_experiment_spec
from qpx_harness.application.experiment_registry import protocol_registered, registered_protocols
from qpx_harness.cli.app import COMMANDS, INTERNAL_TARGETS, main
from qpx_harness.execution.status import ExecutionState
from qpx_harness.validation import ValidationKind, ValidationSurface, validate_command_surface

ROOT = Path(__file__).resolve().parents[2]


def test_cli_contract_and_internal_gateway_surface() -> None:
    assert validate_command_surface(COMMANDS, INTERNAL_TARGETS) == []
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


def test_current_operator_protocols_are_declarative_and_registered() -> None:
    expected = {
        "r3-electron-master-diagnostic": ROOT / "experiments/R3_electron_master_diagnostic/experiment.json",
        "r3-electron-scaling-counterfactual": ROOT / "experiments/R3_electron_scaling_counterfactual/experiment.json",
        "r3-fv-internal-completion": ROOT / "experiments/R3_fv_internal_completion/experiment.json",
        "r4-qf2-local-charge-relaxation": ROOT / "experiments/Issue31_r4_qf2_local_charge_relaxation/experiment.json",
    }
    assert set(registered_protocols()) == set(expected)
    for protocol, path in expected.items():
        spec = load_experiment_spec(path)
        assert spec.protocol == protocol
        assert protocol_registered(spec.protocol)


def test_green_gauss_quantitative_formula_owner_is_analysis() -> None:
    evidence_text = (ROOT / "qpx_harness/evidence/transform.py").read_text()
    analysis_text = (ROOT / "qpx_harness/analysis/green_gauss.py").read_text()
    assert "def normalize_face_evidence" in evidence_text
    assert "from qpx_harness.analysis.green_gauss import derive_face_quantities" in evidence_text
    assert "reconstructed_surface_x" not in evidence_text
    assert "reconstructed_surface_x" in analysis_text
    assert "def derive_cell_quantities" in analysis_text


def test_repository_root_launcher_exists_for_python_qpx_form() -> None:
    launcher = ROOT / "qpx"
    assert launcher.is_file()
    assert "qpx_harness.cli" in launcher.read_text()
