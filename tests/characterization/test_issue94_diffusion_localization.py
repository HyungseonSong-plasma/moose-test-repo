from __future__ import annotations

from pathlib import Path

from experiments.Issue93_r3_electron_isolation.operator_decomposition import (
    build_case_input,
)
from experiments.Issue93_r3_electron_isolation.prepare import (
    ELECTRON_REFERENCE_CASE,
    EXPECTED_MESH_SHA256,
    SOURCE_CASE,
)
from experiments.Issue94_r3_electron_diffusion_localization.localization import (
    CASE_ORDER,
    FROZEN_DIFFUSION,
    FROZEN_MOBILITY,
    _QPX_TRANSPORT_BLOCK,
    build_localization_input,
    classify_first_failure,
    frozen_transport_values,
    prepare_batch,
)


def _strip_issue94_marker(text: str) -> str:
    lines = text.splitlines(keepends=True)
    while lines and lines[0].startswith("# Issue #94"):
        lines.pop(0)
        if lines and lines[0].startswith("# QPX lookup"):
            lines.pop(0)
    return "".join(lines)


def test_issue94_frozen_transport_matches_accepted_issue2_state() -> None:
    values = frozen_transport_values(ELECTRON_REFERENCE_CASE)
    assert values["electron_diffusion"] == FROZEN_DIFFUSION
    assert values["electron_mobility"] == FROZEN_MOBILITY


def test_issue94_l0_and_l3_are_exact_issue93_controls() -> None:
    assert build_localization_input("L0", ELECTRON_REFERENCE_CASE) == build_case_input(
        "C1", ELECTRON_REFERENCE_CASE
    )
    assert build_localization_input("L3", ELECTRON_REFERENCE_CASE) == build_case_input(
        "C2", ELECTRON_REFERENCE_CASE
    )


def test_issue94_l1_changes_only_diffusion_coefficient_owner() -> None:
    c2 = build_case_input("C2", ELECTRON_REFERENCE_CASE)
    l1 = build_localization_input("L1", ELECTRON_REFERENCE_CASE)
    assert f"    coeff = {repr(FROZEN_DIFFUSION)}\n" in l1
    assert "    coeff = electron_diffusion\n" not in l1
    assert "type = QPXElectronTransportLookupMaterial" in l1

    recovered = _strip_issue94_marker(l1).replace(
        f"    coeff = {repr(FROZEN_DIFFUSION)}\n",
        "    coeff = electron_diffusion\n",
        1,
    )
    assert recovered == c2


def test_issue94_l2_replaces_only_qpx_lookup_with_generic_constant_ad_functors() -> None:
    c2 = build_case_input("C2", ELECTRON_REFERENCE_CASE)
    l2 = build_localization_input("L2", ELECTRON_REFERENCE_CASE)
    assert "type = QPXElectronTransportLookupMaterial" not in l2
    assert "type = ADGenericFunctorMaterial" in l2
    assert "prop_names = 'electron_mobility electron_diffusion'" in l2
    assert (
        f"prop_values = '{repr(FROZEN_MOBILITY)} {repr(FROZEN_DIFFUSION)}'" in l2
    )
    assert "    coeff = electron_diffusion\n" in l2

    stripped = _strip_issue94_marker(l2)
    generic_start = stripped.index("  [electron_transport]\n")
    generic_end = stripped.index("  []\n", generic_start) + len("  []\n")
    recovered = stripped[:generic_start] + _QPX_TRANSPORT_BLOCK + stripped[generic_end:]
    assert recovered == c2


def test_issue94_prepare_batch_preserves_real_qvt_identity_and_no_runtime(tmp_path: Path) -> None:
    manifest = prepare_batch(
        tmp_path / "issue94", SOURCE_CASE, ELECTRON_REFERENCE_CASE
    )
    assert manifest["qpx_executed"] is False
    assert manifest["scientific_evr_consumed"] == 0
    assert manifest["identity"]["mesh_sha256"] == EXPECTED_MESH_SHA256
    assert manifest["case_order"] == list(CASE_ORDER)
    assert manifest["frozen_transport"]["electron_diffusion"] == FROZEN_DIFFUSION

    for case_id in CASE_ORDER:
        case_dir = Path(manifest["cases"][case_id]["case_dir"])
        assert (case_dir / "input.i").is_file()
        assert (case_dir / "qvt.msh").is_file()
        assert (case_dir / "electron_moments.txt").is_file()
        assert (case_dir / "expected.json").is_file()


def test_issue94_decision_tree_maps_first_failed_layer() -> None:
    expected = {
        "L0": "L0_CURRENT_EXECUTABLE_CONTROL_REGRESSION_HOLD",
        "L1": "FRAMEWORK_FV_DIFFUSION_BLOCK_GEOMETRY_FAVORED",
        "L2": "GENERIC_FUNCTOR_MATERIAL_COUPLING_FAVORED",
        "L3": "QPX_ELECTRON_TRANSPORT_LOOKUP_FUNCTOR_FAVORED",
        None: "ALL_RESIDUAL_CASES_PASS_JACOBIAN_ONLY_FOLLOWUP",
    }
    for case_id, decision_expected in expected.items():
        decision, hypotheses = classify_first_failure(case_id)
        assert decision == decision_expected
        if case_id == "L1":
            assert hypotheses["FRAMEWORK_FV_DIFFUSION_BLOCK_GEOMETRY"] == "FAVORED"
        elif case_id == "L2":
            assert hypotheses["GENERIC_FUNCTOR_MATERIAL_COUPLING"] == "FAVORED"
        elif case_id == "L3":
            assert hypotheses["QPX_ELECTRON_TRANSPORT_LOOKUP_FUNCTOR"] == "FAVORED"
        elif case_id is None:
            assert hypotheses["JACOBIAN_ONLY_FOLLOWUP"] == "FAVORED"
