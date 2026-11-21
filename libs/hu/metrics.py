"""Convert source-bound structural observations to descriptive HU covariates.

These are NOT a calibrated HU score. AST collection remains owned by Diagnostics.
"""

from __future__ import annotations

from collections.abc import Mapping

from .model import StructuralMetric

# The currently measured Python AST fields. New collectors may supply metrics
# directly without adding a new strategy to this module.
PYTHON_AST_FIELDS = ("loc", "branches", "max_branch_nesting")


def from_python_ast(
    attributes: Mapping[str, object], *, evidence_ids: tuple[str, ...] = (),
) -> tuple[StructuralMetric, ...]:
    """Use the *existing* collector's AST counts; never recompute them here."""
    measured = []
    for name in PYTHON_AST_FIELDS:
        value = attributes.get(name)
        if type(value) is int and value >= 0:
            measured.append(StructuralMetric(
                name=name, value=value, method="python_ast", evidence_ids=evidence_ids,
            ))
    return tuple(measured)
