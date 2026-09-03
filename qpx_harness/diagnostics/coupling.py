"""Compatibility API for coupled runtime analysis via Evidence -> Diagnose."""
from __future__ import annotations

from typing import Any, Iterable

from qpx_harness.diagnose import diagnose_coupled_runtime_evidence
from qpx_harness.evidence import runtime_core_facts
from qpx_harness.petsc.log import line_hits


def analyze_runtime_failure(
    text: str,
    *,
    returncode: int,
    coupled_scaling_variables: Iterable[str] = (),
) -> dict[str, Any]:
    evidence = runtime_core_facts(
        text,
        returncode=returncode,
        coupled_scaling_variables=coupled_scaling_variables,
    )
    return diagnose_coupled_runtime_evidence(evidence)


__all__ = ["analyze_runtime_failure", "line_hits"]
