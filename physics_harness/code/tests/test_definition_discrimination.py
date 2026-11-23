"""P0 contrastive Definition CU controls; deliberately *not* human ratings."""
from __future__ import annotations

from dataclasses import replace
import math
import pytest

from libs.code_understandability.definition_metrics import NameCue
from libs.code_understandability.definition_discrimination import (
    CandidateDefinition, SignatureFacet, discriminate_definition,
)
from experiments.definition_cu_v05.measure import (
    WORD_TO_CONCEPTS, assess_from_source_report, EVIDENCE_KIND_TO_CONCEPT,
)
from physics_harness.code.analysis.definition_inference import BEHAVIOR_RULES


def definition(identifier, *concepts, control=False):
    return CandidateDefinition(
        identifier,
        tuple(SignatureFacet(k, ("source.py:5@" + "a" * 40,)) for k in concepts),
        kind="CONTRAST_CONTROL" if control else "OBSERVED",
    )


def cues(name, *, parent="code", modules=(), apis=()):
    return tuple([NameCue("name", name, 0, "folder"), NameCue("parent", parent, 1, "parent")]
                 + [NameCue("module:"+str(i), x, 2, "m.py") for i,x in enumerate(modules)]
                 + [NameCue("api:"+str(i), x, 3, "m.py:2@"+"a"*40) for i,x in enumerate(apis)])


def compare(gold, pool, name, *, parent="code", modules=(), apis=()):
    return discriminate_definition(gold, pool, cues(name,parent=parent,modules=modules,apis=apis),
                                   WORD_TO_CONCEPTS, source_reference="source.py:5@" + "a"*40)


def test_hard_negative_graph_name_ambiguous_but_context_rescues():
    pool = (definition("model", "record", "relation"),
            definition("serializer", "relation", "serialize", control=True),
            definition("analysis", "interpret", "result", control=True))
    r=compare("model",pool,"graph", modules=("node",))
    assert r.decisions[0].winning_candidates == ("model", "serializer")
    assert r.decisions[0].chosen is None
    assert r.decisions[2].chosen == "model"
    assert r.minimum_extra_cues == 1
    assert r.minimum_cue_labels == ("module:0",)
    assert r.status == "DISTINCT" and not r.human_cu_calibrated
    assert r.decisions[0].surrogate_gain_bits == pytest.approx(math.log2(3/2))


def test_short_contextual_name_can_be_legitimate():
    pool=(definition("plan", "option", "validate"),
          definition("executor", "change", "effect", control=True))
    r=compare("plan",pool,"core",parent="planning")
    assert r.decisions[0].chosen is None
    assert r.decisions[1].chosen == "plan"
    assert r.minimum_correct_tier == 1
    assert r.stable_correct_tier == 1
    assert r.minimum_extra_cues == 0
    assert r.status == "DISTINCT"


def test_misleading_name_is_wrong_then_api_context_can_rescue():
    pool=(definition("plan", "option", "validate"),
          definition("executor", "change", "effect", control=True))
    r=compare("plan",pool,"refactor",modules=("alternatives",),apis=("validate_alternative",))
    assert r.decisions[0].chosen == "executor"
    assert r.decisions[2].chosen is None  # source option vs control change
    assert r.decisions[3].chosen == "plan"
    assert r.minimum_extra_cues == 1  # one compound API cue conveys both concepts
    assert r.minimum_cue_labels == ("api:0",)
    assert r.status == "DISTINCT"


def test_unknown_words_abstain_not_false_quality_failure():
    pool=(definition("plan", "option", "validate"),
          definition("executor", "change", "effect", control=True))
    r=compare("plan",pool,"xyzzy",parent="unknown")
    assert r.status == "ABSTAIN"
    assert r.minimum_extra_cues is None
    assert all(x.surrogate_gain_bits is None for x in r.decisions)


def test_name_change_never_changes_source_definition_signature():
    pool=(definition("plan", "option", "validate"),
          definition("executor", "change", "effect", control=True))
    real=compare("plan",pool,"planning",modules=("alternatives",),apis=("validate_alternative",))
    swapped=compare("plan",pool,"execute",modules=("alternatives",),apis=("validate_alternative",))
    assert pool[0] == pool[0]  # identical immutable source signature
    assert real.name_only_correct and not swapped.name_only_correct
    assert real.final_correct and swapped.final_correct  # context can rescue both
    assert real.source_reference == swapped.source_reference


def test_wrong_semantics_are_not_called_human_information_gain():
    pool=(definition("plan", "option", "validate"),
          definition("executor", "change", "effect", control=True))
    wrong=compare("plan",pool,"execute")
    assert wrong.status == "WRONG"
    assert wrong.decisions[3].surrogate_gain_bits == pytest.approx(1.0)
    assert not wrong.human_cu_calibrated


def test_tie_does_not_claim_accuracy_or_zero_extra_context():
    pool=(definition("a", "relation", "record"),
          definition("b", "relation", "serialize", control=True))
    r=compare("a",pool,"graph")
    assert r.status == "AMBIGUOUS"
    assert r.stable_correct_tier is None
    assert r.minimum_extra_cues is None
    assert r.minimum_correct_tier is None
    assert r.decisions[3].margin_to_next == 0


def test_finite_cue_dp_ignores_duplicated_information_without_counting_it():
    pool=(definition("a", "relation", "record"),
          definition("b", "relation", "serialize", control=True))
    r=compare("a",pool,"graph",modules=("node", "node", "edge"))
    assert r.minimum_extra_cues == 1
    assert r.minimum_cue_labels == ("module:0",)


def test_invalid_or_unproven_reference_rejected():
    pool=(definition("a", "relation"),definition("b", "record",control=True))
    with pytest.raises(ValueError,match="UNSUPPORTED_DISCRIMINATION_REFERENCE"):
        compare("absent",pool,"graph")
    with pytest.raises(ValueError,match="REFERENCE_MUST_BE_OBSERVED"):
        compare("b",pool,"graph")
    with pytest.raises(ValueError,match="DUPLICATE_DISCRIMINATION_CANDIDATE"):
        compare("a",(pool[0],pool[0]),"graph")
    with pytest.raises(ValueError,match="CUE_BUDGET_OR_DUPLICATE"):
        discriminate_definition("a",pool,(NameCue("name","graph",0,"x"),
                                          NameCue("name","node",0,"x")),WORD_TO_CONCEPTS,
                                source_reference="x")
    with pytest.raises(ValueError,match="FACET_EVIDENCE_REQUIRED"):
        SignatureFacet("record",())


def test_source_roles_are_not_derived_from_the_current_name():
    def source_rows():
        rows=[]
        for i,(role,needed,_) in enumerate(BEHAVIOR_RULES):
            refs=[{"kind":k,"source_ref":f"pkg/t{i}/file{i}.py:{j+1}@"+"a"*40}
                  for j,k in enumerate(needed)]
            rows.append({"target":f"t{i}","folder":f"pkg/t{i}","definition":role,
                         "python_source_scope":"COMPLETE_TRACKED_PYTHON_ONLY",
                         "source_evidence":refs,"scanned_files":1})
        return rows
    rows=source_rows()
    report={"schema_version":"0.4","source_provider":"GIT_TREE_EXACT_BLOB",
            "exact_source_revision":"a"*40,"readme_used":False,
            "target_name_used_for_definition_inference":False,"results":rows}
    names=["graph","diagnostics","analysis","refactor","verification"]
    public={f"t{i}":cues(n,modules=("node",),apis=("EvidenceReceipt",))
            for i,n in enumerate(names)}
    result=assess_from_source_report(report,public)
    assert result["reference_definitions"]==5
    assert result["candidate_count"]==10
    assert not result["human_cu_calibrated"]
    assert not result["automatic_change_authorized"]
    assert {x["source_role"] for x in result["cases"]}=={r[0] for r in BEHAVIOR_RULES}
    # Masking evaluated *names* leaves the name-independent source reference untouched.
    public["t0"] = cues("nonsense",modules=("node",),apis=("EvidenceReceipt",))
    mutated=assess_from_source_report(report,public)
    assert [x["source_role"] for x in result["cases"]] == [x["source_role"] for x in mutated["cases"]]


def test_reject_leaked_readme_in_source_role_receipt():
    report={"schema_version":"0.4","source_provider":"GIT_TREE_EXACT_BLOB",
            "exact_source_revision":"a"*40,"readme_used":True,
            "target_name_used_for_definition_inference":False,"results":[]}
    with pytest.raises(ValueError,match="NAME_LEAKAGE"):
        assess_from_source_report(report,{})


def test_later_noisy_context_can_undo_earlier_correct_discrimination():
    pool=(definition("analysis", "interpret", "result"),
          definition("negative", "relation", "interpret",control=True))
    r=compare("analysis",pool,"analysis", modules=("result",), apis=("GraphDiff",))
    assert r.decisions[2].chosen == "analysis"
    assert r.decisions[3].chosen is None
    assert r.minimum_correct_tier == 2
    assert r.stable_correct_tier is None
    assert r.status == "AMBIGUOUS"
    assert r.minimum_extra_cues == 1  # best-case selective disclosure, not automatic progressive correctness


def test_duplicate_meaning_in_competition_forces_abstention():
    # Even an exact name cannot distinguish behavior-identical contracts.
    pool = (definition("observed", "relation", "record"),
            definition("duplicate", "relation", "record", control=True))
    r = compare("observed", pool, "graph", modules=("node",))
    assert r.status == "AMBIGUOUS"
    assert r.minimum_extra_cues is None
    assert r.decisions[3].winning_candidates == ("duplicate", "observed")


def test_invalid_source_witness_blocks_forged_reference():
    from experiments.definition_cu_v05.measure import _candidate_from_source_row
    bad={"folder":"physics_harness/code/graph",
         "python_source_scope":"COMPLETE_TRACKED_PYTHON_ONLY",
         "definition":"GRAPH_MODEL",
         "source_evidence": [{"kind":"FROZEN_RECORD","source_ref":"other.py:2@"+"a"*40},
                             {"kind":"RELATIONAL_FIELDS","source_ref":"graph.py:2@"+"a"*40}]}
    with pytest.raises(ValueError,match="UNBOUND_SOURCE_WITNESS"):
        _candidate_from_source_row(bad)
