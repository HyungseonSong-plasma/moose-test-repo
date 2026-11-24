"""Independent Git-object line provenance gate for GPT naming proposals.

A line present at path@commit is not a proof that the naming statement is true.
Do not interpret this as ownership, semantic equivalence, consumer closure,
or mutation authorization. Does not fetch from network or read the worktree.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from ..diagnostics.providers.git import GitSourceProvider
from ..refactor.naming import NamingCase

_REF = re.compile(r"(.+):([1-9][0-9]*)@([0-9a-f]{40})\Z")


@dataclass(frozen=True, slots=True)
class NamingSourceVerification:
    case_revision: str
    status: str  # SOURCE_ANCHORS_VERIFIED / HOLD / FAILED
    verified_refs: tuple[str, ...]
    unresolved: tuple[str, ...]
    failures: tuple[str, ...]

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False

    @property
    def mutation_approved(self) -> bool:
        return False


def verify_naming_evidence_sources(
        case: NamingCase, provider: GitSourceProvider,
        *, max_refs: int = 128, max_source_bytes: int = 1_000_000,
) -> NamingSourceVerification:
    """Cross-check every declared path:line@blob against a local Git commit.

    The object may be on an earlier commit but must be ancestral to the
    case revision. Missing historical objects are HOLD (never guessed).
    Malformed or contradictory present evidence is FAILED. Textual evidence
    statements are NOT authenticated merely by validating their source line.
    """
    if not isinstance(case, NamingCase) or not isinstance(provider, GitSourceProvider):
        raise TypeError("NAMING_CASE_AND_GIT_PROVIDER_REQUIRED")
    if type(max_refs) is not int or max_refs < 1 or type(max_source_bytes) is not int or max_source_bytes < 1:
        raise ValueError("INVALID_NAMING_SOURCE_BUDGET")
    all_refs = [(e.source_revision, ref) for e in case.evidence for ref in e.source_refs]
    if len(all_refs) > max_refs:
        return NamingSourceVerification(case.revision, "HOLD", (),
                                        ("NAMING_SOURCE_REF_BUDGET_EXCEEDED",), ())
    good: set[str] = set()
    unknown: set[str] = set()
    failures: set[str] = set()
    if len({e.id for e in case.evidence}) != len(case.evidence):
        failures.add("DUPLICATE_NAMING_EVIDENCE")
    try:
        if provider._git("cat-file", "-t", case.revision).strip() != b"commit":
            unknown.add("TARGET_COMMIT_NOT_AVAILABLE")
    except ValueError:
        unknown.add("TARGET_COMMIT_NOT_AVAILABLE")
    cache: dict[tuple[str, str], object] = {}
    observed_revisions: set[str] = set()
    for revision, ref in all_refs:
        match = _REF.fullmatch(ref)
        if not match:
            failures.add("BAD_SOURCE_REFERENCE:" + ref)
            continue
        path, line, stated_blob = match.group(1), int(match.group(2)), match.group(3)
        if revision != case.revision and revision not in observed_revisions:
            try:
                provider._git("merge-base", "--is-ancestor", revision, case.revision)
            except ValueError:
                unknown.add("ANCESTRAL_SOURCE_REVISION_NOT_PROVEN:" + revision)
            observed_revisions.add(revision)
        key = (revision, path)
        if key not in cache:
            try:
                cache[key] = provider.read_at_revision(revision, path)
            except (ValueError, TypeError):
                unknown.add("SOURCE_COMMIT_OR_PATH_UNAVAILABLE:" + path + "@" + revision)
                continue
        source = cache[key]
        if source.record.blob_sha != stated_blob:
            failures.add("SOURCE_BLOB_CONTRADICTION:" + ref)
            continue
        if len(source.content) > max_source_bytes:
            unknown.add("SOURCE_FILE_EXCEEDS_BUDGET:" + path)
            continue
        lines = source.content.splitlines()
        if line > len(lines) or not lines[line - 1].strip():
            failures.add("SOURCE_LINE_NOT_AN_OBSERVATION:" + ref)
            continue
        good.add(ref)
    status = "FAILED" if failures else "HOLD" if unknown else "SOURCE_ANCHORS_VERIFIED"
    return NamingSourceVerification(case.revision, status, tuple(sorted(good)),
                                    tuple(sorted(unknown)), tuple(sorted(failures)))


__all__ = ["NamingSourceVerification", "verify_naming_evidence_sources"]
