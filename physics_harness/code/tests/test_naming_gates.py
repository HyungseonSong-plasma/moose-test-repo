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
from physics_harness.code.verification.junit_compare import ReplayArtifact


def _replay_artifact(revision: str, xml: bytes) -> ReplayArtifact:
    return ReplayArtifact(revision, xml, sha256(xml).hexdigest(), "test-fixture")


def test_candidate_replay_receipt_still_does_not_authorize_mutation(history):
    root, before, baseline = history
    candidate = third_commit(history)
    xml = b'<testsuite><testcase classname="contract" name="public_api"/></testsuite>'
    r = pipeline(history, candidate=candidate,
        replay_baseline=_replay_artifact(baseline, xml),
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
        replay_baseline=_replay_artifact(baseline, xml),
        replay_candidate=_replay_artifact("c" * 40, xml))
    assert r.status == "BLOCKED"
    assert "REPLAY_REVISION_DOES_NOT_MATCH_NAMING_CANDIDATE" in r.blockers


# P1: exact-source declaration identity, not Python runtime rebinding.
from dataclasses import replace
import pytest
from physics_harness.code.tests.test_naming_boundary import NEW, DEST, git, digest, keep
from physics_harness.code.verification.naming_boundary import verify_naming_boundary
from physics_harness.code.verification.naming_candidate import verify_naming_candidate
from physics_harness.code.verification.naming_semantic_review import build_blinded_semantic_packet


def _duplicate_baseline(history, extra, *, evidence_line=None):
    root, before, baseline = history
    content = NEW + extra.encode()
    (root / PATH).write_bytes(content)
    git(root, "add", ".")
    git(root, "commit", "-qm", "baseline identity fixture")
    revision = git(root, "rev-parse", "HEAD")
    original = case(before, baseline)
    ev = []
    for e in original.evidence:
        if e.source_revision == baseline:
            refs = tuple(ref.rsplit("@", 1)[0] + "@" + digest(content)
                         for ref in e.source_refs)
            if e.id == "python" and evidence_line:
                refs = (f"{PATH}:{evidence_line}@{digest(content)}",)
            e = replace(e, source_revision=revision, source_refs=refs)
        ev.append(e)
    return (root, before, revision), replace(original, revision=revision, evidence=tuple(ev))


@pytest.mark.parametrize("before_duplicate,after_duplicate", [(False, True), (True, False), (True, True)])
def test_p1_no_ambiguous_placement_or_comparison(history, before_duplicate, after_duplicate):
    subject = case(history[1], history[2])
    if before_duplicate:
        history, subject = _duplicate_baseline(
            history, "\ndef python_decode(source):\n    return None\n", evidence_line=10)
    dest = "class PythonProvider:\n    def supports(self, value): return True\n\ndef python_decode(source):\n    return source\n"
    if after_duplicate:
        dest += "\ndef python_decode(source):\n    return None\n"
    candidate = third_commit(history, dest_source=dest)
    provider = GitSourceProvider(history[0])
    result = evaluate_naming_safety_gates(subject, extract_option(), provider,
                                         bindings(), candidate, PATH, placements())
    assert result.structural.status == "HOLD"
    assert any("AMBIGUOUS" in x for x in result.structural.unresolved)
    assert all(p.responsibility_id != "python" for p in result.structural.validated_placements)
    assert not result.behavior.comparisons
    if before_duplicate:
        assert not any(e.symbol == PATH+"::function:python_decode"
                       for e in result.blind_review_packet.excerpts)
        boundary = verify_naming_boundary(subject, keep(), provider, bindings())
        assert boundary.status == "HOLD"
        assert "python="+PATH+"::function:python_decode" not in boundary.verified_bindings


def test_p1_duplicate_parent_class_does_not_merge_methods(history):
    history, subject = _duplicate_baseline(history, "\nclass Collector:\n    def other(self): return None\n")
    provider = GitSourceProvider(history[0])
    boundary = verify_naming_boundary(subject, keep(), provider, bindings())
    packet = build_blinded_semantic_packet(subject, provider, bindings())
    assert boundary.status == "HOLD"
    assert "coord="+PATH+"::class:Collector" not in boundary.verified_bindings
    assert not any("::class:Collector" in e.symbol or "::method:Collector." in e.symbol
                   for e in packet.excerpts)


def test_p1_unique_function_ignores_unrelated_duplicate(history):
    history, subject = _duplicate_baseline(history, "\ndef cpp_decode(source):\n    return None\n")
    subject = replace(subject, target_kind="FUNCTION", current_name="python_decode",
                      responsibility_ids=("python",),
                      evidence=tuple(e for e in subject.evidence if e.id not in {"coord","cpp"}))
    provider = GitSourceProvider(history[0])
    mapped = (bindings()[1],)
    boundary = verify_naming_boundary(subject, keep(), provider, mapped)
    packet = build_blinded_semantic_packet(subject, provider, mapped)
    assert boundary.status == "STRUCTURE_WITNESSED"
    assert len(packet.excerpts) == 1
    expected_blob = git(history[0], "rev-parse", f"{history[2]}:{PATH}")
    assert packet.excerpts[0].source_ref == f"{PATH}:4@{expected_blob}"


def test_p1_competing_conditional_declaration_holds(history):
    history, subject = _duplicate_baseline(history, "\nif True:\n    def python_decode(source):\n        return None\n")
    provider = GitSourceProvider(history[0])
    boundary = verify_naming_boundary(subject, keep(), provider, bindings())
    assert boundary.status == "HOLD"
    assert any("AMBIGUOUS" in x for x in boundary.unresolved)
    assert "python="+PATH+"::function:python_decode" not in boundary.verified_bindings
