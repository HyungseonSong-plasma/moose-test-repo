"""Repository integration: actual run_scan -> code-understandability Adapter -> planning context.

Runs in moose-test-repo with the existing Diagnostics/Graph infrastructure.
"""

from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan
from physics_harness.code.analysis.adapters.lucidity_adapter import assess_code_understandability, summarize_understandability
from physics_harness.code.analysis.adapters.lucidity_interpretation import interpret_understandability_indicators
from physics_harness.code.refactor import (
    PlanningAlternative, build_planning_context,
    review_alternatives,
)


def test_actual_run_scan_data_flows_into_metrics_and_planning(git_factory):
    root, revision = git_factory({
        "src/example.py": (
            "def choose(value):\n"
            "    if value:\n"
            "        return str(value)\n"
            "    return 'no'\n"
        ),
    })
    scan = run_scan(
        ScanRequest(repository="example/repo", revision=revision,
                    includes=("src/*.py",), collectors=("python_ast",)),
        GitSourceProvider(root),
    )
    assert scan.status == "COMPLETE"
    target = next(n for n in scan.graph.nodes
                  if n.kind == "python_function" and n.name == "choose")
    assessment = assess_code_understandability(scan, target.id)
    assert assessment.revision == revision
    assert {m.name: m.value for m in assessment.structural_metrics}["branches"] == 1
    assert assessment.predicted_score is None
    summary = summarize_understandability(assessment)
    assert {v.name: v.value for v in summary.values}["structural.branches"] == 1
    computed = {v.name: v.value for v in summary.values}
    assert computed["indicator.branch_density"] == 0.25
    assert computed["indicator.candidate_call_density"] == 0.25
    interpretation = interpret_understandability_indicators(assessment)
    assert interpretation.name == "CODE_UNDERSTANDABILITY_INTERPRETATION"
    assert "not a count of independent responsibilities" in interpretation.summary
    assert "not resolved callees" in interpretation.summary
    assert "UNDERSTANDABILITY_IMPROVEMENT_NOT_INFERRED_FROM_INDICATORS" in interpretation.unknowns
    context = build_planning_context(
        scan, target.id, objectives=("Clarity",),
        assessments=(summary, interpretation),
    )
    baseline = PlanningAlternative("baseline", "KEEP", "Keep the function")
    change = PlanningAlternative(
        "candidate", "CHANGE", "Consider a different expression",
        affected_paths=("src/example.py",), evidence_ids=target.evidence_ids,
        expected_benefits=("Potential readability improvement",),
        risks=("Might alter falsy-value semantics",),
    )
    review = review_alternatives(context, (baseline, change))
    assert tuple(x.disposition for x in review.results) == (
        "ADMISSIBLE", "ADMISSIBLE",
    )
    assert review.recommended_id is None
    assert "VERIFY_BEHAVIORAL_COMPATIBILITY" in review.results[1].required_checks
