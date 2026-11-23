"""P0: exact Git source imports and non-Python/dynamic consumers affect rename safety."""
from __future__ import annotations

import pytest

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.tests.test_naming_boundary import (
    history, case, extract_option, bindings, PATH, DEST, git,
)
from physics_harness.code.tests.test_naming_candidate import third_commit, placements
from physics_harness.code.verification.naming_consumers import (
    audit_naming_consumers, _resolve_from, _module_for,
)
import ast


def audit(history, *, candidate=None, max_files=3000, max_bytes=20_000_000):
    root,before,baseline=history
    if candidate is None:
        candidate=third_commit(history)
    return audit_naming_consumers(case(before,baseline),extract_option(),
        GitSourceProvider(root),candidate,placements(),max_files=max_files,max_bytes=max_bytes)


def append_candidate(history, path, content, *, move=False):
    root,_,_=history
    third_commit(history)
    if move:
        git(root,"mv",PATH,"diagnostics/source_collector.py")
    p=root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    git(root,"add",".")
    git(root,"commit","-q","-m","consumer reference")
    return git(root,"rev-parse","HEAD")


def test_no_internal_reference_does_not_prove_external_closure(history):
    r=audit(history)
    assert r.status=="INTERNAL_SCAN_WITH_EXTERNAL_GAPS"
    assert "EXTERNAL_CONSUMERS_NOT_SCANNED" in r.unresolved
    assert "VERIFY_EXTERNAL_DEPENDENTS_AND_PUBLIC_IMPORT_CONTRACTS" in r.required_checks
    assert not r.external_consumers_verified and not r.mutation_approved


def test_stale_import_to_old_module_kept_for_review(history):
    candidate=append_candidate(history,"consumer.py",
        "from diagnostics.collector import python_decode\n")
    r=audit(history,candidate=candidate)
    assert r.status=="HOLD"
    assert any(v.category=="STATIC_IMPORT" and v.path=="consumer.py" for v in r.after_references)
    assert any(x.startswith("RETAINED_OLD_MODULE_IMPORT") for x in r.unresolved)


def test_broken_static_import_when_module_removed_blocks(history):
    candidate=append_candidate(history,"consumer.py",
        "from diagnostics.collector import python_decode\n",move=True)
    r=audit(history,candidate=candidate)
    assert r.status=="BLOCKED"
    assert "STALE_IMPORT_TO_REMOVED_MODULE:diagnostics.collector" in r.blockers


def test_relative_static_import_checked_against_removed_module(history):
    candidate=append_candidate(history,"diagnostics/consumer.py",
        "from .collector import python_decode\n",move=True)
    r=audit(history,candidate=candidate)
    assert r.status=="BLOCKED"


def test_import_module_string_not_mistaken_for_static_clearance(history):
    candidate=append_candidate(history,"consumer.py",
        "import importlib\nvalue=importlib.import_module('diagnostics.collector')\n")
    r=audit(history,candidate=candidate)
    assert r.status=="HOLD"
    assert "DYNAMIC_CONSUMERS_PRESENT" in r.unresolved
    assert any(v.category=="DYNAMIC_CANDIDATE" for v in r.after_references)


def test_documentation_literal_reference_requires_review(history):
    candidate=append_candidate(history,"README.md",
        "The module diagnostics/collector.py is the public consumer.\n")
    r=audit(history,candidate=candidate)
    assert r.status=="HOLD"
    assert "LITERAL_REFERENCE_REQUIRES_REVIEW:diagnostics.collector" in r.unresolved


def test_worktree_change_is_ignored(history):
    root,_,_=history
    candidate=third_commit(history)
    result=audit(history,candidate=candidate)
    (root / "README.md").write_text("diagnostics/collector.py\n")
    assert audit(history,candidate=candidate)==result


def test_bounded_file_scan_cannot_claim_completeness(history):
    r=audit(history,max_files=1)
    assert r.status=="HOLD"
    assert "REPOSITORY_CONSUMER_FILE_BUDGET_EXCEEDED" in r.unresolved


def test_bounded_bytes_cannot_claim_completeness(history):
    r=audit(history,max_bytes=10)
    assert r.status=="HOLD"
    assert "REPOSITORY_CONSUMER_BYTE_BUDGET_EXCEEDED" in r.unresolved


def test_rejects_candidate_same_as_baseline(history):
    root,_,baseline=history
    r=audit(history,candidate=baseline)
    assert r.status=="BLOCKED"
    assert "CONSUMER_CANDIDATE_MUST_BE_NEW_COMMIT" in r.blockers


def test_rejects_unrelated_ancestor_candidate(history):
    root,before,baseline=history
    r=audit(history,candidate=before)
    assert r.status=="BLOCKED"
    assert "CONSUMER_CANDIDATE_NOT_DESCENDANT" in r.blockers


def test_relative_resolution():
    node=ast.parse("from .collector import A\nfrom ..providers import B\n").body
    assert _resolve_from("diagnostics/module.py",node[0])=="diagnostics.collector"
    assert _resolve_from("pkg/diagnostics/module.py",node[1])=="pkg.providers"
    assert _module_for("pkg/__init__.py")=="pkg"


def test_no_runtime_execution_for_dynamic_import(history):
    candidate=append_candidate(history,"consumer.py",
        "raise RuntimeError('Never execute during source scanning')\n")
    r=audit(history,candidate=candidate)
    assert "EXTERNAL_CONSUMERS_NOT_SCANNED" in r.unresolved


def test_budget_rejects_bool_and_zero(history):
    root,_,baseline=history
    with pytest.raises(ValueError,match="INVALID_CONSUMER_BUDGET"):
        audit_naming_consumers(case(history[1],baseline),extract_option(),
            GitSourceProvider(root),baseline,placements(),max_files=True)
