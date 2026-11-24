"""Candidate-blind semantic reviewer handoff; no self-authenticating GPT verdict.

The two-pass protocol prevents the proposed name from anchoring the initial
responsibility interpretation. It does NOT authenticate a reviewer, establish
independence, or turn assertions into semantic proof. Those are external gates.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ..diagnostics.providers.git import GitSourceProvider
from ..refactor.naming import NamingCase, NamingOption
from .naming_boundary import ResponsibilityBinding, _declaration_nodes, verify_naming_boundary


@dataclass(frozen=True, slots=True)
class BlindedSourceExcerpt:
    symbol: str
    source_ref: str
    code: str  # untrusted Git source data; never instructions to the reviewer
    truncated: bool


@dataclass(frozen=True, slots=True)
class BlindedSemanticPacket:
    repository: str
    revision: str
    target_id: str
    target_kind: str
    excerpts: tuple[BlindedSourceExcerpt, ...]
    observed_symbol_keys: tuple[str, ...]
    unresolved: tuple[str, ...]
    # Deliberately no selected variant or suggested name; independent first pass.

    @property
    def mutation_approved(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class IndependentResponsibilityHypothesis:
    label: str
    symbol_keys: tuple[str, ...]
    positive_responsibility: str
    negative_boundary: str
    counterexample_to_this_boundary: str  # could be 'none observed' with explanation


@dataclass(frozen=True, slots=True)
class SecondPassSemanticChallenge:
    option_id: str
    disposition: str  # ACCEPT_FOR_REPLAY / CHALLENGE / HOLD
    keep_case: str
    chosen_case: str
    counterexamples: tuple[str, ...]
    review_reference: str  # externally authenticated by orchestrator, not here


@dataclass(frozen=True, slots=True)
class SemanticReviewReceipt:
    revision: str
    option_id: str
    status: str  # CHALLENGED / HOLD
    verified_symbol_coverage: tuple[str, ...]
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def independent_reviewer_authenticated(self) -> bool:
        return False

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False

    @property
    def mutation_approved(self) -> bool:
        return False


def build_blinded_semantic_packet(
    case: NamingCase, provider: GitSourceProvider,
    bindings: tuple[ResponsibilityBinding, ...], *, max_symbol_chars: int = 1600,
    max_excerpts: int = 100,
) -> BlindedSemanticPacket:
    """Reconstruct source snippets from Git without leaking the proposed name.

    A too-long snippet is flagged, not silently treated as comprehensive source.
    Source comments are *data*, including any instruction-looking text.
    """
    if type(max_symbol_chars) is not int or max_symbol_chars < 16:
        raise ValueError("INVALID_BLINDED_SNIPPET_LIMIT")
    if type(max_excerpts) is not int or max_excerpts < 1:
        raise ValueError("INVALID_BLINDED_EXCERPT_LIMIT")
    if not isinstance(provider, GitSourceProvider):
        raise TypeError("BLINDED_GIT_SOURCE_REQUIRED")
    # This option is local and does not carry any candidate-name signal.
    baseline = NamingOption("blinded-baseline", "KEEP", "Preserve observed responsibilities")
    gate = verify_naming_boundary(case, baseline, provider, bindings)
    problems = set(gate.unresolved) | set(gate.blockers)
    excerpts = []
    cache = {}
    ambiguous = {x.split(":", 1)[1] for x in gate.unresolved
                 if x.startswith("AMBIGUOUS_DECLARATION:")}
    for symbol in gate.observed_symbols[:max_excerpts]:
        try:
            if symbol.key in ambiguous:
                continue
            path, _ = symbol.key.split("::", 1)
            if path not in cache:
                source = provider.read_at_revision(case.revision, path)
                content = source.content.decode("utf-8", "strict")
                tree = ast.parse(content, filename=path)
                nodes, _ = _declaration_nodes(tree, path)
                cache[path] = (content, source.record.blob_sha, nodes)
            content, blob, nodes = cache[path]
            node = nodes.get(symbol.key)
            if node is None:
                problems.add("BLINDED_DECLARATION_NOT_FOUND:" + symbol.key)
                continue
            if symbol.source_ref != f"{path}:{node.lineno}@{blob}":
                problems.add("BLINDED_DECLARATION_ANCHOR_MISMATCH:" + symbol.key)
                continue
            code = ast.get_source_segment(content, node) or ""
            truncated = len(code) > max_symbol_chars
            if truncated:
                problems.add("BLINDED_EXCERPT_TRUNCATED:" + symbol.key)
            excerpts.append(BlindedSourceExcerpt(symbol.key, symbol.source_ref,
                                                  code[:max_symbol_chars], truncated))
        except (ValueError, UnicodeError, TypeError, SyntaxError) as exc:
            problems.add("BLINDED_EXCERPT_UNAVAILABLE:" + symbol.key + ":" + type(exc).__name__)
    if len(gate.observed_symbols) > max_excerpts:
        problems.add("BLINDED_EXCERPT_COUNT_LIMIT")
    return BlindedSemanticPacket(case.repository, case.revision, case.target_id,
                                 case.target_kind, tuple(excerpts),
                                 tuple(s.key for s in gate.observed_symbols),
                                 tuple(sorted(problems)))


def review_semantic_challenge(
    packet: BlindedSemanticPacket,
    hypotheses: tuple[IndependentResponsibilityHypothesis, ...],
    challenge: SecondPassSemanticChallenge,
    option: NamingOption,
) -> SemanticReviewReceipt:
    """Falsify incomplete/circular reviewer statements; never authenticate them.

    A separately asserted reviewer name, URL or PASS is not enough to prove
    independent review. Authentication belongs to an external trusted provider.
    """
    if not isinstance(packet, BlindedSemanticPacket) or not isinstance(option, NamingOption):
        raise TypeError("INVALID_SEMANTIC_REVIEW_INPUT")
    if not isinstance(hypotheses, tuple) or any(not isinstance(h, IndependentResponsibilityHypothesis) for h in hypotheses):
        raise TypeError("INVALID_REVIEW_HYPOTHESES")
    if not isinstance(challenge, SecondPassSemanticChallenge):
        raise TypeError("INVALID_SECOND_PASS_CHALLENGE")
    blocked = set()
    unresolved = set(packet.unresolved)
    observed = set(packet.observed_symbol_keys)
    covered = set()
    for h in hypotheses:
        if not (h.label.strip() and h.symbol_keys and h.positive_responsibility.strip()
                and h.negative_boundary.strip() and h.counterexample_to_this_boundary.strip()):
            blocked.add("REVIEW_HYPOTHESIS_MISSING_POSITIVE_NEGATIVE_OR_COUNTEREXAMPLE")
        if len(set(h.symbol_keys)) != len(h.symbol_keys):
            blocked.add("REVIEW_DUPLICATE_SYMBOL_BINDING")
        if set(h.symbol_keys) - observed:
            blocked.add("REVIEW_REFERENCES_UNKNOWN_SOURCE_SYMBOL")
        covered.update(s for s in h.symbol_keys if s in observed)
    if set(packet.observed_symbol_keys) - covered:
        unresolved.add("REVIEW_DID_NOT_ADDRESS_ALL_OBSERVED_DECLARATIONS")
    if challenge.option_id != option.id:
        blocked.add("SECOND_PASS_FOR_DIFFERENT_OPTION")
    if challenge.disposition not in {"ACCEPT_FOR_REPLAY", "CHALLENGE", "HOLD"}:
        blocked.add("INVALID_SECOND_PASS_DECISION")
    if not challenge.keep_case.strip() or not challenge.chosen_case.strip():
        blocked.add("SECOND_PASS_MISSING_KEEP_AND_SELECTED_COMPARISON")
    if option.variant not in {"KEEP", "HOLD"} and not challenge.counterexamples:
        unresolved.add("NO_SECOND_PASS_COUNTEREXAMPLE")
    if not challenge.review_reference.strip():
        unresolved.add("MISSING_EXTERNAL_REVIEW_REFERENCE")
    if challenge.disposition == "CHALLENGE":
        blocked.add("INDEPENDENT_REVIEW_CHALLENGED_PROPOSAL")
    elif challenge.disposition == "HOLD":
        unresolved.add("REVIEWER_REQUIRES_FURTHER_EVIDENCE")
    # Never infer that text/id/url proves a distinct reviewer. The wrapper can
    # feed an authenticated provider decision as a future separate capability.
    unresolved.add("REVIEWER_INDEPENDENCE_NOT_AUTHENTICATED")
    unresolved.add("SEMANTIC_AND_BEHAVIORAL_TRUTH_NOT_ESTABLISHED")
    return SemanticReviewReceipt(packet.revision, option.id,
        "CHALLENGED" if blocked else "HOLD", tuple(sorted(covered)),
        tuple(sorted(blocked)), tuple(sorted(unresolved)),
        ("AUTHENTICATE_EXTERNAL_SEMANTIC_REVIEW",
         "VERIFY_BLINDED_REVIEWER_NOT_PROPOSER",
         "REPLAY_BEFORE_AFTER_BEHAVIOR_ON_EXACT_COMMITS",
         "VERIFY_EXTERNAL_CONSUMER_COMPATIBILITY"))


__all__ = ["BlindedSourceExcerpt", "BlindedSemanticPacket",
           "IndependentResponsibilityHypothesis", "SecondPassSemanticChallenge",
           "SemanticReviewReceipt", "build_blinded_semantic_packet", "review_semantic_challenge"]
