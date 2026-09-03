from pathlib import Path

from qpx_harness.evidence_engine import (
    AttributionConfidence,
    AttributionSignals,
    ErrorCategory,
    ErrorLedger,
    classify_attribution,
    create_collision_safe_directory,
    current_run_artifact,
)
from qpx_harness.evidence import error_log as legacy_error_log
from qpx_harness.evidence import artifacts as legacy_artifacts
from qpx_harness.evidence import identity as legacy_identity
from qpx_harness.evidence_engine import artifacts as engine_artifacts
from qpx_harness.evidence_engine import errors as engine_errors
from qpx_harness.evidence_engine import identity as engine_identity


def test_legacy_evidence_modules_are_facades_over_unified_engine():
    assert legacy_error_log.ErrorLedger is engine_errors.ErrorLedger
    assert legacy_error_log.classify_attribution is engine_errors.classify_attribution
    assert legacy_artifacts.current_run_artifact is engine_artifacts.current_run_artifact
    assert legacy_identity.create_collision_safe_directory is engine_identity.create_collision_safe_directory
    assert ErrorLedger is engine_errors.ErrorLedger
    assert current_run_artifact is engine_artifacts.current_run_artifact
    assert create_collision_safe_directory is engine_identity.create_collision_safe_directory


def test_attribution_requires_provenance_and_keeps_conflicts_unclassified():
    user = classify_attribution(
        AttributionSignals(user_controlled_contract_violation=True)
    )
    assistant = classify_attribution(
        AttributionSignals(assistant_generated_contract_violation=True)
    )
    code = classify_attribution(
        AttributionSignals(
            contract_conformant=True,
            reproducible_runtime_failure=True,
            isolated_code_owner="FVDiffusion",
        )
    )
    conflict = classify_attribution(
        AttributionSignals(
            user_controlled_contract_violation=True,
            assistant_generated_contract_violation=True,
        )
    )

    assert user.category is ErrorCategory.USER_ERROR
    assert assistant.category is ErrorCategory.CHATGPT_ERROR
    assert code.category is ErrorCategory.CODE_ERROR
    assert code.confidence is AttributionConfidence.CONFIRMED
    assert conflict.category is ErrorCategory.UNCLASSIFIED
    assert conflict.confidence is AttributionConfidence.UNRESOLVED


def test_error_ledger_accumulates_run_and_persistent_statistics(tmp_path: Path):
    persistent = tmp_path / "persistent" / "errors.jsonl"
    run_root = tmp_path / "run"
    ledger = ErrorLedger.for_run(run_root, persistent_path=persistent)

    user = classify_attribution(
        AttributionSignals(user_controlled_contract_violation=True)
    )
    code = classify_attribution(
        AttributionSignals(
            contract_conformant=True,
            reproducible_runtime_failure=True,
            isolated_code_owner="QPXElectronTransportLookupMaterial",
        )
    )

    ledger.record(
        run_id="run-1",
        issue=94,
        stage="P1",
        case_id="L1",
        error_code="INPUT_CONTRACT_MISMATCH",
        message="declared input does not match the frozen contract",
        source_layer="experiment_contract",
        attribution=user,
        signature="input-contract",
    )
    ledger.record(
        run_id="run-1",
        issue=94,
        stage="P3",
        case_id="L3",
        error_code="REPRODUCIBLE_RUNTIME_FAILURE",
        message="lookup-owned diffusion case reproduces the failure",
        source_layer="qpx_material",
        attribution=code,
        signature="lookup-runtime",
    )

    assert len(ledger.run_events()) == 2
    assert len(ledger.persistent_events()) == 2
    summary = ledger.run_summary()
    assert summary["event_count"] == 2
    assert summary["by_category"] == {"CODE_ERROR": 1, "USER_ERROR": 1}
    assert summary["unique_fingerprint_count"] == 2

    paths = ledger.write_summaries(run_root)
    assert Path(paths["run"]).is_file()
    assert Path(paths["persistent"]).is_file()
