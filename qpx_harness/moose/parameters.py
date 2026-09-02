"""Structure-aware, experiment-agnostic MOOSE parameter operations."""
from __future__ import annotations

import re

from .input import MooseInput, MooseInputError


class MooseParameterError(RuntimeError):
    """Raised when a MOOSE parameter operation is structurally ambiguous or invalid."""


def unquote(value: str | None) -> str | None:
    if value is None:
        return None
    result = value.strip()
    if len(result) >= 2 and result[0] == result[-1] and result[0] in {"'", '"'}:
        result = result[1:-1]
    return result.strip()


def words(value: str | None) -> list[str]:
    raw = unquote(value)
    return raw.split() if raw else []


def _matches(text: str, path: str, name: str) -> tuple[object, str, list[re.Match[str]]]:
    try:
        span = MooseInput(text).unique(path)
    except MooseInputError as exc:
        raise MooseParameterError(f"cannot resolve block {path}: {exc}") from exc
    block = text[span.start : span.end]
    pattern = re.compile(
        rf"(?m)^(?P<prefix>\s*{re.escape(name)}\s*=\s*)"
        rf"(?P<value>[^#\r\n]*?)"
        rf"(?P<suffix>\s*(?:#.*)?$)"
    )
    return span, block, list(pattern.finditer(block))


def parameter_count(text: str, path: str, name: str) -> int:
    return len(_matches(text, path, name)[2])


def get_parameter(text: str, path: str, name: str) -> str | None:
    _, _, matches = _matches(text, path, name)
    if len(matches) > 1:
        raise MooseParameterError(
            f"ambiguous parameter {path}/{name}: {len(matches)} assignments"
        )
    return matches[0].group("value").strip() if matches else None


def upsert_parameter(text: str, path: str, name: str, value: str) -> str:
    count = parameter_count(text, path, name)
    if count > 1:
        raise MooseParameterError(
            f"ambiguous parameter {path}/{name}: {count} assignments"
        )
    try:
        if count == 1:
            out = MooseInput(text).replace_parameters(path, {name: value})[0]
        else:
            out = MooseInput(text).insert_before_close(path, f"  {name} = {value}")[0]
        MooseInput(out)
        return out
    except MooseInputError as exc:
        raise MooseParameterError(f"failed to set {path}/{name}: {exc}") from exc


def direct_children(text: str, parent: str) -> list[str]:
    depth = parent.count("/") + 1
    prefix = parent + "/"
    return sorted(
        block.path
        for block in MooseInput(text).blocks
        if block.path.startswith(prefix) and block.path.count("/") == depth
    )
