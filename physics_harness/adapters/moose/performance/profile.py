"""MOOSE-specific textual performance-profile decoding."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_LIVE_MEMORY_RE = re.compile(
    r"(?P<label>.*?)"
    r"\[\s*(?P<seconds>[0-9]+(?:\.[0-9]+)?)\s*s\]\s*"
    r"\[\s*(?P<memory_mb>[0-9]+(?:\.[0-9]+)?)\s*MB\]"
)
_LINEAR_SOLVE_RE = re.compile(
    r"\bLinear solve\b.*\b(?:converged|diverged|failed)\b",
    re.IGNORECASE,
)


def _clean_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return _ANSI_RE.sub("", path.read_text(errors="replace"))


def _clean_label(raw: str) -> str:
    label = raw.strip()
    label = re.sub(r"\.+$", "", label).strip()
    return label or "<unlabeled>"


def live_memory_samples(path: Path | None) -> list[dict[str, Any]]:
    """Decode MOOSE live ``[seconds] [MB]`` resident-memory annotations."""
    text = _clean_text(path)
    samples: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        match = _LIVE_MEMORY_RE.search(line)
        if not match:
            continue
        samples.append(
            {
                "line": line_number,
                "label": _clean_label(match.group("label")),
                "seconds": float(match.group("seconds")),
                "resident_mb": float(match.group("memory_mb")),
            }
        )
    return samples


def _nearest_before(
    samples: list[dict[str, Any]], line_number: int
) -> dict[str, Any] | None:
    candidates = [sample for sample in samples if int(sample["line"]) < line_number]
    return candidates[-1] if candidates else None


def _nearest_after(
    samples: list[dict[str, Any]], line_number: int
) -> dict[str, Any] | None:
    return next(
        (sample for sample in samples if int(sample["line"]) > line_number),
        None,
    )


def resident_memory_profile(path: Path | None) -> dict[str, Any]:
    """Summarize phase-resolved live resident memory and linear-solve jumps.

    The returned memory values are process-resident observations emitted by
    MOOSE's live PerfGraph display. They are intentionally kept separate from
    PerfGraph section-allocation ``Mem(MB)`` values.
    """
    text = _clean_text(path)
    lines = text.splitlines()
    samples = live_memory_samples(path)
    transitions: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not _LINEAR_SOLVE_RE.search(line):
            continue
        before = _nearest_before(samples, line_number)
        after = _nearest_after(samples, line_number)
        item: dict[str, Any] = {
            "line": line_number,
            "message": line.strip(),
            "before": before,
            "after": after,
            "delta_mb": None,
            "ratio_after_before": None,
        }
        if before is not None and after is not None:
            before_mb = float(before["resident_mb"])
            after_mb = float(after["resident_mb"])
            item["delta_mb"] = after_mb - before_mb
            item["ratio_after_before"] = (
                after_mb / before_mb if before_mb > 0.0 else None
            )
        transitions.append(item)

    setup = next(
        (
            sample
            for sample in samples
            if sample["label"] == "Finished Performing Initial Setup"
        ),
        None,
    )
    user_objects = next(
        (
            sample
            for sample in samples
            if sample["label"] == "Finished Computing User Objects"
        ),
        None,
    )
    first_transition = transitions[0] if transitions else None
    peak = max(samples, key=lambda sample: float(sample["resident_mb"])) if samples else None

    return {
        "samples": samples,
        "first_sample": samples[0] if samples else None,
        "user_objects": user_objects,
        "initial_setup": setup,
        "linear_solve_transitions": transitions,
        "first_linear_solve": first_transition,
        "peak": peak,
    }


def perfgraph_heaviest_section_memory(path: Path | None) -> list[dict[str, Any]]:
    """Decode textual PerfGraph ``Heaviest Sections`` allocation-memory rows."""
    text = _clean_text(path)
    rows: list[dict[str, Any]] = []
    in_table = False
    for line in text.splitlines():
        if line.strip() == "Heaviest Sections:":
            in_table = True
            continue
        if not in_table or not line.lstrip().startswith("|"):
            continue
        if "Section" in line and "Mem(MB)" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            continue
        section, calls, self_s, avg_s, percent, memory_mb = cells
        try:
            rows.append(
                {
                    "section": section,
                    "calls": int(calls),
                    "self_seconds": float(self_s),
                    "avg_seconds": float(avg_s),
                    "percent_application": float(percent),
                    "allocated_mb": float(memory_mb),
                }
            )
        except ValueError:
            continue
    return rows


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


__all__ = [
    "jacobian_self_time",
    "live_memory_samples",
    "perfgraph_heaviest_section_memory",
    "resident_memory_profile",
]
