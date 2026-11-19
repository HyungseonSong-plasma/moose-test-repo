"""Evidence-based, domain-neutral impact, finding, assessment and graph diff."""

from .impact import (
    ImpactResult, TargetCoverage, analyze_impact, analyze_target_coverage,
)
from .findings import propose_finding
from .assessment import Assessment, assess_finding
from .diff import GraphDiff, compare_graphs

__all__ = [
    "ImpactResult", "analyze_impact",
    "TargetCoverage", "analyze_target_coverage",
    "propose_finding", "Assessment", "assess_finding",
    "GraphDiff", "compare_graphs",
]
