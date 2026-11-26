"""Shared lexical HIT primitives; deliberately no block-stack or edit policy."""
from __future__ import annotations

import re

_ADAPTER_BLOCK = re.compile(r"^\s*\[([^\]]*)\]\s*(?:#.*)?$")


def adapter_block_token(raw_line: str) -> str | None:
    """Preserve the adapter's original regex, including inline comments."""
    match = _ADAPTER_BLOCK.match(raw_line.rstrip("\r\n"))
    return match.group(1).strip() if match else None


def collector_block_token(line: str) -> str | None:
    """Read the collector's already uncommented and stripped line."""
    return line[1:-1].strip() if line.startswith("[") and line.endswith("]") else None


def is_block_close(token: str) -> bool:
    return token in {"", "../"}


def strip_child_prefix(token: str) -> str:
    return token[2:] if token.startswith("./") else token
