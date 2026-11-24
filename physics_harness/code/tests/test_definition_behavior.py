"""P0 cases for v0.3 name-independent static behavior evidence."""
from __future__ import annotations

import hashlib
import pytest

from physics_harness.code.analysis.definition_inference import (
    extract_behavior_witnesses, infer_from_behavior, BEHAVIOR_RULE_VERSION,
)

REVISION = "a" * 40


def scan(source: str, path: str = "sample/unit.py", revision: str = REVISION):
    raw = source.encode("utf-8")
    blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    return extract_behavior_witnesses(path, source, blob, revision)


def infer(source: str, path: str = "sample/unit.py"):
    return infer_from_behavior((scan(source, path),), required_paths=(path,))


def test_model_record_evidence_without_class_name():
    src = """from dataclasses import dataclass
@dataclass(frozen=True)
class Whatever:
    source_id: str
    target_id: str
"""
    assert infer(src).role == "GRAPH_MODEL"
    assert infer(src.replace("Whatever", "Anything")).role == "GRAPH_MODEL"


def test_collection_depends_on_parse_and_graph_construction():
    src = """import ast
from whatever import FactBatch
def make(data):
    tree = ast.parse(data)
    return FactBatch(nodes=(),edges=(),evidence=())
"""
    assert infer(src).role == "SOURCE_FACT_COLLECTION"
    assert infer(src.replace("make", "foo")).role == "SOURCE_FACT_COLLECTION"


def test_graph_analysis_requires_result_constructor():
    src = """from whatever import unfold_context, ImpactResult
def run(graph,context):
    view = unfold_context(graph,context)
    return ImpactResult(view=view)
"""
    assert infer(src).role == "GRAPH_ANALYSIS"
    assert infer("from whatever import unfold_context\ndef x(graph,c): return unfold_context(graph,c)\n").role is None


def test_option_plan_requires_iteration_and_validation():
    src = """from anything import validate_alternative
def arbitrary(context, alternatives):
    for item in alternatives:
        validate_alternative(context, item)
"""
    assert infer(src).role == "CHANGE_PLANNING"


def test_verification_requires_provenance_comparison():
    src = """from something import VerificationReceipt
def run(scope, receipt):
    if scope.revision != receipt.revision: raise ValueError('mismatch')
    return VerificationReceipt(status='FAILED')
"""
    assert infer(src).role == "SOURCE_VERIFICATION"


def test_inconsistent_blob_rejected():
    with pytest.raises(ValueError, match="BLOB_MISMATCH"):
        extract_behavior_witnesses("sample/unit.py", "x = 1\n", "b"*40, REVISION)


def test_cross_revision_not_aggregated():
    left = scan("x=1\n", "sample/a.py")
    right = scan("x=2\n", "sample/b.py", "b" * 40)
    with pytest.raises(ValueError, match="CROSS_REVISION"):
        infer_from_behavior((left,right),required_paths=(left.path,right.path))


def test_missing_scope_not_promoted():
    result = infer_from_behavior((scan("import ast\nx=ast.parse('x')\n"),),
                                 required_paths=("sample/unit.py", "sample/other.py"))
    assert result.role is None
    assert "MISSING_REQUIRED_SOURCE" in result.unknowns


def test_multiple_roles_held_ambiguous():
    src = """from dataclasses import dataclass
import ast
@dataclass(frozen=True)
class Other:
    source_id: str
    target_id: str

def f(s):
    ast.parse(s)
    return FactBatch()
"""
    assert infer(src).role is None
    assert "MULTIPLE_BEHAVIOR_ROLES" in infer(src).unknowns


def test_sink_is_not_silent_purity_proof():
    src = """import ast
def f(s, path):
    ast.parse(s)
    path.write_text(s)
    return FactBatch()
"""
    r = infer(src)
    assert r.role == "SOURCE_FACT_COLLECTION"
    assert r.status == "CANDIDATE_WITH_GAPS"
    assert "EXTERNAL_EFFECTS_REQUIRE_REVIEW" in r.unknowns


def test_dynamic_call_marks_scope_uncertain():
    src = """import ast
def f(s):
    ast.parse(s)
    getattr(s,'x')
    return FactBatch()
"""
    r = infer(src)
    assert r.status == "CANDIDATE_WITH_GAPS"
    assert any(x.startswith("DYNAMIC_OR_INDIRECT_CALL") for x in r.unknowns)


def test_unsupported_path_denied():
    with pytest.raises(ValueError, match="INVALID_PATH"):
        extract_behavior_witnesses("../escape.py", "x=1\n", "a"*40, REVISION)


def test_rules_version_stable():
    assert BEHAVIOR_RULE_VERSION == "definition-behavior-v0.3"


def test_generator_iteration_over_alternatives_is_observed():
    src = """def f(context, alternatives):
    return tuple(validate_alternative(context, item) for item in alternatives)
"""
    assert infer(src).role == "CHANGE_PLANNING"


def test_arbitrary_run_method_is_not_mistaken_for_process_launch():
    src = """import ast
def arbitrary(source, obj):
    ast.parse(source)
    obj.run()
    return FactBatch()
"""
    r = infer(src)
    assert r.role == "SOURCE_FACT_COLLECTION"
    assert "EXTERNAL_EFFECTS_REQUIRE_REVIEW" not in r.unknowns


def test_analysis_result_ids_do_not_imply_graph_relation_ownership():
    src = """from dataclasses import dataclass
@dataclass(frozen=True)
class TargetReport:
    target_id: str
    scope_id: str

def analyze(graph, context):
    view = unfold_context(graph, context)
    return ImpactResult(view=view)
"""
    r = infer(src)
    assert r.role == "GRAPH_ANALYSIS"
    assert "RELATIONAL_FIELDS" not in {w.kind for w in r.evidence}


def test_explicit_claim_evidence_pair_is_relation_model():
    src = """from dataclasses import dataclass
@dataclass(frozen=True)
class NameDoesNotMatter:
    subject_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
"""
    assert infer(src).role == "GRAPH_MODEL"
