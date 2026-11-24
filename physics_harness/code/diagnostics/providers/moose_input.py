"""Conservative MOOSE HIT .i block/type/include syntax collector.

A declared type assignment is a reference candidate, not evidence that a
Factory object exists or was instantiated. Includes/expressions are never
implicitly resolved or executed.
"""

from __future__ import annotations

import re

from ...graph import Edge, Evidence, Node, SourceLocation
from ..collector import (
    CollectionResult, FactBatch, SourceInput, SourceRecord, UnresolvedTarget,
    file_node_id, graph_edge_id, stable_id,
)
from ..request import ScanRequest
from .file_reference_facts import FileReferenceFacts, path_kind


_ASSIGNMENT = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.*)$")
_LITERAL_TYPE = re.compile(r"[A-Za-z_]\w*(?:::\w+)*\Z")


def _uncomment(line: str) -> str:
    """Remove shell/HIT comments outside single or double quoted literals."""
    quote = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote is not None and char == quote:
            quote = None
        elif quote is None:
            if char in {"'", '"'}:
                quote = char
            elif char == "#":
                return line[:index]
    return line


class MooseInputCollector:
    name = "moose_input"
    version = "moose-hit-static-v0.3"

    def supports(self, record: SourceRecord) -> bool:
        return record.path.endswith(".i")

    def collect(self, source: SourceInput, request: ScanRequest,
                scope_id: str) -> CollectionResult:
        if not self.supports(source.record):
            return CollectionResult(FactBatch(), "UNSUPPORTED",
                                    ("NOT_MOOSE_INPUT",))
        record = source.record
        content = source.content.decode("utf-8", "strict")
        blocks: list[dict] = []
        stack: list[int] = []
        types: list[tuple[int, str, int]] = []
        includes: list[tuple[int | None, str, int]] = []
        unresolved: set[str] = set()
        seen_paths: set[tuple[str, ...]] = set()
        file_facts = FileReferenceFacts(request, record, scope_id, self.version)

        def observe_path(raw_value: str, line: int, key: str, block_path: tuple[str, ...]):
            value = raw_value.strip()
            if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
                value = value[1:-1]
            # Explicit HIT file fields are not general strings. Anything
            # outside the narrow single-token path contract is unresolved.
            unknown = path_kind(value) != "literal"
            literal = value or "(missing)"
            file_facts.add(
                literal, line, f"hit:{key}:{line}", unknown=unknown,
                details={"path_context": key, "raw_value": raw_value,
                         "block_path": block_path},
            )

        for line_number, raw in enumerate(content.splitlines(), start=1):
            line = _uncomment(raw).strip()
            if not line:
                continue
            if line == "!include" or line.startswith(("!include ", "!include\t")):
                target = line[len("!include"):].strip()
                includes.append((stack[-1] if stack else None,
                                 target or "(missing)", line_number))
                observe_path(target, line_number, "!include",
                             blocks[stack[-1]]["path"] if stack else ())
                unresolved.add(
                    f"MOOSE_INCLUDE_UNRESOLVED:{record.path}:{line_number}"
                )
                continue

            if line.startswith("[") and line.endswith("]"):
                token = line[1:-1].strip()
                if token in {"", "../"}:
                    if not stack:
                        raise ValueError(f"MOOSE_UNBALANCED_CLOSE:{line_number}")
                    stack.pop()
                    continue
                if token.startswith("../"):
                    if not stack:
                        raise ValueError(f"MOOSE_PARENT_OUTSIDE_ROOT:{line_number}")
                    stack.pop()
                    token = token[3:]
                    unresolved.add(
                        f"MOOSE_RELATIVE_PATH_UNVERIFIED:{record.path}:{line_number}"
                    )
                elif token.startswith("./"):
                    token = token[2:]
                if not token or "[" in token or "]" in token:
                    raise ValueError(f"MOOSE_INVALID_BLOCK:{line_number}")
                parent_path = blocks[stack[-1]]["path"] if stack else ()
                path = parent_path + (token,)
                if path in seen_paths:
                    unresolved.add(
                        f"MOOSE_DUPLICATE_BLOCK:{record.path}:{line_number}"
                    )
                    # Treat second declarations as separate source occurrences,
                    # not a silent overwrite of the same logical graph node.
                    path = parent_path + (f"{token}#line{line_number}",)
                seen_paths.add(path)
                blocks.append({
                    "name": token,
                    "path": path,
                    "line": line_number,
                    "parent": stack[-1] if stack else None,
                    "attributes": {},
                    "parameters": set(),
                    "parameter_values": {},
                })
                stack.append(len(blocks) - 1)
                continue

            match = _ASSIGNMENT.fullmatch(line)
            if match and stack:
                key, value = match.groups()
                block = blocks[stack[-1]]
                block["parameters"].add(key)
                if key in block["parameter_values"]:
                    unresolved.add(
                        f"MOOSE_DUPLICATE_PARAMETER:{record.path}:{line_number}:{key}"
                    )
                # Exact textual values, not evaluated expressions or runtime
                # defaults; typed interpretation belongs to Analysis.
                block["parameter_values"][key] = value
                if key in {"active", "inactive"}:
                    blocks[stack[-1]]["attributes"][key] = value
                if key == "type":
                    types.append((stack[-1], value, line_number))
                if key in {"file", "table_file"}:
                    observe_path(value, line_number, key, block["path"])
                if "$" in value:
                    unresolved.add(
                        f"MOOSE_DYNAMIC_PARAMETER:{record.path}:{line_number}:{key}"
                    )
                continue

            unresolved.add(f"MOOSE_STATEMENT_UNPARSED:{record.path}:{line_number}")

        if stack:
            unresolved.add(f"MOOSE_UNCLOSED_BLOCKS:{record.path}")

        nodes: list[Node] = []
        edges: list[Edge] = []
        evidence: list[Evidence] = []
        unknown_targets: list[UnresolvedTarget] = []
        root_id = file_node_id(request.repository, record.path)

        def witness(kind: str, line: int, label: str,
                    *, unknown: bool = False) -> str:
            eid = stable_id(
                "evidence", request.repository, request.revision,
                record.path, record.blob_sha, self.version, kind, line, label,
            )
            evidence.append(Evidence(
                id=eid, kind="STRUCTURAL",
                source_ref=f"{record.path}:{line}@{record.blob_sha}",
                method=self.version, scope_id=scope_id,
                observation_status="UNRESOLVED" if unknown else "SOURCE_DECLARED",
                attributes={
                    "source_sha": request.revision, "blob_sha": record.blob_sha,
                    "line": line, "parser_version": self.version,
                },
            ))
            return eid

        def link(source_id: str, target_id: str, relation: str,
                 eid: str, discriminator: str) -> None:
            edges.append(Edge(
                id=graph_edge_id(source_id, target_id, relation, discriminator),
                source_id=source_id, target_id=target_id, relation=relation,
                discriminator=discriminator, evidence_ids=(eid,),
            ))

        def block_id(index: int) -> str:
            return stable_id("node", request.repository,
                             "moose_input_block", record.path,
                             blocks[index]["path"])

        for index, block in enumerate(blocks):
            eid = witness("block", block["line"], "/".join(block["path"]))
            bid = block_id(index)
            nodes.append(Node(
                id=bid, kind="moose_input_block", name=block["name"],
                qualified_name=f"{record.path}:{'/'.join(block['path'])}",
                location=SourceLocation(record.path, block["line"]),
                attributes={
                    **block["attributes"],
                    "parameter_names": tuple(sorted(block["parameters"])),
                    "parameter_values": tuple(sorted(block["parameter_values"].items())),
                },
                evidence_ids=(eid,),
            ))
            parent = (
                block_id(block["parent"])
                if block["parent"] is not None else root_id
            )
            link(parent, bid, "DECLARES_INPUT_BLOCK",
                 eid, "/".join(block["path"]))

        type_occurrences: set[int] = set()
        for index, expression, line_number in types:
            if index in type_occurrences:
                unresolved.add(
                    f"MOOSE_DUPLICATE_TYPE:{record.path}:{line_number}"
                )
            type_occurrences.add(index)
            source_id = block_id(index)
            type_name = expression.strip().strip("'\"")
            if not _LITERAL_TYPE.fullmatch(type_name):
                eid = witness("dynamic_type", line_number, expression,
                              unknown=True)
                target = stable_id(
                    "node", request.repository, "moose_dynamic_type",
                    record.path, line_number,
                )
                unknown_targets.append(UnresolvedTarget(
                    target, "dynamic_moose_type", eid,
                ))
                link(source_id, target, "DYNAMIC_TYPE_CANDIDATE",
                     eid, f"type:{line_number}")
                unresolved.add(f"MOOSE_TYPE_UNRESOLVED:{record.path}:{line_number}")
                continue
            eid = witness("type", line_number, type_name)
            target = stable_id("node", request.repository, "moose_type", type_name)
            nodes.append(Node(
                id=target, kind="moose_type", name=type_name,
                evidence_ids=(eid,),
            ))
            link(source_id, target, "DECLARES_TYPE_USE",
                 eid, f"type:{line_number}")

        for index, target_name, line_number in includes:
            eid = witness("include", line_number, target_name, unknown=True)
            unknown_id = stable_id(
                "node", request.repository, "moose_include_candidate",
                record.path, line_number, target_name,
            )
            unknown_targets.append(UnresolvedTarget(
                unknown_id, f"unresolved_include:{target_name}", eid,
            ))
            link(root_id if index is None else block_id(index), unknown_id,
                 "INCLUDES_CANDIDATE", eid, f"include:{line_number}")

        file_facts.merge_into(nodes, edges, evidence, unknown_targets, unresolved)
        return CollectionResult(
            FactBatch(
                nodes=tuple(nodes), edges=tuple(edges), evidence=tuple(evidence),
                unresolved_targets=tuple(unknown_targets),
                unresolved=tuple(sorted(unresolved)),
            ),
            status="PARTIAL" if unresolved else "COMPLETE",
        )


__all__ = ["MooseInputCollector"]
