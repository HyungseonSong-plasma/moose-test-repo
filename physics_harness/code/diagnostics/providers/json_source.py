"""Strict JSON source observations; path-shaped strings are candidates, not resolved files."""

from __future__ import annotations

from bisect import bisect_right
import json
import re

from ...graph import Edge, Evidence, Node
from ..collector import (
    CollectionResult, FactBatch, SourceInput, SourceRecord, UnresolvedTarget,
    file_node_id, graph_edge_id, stable_id,
)
from ..request import ScanRequest


_SPACE = re.compile(r"[ \t\r\n]*")
_LITERAL_PATH = re.compile(r"(?:[A-Za-z0-9_.@+-]+/)*[A-Za-z0-9_.@+-]+\.[A-Za-z][A-Za-z0-9_.+-]*\Z")
_PATH_SUFFIX = re.compile(r"\.[A-Za-z][A-Za-z0-9_.+-]*\Z")
_URI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_MAX_DEPTH = 128
_MAX_REFERENCES = 10000


class _Limit(ValueError):
    """A deliberate collector bound; not a syntax error."""


def _invalid_constant(value: str):
    raise ValueError("JSON_NONSTANDARD_CONSTANT")


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _string_values(text: str):
    """Walk JSON containers; delegate scalar decoding to the stdlib.

    Yield (JSON Pointer, decoded string, opening-quote offset) for values only.
    Duplicate keys and trailing data are rejected; no input is executed.
    """
    decoder = json.JSONDecoder(parse_constant=_invalid_constant)

    def skip(index):
        return _SPACE.match(text, index).end()

    def expect(index, token):
        index = skip(index)
        if not text.startswith(token, index):
            raise ValueError("JSON_EXPECTED_" + token)
        return index + 1

    def scalar(index):
        value, end = decoder.raw_decode(text, index)
        if isinstance(value, str):
            value.encode("utf-8", "strict")
        return value, end

    def walk(index, pointer, depth):
        if depth > _MAX_DEPTH:
            raise _Limit("JSON_DEPTH_LIMIT")
        index = skip(index)
        token = text[index:index + 1]
        if token == "{":
            index = skip(index + 1)
            if text.startswith("}", index):
                return index + 1
            seen = set()
            while True:
                if not text.startswith('"', index):
                    raise ValueError("JSON_OBJECT_KEY_REQUIRED")
                key, index = scalar(index)
                if key in seen:
                    raise ValueError("JSON_DUPLICATE_KEY")
                seen.add(key)
                index = expect(index, ":")
                index = yield from walk(index, pointer + "/" + _pointer_token(key), depth + 1)
                index = skip(index)
                if text.startswith("}", index):
                    return index + 1
                index = skip(expect(index, ","))
        if token == "[":
            index = skip(index + 1)
            if text.startswith("]", index):
                return index + 1
            item = 0
            while True:
                index = yield from walk(index, pointer + "/" + str(item), depth + 1)
                index = skip(index)
                if text.startswith("]", index):
                    return index + 1
                index = skip(expect(index, ","))
                item += 1
        value, end = scalar(index)
        if token == '"' and isinstance(value, str):
            yield pointer, value, index
        return end

    end = yield from walk(0, "", 0)
    if skip(end) != len(text):
        raise ValueError("JSON_TRAILING_DATA")


def _path_kind(value: str) -> str | None:
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


class JsonSourceCollector:
    name = "json"
    version = "json-source-static-v0.1"

    def supports(self, record: SourceRecord) -> bool:
        return record.path.endswith(".json")

    def collect(self, source: SourceInput, request: ScanRequest,
                scope_id: str) -> CollectionResult:
        if not self.supports(source.record):
            return CollectionResult(FactBatch(), "UNSUPPORTED", ("NOT_JSON_SOURCE",))
        record = source.record
        try:
            text = source.content.decode("utf-8", "strict")
            # Parse the entire document before returning any observations.
            references = []
            for pointer, value, offset in _string_values(text):
                kind = _path_kind(value)
                if kind is not None:
                    if len(references) >= _MAX_REFERENCES:
                        raise _Limit("JSON_REFERENCE_LIMIT")
                    references.append((pointer, value, offset, kind))
        except _Limit as exc:
            return CollectionResult(FactBatch(unresolved=(f"{exc}:{record.path}",)), "PARTIAL")
        except (ValueError, UnicodeError, RecursionError) as exc:
            detail = str(exc) if str(exc).startswith("JSON_") else type(exc).__name__
            return CollectionResult(FactBatch(), "FAILED", (f"INVALID_JSON:{detail}",))

        line_starts = [0] + [match.end() for match in re.finditer(r"\r\n|\r|\n", text)]
        owner = file_node_id(request.repository, record.path)
        nodes, edges, evidence, unknown_targets = [], [], [], []
        unresolved = set()
        for pointer, value, offset, kind in references:
            line = bisect_right(line_starts, offset)
            column = offset - line_starts[line - 1]
            discriminator = "json:" + pointer
            unknown = kind == "unresolved"
            target_kind = "json_path_expression" if unknown else "file_path_specifier"
            target = stable_id("node", request.repository, target_kind, value)
            relation = "JSON_FILE_REFERENCE_UNRESOLVED" if unknown else "REFERENCES_FILE_CANDIDATE"
            eid = stable_id(
                "evidence", request.repository, request.revision, record.path,
                record.blob_sha, self.version, pointer, value, line, column,
            )
            evidence.append(Evidence(
                id=eid, kind="STRUCTURAL", source_ref=f"{record.path}:{line}@{record.blob_sha}",
                method=self.version, scope_id=scope_id,
                observation_status="UNRESOLVED" if unknown else "SOURCE_DECLARED",
                attributes={"path": record.path, "blob_sha": record.blob_sha,
                            "source_sha": request.revision, "line": line, "column": column,
                            "json_pointer": pointer, "literal": value,
                            "parser_version": self.version},
            ))
            if unknown:
                unknown_targets.append(UnresolvedTarget(target, value, eid))
                unresolved.add(f"JSON_PATH_EXPRESSION_UNRESOLVED:{record.path}:{line}:{column}")
            else:
                nodes.append(Node(id=target, kind=target_kind, name=value, evidence_ids=(eid,)))
            edges.append(Edge(
                id=graph_edge_id(owner, target, relation, discriminator),
                source_id=owner, target_id=target, relation=relation,
                discriminator=discriminator, evidence_ids=(eid,),
            ))
        batch = FactBatch(nodes=tuple(nodes), edges=tuple(edges), evidence=tuple(evidence),
                          unresolved_targets=tuple(unknown_targets),
                          unresolved=tuple(sorted(unresolved)))
        return CollectionResult(batch, "PARTIAL" if unresolved else "COMPLETE")


__all__ = ["JsonSourceCollector"]
