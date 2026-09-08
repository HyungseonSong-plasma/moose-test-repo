"""MOOSE-specific textual performance-profile decoding."""
from __future__ import annotations

import re
from pathlib import Path


def jacobian_self_time(path: Path | None) -> dict[str, float] | None:
    """Decode MOOSE's Jacobian timer row from a textual PerfGraph table."""
    if path is None or not path.is_file():
        return None
    text = path.read_text(errors="replace")
    pattern = re.compile(
        r"^\|\s*NonlinearSystemBase::computeJacobianInternal\s*"
        r"\|\s*(\d+)\s*\|\s*([0-9.eE+-]+)\s*\|\s*([0-9.eE+-]+)\s*"
        r"\|\s*([0-9.eE+-]+)\s*\|",
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    if not matches:
        return None
    calls, self_s, avg_s, percent = max(matches, key=lambda match: float(match[1]))
    return {
        "calls": float(calls),
        "self_seconds": float(self_s),
        "avg_seconds": float(avg_s),
        "percent_application": float(percent),
    }


__all__ = ["jacobian_self_time"]
