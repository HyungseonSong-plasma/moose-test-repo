"""Generic claim assessment and MOOSE contract logic retain public compatibility."""

from physics_harness.code import analysis
from physics_harness.code.analysis import assessment, parameter_contract


def test_public_assessment_exports_preserve_legacy_import_identity():
    names = (
        "ParameterBlockAssessment",
        "ParameterContractAssessment",
        "assess_input_parameter_contract",
    )
    for name in names:
        assert getattr(analysis, name) is getattr(parameter_contract, name)
        assert getattr(assessment, name) is getattr(parameter_contract, name)
        assert name in assessment.__all__


def test_moose_contract_types_remain_fail_closed_when_imported_from_old_location():
    blocked = assessment.ParameterBlockAssessment(
        "block", ("INVALID_DECLARED_ENUM:state_form:bad",), (),
    )
    held = assessment.ParameterBlockAssessment("block", (), ("UNKNOWN",))
    qualified = assessment.ParameterBlockAssessment("block", (), ())
    assert (blocked.disposition, held.disposition, qualified.disposition) == (
        "BLOCKED", "HOLD", "CANDIDATE_FOR_VERIFICATION",
    )
    result = assessment.ParameterContractAssessment(
        target_id="moose:type", blocks=(held,), blockers=("INCOMPLETE",),
        disposition="HOLD", verification_obligations=("VERIFY_NATIVE",),
    )
    assert not result.actionable_without_verification
    assert result.blocks == (held,)
