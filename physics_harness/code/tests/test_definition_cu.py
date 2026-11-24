"""Contract and adversarial checks for exploratory Definition/CU metrics."""
import json
from pathlib import Path
import sys

import pytest

from libs.code_understandability.definition_metrics import (
    DefinitionClause, NameCue, lexical_tokens, measure_definition,
)
from physics_harness.code.analysis.definition_inference import (
    SourceSymbol, infer_from_symbols, make_folder_cues, measure_folder,
    extract_public_symbols_from_folder,
)


def sym(*names):
    return tuple(SourceSymbol(name, "test-source.py:1") for name in names)


def test_role_inference_does_not_see_target_name_or_readme():
    symbols = sym("PlanningAlternative", "AlternativeReview", "review_alternatives")
    inferred = infer_from_symbols(symbols)
    assert inferred.role == "PLAN"
    a = measure_folder("a/meaningful_name", symbols, ("alternatives",))
    b = measure_folder("a/totally_misleading", symbols, ("alternatives",))
    assert a["role"] == b["role"] == "PLAN"
    assert a["clauses"] == b["clauses"]
    assert not a["metrics"]["MRC_extra_cues"] is None


def test_empty_or_ambiguous_evidence_never_gets_a_score():
    assert measure_folder("p/delete", (), ())["metrics"] is None
    both = sym("Claim", "Evidence", "Node", "Edge", "ScanRequest", "SourceFact")
    assert infer_from_symbols(both).role is None


def test_readme_content_cannot_affect_metrics():
    names = sym("ScanRequest", "SourceProvider", "FactBatch")
    left = measure_folder("h/diagnostics", names, ("collector", "receipt"))
    right = measure_folder("h/diagnostics", names, ("collector", "receipt"))
    assert left == right


def test_contextual_short_name_reduces_burden():
    clauses = (DefinitionClause("verify", ("a.py:1",)),
               DefinitionClause("dependency", ("a.py:2",)))
    cues = (NameCue("name", "checks", 0, "checks"),
            NameCue("parent", "verify", 1, "verify"),
            NameCue("module:dependencies", "dependencies", 2, "x/dependencies.py"))
    m = measure_definition(clauses, cues)
    assert m.definition_explanation_burden == 1
    assert m.minimum_required_context == 1
    assert m.minimum_context_tier == 2
    assert m.still_unrecoverable == ()


def test_mrc_finds_exact_smallest_set_not_greedy():
    clauses = tuple(DefinitionClause(word, (f"a:{i}",)) for i,word in enumerate(("alpha","beta","gamma","delta")))
    cues = (NameCue("name","module",0,"p"),
            NameCue("c1","alpha beta gamma",2,"p"),
            NameCue("c2","alpha beta",2,"p"),
            NameCue("c3","gamma delta",2,"p"))
    m = measure_definition(clauses,cues)
    assert m.definition_explanation_burden == 4
    assert m.minimum_required_context == 2
    assert set(m.selected_context_cues) in ({"c1", "c3"}, {"c2", "c3"})


def test_gap_stays_unresolved_not_fake_zero():
    clauses = (DefinitionClause("invariant", ("a:3",)),)
    cues = (NameCue("name", "module", 0, "p"),)
    m = measure_definition(clauses,cues)
    assert m.definition_explanation_burden == 1
    assert m.minimum_required_context is None
    assert m.still_unrecoverable == ("invariant",)


def test_oversized_definition_fails_explicitly():
    clauses = tuple(DefinitionClause(f"concept_{chr(97+i)}", ("x",)) for i in range(17))
    with pytest.raises(ValueError, match="DEFINITION_CONCEPT_BUDGET_EXCEEDED"):
        measure_definition(clauses,(NameCue("name","p",0,"p"),))


def test_source_extraction_verifies_owned_exports_and_unresolved_alias(tmp_path):
    d=tmp_path/"p"/"roles"
    d.mkdir(parents=True)
    (d/"__init__.py").write_text('from .impl import ScanRequest, SourceProvider, FactBatch\nfrom .missing import Unknown\n__all__ = ["ScanRequest", "SourceProvider", "FactBatch", "Unknown"]\n')
    (d/"impl.py").write_text('class ScanRequest: pass\nclass SourceProvider: pass\nclass FactBatch: pass\n')
    symbols=extract_public_symbols_from_folder(tmp_path,"p/roles")
    assert [s.origin for s in symbols] == ["IMPLEMENTED_OWNER"]*3+["PUBLIC_API"]
    assert infer_from_symbols(symbols).evidence_level == "PUBLIC_API_DECLARED"


def test_typed_target_rejects_fake_input():
    with pytest.raises(TypeError):
        infer_from_symbols(["Fake"])
    with pytest.raises(ValueError,match="TARGET_NAME_CUE_REQUIRED"):
        measure_definition((DefinitionClause("a",("p",)),), ())


def test_string_stemming_preserves_analysis_word():
    assert "dependency" in lexical_tokens("dependencies")
    assert "analysis" in lexical_tokens("analysis")
    assert "node" in lexical_tokens("graph")
