"""Legacy module-path compatibility for the #769 read-only naming integration.

No numerical algorithm or public symbol definition is changed by these aliases.
"""
import importlib

import pytest


@pytest.mark.parametrize(
    "old_path,new_path,public_symbols",
    [
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
    from libs.code_lucidity import UnderstandabilityInput
    from physics_harness.code.analysis.adapters.lucidity_adapter import assess_code_understandability
    from physics_harness.code.verification.naming_replay import ReplayArtifact

    assert UnderstandabilityInput.__module__ == "libs.code_lucidity.model"
    assert assess_code_understandability.__module__ == "physics_harness.code.analysis.adapters.lucidity_adapter"
    assert ReplayArtifact.__module__ == "physics_harness.code.verification.junit_compare"


@pytest.mark.parametrize("retired", [
    "libs.code_understandability",
    "libs.code_understandability.evaluation",
    "libs.code_understandability.metrics",
    "libs.code_understandability.model",
    "physics_harness.code.analysis.understandability_adapter",
    "physics_harness.code.analysis.understandability_interpretation",
    "physics_harness.code.analysis.lucidity_adapter",
    "physics_harness.code.analysis.lucidity_interpretation",
])
def test_retired_module_path_cannot_be_imported(retired):
    with pytest.raises(ModuleNotFoundError) as exc:
        importlib.import_module(retired)
    assert retired == exc.value.name or retired.startswith(exc.value.name + ".")
