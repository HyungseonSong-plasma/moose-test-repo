"""Canonical fact IDs and typed, read-only collector contract.

Collectors emit source-bound facts, never semantic/deletion verdicts. An
unhandled source or dynamic reference must surface as a coverage issue.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from collections.abc import Mapping
from typing import Protocol

from ..graph import Edge, Evidence, Node
from .request import ScanRequest, normalized_path


def stable_id(prefix: str, *parts: object) -> str:
    """Stable logical IDs: callers decide whether revision belongs in the key."""
    if not isinstance(prefix, str) or not prefix or ":" in prefix:
        raise ValueError("INVALID_ID_PREFIX")
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return prefix + ":" + sha256(payload.encode("utf-8")).hexdigest()


def file_node_id(repository: str, path: str) -> str:
    return stable_id("node", repository, "file", normalized_path(path))


def graph_edge_id(source_id: str, target_id: str, relation: str,
                  discriminator: str = "") -> str:
    return stable_id("edge", source_id, target_id, relation, discriminator)


def scan_scope_id(request: ScanRequest) -> str:
    # Collector selection is set-like: request order cannot change scope identity.
    return stable_id("scope", request.repository, request.revision,
                     request.includes, request.excludes, tuple(sorted(request.collectors)))


@dataclass(frozen=True, slots=True)
class SourceRecord:
    path: str
    blob_sha: str
    mode: str
    size: int

    def __post_init__(self) -> None:
        normalized_path(self.path)
        if (not isinstance(self.blob_sha, str) or len(self.blob_sha) != 40
                or any(ch not in "0123456789abcdef" for ch in self.blob_sha)):
            raise ValueError("INVALID_BLOB_SHA")
        if not isinstance(self.mode, str) or not self.mode:
            raise ValueError("INVALID_SOURCE_MODE")
        if type(self.size) is not int or self.size < 0:
            raise ValueError("INVALID_SOURCE_SIZE")


@dataclass(frozen=True, slots=True)
class SourceInput:
    record: SourceRecord
    content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.record, SourceRecord) or not isinstance(self.content, bytes):
            raise TypeError("INVALID_SOURCE_INPUT")


@dataclass(frozen=True, slots=True)
class UnresolvedTarget:
    node_id: str
    name: str
    evidence_id: str

    def __post_init__(self) -> None:
        if not all(isinstance(v, str) and v for v in (self.node_id, self.name, self.evidence_id)):
            raise ValueError("INVALID_UNRESOLVED_TARGET")


@dataclass(frozen=True, slots=True)
class FactBatch:
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    unresolved_targets: tuple[UnresolvedTarget, ...] = ()
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, cls in (("nodes", Node), ("edges", Edge), ("evidence", Evidence),
                          ("unresolved_targets", UnresolvedTarget)):
            value = getattr(self, name)
            if not isinstance(value, tuple) or any(not isinstance(x, cls) for x in value):
                raise TypeError(f"{name} must be a tuple of {cls.__name__}")
        if not isinstance(self.unresolved, tuple) or any(
            not isinstance(x, str) or not x for x in self.unresolved
        ):
            raise ValueError("unresolved must be a tuple of nonempty strings")


COLLECTION_STATUSES = frozenset({"COMPLETE", "PARTIAL", "UNSUPPORTED", "FAILED"})


@dataclass(frozen=True, slots=True)
class CollectionResult:
    batch: FactBatch
    status: str = "COMPLETE"
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.batch, FactBatch):
            raise TypeError("collection batch must be a FactBatch")
        if self.status not in COLLECTION_STATUSES:
            raise ValueError("UNKNOWN_COLLECTION_STATUS")
        if self.status == "COMPLETE" and (
            self.batch.unresolved or self.batch.unresolved_targets or self.errors
        ):
            raise ValueError("FALSE_COMPLETE_COLLECTION")
        if not isinstance(self.errors, tuple) or any(
            not isinstance(e, str) or not e for e in self.errors
        ):
            raise ValueError("errors must be nonempty strings")


class SourceProvider(Protocol):
    def inventory(self, request: ScanRequest) -> tuple[SourceRecord, ...]: ...
    def read(self, record: SourceRecord) -> bytes: ...


class Collector(Protocol):
    name: str
    version: str

    def supports(self, record: SourceRecord) -> bool: ...

    def collect(self, source: SourceInput, request: ScanRequest,
                scope_id: str) -> CollectionResult: ...


def run_scan(
    request: ScanRequest,
    provider: SourceProvider,
    *,
    registry: Mapping[str, Collector] | None = None,
):
    """Run bounded read-only collectors and return a scoped diagnostic graph.

    Inventory is HEAD-bound. Failed/unsupported/budget-limited sources remain
    visible in the receipt, and cannot produce false COMPLETE coverage.
    """
    import hashlib
    from fnmatch import fnmatchcase
    from pathlib import PurePosixPath
    import time

    from ..graph import Evidence, Node, SourceLocation
    from .assemble import GraphAssembler
    from .receipt import FileCoverage, create_receipt

    if not isinstance(request, ScanRequest):
        raise TypeError("request must be a ScanRequest")
    if registry is None:
        from .providers.cpp import CppSourceCollector
        from .providers.moose_input import MooseInputCollector
        from .providers.python_ast import PythonAstCollector
        from .providers.workflow import WorkflowCollector
        registry = {
            "workflow": WorkflowCollector(),
            "python_ast": PythonAstCollector(),
            "cpp": CppSourceCollector(),
            "moose_input": MooseInputCollector(),
        }
    selected_collectors = []
    for key in request.collectors:
        item = registry.get(key)
        if item is None or item.name != key:
            raise ValueError(f"UNKNOWN_COLLECTOR: {key}")
        selected_collectors.append(item)

    # Make handler execution and receipt ordering independent of request ordering.
    selected_collectors.sort(key=lambda item: item.name)

    started = time.monotonic()
    inventory = provider.inventory(request)
    if not isinstance(inventory, tuple) or any(
        not isinstance(item, SourceRecord) for item in inventory
    ):
        raise TypeError("provider.inventory must return tuple[SourceRecord]")
    if len({record.path for record in inventory}) != len(inventory):
        raise ValueError("DUPLICATE_PROVIDER_SOURCE")
    scope_id = scan_scope_id(request)
    records = sorted(inventory, key=lambda record: record.path)
    receipts: list[FileCoverage] = []
    batches: list[FactBatch] = []
    unresolved: list[str] = []
    attempted = 0
    read_bytes = 0

    if request.roots:
        unresolved.append("ROOT_TARGET_FILTER_NOT_IMPLEMENTED")

    for pattern in request.includes:
        if not any(fnmatchcase(item.path, pattern) for item in records):
            unresolved.append(f"INCLUDE_PATTERN_UNMATCHED:{pattern}")

    for record in records:
        matched = any(fnmatchcase(record.path, p) for p in request.includes)
        if not matched:
            continue
        if not request.selects(record.path):
            receipts.append(FileCoverage(record.path, record.blob_sha, "EXCLUDED"))
            continue

        # The Git tree proves the tracked file's identity, even when parsing
        # the source is unsupported or budget-limited.
        file_evidence_id = stable_id(
            "evidence", request.repository, request.revision,
            record.path, record.blob_sha, "GIT_TREE",
        )
        node_id = file_node_id(request.repository, record.path)
        batches.append(FactBatch(
            nodes=(Node(
                id=node_id, kind="file", name=PurePosixPath(record.path).name,
                qualified_name=record.path,
                location=SourceLocation(record.path),
                evidence_ids=(file_evidence_id,),
            ),),
            evidence=(Evidence(
                id=file_evidence_id, kind="SOURCE_IDENTITY",
                source_ref=f"{record.path}@{record.blob_sha}",
                method="GIT_TREE",
                scope_id=scope_id, observation_status="SOURCE_DECLARED",
                attributes={
                    "repository": request.repository, "revision": request.revision,
                    "blob_sha": record.blob_sha, "mode": record.mode,
                    "byte_size": record.size,
                },
            ),),
        ))

        if record.mode not in {"100644", "100755"}:
            receipts.append(FileCoverage(record.path, record.blob_sha, "UNSUPPORTED",
                                         details=("NON_REGULAR_GIT_SOURCE",)))
            unresolved.append(f"NON_REGULAR_GIT_SOURCE:{record.path}")
            continue
        handlers = []
        support_errors = []
        for handler in selected_collectors:
            try:
                if handler.supports(record):
                    handlers.append(handler)
            except Exception as exc:
                support_errors.append(
                    f"COLLECTOR_SUPPORTS_FAILED:{handler.name}:{type(exc).__name__}"
                )
        if not handlers:
            if support_errors:
                receipts.append(FileCoverage(
                    record.path, record.blob_sha, "FAILED",
                    details=tuple(sorted(support_errors)),
                ))
                unresolved.append(f"FAILED:{record.path}")
            else:
                receipts.append(FileCoverage(
                    record.path, record.blob_sha, "UNSUPPORTED",
                    details=("NO_COLLECTOR",),
                ))
                unresolved.append(f"NO_COLLECTOR:{record.path}")
            continue
        if (attempted >= request.budget.max_files
                or read_bytes + record.size > request.budget.max_bytes
                or time.monotonic() - started > request.budget.max_seconds):
            receipts.append(FileCoverage(
                record.path, record.blob_sha, "SKIPPED_BUDGET",
                details=("BUDGET_EXCEEDED",),
            ))
            unresolved.append(f"BUDGET_EXCEEDED:{record.path}")
            continue
        attempted += 1
        read_bytes += record.size
        try:
            data = provider.read(record)
        except Exception as exc:
            # Integrity failures are not parser failures: they invalidate
            # exact-source provenance and must reject the entire scan.
            raise ValueError(f"SOURCE_READ_FAILED:{record.path}") from exc
        if len(data) != record.size or hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest() != record.blob_sha:
            raise ValueError(f"SOURCE_BLOB_IDENTITY_MISMATCH:{record.path}")

        all_details: list[str] = list(support_errors)
        statuses: set[str] = {"FAILED"} if support_errors else set()
        for handler in handlers:
            try:
                output = handler.collect(SourceInput(record, data), request, scope_id)
                if not isinstance(output, CollectionResult):
                    raise TypeError("collector must return CollectionResult")
                batches.append(output.batch)
                all_details.extend(output.errors + output.batch.unresolved)
                statuses.add(output.status)
                if output.status in {"UNSUPPORTED", "PARTIAL", "FAILED"}:
                    all_details.append(f"COLLECTOR_{output.status}:{handler.name}")
            except Exception as exc:
                statuses.add("FAILED")
                all_details.append(f"COLLECTOR_FAILED:{handler.name}:{type(exc).__name__}")

        # The conservative merge is commutative: never hide PARTIAL under
        # UNSUPPORTED just because a collector happened to run last.
        final_status = (
            "FAILED" if "FAILED" in statuses
            else "UNRESOLVED" if "PARTIAL" in statuses
            else "UNSUPPORTED" if "UNSUPPORTED" in statuses
            else "SCANNED"
        )
        if time.monotonic() - started > request.budget.max_seconds:
            final_status = "UNRESOLVED" if final_status == "SCANNED" else final_status
            all_details.append("TIME_BUDGET_EXCEEDED")
        receipts.append(FileCoverage(
            record.path, record.blob_sha, final_status,
            collectors=tuple(c.name for c in handlers),
            details=tuple(sorted(set(all_details))),
        ))
        if final_status != "SCANNED":
            unresolved.append(f"{final_status}:{record.path}")

    if not receipts:
        unresolved.append("NO_MATCHED_FILES")
    versions = tuple(sorted((c.name, c.version) for c in selected_collectors))
    receipt = create_receipt(
        request, scope_id=scope_id, files=receipts,
        collector_versions=versions, unresolved=tuple(unresolved),
        attempted_files=attempted, read_bytes=read_bytes,
        elapsed_seconds=time.monotonic() - started,
    )
    return GraphAssembler().assemble(request, tuple(batches), receipt)
