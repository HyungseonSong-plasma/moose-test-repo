"""Issue-agnostic parsers for MOOSE console value blocks."""
from __future__ import annotations

import re

FLOAT_PATTERN = r"[+\-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|nan|inf(?:inity)?)"


def parse_variable_residual_norms(text: str) -> list[dict[str, float]]:
    """Parse MOOSE ``|residual|_2 of individual variables`` blocks."""
    blocks: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for line in text.splitlines():
        if "|residual|_2 of individual variables:" in line:
            current = {}
            blocks.append(current)
            continue
        if current is None:
            continue
        match = re.match(
            rf"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*({FLOAT_PATTERN})\s*$",
            line,
            re.IGNORECASE,
        )
        if match:
            try:
                current[match.group(1)] = float(match.group(2))
            except ValueError:
                pass
        elif line.strip() and current:
            current = None
    return [block for block in blocks if block]


def parse_automatic_scaling_factors(text: str) -> list[dict[str, float]]:
    """Parse MOOSE ``Automatic scaling factors`` blocks."""
    blocks: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for line in text.splitlines():
        if line.strip() == "Automatic scaling factors:":
            current = {}
            blocks.append(current)
            continue
        if current is None:
            continue
        match = re.match(
            rf"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*({FLOAT_PATTERN})(?:\s+.*)?$",
            line,
            re.IGNORECASE,
        )
        if match:
            try:
                current[match.group(1)] = float(match.group(2))
            except ValueError:
                pass
        elif not line.strip():
            current = None
        elif current:
            current = None
    return [block for block in blocks if block]
