"""Read-only Python AST declarations and *candidate* reference collector.

This collector does not resolve names, infer reachability, or assert execution.
It records syntax with exact blob/line Evidence. Consumers must not treat
*_CANDIDATE edges as confirmed runtime dependencies.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from io import BytesIO
import tokenize

from ...graph import Edge, Evidence, Node, SourceLocation
from ..collector import (
    CollectionResult, FactBatch, SourceInput, SourceRecord, UnresolvedTarget,
    file_node_id, graph_edge_id, stable_id,
)
from ..request import ScanRequest
from .file_reference_facts import FileReferenceFacts, path_kind


_DEFINITIONS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_BRANCHES = (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While,
             ast.Try, ast.ExceptHandler, ast.Match)
_MOOSE_TYPE_LINE = re.compile(r"(?m)^[ \t]*type[ \t]*=[ \t]*([^\n#]*)")
_MOOSE_IDENTIFIER = re.compile(r"[A-Za-z_]\w*(?:::\w+)*\Z")


def _body_metrics(node: ast.AST) -> tuple[int, int]:
    """Count branches and maximum branch nesting, excluding nested declarations."""
    branches = 0
    maximum = 0

    def walk(item: ast.AST, depth: int) -> None:
        nonlocal branches, maximum
        if item is not node and isinstance(item, _DEFINITIONS):
            return
        nested = depth + int(isinstance(item, _BRANCHES))
        if nested > depth:
            branches += 1
            maximum = max(maximum, nested)
        for child in ast.iter_child_nodes(item):
            walk(child, nested)

    for statement in getattr(node, "body", ()):
        walk(statement, 0)
    return branches, maximum


class PythonAstCollector:
    name = "python_ast"
    version = "python-ast-v0.3"

    def supports(self, record: SourceRecord) -> bool:
        return record.path.endswith(".py")

    def collect(self, source: SourceInput, request: ScanRequest,
                scope_id: str) -> CollectionResult:
        if not self.supports(source.record):
            return CollectionResult(
                FactBatch(), "UNSUPPORTED", ("NOT_PYTHON_SOURCE",),
            )
        record = source.record
        encoding, _ = tokenize.detect_encoding(BytesIO(source.content).readline)
        text = source.content.decode(encoding)
        root = ast.parse(text, filename=record.path, type_comments=True)
        nodes: list[Node] = []
        edges: list[Edge] = []
        evidence: list[Evidence] = []
        unresolved: set[str] = set()
        unresolved_targets: list[UnresolvedTarget] = []
        occurrences: Counter[tuple[str, str]] = Counter()
        file_facts = FileReferenceFacts(request, record, scope_id, self.version)
        parents = {id(child): parent for parent in ast.walk(root)
                   for child in ast.iter_child_nodes(parent)}
        docstrings = {
            id(statement.body[0].value)
            for statement in ast.walk(root)
            if isinstance(statement, (ast.Module, *_DEFINITIONS))
            and statement.body
            and isinstance(statement.body[0], ast.Expr)
            and isinstance(statement.body[0].value, ast.Constant)
            and isinstance(statement.body[0].value.value, str)
        }

        def witness(node: ast.AST, kind: str, statement: str,
                    *, unknown: bool = False, line_override: int | None = None) -> str:
            line = line_override or getattr(node, "lineno", 1)
            column = getattr(node, "col_offset", 0)
            eid = stable_id(
                "evidence", request.repository, request.revision,
                record.path, record.blob_sha, self.version,
                kind, line, column, statement,
            )
            evidence.append(Evidence(
                id=eid, kind="STRUCTURAL",
                source_ref=f"{record.path}:{line}@{record.blob_sha}",
                method=self.version, scope_id=scope_id,
                observation_status="UNRESOLVED" if unknown else "SOURCE_DECLARED",
                attributes={
                    "path": record.path, "blob_sha": record.blob_sha,
                    "source_sha": request.revision, "line": line,
                    "column": column, "parser_version": self.version,
                },
            ))
            return eid

        def link(parent: str, child: str, relation: str,
                 eid: str, discriminator: str) -> None:
            edges.append(Edge(
                id=graph_edge_id(parent, child, relation, discriminator),
                source_id=parent, target_id=child, relation=relation,
                discriminator=discriminator, evidence_ids=(eid,),
            ))

        class SyntaxVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.owners = [(file_node_id(request.repository, record.path), "")]
                self.literal_context = "template"

            @property
            def owner(self) -> str:
                return self.owners[-1][0]

            def candidate(self, item: ast.AST, relation: str,
                          kind: str, name: str, discriminator: str) -> None:
                eid = witness(item, relation, name + ":" + discriminator)
                target = stable_id("node", request.repository, kind, name)
                nodes.append(Node(
                    id=target, kind=kind, name=name, language="python",
                    evidence_ids=(eid,),
                ))
                link(self.owner, target, relation, eid, discriminator)

            def definition(self, item: ast.AST, kind: str) -> None:
                parent, qualified_parent = self.owners[-1]
                name = item.name
                occurrence_key = (parent, name)
                occurrences[occurrence_key] += 1
                index = occurrences[occurrence_key]
                qualified = ".".join(filter(None, (qualified_parent, name)))
                if index > 1:
                    qualified += f"#{index}"
                node_id = stable_id(
                    "node", request.repository, "python_symbol",
                    record.path, qualified,
                )
                eid = witness(item, "DEFINES", qualified)
                branches, depth = _body_metrics(item)
                start = item.lineno
                end = getattr(item, "end_lineno", start) or start
                nodes.append(Node(
                    id=node_id, kind=kind, name=name,
                    qualified_name=f"{record.path}:{qualified}",
                    language="python",
                    location=SourceLocation(record.path, start, end),
                    attributes={
                        "qualified_symbol": qualified,
                        "loc": end - start + 1,
                        "branches": branches, "max_branch_nesting": depth,
                    },
                    evidence_ids=(eid,),
                ))
                link(parent, node_id, "DEFINES", eid, qualified)

                # Decorators, signatures, and class bases execute or resolve
                # in the enclosing scope rather than in the new function body.
                for decorator in item.decorator_list:
                    self.visit(decorator)
                if isinstance(item, ast.ClassDef):
                    for expression in (*item.bases, *(v.value for v in item.keywords)):
                        self.visit(expression)
                else:
                    self.visit(item.args)
                    if item.returns is not None:
                        self.visit(item.returns)

                self.owners.append((node_id, qualified))
                for statement in item.body:
                    self.visit(statement)
                self.owners.pop()

            def visit_ClassDef(self, item: ast.ClassDef) -> None:
                self.definition(item, "python_class")

            def visit_FunctionDef(self, item: ast.FunctionDef) -> None:
                self.definition(item, "python_function")

            def visit_AsyncFunctionDef(self, item: ast.AsyncFunctionDef) -> None:
                self.definition(item, "python_async_function")

            def visit_Import(self, item: ast.Import) -> None:
                for index, alias in enumerate(item.names):
                    self.candidate(
                        alias, "IMPORTS_CANDIDATE", "python_import_specifier",
                        alias.name, f"{item.lineno}:{item.col_offset}:{index}",
                    )

            def visit_ImportFrom(self, item: ast.ImportFrom) -> None:
                module = "." * item.level + (item.module or "")
                for index, alias in enumerate(item.names):
                    name = f"{module}:{alias.name}"
                    self.candidate(
                        alias, "IMPORTS_CANDIDATE", "python_import_specifier",
                        name, f"{item.lineno}:{item.col_offset}:{index}",
                    )

            def visit_Call(self, item: ast.Call) -> None:
                name = ast.unparse(item.func)
                call_id = stable_id(
                    "node", request.repository, "python_call_site", record.path,
                    item.lineno, item.col_offset,
                    item.end_lineno, item.end_col_offset,
                )
                eid = witness(item, "CALLS_CANDIDATE", name)
                nodes.append(Node(
                    id=call_id, kind="python_call_site", name=name[:200],
                    language="python",
                    location=SourceLocation(record.path, item.lineno),
                    attributes={"callee_expression": name},
                    evidence_ids=(eid,),
                ))
                discriminator = f"{item.lineno}:{item.col_offset}"
                link(self.owner, call_id, "CALLS_CANDIDATE", eid, discriminator)

                dynamic = name in {
                    "getattr", "setattr", "delattr", "__import__", "eval", "exec",
                    "importlib.import_module",
                }
                if dynamic:
                    unknown_eid = witness(item, "DYNAMIC_REFERENCE", name, unknown=True)
                    unknown_id = stable_id(
                        "node", request.repository, "python_dynamic_target",
                        record.path, item.lineno, item.col_offset,
                    )
                    unresolved_targets.append(
                        UnresolvedTarget(unknown_id, f"dynamic:{name}", unknown_eid),
                    )
                    link(self.owner, unknown_id, "DYNAMIC_REFERENCE_CANDIDATE",
                         unknown_eid, discriminator)
                    unresolved.add(f"DYNAMIC_PYTHON_REFERENCE:{record.path}:{item.lineno}")
                if name in {"Path", "pathlib.Path", "PurePath", "pathlib.PurePath"}:
                    if (item.keywords or len(item.args) > 1 or any(
                        not isinstance(arg, ast.Constant) or not isinstance(arg.value, str)
                        for arg in item.args
                    )):
                        self.file_fact(item, ast.unparse(item), "PATH_CONSTRUCTOR_EXPRESSION",
                                       unknown=True, tag="constructor")
                elif isinstance(item.func, ast.Attribute) and item.func.attr in {"glob", "rglob"}:
                    if item.args and not isinstance(item.args[0], ast.Constant):
                        self.file_fact(item, ast.unparse(item), "GLOB_EXPRESSION",
                                       unknown=True, tag="glob")
                self.generic_visit(item)

            def visit_Assert(self, item: ast.Assert) -> None:
                previous = self.literal_context
                self.literal_context = "historical_assertion"
                self.generic_visit(item)
                self.literal_context = previous

            def visit_Return(self, item: ast.Return) -> None:
                previous = self.literal_context
                self.literal_context = "possible_generator"
                self.generic_visit(item)
                self.literal_context = previous

            def collect_moose_literal(self, item: ast.AST, value: str) -> None:
                for match in _MOOSE_TYPE_LINE.finditer(value):
                    raw_type = match.group(1).strip()
                    name = raw_type.strip("'\"")
                    line = min(
                        getattr(item, "lineno", 1) + value.count("\n", 0, match.start()),
                        getattr(item, "end_lineno", getattr(item, "lineno", 1)),
                    )
                    offset = f"{line}:{getattr(item, 'col_offset', 0)}:{match.start()}"
                    if _MOOSE_IDENTIFIER.fullmatch(name):
                        relation = {
                            "historical_assertion": "HISTORICAL_ASSERTS_TYPE",
                            "possible_generator": "MAY_GENERATE_INPUT",
                        }.get(self.literal_context, "DECLARES_GENERATOR_TEMPLATE_CANDIDATE")
                        eid = witness(item, relation, f"{name}:{offset}",
                                      line_override=line)
                        target_id = stable_id(
                            "node", request.repository, "moose_type", name,
                        )
                        nodes.append(Node(
                            id=target_id, kind="moose_type", name=name,
                            evidence_ids=(eid,),
                        ))
                        link(self.owner, target_id, relation, eid, offset)
                    else:
                        eid = witness(
                            item, "DYNAMIC_MOOSE_TYPE_TEMPLATE", offset,
                            unknown=True, line_override=line,
                        )
                        target_id = stable_id(
                            "node", request.repository, "python_dynamic_moose_type",
                            record.path, offset,
                        )
                        unresolved_targets.append(UnresolvedTarget(
                            target_id, "dynamic_moose_type", eid,
                        ))
                        link(self.owner, target_id, "MOOSE_TYPE_TEMPLATE_UNRESOLVED",
                             eid, offset)
                        unresolved.add(
                            f"PYTHON_MOOSE_TYPE_TEMPLATE_UNRESOLVED:{record.path}:{line}"
                        )

            def file_fact(self, item: ast.AST, literal: str, context: str,
                          *, unknown: bool = False, tag: str = "literal") -> None:
                line, col = item.lineno, item.col_offset
                end_line, end_col = item.end_lineno, item.end_col_offset
                file_facts.add(
                    literal, line, f"python:{tag}:{line}:{col}:{end_line}:{end_col}",
                    unknown=unknown,
                    details={"column": col, "end_line": end_line, "end_column": end_col,
                             "column_unit": "UTF8_BYTE", "path_context": context,
                             "literal_context": self.literal_context,
                             "source_expression": ast.get_source_segment(text, item)},
                )

            def visit_Constant(self, item: ast.Constant) -> None:
                if not isinstance(item.value, str) or id(item) in docstrings:
                    return
                self.collect_moose_literal(item, item.value)
                kind = path_kind(item.value)
                if kind is None:
                    return
                parent = parents.get(id(item))
                context = "STRING_LITERAL"
                unknown = kind == "unresolved"
                if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div):
                    context = "PATH_OPERAND"
                    # A suffix of a nested chain is not a standalone path.
                    if (parent.right is not item or isinstance(parent.left, ast.BinOp)
                            or (isinstance(parents.get(id(parent)), ast.BinOp)
                                and isinstance(parents[id(parent)].op, ast.Div))):
                        context, unknown = "COMPOSED_PATH_FRAGMENT", True
                elif isinstance(parent, ast.Call) and ast.unparse(parent.func) in {
                    "Path", "pathlib.Path", "PurePath", "pathlib.PurePath",
                }:
                    context = "PATH_CONSTRUCTOR_ARGUMENT"
                    if len(parent.args) != 1 or parent.keywords:
                        context, unknown = "COMPOSED_PATH_FRAGMENT", True
                self.file_fact(item, item.value, context, unknown=unknown)

            def visit_BinOp(self, item: ast.BinOp) -> None:
                if isinstance(item.op, ast.Div) and any(
                    isinstance(part, ast.Constant) and isinstance(part.value, str)
                    and path_kind(part.value) is not None for part in ast.walk(item)
                ):
                    self.file_fact(item, ast.unparse(item), "PATH_COMPOSITION",
                                   unknown=True, tag="composition")
                self.generic_visit(item)


            def visit_JoinedStr(self, item: ast.JoinedStr) -> None:
                # Formatted values remain dynamic; retain the literal fragments
                # but do not evaluate the Python expression or generated input.
                parts = []
                dynamic = False
                for part in item.values:
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        parts.append(part.value)
                    elif isinstance(part, ast.FormattedValue):
                        dynamic = True
                        parts.append("<PYTHON_DYNAMIC_EXPRESSION>")
                        self.visit(part.value)
                        if part.format_spec is not None:
                            self.visit(part.format_spec)
                literal = "".join(parts)
                self.collect_moose_literal(item, literal)
                if dynamic and path_kind(literal.replace("<PYTHON_DYNAMIC_EXPRESSION>", "{dynamic}")) is not None:
                    self.file_fact(item, ast.unparse(item), "FORMATTED_PATH_EXPRESSION",
                                   unknown=True, tag="formatted")
                if dynamic and _MOOSE_TYPE_LINE.search(literal):
                    unresolved.add(
                        f"PYTHON_GENERATOR_RENDER_UNVERIFIED:{record.path}:{item.lineno}"
                    )

            def visit_Name(self, item: ast.Name) -> None:
                if isinstance(item.ctx, ast.Load):
                    self.candidate(
                        item, "REFERENCES_CANDIDATE", "python_name_specifier",
                        item.id, f"{item.lineno}:{item.col_offset}",
                    )

            def visit_Attribute(self, item: ast.Attribute) -> None:
                if isinstance(item.ctx, ast.Load):
                    self.candidate(
                        item, "REFERENCES_CANDIDATE", "python_attribute_specifier",
                        ast.unparse(item),
                        f"{item.lineno}:{item.col_offset}",
                    )
                self.generic_visit(item)

        SyntaxVisitor().visit(root)
        file_facts.merge_into(nodes, edges, evidence, unresolved_targets, unresolved)
        return CollectionResult(
            FactBatch(
                nodes=tuple(nodes), edges=tuple(edges), evidence=tuple(evidence),
                unresolved_targets=tuple(unresolved_targets),
                unresolved=tuple(sorted(unresolved)),
            ),
            status="PARTIAL" if unresolved else "COMPLETE",
        )


__all__ = ["PythonAstCollector"]
