"""Contrastive Definition identification from separately sourced concept cues.

This computes **model** predictions under a caller-declared ontology. It does
not evaluate human code comprehension or certify the ontology as correct.
Definition concepts and their witnesses must originate independently from the
name/cue matching stage. Abstention is a first-class outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import log2
from collections.abc import Mapping
import re

from .definition_metrics import NameCue

RULE_VERSION = "contrastive-definition-v0.5"
WORD_PATTERN = re.compile(r"[a-z]+")
CONCEPT_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")
MAX_FACETS = 16
MAX_CUES = 80


def _tokens(value: str) -> frozenset[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return frozenset(WORD_PATTERN.findall(value.lower()))


@dataclass(frozen=True)
class SignatureFacet:
    concept: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.concept, str) or not CONCEPT_PATTERN.fullmatch(self.concept):
            raise ValueError("INVALID_DISCRIMINATION_CONCEPT")
        if (not isinstance(self.evidence_ids, tuple) or not self.evidence_ids
                or any(not isinstance(e, str) or not e.strip() for e in self.evidence_ids)):
            raise ValueError("DISCRIMINATION_FACET_EVIDENCE_REQUIRED")


@dataclass(frozen=True)
class CandidateDefinition:
    identifier: str
    facets: tuple[SignatureFacet, ...]
    kind: str = "OBSERVED"  # OBSERVED or CONTRAST_CONTROL

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("INVALID_DISCRIMINATION_CANDIDATE")
        if self.kind not in {"OBSERVED", "CONTRAST_CONTROL"}:
            raise ValueError("INVALID_DISCRIMINATION_CANDIDATE_KIND")
        if (not isinstance(self.facets, tuple) or not self.facets
                or not all(isinstance(x, SignatureFacet) for x in self.facets)
                or len(set(f.concept for f in self.facets)) != len(self.facets)):
            raise ValueError("UNIQUE_DISCRIMINATION_FACETS_REQUIRED")


@dataclass(frozen=True)
class TierDecision:
    tier: int
    winning_candidates: tuple[str, ...]
    chosen: str | None
    top_score: int
    margin_to_next: int | None
    surrogate_gain_bits: float | None
    # This is log2(candidate_count / top_tie_count), under a *model-only*
    # uniform shortlist assumption. It is NOT observed human information gain.


@dataclass(frozen=True)
class DefinitionDiscrimination:
    benchmark_target: str
    source_reference: str
    decisions: tuple[TierDecision, ...]
    minimum_correct_tier: int | None
    stable_correct_tier: int | None
    minimum_extra_cues: int | None
    minimum_cue_labels: tuple[str, ...]
    final_correct: bool
    name_only_correct: bool
    status: str
    rule_version: str = RULE_VERSION
    human_cu_calibrated: bool = False


def _validate(benchmark_target: str, candidates: tuple[CandidateDefinition, ...],
              cues: tuple[NameCue, ...], ontology: Mapping[str, tuple[str, ...]]) -> None:
    if not isinstance(candidates, tuple) or len(candidates) < 2 or not all(
        isinstance(x, CandidateDefinition) for x in candidates
    ):
        raise ValueError("DISCRIMINATION_COMPETING_DEFINITIONS_REQUIRED")
    if len({x.identifier for x in candidates}) != len(candidates):
        raise ValueError("DUPLICATE_DISCRIMINATION_CANDIDATE")
    if benchmark_target not in {x.identifier for x in candidates}:
        raise ValueError("UNSUPPORTED_DISCRIMINATION_REFERENCE")
    if next(c for c in candidates if c.identifier == benchmark_target).kind != "OBSERVED":
        raise ValueError("DISCRIMINATION_REFERENCE_MUST_BE_OBSERVED")
    if not isinstance(cues, tuple) or not all(isinstance(c, NameCue) for c in cues):
        raise TypeError("DISCRIMINATION_CUES_REQUIRED")
    if len(cues) > MAX_CUES or len({c.label for c in cues}) != len(cues):
        raise ValueError("DISCRIMINATION_CUE_BUDGET_OR_DUPLICATE")
    if sum(c.tier == 0 for c in cues) != 1:
        raise ValueError("EXACTLY_ONE_TARGET_NAME_REQUIRED")
    if not isinstance(ontology, Mapping):
        raise TypeError("DISCRIMINATION_ONTOLOGY_REQUIRED")
    known = {f.concept for c in candidates for f in c.facets}
    if len(known) > MAX_FACETS:
        raise ValueError("DISCRIMINATION_FACET_BUDGET_EXCEEDED")
    for word, mapped in ontology.items():
        if (not isinstance(word, str) or not CONCEPT_PATTERN.fullmatch(word)
                or not isinstance(mapped, tuple) or not mapped
                or not all(isinstance(v, str) and CONCEPT_PATTERN.fullmatch(v) for v in mapped)):
            raise ValueError("INVALID_DISCRIMINATION_ONTOLOGY")


def _cue_facets(cue: NameCue, ontology: Mapping[str, tuple[str, ...]]) -> frozenset[str]:
    return frozenset(facet for token in _tokens(cue.text)
                     for facet in ontology.get(token, ()))


def _decision(tier: int, active: frozenset[str],
              candidates: tuple[CandidateDefinition, ...]) -> TierDecision:
    scores = [(sum(f.concept in active for f in candidate.facets), candidate.identifier)
              for candidate in candidates]
    best = max(n for n, _ in scores)
    if best == 0:
        return TierDecision(tier, (), None, 0, None, None)
    winners = tuple(sorted(identifier for count, identifier in scores if count == best))
    less = [count for count, _ in scores if count < best]
    margin = best - max(less) if less else 0
    return TierDecision(
        tier, winners, winners[0] if len(winners) == 1 else None, best, margin,
        log2(len(candidates) / len(winners)),
    )


def discriminate_definition(
    benchmark_target: str,
    candidates: tuple[CandidateDefinition, ...],
    cues: tuple[NameCue, ...],
    ontology: Mapping[str, tuple[str, ...]],
    *, source_reference: str,
) -> DefinitionDiscrimination:
    """Match disclosed *names* to source-derived candidate signatures.

    The reference is supplied independently by the evidence evaluator. No
    candidate's human-readable label is used as an input feature. Cost counts
    additional distinct name cues, not LOC or human search time. Min-cue DP is
    exact within a bounded finite union-of-facets universe.
    """
    _validate(benchmark_target, candidates, cues, ontology)
    if not isinstance(source_reference, str) or not source_reference.strip():
        raise ValueError("DISCRIMINATION_REFERENCE_EVIDENCE_REQUIRED")
    cue_features = {c.label: _cue_facets(c, ontology) for c in cues}
    decisions: list[TierDecision] = []
    for tier in range(4):
        visible = frozenset().union(*(cue_features[c.label] for c in cues if c.tier <= tier))
        decisions.append(_decision(tier, visible, candidates))
    earliest = next((d.tier for d in decisions if d.chosen == benchmark_target), None)
    stable_tier = next((i for i in range(4) if all(
        d.chosen == benchmark_target for d in decisions[i:]
    )), None)

    base = frozenset().union(*(cue_features[c.label] for c in cues if c.tier <= 1))
    extra = tuple(sorted((c for c in cues if c.tier >= 2), key=lambda c: (c.tier, c.label)))
    facets = sorted({f.concept for c in candidates for f in c.facets})
    index = {key: 1 << i for i, key in enumerate(facets)}
    base_mask = sum(index[k] for k in base if k in index)
    # DP over unique semantic coverage masks: avoids enumerating 2**API-cues.
    # For identical masks, retain the cheapest plan with deterministic tie-break.
    plans: dict[int, tuple[NameCue, ...]] = {0: ()}

    def rank(plan: tuple[NameCue, ...]) -> tuple:
        return (len(plan), max((c.tier for c in plan), default=0), tuple(c.label for c in plan))

    for c in extra:
        bits = sum(index[k] for k in cue_features[c.label] if k in index)
        if not bits:
            continue
        next_plans = dict(plans)
        for mask, prev in plans.items():
            new_mask = mask | bits
            proposal = prev + (c,)
            if new_mask not in next_plans or rank(proposal) < rank(next_plans[new_mask]):
                next_plans[new_mask] = proposal
        plans = next_plans
    valid = []
    for mask, plan in plans.items():
        tokens = frozenset(key for key, bit in index.items() if (base_mask | mask) & bit)
        if _decision(3, tokens, candidates).chosen == benchmark_target:
            valid.append(plan)
    best_plan = min(valid, key=rank) if valid else None
    last = decisions[-1]
    status = ("DISTINCT" if last.chosen == benchmark_target else
              "WRONG" if last.chosen is not None else
              "ABSTAIN" if last.top_score == 0 else "AMBIGUOUS")
    return DefinitionDiscrimination(
        benchmark_target, source_reference, tuple(decisions), earliest, stable_tier,
        len(best_plan) if best_plan is not None else None,
        tuple(c.label for c in best_plan or ()),
        last.chosen == benchmark_target,
        decisions[0].chosen == benchmark_target,
        status,
    )
