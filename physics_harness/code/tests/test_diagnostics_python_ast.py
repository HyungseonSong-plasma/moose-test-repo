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



def test_python_literal_moose_type_joins_cpp_and_input_candidate_identity(git_factory):
    python_code = """\
def make_input():
    return '''[FVKernels]
  [energy_joule]
    type = PhysicsFVElectronEnergyJouleHeating
  []
[]
'''
"""
    cpp_code = 'registerMooseObject("PhysicsApp", PhysicsFVElectronEnergyJouleHeating);\n'
    input_code = "[FVKernels]\n  [energy_joule]\n    type = PhysicsFVElectronEnergyJouleHeating\n  []\n[]\n"
    result = scan(
        git_factory,
        {
            "scripts/generate.py": python_code, "src/kernel.C": cpp_code,
            "inputs/case.i": input_code,
        },
        includes=("scripts/*.py", "src/*.C", "inputs/*.i"),
        collectors=("cpp", "moose_input", "python_ast"),
    )
    assert result.status == "COMPLETE"
    target = [n for n in result.graph.nodes
              if n.kind == "moose_type" and n.name == "PhysicsFVElectronEnergyJouleHeating"]
    assert len(target) == 1
    kinds = {e.relation for e in result.graph.edges if e.target_id == target[0].id}
    assert {"MAY_GENERATE_INPUT", "DECLARES_TYPE_USE",
            "DECLARES_MOOSE_REGISTRATION"}.issubset(kinds)
    assert len(target[0].evidence_ids) == 3
    assert not result.graph.claims
    assert "RUNTIME_INSTANTIATES" not in kinds


def test_python_history_assertion_is_not_active_generator(git_factory):
    text = '''\
def verify(contents):
    assert "type = PhysicsFVElectronEnergyJouleHeating" in contents
'''
    result = scan(git_factory, {"src/verify.py": text})
    assert result.status == "COMPLETE"
    relevant = [e for e in result.graph.edges
                if e.relation == "HISTORICAL_ASSERTS_TYPE"]
    assert len(relevant) == 1
    assert relevant[0].target_id in result.graph.nodes_by_id()
    assert not any(e.relation == "MAY_GENERATE_INPUT" for e in result.graph.edges)


def test_fstring_literal_type_is_candidate_but_render_unverified(git_factory):
    source = """\
def make_input(species):
    return f'''[FVKernels]
  [energy_{species}]
    type = PhysicsFVElectronEnergyJouleHeating
    variable = {species}
  []
[]
'''
"""
    result = scan(git_factory, {"src/make.py": source})
    assert result.status == "PARTIAL"
    assert any(e.relation == "MAY_GENERATE_INPUT" for e in result.graph.edges)
    assert any(u.startswith("PYTHON_GENERATOR_RENDER_UNVERIFIED:")
               for u in result.receipt.unresolved)
    assert not any(e.relation == "RUNTIME_INSTANTIATES"
                   for e in result.graph.edges)


def test_dynamic_fstring_type_is_unresolved_not_literal_type(git_factory):
    source = """\
def make_input(kernel):
    return f'''[FVKernels]
  [joule]
    type = {kernel}
  []
[]
'''
"""
    result = scan(git_factory, {"src/generate.py": source})
    assert result.status == "PARTIAL"
    assert any(e.relation == "MOOSE_TYPE_TEMPLATE_UNRESOLVED"
               for e in result.graph.edges)
    assert any(n.kind == "unresolved" for n in result.graph.nodes)
    assert not any(n.kind == "moose_type" for n in result.graph.nodes)


def test_docstring_is_not_treated_as_generator_consumer(git_factory):
    source = """\
def explain():
    '''Example input:
    type = PhysicsFVElectronEnergyJouleHeating
    '''
    return None
"""
    result = scan(git_factory, {"src/docs.py": source})
    assert result.status == "COMPLETE"
    assert not any(n.kind == "moose_type" for n in result.graph.nodes)


def test_static_generator_source_evidence_is_revision_bound(git_factory):
    first = scan(git_factory, {
        "src/generated.py": "DECK = 'type = MyKernel'\n",
    })
    second = scan(git_factory, {
        "src/generated.py": "DECK = 'type = MyKernel' # changed\n",
    })
    rel = "DECLARES_GENERATOR_TEMPLATE_CANDIDATE"
    assert {e.relation for e in first.graph.edges} >= {rel}
    assert first.status == second.status == "COMPLETE"
    first_node = next(n for n in first.graph.nodes if n.kind == "moose_type")
    second_node = next(n for n in second.graph.nodes if n.kind == "moose_type")
    assert first_node.id == second_node.id
    assert set(first_node.evidence_ids) != set(second_node.evidence_ids)



def test_shared_static_import_candidates_preserve_guard_contract(tmp_path):
    import ast
    from physics_harness.code.diagnostics.providers.python_ast import static_import_candidates

    path = tmp_path / "pkg" / "sub" / "module.py"
    tree = ast.parse("""\
import os as operating, json
from math import sin as sine
from . import sibling
from ..core import thing as alias
from ..base import *
from ....far import name
def nested():
    import pkg.inner
__import__("literal_dynamic")
importlib.import_module("other_dynamic")
""")
    refs = {ref for node in ast.walk(tree)
            for ref in static_import_candidates(node, path, tmp_path)}
    assert refs == {
        "os", "json", "math", "math.sin", "pkg.sub", "pkg.sub.sibling",
        "pkg.core", "pkg.core.thing", "pkg.base", "far", "far.name",
        "pkg.inner",
    }


def test_shared_static_import_candidates_absolute_without_relative_path(tmp_path):
    import ast
    from physics_harness.code.diagnostics.providers.python_ast import static_import_candidates

    outside = tmp_path.parent / "outside.py"
    node = ast.parse("import os").body[0]
    assert static_import_candidates(node, outside, tmp_path) == {"os"}
    relative = ast.parse("from . import member").body[0]
    with pytest.raises(ValueError):
        static_import_candidates(relative, outside, tmp_path)
