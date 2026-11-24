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


@pytest.mark.parametrize("policy,keep_old,expected_blocker", [
    ("PRESERVE_COMPATIBILITY", True, None),
    ("PRESERVE_COMPATIBILITY", False, "REQUIRED_COMPATIBILITY_PATH_MISSING_OR_NONREGULAR:pkg/old.py"),
    ("RETIRE_OLD_PATH", True, "RETIRED_MODULE_PATH_STILL_PRESENT:pkg/old.py"),
    ("RETIRE_OLD_PATH", False, None),
])
def test_explicit_module_path_policy(git_factory, policy, keep_old, expected_blocker):
    from physics_harness.code.verification.naming_consumers import verify_module_path_transition
    root, base = git_factory({"pkg/old.py": "from .new import value\n",
                              "pkg/new.py": "value = 1\n"})
    if not keep_old:
        (root / "pkg/old.py").unlink()
    (root / "client.py").write_text("from pkg.new import value\n")
    git(root, "add", "."); git(root, "commit", "-qm", "candidate")
    after = git(root, "rev-parse", "HEAD")
    result = verify_module_path_transition(GitSourceProvider(root), base, after,
                                           "pkg/old.py", "pkg/new.py", policy)
    assert result.old_path_present is keep_old
    assert result.new_path_present is True
    assert result.path_policy_witnessed is (expected_blocker is None)
    assert result.status == ("BLOCKED" if expected_blocker else "HOLD")
    if expected_blocker:
        assert expected_blocker in result.blockers
    assert "EXTERNAL_CONSUMERS_NOT_SCANNED" in result.unresolved
    assert not result.mutation_approved


@pytest.mark.parametrize("stale,remnant", [(True, False), (False, True), (False, False)])
def test_package_retirement_checks_import_and_entire_directory(git_factory, stale, remnant):
    from physics_harness.code.verification.naming_consumers import verify_module_path_transition
    root, base = git_factory({"pkg/old/__init__.py": "from pkg.new import value\n",
                              "pkg/old/extra.py": "pass\n", "pkg/new/__init__.py": "value = 1\n"})
    (root / "pkg/old/__init__.py").unlink()
    if not remnant:
        (root / "pkg/old/extra.py").unlink()
    (root / "client.py").write_text("from pkg.old import value\n" if stale else "from pkg.new import value\n")
    git(root, "add", "."); git(root, "commit", "-qm", "candidate")
    result = verify_module_path_transition(GitSourceProvider(root), base, git(root, "rev-parse", "HEAD"),
                                           "pkg/old/__init__.py", "pkg/new/__init__.py", "RETIRE_OLD_PATH")
    assert result.old_path_present is remnant
    assert ("STALE_IMPORT_TO_RETIRED_MODULE:pkg.old" in result.blockers) is stale
    assert ("RETIRED_MODULE_PATH_STILL_PRESENT:pkg/old/__init__.py" in result.blockers) is remnant
    assert result.status == ("BLOCKED" if stale or remnant else "HOLD")


def test_retirement_does_not_confuse_symlink_or_missing_commit_with_absence(git_factory):
    from physics_harness.code.verification.naming_consumers import verify_module_path_transition
    root, base = git_factory({"pkg/old.py": "pass\n", "pkg/new.py": "pass\n"})
    (root / "pkg/old.py").unlink()
    (root / "pkg/old.py").symlink_to("new.py")
    git(root, "add", "."); git(root, "commit", "-qm", "candidate")
    provider = GitSourceProvider(root)
    result = verify_module_path_transition(provider, base, git(root, "rev-parse", "HEAD"),
                                           "pkg/old.py", "pkg/new.py", "RETIRE_OLD_PATH")
    assert result.old_path_present is True and result.status == "BLOCKED"
    missing = verify_module_path_transition(provider, base, "0"*40,
                                            "pkg/old.py", "pkg/new.py", "RETIRE_OLD_PATH")
    assert missing.old_path_present is None and not missing.path_policy_witnessed
    assert missing.status == "HOLD"
