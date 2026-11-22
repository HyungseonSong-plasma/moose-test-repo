"""P0: one result surface never grants mutation permission from model text."""
from __future__ import annotations

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.tests.test_naming_boundary import (
    history, case, bindings, extract_option, PATH,
)
from physics_harness.code.tests.test_naming_candidate import third_commit, placements
from physics_harness.code.verification.naming_gates import evaluate_naming_safety_gates
from physics_harness.code.tests.test_naming_semantic_review import hypotheses, challenge


def pipeline(history, candidate=None, **kw):
    root,before,base=history
    if candidate is None:
        candidate=third_commit(history)
    return evaluate_naming_safety_gates(case(before,base),extract_option(),
        GitSourceProvider(root), bindings(), candidate, PATH, placements(),**kw)


def test_exact_commit_pipeline_has_all_gates_and_no_mutation_authority(history):
    r=pipeline(history)
    assert r.structural.status=="STRUCTURAL_DELTA_VERIFIED"
    assert r.behavior.status=="HOLD"
    assert r.consumers.status=="INTERNAL_SCAN_WITH_EXTERNAL_GAPS"
    assert r.blind_review_packet.excerpts
    assert r.status=="HOLD"
    assert not r.mutation_approved and not r.semantic_compatibility_proven
    assert "AUTHENTICATED_INDEPENDENT_SEMANTIC_REVIEW" in r.required_checks


def test_submitted_self_report_does_not_upgrade_to_pass(history):
    root,before,base=history
    candidate=third_commit(history)
    first=pipeline(history,candidate=candidate)
    r=pipeline(history,candidate=candidate,
       reviewer_hypotheses=hypotheses(first.blind_review_packet),
       reviewer_challenge=challenge(extract_option()))
    assert r.semantic_review is not None
    assert r.semantic_review.status=="HOLD"
    assert r.status=="HOLD"
    assert not r.mutation_approved


def test_incomplete_two_pass_review_holds(history):
    root,before,base=history
    candidate=third_commit(history)
    r=pipeline(history,candidate=candidate,reviewer_hypotheses=())
    assert r.semantic_review is None
    assert "INCOMPLETE_TWO_PASS_SEMANTIC_REVIEW" in r.unresolved


def test_missing_candidate_symbol_blocks_pipeline(history):
    root,before,base=history
    candidate=third_commit(history,dest_source="class PythonProvider: pass\n")
    r=pipeline(history,candidate=candidate)
    assert r.status=="BLOCKED"
    assert any("CANDIDATE_SYMBOL_NOT_DECLARED" in x for x in r.blockers)


def test_repo_consumer_scan_budget_holds_even_if_no_imports(history):
    r=pipeline(history,max_consumer_files=1)
    assert r.status=="HOLD"
    assert "REPOSITORY_CONSUMER_FILE_BUDGET_EXCEEDED" in r.unresolved


from hashlib import sha256
from physics_harness.code.verification.naming_replay import ReplayArtifact


def _replay_artifact(revision: str, xml: bytes) -> ReplayArtifact:
    return ReplayArtifact(revision, xml, sha256(xml).hexdigest(), "test-fixture")


def test_candidate_replay_receipt_still_does_not_authorize_mutation(history):
    root, before, baseline = history
    candidate = third_commit(history)
    xml = b'<testsuite><testcase classname="contract" name="public_api"/></testsuite>'
    r = pipeline(history, candidate=candidate,
        replay_baseline=_replay_artifact(before, xml),
        replay_candidate=_replay_artifact(candidate, xml))
    assert r.replay is not None and r.replay.status == "HOLD"
    assert r.status in {"HOLD", "BLOCKED"}
    assert not r.mutation_approved
    assert "AUTHENTICATE_CI_PRODUCER_AND_ARTIFACT_ORIGIN" in r.unresolved


def test_candidate_replay_wrong_revision_blocks(history):
    root, before, baseline = history
    candidate = third_commit(history)
    xml = b'<testsuite><testcase name="public_api"/></testsuite>'
    r = pipeline(history, candidate=candidate,
        replay_baseline=_replay_artifact(before, xml),
        replay_candidate=_replay_artifact("c" * 40, xml))
    assert r.status == "BLOCKED"
    assert "REPLAY_REVISION_DOES_NOT_MATCH_NAMING_CANDIDATE" in r.blockers
