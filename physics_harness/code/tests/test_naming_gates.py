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


def test_p1_new_destination_duplicate_is_not_validated(history):
    root, before, base = history
    third_commit(history)
    new_path = "diagnostics/providers/new.py"
    (root / new_path).write_text("def python_decode(source): return source\ndef python_decode(source): return None\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "new destination collision")
    after = git(root, "rev-parse", "HEAD")
    mapped = placements()[:-1] + (replace(placements()[-1], after_symbol=new_path+"::function:python_decode"),)
    result = evaluate_naming_safety_gates(
        case(before, base), extract_option(dest=new_path, existing=False),
        GitSourceProvider(root), bindings(), after, PATH, mapped)
    assert result.structural.status == "HOLD"
    assert "AMBIGUOUS_DECLARATION:"+new_path+"::function:python_decode" in result.structural.unresolved
    assert mapped[-1] not in result.structural.validated_placements
    assert not result.behavior.comparisons


def test_p1_duplicate_candidate_class_cannot_validate_owner(history):
    root, before, base = history
    third_commit(history)
    p = root / PATH
    p.write_text(p.read_text() + "\nclass Collector:\n    def other(self): return None\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "candidate owner collision")
    after = git(root, "rev-parse", "HEAD")
    result = evaluate_naming_safety_gates(case(before, base), extract_option(),
        GitSourceProvider(root), bindings(), after, PATH, placements())
    assert result.structural.status == "HOLD"
    assert placements()[0] not in result.structural.validated_placements
    assert not result.behavior.comparisons


@pytest.mark.parametrize("extra,ambiguous_key", [
    ("\nfrom typing import overload\n@overload\ndef python_decode(source): ...\n",
     "::function:python_decode"),
    ("\nclass Holder:\n    @property\n    def value(self): return 1\n"
     "    @value.setter\n    def value(self, v): pass\n", "::method:Holder.value"),
])
def test_p1_valid_python_repeated_keys_are_unresolved_not_invalid(history, extra, ambiguous_key):
    history, subject = _duplicate_baseline(history, extra)
    provider = GitSourceProvider(history[0])
    boundary = verify_naming_boundary(subject, keep(), provider, bindings())
    packet = build_blinded_semantic_packet(subject, provider, bindings())
    assert boundary.status == "HOLD"
    assert not boundary.blockers
    assert "AMBIGUOUS_DECLARATION:"+PATH+ambiguous_key in boundary.unresolved
    assert not any(e.symbol == PATH+ambiguous_key for e in packet.excerpts)


def test_p1_unique_control_excerpt_matches_exact_source_anchor(history):
    root, before, base = history
    packet = build_blinded_semantic_packet(case(before, base), GitSourceProvider(root), bindings())
    excerpt = next(e for e in packet.excerpts if e.symbol == PATH+"::function:python_decode")
    assert excerpt.source_ref == f"{PATH}:4@{digest(NEW)}"
    assert excerpt.code == "def python_decode(source):\n    return source"
    assert not packet.unresolved


def test_p1_mismatched_observed_anchor_cannot_be_a_blinded_excerpt(history, monkeypatch):
    # Inject a corrupted intermediate receipt, keeping real Git source immutable.
    from physics_harness.code.verification import naming_semantic_review as semantic
    root, before, base = history
    provider = GitSourceProvider(root)
    subject = case(before, base)
    gate = verify_naming_boundary(subject, keep(), provider, bindings())
    forged = tuple(replace(s, source_ref=f"{PATH}:7@{digest(NEW)}")
                   if s.key == PATH+"::function:python_decode" else s
                   for s in gate.observed_symbols)
    monkeypatch.setattr(semantic, "verify_naming_boundary", lambda *a, **kw:
                        replace(gate, observed_symbols=forged))
    packet = build_blinded_semantic_packet(subject, provider, bindings())
    assert "BLINDED_DECLARATION_ANCHOR_MISMATCH:"+PATH+"::function:python_decode" in packet.unresolved
    assert not any(e.symbol == PATH+"::function:python_decode" for e in packet.excerpts)


def test_p1_second_pass_cannot_credit_ambiguous_observation(history):
    from physics_harness.code.verification.naming_semantic_review import review_semantic_challenge
    history, subject = _duplicate_baseline(
        history, "\ndef python_decode(source):\n    return None\n", evidence_line=10)
    provider = GitSourceProvider(history[0])
    packet = build_blinded_semantic_packet(subject, provider, bindings())
    opt = extract_option()
    receipt = review_semantic_challenge(packet, hypotheses(packet), challenge(opt), opt)
    key = PATH+"::function:python_decode"
    assert key in packet.observed_symbol_keys
    assert key not in receipt.verified_symbol_coverage
    assert "REVIEW_SYMBOL_WITHOUT_VERIFIED_EXCERPT:"+key in receipt.unresolved
    assert receipt.status == "HOLD"


def test_p1_second_pass_cannot_credit_omitted_excerpt(history):
    from physics_harness.code.verification.naming_semantic_review import review_semantic_challenge
    root, before, base = history
    packet = build_blinded_semantic_packet(case(before, base), GitSourceProvider(root),
                                          bindings(), max_excerpts=1)
    opt = extract_option()
    receipt = review_semantic_challenge(packet, hypotheses(packet), challenge(opt), opt)
    assert set(receipt.verified_symbol_coverage) == {e.symbol for e in packet.excerpts}
    assert receipt.status == "HOLD"


def test_p1_residual_ambiguous_extracted_source_is_not_a_valid_placement(history):
    root, before, base = history
    candidate = third_commit(history, source=False)
    p = root / PATH
    p.write_bytes(p.read_bytes() + b"\ndef python_decode(source): return None\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "ambiguous residual source")
    candidate = git(root, "rev-parse", "HEAD")
    result = pipeline(history, candidate=candidate)
    assert result.structural.status == "HOLD"
    assert "EXTRACTED_SOURCE_SYMBOL_STILL_DECLARED:"+PATH+"::function:python_decode" in result.structural.unresolved
    assert placements()[-1] not in result.structural.validated_placements
    assert not result.behavior.comparisons


def test_p1_folder_ambiguity_preserves_unique_other_owners(history):
    history, subject = _duplicate_baseline(history, "\ndef python_decode(source): return None\n")
    subject = replace(subject, target_kind="FOLDER", current_path="diagnostics", current_name="diagnostics")
    provider = GitSourceProvider(history[0])
    boundary = verify_naming_boundary(subject, keep(), provider, bindings())
    packet = build_blinded_semantic_packet(subject, provider, bindings())
    assert boundary.status == "HOLD"
    assert "AMBIGUOUS_DECLARATION:"+PATH+"::function:python_decode" in boundary.unresolved
    assert not any(e.symbol == PATH+"::function:python_decode" for e in packet.excerpts)
    assert any(e.symbol == DEST+"::class:PythonProvider" for e in packet.excerpts)


def test_p1_nested_local_name_does_not_create_module_owner_collision(history):
    history, subject = _duplicate_baseline(history,
        "\ndef outer():\n    def python_decode(source): return None\n    return python_decode\n")
    subject = replace(subject, target_kind="FUNCTION", current_name="python_decode",
                      responsibility_ids=("python",))
    provider = GitSourceProvider(history[0])
    boundary = verify_naming_boundary(subject, keep(), provider, (bindings()[1],))
    assert boundary.status == "STRUCTURE_WITNESSED"


@pytest.mark.parametrize("first,second", [("return 1", "return 2"), ("return 2", "return 1")])
def test_p1_duplicate_order_never_selects_a_body(history, first, second):
    history, subject = _duplicate_baseline(history,
        f"\ndef python_decode(source): {first}\ndef python_decode(source): {second}\n")
    provider = GitSourceProvider(history[0])
    packet = build_blinded_semantic_packet(subject, provider, bindings())
    assert "AMBIGUOUS_DECLARATION:"+PATH+"::function:python_decode" in packet.unresolved
    assert not any(e.symbol == PATH+"::function:python_decode" for e in packet.excerpts)
