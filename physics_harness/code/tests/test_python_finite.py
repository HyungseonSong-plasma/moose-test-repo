"""P3 bounded source candidates: no execution or global closure."""
from dataclasses import replace
import importlib.util

import pytest

from physics_harness.code.diagnostics import (
    FactBatch, GitSourceProvider, GraphAssembler, ScanRequest, run_scan,
)
from physics_harness.code.verification.consistency import verify_generated_artifact

PATH = "src/generate.py"


def scan(git_factory, source, *, collectors=("python_static",), extra=None):
    root, revision = git_factory({PATH: source, **(extra or {})})
    request = ScanRequest("example/repo", revision, ("src/*",), collectors=collectors)
    provider = GitSourceProvider(root)
    return request, provider, run_scan(request, provider)


def alternatives(result, relation="STATIC_CALL_ALTERNATIVE"):
    nodes = result.graph.nodes_by_id()
    return {(nodes[e.source_id].name, nodes[e.target_id].name)
            for e in result.graph.edges if e.relation == relation}


SOURCE = """
def alpha():
    return 'alpha'
def beta():
    return 'beta'
def entry(flag):
    fn = alpha if flag else beta
    return fn()
"""


def test_finite_alias_conditional_candidates_and_default_unchanged(git_factory):
    req, provider, result = scan(git_factory, SOURCE)
    assert alternatives(result) == {("fn", "alpha"), ("fn", "beta")}
    assert result.status == "PARTIAL"
    assert result.verification.status == "UNVERIFIED"
    assert not result.verification.failures
    ev = [e for e in result.graph.evidence if e.kind == "PYTHON_STATIC_ALTERNATIVE"]
    assert len(ev) == 2 and all(e.observation_status == "INFERRED" for e in ev)
    assert all(e.attributes["blob_sha"] == result.receipt.files[0].blob_sha for e in ev)
    assert not any(e.observation_status == "RUNTIME_OBSERVED" for e in result.graph.evidence)
    default = run_scan(replace(req, collectors=("python_ast",)), provider)
    assert not alternatives(default)
    assert default.status == "COMPLETE"
    assert {n.id for n in default.graph.nodes} <= {n.id for n in result.graph.nodes}
    assert run_scan(req, provider).graph == result.graph


def test_if_join_early_return_and_literal_branch(git_factory):
    _, _, result = scan(git_factory, """
def alpha(): return 'alpha'
def beta(): return 'beta'
def entry(flag):
    if flag:
        return alpha()
    if True:
        fn = beta
    else:
        fn = alpha
    return fn()
""")
    assert alternatives(result) == {("alpha", "alpha"), ("fn", "beta")}
    assert not result.verification.failures


def test_missing_branch_and_unknown_dictionary_key_stay_partial(git_factory):
    _, _, result = scan(git_factory, """
def alpha(): return 'alpha'
def beta(): return 'beta'
def entry(flag, key):
    if flag:
        fn = alpha
    fn()
    target = {'x': alpha, 'y': beta}[key]
    return target()
""")
    assert alternatives(result) == {("fn", "alpha"), ("target", "alpha"), ("target", "beta")}
    for name in ("fn", "target"):
        site = next(n for n in result.graph.nodes if n.kind == "python_call_site" and n.name == name)
        assert "PYTHON_STATIC_CALLEE_UNRESOLVED:" + site.id in result.graph.scope.unresolved


def test_static_dictionary_known_key(git_factory):
    _, _, result = scan(git_factory, """
def alpha(): return 'alpha'
def beta(): return 'beta'
KEY = 'x'
def entry():
    target = {'x': alpha, 'y': beta}[KEY]
    return target()
""")
    assert alternatives(result) == {("target", "alpha")}


def test_return_type_candidates_join_existing_moose_type(git_factory):
    source = """
PREFIX = 'Physics'
def entry(flag):
    suffix = 'First' if flag else 'Second'
    kind = PREFIX + suffix
    return f'[Kernels]\\n [./k]\\n type = {kind}\\n [../]\\n[]\\n'
"""
    _, _, result = scan(git_factory, source, collectors=("python_static", "cpp"),
                        extra={"src/kernel.C": 'registerMooseObject("PhysicsApp", PhysicsFirst);\n'})
    assert alternatives(result, "STATIC_RETURN_TYPE_ALTERNATIVE") == {
        ("entry", "PhysicsFirst"), ("entry", "PhysicsSecond")}
    first = [n for n in result.graph.nodes if n.kind == "moose_type" and n.name == "PhysicsFirst"]
    assert len(first) == 1
    assert {"STATIC_RETURN_TYPE_ALTERNATIVE", "DECLARES_MOOSE_REGISTRATION"} <= {
        e.relation for e in result.graph.edges if e.target_id == first[0].id}
    assert not result.verification.failures


@pytest.mark.parametrize("body", [
    "def entry(alpha):\n    return alpha()\n",
    "def entry():\n    alpha()\n    alpha = 0\n",
    "def entry(obj):\n    return getattr(obj, 'alpha')()\n",
    "def entry():\n    return factory()()\n",
    "def entry():\n    for x in []:\n        pass\n    return alpha()\n",
    "def entry():\n    global alpha\n    return alpha()\n",
])
def test_unsupported_or_shadowed_callee_is_not_invented(git_factory, body):
    _, _, result = scan(git_factory, "def alpha(): return 'alpha'\n" + body)
    assert not alternatives(result)
    assert result.status == "PARTIAL"
    assert any("PYTHON_STATIC_" in v for v in result.graph.scope.unresolved)
    assert not result.verification.failures


def test_decorated_or_rebound_function_not_inferred(git_factory):
    _, _, result = scan(git_factory, """
@decorator
def alpha(): return 'alpha'
def beta(): return 'beta'
beta = external
def entry(flag):
    target = alpha if flag else beta
    return target()
""")
    assert not alternatives(result)
    assert result.status == "PARTIAL"


def test_scan_does_not_execute_module(git_factory):
    _, _, result = scan(git_factory, "raise RuntimeError('must not execute')\n" + SOURCE)
    assert alternatives(result) == {("fn", "alpha"), ("fn", "beta")}
    assert not result.verification.failures


def test_alternative_budget_discards_inference_not_source_facts(git_factory):
    functions = "\n".join(f"def fn{i}(): return 'x'" for i in range(9))
    table = ", ".join(f"'{i}': fn{i}" for i in range(9))
    source = functions + f"\ndef entry(key):\n    target = {{{table}}}[key]\n    return target()\n"
    _, _, result = scan(git_factory, source)
    assert not alternatives(result)
    assert "PYTHON_STATIC_ALTERNATIVE_LIMIT" in result.graph.scope.unresolved
    assert any(n.kind == "python_call_site" for n in result.graph.nodes)
    assert not result.verification.failures


def test_static_and_p2_runtime_share_same_existing_site(git_factory):
    from physics_harness.code.verification.python_call_trace import (
        SelectedPythonFunction, trace_generated_calls,
    )
    req, provider, result = scan(git_factory, SOURCE,
                                 collectors=("python_ast", "python_static"))
    spec = importlib.util.spec_from_file_location("p3_fixture", provider.root / PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    blob = provider.read_at_revision(req.revision, PATH).record.blob_sha
    functions = tuple(SelectedPythonFunction(PATH, blob, getattr(module, name))
                      for name in ("entry", "alpha", "beta"))
    site = next(n for n in result.graph.nodes if n.kind == "python_call_site" and n.name == "fn")
    trace = trace_generated_calls(
        req, provider, entry=functions[0], functions=functions, site_ids=(site.id,),
        trace_id="p3-join", arguments={"flag": True}, artifact_path="inputs/generated.i",
        run_id=10, attempt=1, job_id=21, workflow_path=".github/workflows/example.yml")
    base = FactBatch(nodes=result.graph.nodes, edges=result.graph.edges,
                     evidence=result.graph.evidence, unresolved=result.graph.scope.unresolved)
    combined = GraphAssembler().assemble(req, (base, trace.result.batch), result.receipt)
    assert not combined.verification.failures
    assert alternatives(combined) == {("fn", "alpha"), ("fn", "beta")}
    assert alternatives(combined, "PYTHON_FRAME_CALL_OBSERVED") == {("fn", "alpha")}
    assert combined.status == "PARTIAL"


@pytest.mark.parametrize("field,value", [
    ("blob_sha", "a" * 40), ("target_id", "node:" + "b" * 64),
    ("position", (99, 1, 99, 2)), ("alternative", "other"),
])
def test_static_metadata_tamper_fails_verification(git_factory, field, value):
    _, _, result = scan(git_factory, SOURCE)
    ev = next(e for e in result.graph.evidence if e.kind == "PYTHON_STATIC_ALTERNATIVE")
    bad = replace(ev, attributes={**dict(ev.attributes), field: value})
    graph = replace(result.graph, evidence=tuple(
        bad if e.id == ev.id else e for e in result.graph.evidence))
    receipt = verify_generated_artifact(graph, result.receipt)
    assert receipt.status == "FAILED"
    assert "PYTHON_STATIC_PROVENANCE_INVALID:" + ev.id in receipt.failures
