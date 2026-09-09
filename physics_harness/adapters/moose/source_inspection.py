"""MOOSE-specific C++ source inspection.

This module interprets source structures that are specifically meaningful in
MOOSE. Generic C++ parsing remains in
:mod:`physics_harness.observation.source_code.cpp`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from physics_harness.observation.source_code.cpp import (
    CppSource,
    CppSourceError,
    split_call_arguments,
)

CPP_TEXT_SUFFIXES = {".C", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"}


class FunctorInspectionError(CppSourceError):
    pass


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def extract_functor_property_declaration(
    text: str,
    property_marker: str,
    *,
    value_type: str = "ADReal",
) -> dict[str, Any]:
    cpp = CppSource(text)
    calls = [
        call
        for call in cpp.calls("addFunctorProperty", containing=property_marker)
        if re.search(
            rf"addFunctorProperty\s*<\s*{re.escape(value_type)}\s*>",
            call.slice(text),
        )
    ]
    if len(calls) != 1:
        raise FunctorInspectionError(
            f"expected exactly one {property_marker} addFunctorProperty declaration, found {len(calls)}"
        )
    call = calls[0]
    raw = call.slice(text)
    arguments = split_call_arguments(cpp, call).arguments
    return {
        "line": _line_number(text, call.start),
        "argument_count": len(arguments),
        "execution_tokens": sorted(set(re.findall(r"\bEXEC_[A-Z0-9_]+\b", raw))),
        "calls_full_evaluate": "evaluate" in raw,
        "snippet": " ".join(raw.split())[:700],
    }


def _source_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for base_name in ("src", "include"):
        base = Path(root) / base_name
        if base.is_dir():
            paths.extend(
                path
                for path in base.rglob("*")
                if path.is_file() and path.suffix in CPP_TEXT_SUFFIXES
            )
    return sorted(paths)


def _class_files(root: Path, class_name: str) -> list[Path]:
    result: list[Path] = []
    for path in _source_files(root):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if class_name in text:
            result.append(path)
    return result


def _space_arg_bindings(text: str) -> dict[str, str]:
    masked = CppSource(text).masked
    bindings: dict[str, str] = {}
    patterns = {
        "ElemQpArg": (
            r"\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemQpArg\s*\(",
            r"\b(?:Moose::)?ElemQpArg\s+([A-Za-z_]\w*)",
        ),
        "ElemSideQpArg": (
            r"\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemSideQpArg\s*\(",
            r"\b(?:Moose::)?ElemSideQpArg\s+([A-Za-z_]\w*)",
        ),
        "ElemArg": (
            r"\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemArg\s*\(",
            r"\b(?:Moose::)?ElemArg\s+([A-Za-z_]\w*)",
        ),
        "FaceArg": (
            r"\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*(?:makeFace|makeFaceArg)\s*\(",
            r"\b(?:Moose::)?FaceArg\s+([A-Za-z_]\w*)",
        ),
    }
    for kind, expressions in patterns.items():
        for expression in expressions:
            for match in re.finditer(expression, masked):
                bindings[match.group(1)] = kind
    return bindings


def _infer_space_argument(expression: str, bindings: dict[str, str]) -> str:
    stripped = expression.strip()
    for kind, tokens in (
        ("ElemSideQpArg", ("makeElemSideQpArg", "ElemSideQpArg")),
        ("ElemQpArg", ("makeElemQpArg", "ElemQpArg")),
        ("FaceArg", ("makeFaceArg", "makeFace", "FaceArg")),
        ("ElemArg", ("makeElemArg", "ElemArg")),
    ):
        if any(token in stripped for token in tokens):
            return kind
    if re.fullmatch(r"[A-Za-z_]\w*", stripped) and stripped in bindings:
        return bindings[stripped]
    return "UNKNOWN"


def _parameter_functor_variables(text: str, parameter: str) -> set[str]:
    variables: set[str] = set()
    patterns = (
        rf"\b([A-Za-z_]\w*)\s*\(\s*getFunctor\s*<\s*ADReal\s*>\s*\([^)]*[\"']{re.escape(parameter)}[\"'][^)]*\)\s*\)",
        rf"\b([A-Za-z_]\w*)\s*=\s*getFunctor\s*<\s*ADReal\s*>\s*\([^;]*[\"']{re.escape(parameter)}[\"'][^;]*\)",
        rf"\b([A-Za-z_]\w*)\s*\(\s*getFunctor\s*<\s*ADReal\s*>\s*\([^)]*getParam[^)]*[\"']{re.escape(parameter)}[\"']",
    )
    for pattern in patterns:
        variables.update(match.group(1) for match in re.finditer(pattern, text, re.S))
    if re.search(rf"[\"']{re.escape(parameter)}[\"']", text):
        for name in (f"_{parameter}", parameter):
            if re.search(rf"\b{re.escape(name)}\b", text):
                variables.add(name)
    return variables


def parameter_functor_calls(
    root: Path,
    class_name: str,
    parameter: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    root = Path(root)
    files = _class_files(root, class_name)
    if not files:
        return [], []
    texts = {path: path.read_text(errors="replace") for path in files}
    variables = _parameter_functor_variables("\n".join(texts.values()), parameter)
    rows: list[dict[str, Any]] = []
    for path, text in texts.items():
        cpp = CppSource(text)
        bindings = _space_arg_bindings(text)
        for variable in sorted(variables, key=len, reverse=True):
            for call in cpp.calls(variable):
                try:
                    parsed = split_call_arguments(cpp, call)
                except CppSourceError:
                    continue
                if not parsed.arguments:
                    continue
                first = parsed.arguments[0]
                if "getFunctor" in first:
                    continue
                line_start = text.rfind("\n", 0, call.start) + 1
                line_end = text.find("\n", parsed.close_paren)
                line_end = len(text) if line_end < 0 else line_end
                rows.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": _line_number(text, call.start),
                        "consumer_type": class_name,
                        "parameter": parameter,
                        "functor_variable": variable,
                        "first_argument": first.strip()[:240],
                        "space_arg": _infer_space_argument(first, bindings),
                        "snippet": " ".join(text[line_start:line_end].split())[:700],
                    }
                )
    unique = {
        (row["path"], row["line"], row["functor_variable"], row["first_argument"]): row
        for row in rows
    }
    return list(unique.values()), [str(path.relative_to(root)) for path in files]


__all__ = [
    "CPP_TEXT_SUFFIXES",
    "FunctorInspectionError",
    "extract_functor_property_declaration",
    "parameter_functor_calls",
]
