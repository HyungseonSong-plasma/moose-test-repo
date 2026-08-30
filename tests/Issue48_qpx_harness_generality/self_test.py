"""P0 characterization for reusable MOOSE/PETSc mutation primitives.

This test intentionally knows concrete examples; the production primitives must not.
"""
from __future__ import annotations

from pathlib import Path

from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import options as po
from qpx_harness import augmented_jacobian_localization as issue46_legacy
from qpx_harness import fast_plasma_coupling_diagnostic as issue43_legacy
from qpx_harness import petsc_first_linear_diagnostic as issue45_legacy
from recipes import issue43_coupling_diagnostic as issue43_recipe
from recipes import issue45_first_linear as issue45_recipe
from recipes import issue46_jacobian_localization as issue46_recipe


def _fixture() -> str:
    return """[Executioner]\n  type = Transient\n  petsc_options = '-snes_converged_reason -ksp_converged_reason'\n  petsc_options_iname = '-pc_type -pc_factor_shift_type'\n  petsc_options_value = 'lu NONZERO'\n[]\n\n[Outputs]\n  [console]\n    type = Console\n  []\n[]\n"""


def _expect_error(fn, label: str) -> None:
    try:
        fn()
    except (mp.MooseParameterError, po.PetscOptionsError):
        return
    raise AssertionError(f"negative control unexpectedly passed: {label}")


def _check_moose_parameters() -> None:
    text = _fixture()
    assert mp.unquote("'a b'") == "a b"
    assert mp.words("'a b'") == ["a", "b"]
    assert mp.get_parameter(text, "Executioner", "type") == "Transient"
    assert mp.parameter_count(text, "Executioner", "type") == 1

    replaced = mp.upsert_parameter(text, "Executioner", "type", "Steady")
    assert mp.get_parameter(replaced, "Executioner", "type") == "Steady"
    assert mp.parameter_count(replaced, "Executioner", "type") == 1

    inserted = mp.upsert_parameter(text, "Executioner", "nl_max_its", "1")
    assert mp.get_parameter(inserted, "Executioner", "nl_max_its") == "1"
    assert mp.parameter_count(inserted, "Executioner", "nl_max_its") == 1

    children = mp.direct_children(text, "Outputs")
    assert children == ["Outputs/console"]

    ambiguous = text.replace("  type = Transient\n", "  type = Transient\n  type = Steady\n", 1)
    _expect_error(
        lambda: mp.upsert_parameter(ambiguous, "Executioner", "type", "Transient"),
        "ambiguous parameter",
    )


def _check_petsc_options() -> None:
    text = _fixture()
    assert po.get_flags(text) == ["-snes_converged_reason", "-ksp_converged_reason"]

    added = po.add_flags(text, ["-ksp_view", "-snes_converged_reason"])
    assert po.get_flags(added) == [
        "-snes_converged_reason",
        "-ksp_converged_reason",
        "-ksp_view",
    ]

    removed = po.remove_flags(added, ["-ksp_converged_reason"])
    assert po.get_flags(removed) == ["-snes_converged_reason", "-ksp_view"]

    assert po.get_name_value_pairs(text) == [
        ("-pc_type", "lu"),
        ("-pc_factor_shift_type", "NONZERO"),
    ]
    replaced = po.upsert_name_value(text, "-pc_type", "ilu")
    assert po.get_name_value_pairs(replaced) == [
        ("-pc_type", "ilu"),
        ("-pc_factor_shift_type", "NONZERO"),
    ]
    appended = po.upsert_name_value(replaced, "-mat_fd_type", "ds")
    assert po.get_name_value_pairs(appended)[-1] == ("-mat_fd_type", "ds")
    deleted = po.remove_name_value(appended, "-pc_factor_shift_type")
    assert po.get_name_value_pairs(deleted) == [
        ("-pc_type", "ilu"),
        ("-mat_fd_type", "ds"),
    ]

    mismatch = text.replace("petsc_options_value = 'lu NONZERO'", "petsc_options_value = 'lu'")
    _expect_error(lambda: po.get_name_value_pairs(mismatch), "iname/value mismatch")


def _check_recipe_equivalence() -> None:
    text = _fixture()

    for jacobian_test in (False, True):
        old_text, old_meta = issue43_legacy.instrument_input(
            text, jacobian_test=jacobian_test
        )
        new_text, new_meta = issue43_recipe.instrument_input(
            text, jacobian_test=jacobian_test
        )
        if new_text != old_text or new_meta != old_meta:
            raise AssertionError(
                f"Issue43 recipe drift for jacobian_test={jacobian_test}"
            )

    old45_text, old45_meta = issue45_legacy.instrument_first_linear(text)
    new45_text, new45_meta = issue45_recipe.instrument_first_linear(text)
    if new45_text != old45_text or new45_meta != old45_meta:
        raise AssertionError("Issue45 recipe drift")

    old46_text, old46_meta = issue46_legacy.instrument_localization(old45_text)
    new46_text, new46_meta = issue46_recipe.instrument_localization(old45_text)
    if new46_text != old46_text or new46_meta != old46_meta:
        raise AssertionError("Issue46 recipe drift")


def _check_generality_surface() -> None:
    root = Path(__file__).resolve().parents[2]
    for rel in (
        "qpx_harness/moose/parameters.py",
        "qpx_harness/petsc/options.py",
    ):
        source = (root / rel).read_text()
        for forbidden in (
            "ISSUE =",
            "C0_TARGET",
            "potential_plasma",
            "r45_inventory_lambda",
            "FD_REFERENCE_QUANTIZATION_CONFIRMED",
        ):
            if forbidden in source:
                raise AssertionError(f"special-case semantic leaked into {rel}: {forbidden}")
        if "fast_plasma" in source or "electron_inventory" in source or "jacobian_fd_reference_audit" in source:
            raise AssertionError(f"reverse dependency leaked into {rel}")

    for rel in (
        "recipes/issue43_coupling_diagnostic.py",
        "recipes/issue45_first_linear.py",
        "recipes/issue46_jacobian_localization.py",
    ):
        source = (root / rel).read_text()
        if "qpx_harness.moose" not in source and "qpx_harness.petsc" not in source:
            raise AssertionError(f"recipe does not compose generic primitives: {rel}")


def main() -> int:
    try:
        _check_moose_parameters()
        print("ISSUE48_GENERALITY_CHECK: moose-parameter-primitives=PASS")
        _check_petsc_options()
        print("ISSUE48_GENERALITY_CHECK: petsc-option-primitives=PASS")
        _check_recipe_equivalence()
        print("ISSUE48_GENERALITY_CHECK: issue43-45-46-recipe-equivalence=PASS")
        _check_generality_surface()
        print("ISSUE48_GENERALITY_CHECK: primitive-boundary=PASS")
    except Exception as exc:
        print(f"ISSUE48_GENERALITY_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_GENERALITY_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
