"""Source-only cross-format file-reference observations and exact Git resolution."""

from physics_harness.code.analysis import resolve_file_references
from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan


def scan(git_factory, files):
    root, sha = git_factory(files)
    provider = GitSourceProvider(root)
    patterns = tuple(sorted({p.rsplit(".", 1)[-1] for p in files if p.endswith((".i", ".py", ".json"))}))
    collectors = {"i": "moose_input", "py": "python_ast", "json": "json"}
    result = run_scan(ScanRequest("example/repo", sha, tuple("*." + p for p in patterns),
                                  collectors=tuple(collectors[p] for p in patterns)), provider)
    return result, provider


def references(result):
    evidence = result.graph.evidence_by_id()
    return [(edge, evidence[edge.evidence_ids[0]]) for edge in result.graph.edges
            if edge.relation in {"REFERENCES_FILE_CANDIDATE", "FILE_REFERENCE_UNRESOLVED",
                                 "JSON_FILE_REFERENCE_UNRESOLVED"}]


def test_python_whole_literal_and_composition_are_distinct(git_factory):
    src = '''"""not_a_consumer.i"""
ROOT = object()
paths = ("case.i", "case.i", "ordinary prose")
a = ROOT / "physics_app/ci/case.i"
b = ROOT / "physics_app" / "case.i"
c = Path("dir", "case.i")
d = Path(variable)
e = f"{variable}/case.i"
f = Path("other.i")
'''
    result, _ = scan(git_factory, {"script.py": src})
    rows = references(result)
    candidates = [ev for e, ev in rows if e.relation == "REFERENCES_FILE_CANDIDATE"]
    assert sorted(ev.attributes["literal"] for ev in candidates) == [
        "case.i", "case.i", "other.i", "physics_app/ci/case.i"]
    assert sum(ev.attributes["path_context"] == "COMPOSED_PATH_FRAGMENT"
               for _, ev in rows) == 2
    assert any(ev.attributes["path_context"] == "FORMATTED_PATH_EXPRESSION" for _, ev in rows)
    assert any(ev.attributes["path_context"] == "PATH_COMPOSITION" for _, ev in rows)
    assert result.status == "PARTIAL"
    assert not result.graph.claims
    assert all(ev.observation_status != "RUNTIME_OBSERVED" for _, ev in rows)
    ev, = [ev for ev in candidates if ev.attributes["literal"] == "physics_app/ci/case.i"]
    assert ev.attributes["line"] == 4
    assert ev.attributes["source_expression"] == '"physics_app/ci/case.i"'
    assert ev.attributes["column_unit"] == "UTF8_BYTE"


def test_hit_include_file_and_table_keep_existing_facts(git_factory):
    source = """!include base.i
[Mesh]
  type = FileMesh
  file = '../../experiments/qvt.msh' # mesh
[]
[Materials]
  [transport]
    type = DDTransportMaterial
    table_file = "../../experiments/electron_moments.txt"
  []
[]
"""
    result, _ = scan(git_factory, {"physics_app/ci/case.i": source, "base.i": ""})
    rows = references(result)
    paths = {ev.attributes["literal"]: ev for _, ev in rows}
    assert set(paths) == {"base.i", "../../experiments/qvt.msh",
                          "../../experiments/electron_moments.txt"}
    assert paths["../../experiments/qvt.msh"].attributes["line"] == 4
    assert paths["../../experiments/qvt.msh"].attributes["raw_value"] == "'../../experiments/qvt.msh'"
    assert paths["../../experiments/electron_moments.txt"].attributes["block_path"] == ("Materials", "transport")
    assert {e.relation for e in result.graph.edges} >= {
        "INCLUDES_CANDIDATE", "DECLARES_TYPE_USE", "DECLARES_INPUT_BLOCK"}
    assert result.status == "PARTIAL"  # include expansion remains unresolved


def test_hit_dynamic_duplicate_and_multivalue_not_silently_resolved(git_factory):
    source = """[Mesh]
  file = one.msh
  file = '\${ROOT}/two.msh'
  table_file = 'one.txt two.txt'
[]
""".replace("\\$", "$")
    result, _ = scan(git_factory, {"case.i": source})
    rows = references(result)
    assert sum(e.relation == "FILE_REFERENCE_UNRESOLVED" for e, _ in rows) == 2
    assert sum(e.relation == "REFERENCES_FILE_CANDIDATE" for e, _ in rows) == 1
    assert any(v.startswith("MOOSE_DUPLICATE_PARAMETER:") for v in result.receipt.unresolved)


def test_cross_format_shared_specifier_and_exact_git_resolution(git_factory):
    result, provider = scan(git_factory, {
        "contract.json": '{"path":"inputs/case.i"}',
        "script.py": 'filename = "inputs/case.i"\n',
        "other.i": "[Mesh]\n file = inputs/case.i\n[]\n",
        "inputs/case.i": "[Mesh]\n[]\n",
    })
    rows = references(result)
    assert result.status == "COMPLETE"
    assert len(rows) == 3
    assert len({e.target_id for e, _ in rows}) == 1
    target = result.graph.nodes_by_id()[rows[0][0].target_id]
    assert target.kind == "file_path_specifier" and len(target.evidence_ids) == 3
    report = resolve_file_references(result.graph, result.receipt, provider,
        bases_by_edge={e.id: ("REPOSITORY_ROOT",) for e, _ in rows})
    assert len(report.rows) == 3
    assert all(r.status == "RESOLVED_CANDIDATE" and r.targets[0].path == "inputs/case.i"
               for r in report.rows)
    assert not report.safe_to_delete


def test_hit_relative_mesh_table_resolve_against_explicit_owner(git_factory):
    result, provider = scan(git_factory, {
        "physics_app/ci/case.i": "[Mesh]\n file = '../../experiments/qvt.msh'\n table_file = '../../experiments/moments.txt'\n[]\n",
        "experiments/qvt.msh": "mesh", "experiments/moments.txt": "table",
    })
    refs = references(result)
    report = resolve_file_references(result.graph, result.receipt, provider,
        bases_by_edge={e.id: ("OWNER_DIRECTORY",) for e, _ in refs})
    assert {r.targets[0].path for r in report.rows} == {
        "experiments/qvt.msh", "experiments/moments.txt"}
    assert all(r.status == "RESOLVED_CANDIDATE" and r.targets[0].coverage == "OUT_OF_SCOPE"
               for r in report.rows)
