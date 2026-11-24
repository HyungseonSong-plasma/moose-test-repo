"""P0: independent immutable source structural boundary checks, not semantic proof."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha1
from pathlib import Path
import subprocess

import pytest

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.refactor.naming import (
    NamingCase, NamingEvidence, NamingOption, ExtractionUnit,
)
from physics_harness.code.verification.naming_boundary import (
    ResponsibilityBinding, verify_naming_boundary,
)

PATH = "diagnostics/collector.py"
DEST = "diagnostics/providers/python.py"
OLD = b"class Collector:\n    def collect(self, source): return source\n"
NEW = b"class Collector:\n    def collect(self, source): return source\n\ndef python_decode(source):\n    return source\n\ndef cpp_decode(source):\n    return source\n"
EXISTING = b"class PythonProvider:\n    def supports(self, value): return True\n"


def git(root, *args):
    return subprocess.check_output(("git", "-C", str(root), *args), text=True).strip()


def digest(content):
    return sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


@pytest.fixture
def history(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.test")
    f = root / PATH
    f.parent.mkdir(parents=True)
    f.write_bytes(OLD)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "before")
    before = git(root, "rev-parse", "HEAD")
    f.write_bytes(NEW)
    existing = root / DEST
    existing.parent.mkdir(parents=True)
    existing.write_bytes(EXISTING)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "after")
    after = git(root, "rev-parse", "HEAD")
    return root, before, after


def evidence(rid, kind, revision, *, line=1, old=False, path=PATH):
    blob = digest(OLD if old else NEW) if path == PATH else digest(EXISTING)
    return NamingEvidence(rid, kind, rid, (f"{path}:{line}@{blob}",), revision)


def case(before, after, *, target_kind="FILE", target_name="collector", target_path=PATH,
         coherent="COHERENT", name_fit="VALID"):
    ev = (
      evidence("coord", "RESPONSIBILITY", after, line=1),
      evidence("python", "RESPONSIBILITY", after, line=4),
      evidence("cpp", "RESPONSIBILITY", after, line=7),
      evidence("boundary", "BOUNDARY", after, line=1),
      evidence("context", "CONTEXT", after, line=1),
      evidence("seam", "EXTRACTION_SEAM", after, line=4),
      evidence("evolution", "EVOLUTION", before, old=True, line=1),
    )
    return NamingCase("example/repo", after, target_kind, "collector-role",
        target_name, target_path, ("coord", "python", "cpp"), ev,
        "RESOLVED", coherent, name_fit,
        ("seam",) if name_fit == "NARROW" else (), (), ())


def bindings():
    return (
        ResponsibilityBinding("coord", (PATH + "::class:Collector",)),
        ResponsibilityBinding("python", (PATH + "::function:python_decode",)),
        ResponsibilityBinding("cpp", (PATH + "::function:cpp_decode",)),
    )


def keep():
    return NamingOption("keep", "KEEP", "Stable generic owner remains")


def extraction(*, dest=DEST, existing=True):
    return ExtractionUnit("python-provider", "python_provider", ("python",),
                          ("seam",), dest, existing)


def extract_option(*, variant="EXTRACT_KEEP", dest=DEST, existing=True):
    return NamingOption("extract", variant, "Delegate Python implementation to provider",
          proposed_name="source_collector" if variant == "EXTRACT_RENAME" else None,
          module_path_policy="RETIRE_OLD_PATH" if variant == "EXTRACT_RENAME" else None,
          coverage_rationale="Own coordination and C++ scan",
          boundary_rationale="Does not implement Python parser after extraction",
          context_rationale="Diagnostics gives collector semantics",
          retained_responsibility_ids=("coord", "cpp"),
          extracted_units=(extraction(dest=dest, existing=existing),),
          post_extraction_name_fit="VALID",
          evidence_ids=("seam", "evolution", "boundary", "context"),
          impact_paths=(PATH,))


def inspect(history, *, obj=None, mapped=None, subject=None):
    root, before, after = history
    c = subject or case(before, after)
    return verify_naming_boundary(c, obj or keep(), GitSourceProvider(root), mapped or bindings())


def test_valid_keep_real_exact_git_declarations(history):
    r = inspect(history)
    assert r.status == "STRUCTURE_WITNESSED"
    assert len(r.verified_bindings) == 3
    assert not r.semantic_compatibility_proven
    assert not r.mutation_approved
    assert "INDEPENDENT_RESPONSIBILITY_INTERPRETATION" in r.required_checks


def test_existing_provider_destination_and_extract_keep(history):
    root, before, after = history
    c = case(before, after)
    r = inspect(history, obj=extract_option(), subject=c)
    assert r.status == "STRUCTURE_WITNESSED"
    assert r.existing_destinations == (DEST,)
    assert not r.mutation_approved


def test_stable_name_extract_and_rename_blocked(history):
    r = inspect(history, obj=extract_option(variant="EXTRACT_RENAME"))
    assert r.status == "REJECTED"
    assert "VALID_NAME_DOES_NOT_REQUIRE_RENAME" in r.blockers


def test_current_worktree_tampering_cannot_change_observed_symbols(history):
    root, before, after = history
    (root / PATH).write_text("# tampered\n", encoding="utf8")
    r = inspect(history)
    assert r.status == "STRUCTURE_WITNESSED"
    assert "function:python_decode" in " ".join(x.key for x in r.observed_symbols)


def test_claim_to_missing_symbol_fails(history):
    bad = bindings()[:1] + (ResponsibilityBinding("python", (PATH+"::function:fiction",)),) + bindings()[2:]
    r = inspect(history, mapped=bad)
    assert r.status == "REJECTED"
    assert any("BOUND_SYMBOL_NOT_OWNED" in x for x in r.blockers)


def test_invented_binding_fails(history):
    r = inspect(history, mapped=bindings() + (ResponsibilityBinding("extra", (PATH+"::function:cpp_decode",)),))
    assert r.status == "REJECTED"
    assert "INVENTED_BOUND_RESPONSIBILITY" in r.blockers


def test_missing_responsibility_binding_holds(history):
    r = inspect(history, mapped=bindings()[:-1])
    assert r.status == "HOLD"
    assert "RESPONSIBILITY_NOT_BOUND:cpp" in r.unresolved


def test_duplicate_bindings_rejected(history):
    r = inspect(history, mapped=bindings() + (bindings()[0],))
    assert r.status == "REJECTED"
    assert "DUPLICATE_RESPONSIBILITY_BINDING" in r.blockers


def test_declaration_citation_required_not_arbitrary_line(history):
    root, before, after = history
    c = case(before, after)
    ev = tuple(replace(e, source_refs=(f"{PATH}:5@{digest(NEW)}",)) if e.id == "python" else e for e in c.evidence)
    r = inspect(history, subject=replace(c, evidence=ev))
    assert r.status == "HOLD"
    assert any("RESPONSIBILITY_CITATION_NOT_DECLARATION" in x for x in r.unresolved)


def test_invalid_current_blob_rejected(history):
    root, before, after = history
    c = case(before, after)
    ev = tuple(replace(e, source_refs=(f"{PATH}:4@{'0'*40}",)) if e.id == "python" else e for e in c.evidence)
    r = inspect(history, subject=replace(c, evidence=ev))
    assert r.status == "REJECTED"
    assert any("SOURCE_BLOB_CONTRADICTION" in x for x in r.blockers)


def test_new_destination_path_exists_rejected(history):
    r = inspect(history, obj=extract_option(existing=False))
    assert r.status == "REJECTED"
    assert any("NEW_EXTRACTION_PATH_ALREADY_EXISTS" in x for x in r.blockers)


def test_claimed_existing_destination_not_found_rejected(history):
    r = inspect(history, obj=extract_option(dest="diagnostics/providers/missing.py"))
    assert r.status == "REJECTED"
    assert any("DECLARED_EXISTING_OWNER_NOT_FOUND" in x for x in r.blockers)


def test_new_destination_missing_is_reviewable_as_structure(history):
    r = inspect(history, obj=extract_option(dest="diagnostics/providers/new.py",existing=False))
    assert r.status == "STRUCTURE_WITNESSED"
    assert r.existing_destinations == ()


def test_shared_symbol_across_postowners_holds(history):
    m=(ResponsibilityBinding("coord", (PATH+"::class:Collector",)),
       ResponsibilityBinding("python", (PATH+"::function:python_decode",)),
       ResponsibilityBinding("cpp", (PATH+"::function:python_decode",)))
    root,before,after=history
    c=case(before,after)
    ev=tuple(replace(e,source_refs=(f"{PATH}:4@{digest(NEW)}",)) if e.id=="cpp" else e for e in c.evidence)
    r=inspect(history,obj=extract_option(),mapped=m,subject=replace(c,evidence=ev))
    assert r.status == "HOLD"
    assert any("SHARED_SYMBOL_SPLIT_NEEDS_BEHAVIORAL_SEAM" in x for x in r.unresolved)


def test_existing_owner_duplicate_implementation_holds(history):
    root,before,after=history
    p=root / DEST
    p.write_text("def python_decode(source): return source\n",encoding="utf8")
    git(root,"add",".")
    git(root,"commit","-q","-m","overlap")
    new_head=git(root,"rev-parse","HEAD")
    c=case(before,after)
    # Re-anchoring all current claims to new commit, which preserves collector blob.
    ev=tuple(replace(e,source_revision=new_head) if e.source_revision==after else e for e in c.evidence)
    c=replace(c,revision=new_head,evidence=ev)
    r=verify_naming_boundary(c,extract_option(),GitSourceProvider(root),bindings())
    assert r.status == "HOLD"
    assert any("POSSIBLE_DUPLICATE_IMPLEMENTATION" in x for x in r.unresolved)


def test_class_scope_restricts_to_class_and_its_methods(history):
    root,before,after=history
    c=case(before,after,target_kind="CLASS",target_name="Collector")
    c=replace(c,responsibility_ids=("coord",))
    r=inspect(history,subject=c,mapped=(ResponsibilityBinding("coord",(PATH+"::class:Collector",)),))
    assert r.status == "STRUCTURE_WITNESSED"
    assert all("function:python_decode" not in x.key for x in r.observed_symbols)


def test_function_scope_is_single_declaration(history):
    root,before,after=history
    c=case(before,after,target_kind="FUNCTION",target_name="python_decode")
    c=replace(c,responsibility_ids=("python",))
    r=inspect(history,subject=c,mapped=(ResponsibilityBinding("python",(PATH+"::function:python_decode",)),))
    assert r.status == "STRUCTURE_WITNESSED"
    assert len(r.observed_symbols) == 1


def test_folder_scope_includes_exact_git_python_sources(history):
    root,before,after=history
    c=case(before,after,target_kind="FOLDER",target_name="diagnostics",target_path="diagnostics")
    r=inspect(history,subject=c)
    assert r.status == "STRUCTURE_WITNESSED"
    assert any(x.key.startswith(DEST) for x in r.observed_symbols)


def test_nonexistent_target_holds(history):
    root,before,after=history
    c=replace(case(before,after),current_path="diagnostics/nonexistent.py")
    r=inspect(history,subject=c)
    assert r.status == "HOLD"
    assert "TARGET_PYTHON_SOURCE_NOT_FOUND" in r.unresolved


def test_file_budget_holds(history):
    root,before,after=history
    c=case(before,after,target_kind="FOLDER",target_name="diagnostics",target_path="diagnostics")
    r=verify_naming_boundary(c,keep(),GitSourceProvider(root),bindings(),max_files=1)
    assert r.status == "HOLD"
    assert "SOURCE_FILE_BUDGET_EXCEEDED" in r.unresolved


def test_non_git_provider_rejected(history):
    root,before,after=history
    with pytest.raises(TypeError,match="BOUNDARY_GIT_PROVIDER_REQUIRED"):
        verify_naming_boundary(case(before,after),keep(),object(),bindings())


def test_extract_cannot_ignore_unmapped_owner_declaration(history):
    root,before,after=history
    # Explicitly scoped observations are insufficient if a module-level
    # declaration has no bound owner responsibility before extraction.
    c=case(before,after)
    c=replace(c,responsibility_ids=("coord", "python"))
    m=bindings()[:2]
    candidate=extract_option()
    candidate=replace(candidate,retained_responsibility_ids=("coord",))
    r=inspect(history,obj=candidate,mapped=m,subject=c)
    assert r.status=="HOLD"
    assert "OWNER_DECLARATION_INVENTORY_NOT_ACCOUNTED" in r.unresolved
    assert PATH+"::function:cpp_decode" in r.unbound_owner_declarations


def test_keep_allows_bounded_partial_inspection_but_discloses_unbound(history):
    root,before,after=history
    c=replace(case(before,after),responsibility_ids=("coord",))
    r=inspect(history,subject=c,mapped=bindings()[:1])
    assert r.status=="STRUCTURE_WITNESSED"
    assert PATH+"::function:cpp_decode" in r.unbound_owner_declarations
    assert not r.mutation_approved


def test_boundary_reuses_only_budgeted_scope_reads(history, monkeypatch):
    root, before, baseline = history
    provider = GitSourceProvider(root)
    real_read = provider.read_at_revision
    calls = []

    def read(revision, path):
        calls.append((revision, path))
        return real_read(revision, path)

    monkeypatch.setattr(provider, "read_at_revision", read)
    subject = case(before, baseline)
    result = verify_naming_boundary(subject, keep(), provider, bindings())
    assert result.status == "STRUCTURE_WITNESSED"
    # Independent provenance once, then one scope read (no second AST read).
    assert calls.count((baseline, PATH)) == 2
    assert calls.count((before, PATH)) == 1
    calls.clear()
    repeated = verify_naming_boundary(subject, keep(), provider, bindings())
    assert repeated == result
    assert calls.count((baseline, PATH)) == 2
    assert calls.count((before, PATH)) == 1


def test_boundary_folder_budget_precedes_parsing(history):
    root, before, baseline = history
    malformed = root / "diagnostics/aaa.py"
    malformed.write_bytes(b"def invalid(\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "malformed first source")
    revision = git(root, "rev-parse", "HEAD")
    subject = case(before, baseline, target_kind="FOLDER", target_name="diagnostics",
                   target_path="diagnostics")
    subject = replace(subject, revision=revision,
                      evidence=tuple(replace(e, source_revision=revision)
                                     if e.source_revision == baseline else e
                                     for e in subject.evidence))
    provider = GitSourceProvider(root)
    result = verify_naming_boundary(subject, keep(), provider, bindings(),
                                    max_bytes=len(malformed.read_bytes()))
    assert "SOURCE_BYTE_BUDGET_EXCEEDED" in result.unresolved
    assert not any(x.startswith("EXACT_SOURCE_OR_AST_UNAVAILABLE:")
                   for x in result.unresolved)
    assert result.observed_symbols == ()
    enough = verify_naming_boundary(subject, keep(), provider, bindings())
    assert "EXACT_SOURCE_OR_AST_UNAVAILABLE:SyntaxError" in enough.unresolved
    assert enough.observed_symbols == ()


def test_boundary_destination_still_read_independently(history, monkeypatch):
    root, before, baseline = history
    provider = GitSourceProvider(root)
    real_read = provider.read_at_revision
    calls = []

    def read(revision, path):
        calls.append((revision, path))
        return real_read(revision, path)

    monkeypatch.setattr(provider, "read_at_revision", read)
    result = verify_naming_boundary(case(before, baseline), extract_option(),
                                    provider, bindings())
    assert result.status == "STRUCTURE_WITNESSED"
    assert calls.count((baseline, PATH)) == 2
    assert calls.count((baseline, DEST)) == 1
    assert calls.count((before, PATH)) == 1
