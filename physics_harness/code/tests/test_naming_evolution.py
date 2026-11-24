"""P0: exact-blob history and delegation evidence, without naming authority."""
from __future__ import annotations

from hashlib import sha1
from physics_harness.code.tests.conftest import git

import pytest

from physics_harness.code.refactor.evolution import (
    audit_source_evolution, compare_source_history, find_delegation_seams,
    observe_python_structure,
)

BEFORE = b'''from typing import Protocol
class Collector(Protocol):
    def supports(self, record): ...
    def collect(self, source, request): ...
def run_scan():
    from .providers.workflow import WorkflowCollector
    return WorkflowCollector()
'''
AFTER = b'''from typing import Protocol
class Collector(Protocol):
    def supports(self, record): ...
    def collect(self, source, request): ...
def run_scan():
    from .providers.workflow import WorkflowCollector
    from .providers.python_ast import PythonAstCollector
    from .providers.cpp import CppSourceCollector
    return WorkflowCollector(), PythonAstCollector(), CppSourceCollector()
'''

PROVIDERS = {
    "workflow": b"class WorkflowCollector:\n def supports(self,record): return True\n def collect(self,source,request): return ()\n",
    "python_ast": b"class PythonAstCollector:\n def supports(self,record): return True\n def collect(self,source,request): return ()\n",
    "cpp": b"class CppSourceCollector:\n def supports(self,record): return True\n def collect(self,source,request): return ()\n",
}
OWNER = "diagnostics/collector.py"
B = "1" * 40
A = "2" * 40


def blob(content: bytes) -> str:
    return sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def scan(path: str, content: bytes, revision: str):
    return observe_python_structure(path, content, blob(content), revision)


def providers(revision: str):
    return tuple(scan(f"diagnostics/providers/{name}.py", content, revision)
                 for name, content in PROVIDERS.items())


def initial():
    return scan(OWNER, BEFORE, B)


def current():
    return scan(OWNER, AFTER, A)


def test_ast_change_is_name_independent_and_declarations_remain():
    old, new = initial(), current()
    diff = compare_source_history(old, new)
    assert diff.identity_status == "DECLARATION_OVERLAP_CANDIDATE"
    assert diff.unchanged_definitions == ("class:Collector", "function:run_scan")
    assert "FUNCTION_BODIES_NOT_SEMANTICALLY_COMPARED" in diff.unknowns
    assert diff.added_definitions == diff.removed_definitions == ()
    assert (".providers.cpp", "CppSourceCollector", "CppSourceCollector") in diff.added_imports
    assert (".providers.python_ast", "PythonAstCollector", "PythonAstCollector") in diff.added_imports
    assert not diff.mutation_approved


def test_declared_code_has_exact_file_blob_line_refs():
    s = initial()
    assert s.classes[0].source_ref == f"{OWNER}:2@{blob(BEFORE)}"
    assert any(x.source_ref == f"{OWNER}:6@{blob(BEFORE)}" for x in s.imports)
    assert s.classes[0].is_protocol


def test_reject_wrong_source_bytes_or_wrong_revision():
    with pytest.raises(ValueError, match="EVOLUTION_BLOB_MISMATCH"):
        observe_python_structure(OWNER, AFTER, blob(BEFORE), A)
    with pytest.raises(ValueError, match="INVALID_SOURCE_IDENTITY"):
        observe_python_structure(OWNER, AFTER, blob(AFTER), "not-a-sha")


def test_reject_path_traversal_and_non_python_source():
    for path in ("../unsafe.py", "/absolute.py", "diagnostics/../unsafe.py", "diagnostics\\x.py"):
        with pytest.raises(ValueError, match="INVALID_EVOLUTION_PATH"):
            scan(path, BEFORE, B)
    with pytest.raises(ValueError, match="ONLY_PYTHON"):
        scan("diagnostics/collector.cpp", BEFORE, B)


def test_new_provider_imports_match_external_implementation_owners():
    seams = find_delegation_seams(current(), providers(A))
    assert {x.imported_implementation for x in seams} == {
        "WorkflowCollector", "PythonAstCollector", "CppSourceCollector"}
    assert all(x.protocol == "Collector" and x.matched_methods == ("collect", "supports")
               for x in seams)
    assert all(x.implementation_ref.endswith("@" + blob(PROVIDERS[x.implementation_path.split("/")[-1][:-3]]))
               for x in seams)


def test_same_class_name_in_wrong_module_is_not_an_owner_witness():
    wrong = scan("diagnostics/providers/other.py", PROVIDERS["cpp"], A)
    assert all(x.imported_implementation != "CppSourceCollector"
               for x in find_delegation_seams(current(), (wrong,)))


def test_methodless_import_does_not_fake_a_delegation_seam():
    wrong = scan("diagnostics/providers/cpp.py", b"class CppSourceCollector: pass\n", A)
    assert all(x.imported_implementation != "CppSourceCollector"
               for x in find_delegation_seams(current(), (wrong,)))


def test_cross_revision_sources_are_rejected():
    with pytest.raises(ValueError, match="CROSS_REVISION_DELEGATION"):
        find_delegation_seams(current(), providers(B))


def test_duplicate_source_path_fails_closed():
    items = providers(A)
    with pytest.raises(ValueError, match="DUPLICATE_IMPLEMENTATION_SOURCE"):
        find_delegation_seams(current(), (items[0], items[0]))


def test_unknown_import_semantics_are_not_silently_resolved():
    source = b"from .providers import *\nfrom importlib import import_module\nvalue = import_module('x')\n"
    obs = scan(OWNER, source, A)
    assert any("WILDCARD_IMPORT" in x for x in obs.unknowns)
    assert any("DYNAMIC_REFERENCE" in x for x in obs.unknowns)


def test_move_same_declarations_does_not_certify_identity():
    old = initial()
    moved = scan("diagnostics/new_collector.py", AFTER, A)
    diff = compare_source_history(old, moved)
    assert "MOVED_PATH_IDENTITY_NOT_VERIFIED" in diff.unknowns
    assert diff.identity_status == "DECLARATION_OVERLAP_CANDIDATE"
    out = audit_source_evolution(old, moved, providers(B), providers(A))
    assert out.disposition == "HOLD" and not out.mutation_approved


def test_no_continuous_declarations_cannot_claim_same_logical_owner():
    replaced = scan(OWNER, b"def completely_new(): return 1\n", A)
    diff = compare_source_history(initial(), replaced)
    assert diff.identity_status == "UNRESOLVED"
    assert "NO_DECLARATION_CONTINUITY_WITNESS" in diff.unknowns


def test_history_expansion_with_existing_seams_prefers_keep_review_not_refactor():
    old, new = initial(), current()
    r = audit_source_evolution(old, new, (providers(B)[0],), providers(A))
    assert r.disposition == "KEEP_CONSIDERATION"
    assert {x.imported_implementation for x in r.newly_observed_seams} == {
        "PythonAstCollector", "CppSourceCollector"}
    assert "INDEPENDENT_RESPONSIBILITY_DEFINITION" in r.required_checks
    assert not r.mutation_approved


def test_semantic_name_fitness_is_never_inferred_from_module_tokens():
    r = audit_source_evolution(initial(), current(), (), ())
    assert r.disposition != "KEEP_CONSIDERATION"
    assert not r.mutation_approved


def test_non_proven_inline_implementation_raises_extraction_review_only():
    old = scan(OWNER, b"from typing import Protocol\nclass Role(Protocol):\n def collect(self): ...\nclass Owner:\n def collect(self): return 1\n", B)
    new = scan(OWNER, b"from typing import Protocol\nclass Role(Protocol):\n def collect(self): ...\nclass Owner:\n def collect(self): return 2\n", A)
    r = audit_source_evolution(old, new, (), ())
    assert r.disposition == "EXTRACTION_REVIEW"
    assert "VERIFY_INLINE_IMPLEMENTATION_OWNERSHIP" in r.required_checks
    assert not r.mutation_approved


def test_source_history_requires_different_revisions():
    with pytest.raises(ValueError, match="EVOLUTION_REVISIONS_MUST_DIFFER"):
        compare_source_history(initial(), initial())


def test_real_local_git_tree_reader_never_uses_dirty_worktree(git_factory):
    from physics_harness.code.diagnostics.providers.git import GitSourceProvider
    root, before_sha = git_factory({
        OWNER: BEFORE, "diagnostics/providers/workflow.py": PROVIDERS["workflow"],
    })
    path = root / OWNER
    source_dir = root / "diagnostics/providers"
    path.write_bytes(AFTER)
    (source_dir / "python_ast.py").write_bytes(PROVIDERS["python_ast"])
    (source_dir / "cpp.py").write_bytes(PROVIDERS["cpp"])
    git(root, "add", OWNER, "diagnostics/providers/python_ast.py", "diagnostics/providers/cpp.py")
    git(root, "commit", "-qm", "after")
    after_sha = git(root, "rev-parse", "HEAD")
    provider = GitSourceProvider(root)
    before_file = provider.read_at_revision(before_sha, OWNER)
    after_file = provider.read_at_revision(after_sha, OWNER)
    assert before_file.content == BEFORE and after_file.content == AFTER
    assert before_file.record.blob_sha == blob(BEFORE)
    assert after_file.record.blob_sha == blob(AFTER)
    path.write_text("def tampered(): pass\n", encoding="utf-8")
    assert provider.read_at_revision(before_sha, OWNER).content == BEFORE
    assert provider.read_at_revision(after_sha, OWNER).content == AFTER
    r = compare_source_history(
        observe_python_structure(OWNER, before_file.content, before_file.record.blob_sha, before_sha),
        observe_python_structure(OWNER, after_file.content, after_file.record.blob_sha, after_sha))
    assert r.unchanged_definitions == ("class:Collector", "function:run_scan")
    from physics_harness.code.refactor.evolution import audit_git_history
    report = audit_git_history(
        provider, before_sha, after_sha, OWNER,
        previous_owner_paths=("diagnostics/providers/workflow.py",),
        current_owner_paths=("diagnostics/providers/workflow.py",
                             "diagnostics/providers/python_ast.py",
                             "diagnostics/providers/cpp.py"))
    assert report.disposition == "KEEP_CONSIDERATION"
    assert {s.imported_implementation for s in report.newly_observed_seams} == {
        "PythonAstCollector", "CppSourceCollector"}
    assert not report.mutation_approved
    with pytest.raises(ValueError, match="HISTORY_REVISIONS_NOT_ANCESTRAL"):
        audit_git_history(provider, after_sha, before_sha, OWNER)
    with pytest.raises(ValueError, match="HISTORY_SOURCE_UNRESOLVED"):
        provider.read_at_revision(after_sha, "diagnostics/untracked.py")
    with pytest.raises(ValueError, match="INVALID_HISTORY_REVISION"):
        provider.read_at_revision("HEAD", OWNER)
    with pytest.raises(ValueError, match="INVALID_HISTORY_PATH"):
        provider.read_at_revision(after_sha, "../secret.py")
    with pytest.raises(ValueError, match="HISTORY_COMMIT_UNAVAILABLE"):
        audit_git_history(provider, "f" * 40, after_sha, OWNER)
    link = root / "diagnostics/redirect.py"
    link.symlink_to("collector.py")
    git(root, "add", "diagnostics/redirect.py")
    git(root, "commit", "-qm", "symlink")
    new_head = git(root, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="HISTORY_SOURCE_INVALID"):
        provider.read_at_revision(new_head, "diagnostics/redirect.py")


def test_arbitrary_class_method_is_not_an_extraction_seam():
    before = scan(OWNER, b"class Owner:\n def collect(self): return 1\n", B)
    after = scan(OWNER, b"class Owner:\n def collect(self): return 2\n", A)
    result = audit_source_evolution(before, after, (), ())
    assert result.disposition == "HOLD"
    assert not result.mutation_approved
