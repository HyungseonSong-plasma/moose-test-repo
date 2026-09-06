"""Issue-agnostic PETSc KSP identity, residual parsing, and fidelity facts."""
from __future__ import annotations

import math
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


def residual_fidelity_audit(
    rows: list[dict[str, float]],
    *,
    restart: int | None = None,
    ratio_threshold: float = 1.0e6,
) -> dict[str, Any]:
    """Summarize reported-vs-true KSP residual fidelity without assigning cause.

    PETSc may report a preconditioned/recursive residual that separates from the
    explicitly computed true residual.  This helper records that separation and
    whether observations happen to land on a GMRES restart boundary.  A restart
    boundary is chronology only; this function intentionally makes no causal
    claim about restart, conditioning, orthogonality loss, or formulation error.
    """
    if ratio_threshold <= 1.0:
        raise ValueError("ratio_threshold must be greater than 1")

    finite_rows = [
        row
        for row in rows
        if math.isfinite(row.get("reported_residual", math.nan))
        and math.isfinite(row.get("true_residual", math.nan))
        and math.isfinite(row.get("relative_true_residual", math.nan))
    ]
    samples: list[dict[str, Any]] = []
    for row in finite_rows:
        reported = abs(float(row["reported_residual"]))
        true = abs(float(row["true_residual"]))
        if reported == 0.0 and true == 0.0:
            ratio = 1.0
        elif reported == 0.0:
            ratio = math.inf
        elif true == 0.0:
            ratio = math.inf
        else:
            ratio = max(true / reported, reported / true)
        iteration = int(row["iteration"])
        at_restart_boundary = bool(
            isinstance(restart, int)
            and restart > 0
            and iteration > 0
            and iteration % restart == 0
        )
        samples.append(
            {
                **row,
                "residual_separation_ratio": ratio,
                "at_restart_boundary": at_restart_boundary,
            }
        )

    finite_ratios = [
        sample["residual_separation_ratio"]
        for sample in samples
        if math.isfinite(sample["residual_separation_ratio"])
    ]
    infinite_separation = any(
        not math.isfinite(sample["residual_separation_ratio"])
        for sample in samples
    )
    max_ratio = math.inf if infinite_separation else (max(finite_ratios) if finite_ratios else None)
    worst = None
    if samples:
        worst = max(
            samples,
            key=lambda sample: sample["residual_separation_ratio"],
        )

    first = samples[0] if samples else None
    last = samples[-1] if samples else None
    reported_reduction = None
    true_reduction = None
    if first is not None and last is not None:
        first_reported = abs(float(first["reported_residual"]))
        first_true = abs(float(first["true_residual"]))
        if first_reported > 0.0:
            reported_reduction = abs(float(last["reported_residual"])) / first_reported
        if first_true > 0.0:
            true_reduction = abs(float(last["true_residual"])) / first_true

    fidelity_loss = bool(
        max_ratio is not None
        and (not math.isfinite(max_ratio) or max_ratio >= ratio_threshold)
    )
    return {
        "sample_count": len(rows),
        "finite_sample_count": len(samples),
        "ratio_threshold": ratio_threshold,
        "max_residual_separation_ratio": max_ratio,
        "worst_iteration": worst["iteration"] if worst is not None else None,
        "worst_at_restart_boundary": (
            worst["at_restart_boundary"] if worst is not None else False
        ),
        "restart": restart,
        "restart_boundary_observed": any(
            sample["at_restart_boundary"] for sample in samples
        ),
        "reported_residual_reduction": reported_reduction,
        "true_residual_reduction": true_reduction,
        "residual_fidelity_loss_observed": fidelity_loss,
        "causal_attribution": "NOT_ESTABLISHED",
        "samples": samples,
    }


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
