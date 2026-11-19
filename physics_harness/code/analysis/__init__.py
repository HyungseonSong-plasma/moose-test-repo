"""Evidence-based, domain-neutral impact, finding, assessment and graph diff."""

from .impact import ImpactResult, analyze_impact
from .findings import propose_finding
from .assessment import Assessment, assess_finding
from .diff import GraphDiff, compare_graphs

__all__ = [
    "ImpactResult", "analyze_impact",
    "propose_finding", "Assessment", "assess_finding",
    "GraphDiff", "compare_graphs",
]
