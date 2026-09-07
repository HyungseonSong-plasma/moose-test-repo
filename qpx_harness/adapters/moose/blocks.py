"""Reusable structural block mutations for MOOSE HIT input text.

This module owns syntax-preserving block mechanics only. It must not know any
physics variable, Issue number, solver policy, or experiment identity.
"""
from __future__ import annotations

from .input import MooseInput, MooseInputError


class MooseBlockError(ValueError):
    """Raised when a structural block mutation is ambiguous or invalid."""


def has_block(text: str, path: str) -> bool:
    """Return whether one or more blocks match ``path``."""
    return bool(MooseInput(text).find(path))


def require_absent(text: str, path: str) -> None:
    """Reject a mutation when ``path`` already exists."""
    if has_block(text, path):
        raise MooseBlockError(f"block already exists: {path}")


def append_top_level_block(text: str, block_text: str) -> str:
    """Append one complete top-level block and validate the resulting input."""
    payload = block_text.strip("\n")
    if not payload:
        raise MooseBlockError("top-level block payload must not be empty")
    prefix = text
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix and not prefix.endswith("\n\n"):
        prefix += "\n"
    out = prefix + payload + "\n"
    try:
        MooseInput(out)
    except MooseInputError as exc:
        raise MooseBlockError(f"invalid appended top-level block: {exc}") from exc
    return out


def insert_child_block(text: str, parent: str, block_text: str) -> str:
    """Insert one complete child block immediately before a parent's close."""
    payload = block_text.rstrip()
    if not payload:
        raise MooseBlockError("child block payload must not be empty")
    try:
        out = MooseInput(text).insert_before_close(parent, payload)[0]
        MooseInput(out)
    except MooseInputError as exc:
        raise MooseBlockError(f"failed to insert child block under {parent}: {exc}") from exc
    return out


def remove_block(text: str, path: str) -> str:
    """Remove exactly one block selected by ``path``."""
    try:
        span = MooseInput(text).unique(path)
    except MooseInputError as exc:
        raise MooseBlockError(f"failed to locate unique block {path}: {exc}") from exc
    out = text[: span.start] + text[span.end :]
    try:
        MooseInput(out)
    except MooseInputError as exc:
        raise MooseBlockError(f"invalid input after removing {path}: {exc}") from exc
    return out


def replace_block(text: str, path: str, replacement: str) -> str:
    """Replace exactly one block selected by ``path`` with complete block text."""
    try:
        span = MooseInput(text).unique(path)
    except MooseInputError as exc:
        raise MooseBlockError(f"failed to locate unique block {path}: {exc}") from exc
    payload = replacement.rstrip() + "\n"
    out = text[: span.start] + payload + text[span.end :]
    try:
        MooseInput(out)
    except MooseInputError as exc:
        raise MooseBlockError(f"invalid replacement for {path}: {exc}") from exc
    return out
