"""Evidence-driven, policy-free Code Verification v0.1.

Source-snapshot verification is not evidence of runtime or semantic parity.
"""

from .engine import (
    ChangeVerificationPlan, VerificationReceipt,
    plan_change_verification, verify_generated_artifact,
)

__all__ = [
    "ChangeVerificationPlan", "VerificationReceipt",
    "plan_change_verification", "verify_generated_artifact",
]
