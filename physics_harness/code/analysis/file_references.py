"""Resolve observed path candidates against an immutable Git inventory, not runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..diagnostics import EvidenceReceipt, GitSourceProvider, ScanRequest, file_node_id
from ..diagnostics.request import normalized_path
from ..graph import GraphSnapshot


_BASES = frozenset({"REPOSITORY_ROOT", "OWNER_DIRECTORY"})
_LITERAL_RELATIONS = frozenset({"REFERENCES_FILE_CANDIDATE"})
_UNKNOWN_RELATIONS = frozenset({"JSON_FILE_REFERENCE_UNRESOLVED", "FILE_REFERENCE_UNRESOLVED"})


@dataclass(frozen=True, slots=True)
class FileReferenceTarget:
    path: str
    blob_sha: str
    mode: str
    coverage: str  # receipt file status or OUT_OF_SCOPE


@dataclass(frozen=True, slots=True)
class FileReferenceResolution:
    edge_id: str
    source_path: str
    literal: str
    evidence_ids: tuple[str, ...]
    bases: tuple[str, ...]
    attempted_paths: tuple[str, ...]
    targets: tuple[FileReferenceTarget, ...]
    status: str  # RESOLVED_CANDIDATE / AMBIGUOUS / MISSING / UNRESOLVED / NON_REGULAR
    reason: str


@dataclass(frozen=True, slots=True)
class FileReferenceReport:
    repository: str
    revision: str
    scope_id: str
    rows: tuple[FileReferenceResolution, ...]
    source_coverage: str

    @property
    def global_consumer_closed(self) -> bool:
        return False

    @property
    def safe_to_delete(self) -> bool:
        return False


def _join(owner: str, literal: str, base: str) -> str:
    # Never interpret an absolute path, shell expression, URI, glob or an
    # escaping parent traversal as a tracked repository path.
    if (not literal or literal.startswith(("/", "~"))
            or any(ch in literal for ch in "\x00\r\n\\:*?[]{}$")
            or literal.endswith("/")):
        raise ValueError("UNSUPPORTED_LITERAL_PATH")
    parts = list(PurePosixPath(owner).parent.parts) if base == "OWNER_DIRECTORY" else []
    for part in literal.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError("PATH_ESCAPES_REPOSITORY")
            parts.pop()
        else:
            parts.append(part)
    return normalized_path("/".join(parts))


def resolve_file_references(
    graph: GraphSnapshot,
    receipt: EvidenceReceipt,
    provider: GitSourceProvider,
    *,
    bases_by_edge: Mapping[str, tuple[str, ...]],
) -> FileReferenceReport:
    """Resolve each occurrence with caller-declared path-base alternatives.

    A literal node is not a canonical file node. Base choice is per edge,
    never per shared specifier; the same literal can mean different files.
    Missing bases, dynamic paths, nonregular targets and ambiguity remain
    explicit. An out-of-scope target can exist without having been parsed.
    Metadata verification is not an independent parser replay.
    """
    if not isinstance(provider, GitSourceProvider):
        raise TypeError("FILE_REFERENCE_GIT_PROVIDER_REQUIRED")
    from ..verification.consistency import verify_generated_artifact

    verification = verify_generated_artifact(graph, receipt)
    if verification.failures:
        raise ValueError("FILE_REFERENCE_INVALID_SOURCE_RECEIPT")
    if not isinstance(bases_by_edge, Mapping):
        raise TypeError("FILE_REFERENCE_BASE_MAPPING_REQUIRED")

    nodes = graph.nodes_by_id()
    witnesses = graph.evidence_by_id()
    edges = tuple(e for e in graph.edges
                  if e.relation in _LITERAL_RELATIONS | _UNKNOWN_RELATIONS)
    if set(bases_by_edge) - {e.id for e in edges}:
        raise ValueError("UNKNOWN_FILE_REFERENCE_EDGE")
    for bases in bases_by_edge.values():
        if (not isinstance(bases, tuple) or not bases
                or any(not isinstance(b, str) or b not in _BASES for b in bases)
                or len(set(bases)) != len(bases)):
            raise ValueError("INVALID_FILE_REFERENCE_BASES")

    request = ScanRequest(
        repository=receipt.repository, revision=receipt.revision,
        includes=receipt.requested_includes, excludes=receipt.requested_excludes,
        collectors=tuple(name for name, _ in receipt.collector_versions),
    )
    inventory = {r.path: r for r in provider.inventory(request)}
    coverage = {r.path: r for r in receipt.files}
    for path, entry in coverage.items():
        if path not in inventory or inventory[path].blob_sha != entry.blob_sha:
            raise ValueError("FILE_REFERENCE_INVENTORY_RECEIPT_MISMATCH:" + path)

    rows = []
    for edge in sorted(edges, key=lambda e: e.id):
        target = nodes[edge.target_id]
        literal = target.name
        unknown = edge.relation in _UNKNOWN_RELATIONS
        evidence = tuple(witnesses[eid] for eid in edge.evidence_ids)
        source_paths = {e.attributes.get("path") for e in evidence}
        if (not evidence or len(source_paths) != 1
                or not all(isinstance(path, str) for path in source_paths)):
            raise ValueError("FILE_REFERENCE_SOURCE_WITNESS_REQUIRED")
        owner = next(iter(source_paths))
        if (owner not in coverage or coverage[owner].status == "EXCLUDED"
                or edge.source_id != file_node_id(receipt.repository, owner)
                or nodes[edge.source_id].kind != "file"
                or target.kind != ("unresolved" if unknown else "file_path_specifier")
                or any(e.attributes.get("literal") != literal
                       or e.attributes.get("source_sha") != receipt.revision
                       or e.observation_status != ("UNRESOLVED" if unknown else "SOURCE_DECLARED")
                       for e in evidence)):
            raise ValueError("FILE_REFERENCE_WITNESS_MISMATCH:" + edge.id)
        bases = tuple(sorted(bases_by_edge.get(edge.id, ())))
        attempted: set[str] = set()
        invalid = False
        if not unknown:
            for base in bases:
                try:
                    attempted.add(_join(owner, literal, base))
                except ValueError:
                    invalid = True
        targets = tuple(
            FileReferenceTarget(path, inventory[path].blob_sha, inventory[path].mode,
                                coverage[path].status if path in coverage else "OUT_OF_SCOPE")
            for path in sorted(attempted) if path in inventory
        )
        if unknown:
            status, reason = "UNRESOLVED", "DYNAMIC_OR_UNSUPPORTED_EXPRESSION"
        elif not bases:
            status, reason = "UNRESOLVED", "PATH_BASE_UNDECLARED"
        elif invalid:
            status, reason = "UNRESOLVED", "UNSUPPORTED_OR_ESCAPING_PATH"
        elif len(targets) > 1:
            status, reason = "AMBIGUOUS", "MULTIPLE_TRACKED_CANDIDATES"
        elif not targets:
            status, reason = "MISSING", "NO_TRACKED_MATCH_IN_DECLARED_BASES"
        elif targets[0].mode not in {"100644", "100755"}:
            status, reason = "NON_REGULAR", "NON_REGULAR_GIT_TARGET"
        else:
            status, reason = "RESOLVED_CANDIDATE", "EXACT_TRACKED_PATH"
        rows.append(FileReferenceResolution(
            edge.id, owner, literal, tuple(sorted(edge.evidence_ids)), bases,
            tuple(sorted(attempted)), targets, status, reason,
        ))
    return FileReferenceReport(receipt.repository, receipt.revision, receipt.scope_id,
                               tuple(rows), receipt.completeness)


__all__ = ["FileReferenceTarget", "FileReferenceResolution", "FileReferenceReport",
           "resolve_file_references"]
