"""Strict, source-bound JSON path-candidate tests; no runtime or deletion claims."""

import pytest

from physics_harness.code.diagnostics import (
    GitSourceProvider, JsonSourceCollector, ScanRequest, SourceRecord, run_scan,
)


def scan(git_factory, files, *, includes=("*.json",), collectors=("json",)):
    root, sha = git_factory(files)
    request = ScanRequest(repository="example/repo", revision=sha, includes=includes,
                          collectors=collectors)
    return run_scan(request, GitSourceProvider(root))


def witnesses(result):
    return [e for e in result.graph.evidence if e.method == JsonSourceCollector.version]


def test_json_nested_references_exact_pointer_and_token_positions(git_factory):
    src = (
        '{\n'
        '  "representative": {"oracle": "physics_app\\/ci\\/case.i"},\n'
        '  "a/b~c": ["physics_app/ci/case.i", "physics_app/ci/case.i"],\n'
        '  "not_a_reference": 123,\n'
        '  "url": "https://example.com/case.i",\n'
        '  "description": "a historical note",\n'
        '  "case.i": false\n'
        '}\n'
    )
    result = scan(git_factory, {"docs/contract.json": src})
    assert result.status == "COMPLETE"
    assert result.verification.status == "VERIFIED"
    assert result.receipt.collector_versions == (("json", JsonSourceCollector.version),)
    refs = {e.attributes["json_pointer"]: e for e in witnesses(result)}
    assert set(refs) == {"/representative/oracle", "/a~1b~0c/0", "/a~1b~0c/1"}
    first = refs["/representative/oracle"]
    assert first.attributes["line"] == 2
    assert first.attributes["column"] == src.splitlines()[1].index('"physics_app')
    assert first.attributes["literal"] == "physics_app/ci/case.i"
    assert first.source_ref == "docs/contract.json:2@" + result.receipt.files[0].blob_sha
    assert first.attributes["source_sha"] == result.receipt.revision
    target, = [n for n in result.graph.nodes if n.kind == "file_path_specifier"]
    assert target.name == "physics_app/ci/case.i"
    assert len(target.evidence_ids) == 3
    edges = [e for e in result.graph.edges if e.relation == "REFERENCES_FILE_CANDIDATE"]
    assert len(edges) == 3 and len({e.id for e in edges}) == 3
    assert all(e.target_id == target.id for e in edges)
    assert not any(n.kind == "file" and n.name == "case.i" for n in result.graph.nodes)
    assert not result.graph.claims
    assert all(e.observation_status == "SOURCE_DECLARED" for e in witnesses(result))


@pytest.mark.parametrize("source", [
    '{"a":"one.i","a":"two.i"}', '{"a": {"x": 1, "x": 2}}',
    '{"a":1,}', '["case.i",]', '{"a":NaN}', '{"a":Infinity}',
    '{"a":-Infinity}', '{"a": "case.i"} trailing', '{"a": "case.i"',
    '{"a":01}', '{"a":"\\ud800"}', b'{"a":"\xff"}',
])
def test_invalid_json_no_partial_fake_evidence(git_factory, source):
    result = scan(git_factory, {"bad.json": source})
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "FAILED"
    assert not witnesses(result)
    assert not result.graph.edges
    assert any("INVALID_JSON" in detail for detail in result.receipt.files[0].details)


def test_same_path_across_documents_and_revisions_stable(git_factory):
    first = scan(git_factory, {"a.json": '{"ref":"dir/case.i"}',
                               "b.json": '{"ref":"dir/case.i"}'})
    second = scan(git_factory, {"a.json": '{\n  "ref": "dir/case.i"\n}',
                                "b.json": '{"ref":"dir/case.i"}'})
    assert first.status == second.status == "COMPLETE"
    nodes = lambda r: {n.id for n in r.graph.nodes if n.kind == "file_path_specifier"}
    edges = lambda r: {e.id for e in r.graph.edges}
    assert nodes(first) == nodes(second)
    assert edges(first) == edges(second)
    assert {e.id for e in witnesses(first)}.isdisjoint({e.id for e in witnesses(second)})
    target, = [n for n in first.graph.nodes if n.kind == "file_path_specifier"]
    assert len(target.evidence_ids) == 2


def test_dynamic_or_nonportable_path_is_unresolved(git_factory):
    result = scan(git_factory, {"paths.json":
                  '["$' + '{ROOT}/case.i","inputs/*.i","/tmp/case.i","../valid.i"]'})
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "UNRESOLVED"
    assert sum(e.relation == "JSON_FILE_REFERENCE_UNRESOLVED" for e in result.graph.edges) == 3
    assert sum(e.relation == "REFERENCES_FILE_CANDIDATE" for e in result.graph.edges) == 1
    assert sum(e.observation_status == "UNRESOLVED" for e in witnesses(result)) == 3
    assert any(v.startswith("JSON_PATH_EXPRESSION_UNRESOLVED:") for v in result.receipt.unresolved)


def test_top_level_value_and_crlf_utf8_location(git_factory):
    root_value = scan(git_factory, {"a.json": '"dir/case.i"'})
    e, = witnesses(root_value)
    assert e.attributes["json_pointer"] == ""
    assert (e.attributes["line"], e.attributes["column"]) == (1, 0)
    src = '{\r\n  "한글": "dir/case.i"\r\n}'
    result = scan(git_factory, {"a.json": src})
    e, = witnesses(result)
    assert e.attributes["json_pointer"] == "/한글"
    assert (e.attributes["line"], e.attributes["column"]) == (2, src.splitlines()[1].index('"dir'))


def test_depth_budget_marks_partial(git_factory):
    result = scan(git_factory, {"deep.json": "[" * 130 + '"case.i"' + "]" * 130})
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "UNRESOLVED"
    assert any(v.startswith("JSON_DEPTH_LIMIT:") for v in result.receipt.unresolved)
    assert not witnesses(result)


def test_reference_budget_marks_partial(git_factory, monkeypatch):
    from physics_harness.code.diagnostics.providers import json_source
    monkeypatch.setattr(json_source, "_MAX_REFERENCES", 2)
    result = scan(git_factory, {"paths.json": '["a.i","b.i","c.i"]'})
    assert result.status == "PARTIAL"
    assert any(v.startswith("JSON_REFERENCE_LIMIT:") for v in result.receipt.unresolved)
    assert not witnesses(result)


def test_json_support_opt_in_and_multi_collector(git_factory):
    c = JsonSourceCollector()
    assert c.supports(SourceRecord("config.json", "a" * 40, "100644", 0))
    assert not c.supports(SourceRecord("config.yaml", "a" * 40, "100644", 0))
    result = scan(git_factory, {"config.json": '{"ref":"case.i"}',
                               "code.py": "def f():\n    return 1\n"},
                  includes=("*.json", "*.py"), collectors=("python_ast", "json"))
    assert result.status == "COMPLETE"
    assert {e.relation for e in result.graph.edges} >= {"REFERENCES_FILE_CANDIDATE", "DEFINES"}
    assert ScanRequest("example/repo", "a" * 40, ("*.json",)).collectors == ("workflow",)
