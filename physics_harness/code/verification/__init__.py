"""Evidence-driven, policy-free Code Verification v0.1.

Source-snapshot verification is not evidence of runtime or semantic parity.
"""

from .consistency import VerificationReceipt, verify_generated_artifact
from .post_change import ChangeVerificationPlan, plan_change_verification

__all__ = [
    "ChangeVerificationPlan", "VerificationReceipt",
    "plan_change_verification", "verify_generated_artifact",
]
