"""P0: isolated case selection, per-lane evidence and failure controls."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import issue652_g6_runtime_gate as g6
import issue652_g6b_parallel_evidence as evidence


@pytest.mark.parametrize("raw,wanted", [
    (None, ("417", "941")), ("417", ("417",)), ("941", ("941",)),
])
def test_case_selector(raw, wanted):
    assert g6.selected_cases(raw) == wanted


@pytest.mark.parametrize("raw", ["999", "", "../417", "417,941", "all"])
def test_case_selector_rejects_unapproved(raw):
    with pytest.raises(ValueError, match="ALLOWLIST"):
        g6.selected_cases(raw)


def test_exact_one_or_both_case_loop_and_protected_lifecycle():
    source = (ROOT / "ci/guards/issue652_g6_runtime_gate.py").read_text()
    assert "for case in cases:" in source
    assert "for name in sorted(REQUIRED[case]):" in source
    assert "secure_tmpfs_cleanup(private)" in source
    assert "secure_tmpfs_cleanup(protected)" in source
    assert 'parser.add_argument("--case", choices=CASES' in source
    assert '"P4_100us": "NOT_RUN"' in source


def _valid_public(source):
    case = {
        "new_lookup_sha256": evidence.SOURCE_100_SHA,
        "P0": "PASS_SCRATCH_ONLY_100ROW_PROVENANCE",
        "science": "SCIENCE_HOLD", "P3_100us": "NOT_RUN",
        "unchanged_11_layer_sha256": {str(k): "a" * 64 for k in range(11)},
        "time": {"time_points": 461, "intervals": 460, "end_time_seconds": 1e-4},
    }
    return {
        "schema": "issue652.g6b.publicd100.stage.v1",
        "source_sha": source, "original_publicd_lookup_sha256": evidence.SOURCE_100_SHA,
        "lookup_rows": 100, "protected_rate_data_in_receipt": False,
        "cases": {"417": case, "941": case},
    }


def _valid_native(source, case):
    return {
        "schema": "issue652.g6.registration_p3.v1",
        "source_sha": source, "oci": evidence.OCI,
        "binary_sha256": "1" * 64, "observer_sha256": "2" * 64,
        "raw_private_rates_in_artifact": False,
        "science": "SCIENCE_HOLD", "P4_100us": "NOT_RUN",
        "registration": "PASS_TYPED_15_OWNERS",
        "P3_3ns": "PASS_FINITE_3NS_NO_BASELINE_PARITY",
        "cases": {case: {
            "P2_syntax_ok": True, "P2_trace_return_code": 0,
            "P3_return_code": 0,
            "registration": {
                "status": "EXPECTED_15_GENERATED_OWNERS_TRACE_PASS",
                "observed_expected_owners": {str(i): "kind" for i in range(15)},
            },
            "P3_3ns": {
                "status": "SHORT_3NS_POSTPROCESSORS_FINITE",
                "time_rows": 4, "final_seconds": 3e-9,
                "baseline_semantic_parity": "NOT_EVALUATED",
                "charge_conservation_residual": "NOT_MEASURED",
            },
        }},
    }


def test_both_independent_cases_and_negative_controls():
    source = "a" * 40
    manifest = {"files": {
        "physics_app/physics-opt": "1" * 64,
        "physics_app/g6_owner_tracer.so": "2" * 64,
    }}
    public = _valid_public(source)
    for case in evidence.CASES:
        receipt = evidence.validate_case(public, _valid_native(source, case),
                                         manifest, case, source)
        assert receipt["case_id"] == case
        assert receipt["scientific_status"] == "HOLD"
        assert receipt["P4_100us"] == "NOT_RUN"
    with pytest.raises(evidence.ParallelEvidenceHold, match="SCOPE"):
        evidence.validate_case(public, _valid_native(source, "417"),
                               manifest, "941", source)
    corrupted = _valid_native(source, "941")
    corrupted["cases"]["941"]["P3_3ns"]["final_seconds"] = 0.0
    with pytest.raises(evidence.ParallelEvidenceHold, match="3NS_EVIDENCE"):
        evidence.validate_case(public, corrupted, manifest, "941", source)
