"""Evidence-driven, policy-free Code Verification v0.1.

Source-snapshot verification is not evidence of runtime or semantic parity.
"""

from .consistency import VerificationReceipt, verify_generated_artifact
from .dependencies import (
    ChangeVerificationPlan, DependencyContract, DependencyFinding,
    DependencyRule, DependencyVerification, plan_change_verification,
    verify_dependencies, verify_dependency_repository,
)
from .naming_provenance import (
    NamingSourceVerification, verify_naming_evidence_sources,
)

__all__ = [
    "ChangeVerificationPlan", "VerificationReceipt",
    "plan_change_verification", "verify_generated_artifact",
    "DependencyContract", "DependencyFinding", "DependencyRule",
    "DependencyVerification", "verify_dependencies",
    "verify_dependency_repository",
    "NamingSourceVerification", "verify_naming_evidence_sources",
]
