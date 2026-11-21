"""Repository integration: actual run_scan -> HU adapter -> planning context.

Runs in moose-test-repo with the existing Diagnostics/Graph infrastructure.
"""

from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan
from physics_harness.code.analysis.hu_adapter import assess_code_hu, summarize_hu
from physics_harness.code.refactor import (
    PlanningAlternative, build_planning_context,
    review_alternatives,
)


def test_actual_run_scan_data_flows_into_hu_and_planning(git_factory):
    root, revision = git_factory({
        "src/example.py": (
            "def choose(value):\n"
            "    if value:\n"
            "        return 'yes'\n"
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
    hu = assess_code_hu(scan, target.id)
    assert hu.revision == revision
    assert {m.name: m.value for m in hu.structural_metrics}["branches"] == 1
    assert hu.predicted_score is None
    summary = summarize_hu(hu)
    assert {v.name: v.value for v in summary.values}["structural.branches"] == 1
    context = build_planning_context(
        scan, target.id, objectives=("Clarity",), assessments=(summary,),
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
