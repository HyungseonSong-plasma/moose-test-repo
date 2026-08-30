#!/usr/bin/env python3
"""P0 behavior characterization for the thin Issue46 FD-reference recipe."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import augmented_jacobian_localization as legacy_loc
from qpx_harness import jacobian_fd_reference_audit as legacy
from qpx_harness import petsc_first_linear_diagnostic as legacy_first
from recipes import issue46_fd_reference as recipe


def _assert_same(left, right, label: str) -> None:
    if left != right:
        raise AssertionError(f"{label} drift: {left!r} != {right!r}")


def _baseline_text() -> str:
    base = legacy._issue46_synthetic_constrained_input(legacy.TARGET)
    first_text, _ = legacy_first.instrument_first_linear(base)
    baseline, _ = legacy_loc.instrument_localization(first_text)
    return baseline


def _check_predictor_and_construction() -> None:
    for vector_norm, component_value in ((123.0, 7.0), (3.2e17, 1.0e16)):
        _assert_same(
            recipe.predict_fd_step_quantization(
                vector_norm=vector_norm,
                component_value=component_value,
            ),
            legacy.predict_fd_step_quantization(
                vector_norm=vector_norm,
                component_value=component_value,
            ),
            "explicit predictor",
        )
    _assert_same(
        recipe.historical_evr1_prediction(),
        legacy._historical_evr1_prediction(),
        "historical predictor",
    )
    _assert_same(
        recipe.historical_mechanism_evidence(),
        legacy._historical_mechanism_evidence(),
        "historical mechanism evidence",
    )

    baseline = _baseline_text()
    old_text, old_meta = legacy.instrument_ds_reference(baseline)
    new_text, new_meta = recipe.instrument_ds_reference(baseline)
    _assert_same(new_text, old_text, "DS input construction")
    _assert_same(new_meta, old_meta, "DS construction metadata")
    _assert_same(
        recipe.remove_fd_type_pair(new_text),
        legacy._remove_fd_type_pair(old_text),
        "DS option removal",
    )


def _check_directional_localization() -> None:
    log = legacy._synthetic_log(
        4.0e-5,
        ["row 0: (4, 0.0)", "row 4: (0, 2.0e-4)"],
    )
    dofmap = legacy._synthetic_dofmap()
    old = legacy.directional_localization(log, dofmap)
    new = recipe.directional_localization(log, dofmap)
    _assert_same(new, old, "directional localization")


def _check_termination_and_applicability() -> None:
    cases = (
        (legacy._synthetic_log(5.0e-11, []), 1),
        (legacy._synthetic_log(5.0e-11, []) + "Segmentation fault (core dumped)\n", 139),
        ("runtime completed\n", 0),
        ("runtime failed\n", 2),
    )
    for text, rc in cases:
        old = legacy._termination_admissibility(text, returncode=rc)
        new = recipe.termination_admissibility(text, returncode=rc)
        _assert_same(new["status"], old["status"], "termination status")
        _assert_same(new["class"], old["class"], "termination class")
        _assert_same(new["reason"], old["reason"], "termination reason")

    for text in (
        "PETSc Release Version 3.25.2\n",
        "PETSC_VERSION=3.24.0\n",
        "no version here\n",
    ):
        _assert_same(
            recipe.runtime_mechanism_applicability(text),
            legacy._runtime_mechanism_applicability(text),
            "runtime mechanism applicability",
        )


def _provenance_kwargs(*, log_preexisting: bool = False, input_after: str = "abc"):
    root = Path("/tmp/issue46-evidence")
    case = root / "c0_ds_reference"
    return {
        "root": root,
        "case_dir": case,
        "input_path": case / "input.i",
        "source_case": Path("/tmp/issue46-source-case"),
        "input_sha_before": "abc",
        "input_sha_after": input_after,
        "log_path": root / "p3_c0_ds_reference.log",
        "log_preexisting": log_preexisting,
        "log_exists": True,
        "dofmap_path": case / "r46_dofmap.json",
        "dofmap_preexisting": False,
        "dofmap_exists": True,
        "source_dofmaps_before": (),
        "source_dofmaps_after": (),
    }


def _check_provenance() -> None:
    for kwargs in (
        _provenance_kwargs(),
        _provenance_kwargs(log_preexisting=True),
        _provenance_kwargs(input_after="drift"),
    ):
        _assert_same(
            recipe.evidence_provenance_status(**kwargs),
            legacy._evidence_provenance_status(**kwargs),
            "evidence provenance",
        )


def _check_final_discriminator() -> None:
    identity = {
        "status": "PASS",
        "class": "ISSUE46_EXPERIMENT_IDENTITY_PASS",
        "reason": "characterized identity",
    }
    applicability = {
        "status": "PASS",
        "class": "PETSC_WP_MECHANISM_APPLICABILITY_PASS",
        "reason": "characterized applicability",
        "reference_version": "3.25.2",
        "runtime_version": "3.25.2",
    }
    dofmap = legacy._synthetic_dofmap()
    cases = (
        legacy._synthetic_log(5.0e-11, []),
        legacy._synthetic_log(4.0e-5, ["row 4: (0, 2.0e-4)"]),
        legacy._synthetic_log(5.0e-11, []).split("Linear solve", 1)[0],
    )
    for log in cases:
        old = legacy.analyze_ds_runtime(
            log,
            dofmap,
            returncode=1,
            experiment_identity=identity,
            mechanism_applicability=applicability,
        )
        new = recipe.analyze_ds_runtime(
            log,
            dofmap,
            returncode=1,
            experiment_identity=identity,
            mechanism_applicability=applicability,
        )
        for key in ("status", "class", "reason", "ds_discriminator", "prediction"):
            _assert_same(new.get(key), old.get(key), f"final discriminator {key}")
        if "directional" in old:
            _assert_same(new.get("directional"), old.get("directional"), "final directional")


def _check_dependency_boundary() -> None:
    source = (ROOT / "recipes/issue46_fd_reference.py").read_text()
    forbidden = (
        "augmented_jacobian_localization",
        "electron_inventory_nullspace",
        "jacobian_fd_reference_audit",
        "petsc_first_linear_diagnostic",
        "fast_plasma_coupling_diagnostic",
    )
    for token in forbidden:
        if token in source:
            raise AssertionError(f"legacy reverse dependency leaked into Issue46 recipe: {token}")
    required = (
        "qpx_harness.petsc",
        "qpx_harness.moose",
        "qpx_harness import artifacts",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"Issue46 recipe does not compose required generic layer: {token}")


def main() -> int:
    try:
        _check_predictor_and_construction()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: predictor-and-construction=PASS")
        _check_directional_localization()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: directional-localization=PASS")
        _check_termination_and_applicability()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: termination-and-applicability=PASS")
        _check_provenance()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: evidence-provenance=PASS")
        _check_final_discriminator()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: final-discriminator=PASS")
        _check_dependency_boundary()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: recipe-reverse-dependency=NONE")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE46_FD_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE46_FD_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
