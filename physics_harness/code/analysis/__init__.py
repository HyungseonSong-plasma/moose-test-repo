"""Evidence-based, domain-neutral impact, finding, assessment and graph diff."""

from .impact import (
    ImpactResult, TargetCoverage, analyze_impact, analyze_target_coverage,
)
from .findings import propose_finding
from .assessment import Assessment, assess_finding
from .parameter_contract import (
    ParameterBlockAssessment, ParameterContractAssessment,
    assess_input_parameter_contract,
)
from .diff import GraphDiff, compare_graphs
from .file_references import (
    FileReferenceTarget, FileReferenceResolution, FileReferenceReport,
    resolve_file_references,
)
from .usage_matrix import (
    UsageRelation, UsageWitness, UsageReference, UsageRow,
    UsageMatrix, build_usage_matrix,
)
from .adapters import (
    assess_code_understandability, summarize_understandability,
    interpret_understandability_indicators,
)

__all__ = [
    "ImpactResult", "analyze_impact",
    "TargetCoverage", "analyze_target_coverage",
    "propose_finding", "Assessment", "assess_finding",
    "ParameterBlockAssessment", "ParameterContractAssessment",
    "assess_input_parameter_contract",
    "GraphDiff", "compare_graphs",
    "FileReferenceTarget", "FileReferenceResolution", "FileReferenceReport",
    "resolve_file_references",
    "UsageRelation", "UsageWitness", "UsageReference", "UsageRow",
    "UsageMatrix", "build_usage_matrix",
    "assess_code_understandability", "summarize_understandability",
    "interpret_understandability_indicators",
]
