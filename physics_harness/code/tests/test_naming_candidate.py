"""P0: exact Git candidate placement checks do not certify semantic equivalence."""
from __future__ import annotations
from dataclasses import replace
from hashlib import sha1

import pytest

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.refactor.naming import NamingEvidence, NamingOption
from physics_harness.code.verification.naming_candidate import CandidatePlacement, verify_naming_candidate
from physics_harness.code.tests.test_naming_boundary import (
    history, case, bindings, extract_option, PATH, DEST, NEW, git, digest,
)


def placement(rid, symbol, *, owner="original", to_path=PATH):
    return CandidatePlacement(rid, PATH+"::"+symbol, to_path+"::"+symbol, owner)


def placements():
    return (placement("coord", "class:Collector"),
            placement("cpp", "function:cpp_decode"),
            placement("python", "function:python_decode", owner="python-provider", to_path=DEST))


def third_commit(history, *, dest_source="class PythonProvider:\n    def supports(self, value): return True\n\ndef python_decode(source):\n    return source\n", source=True):
    root, before, baseline = history
    if source:
        (root / PATH).write_text("class Collector:\n    def collect(self, source): return source\n\ndef cpp_decode(source):\n    return source\n")
    (root / DEST).write_text(dest_source)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "candidate extraction")
    return git(root, "rev-parse", "HEAD")


def audit(history, candidate=None, *, subject=None, opt=None, mapped=None):
    root, before, baseline = history
    if candidate is None:
        candidate=third_commit(history)
    return verify_naming_candidate(subject or case(before, baseline),
          opt or extract_option(), GitSourceProvider(root), bindings(),
          candidate, PATH, mapped or placements())


def test_extraction_candidate_structural_move_is_witnessed(history):
    r=audit(history)
    assert r.status == "STRUCTURAL_DELTA_VERIFIED"
    assert len(r.validated_placements)==3
    assert not r.semantic_compatibility_proven and not r.mutation_approved
    assert "VERIFY_BEFORE_AFTER_BEHAVIORAL_COMPATIBILITY" in r.required_checks


def test_extract_symbol_still_in_source_holds(history):
    r=audit(history,candidate=third_commit(history,source=False))
    assert r.status=="HOLD"
    assert any("EXTRACTED_SOURCE_SYMBOL_STILL_DECLARED" in x for x in r.unresolved)


def test_candidate_function_signature_changed_holds(history):
    content="class PythonProvider:\n    def supports(self, value): return True\n\ndef python_decode(source, extra):\n    return source\n"
    r=audit(history,candidate=third_commit(history,dest_source=content))
    assert r.status=="HOLD"
    assert any("DECLARATION_SIGNATURE_CHANGED" in x for x in r.unresolved)


def test_candidate_missing_extracted_declaration_is_rejected(history):
    content="class PythonProvider:\n    def supports(self, value): return True\n"
    r=audit(history,candidate=third_commit(history,dest_source=content))
    assert r.status=="REJECTED"
    assert any("CANDIDATE_SYMBOL_NOT_DECLARED" in x for x in r.blockers)


def test_candidate_missing_allocation_holds(history):
    r=audit(history,mapped=placements()[:-1])
    assert r.status=="HOLD"
    assert "CANDIDATE_DROPPED_RESPONSIBILITY_SYMBOL" in r.unresolved


def test_candidate_invented_owner_fails(history):
    bad=placements()[:-1]+(replace(placements()[-1],owner_id="nonexistent-owner"),)
    r=audit(history,mapped=bad)
    assert r.status=="REJECTED"
    assert any("UNKNOWN_OWNER" in x for x in r.blockers)


def test_candidate_existing_owner_placement_wrong_path_rejected(history):
    bad=placements()[:-1]+(replace(placements()[-1],after_symbol=PATH+"::function:python_decode"),)
    r=audit(history,mapped=bad)
    assert r.status=="REJECTED"
    assert any("PLACEMENT_ON_WRONG_OWNER_PATH" in x for x in r.blockers)


def test_candidate_not_a_descendant_is_rejected(history):
    root,before,after=history
    # Before is an ancestor, but cannot be a descendant of current baseline.
    r=audit(history,candidate=before)
    assert r.status=="REJECTED"
    assert "CANDIDATE_NOT_DESCENDANT_OF_BASELINE" in r.blockers


def test_candidate_same_commit_rejected(history):
    root,before,after=history
    r=audit(history,candidate=after)
    assert r.status=="REJECTED"
    assert "CANDIDATE_MUST_BE_DISTINCT_COMMIT" in r.blockers


def test_candidate_worktree_tampering_does_not_change_result(history):
    root,before,after=history
    candidate=third_commit(history)
    (root / DEST).write_text("# malicious worktree\n")
    (root / PATH).write_text("# malicious worktree\n")
    r=audit(history,candidate=candidate)
    assert r.status=="STRUCTURAL_DELTA_VERIFIED"


def test_keep_candidate_is_not_an_edit(history):
    from physics_harness.code.tests.test_naming_boundary import keep
    root,before,after=history
    candidate=third_commit(history)
    r=audit(history,candidate=candidate,opt=keep())
    assert r.status=="REJECTED"
    assert "NO_EDIT_CANDIDATE_FOR_KEEP_OR_HOLD" in r.blockers


def test_candidate_rename_file_requires_renamed_file_and_maintained_declarations(history):
    root,before,baseline=history
    # Revised name is a hypothesis with independent baseline mismatch evidence.
    c=case(before,baseline)
    mismatch=NamingEvidence("name_mismatch", "NAME_MISMATCH", "Existing name too narrow",
              (f"{PATH}:4@{digest(NEW)}",),baseline)
    c=replace(c,name_fit="NARROW", name_mismatch_evidence_ids=("name_mismatch",),
              evidence=c.evidence+(mismatch,))
    opt=NamingOption("rename", "RENAME", "Widen to stable source_collector",
             proposed_name="source_collector",module_path_policy="RETIRE_OLD_PATH",retained_responsibility_ids=c.responsibility_ids,
             evidence_ids=("name_mismatch","evolution","boundary","context"),
             coverage_rationale="Collector handles diverse sources",
             boundary_rationale="Does not plan/verify code changes",
             context_rationale="Stable diagnostics domain",impact_paths=(PATH,))
    renamed="diagnostics/source_collector.py"
    git(root,"mv",PATH,renamed)
    git(root,"commit","-q","-m","rename candidate")
    after=git(root,"rev-parse","HEAD")
    moves=tuple(CandidatePlacement(b.responsibility_id,old,old.replace(PATH+"::",renamed+"::"),"original")
                for b in bindings() for old in b.source_symbols)
    r=verify_naming_candidate(c,opt,GitSourceProvider(root),bindings(),after,renamed,moves)
    assert r.status=="STRUCTURAL_DELTA_VERIFIED"
    assert len(r.validated_placements)==3
    assert not r.mutation_approved


def test_candidate_rename_cannot_keep_same_path(history):
    root,before,baseline=history
    c=case(before,baseline)
    mismatch=NamingEvidence("name_mismatch","NAME_MISMATCH","too narrow",
                           (f"{PATH}:4@{digest(NEW)}",),baseline)
    c=replace(c,name_fit="NARROW",name_mismatch_evidence_ids=("name_mismatch",),
              evidence=c.evidence+(mismatch,))
    opt=NamingOption("rename","RENAME","rename",proposed_name="source_collector",module_path_policy="RETIRE_OLD_PATH",
          retained_responsibility_ids=c.responsibility_ids,
          evidence_ids=("name_mismatch","evolution","boundary","context"),
          coverage_rationale="cover",boundary_rationale="not broad",context_rationale="diagnostics",
          impact_paths=(PATH,))
    candidate=third_commit(history)
    r=verify_naming_candidate(c,opt,GitSourceProvider(root),bindings(),candidate,PATH,placements())
    assert r.status=="REJECTED"
    assert "CANDIDATE_PATH_DOES_NOT_IMPLEMENT_RENAME" in r.blockers


def test_candidate_api_return_annotation_change_holds(history):
    dest="class PythonProvider:\n    def supports(self, value): return True\n\ndef python_decode(source) -> int:\n    return 42\n"
    r=audit(history,candidate=third_commit(history,dest_source=dest))
    assert r.status=="HOLD"
    assert any("DECLARATION_SIGNATURE_CHANGED" in s for s in r.unresolved)
