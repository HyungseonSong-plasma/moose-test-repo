"""P0 — GPT naming selection must not self-authenticate history or approve edits."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha1
from pathlib import Path
import subprocess

import pytest

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.refactor.naming import (
    NamingCase, NamingEvidence, NamingOption, NamingRecommendation, ExtractionUnit,
    RejectedNamingCandidate, adjudicate_naming_recommendation,
    build_naming_recommendation_brief,
)
from physics_harness.code.verification.naming_provenance import (
    verify_naming_evidence_sources,
)

PATH = "diagnostics/python_collector.py"
OLD = b"class PythonCollector:\n    def collect(self, source): return source\n"
NEW = b"class PythonCollector:\n    def collect(self, source): return source\n    def collect_cpp(self, source): return source\n"


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def digest(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.test")
    file = root / PATH
    file.parent.mkdir()
    file.write_bytes(OLD)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "python only")
    before = git(root, "rev-parse", "HEAD")
    file.write_bytes(NEW)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "cpp added")
    after = git(root, "rev-parse", "HEAD")
    return root, before, after


def ev(id: str, kind: str, revision: str, content: bytes, line: int) -> NamingEvidence:
    return NamingEvidence(id, kind, id.replace("_", " "),
                          (f"{PATH}:{line}@{digest(content)}",), revision)


def case(before: str, after: str, *, name_fit="NARROW", unknowns=()) -> NamingCase:
    evidence = (
        ev("collect", "RESPONSIBILITY", after, NEW, 2),
        ev("cpp", "RESPONSIBILITY", after, NEW, 3),
        ev("narrow", "NAME_MISMATCH", after, NEW, 3),
        ev("boundary", "BOUNDARY", after, NEW, 1),
        ev("context", "CONTEXT", after, NEW, 1),
        ev("evolution", "EVOLUTION", before, OLD, 2),
    )
    return NamingCase("example/repo", after, "FILE", "collector-role",
                      "python_collector", PATH, ("collect", "cpp"), evidence,
                      "RESOLVED", "COHERENT", name_fit,
                      ("narrow",) if name_fit == "NARROW" else (), (), unknowns)


def options():
    return (
        NamingOption("keep", "KEEP", "Keep existing owner and name"),
        NamingOption("rename", "RENAME", "Name covers both observed source kinds",
                     proposed_name="source_collector", module_path_policy="RETIRE_OLD_PATH",
                     coverage_rationale="Existing collector responsibilities are preserved",
                     boundary_rationale="Does not plan or mutate sources",
                     context_rationale="diagnostics is the namespace",
                     retained_responsibility_ids=("collect", "cpp"),
                     evidence_ids=("collect", "cpp", "narrow", "boundary", "context", "evolution"),
                     impact_paths=(PATH,)),
    )


def suggestion(*, selected="rename", rejected=None, keep_evidence=("narrow",), why="Python-specific name omits observed C++ collection", unresolved=()):
    if rejected is None:
        rejected = (RejectedNamingCandidate("keep", "Narrow language name", ("narrow",)),)
    return NamingRecommendation(selected, why, keep_evidence, rejected,
                                "Stable responsibility name preferred", unresolved)


def test_actual_git_provenance_and_revision_ancestry(repository):
    root, before, after = repository
    receipt = verify_naming_evidence_sources(case(before, after), GitSourceProvider(root))
    assert receipt.status == "SOURCE_ANCHORS_VERIFIED"
    assert len(receipt.verified_refs) == 4  # many claims share the same source line
    assert receipt.failures == receipt.unresolved == ()
    assert not receipt.semantic_compatibility_proven
    assert not receipt.mutation_approved


def test_worktree_modified_after_commit_does_not_change_verification(repository):
    root, before, after = repository
    (root / PATH).write_text("# uncommitted tampered worktree\n", encoding="utf-8")
    assert verify_naming_evidence_sources(case(before, after), GitSourceProvider(root)).status == "SOURCE_ANCHORS_VERIFIED"


def test_wrong_blob_fails_closed(repository):
    root, before, after = repository
    c = case(before, after)
    bad = replace(c.evidence[0], source_refs=(f"{PATH}:2@{'0'*40}",))
    c = replace(c, evidence=(bad,) + c.evidence[1:])
    r = verify_naming_evidence_sources(c, GitSourceProvider(root))
    assert r.status == "FAILED"
    assert any("SOURCE_BLOB_CONTRADICTION" in x for x in r.failures)


def test_unavailable_history_is_hold_not_pass(repository):
    root, before, after = repository
    c = case(before, after)
    earlier = replace(c.evidence[-1], source_revision="0"*40)
    c = replace(c, evidence=c.evidence[:-1] + (earlier,))
    receipt = verify_naming_evidence_sources(c, GitSourceProvider(root))
    assert receipt.status == "HOLD"
    assert any("ANCESTRAL" in x for x in receipt.unresolved)


def test_out_of_range_line_fails_closed(repository):
    root, before, after = repository
    c = case(before, after)
    bad = replace(c.evidence[0], source_refs=(f"{PATH}:999@{digest(NEW)}",))
    r = verify_naming_evidence_sources(replace(c, evidence=(bad,) + c.evidence[1:]), GitSourceProvider(root))
    assert r.status == "FAILED"
    assert any("SOURCE_LINE_NOT_AN_OBSERVATION" in x for x in r.failures)


def test_bounded_provenance_budget_is_hold(repository):
    root, before, after = repository
    r = verify_naming_evidence_sources(case(before, after), GitSourceProvider(root), max_refs=1)
    assert r.status == "HOLD"
    assert r.unresolved == ("NAMING_SOURCE_REF_BUDGET_EXCEEDED",)


def test_brief_for_gpt_is_version_bound_and_has_keep(repository):
    root, before, after = repository
    brief = build_naming_recommendation_brief(case(before, after), options())
    assert brief["revision"] == after
    assert {o["id"] for o in brief["options"]} == {"keep", "rename"}
    assert any("speculative future" in rule.lower() for rule in brief["rules"])
    assert "keep_counterevidence_ids" in brief["output_contract"]


def test_keep_baseline_required(repository):
    root, before, after = repository
    with pytest.raises(ValueError, match="EXACTLY_ONE_KEEP_BASELINE"):
        build_naming_recommendation_brief(case(before, after), options()[1:])


def test_candidate_comparison_can_only_recommend_for_verification(repository):
    root, before, after = repository
    r = adjudicate_naming_recommendation(case(before, after), options(), suggestion(), GitSourceProvider(root))
    assert r.disposition == "RECOMMEND_FOR_VERIFICATION"
    assert r.recommended_option_id == "rename"
    assert "VERIFY_ALL_REFERENCES_AND_CONSUMERS" in r.required_checks
    assert "INDEPENDENT_SEMANTIC_NAME_AND_BOUNDARY_REVIEW" in r.required_checks
    assert not r.mutation_approved


def test_naming_choice_lacking_keep_refutation_holds(repository):
    root, before, after = repository
    r = adjudicate_naming_recommendation(case(before, after), options(),
        suggestion(why="", keep_evidence=()), GitSourceProvider(root))
    assert r.disposition == "HOLD"
    assert "WHY_NOT_KEEP_MISSING" in r.unresolved


def test_not_comparing_keep_holds(repository):
    root, before, after = repository
    r = adjudicate_naming_recommendation(case(before, after), options(),
        suggestion(rejected=()), GitSourceProvider(root))
    assert r.disposition == "HOLD"
    assert "COMPETING_OPTIONS_NOT_ALL_COMPARED" in r.unresolved


def test_fabricated_rejection_evidence_is_blocker(repository):
    root, before, after = repository
    fake = (RejectedNamingCandidate("keep", "I made this up", ("not_in_case",)),)
    r = adjudicate_naming_recommendation(case(before, after), options(),
        suggestion(rejected=fake), GitSourceProvider(root))
    assert r.disposition == "HOLD"
    assert "REJECTION_WITH_UNKNOWN_EVIDENCE" in r.blockers


def test_valid_general_name_is_keep_not_rename(repository):
    root, before, after = repository
    c = replace(case(before, after, name_fit="VALID"), current_name="source_collector")
    keep = NamingRecommendation("keep", "", (),
        (RejectedNamingCandidate("rename", "Valid general name already covers role", ("collect",)),),
        "Default keep stable responsibility name")
    r = adjudicate_naming_recommendation(c, options(), keep, GitSourceProvider(root))
    assert r.disposition == "KEEP" and r.recommended_option_id == "keep"
    assert not r.mutation_approved


def test_valid_name_cannot_be_renamed_even_if_gpt_prefers_it(repository):
    root, before, after = repository
    c = replace(case(before, after, name_fit="VALID"), current_name="source_collector")
    r = adjudicate_naming_recommendation(c, options(), suggestion(), GitSourceProvider(root))
    assert r.disposition == "HOLD"
    assert "STABLE_VALID_NAME_MUST_BE_KEPT" in r.blockers


def test_uncertainty_in_case_or_gpt_holds(repository):
    root, before, after = repository
    c = case(before, after, unknowns=("DYNAMIC_CONSUMERS_NOT_RESOLVED",))
    r = adjudicate_naming_recommendation(c, options(), suggestion(), GitSourceProvider(root))
    assert r.disposition == "HOLD"
    assert "DYNAMIC_CONSUMERS_NOT_RESOLVED" in r.unresolved
    r2 = adjudicate_naming_recommendation(case(before, after), options(),
          suggestion(unresolved=("Naming ambiguous",)), GitSourceProvider(root))
    assert "GPT_DISCLOSED_UNRESOLVED_QUESTIONS" in r2.unresolved


def test_stale_responsibility_source_cannot_authorize_recommendation(repository):
    root, before, after = repository
    c = case(before, after)
    bad = replace(c.evidence[0], source_refs=(f"{PATH}:2@{digest(OLD)}",), source_revision=before)
    c = replace(c, evidence=(bad,) + c.evidence[1:])
    r = adjudicate_naming_recommendation(c, options(), suggestion(), GitSourceProvider(root))
    assert "CURRENT_RESPONSIBILITY_WITNESS_MISSING" in r.unresolved


def test_no_historical_change_witness_holds(repository):
    root, before, after = repository
    c = case(before, after)
    nohistory = replace(c.evidence[-1], source_refs=(f"{PATH}:2@{digest(NEW)}",), source_revision=after)
    c = replace(c, evidence=c.evidence[:-1] + (nohistory,))
    r = adjudicate_naming_recommendation(c, options(), suggestion(), GitSourceProvider(root))
    assert "HISTORICAL_EVOLUTION_WITNESS_MISSING" in r.unresolved


def test_no_citation_can_claim_semantic_equivalence(repository):
    root, before, after = repository
    r = adjudicate_naming_recommendation(case(before, after), options(), suggestion(), GitSourceProvider(root))
    assert not r.mutation_approved
    assert r.provenance == "SOURCE_ANCHORS_VERIFIED"
    assert "VERIFY_SEMANTIC_COMPATIBILITY" in r.required_checks


def test_extract_keep_can_win_when_name_still_valid_but_ownership_is_mixed(repository):
    root, before, after = repository
    c = replace(case(before, after, name_fit="VALID"), current_name="collector",
                coherence="MIXED")
    seam = ev("seam", "EXTRACTION_SEAM", after, NEW, 3)
    c = replace(c, evidence=c.evidence + (seam,))
    extracted = ExtractionUnit("cpp-owner", "cpp", ("cpp",), ("seam",),
                               "diagnostics/providers/cpp.py", destination_existing=True)
    common = dict(retained_responsibility_ids=("collect",), extracted_units=(extracted,),
                  post_extraction_name_fit="VALID",
                  evidence_ids=("collect", "cpp", "boundary", "context", "seam", "evolution"),
                  coverage_rationale="Split observed C++ implementation",
                  boundary_rationale="Collector owns orchestration, not the language implementation",
                  context_rationale="Existing diagnostics/providers owner",
                  impact_paths=(PATH,))
    extract_keep = NamingOption("extract_keep", "EXTRACT_KEEP", "Delegate implementation",
                                **common)
    extract_rename = NamingOption("extract_rename", "EXTRACT_RENAME", "Delegate and rename",
                                  proposed_name="source_collector", module_path_policy="RETIRE_OLD_PATH", **common)
    proposed = (options()[0], options()[1], extract_keep, extract_rename)
    counterarguments = (
        RejectedNamingCandidate("keep", "Mixed implementation should be separated", ("seam",)),
        RejectedNamingCandidate("rename", "Rename cannot resolve mixing", ("seam",)),
        RejectedNamingCandidate("extract_rename", "Original generic name remains valid", ("collect",)),
    )
    chosen = NamingRecommendation("extract_keep", "Separable C++ implementation remains inline",
                                  ("seam",), counterarguments,
                                  "Extract implementation but preserve generic collector name")
    result = adjudicate_naming_recommendation(c, proposed, chosen, GitSourceProvider(root))
    assert result.disposition == "RECOMMEND_FOR_VERIFICATION", result
    assert result.recommended_option_id == "extract_keep"
    assert "VERIFY_EXTRACTION_SEAM_BEHAVIOR" in result.required_checks
    assert not result.mutation_approved


def test_extract_keep_without_structural_keep_refutation_holds(repository):
    root, before, after = repository
    c = replace(case(before, after, name_fit="VALID"), current_name="collector",
                coherence="MIXED")
    seam = ev("seam", "EXTRACTION_SEAM", after, NEW, 3)
    c = replace(c, evidence=c.evidence + (seam,))
    extracted = ExtractionUnit("cpp-owner", "cpp", ("cpp",), ("seam",),
                               "diagnostics/providers/cpp.py", destination_existing=True)
    plan = NamingOption("extract_keep", "EXTRACT_KEEP", "Delegate implementation",
        retained_responsibility_ids=("collect",), extracted_units=(extracted,),
        post_extraction_name_fit="VALID",
        evidence_ids=("collect", "cpp", "boundary", "context", "seam", "evolution"),
        coverage_rationale="Split implementation", boundary_rationale="Keep scope",
        context_rationale="Use existing owner", impact_paths=(PATH,))
    proposal = NamingRecommendation("extract_keep", "Extract implementation", ("collect",),
        (RejectedNamingCandidate("keep", "Inline code should move", ("seam",)),), "Plan")
    result = adjudicate_naming_recommendation(c, (options()[0], plan), proposal,
                                            GitSourceProvider(root))
    assert "KEEP_NOT_REFUTED_BY_EXTRACTION_SEAM" in result.unresolved
    assert result.disposition == "HOLD"
