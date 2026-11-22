"""Verification v0.1: source artifact integrity and inferred change obligations."""

from dataclasses import replace

import pytest

from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan
from physics_harness.code.graph import Evidence, GraphSnapshot
from physics_harness.code.verification import (
    ChangeVerificationPlan, VerificationReceipt,
    plan_change_verification, verify_generated_artifact,
)
from physics_harness.code.verification.consistency import (
    VerificationReceipt as ConsistencyReceipt,
    verify_generated_artifact as verify_consistency,
)
from physics_harness.code.verification.dependencies import (
    ChangeVerificationPlan as PostChangePlan,
    plan_change_verification as plan_post_change,
)


def scan(git_factory, content, *, path="src/kernel.C", collector="cpp"):
    root, sha = git_factory({path: content})
    req = ScanRequest(
        repository="example/repo", revision=sha,
        includes=(path,), collectors=(collector,),
    )
    return run_scan(req, GitSourceProvider(root))


def test_verification_module_owners_preserve_package_api():
    assert VerificationReceipt is ConsistencyReceipt
    assert verify_generated_artifact is verify_consistency
    assert ChangeVerificationPlan is PostChangePlan
    assert plan_change_verification is plan_post_change


def test_every_diagnostic_scan_attaches_scope_limited_verified_receipt(git_factory):
    result = scan(git_factory, 'registerMooseObject("App", A);\n')
    assert result.status == "COMPLETE"
    verification = result.verification
    assert verification.status == "VERIFIED"
    assert verification.artifact_verified
    assert verification.revision == result.graph.scope.revision
    assert "SOURCE_METADATA_PROVENANCE" in verification.verified_properties
    assert "SEMANTIC_COMPATIBILITY_UNPROVEN" in verification.unverified_properties
    assert not verification.semantic_compatibility_proven


def test_new_directory_does_not_require_any_fixed_policy_role(git_factory):
    result = scan(git_factory, "def new_func():\n    return 1\n",
                  path="new_capability/new.py", collector="python_ast")
    assert result.verification.status == "VERIFIED"
    assert result.receipt.scanned_count == 1


def test_bad_revision_and_wrong_blob_are_not_auto_verified(git_factory):
    result = scan(git_factory, 'registerMooseObject("App", A);\n')
    wrong_sha = replace(result.receipt, revision="f" * 40)
    cross_head = verify_generated_artifact(result.graph, wrong_sha)
    assert cross_head.status == "FAILED"
    assert "GRAPH_RECEIPT_SCOPE_MISMATCH" in cross_head.failures

    entry = result.receipt.files[0]
    wrong_blob = replace(result.receipt, files=(
        replace(entry, blob_sha="a" * 40),))
    mismatch = verify_generated_artifact(result.graph, wrong_blob)
    assert mismatch.status == "FAILED"
    assert any("SOURCE_REFERENCE_NOT_BOUND" in f for f in mismatch.failures)


def test_forged_source_line_or_path_is_detected(git_factory):
    result = scan(git_factory, 'registerMooseObject("App", A);\n')
    source = next(e for e in result.graph.evidence if e.method != "GIT_TREE")
    new_ev = replace(source, source_ref="src/kernel.C:999@" +
                     result.receipt.files[0].blob_sha)
    evidence = tuple(new_ev if x.id == source.id else x
                     for x in result.graph.evidence)
    graph = replace(result.graph, evidence=evidence)
    check = verify_generated_artifact(graph, result.receipt)
    assert check.status == "FAILED"
    assert any("SOURCE_LINE_MISMATCH" in x for x in check.failures)


def test_partial_scan_remains_unverified_not_failed(git_factory):
    result = scan(git_factory, '#if FEATURE\nregisterMooseObject("App", A);\n#endif\n')
    assert result.status == "PARTIAL"
    assert result.verification.status == "UNVERIFIED"
    assert "INCOMPLETE_REQUESTED_SCOPE" in result.verification.unverified_properties
    assert not result.verification.artifact_verified


def test_external_runtime_claim_needs_independent_verification(git_factory):
    result = scan(git_factory, 'registerMooseObject("App", A);\n')
    scope = result.graph.scope
    evidence = Evidence(
        "runtime:1", "RUNTIME", "https://example.invalid/runs/2",
        "GITHUB_ACTIONS_REST", scope.id,
        observation_status="RUNTIME_OBSERVED",
        attributes={"source_sha":scope.revision, "run_id":2,"attempt":1,
                    "url":"https://example.invalid/runs/2"},
    )
    graph = replace(result.graph, evidence=result.graph.evidence + (evidence,))
    check = verify_generated_artifact(graph, result.receipt)
    assert check.status == "UNVERIFIED"
    assert "RUNTIME_EXECUTION_NOT_INDEPENDENTLY_VERIFIED" in check.unverified_properties
    bad = replace(evidence, attributes={
        **dict(evidence.attributes), "source_sha":"d"*40,
    })
    corrupted = replace(graph, evidence=graph.evidence[:-1] + (bad,))
    assert verify_generated_artifact(corrupted, result.receipt).status == "FAILED"


def test_dependency_addition_requests_impact_and_test_replay(git_factory):
    first = scan(git_factory, "def foo():\n    return 1\n",
                 path="new_area/a.py", collector="python_ast")
    second = scan(git_factory,
                  "from pathlib import Path\n\ndef foo():\n    return Path('x')\n",
                  path="new_area/a.py", collector="python_ast")
    plan = plan_change_verification(
        first.graph, second.graph, first.receipt, second.receipt)
    assert "VERIFY_DEPENDENCY_AND_CALL_IMPACT" in plan.required_checks
    assert "REPLAY_IMPACTED_TESTS_AT_AFTER_HEAD" in plan.required_checks
    assert plan.impacted_subjects
    assert not plan.mutation_approved
    assert plan.disposition == "UNVERIFIED"


def test_removed_registration_requires_consumer_closure(git_factory):
    before = scan(git_factory, 'registerMooseObject("App", A);\n')
    after = scan(git_factory, "// registration removed\n")
    plan = plan_change_verification(
        before.graph, after.graph, before.receipt, after.receipt)
    assert "VERIFY_REMOVED_CONSUMERS_AND_REFERENCES" in plan.required_checks
    assert not plan.mutation_approved


def test_partial_after_head_requires_coverage_resolution(git_factory):
    before = scan(git_factory, 'registerMooseObject("App", A);\n')
    after = scan(git_factory, '#if T\nregisterMooseObject("App", A);\n#endif\n')
    plan = plan_change_verification(
        before.graph, after.graph, before.receipt, after.receipt)
    assert "RESOLVE_SOURCE_PROVENANCE_AND_COVERAGE" in plan.required_checks
    assert "VERIFY_SCOPE_AND_UNRESOLVED_DELTA" in plan.required_checks
    assert not plan.mutation_approved



def test_new_cross_package_import_derives_checks_not_a_role_policy(git_factory):
    before = scan(git_factory, "def use():\n    return 1\n",
                  path="physics_harness/ontology/new.py", collector="python_ast")
    after = scan(git_factory,
                 "from physics_harness.adapters.moose import create\n"
                 "def use():\n    return create\n",
                 path="physics_harness/ontology/new.py", collector="python_ast")
    plan = plan_change_verification(
        before.graph, after.graph, before.receipt, after.receipt)
    assert "VERIFY_DEPENDENCY_AND_CALL_IMPACT" in plan.required_checks
    assert "REPLAY_IMPACTED_TESTS_AT_AFTER_HEAD" in plan.required_checks
    assert not plan.mutation_approved
    assert not any(x.startswith("FORBIDDEN_ROLE") for x in plan.findings)


def test_new_subprocess_use_generates_evidence_obligation_not_path_rejection(git_factory):
    before = scan(git_factory, "def invoke():\n    return 1\n",
                  path="physics_harness/ontology/new.py", collector="python_ast")
    after = scan(git_factory,
                 "import subprocess\n"
                 "def invoke():\n    return subprocess.run(['true'])\n",
                 path="physics_harness/ontology/new.py", collector="python_ast")
    plan = plan_change_verification(
        before.graph, after.graph, before.receipt, after.receipt)
    assert "VERIFY_DEPENDENCY_AND_CALL_IMPACT" in plan.required_checks
    assert "VERIFY_BEHAVIORAL_COMPATIBILITY" in plan.required_checks
    assert plan.disposition == "UNVERIFIED"
    assert not plan.mutation_approved


@pytest.mark.parametrize("source_ref_suffix", [
    ":0@", ":-1@", ":1.5@", ":1@", "x:1@", ":1@",
])
def test_source_reference_lookup_rejects_invalid_line_blob_and_prefix(
    git_factory, source_ref_suffix,
):
    result = scan(git_factory, 'registerMooseObject("App", A);\n')
    source = next(e for e in result.graph.evidence if e.method != "GIT_TREE")
    path = result.receipt.files[0].path
    blob = result.receipt.files[0].blob_sha
    if source_ref_suffix == ":1@":
        ref = path + source_ref_suffix + ("a" * 40 if blob != "a" * 40 else "b" * 40)
    elif source_ref_suffix == "x:1@":
        ref = path + source_ref_suffix + blob
    else:
        ref = path + source_ref_suffix + blob
    changed = replace(source, source_ref=ref)
    graph = replace(result.graph, evidence=tuple(
        changed if item.id == source.id else item for item in result.graph.evidence
    ))
    report = verify_generated_artifact(graph, result.receipt)
    assert report.status == "FAILED"
    assert f"SOURCE_REFERENCE_NOT_BOUND_TO_RECEIPT:{source.id}" in report.failures


def test_shared_blob_across_distinct_source_paths_remains_verified(git_factory):
    text = 'registerMooseObject("App", A);\n'
    root, revision = git_factory({"src/first.C": text, "src/second.C": text})
    request = ScanRequest(
        repository="example/repo", revision=revision,
        includes=("src/*.C",), collectors=("cpp",),
    )
    diagnostic = run_scan(request, GitSourceProvider(root))
    assert len(diagnostic.receipt.files) == 2
    assert diagnostic.receipt.files[0].blob_sha == diagnostic.receipt.files[1].blob_sha
    assert diagnostic.verification.status == "VERIFIED"
    again = verify_generated_artifact(diagnostic.graph, diagnostic.receipt)
    assert again.status == "VERIFIED"
    assert not again.failures


def test_line_reference_must_match_evidence_attributes_with_shared_blob(git_factory):
    source_text = 'registerMooseObject("App", A);\n'
    root, revision = git_factory({
        "src/first.C": source_text, "src/second.C": source_text,
    })
    diagnostic = run_scan(
        ScanRequest(repository="example/repo", revision=revision,
                    includes=("src/*.C",), collectors=("cpp",)),
        GitSourceProvider(root),
    )
    evidence = next(x for x in diagnostic.graph.evidence
                    if x.method != "GIT_TREE" and x.attributes.get("line") == 1)
    path, _, blob = evidence.source_ref.partition(":1@")
    corrupted = replace(evidence, source_ref=f"{path}:2@{blob}")
    graph = replace(diagnostic.graph, evidence=tuple(
        corrupted if x.id == evidence.id else x for x in diagnostic.graph.evidence
    ))
    verification = verify_generated_artifact(graph, diagnostic.receipt)
    assert verification.status == "FAILED"
    assert f"SOURCE_LINE_MISMATCH:{evidence.id}" in verification.failures
