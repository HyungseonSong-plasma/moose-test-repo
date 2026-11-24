"""Definition CU modules have one canonical implementation and legacy aliases."""

from libs.code_lucidity import definition_metrics as canonical_metrics
from libs.code_lucidity import definition_discrimination as canonical_discrimination
from libs.code_understandability import definition_metrics as legacy_metrics
from libs.code_understandability import definition_discrimination as legacy_discrimination
from physics_harness.code.analysis import definition_inference


def test_definition_metrics_legacy_paths_share_canonical_types_and_functions():
    for name in ("DefinitionClause", "NameCue", "lexical_tokens", "measure_definition"):
        assert getattr(canonical_metrics, name) is getattr(legacy_metrics, name)
    for name in ("CandidateDefinition", "SignatureFacet", "discriminate_definition"):
        assert getattr(canonical_discrimination, name) is getattr(legacy_discrimination, name)


def test_analysis_inference_consumes_canonical_definition_type():
    assert definition_inference.DefinitionClause is canonical_metrics.DefinitionClause
    assert definition_inference.NameCue is canonical_metrics.NameCue
