"""Source-bound Python AST collector tests; no import execution or runtime claims."""

from pathlib import Path

import pytest

from physics_harness.code.diagnostics import (
    GitSourceProvider, PythonAstCollector, ScanRequest, run_scan,
)


SOURCE = """\
import os
from math import sin as sine

def outer(value):
    if value:
        return sine(value)
    return 0

class Widget:
    def call(self, x):
        return outer(x)
"""


def scan(git_factory, files, *, includes=("src/*.py",),
         collectors=("python_ast",)):
    root, sha = git_factory(files)
    req = ScanRequest(
        repository="example/repo", revision=sha, includes=includes,
        collectors=collectors,
    )
    return run_scan(req, GitSourceProvider(root))


def test_python_ast_declarations_imports_calls_and_references_are_candidates(git_factory):
    result = scan(git_factory, {"src/code.py": SOURCE})
    assert result.status == "COMPLETE"
    kinds = {n.kind for n in result.graph.nodes}
    assert {"python_class", "python_function", "python_import_specifier",
            "python_call_site", "python_name_specifier"}.issubset(kinds)
    relations = {e.relation for e in result.graph.edges}
    assert {"DEFINES", "IMPORTS_CANDIDATE",
            "CALLS_CANDIDATE", "REFERENCES_CANDIDATE"}.issubset(relations)
    assert all(e.evidence_ids for e in result.graph.edges)
    assert all(e.observation_status == "SOURCE_DECLARED"
               for e in result.graph.evidence)
    assert not result.graph.claims
    assert "CALLS" not in relations
    assert "EXECUTED" not in relations
    functions = {n.qualified_name: n for n in result.graph.nodes
                 if n.kind == "python_function"}
    assert "src/code.py:outer" in functions
    assert "src/code.py:Widget.call" in functions
    assert functions["src/code.py:outer"].attributes["branches"] == 1
    assert functions["src/code.py:outer"].location.start_line == 4
    assert functions["src/code.py:outer"].attributes["loc"] == 4


def test_python_ast_nested_function_metrics_exclude_nested_definitions(git_factory):
    source = """\
def outer(x):
    if x:
        return 1
    def inner(v):
        if v:
            if v > 1:
                return 2
    return inner(x)
"""
    result = scan(git_factory, {"src/code.py": source})
    symbols = {node.qualified_name: node for node in result.graph.nodes
               if node.kind == "python_function"}
    assert symbols["src/code.py:outer"].attributes["branches"] == 1
    assert symbols["src/code.py:outer.inner"].attributes["branches"] == 2
    assert symbols["src/code.py:outer.inner"].attributes["max_branch_nesting"] == 2


def test_reflective_calls_surface_unresolved_and_partial(git_factory):
    source = """\
def resolve(obj, name):
    return getattr(obj, name)(4)

import importlib
module = importlib.import_module("other")
"""
    result = scan(git_factory, {"src/code.py": source})
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "UNRESOLVED"
    assert any(msg.startswith("DYNAMIC_PYTHON_REFERENCE:")
               for msg in result.receipt.unresolved)
    assert any(n.kind == "unresolved" for n in result.graph.nodes)
    assert any(e.relation == "DYNAMIC_REFERENCE_CANDIDATE"
               for e in result.graph.edges)
    assert any(e.observation_status == "UNRESOLVED"
               for e in result.graph.evidence)
    assert all(e.observation_status != "RUNTIME_OBSERVED"
               for e in result.graph.evidence)


@pytest.mark.parametrize("source", [
    "def bad(:\n  pass\n",
    b"# coding: ascii\nvalue = '\xff'\n",
])
def test_malformed_python_fails_closed_without_fake_complete(git_factory, source):
    result = scan(git_factory, {"src/code.py": source})
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "FAILED"
    assert not any(e.relation == "DEFINES" for e in result.graph.edges)
    assert any(v.startswith("COLLECTOR_FAILED:python_ast")
               for v in result.receipt.files[0].details)


def test_file_identity_and_declarations_stable_across_revisions(git_factory):
    one = scan(git_factory, {"src/code.py": SOURCE})
    two = scan(git_factory, {"src/code.py": SOURCE.replace("return 0", "return 10")})
    first = {n.qualified_name: n.id for n in one.graph.nodes
             if n.kind in {"python_function", "python_class"}}
    second = {n.qualified_name: n.id for n in two.graph.nodes
              if n.kind in {"python_function", "python_class"}}
    assert first == second
    assert one.graph.scope.revision != two.graph.scope.revision
    assert {e.id for e in one.graph.evidence} != {e.id for e in two.graph.evidence}


def test_multiple_python_files_share_identifier_specifiers_without_conflicts(git_factory):
    result = scan(git_factory, {
        "src/a.py": "def f():\n    return len([1])\n",
        "src/b.py": "def g():\n    return len([2])\n",
    })
    assert result.status == "COMPLETE"
    name_specifiers = [n for n in result.graph.nodes
                       if n.kind == "python_name_specifier" and n.name == "len"]
    assert len(name_specifiers) == 1
    assert len(name_specifiers[0].evidence_ids) == 2
    assert result.receipt.scanned_count == 2


def test_existing_workflow_default_and_explicit_multi_collector_scan(git_factory):
    workflow = "on: [push]\njobs:\n  check:\n    steps:\n      - run: echo ok\n"
    result = scan(
        git_factory,
        {".github/workflows/check.yml": workflow, "src/code.py": SOURCE},
        includes=(".github/workflows/*.yml", "src/*.py"),
        collectors=("workflow", "python_ast"),
    )
    assert result.status == "COMPLETE"
    assert {n.kind for n in result.graph.nodes} >= {
        "workflow", "python_function", "python_class",
    }
    assert result.receipt.scanned_count == 2
    assert result.receipt.collector_versions == (
        ("python_ast", PythonAstCollector.version),
        ("workflow", "github-actions-static-v0.1"),
    )


def test_python_collector_support_does_not_expand_other_source_formats():
    from physics_harness.code.diagnostics import SourceRecord
    collector = PythonAstCollector()
    assert collector.supports(SourceRecord("src/code.py", "a" * 40, "100644", 1))
    assert not collector.supports(
        SourceRecord("src/code.C", "a" * 40, "100644", 1),
    )



def test_nested_calls_sharing_start_position_get_distinct_canonical_nodes(git_factory):
    result = scan(git_factory, {
        "src/code.py": "def outer(obj, name):\n    return getattr(obj, name)(4)\n",
    })
    assert result.status == "PARTIAL"
    calls = [n for n in result.graph.nodes if n.kind == "python_call_site"]
    assert {n.attributes["callee_expression"] for n in calls} == {
        "getattr", "getattr(obj, name)",
    }
    assert len({n.id for n in calls}) == 2
    assert all(edge.evidence_ids for edge in result.graph.edges)
