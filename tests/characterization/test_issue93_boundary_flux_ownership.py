from __future__ import annotations

from pathlib import Path

from experiments.Issue93_r3_electron_isolation.boundary_flux_ownership import (
    PLASMA_INTERFACE_BOUNDARIES,
    build_boundary_excluded_input,
    build_jacobian_input,
    prepare_batch,
    residual_trace_is_zero,
)
from experiments.Issue93_r3_electron_isolation.operator_decomposition import (
    build_case_input,
)
from experiments.Issue93_r3_electron_isolation.prepare import (
    ELECTRON_REFERENCE_CASE,
    EXPECTED_MESH_SHA256,
    SOURCE_CASE,
)


def test_issue93_j3_boundary_excluded_case_is_exact_c2_derivative() -> None:
    c2 = build_case_input("C2", ELECTRON_REFERENCE_CASE)
    d0 = build_boundary_excluded_input(ELECTRON_REFERENCE_CASE)

    assert "type = FVDiffusion" in d0
    assert "type = QPXFVElectrostaticDrift" not in d0
    assert "expression = '0.0*x'" in d0
    assert "dt = 1e-8" in d0

    boundary_text = " ".join(PLASMA_INTERFACE_BOUNDARIES)
    assert f"boundaries_to_avoid = '{boundary_text}'" in d0
    assert d0.count("boundaries_to_avoid") == 1

    # Removing only the J3 marker and the new assignment recovers exact J2 C2.
    payload = d0.splitlines(keepends=True)[2:]
    recovered = "".join(payload).replace(
        f"    boundaries_to_avoid = '{boundary_text}'\n", "", 1
    )
    assert recovered == c2


def test_issue93_j3_jacobian_fallback_is_exact_original_c2() -> None:
    assert build_jacobian_input(ELECTRON_REFERENCE_CASE) == build_case_input(
        "C2", ELECTRON_REFERENCE_CASE
    )


def test_issue93_j3_prepare_batch_preserves_identity_and_evr(tmp_path: Path) -> None:
    manifest = prepare_batch(
        tmp_path / "j3", SOURCE_CASE, ELECTRON_REFERENCE_CASE
    )
    assert manifest["qpx_executed"] is False
    assert manifest["scientific_evr_consumed"] == 0
    assert manifest["identity"]["mesh_sha256"] == EXPECTED_MESH_SHA256
    assert manifest["case_order"] == ["D0", "JAC"]
    assert manifest["plasma_interface_boundaries"] == list(
        PLASMA_INTERFACE_BOUNDARIES
    )

    for case_id in ("D0", "JAC"):
        case_dir = Path(manifest["cases"][case_id]["case_dir"])
        assert (case_dir / "input.i").is_file()
        assert (case_dir / "qvt.msh").is_file()
        assert (case_dir / "electron_moments.txt").is_file()
        assert (case_dir / "expected.json").is_file()


def test_issue93_j3_zero_residual_contract_is_strict() -> None:
    assert residual_trace_is_zero([0.0, 0.0])
    assert residual_trace_is_zero([1.0e-14, 2.0e-13])
    assert not residual_trace_is_zero([])
    assert not residual_trace_is_zero([1.0e-9])
