"""Canonical metric-engine behavior and legacy Human Understandability compatibility."""

from dataclasses import replace
from types import SimpleNamespace as Obj

from libs.code_understandability import (
    HumanObservation, UnderstandabilityAssessment, UnderstandabilityInput,
    compare_understandability, evaluate_understandability, from_python_ast,
)
from libs.hu import HUAssessment, HUInput, HUObservation, compare_hu, evaluate_hu
from physics_harness.code.analysis import (
    assess_code_understandability, interpret_understandability_indicators,
    summarize_understandability,
)
from physics_harness.code.analysis.hu_adapter import assess_code_hu, summarize_hu
from physics_harness.code.analysis.hu_interpretation import interpret_hu_indicators
from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan
from physics_harness.code.refactor import (
    PlanningAlternative, build_planning_context, review_alternatives,
)


REV = "a" * 40
BLOB = "b" * 40


def sample(*, observations=(), attrs=None):
    metrics = from_python_ast(
        {"loc": 20, "branches": 4} if attrs is None else attrs,
        evidence_ids=("ev:source",),
    )
    return UnderstandabilityInput(
        "node:target", REV, BLOB, structural_metrics=metrics,
        observations=observations,
    )


def diagnostic(*, attributes=None):
    node = Obj(
        id="node:target", location=Obj(path="src/example.py"),
        attributes={"loc": 4, "branches": 1} if attributes is None else attributes,
        evidence_ids=("ev:source",),
    )
    graph = Obj(
        scope=Obj(id="scope:1", repository="example/repo", revision=REV,
                  unresolved=(), completeness="COMPLETE"),
        nodes_by_id=lambda: {node.id: node}, edges=(),
    )
    receipt = Obj(
        repository="example/repo", revision=REV, scope_id="scope:1",
        files=(Obj(path="src/example.py", blob_sha=BLOB, status="SCANNED",
                   collectors=("python_ast",)),),
        unresolved=(), completeness="COMPLETE",
    )
    verified = Obj(
        repository="example/repo", revision=REV, scope_id="scope:1",
        status="VERIFIED", unverified_properties=(),
    )
    return Obj(graph=graph, receipt=receipt, verification=verified)


def test_metrics_do_not_require_human_rating():
    result = evaluate_understandability(sample())
    assert isinstance(result, UnderstandabilityAssessment)
    assert [i.name for i in result.indicators] == ["branch_density"]
    assert result.indicators[0].value == 0.2
    assert result.predicted_score is None
    assert result.observed == ()
    assert "HUMAN_UNDERSTANDABILITY_NOT_OBSERVED" not in result.unknowns


def test_human_judgments_are_optional_evidence_not_a_score():
    observed = (
        HumanObservation("person1", "question", "intent", True, REV, BLOB),
        HumanObservation("person2", "question", "intent", False, REV, BLOB),
    )
    result = evaluate_understandability(sample(observations=observed))
    assert result.observed[0].positive_rate == 0.5
    assert result.predicted_score is None


def test_legacy_models_are_identity_aliases_and_keep_historical_missingness():
    assert HUInput is UnderstandabilityInput
    assert HUAssessment is UnderstandabilityAssessment
    assert HUObservation is HumanObservation
    old = evaluate_hu(sample())
    current = evaluate_understandability(sample())
    assert old.indicators == current.indicators
    assert "HUMAN_UNDERSTANDABILITY_NOT_OBSERVED" in old.unknowns
    assert "HUMAN_UNDERSTANDABILITY_NOT_OBSERVED" not in current.unknowns
    assert isinstance(replace(old, unknowns=("UNKNOWN_SCOPE",)), UnderstandabilityAssessment)


def test_comparisons_preserve_measurement_deltas_and_unknowns():
    a = sample()
    b = sample(attrs={"loc": 20, "branches": 2})
    comparison = compare_understandability(
        evaluate_understandability(a), evaluate_understandability(b),
    )
    assert comparison.indicator_differences[0].difference == -0.1
    assert "STRUCTURAL_DELTA_NOT_UNDERSTANDABILITY_IMPROVEMENT_PROOF" in comparison.unknowns
    assert not comparison.improvement_proven
    legacy = compare_hu(evaluate_hu(a), evaluate_hu(b))
    assert "STRUCTURAL_DELTA_NOT_HU_IMPROVEMENT_PROOF" in legacy.unknowns
    assert legacy.indicator_differences == comparison.indicator_differences


def test_new_adapter_reports_measured_code_metrics_without_human_gate():
    scan = diagnostic()
    assessment = assess_code_understandability(scan, "node:target")
    assert "HUMAN_UNDERSTANDABILITY_NOT_OBSERVED" not in assessment.unknowns
    record = summarize_understandability(assessment)
    assert record.name == "CODE_UNDERSTANDABILITY"
    assert record.status == "MEASURED"
    assert record.source_revision == REV
    assert record.values[-1].name == "indicator.branch_density"
    interpretation = interpret_understandability_indicators(assessment)
    assert interpretation.name == "CODE_UNDERSTANDABILITY_INTERPRETATION"
    assert "UNDERSTANDABILITY_IMPROVEMENT_NOT_INFERRED_FROM_INDICATORS" in interpretation.unknowns


def test_legacy_adapter_output_keys_and_status_are_preserved():
    scan = diagnostic()
    legacy = assess_code_hu(scan, "node:target")
    record = summarize_hu(legacy)
    assert record.name == "HU"
    assert record.status == "REVIEW_REQUIRED"
    assert "HUMAN_UNDERSTANDABILITY_NOT_OBSERVED" in record.unknowns
    interpreted = interpret_hu_indicators(legacy)
    assert interpreted.name == "HU_INTERPRETATION"
    assert "HU_IMPROVEMENT_NOT_INFERRED_FROM_INDICATORS" in interpreted.unknowns


def test_missing_code_facts_remain_unknown_and_not_measured():
    result = assess_code_understandability(diagnostic(attributes={}), "node:target")
    record = summarize_understandability(result)
    assert record.status == "REVIEW_REQUIRED"
    assert not record.values
    assert "HU_STRUCTURAL_METRICS_UNAVAILABLE" in record.unknowns


def test_real_scan_metrics_flow_into_planning_without_human_raters(git_factory):
    root, sha = git_factory({
        "src/sample.py": "def choose(value):\n    if value:\n        return 1\n    return 0\n",
    })
    scanned = run_scan(
        ScanRequest(repository="example/repo", revision=sha,
                    includes=("src/*.py",), collectors=("python_ast",)),
        GitSourceProvider(root),
    )
    node = next(n for n in scanned.graph.nodes
                if n.kind == "python_function" and n.name == "choose")
    metric = assess_code_understandability(scanned, node.id)
    record = summarize_understandability(metric)
    interpretation = interpret_understandability_indicators(metric)
    assert record.status == "MEASURED"
    context = build_planning_context(
        scanned, node.id, objectives=("Understandability",),
        assessments=(record, interpretation),
    )
    result = review_alternatives(
        context,
        (PlanningAlternative("baseline", "KEEP", "No source change"),),
    )
    assert result.results[0].disposition == "ADMISSIBLE"
    assert not result.mutation_approved
