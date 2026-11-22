"""Evidence-bound, exploratory definition explanation/context indicators.

Measures source-derived concept recoverability under an *explicit cue protocol*.
These are neither human comprehension outcomes nor calibrated CU quality scores.
No README text is consulted here; no mutation decisions are made.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


# Generic lexical entailments. Version this vocabulary; do not learn it from
# the target under evaluation. These links are hypotheses, not human validation.
LEXICON_VERSION = "definition-lexicon-v0.2"
ENTAILMENTS = {
    "graph": ("node", "edge"),
    "analysis": ("analyze", "assess"),
    "analyze": ("analysis", "assess"),
    "assessment": ("assess",),
    "planning": ("plan",),
    "plan": ("planning",),
    "verification": ("verify",),
    "verify": ("verification",),
    "collection": ("collect",),
    "collect": ("collection",),
    "refactoring": ("refactor",),
    "diagnostic": ("diagnostics",),
}


def lexical_tokens(text: str) -> frozenset[str]:
    """Split snake_case/CamelCase without importing or executing source."""
    if not isinstance(text, str):
        raise TypeError("CUE_TEXT_REQUIRED")
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    tokens = frozenset(re.findall(r"[a-z]+", words.lower()))
    expanded = set(tokens)
    for token in tokens:
        if token.endswith("ies") and len(token) > 4:
            expanded.add(token[:-3] + "y")
        elif token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
            expanded.add(token[:-1])
    for token in tokens:
        expanded.update(ENTAILMENTS.get(token, ()))
    return frozenset(expanded)


@dataclass(frozen=True)
class DefinitionClause:
    concept: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z_]*", self.concept):
            raise ValueError("INVALID_DEFINITION_CONCEPT")
        if not self.source_refs or any(not x for x in self.source_refs):
            raise ValueError("DEFINITION_CLAUSE_REQUIRES_SOURCE")


@dataclass(frozen=True)
class NameCue:
    label: str
    text: str
    tier: int  # 0 target name, 1 parent path, 2 nearby module, 3 owned API
    source_ref: str

    def __post_init__(self) -> None:
        if not self.label or not self.text or not self.source_ref:
            raise ValueError("INCOMPLETE_NAME_CUE")
        if type(self.tier) is not int or self.tier not in range(4):
            raise ValueError("INVALID_NAME_CUE_TIER")


@dataclass(frozen=True)
class DefinitionMeasurement:
    total_concepts: int
    definition_explanation_burden: int
    explanation_burden_fraction: float | None
    unpredicted_concepts: tuple[str, ...]
    minimum_required_context: int | None  # additional cues beyond name+parent
    minimum_context_tier: int | None
    selected_context_cues: tuple[str, ...]
    still_unrecoverable: tuple[str, ...]
    lexicon_version: str = LEXICON_VERSION
    human_cu_proven: bool = False


def measure_definition(
    clauses: tuple[DefinitionClause, ...], cues: tuple[NameCue, ...],
) -> DefinitionMeasurement:
    """Calculate DEB and exact finite-cue MRC by DP on concept masks.

    DEB: concepts NOT recoverable from target name+parent path (tiers 0..1).
    MRC: minimum additional distinct allowed cues from tiers 2..3 to cover
         all remaining concepts. None if unreachable within the declared cues.
    Context costs count inspected semantic units, not tokens or source LOC.
    """
    if not isinstance(clauses, tuple) or not all(isinstance(x, DefinitionClause) for x in clauses):
        raise TypeError("DEFINITION_CLAUSES_REQUIRED")
    if not isinstance(cues, tuple) or not all(isinstance(x, NameCue) for x in cues):
        raise TypeError("NAME_CUES_REQUIRED")
    if not clauses or len({x.concept for x in clauses}) != len(clauses):
        raise ValueError("UNIQUE_DEFINITION_CLAUSES_REQUIRED")
    if len({x.label for x in cues}) != len(cues):
        raise ValueError("DUPLICATE_NAME_CUE")
    if not any(x.tier == 0 for x in cues):
        raise ValueError("TARGET_NAME_CUE_REQUIRED")
    concepts = tuple(x.concept for x in clauses)
    baseline = set().union(*(lexical_tokens(x.text) for x in cues if x.tier <= 1))
    uncovered = tuple(x for x in concepts if x not in baseline)
    if not uncovered:
        return DefinitionMeasurement(len(concepts), 0, 0.0, (), 0, 0, (), ())

    # Dynamic programming over observed concept coverage. The local definition
    # rule set is bounded; allow at most 16 clauses to avoid exponential blowup.
    if len(uncovered) > 16:
        raise ValueError("DEFINITION_CONCEPT_BUDGET_EXCEEDED")
    all_bits = (1 << len(uncovered)) - 1
    remaining = tuple(sorted((x for x in cues if x.tier >= 2), key=lambda x:(x.tier, x.label)))
    # mask -> selected cues. Tie-break by fewer cues, shallower deepest tier,
    # then stable cue labels; no nondeterministic set iteration.
    plans: dict[int, tuple[NameCue, ...]] = {0: ()}

    def rank(plan: tuple[NameCue, ...]) -> tuple:
        return (len(plan), max((x.tier for x in plan), default=0), tuple(x.label for x in plan))

    for cue in remaining:
        words = lexical_tokens(cue.text)
        bits = sum(1 << i for i, word in enumerate(uncovered) if word in words)
        if bits == 0:
            continue
        updated = dict(plans)
        for mask, plan in plans.items():
            merged = mask | bits
            candidate = plan + (cue,)
            if merged not in updated or rank(candidate) < rank(updated[merged]):
                updated[merged] = candidate
        plans = updated
    chosen = plans.get(all_bits)
    resolved_bits = all_bits if chosen is not None else max(plans, key=lambda x: (x.bit_count(), -len(plans[x])))
    return DefinitionMeasurement(
        total_concepts=len(concepts),
        definition_explanation_burden=len(uncovered),
        explanation_burden_fraction=len(uncovered)/len(concepts),
        unpredicted_concepts=uncovered,
        minimum_required_context=len(chosen) if chosen is not None else None,
        minimum_context_tier=max((x.tier for x in chosen), default=0) if chosen is not None else None,
        selected_context_cues=tuple(x.label for x in chosen or ()),
        still_unrecoverable=tuple(word for i,word in enumerate(uncovered) if not (resolved_bits & (1 << i))),
    )


@dataclass(frozen=True)
class ContextTierCoverage:
    """Cumulative lexical clauses visible at a fixed disclosure tier."""

    tier: int
    covered: tuple[str, ...]
    gained: tuple[str, ...]


@dataclass(frozen=True)
class DefinitionContextProfile:
    """Evidence-preserving disclosure profile, NOT semantic CU calibration."""

    tiers: tuple[ContextTierCoverage, ...]
    still_uncovered: tuple[str, ...]
    evidence_protocol: str = LEXICON_VERSION
    semantic_comprehension_proven: bool = False


def profile_definition_context(
    clauses: tuple[DefinitionClause, ...], cues: tuple[NameCue, ...],
) -> DefinitionContextProfile:
    """Separate name, parent, module and API gains without assigning CU quality.

    The same lexical entailment protocol as DEB/MRC is used. A zero gain can
    indicate an inadequate lexicon, not an uninformative name. No README input.
    """
    measure_definition(clauses, cues)  # canonical input contract & evidence validation
    concepts = tuple(c.concept for c in clauses)
    seen: set[str] = set()
    levels = []
    for tier in range(4):
        words = set().union(*(lexical_tokens(c.text) for c in cues if c.tier <= tier))
        observed = {x for x in concepts if x in words}
        levels.append(ContextTierCoverage(
            tier=tier,
            covered=tuple(x for x in concepts if x in observed),
            gained=tuple(x for x in concepts if x in observed and x not in seen),
        ))
        seen = observed
    return DefinitionContextProfile(
        tiers=tuple(levels),
        still_uncovered=tuple(x for x in concepts if x not in seen),
    )
