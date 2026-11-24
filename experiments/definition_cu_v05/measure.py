"""v0.5 contrastive naming benchmark over v0.4 Git-source behavior receipts.

Target roles come ONLY from prior name-blind source/behavior rules. Name cues
come from independently declared visible context. The lexicon is hand-curated,
not learned or calibrated with human choices; do not turn rates into CU gates.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path

from libs.code_understandability.definition_metrics import NameCue
from libs.code_understandability.definition_discrimination import (
    CandidateDefinition, SignatureFacet, discriminate_definition, RULE_VERSION,
)
from physics_harness.code.analysis.definition_inference import BEHAVIOR_RULES
from experiments.definition_cu_v04.measure import (
    ROOT, TARGETS, _public_cues, _under, measure_repository as measure_v04,
)

# This is an explicit, preregistered **semantic hypothesis lexicon**. It is
# not an empirically learned semantic model; no role label is a lookup key.
# It is deliberately shared across all targets and controls without reweighting.
ONTOLOGY_VERSION = "contrastive-concepts-v0.5-precalibration"
WORD_TO_CONCEPTS: dict[str, tuple[str, ...]] = {
    "graph": ("relation",), "node": ("record",), "edge": ("relation",),
    "evidence": ("evidence",), "fact": ("evidence",),
    "snapshot": ("record",), "model": ("record",),
    "diagnostics": ("observe",), "diagnostic": ("observe",),
    "collect": ("evidence",), "collector": ("evidence",), "collection": ("evidence",),
    "parse": ("parse",), "parser": ("parse",), "ast": ("parse",),
    "source": ("source",), "code": ("source",),
    "analysis": ("interpret",), "analyze": ("interpret",), "impact": ("result",),
    "result": ("result",), "assessment": ("result",),
    "review": ("validate",), "alternative": ("option",), "alternatives": ("option",),
    "planning": ("option",), "plan": ("option",), "validate": ("validate",),
    "refactor": ("change",), "change": ("change",), "execute": ("effect",),
    "execution": ("effect",), "write": ("effect",),
    "verification": ("provenance",), "verify": ("provenance",),
    "receipt": ("receipt",), "dependency": ("provenance",),
    "export": ("serialize",), "serialize": ("serialize",),
    "format": ("format",), "log": ("log",),
}

# Feature names describe observation *kinds*, not target names. They are
# source-side signatures, not lexical entailment from an API/class label.
EVIDENCE_KIND_TO_CONCEPT = {
    "FROZEN_RECORD": "record",
    "RELATIONAL_FIELDS": "relation",
    "SOURCE_PARSE": "parse",
    "GRAPH_FACT_CONSTRUCTION": "evidence",
    "GRAPH_TRAVERSAL": "interpret",
    "ANALYSIS_RESULT": "result",
    "OPTIONS_ITERATION": "option",
    "OPTION_VALIDATION": "validate",
    "PROVENANCE_COMPARISON": "provenance",
    "VERIFICATION_RESULT": "receipt",
}

# Hard negatives are distinct conceptual responsibilities, NOT existing
# repository entities. They must remain tagged synthetic in the assessment.
CONTRASTS = {
    "CONTROL_RELATION_INTERPRETATION": ("relation", "interpret"),
    "CONTROL_SOURCE_PARSER_ONLY": ("parse", "format"),
    "CONTROL_CHANGE_EXECUTION": ("change", "effect"),
    "CONTROL_RELATION_SERIALIZATION": ("relation", "serialize"),
    "CONTROL_PROVENANCE_LOGGING": ("provenance", "log"),
}


def _candidate_from_source_row(row: dict) -> CandidateDefinition | None:
    """Freeze only the witness kinds needed by a previously inferred role.

    Neither the target directory name nor public API labels are used here.
    Evidence refs are exact path:line@blob strings from source scanning.
    """
    role = row.get("definition")
    if not role or row.get("python_source_scope") != "COMPLETE_TRACKED_PYTHON_ONLY":
        return None
    matches = [(required, clauses) for label, required, clauses in BEHAVIOR_RULES if label == role]
    if len(matches) != 1:
        return None
    needed, _ = matches[0]
    witnesses = row.get("source_evidence", ())
    facets = []
    for kind in needed:
        concept = EVIDENCE_KIND_TO_CONCEPT.get(kind)
        refs = tuple(sorted({w["source_ref"] for w in witnesses if w["kind"] == kind}))
        if not concept or not refs:
            return None
        if any(not ref.startswith(row["folder"] + "/") or not re.fullmatch(
            r"[^@]+:[1-9][0-9]*@[0-9a-f]{40}", ref
        ) for ref in refs):
            raise ValueError("DISCRIMINATION_UNBOUND_SOURCE_WITNESS")
        facets.append(SignatureFacet(concept, refs))
    if len({f.concept for f in facets}) != len(facets):
        return None
    return CandidateDefinition(role, tuple(facets))


def _controls() -> tuple[CandidateDefinition, ...]:
    return tuple(CandidateDefinition(
        name, tuple(SignatureFacet(c, (f"synthetic-control:{name}:{c}",)) for c in facets),
        kind="CONTRAST_CONTROL",
    ) for name, facets in sorted(CONTRASTS.items()))


def assess_from_source_report(v04: dict, public_cues: dict[str, tuple[NameCue, ...]]) -> dict:
    """Compute every target against the SAME observed+control definitions."""
    if v04.get("schema_version") != "0.4" or v04.get("source_provider") != "GIT_TREE_EXACT_BLOB":
        raise ValueError("CONTRASTIVE_SOURCE_RECEIPT_REQUIRED")
    if v04.get("readme_used") is not False or v04.get("target_name_used_for_definition_inference") is not False:
        raise ValueError("CONTRASTIVE_NAME_LEAKAGE")
    rows = v04["results"]
    actual = tuple(c for row in rows if (c := _candidate_from_source_row(row)) is not None)
    if len({c.identifier for c in actual}) != len(actual):
        raise ValueError("DUPLICATE_CONTRASTIVE_OBSERVED_ROLE")
    candidates = actual + _controls()
    summary = []
    for row in rows:
        label = row["target"]
        candidate = _candidate_from_source_row(row)
        if candidate is None:
            summary.append({"target": label, "source_role": row.get("definition"),
                            "status": "NO_INDEPENDENT_SOURCE_REFERENCE", "assessment": None})
            continue
        cues = public_cues[label]
        witness = candidate.facets[0].evidence_ids[0]
        evaluated = discriminate_definition(
            candidate.identifier, candidates, cues, WORD_TO_CONCEPTS,
            source_reference=witness,
        )
        # Name-only substitution controls keep exactly the SAME inferred role,
        # reference witness, parent/modules/API. Only the target label changes.
        name = next(c for c in cues if c.tier == 0)
        swapped = next(t for t in TARGETS if t != name.text and t != "delete")
        def with_name(replacement: str) -> tuple[NameCue, ...]:
            return tuple(NameCue(c.label, replacement, c.tier, c.source_ref)
                         if c.tier == 0 else c for c in cues)
        swapped_result = discriminate_definition(candidate.identifier, candidates,
                                                with_name(swapped), WORD_TO_CONCEPTS,
                                                source_reference=witness)
        blank_result = discriminate_definition(candidate.identifier, candidates,
                                              with_name("unlabelled"), WORD_TO_CONCEPTS,
                                              source_reference=witness)
        summary.append({
            "target": label, "source_role": candidate.identifier,
            "source_facets": [asdict(x) for x in candidate.facets],
            "status": evaluated.status,
            "assessment": asdict(evaluated),
            "counterfactual_names": {
                "original": name.text, "substituted": swapped,
                "swapped_name_only_correct": swapped_result.name_only_correct,
                "swapped_final_correct": swapped_result.final_correct,
                "blank_name_only_correct": blank_result.name_only_correct,
                "blank_final_correct": blank_result.final_correct,
                "source_role_invariant": True,
            },
        })
    eligible = [r for r in summary if r["assessment"] is not None]
    return {
        "schema_version": "0.5", "source_revision": v04["exact_source_revision"],
        "source_provider": "GIT_TREE_EXACT_BLOB",
        "source_python_scope": "tracked production python under bounded code folders",
        "source_files": sum(r["scanned_files"] for r in rows),
        "name_readme_used_in_definition_inference": False,
        "ontology_version": ONTOLOGY_VERSION, "discriminator_version": RULE_VERSION,
        "reference_kind": "behavior_rules_source_proxy_NOT_independent_human_ground_truth",
        "reference_definitions": len(actual), "synthetic_contrast_definitions": len(CONTRASTS),
        "candidate_count": len(candidates), "cases": summary,
        "metrics": {
            "DDA_source_reference_proxy_name_only": sum(r["assessment"]["name_only_correct"] for r in eligible) / len(eligible) if eligible else None,
            "DDA_source_reference_proxy_full_context": sum(r["assessment"]["final_correct"] for r in eligible) / len(eligible) if eligible else None,
            "DDA_proxy_full_context_blank_name": sum(r["counterfactual_names"]["blank_final_correct"] for r in eligible) / len(eligible) if eligible else None,
            "DDA_proxy_full_context_swapped_name": sum(r["counterfactual_names"]["swapped_final_correct"] for r in eligible) / len(eligible) if eligible else None,
            "name_advantage_over_blank_count": sum(
                int(r["assessment"]["final_correct"]) - int(r["counterfactual_names"]["blank_final_correct"])
                for r in eligible),
            "name_advantage_over_swap_count": sum(
                int(r["assessment"]["final_correct"]) - int(r["counterfactual_names"]["swapped_final_correct"])
                for r in eligible),
            "eligible_cases": len(eligible),
            "distinct_final": sum(r["status"] == "DISTINCT" for r in eligible),
            "wrong_final": sum(r["status"] == "WRONG" for r in eligible),
            "ambiguous_final": sum(r["status"] == "AMBIGUOUS" for r in eligible),
            "abstain_final": sum(r["status"] == "ABSTAIN" for r in eligible),
        },
        "human_cu_calibrated": False,
        "automatic_change_authorized": False,
    }


def measure_repository(root: Path, expected_revision: str | None = None) -> dict:
    from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest
    from experiments.definition_cu_v04.measure import _public_cues

    v04 = measure_v04(root, expected_revision)
    revision = v04["exact_source_revision"]
    provider = GitSourceProvider(root)
    request = ScanRequest(repository="HyungseonSong-plasma/moose-test-repo", revision=revision,
                          includes=(ROOT + "/**",), collectors=("python_ast",))
    inventory = provider.inventory(request)
    cues = {}
    for row in v04["results"]:
        folder = row["folder"]
        selected = tuple(r for r in inventory if _under(r.path, folder))
        if selected and row.get("python_source_scope") == "COMPLETE_TRACKED_PYTHON_ONLY":
            cues[row["target"]] = _public_cues(folder, selected, provider)
    return assess_from_source_report(v04, cues)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--expected-revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = measure_repository(args.root, args.expected_revision)
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
