"""Strict JSON source observations; path-shaped strings are candidates, not resolved files."""

from __future__ import annotations

from bisect import bisect_right
import json
import re

from ..collector import CollectionResult, FactBatch, SourceInput, SourceRecord, stable_id
from .file_reference_facts import FileReferenceFacts, path_kind
from ..request import ScanRequest


_SPACE = re.compile(r"[ \t\r\n]*")
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
                kind = path_kind(value)
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
        facts = FileReferenceFacts(request, record, scope_id, self.version)
        for pointer, value, offset, kind in references:
            line = bisect_right(line_starts, offset)
            column = offset - line_starts[line - 1]
            eid = stable_id(
                "evidence", request.repository, request.revision, record.path,
                record.blob_sha, self.version, pointer, value, line, column,
            )
            facts.add(
                value, line, "json:" + pointer, unknown=kind == "unresolved",
                details={"column": column, "json_pointer": pointer},
                evidence_id=eid, unknown_relation="JSON_FILE_REFERENCE_UNRESOLVED",
                unknown_kind="json_path_expression",
                unresolved_reason=f"JSON_PATH_EXPRESSION_UNRESOLVED:{record.path}:{line}:{column}",
            )
        unresolved = facts.unresolved
        batch = FactBatch(nodes=tuple(facts.nodes), edges=tuple(facts.edges),
                          evidence=tuple(facts.evidence),
                          unresolved_targets=tuple(facts.unknown_targets),
                          unresolved=tuple(sorted(unresolved)))
        return CollectionResult(batch, "PARTIAL" if unresolved else "COMPLETE")


__all__ = ["JsonSourceCollector"]
