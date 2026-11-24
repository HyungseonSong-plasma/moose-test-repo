"""Validate scoped GraphSnapshot/EvidenceReceipt metadata consistency.

VERIFIED is bounded source-metadata provenance, not runtime or semantic proof.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..diagnostics.receipt import EvidenceReceipt
from ..graph import GraphSnapshot


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    repository: str
    revision: str
    scope_id: str
    status: str
    verified_properties: tuple[str, ...]
    unverified_properties: tuple[str, ...]
    failures: tuple[str, ...]

    @property
    def artifact_verified(self) -> bool:
        return self.status == "VERIFIED"

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False


def verify_generated_artifact(
    graph: GraphSnapshot, receipt: EvidenceReceipt,
) -> VerificationReceipt:
    """Check actual diagnostic output against exact-HEAD source receipts.

    Does not re-read Git objects or assert that source syntax was interpreted
    exhaustively. A matching Blob SHA is provenance metadata, not execution.
    """
    if not isinstance(graph, GraphSnapshot) or not isinstance(
        receipt, EvidenceReceipt
    ):
        raise TypeError("verification requires GraphSnapshot and EvidenceReceipt")

    scope = graph.scope
    failures: set[str] = set()
    unknown: set[str] = set()
    verified: set[str] = {"GRAPH_REFERENCE_INTEGRITY"}

    if (scope.id != receipt.scope_id or scope.repository != receipt.repository
            or scope.revision != receipt.revision):
        failures.add("GRAPH_RECEIPT_SCOPE_MISMATCH")
    else:
        verified.add("SCOPE_IDENTITY")

    paths = {item.path: item for item in receipt.files}
    # Index by exact blob identity; the same blob can belong to multiple paths.
    # Keep all path candidates so ambiguous source references still fail closed.
    paths_by_blob: dict[str, list[tuple[str, object]]] = {}
    for path, item in paths.items():
        paths_by_blob.setdefault(item.blob_sha, []).append((path, item))
    included = tuple(sorted(
        item.path for item in receipt.files if item.status != "EXCLUDED"
    ))
    excluded = tuple(sorted(
        item.path for item in receipt.files if item.status == "EXCLUDED"
    ))
    if scope.included_paths != included or scope.excluded_paths != excluded:
        failures.add("GRAPH_RECEIPT_FILES_MISMATCH")
    else:
        verified.add("FILE_SCOPE_MEMBERSHIP")

    if (scope.completeness != receipt.completeness
            or scope.unresolved != receipt.unresolved):
        failures.add("GRAPH_RECEIPT_COMPLETENESS_MISMATCH")
    elif scope.completeness != "COMPLETE":
        unknown.add("INCOMPLETE_REQUESTED_SCOPE")
    else:
        verified.add("REQUESTED_FILE_COVERAGE")

    if any(item.status != "SCANNED" for item in receipt.files
           if item.status != "EXCLUDED"):
        unknown.add("UNSCANNED_REQUESTED_FILES")
    if not included:
        unknown.add("EMPTY_SOURCE_SCOPE")

    evidence_by_id = {item.id: item for item in graph.evidence}
    nodes_by_id = {item.id: item for item in graph.nodes}
    for evidence in graph.evidence:
        attrs = evidence.attributes
        if evidence.kind == "GENERATED_INPUT":
            # Artifact declarations are not tracked Git source and do not
            # attest a successful generator run or Native instantiation.
            from ..diagnostics.providers.generated_input import GeneratedInputIdentity
            try:
                identity = GeneratedInputIdentity(**dict(attrs["generated_input"]))
                line = attrs["line"]
                anchor_id = attrs["anchor_evidence_id"]
                anchor = evidence_by_id[anchor_id]
                anchor_attrs = anchor.attributes
                producer = paths[identity.producer_path]
                if (identity.repository != scope.repository or
                        identity.source_sha != scope.revision or
                        producer.blob_sha != identity.producer_blob_sha or
                        producer.status == "EXCLUDED" or
                        not producer.collectors or
                        evidence.source_ref != identity.reference(line) or
                        anchor.kind != "GENERATED_INPUT" or
                        anchor_attrs.get("generated_input") != attrs["generated_input"] or
                        anchor_attrs.get("line") != 0 or
                        anchor_attrs.get("anchor_evidence_id") != anchor_id or
                        anchor.source_ref != identity.reference(0) or
                        anchor.observation_status != "INFERRED" or
                        attrs.get("causal_binding") != "UNVERIFIED" or
                        evidence.observation_status not in
                        {"INFERRED", "SOURCE_DECLARED", "UNRESOLVED"} or
                        (line == 0 and evidence.id != anchor_id) or
                        (line > 0 and evidence.observation_status == "INFERRED")):
                    raise ValueError("GENERATED_PROVENANCE_MISMATCH")
            except (KeyError, TypeError, ValueError, AttributeError):
                failures.add("GENERATED_INPUT_PROVENANCE_INVALID:" + evidence.id)
            unknown.add("GENERATED_PRODUCER_CAUSAL_BINDING_UNVERIFIED")
            if evidence.observation_status == "UNRESOLVED":
                unknown.add("UNRESOLVED_GENERATED_INPUT_EVIDENCE")
            continue
        if evidence.kind == "PYTHON_CALL_TRACE":
            from .python_call_trace import validate_python_trace_metadata
            try:
                validate_python_trace_metadata(
                    evidence, scope, paths, nodes_by_id, graph.edges, evidence_by_id)
            except (KeyError, TypeError, ValueError, AttributeError):
                failures.add("PYTHON_TRACE_PROVENANCE_INVALID:" + evidence.id)
            unknown.add("RUNTIME_EXECUTION_NOT_INDEPENDENTLY_VERIFIED")
            continue
        if evidence.observation_status == "RUNTIME_OBSERVED":
            if attrs.get("source_sha") != scope.revision:
                failures.add("CROSS_HEAD_RUNTIME_EVIDENCE:" + evidence.id)
            if not all(attrs.get(key) for key in ("run_id", "attempt", "url")):
                failures.add("RUNTIME_PROVENANCE_INCOMPLETE:" + evidence.id)
            if attrs.get("url") != evidence.source_ref:
                failures.add("RUNTIME_SOURCE_REFERENCE_MISMATCH:" + evidence.id)
            unknown.add("RUNTIME_EXECUTION_NOT_INDEPENDENTLY_VERIFIED")
            continue

        ref = evidence.source_ref
        matches = []
        # Only receipt entries with the final @blob can match the old strict
        # path[@blob] / path:decimal_line@blob predicate.
        ref_blob = ref.rpartition("@")[2]
        for path, item in paths_by_blob.get(ref_blob, ()):
            if ref == path + "@" + item.blob_sha:
                matches.append((path, item, None))
            elif ref.startswith(path + ":") and ref.endswith("@" + item.blob_sha):
                line = ref[len(path) + 1:-(len(item.blob_sha) + 1)]
                if line.isdecimal() and int(line) > 0:
                    matches.append((path, item, int(line)))
        if len(matches) != 1:
            failures.add("SOURCE_REFERENCE_NOT_BOUND_TO_RECEIPT:" + evidence.id)
            continue

        path, file, line = matches[0]
        if file.status == "EXCLUDED":
            failures.add("SOURCE_EVIDENCE_FROM_EXCLUDED_PATH:" + evidence.id)
        if attrs.get("blob_sha") != file.blob_sha:
            failures.add("SOURCE_BLOB_MISMATCH:" + evidence.id)
        revision = attrs.get("source_sha", attrs.get("revision"))
        if revision != scope.revision:
            failures.add("SOURCE_REVISION_MISMATCH:" + evidence.id)
        if attrs.get("path") not in (None, path):
            failures.add("SOURCE_PATH_MISMATCH:" + evidence.id)
        if line is not None and attrs.get("line") != line:
            failures.add("SOURCE_LINE_MISMATCH:" + evidence.id)
        if evidence.method != "GIT_TREE" and line is None:
            failures.add("SOURCE_LINE_ABSENT:" + evidence.id)
        if evidence.observation_status == "UNRESOLVED":
            unknown.add("UNRESOLVED_SOURCE_EVIDENCE")

    if not any(x.startswith("SOURCE_") for x in failures):
        verified.add("SOURCE_METADATA_PROVENANCE")

    # Verified source integrity must not be conflated with global safety.
    unknown.update((
        "GLOBAL_CONSUMER_CLOSURE_UNPROVEN",
        "SEMANTIC_COMPATIBILITY_UNPROVEN",
        "NATIVE_RUNTIME_COMPATIBILITY_UNPROVEN",
    ))
    status = "FAILED" if failures else (
        "UNVERIFIED" if scope.completeness != "COMPLETE" or
        "UNSCANNED_REQUESTED_FILES" in unknown or
        "UNRESOLVED_SOURCE_EVIDENCE" in unknown or
        "RUNTIME_EXECUTION_NOT_INDEPENDENTLY_VERIFIED" in unknown or
        "GENERATED_PRODUCER_CAUSAL_BINDING_UNVERIFIED" in unknown or
        "EMPTY_SOURCE_SCOPE" in unknown else "VERIFIED"
    )
    return VerificationReceipt(
        repository=scope.repository, revision=scope.revision,
        scope_id=scope.id, status=status,
        verified_properties=tuple(sorted(verified)),
        unverified_properties=tuple(sorted(unknown)),
        failures=tuple(sorted(failures)),
    )


__all__ = ["VerificationReceipt", "verify_generated_artifact"]
