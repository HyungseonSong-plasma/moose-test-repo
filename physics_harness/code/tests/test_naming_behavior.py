"""P0: a matching signature or body shape is not semantic compatibility."""
from __future__ import annotations

from dataclasses import replace

import pytest

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.tests.test_naming_boundary import history, case, bindings, extract_option, PATH, DEST, git
from physics_harness.code.tests.test_naming_candidate import third_commit, placements
from physics_harness.code.verification.naming_behavior import (
    _ast_symbols, _projection, _hazards, verify_naming_behavior_projection,
)


def scan(history, *, candidate=None, dest=None, mapped=None, opt=None):
    root, before, baseline = history
    if candidate is None:
        candidate = third_commit(history, dest_source=dest or
            "class PythonProvider:\n    def supports(self, value): return True\n\ndef python_decode(source):\n    return source\n")
    return verify_naming_behavior_projection(case(before, baseline),
        opt or extract_option(), GitSourceProvider(root), bindings(),
        candidate, PATH, mapped or placements())


def test_same_ast_body_requires_context_and_behavior_replay(history):
    r = scan(history)
    assert r.status == "HOLD"
    assert len(r.comparisons) == 3
    assert all(x.body_equal for x in r.comparisons)
    assert "MODULE_RESOLUTION_CHANGED" in r.unresolved
    assert "INDEPENDENT_BEFORE_AFTER_EXECUTABLE_TEST_REPLAY" in r.required_checks
    assert not r.semantic_compatibility_proven and not r.mutation_approved


def test_same_signature_changed_return_value_requires_behavior_replay(history):
    r = scan(history, dest="class PythonProvider:\n    def supports(self, value): return True\n\ndef python_decode(source):\n    return 42\n")
    assert r.status == "HOLD"
    changed = [s for s in r.comparisons if s.responsibility_id == "python"]
    assert len(changed) == 1 and not changed[0].body_equal
    assert any(x.startswith("EXECUTABLE_AST_BODY_CHANGED") for x in r.unresolved)


def test_same_signature_replacing_call_with_side_effect_is_detected(history):
    r = scan(history, dest="class PythonProvider:\n    def supports(self, value): return True\n\ndef python_decode(source):\n    open('/tmp/leak', 'w').write('x')\n    return source\n")
    assert r.status == "HOLD"
    assert any(x.startswith("EXECUTABLE_AST_BODY_CHANGED") for x in r.unresolved)


def test_identical_body_new_import_environment_is_not_certified(history):
    r = scan(history, dest="import sys\n\nclass PythonProvider:\n    def supports(self, value): return True\n\ndef python_decode(source):\n    return source\n")
    assert "MODULE_IMPORT_ENVIRONMENT_UNVERIFIED" in r.unresolved
    assert all(x.body_equal for x in r.comparisons)


def test_worktree_mutation_cannot_change_committed_body_evidence(history):
    root, _, _ = history
    candidate = third_commit(history)
    a = scan(history, candidate=candidate)
    (root / DEST).write_text("def python_decode(x): return 9000\n")
    b = scan(history, candidate=candidate)
    assert a == b


def test_failed_structural_candidate_does_not_claim_body_match(history):
    root, _, baseline = history
    r = scan(history, candidate=baseline)
    assert r.status == "REJECTED"
    assert not r.comparisons
    assert "STRUCTURAL_CANDIDATE_NOT_VERIFIED" in r.unresolved


def test_missing_extraction_symbol_prevents_behavior_conclusion(history):
    r = scan(history, dest="class PythonProvider: pass\n")
    assert r.status == "REJECTED"
    assert not r.comparisons


def test_non_ancestral_candidate_is_rejected(history):
    root,before,baseline = history
    r=scan(history,candidate=before)
    assert r.status == "REJECTED"


def test_body_projection_does_not_depend_on_function_name():
    before,_ = _ast_symbols(b"def old(x):\n    return x + 1\n", "old.py")
    after,_ = _ast_symbols(b"def new(x):\n    return x + 1\n", "new.py")
    assert _projection(before["old.py::function:old"]) == _projection(after["new.py::function:new"])


def test_same_body_projection_detects_value_changes():
    before,_ = _ast_symbols(b"def f(x): return x + 1\n", "old.py")
    after,_ = _ast_symbols(b"def f(x): return x + 2\n", "old.py")
    assert _projection(before["old.py::function:f"]) != _projection(after["old.py::function:f"])


def test_reflection_and_global_state_hazards_are_visible():
    nodes,tree = _ast_symbols(b"import os\ndef f(x):\n    global state\n    return getattr(x,'value')\n", "a.py")
    hazards = _hazards(nodes["a.py::function:f"],tree)
    assert "GLOBAL_OR_NONLOCAL_STATE" in hazards
    assert "REFLECTION_OR_DYNAMIC_CALL:getattr" in hazards
    assert "MODULE_IMPORT_ENVIRONMENT_UNVERIFIED" in hazards


def test_ast_parse_handles_async_method():
    symbols,_=_ast_symbols(b"class Collector:\n    async def collect(self, source):\n        return source\n", "a.py")
    assert "a.py::class:Collector" in symbols
    assert "a.py::method:Collector.collect" in symbols


def test_budget_validation(history):
    root,_,_=history
    with pytest.raises(ValueError, match="INVALID_BEHAVIOR_SOURCE_BUDGET"):
        verify_naming_behavior_projection(case(history[1],history[2]), extract_option(),
            GitSourceProvider(root), bindings(), history[2], PATH, (), max_source_bytes=0)


def test_unchanged_body_cannot_prove_same_module_global_resolution():
    before, pre_tree = _ast_symbols(b"VALUE = 1\ndef get(): return VALUE\n", "a.py")
    after, post_tree = _ast_symbols(b"VALUE = 2\ndef get(): return VALUE\n", "a.py")
    assert _projection(before["a.py::function:get"]) == _projection(after["a.py::function:get"])
    assert "MODULE_INITIALIZATION_CONTEXT_UNVERIFIED" in _hazards(after["a.py::function:get"],post_tree)


def test_changed_method_body_detected_inside_class_projection():
    before,_ = _ast_symbols(b"class C:\n    def f(self): return 1\n", "a.py")
    after,_ = _ast_symbols(b"class C:\n    def f(self): return 2\n", "a.py")
    assert _projection(before["a.py::class:C"]) != _projection(after["a.py::class:C"])
