"""Exact before/after candidate symbol-placement checks, not semantic approval.

A proposed rename/extraction is checked *after* applying it on a distinct Git
commit in an isolated branch. This module cannot apply edits, verify all dynamic
consumers, or certify behavioral compatibility; it refuses to self-authorize.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re

from ..diagnostics.providers.git import GitSourceProvider
from ..refactor.naming import NamingCase, NamingOption
from .naming_boundary import (
    ResponsibilityBinding, _key_in_scope, _symbol_inventory, _tree_paths,
    verify_naming_boundary,
)


@dataclass(frozen=True, slots=True)
class CandidatePlacement:
    responsibility_id: str
    before_symbol: str
    after_symbol: str
    owner_id: str  # "original" or an ExtractionUnit.owner_id

    def __post_init__(self) -> None:
        if not all(isinstance(x, str) and x for x in (
                self.responsibility_id, self.before_symbol, self.after_symbol, self.owner_id)):
            raise ValueError("INVALID_CANDIDATE_PLACEMENT")
        if "::" not in self.before_symbol or "::" not in self.after_symbol:
            raise ValueError("INVALID_CANDIDATE_SYMBOL_KEY")


@dataclass(frozen=True, slots=True)
class NamingCandidateReceipt:
    baseline_revision: str
    candidate_revision: str
    option_id: str
    status: str  # STRUCTURAL_DELTA_VERIFIED / HOLD / REJECTED
    validated_placements: tuple[CandidatePlacement, ...]
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False

    @property
    def mutation_approved(self) -> bool:
        return False


def verify_naming_candidate(
    case: NamingCase, option: NamingOption, provider: GitSourceProvider,
    baseline_bindings: tuple[ResponsibilityBinding, ...],
    candidate_revision: str, candidate_owner_path: str,
    placements: tuple[CandidatePlacement, ...], *, max_files: int = 64,
) -> NamingCandidateReceipt:
    """Check exact descendant Git trees and full bound symbol placements.

    No caller-supplied PASS result or manually asserted file list is trusted.
    Even structural success *requires* independent behavior, name semantics,
    consumer/namespace and post-integration verification.
    """
    if not isinstance(case, NamingCase) or not isinstance(option, NamingOption):
        raise TypeError("CANDIDATE_CASE_OPTION_REQUIRED")
    if not isinstance(provider, GitSourceProvider) or not isinstance(placements, tuple) or any(
        not isinstance(p, CandidatePlacement) for p in placements):
        raise TypeError("CANDIDATE_PROVIDER_PLACEMENTS_REQUIRED")
    if not isinstance(candidate_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate_revision):
        raise ValueError("INVALID_CANDIDATE_COMMIT")
    if not isinstance(candidate_owner_path, str) or not candidate_owner_path:
        raise ValueError("INVALID_CANDIDATE_OWNER_PATH")
    if type(max_files) is not int or max_files < 1:
        raise ValueError("INVALID_CANDIDATE_FILE_BUDGET")
    blocked: set[str] = set()
    unknown: set[str] = set()
    checks = {"INDEPENDENT_SEMANTIC_NAME_AND_BOUNDARY_REVIEW",
              "VERIFY_ALL_IMPORTS_DYNAMIC_AND_EXTERNAL_CONSUMERS",
              "VERIFY_BEFORE_AFTER_BEHAVIORAL_COMPATIBILITY",
              "VERIFY_PUBLIC_API_AND_SERIALIZATION_CONTRACT",
              "REPLAY_TESTS_ON_EXACT_CANDIDATE_AND_INTEGRATION_HEAD",
              "VERIFY_NAMING_IDEMPOTENCE_AND_ROLLBACK"}
    if option.variant in {"KEEP", "HOLD"}:
        blocked.add("NO_EDIT_CANDIDATE_FOR_KEEP_OR_HOLD")
    if candidate_revision == case.revision:
        blocked.add("CANDIDATE_MUST_BE_DISTINCT_COMMIT")
    else:
        try:
            provider._git("merge-base", "--is-ancestor", case.revision, candidate_revision)
        except ValueError:
            blocked.add("CANDIDATE_NOT_DESCENDANT_OF_BASELINE")
    baseline = verify_naming_boundary(case, option, provider, baseline_bindings,
                                      max_files=max_files)
    blocked.update(baseline.blockers)
    unknown.update(baseline.unresolved)
    if baseline.status != "STRUCTURE_WITNESSED":
        unknown.add("BASELINE_BOUNDARY_NOT_WITNESSED")
    # No candidate facts are inferred if provenance/ancestry already failed.
    try:
        old_paths = _tree_paths(provider, case.revision)
        new_paths = _tree_paths(provider, candidate_revision)
    except (ValueError, TypeError, UnicodeError) as exc:
        unknown.add("CANDIDATE_GIT_SOURCE_UNAVAILABLE:" + type(exc).__name__)
        old_paths, new_paths = frozenset(), frozenset()
    if case.target_kind in {"FILE", "FOLDER"}:
        if option.variant in {"RENAME", "EXTRACT_RENAME"}:
            expected = option.proposed_name
            actual = (PurePosixPath(candidate_owner_path).stem if case.target_kind == "FILE"
                      else PurePosixPath(candidate_owner_path).name)
            if expected != actual or candidate_owner_path == case.current_path:
                blocked.add("CANDIDATE_PATH_DOES_NOT_IMPLEMENT_RENAME")
        elif candidate_owner_path != case.current_path:
            blocked.add("EXTRACT_KEEP_CHANGED_OWNER_PATH")
    elif candidate_owner_path != case.current_path:
        # Function/class names may change in place. File moves are separate.
        unknown.add("ADDITIONAL_MODULE_MOVE_NOT_DECLARED")
    if case.target_kind == "FOLDER":
        unknown.add("DIRECTORY_RENAME_CONSUMER_CLOSURE_UNSUPPORTED")
    elif candidate_owner_path not in new_paths:
        blocked.add("CANDIDATE_OWNER_PATH_MISSING")
    if candidate_owner_path != case.current_path and case.current_path in new_paths:
        unknown.add("BASELINE_OWNER_PATH_STILL_PRESENT_CHECK_COMPAT_SHIM")
    required_before = {(b.responsibility_id, symbol) for b in baseline_bindings
                       for symbol in b.source_symbols}
    witnessed = {(p.responsibility_id, p.before_symbol) for p in placements}
    if len(witnessed) != len(placements):
        blocked.add("DUPLICATE_CANDIDATE_PLACEMENT")
    if witnessed - required_before:
        blocked.add("CANDIDATE_HAS_UNDECLARED_SOURCE_SYMBOL")
    if required_before - witnessed:
        unknown.add("CANDIDATE_DROPPED_RESPONSIBILITY_SYMBOL")
    unit_by_id = {u.owner_id: u for u in option.extracted_units}
    by_id = {b.responsibility_id for b in baseline_bindings}
    before_ambiguities = {x.split(":", 1)[1] for x in baseline.unresolved
                          if x.startswith("AMBIGUOUS_DECLARATION:")}
    key_set = {s.key: s for s in baseline.observed_symbols
               if s.key not in before_ambiguities}
    after_paths = {candidate_owner_path} if candidate_owner_path in new_paths else set()
    for u in option.extracted_units:
        if u.destination_path is None:
            unknown.add("EXTRACT_DESTINATION_UNSPECIFIED:" + u.owner_id)
        elif u.destination_path not in new_paths:
            blocked.add("CANDIDATE_DESTINATION_MISSING:" + u.destination_path)
        else:
            after_paths.add(u.destination_path)
    if len(after_paths) > max_files:
        unknown.add("CANDIDATE_FILE_BUDGET_EXCEEDED")
    after_symbols = {}
    after_ambiguities: set[str] = set()
    if new_paths and len(after_paths) <= max_files:
        try:
            after_inventory = _symbol_inventory(provider, candidate_revision,
                                                tuple(sorted(after_paths)),
                                                ambiguous=after_ambiguities)
            after_symbols = {s.key: s for s in after_inventory
                             if s.key not in after_ambiguities}
            selected = {p.after_symbol for p in placements}
            # Full ownership scans cover all affected files. Bounded class/function
            # cases additionally cover the renamed target and enclosing class.
            target_name = (option.proposed_name if option.variant == "RENAME"
                           else case.current_name) or case.current_name
            relevant = {key for key in after_ambiguities
                        if case.target_kind in {"FILE", "FOLDER"}
                        or key in selected
                        or _key_in_scope(key, case.target_kind,
                                         candidate_owner_path, target_name)
                        or any(key.startswith(p + "::method:" + n + ".")
                               for sym in selected if "::class:" in sym
                               for p, n in (sym.split("::class:", 1),))}
            unknown.update("AMBIGUOUS_DECLARATION:" + key for key in relevant)
        except (ValueError, UnicodeError, SyntaxError) as exc:
            unknown.add("CANDIDATE_SOURCE_PARSE_FAILED:" + type(exc).__name__)
    verified = []
    allowed_owners = {"original"} | set(unit_by_id)
    for p in placements:
        if p.responsibility_id not in by_id:
            blocked.add("PLACEMENT_HAS_UNDECLARED_RESPONSIBILITY")
        if p.owner_id not in allowed_owners:
            blocked.add("PLACEMENT_HAS_UNKNOWN_OWNER:" + p.owner_id)
            continue
        permitted = (p.responsibility_id in option.retained_responsibility_ids if p.owner_id == "original"
                     else p.responsibility_id in unit_by_id[p.owner_id].responsibility_ids)
        if not permitted:
            blocked.add("PLACEMENT_CONTRADICTS_RESPONSIBILITY_ALLOCATION:" + p.responsibility_id)
        expected_path = candidate_owner_path if p.owner_id == "original" else unit_by_id[p.owner_id].destination_path
        if expected_path is None or not p.after_symbol.startswith(expected_path + "::"):
            blocked.add("PLACEMENT_ON_WRONG_OWNER_PATH:" + p.after_symbol)
        if p.before_symbol in before_ambiguities or p.after_symbol in after_ambiguities:
            continue  # never validate a placement using an arbitrary declaration
        old = key_set.get(p.before_symbol)
        current = after_symbols.get(p.after_symbol)
        if not old:
            blocked.add("BASELINE_PLACEMENT_SYMBOL_NOT_OBSERVED:" + p.before_symbol)
        if not current:
            blocked.add("CANDIDATE_SYMBOL_NOT_DECLARED:" + p.after_symbol)
        if old and current:
            if old.signature != current.signature:
                unknown.add("DECLARATION_SIGNATURE_CHANGED:" + p.before_symbol)
            else:
                verified.append(p)
            if p.owner_id != "original" and p.before_symbol in after_symbols:
                unknown.add("EXTRACTED_SOURCE_SYMBOL_STILL_DECLARED:" + p.before_symbol)
    if option.variant == "RENAME":
        if any(p.owner_id != "original" for p in placements):
            blocked.add("RENAME_ONLY_HAS_EXTRACTED_PLACEMENTS")
        if case.target_kind in {"CLASS", "FUNCTION"}:
            old_target = ("class:" if case.target_kind == "CLASS" else "function:") + case.current_name
            new_target = ("class:" if case.target_kind == "CLASS" else "function:") + (option.proposed_name or "")
            if not any(p.before_symbol.endswith("::" + old_target) and p.after_symbol.endswith("::" + new_target)
                       for p in placements):
                blocked.add("CANDIDATE_SYMBOL_DOES_NOT_RENAME_TARGET")
    if option.variant == "EXTRACT_KEEP" and any(p.after_symbol != p.before_symbol
                                                   for p in placements if p.owner_id == "original"):
        unknown.add("RETAINED_SYMBOLS_CHANGED_DURING_EXTRACT_KEEP")
    status = "REJECTED" if blocked else "HOLD" if unknown else "STRUCTURAL_DELTA_VERIFIED"
    return NamingCandidateReceipt(case.revision, candidate_revision, option.id,
                                  status, tuple(verified), tuple(sorted(blocked)),
                                  tuple(sorted(unknown)), tuple(sorted(checks)))


__all__ = ["CandidatePlacement", "NamingCandidateReceipt", "verify_naming_candidate"]
