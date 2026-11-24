"""Bounded generated-HIT byte evidence, separate from Git and Native observations.

The caller must independently select the expected identity. A matching supplied
receipt is not authenticated proof that the producer ran. Acquisition and
causal binding are separate follow-up gates; this provider never executes code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha1, sha256
import re
from time import monotonic

from ...graph import Edge, Evidence, Node
from ..collector import (
    CollectionResult, FactBatch, SourceInput, SourceRecord, file_node_id,
    graph_edge_id, scan_scope_id, stable_id,
)
from ..request import ScanRequest, normalized_path
from .git import GitSourceProvider
from .moose_input import MooseInputCollector


@dataclass(frozen=True, slots=True)
class GeneratedInputIdentity:
    repository: str
    source_sha: str
    producer_path: str
    producer_blob_sha: str
    run_id: int
    attempt: int
    artifact_id: int
    artifact_path: str
    artifact_sha256: str
    invocation_sha256: str

    def __post_init__(self):
        if not isinstance(self.repository, str) or not re.fullmatch(
                r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise ValueError("GENERATED_REPOSITORY_INVALID")
        for name, length in (("source_sha", 40), ("producer_blob_sha", 40),
                             ("artifact_sha256", 64), ("invocation_sha256", 64)):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(
                    "[0-9a-f]{" + str(length) + "}", value):
                raise ValueError("GENERATED_DIGEST_INVALID:" + name)
        for name in ("run_id", "attempt", "artifact_id"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError("GENERATED_ID_INVALID:" + name)
        normalized_path(self.producer_path)
        normalized_path(self.artifact_path)
        if not self.artifact_path.endswith(".i") or not re.fullmatch(
                r"[A-Za-z0-9_.+/-]+", self.artifact_path):
            raise ValueError("GENERATED_HIT_PATH_INVALID")

    @property
    def key(self):
        return stable_id("generated", asdict(self))

    def reference(self, line):
        if type(line) is not int or line < 0:
            raise ValueError("GENERATED_LINE_INVALID")
        return (
            f"artifact://{self.repository}/{self.run_id}/{self.attempt}/"
            f"{self.artifact_id}/{self.artifact_path}@{self.artifact_sha256}"
            f"#L{line}"
        )


def collect_generated_input(
    request: ScanRequest,
    provider: GitSourceProvider,
    *,
    expected: GeneratedInputIdentity,
    receipt: GeneratedInputIdentity,
    content: bytes,
) -> CollectionResult:
    """Verify supplied bytes and producer Git identity, then reuse HIT parsing.

    Assemble the returned FactBatch with the existing producer source facts
    and their EvidenceReceipt. No generated file enters the Git inventory.
    Run/attempt/artifact attribution is a supplied identity, not independently
    verified execution; the result is deliberately PARTIAL.
    """
    started = monotonic()
    if not isinstance(expected, GeneratedInputIdentity) or not isinstance(
            receipt, GeneratedInputIdentity):
        raise TypeError("GENERATED_IDENTITY_REQUIRED")
    if expected != receipt:
        raise ValueError("GENERATED_RECEIPT_IDENTITY_MISMATCH")
    if (receipt.repository != request.repository or
            receipt.source_sha != request.revision):
        raise ValueError("GENERATED_SOURCE_SCOPE_MISMATCH")
    if not request.selects(receipt.producer_path):
        raise ValueError("GENERATED_PRODUCER_OUT_OF_SCOPE")
    if not isinstance(content, bytes):
        raise TypeError("GENERATED_BYTES_REQUIRED")
    if len(content) > request.budget.max_bytes:
        raise ValueError("GENERATED_BYTE_BUDGET_EXCEEDED")
    if sha256(content).hexdigest() != receipt.artifact_sha256:
        raise ValueError("GENERATED_CONTENT_DIGEST_MISMATCH")
    producer = provider.read_at_revision(request.revision, receipt.producer_path)
    if producer.record.blob_sha != receipt.producer_blob_sha:
        raise ValueError("GENERATED_PRODUCER_BLOB_MISMATCH")

    scope_id = scan_scope_id(request)
    # A private parser adapter only: this virtual path and Git-style content
    # hash never become Git source evidence or a tracked file receipt.
    virtual_path = "_generated_input_parser/" + receipt.key.split(":")[1] + ".i"
    parser_hash = sha1(b"blob " + str(len(content)).encode("ascii")
                       + b"\0" + content).hexdigest()
    parsed = MooseInputCollector().collect(
        SourceInput(SourceRecord(virtual_path, parser_hash, "100644", len(content)),
                    content), request, scope_id)
    if monotonic() - started > request.budget.max_seconds:
        raise ValueError("GENERATED_TIME_BUDGET_EXCEEDED")

    artifact_node = stable_id("node", request.repository, "generated_moose_input",
                              receipt.key)
    root = file_node_id(request.repository, virtual_path)
    producer_node = file_node_id(request.repository, receipt.producer_path)
    origin = asdict(receipt)
    anchor_id = stable_id("evidence", receipt.key, scope_id, "generated_bytes")
    anchor = Evidence(
        id=anchor_id, kind="GENERATED_INPUT", source_ref=receipt.reference(0),
        method="generated-hit-v0.1", scope_id=scope_id,
        observation_status="INFERRED",
        attributes={"generated_input": origin, "line": 0,
                    "anchor_evidence_id": anchor_id,
                    "causal_binding": "UNVERIFIED"},
    )
    evidence = [anchor]
    ids = {}
    for ev in parsed.batch.evidence:
        attrs = dict(ev.attributes)
        line = attrs.pop("line")
        for name in ("blob_sha", "source_sha", "path"):
            attrs.pop(name, None)
        eid = stable_id("evidence", receipt.key, scope_id, ev.id)
        ids[ev.id] = eid
        evidence.append(replace(
            ev, id=eid, kind="GENERATED_INPUT",
            source_ref=receipt.reference(line),
            attributes={**attrs, "generated_input": origin, "line": line,
                        "anchor_evidence_id": anchor_id,
                        "causal_binding": "UNVERIFIED"},
        ))

    nodes = [Node(id=artifact_node, kind="generated_moose_input",
                  name=receipt.artifact_path, attributes={"generated_input": origin},
                  evidence_ids=(anchor_id,))]
    for node in parsed.batch.nodes:
        changed = replace(node, evidence_ids=tuple(ids[e] for e in node.evidence_ids))
        if node.kind == "moose_input_block":
            changed = replace(
                changed, kind="generated_moose_input_block",
                qualified_name=None, location=None,
                attributes={**dict(node.attributes),
                            "artifact_node_id": artifact_node,
                            "block_path": node.qualified_name.split(":", 1)[1],
                            "artifact_line": node.location.start_line},
            )
        nodes.append(changed)

    relation = "GENERATED_INPUT_CANDIDATE"
    edges = [Edge(
        id=graph_edge_id(producer_node, artifact_node, relation, receipt.key),
        source_id=producer_node, target_id=artifact_node, relation=relation,
        discriminator=receipt.key, evidence_ids=(anchor_id,),
    )]
    for edge in parsed.batch.edges:
        source = artifact_node if edge.source_id == root else edge.source_id
        target = artifact_node if edge.target_id == root else edge.target_id
        relation = "GENERATED_" + edge.relation
        edges.append(replace(
            edge, id=graph_edge_id(source, target, relation, edge.discriminator or ""),
            source_id=source, target_id=target, relation=relation,
            evidence_ids=tuple(ids[e] for e in edge.evidence_ids),
        ))
    unknown_targets = tuple(
        replace(target, evidence_id=ids[target.evidence_id])
        for target in parsed.batch.unresolved_targets
    )
    unresolved = tuple(sorted({
        "GENERATED_PRODUCER_CAUSAL_BINDING_UNVERIFIED:" + receipt.key,
        *(reason.replace(virtual_path, receipt.reference(0))
          for reason in parsed.batch.unresolved),
    }))
    return CollectionResult(
        FactBatch(nodes=tuple(nodes), edges=tuple(edges), evidence=tuple(evidence),
                  unresolved_targets=unknown_targets, unresolved=unresolved),
        status="PARTIAL", errors=parsed.errors,
    )


__all__ = ["GeneratedInputIdentity", "collect_generated_input"]
