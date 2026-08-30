"""Issue-agnostic PETSc KSP identity and residual parsing."""
from __future__ import annotations

import re
from typing import Any

FLOAT_PATTERN = r"[+\-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|nan|inf(?:inity)?)"


def parse_true_residuals(text: str) -> list[dict[str, float]]:
    """Parse KSP reported and true residual monitor rows."""
    pattern = re.compile(
        rf"(?m)^\s*(\d+)\s+KSP\s+.*?resid norm\s+({FLOAT_PATTERN})\s+true resid norm\s+({FLOAT_PATTERN})\s+\|\|r\(i\)\|\|/\|\|b\|\|\s+({FLOAT_PATTERN})\s*$",
        re.IGNORECASE,
    )
    rows: list[dict[str, float]] = []
    for match in pattern.finditer(text):
        try:
            rows.append(
                {
                    "iteration": int(match.group(1)),
                    "reported_residual": float(match.group(2)),
                    "true_residual": float(match.group(3)),
                    "relative_true_residual": float(match.group(4)),
                }
            )
        except ValueError:
            pass
    return rows


def parse_ksp_view(text: str) -> dict[str, Any]:
    """Parse the first PETSc KSP/PC identity block."""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("KSP Object:")),
        None,
    )
    if start is None:
        return {}

    base_indent = len(lines[start]) - len(lines[start].lstrip())
    ksp_type: str | None = None
    restart: int | None = None
    pc_type: str | None = None
    in_pc = False

    for line in lines[start + 1 :]:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("KSP Object:") and indent <= base_indent:
            break
        if stripped.startswith("PC Object:") and indent <= base_indent + 2:
            in_pc = True
            continue
        type_match = re.match(r"type:\s+(\S+)", stripped)
        if type_match:
            if in_pc and pc_type is None:
                pc_type = type_match.group(1).lower()
            elif not in_pc and ksp_type is None:
                ksp_type = type_match.group(1).lower()
        if not in_pc and restart is None:
            restart_match = re.search(r"\brestart\s*=\s*(\d+)", stripped)
            if restart_match:
                restart = int(restart_match.group(1))
        if in_pc and pc_type is not None and ksp_type is not None:
            break

    return {"ksp_type": ksp_type, "restart": restart, "pc_type": pc_type}
