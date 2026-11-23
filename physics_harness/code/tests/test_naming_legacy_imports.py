"""Legacy module-path compatibility for the #769 read-only naming integration.

No numerical algorithm or public symbol definition is changed by these aliases.
"""
import importlib

import pytest


@pytest.mark.parametrize(
    "old_path,new_path,public_symbols",
    [
        ("libs.code_understandability", "libs.code_lucidity",
         ("UnderstandabilityInput", "evaluate_understandability", "from_python_ast")),
        ("libs.code_understandability.evaluation", "libs.code_lucidity.evaluation",
         ("evaluate_understandability", "compare_understandability", "MetricDifference")),
        ("libs.code_understandability.metrics", "libs.code_lucidity.metrics",
         ("from_python_ast", "derive_indicators")),
        ("libs.code_understandability.model", "libs.code_lucidity.model",
         ("UnderstandabilityInput", "UnderstandabilityAssessment", "HumanObservation")),
        ("physics_harness.code.analysis.understandability_adapter",
         "physics_harness.code.analysis.lucidity_adapter",
         ("assess_code_understandability", "summarize_understandability")),
        ("physics_harness.code.analysis.understandability_interpretation",
         "physics_harness.code.analysis.lucidity_interpretation",
         ("interpret_understandability_indicators",)),
        ("physics_harness.code.verification.naming_replay",
         "physics_harness.code.verification.junit_compare",
         ("ReplayArtifact", "ReplayComparison", "compare_candidate_replay")),
        ("physics_harness.code.verification.naming_replay_execution",
         "physics_harness.code.verification.pytest_revision_runner",
         ("NamingReplayRun", "NamingReplayReceipt",
          "run_naming_test_replay", "build_executed_replay_artifact_pair")),
    ],
)
def test_legacy_import_path_preserves_public_symbol_identity(
    old_path, new_path, public_symbols
):
    old = importlib.import_module(old_path)
    new = importlib.import_module(new_path)
    for symbol in public_symbols:
        assert getattr(old, symbol) is getattr(new, symbol), (old_path, symbol)


def test_legacy_objects_are_defined_only_in_canonical_module():
    from libs.code_understandability import UnderstandabilityInput
    from physics_harness.code.analysis.understandability_adapter import assess_code_understandability
    from physics_harness.code.verification.naming_replay import ReplayArtifact

    assert UnderstandabilityInput.__module__ == "libs.code_lucidity.model"
    assert assess_code_understandability.__module__ == "physics_harness.code.analysis.lucidity_adapter"
    assert ReplayArtifact.__module__ == "physics_harness.code.verification.junit_compare"
