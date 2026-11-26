"""Conservative, source-bound C++/MOOSE registration syntax collector.

Regex only detects narrow, literal source forms. It never claims that a
registered factory type was compiled, linked, instantiated or executed.
Unsupported conditional/preprocessed constructs remain unresolved.
"""

from __future__ import annotations

import re

from ...cpp_lexical import mask_cpp
from ...graph import Edge, Evidence, Node, SourceLocation
from ..collector import (
    CollectionResult, FactBatch, SourceInput, SourceRecord,
    file_node_id, graph_edge_id, stable_id,
)
from ..request import ScanRequest


_SUFFIXES = (".C", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".H")
_REGISTER = re.compile(
    r'(?m)^[ \t]*(register(?:AD)?MooseObject)[ \t]*'
    r'\([ \t]*"([^"\n]+)"[ \t]*,[ \t]*'
    r'([A-Za-z_]\w*)[ \t]*\)[ \t]*;',
)
_REGISTER_TOKEN = re.compile(r"\bregister(?:AD)?MooseObject\b")
_INCLUDE = re.compile(r'(?m)^[ \t]*#[ \t]*include[ \t]*[<"]([^>"\n]+)[>"]')
_CLASS = re.compile(
    r'(?m)^[ \t]*(?:class|struct)[ \t]+([A-Za-z_]\w*)'
    r'(?:[ \t\r\n]*:[ \t\r\n]*public[ \t\r\n]+'
    r'([A-Za-z_]\w*(?:::\w+)*))?'
    r'[ \t\r\n]*(?:\{|;)',
)
# Unhandled class/struct declaration forms must not silently pass as SCANNED.
# This is intentionally conservative; it is not a general C++ parser.
_CLASS_START = re.compile(r'(?m)^[ \t]*(?:class|struct)\b')
_CONDITIONAL = re.compile(r"(?m)^[ \t]*#[ \t]*(?:if|ifdef|ifndef|elif)\b")

_VALID_PARAMS_START = re.compile(
    r"(?m)^[ \t]*([A-Za-z_]\w*(?:::\w+)*)::validParams\s*\(\s*\)\s*\{"
)
_PARAM_CALL = re.compile(
    r'\bparams\s*\.\s*add(?P<required>Required)?Param\s*<\s*'
    r'(?P<cpp_type>[A-Za-z_]\w*(?:::\w+)*)\s*>\s*\(\s*"'
    r'(?P<name>[^"\n]+)"'
)
_PARAM_TOKEN = re.compile(r"\bparams\s*\.\s*add(?:Required)?Param\b")
_CPP_ENUM = re.compile(
    r'MooseEnum\s*\(\s*"([^"\n]+)"\s*'
    r'(?:,\s*"([^"\n]+)")?\s*\)'
)


def _without_comments(text: str) -> str:
    """Mask comments without changing offsets or newlines; keep literals."""
    return mask_cpp(text, mask_literals=False)


def _closing_brace(text: str, opening: int) -> int | None:
    """Find a balanced function body end; ignore string literal braces."""
    depth = 0
    quote = None
    escaped = False
    for index in range(opening, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


class CppSourceCollector:
    name = "cpp"
    version = "cpp-static-v0.2"

    def supports(self, record: SourceRecord) -> bool:
        return record.path.endswith(_SUFFIXES)

    def collect(self, source: SourceInput, request: ScanRequest,
                scope_id: str) -> CollectionResult:
        if not self.supports(source.record):
            return CollectionResult(FactBatch(), "UNSUPPORTED", ("NOT_CPP_SOURCE",))
        record = source.record
        source_text = source.content.decode("utf-8", "strict")
        text = _without_comments(source_text)
        parent = file_node_id(request.repository, record.path)
        nodes: list[Node] = []
        edges: list[Edge] = []
        evidence: list[Evidence] = []
        unresolved: set[str] = set()

        def line_of(start: int) -> int:
            return text.count("\n", 0, start) + 1

        def witness(kind: str, start: int, token: str) -> str:
            line = line_of(start)
            eid = stable_id(
                "evidence", request.repository, request.revision,
                record.path, record.blob_sha, self.version, kind, line, token,
            )
            evidence.append(Evidence(
                id=eid, kind="STRUCTURAL",
                source_ref=f"{record.path}:{line}@{record.blob_sha}",
                method=self.version, scope_id=scope_id,
                observation_status="SOURCE_DECLARED",
                attributes={
                    "source_sha": request.revision,
                    "blob_sha": record.blob_sha, "line": line,
                    "parser_version": self.version,
                },
            ))
            return eid

        def relation(src: str, target: str, kind: str, eid: str,
                     discriminator: str, *, attributes=None) -> None:
            edges.append(Edge(
                id=graph_edge_id(src, target, kind, discriminator),
                source_id=src, target_id=target, relation=kind,
                discriminator=discriminator,
                attributes=attributes or {},
                evidence_ids=(eid,),
            ))

        for match in _INCLUDE.finditer(text):
            name = match.group(1)
            eid = witness("include", match.start(), name)
            node_id = stable_id("node", request.repository,
                                "cpp_include_specifier", name)
            nodes.append(Node(
                id=node_id, kind="cpp_include_specifier", name=name,
                language="cpp", evidence_ids=(eid,),
            ))
            relation(parent, node_id, "INCLUDES_CANDIDATE", eid,
                     f"{line_of(match.start())}:{name}")

        matched_class_starts: set[int] = set()
        for match in _CLASS.finditer(text):
            matched_class_starts.add(match.start())
            name, base = match.groups()
            line = line_of(match.start())
            eid = witness("class", match.start(), name)
            class_id = stable_id(
                "node", request.repository, "cpp_class", record.path, name,
            )
            nodes.append(Node(
                id=class_id, kind="cpp_class", name=name,
                qualified_name=f"{record.path}:{name}", language="cpp",
                location=SourceLocation(record.path, line),
                evidence_ids=(eid,),
            ))
            relation(parent, class_id, "DEFINES", eid, f"class:{name}:{line}")
            if base is not None:
                eid = witness("base", match.start(), f"{name}:{base}")
                base_id = stable_id("node", request.repository,
                                    "cpp_base_specifier", base)
                nodes.append(Node(
                    id=base_id, kind="cpp_base_specifier", name=base,
                    language="cpp", evidence_ids=(eid,),
                ))
                relation(class_id, base_id, "INHERITS_CANDIDATE",
                         eid, f"{line}:{base}")

        for match in _CLASS_START.finditer(text):
            if match.start() not in matched_class_starts:
                unresolved.add(
                    f"CPP_CLASS_UNPARSED:{record.path}:{line_of(match.start())}"
                )

        matched_starts = set()
        for match in _REGISTER.finditer(text):
            matched_starts.add(match.start(1))
            macro, app, type_name = match.groups()
            eid = witness("registration", match.start(), f"{macro}:{app}:{type_name}")
            type_id = stable_id("node", request.repository, "moose_type", type_name)
            nodes.append(Node(
                id=type_id, kind="moose_type", name=type_name,
                evidence_ids=(eid,),
            ))
            relation(parent, type_id, "DECLARES_MOOSE_REGISTRATION",
                     eid, f"{line_of(match.start())}:{macro}",
                     attributes={"app": app, "macro": macro})

        # Bound parameter evidence to the owning C++ validParams() body.
        # These declarations are never proof of runtime accepted parameters.
        for match in _VALID_PARAMS_START.finditer(text):
            owner = match.group(1)
            closing = _closing_brace(text, match.end() - 1)
            if closing is None:
                unresolved.add(
                    f"CPP_VALIDPARAMS_UNPARSED:{record.path}:{line_of(match.start())}"
                )
                continue
            body = text[match.end():closing]
            declared_starts = set()
            type_id = stable_id("node", request.repository, "moose_type", owner)
            for declaration in _PARAM_CALL.finditer(body):
                declared_starts.add(declaration.start())
                name = declaration.group("name")
                parameter_type = declaration.group("cpp_type")
                required = declaration.group("required") is not None
                start = match.end() + declaration.start()
                call_end = body.find(");", declaration.end())
                if call_end < 0:
                    unresolved.add(
                        f"CPP_PARAM_UNTERMINATED:{record.path}:{line_of(start)}"
                    )
                    continue
                options: tuple[str, ...] = ()
                default: str | None = None
                if parameter_type == "MooseEnum":
                    enum = _CPP_ENUM.search(body, declaration.end(), call_end)
                    if enum is None:
                        unresolved.add(
                            f"CPP_MOOSE_ENUM_OPTIONS_UNRESOLVED:"
                            f"{record.path}:{line_of(start)}:{name}"
                        )
                        continue
                    options = tuple(enum.group(1).split())
                    default = enum.group(2)
                eid = witness("param_contract", start,
                              f"{owner}:{name}:{parameter_type}:{options}:{default}")
                nodes.append(Node(
                    id=type_id, kind="moose_type", name=owner,
                    evidence_ids=(eid,),
                ))
                parameter_id = stable_id(
                    "node", request.repository, "moose_param_contract", owner, name,
                )
                nodes.append(Node(
                    id=parameter_id, kind="moose_param_contract", name=name,
                    language="cpp",
                    attributes={
                        "parameter_type": parameter_type,
                        "required": required, "enum_options": options,
                        "enum_default": default,
                    },
                    evidence_ids=(eid,),
                ))
                relation(type_id, parameter_id, "DECLARES_PARAM_CONTRACT",
                         eid, name)
            for token in _PARAM_TOKEN.finditer(body):
                if token.start() not in declared_starts:
                    unresolved.add(
                        f"CPP_PARAM_DECLARATION_UNPARSED:"
                        f"{record.path}:{line_of(match.end()+token.start())}"
                    )

        for match in _REGISTER_TOKEN.finditer(text):
            if match.start() not in matched_starts:
                unresolved.add(
                    f"UNPARSED_MOOSE_REGISTRATION:{record.path}:{line_of(match.start())}"
                )
        if _CONDITIONAL.search(text):
            unresolved.add(f"CONDITIONAL_COMPILATION_UNRESOLVED:{record.path}")
        if 'R"' in source_text:
            unresolved.add(f"CXX_RAW_STRING_UNSUPPORTED:{record.path}")

        return CollectionResult(
            FactBatch(
                nodes=tuple(nodes), edges=tuple(edges),
                evidence=tuple(evidence), unresolved=tuple(sorted(unresolved)),
            ),
            status="PARTIAL" if unresolved else "COMPLETE",
        )


__all__ = ["CppSourceCollector"]
