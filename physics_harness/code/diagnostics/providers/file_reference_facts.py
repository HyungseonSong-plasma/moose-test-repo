"""Shared lexical path observations; no path resolution or runtime authority."""

from __future__ import annotations

import re

from ...graph import Edge, Evidence, Node
from ..collector import UnresolvedTarget, file_node_id, graph_edge_id, stable_id

_LITERAL_PATH = re.compile(r"(?:[A-Za-z0-9_.@+-]+/)*[A-Za-z0-9_.@+-]+\.[A-Za-z][A-Za-z0-9_.+-]*\Z")
_PATH_SUFFIX = re.compile(r"\.[A-Za-z][A-Za-z0-9_.+-]*\Z")
_URI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")

def path_kind(value: str) -> str | None:
    """Conservative lexical discriminator, not a repository path resolver."""
    if _URI.match(value):
        return None
    if _LITERAL_PATH.fullmatch(value):
        return "literal"
    if (_PATH_SUFFIX.search(value) and not any(ch in value for ch in "\r\n\t")
            and (value.startswith(("/", "~", "$")) or "/" in value or "\\" in value
                 or any(ch in value for ch in "*?{}[]"))):
        return "unresolved"
    return None



class FileReferenceFacts:
    """Accumulate file-root edges with source-specific witness metadata."""

    def __init__(self, request, record, scope_id, version):
        self.request = request
        self.record = record
        self.scope_id = scope_id
        self.version = version
        self.nodes = []
        self.edges = []
        self.evidence = []
        self.unknown_targets = []
        self.unresolved = set()

    def add(self, literal, line, discriminator, *, unknown=False, details=None,
            evidence_id=None, unknown_relation="FILE_REFERENCE_UNRESOLVED",
            unknown_kind="file_path_expression", unresolved_reason=None):
        record, request = self.record, self.request
        kind = unknown_kind if unknown else "file_path_specifier"
        target = stable_id("node", request.repository, kind, literal)
        relation = unknown_relation if unknown else "REFERENCES_FILE_CANDIDATE"
        eid = evidence_id or stable_id(
            "evidence", request.repository, request.revision, record.path,
            record.blob_sha, self.version, relation, discriminator, literal, line,
        )
        owner = file_node_id(request.repository, record.path)
        self.evidence.append(Evidence(
            id=eid, kind="STRUCTURAL", source_ref=f"{record.path}:{line}@{record.blob_sha}",
            method=self.version, scope_id=self.scope_id,
            observation_status="UNRESOLVED" if unknown else "SOURCE_DECLARED",
            attributes={**(details or {}), "path": record.path,
                        "blob_sha": record.blob_sha, "source_sha": request.revision,
                        "line": line, "literal": literal, "parser_version": self.version},
        ))
        if unknown:
            self.unknown_targets.append(UnresolvedTarget(target, literal, eid))
            self.unresolved.add(unresolved_reason or
                                f"FILE_REFERENCE_UNRESOLVED:{record.path}:{discriminator}")
        else:
            self.nodes.append(Node(id=target, kind=kind, name=literal, evidence_ids=(eid,)))
        self.edges.append(Edge(
            id=graph_edge_id(owner, target, relation, discriminator),
            source_id=owner, target_id=target, relation=relation,
            discriminator=discriminator, evidence_ids=(eid,),
        ))

    def merge_into(self, nodes, edges, evidence, unknown_targets, unresolved):
        nodes.extend(self.nodes)
        edges.extend(self.edges)
        evidence.extend(self.evidence)
        unknown_targets.extend(self.unknown_targets)
        unresolved.update(self.unresolved)
