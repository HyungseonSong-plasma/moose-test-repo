"""Usage Matrix v0.1: evidence, scope and safety regression tests."""

from dataclasses import replace
import json

import pytest

from physics_harness.code.analysis import UsageRelation, build_usage_matrix
from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan
from physics_harness.code.graph import Edge, Evidence, GraphSnapshot, Node, Scope


CPP = (
    'registerMooseObject("DemoApp", UsedKernel);\n'
    'registerMooseObject("DemoApp", UnusedKernel);\n'
)
INPUT = (
    '[FVKernels]\n'
    '  [./used]\n'
    '    type = UsedKernel\n'
    '  [../]\n'
    '[]\n'
)
PATHS = ('inputs/example.i', 'src/kernels.C')
RULES = (UsageRelation('DECLARES_TYPE_USE', 'DIRECT_DECLARATION'),)
IGNORED = ('DECLARES_MOOSE_REGISTRATION',)


def scanned(git_factory, input_text=INPUT):
    root, sha = git_factory({'src/kernels.C': CPP, 'inputs/example.i': input_text})
    result = run_scan(
        ScanRequest(repository='example/repo', revision=sha,
                    includes=PATHS, collectors=('cpp', 'moose_input')),
        GitSourceProvider(root),
    )
    target_ids = {
        node.name: node.id for node in result.graph.nodes
        if node.kind == 'moose_type'
    }
    return result, target_ids


def matrix(result, target_ids, *, ignored=IGNORED, surfaces=()):
    return build_usage_matrix(
        result.graph, result.receipt, tuple(target_ids.values()), RULES,
        required_paths=PATHS, unverified_surfaces=surfaces,
        ignored_relations=ignored,
    )


def test_real_cpp_and_moose_sources_produce_deterministic_rows(git_factory):
    result, ids = scanned(git_factory)
    assert result.status == 'COMPLETE'
    first = matrix(result, ids)
    second = build_usage_matrix(
        result.graph, result.receipt,
        tuple(reversed(tuple(ids.values()))), tuple(reversed(RULES)),
        required_paths=PATHS, ignored_relations=IGNORED,
    )
    assert first == second
    rows = {row.target_name: row for row in first.rows}
    used = rows['UsedKernel']
    unused = rows['UnusedKernel']
    assert used.screening == 'RETAIN'
    assert used.identified_consumer_count == 1
    assert len(used.references) == 1
    witness = used.references[0].witnesses[0]
    assert witness.observation_status == 'SOURCE_DECLARED'
    assert witness.source_ref.startswith('inputs/example.i:')
    assert unused.screening == 'REVIEW_CANDIDATE'
    assert unused.identified_consumer_count == 0
    assert unused.coverage.complete_within_requested_scope
    assert not first.global_consumer_closed
    assert not first.mutation_approved
    assert not used.safe_to_delete and not unused.safe_to_delete
    exported = first.to_dict()
    assert exported['schema'] == 'code.usage_matrix.v0.1'
    assert exported['revision'] == result.graph.scope.revision
    assert exported['rows'][0]['safe_to_delete'] is False
    assert json.loads(json.dumps(exported))['rows'][0]['coverage']['scope_id']
    assert '| UsedKernel | 1 | DIRECT_DECLARATION: 1 | RETAIN |' in first.to_markdown()


def test_undeclared_surface_and_unclassified_relation_hold(git_factory):
    result, ids = scanned(git_factory)
    gap = matrix(result, ids, surfaces=('external_generators',))
    zero = next(row for row in gap.rows if row.target_name == 'UnusedKernel')
    assert zero.screening == 'HOLD'
    assert 'UNVERIFIED_CONSUMER_SURFACES' in zero.blockers
    unknown = matrix(result, ids, ignored=())
    zero = next(row for row in unknown.rows if row.target_name == 'UnusedKernel')
    assert zero.screening == 'HOLD'
    assert zero.unclassified_edge_ids
    assert 'UNCLASSIFIED_INCIDENT_EDGES' in zero.blockers


def test_incomplete_generator_input_is_hold_not_zero_caller(git_factory):
    result, ids = scanned(git_factory, INPUT.replace('UsedKernel', '$' + '{KERNEL}'))
    assert result.status == 'PARTIAL'
    report = matrix(result, ids)
    for row in report.rows:
        assert row.screening == 'HOLD'
        assert not row.coverage.complete_within_requested_scope


def test_unknown_duplicate_target_relation_policy_and_revision_rejected(git_factory):
    result, ids = scanned(git_factory)
    a = ids['UsedKernel']
    kwargs = dict(required_paths=PATHS, ignored_relations=IGNORED)
    with pytest.raises(ValueError, match='INVALID_USAGE_TARGETS'):
        build_usage_matrix(result.graph, result.receipt, (a, a), RULES, **kwargs)
    with pytest.raises(ValueError, match='UNKNOWN_USAGE_TARGET'):
        build_usage_matrix(result.graph, result.receipt, ('missing',), RULES, **kwargs)
    with pytest.raises(ValueError, match='DUPLICATE_USAGE_RELATION_SELECTOR'):
        build_usage_matrix(result.graph, result.receipt, (a,), RULES + RULES, **kwargs)
    with pytest.raises(ValueError, match='CONFLICTING_USAGE_RELATION_POLICY'):
        build_usage_matrix(result.graph, result.receipt, (a,), RULES,
                           required_paths=PATHS,
                           ignored_relations=('DECLARES_TYPE_USE',))
    with pytest.raises(ValueError, match='unknown relation direction'):
        UsageRelation('DECLARES_TYPE_USE', 'DIRECT', direction='SIDEWAYS')
    wrong = replace(result.receipt, revision='f' * 40)
    with pytest.raises(ValueError, match='TARGET_COVERAGE_SCOPE_MISMATCH'):
        build_usage_matrix(result.graph, wrong, (a,), RULES, **kwargs)


def test_missing_edge_evidence_does_not_create_verified_consumer(git_factory):
    result, ids = scanned(git_factory)
    stripped = tuple(
        replace(edge, evidence_ids=()) if edge.relation == 'DECLARES_TYPE_USE'
        else edge for edge in result.graph.edges
    )
    graph = replace(result.graph, edges=stripped)
    report = build_usage_matrix(
        graph, result.receipt, (ids['UsedKernel'],), RULES,
        required_paths=PATHS, ignored_relations=IGNORED,
    )
    row = report.rows[0]
    assert row.identified_consumer_count == 1
    assert row.screening == 'HOLD'
    assert 'USAGE_EDGE_EVIDENCE_MISSING' in row.blockers
    assert not row.safe_to_delete


def test_forward_rule_is_explicit_and_not_misclassified(git_factory):
    result, _ = scanned(git_factory)
    source = next(node.id for node in result.graph.nodes
                  if node.kind == 'file' and node.location and
                  node.location.path == 'src/kernels.C')
    forward = build_usage_matrix(
        result.graph, result.receipt, (source,),
        (UsageRelation('DECLARES_MOOSE_REGISTRATION', 'REGISTERED_TYPE', 'FORWARD'),),
        required_paths=PATHS,
    )
    assert forward.rows[0].identified_consumer_count == 2
    assert {r.consumer_name for r in forward.rows[0].references} == {
        'UsedKernel', 'UnusedKernel',
    }
    assert all(ref.witnesses[0].observation_status == 'SOURCE_DECLARED'
               for ref in forward.rows[0].references)


def test_inferred_evidence_and_cross_head_runtime_cannot_certify_usage():
    sha = 'a' * 40
    scope = Scope('scope:test', 'example/repo', sha,
                  included_paths=('src/item.py',), completeness='COMPLETE')
    ev = Evidence('ev:candidate', 'CANDIDATE', 'src/item.py:1', 'SOURCE_SCAN',
                  scope.id, observation_status='INFERRED')
    graph = GraphSnapshot(
        scope, nodes=(Node('n:t', 'symbol', 'target', evidence_ids=(ev.id,)),
                      Node('n:c', 'symbol', 'candidate')),
        edges=(Edge('e:c', 'n:c', 'n:t', 'USES', evidence_ids=(ev.id,)),),
        evidence=(ev,),
    )
    from physics_harness.code.diagnostics.receipt import EvidenceReceipt, FileCoverage
    receipt = EvidenceReceipt(
        repository='example/repo', revision=sha, scope_id=scope.id,
        requested_includes=('src/item.py',), requested_excludes=(),
        collector_versions=(('synthetic', 'v1'),),
        files=(FileCoverage('src/item.py', 'b' * 40, 'SCANNED'),),
        completeness='COMPLETE',
    )
    report = build_usage_matrix(graph, receipt, ('n:t',),
                                (UsageRelation('USES', 'POSSIBLE'),),
                                required_paths=('src/item.py',))
    assert report.rows[0].screening == 'HOLD'
    runtime = replace(ev, observation_status='RUNTIME_OBSERVED',
                      attributes={'source_sha': 'c' * 40})
    report = build_usage_matrix(replace(graph, evidence=(runtime,)), receipt,
                                ('n:t',), (UsageRelation('USES', 'POSSIBLE'),),
                                required_paths=('src/item.py',))
    assert 'UNVERIFIED_RUNTIME_REVISION' in report.rows[0].blockers
    assert report.rows[0].screening == 'HOLD'
    assert not report.rows[0].safe_to_delete

    # A same-revision runtime witness can support a known consumer, but
    # still never proves authorization or global consumer closure.
    current = replace(runtime, attributes={'source_sha': sha})
    report = build_usage_matrix(replace(graph, evidence=(current,)), receipt,
                                ('n:t',), (UsageRelation('USES', 'POSSIBLE'),),
                                required_paths=('src/item.py',))
    assert report.rows[0].screening == 'RETAIN'
    assert not report.global_consumer_closed
    assert not report.mutation_approved


def test_missing_required_path_cannot_be_silently_ignored(git_factory):
    result, ids = scanned(git_factory)
    report = build_usage_matrix(
        result.graph, result.receipt, (ids['UnusedKernel'],), RULES,
        required_paths=PATHS + ('inputs/unscanned.i',),
        ignored_relations=IGNORED,
    )
    row = report.rows[0]
    assert row.screening == 'HOLD'
    assert 'TARGET_REQUIRED_PATHS_NOT_SCANNED' in row.blockers
    assert row.coverage.missing_required_paths == ('inputs/unscanned.i',)


@pytest.mark.parametrize("input_text", [INPUT, INPUT.replace("UsedKernel", "$" + "{KERNEL}")])
def test_batch_coverage_equals_standalone_on_complete_and_partial_scope(git_factory, input_text):
    from physics_harness.code.analysis.impact import analyze_target_coverage

    result, ids = scanned(git_factory, input_text)
    required = PATHS + ("inputs/missing.i",)
    surfaces = ("external", "runtime")
    batch = build_usage_matrix(result.graph, result.receipt, tuple(reversed(tuple(ids.values()))),
                               RULES, required_paths=required,
                               unverified_surfaces=surfaces, ignored_relations=IGNORED)
    for row in batch.rows:
        assert row.coverage == analyze_target_coverage(
            result.graph, result.receipt, row.target_id, required_paths=required,
            unverified_surfaces=surfaces)


def test_batch_coverage_preserves_self_ignored_and_isolated_evidence(git_factory):
    from physics_harness.code.analysis.impact import analyze_target_coverage

    result, ids = scanned(git_factory)
    target = ids["UsedKernel"]
    witness = result.graph.evidence[0]
    self_edge = Edge("edge:p4-self", target, target, "SELF", evidence_ids=(witness.id,))
    isolated = Node("node:p4-isolated", "symbol", "isolated")
    graph = replace(result.graph, nodes=result.graph.nodes + (isolated,),
                    edges=result.graph.edges + (self_edge,))
    rules = RULES + (UsageRelation("SELF", "SELF"),)
    targets = (target, isolated.id)
    batch = build_usage_matrix(graph, result.receipt, targets, rules,
                               required_paths=PATHS, ignored_relations=IGNORED)
    rows = {row.target_id: row for row in batch.rows}
    assert "SELF_REFERENCE_NOT_EXTERNAL_CONSUMER" in rows[target].blockers
    assert witness.id in rows[target].coverage.related_evidence_ids
    assert "TARGET_EVIDENCE_ABSENT" in rows[isolated.id].coverage.local_blockers
    assert not rows[isolated.id].references
    for row in batch.rows:
        assert row.coverage == analyze_target_coverage(
            graph, result.receipt, row.target_id, required_paths=PATHS)
    ignored = build_usage_matrix(graph, result.receipt, targets, RULES,
                                 required_paths=PATHS, ignored_relations=IGNORED + ("SELF",))
    assert tuple(row.coverage for row in ignored.rows) == tuple(row.coverage for row in batch.rows)


def test_batch_builds_graph_maps_once(git_factory, monkeypatch):
    result, ids = scanned(git_factory)
    calls = {"nodes": 0, "evidence": 0}
    original_nodes = GraphSnapshot.nodes_by_id
    original_evidence = GraphSnapshot.evidence_by_id

    def nodes(graph):
        calls["nodes"] += 1
        return original_nodes(graph)

    def evidence(graph):
        calls["evidence"] += 1
        return original_evidence(graph)

    monkeypatch.setattr(GraphSnapshot, "nodes_by_id", nodes)
    monkeypatch.setattr(GraphSnapshot, "evidence_by_id", evidence)
    assert len(matrix(result, ids).rows) == 2
    assert calls == {"nodes": 1, "evidence": 1}
