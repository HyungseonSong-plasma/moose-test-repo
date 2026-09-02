from experiments.R3_electron_master_diagnostic.cases import build_case_text
from experiments.R3_electron_master_diagnostic.spec import CHEAP_CASES


def test_all_master_cases_construct_from_current_issue94_inputs():
    for spec in CHEAP_CASES:
        text = build_case_text(spec)
        assert f"R3 master diagnostic: {spec.case_id}" in text
        assert "[Variables]" in text
        assert "[FVKernels]" in text
        assert "diag_electron_diffusion_min" in text
        assert "diag_electron_diffusion_max" in text
