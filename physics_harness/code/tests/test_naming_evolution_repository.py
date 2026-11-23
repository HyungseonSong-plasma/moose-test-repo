"""Real exact-HEAD integration: owner/protocol/provider delegation evidence.

This intentionally does NOT fetch historical objects from remote in CI; shallow
checkouts may lack older commits. Older history is separately checked in a
self-contained two-commit Git integration test.
"""
from pathlib import Path
import subprocess

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.refactor.evolution import (
    find_delegation_seams, observe_python_structure,
)

ROOT = Path(__file__).resolve().parents[3]
BASE = "physics_harness/code/diagnostics/"


def test_repository_collector_already_has_external_language_owners():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   text=True).strip()
    provider = GitSourceProvider(ROOT)

    def read(path):
        file = provider.read_at_revision(head, path)
        return observe_python_structure(path, file.content,
                                        file.record.blob_sha, head)

    owner = read(BASE + "collector.py")
    implementations = tuple(read(BASE + "providers/" + module + ".py")
                            for module in ("python_ast", "cpp", "moose_input"))
    seams = find_delegation_seams(owner, implementations)
    assert {s.imported_implementation for s in seams} == {
        "PythonAstCollector", "CppSourceCollector", "MooseInputCollector"}
    assert {s.protocol for s in seams} == {"Collector"}
    assert "function:run_scan" in owner.declared_keys
    assert all(x.implementation_ref.endswith("@" +
           next(m.blob_sha for m in implementations if m.path == x.implementation_path))
           for x in seams)
    # An observed existing seam is NOT an instruction to extract a new libs/.
    assert all(s.implementation_path.startswith(BASE + "providers/") for s in seams)
