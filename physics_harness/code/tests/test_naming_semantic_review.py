"""P0: no GPT self-attestation can become independent semantic clearance."""
from __future__ import annotations

from dataclasses import fields, replace

import pytest

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.tests.test_naming_boundary import (
    history, case, bindings, extract_option, PATH,
)
from physics_harness.code.verification.naming_semantic_review import (
    BlindedSemanticPacket, BlindedSourceExcerpt, IndependentResponsibilityHypothesis,
    SecondPassSemanticChallenge, build_blinded_semantic_packet,
    review_semantic_challenge,
)


def packet(history, **kwargs):
    root,before,baseline=history
    return build_blinded_semantic_packet(case(before,baseline),GitSourceProvider(root),
                                         bindings(),**kwargs)


def hypotheses(p):
    return (IndependentResponsibilityHypothesis("collection coordination",
        p.observed_symbol_keys,
        "Own source collection and delegate syntax-specific collection",
        "Does not analyze evidence quality or change production code",
        "If code executed refactor operations, this boundary would be false"),)


def challenge(option, *, disposition="ACCEPT_FOR_REPLAY", counterexamples=("Compare with keeping existing coordinator",)):
    return SecondPassSemanticChallenge(option.id,disposition,
        "Existing name is sufficient for collection coordination",
        "Extraction is justified only if code evidence proves an internal seam",
        counterexamples,"https://github.com/example/repo/pull/2#review-11")


def test_blinded_packet_has_no_candidate_name_or_selected_variant(history):
    p=packet(history)
    names={x.name for x in fields(BlindedSemanticPacket)}
    assert "proposed_name" not in names and "selected_variant" not in names
    assert p.observed_symbol_keys and p.excerpts
    assert all(x.source_ref.count("@") == 1 for x in p.excerpts)
    assert not p.mutation_approved


def test_consistent_review_is_still_not_authenticated(history):
    p=packet(history)
    opt=extract_option()
    r=review_semantic_challenge(p,hypotheses(p),challenge(opt),opt)
    assert r.status=="HOLD"
    assert not r.independent_reviewer_authenticated
    assert not r.semantic_compatibility_proven and not r.mutation_approved
    assert "REVIEWER_INDEPENDENCE_NOT_AUTHENTICATED" in r.unresolved


def test_second_pass_challenge_blocks_recommendation(history):
    p=packet(history)
    opt=extract_option()
    r=review_semantic_challenge(p,hypotheses(p),challenge(opt,disposition="CHALLENGE"),opt)
    assert r.status=="CHALLENGED"
    assert "INDEPENDENT_REVIEW_CHALLENGED_PROPOSAL" in r.blockers


def test_unknown_symbol_from_reviewer_is_not_accepted(history):
    p=packet(history)
    opt=extract_option()
    bad=(replace(hypotheses(p)[0],symbol_keys=("forged/file.py::function:fake",)),)
    r=review_semantic_challenge(p,bad,challenge(opt),opt)
    assert r.status=="CHALLENGED"
    assert "REVIEW_REFERENCES_UNKNOWN_SOURCE_SYMBOL" in r.blockers


def test_incomplete_first_pass_cannot_be_silently_accepted(history):
    p=packet(history)
    opt=extract_option()
    h=(replace(hypotheses(p)[0],symbol_keys=p.observed_symbol_keys[:1]),)
    r=review_semantic_challenge(p,h,challenge(opt),opt)
    assert r.status=="HOLD"
    assert "REVIEW_DID_NOT_ADDRESS_ALL_OBSERVED_DECLARATIONS" in r.unresolved


def test_missing_negative_boundary_is_challenged(history):
    p=packet(history)
    opt=extract_option()
    h=(replace(hypotheses(p)[0],negative_boundary=""),)
    r=review_semantic_challenge(p,h,challenge(opt),opt)
    assert r.status=="CHALLENGED"


def test_no_counterexample_for_mutation_is_hold(history):
    p=packet(history)
    opt=extract_option()
    r=review_semantic_challenge(p,hypotheses(p),challenge(opt,counterexamples=()),opt)
    assert r.status=="HOLD"
    assert "NO_SECOND_PASS_COUNTEREXAMPLE" in r.unresolved


def test_second_pass_for_different_candidate_is_rejected(history):
    p=packet(history)
    opt=extract_option()
    r=review_semantic_challenge(p,hypotheses(p),replace(challenge(opt),option_id="other"),opt)
    assert r.status=="CHALLENGED"
    assert "SECOND_PASS_FOR_DIFFERENT_OPTION" in r.blockers


def test_review_url_is_not_authentication(history):
    p=packet(history)
    opt=extract_option()
    r=review_semantic_challenge(p,hypotheses(p),replace(challenge(opt),review_reference="https://github.com/example/repo/pull/2#review-11"),opt)
    assert "REVIEWER_INDEPENDENCE_NOT_AUTHENTICATED" in r.unresolved


def test_missing_review_url_holds(history):
    p=packet(history)
    opt=extract_option()
    r=review_semantic_challenge(p,hypotheses(p),replace(challenge(opt),review_reference=""),opt)
    assert "MISSING_EXTERNAL_REVIEW_REFERENCE" in r.unresolved


def test_truncated_source_excerpt_is_disclosed(history):
    p=packet(history,max_symbol_chars=20)
    assert any(x.truncated for x in p.excerpts)
    assert any(x.startswith("BLINDED_EXCERPT_TRUNCATED") for x in p.unresolved)


def test_excerpt_limit_is_disclosed(history):
    p=packet(history,max_excerpts=1)
    assert len(p.excerpts)==1
    assert "BLINDED_EXCERPT_COUNT_LIMIT" in p.unresolved


def test_stale_worktree_does_not_change_packet(history):
    root,_,_=history
    first=packet(history)
    (root / PATH).write_text("# made after pinned commit\n")
    assert packet(history)==first


def test_packet_requires_git_source_provider(history):
    root,before,baseline=history
    with pytest.raises(TypeError,match="BLINDED_GIT_SOURCE_REQUIRED"):
        build_blinded_semantic_packet(case(before,baseline),object(),bindings())
