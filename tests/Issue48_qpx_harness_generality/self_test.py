"""P0 characterization for reusable MOOSE/PETSc mutation primitives.

This test intentionally knows concrete examples; the production primitives must not.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import artifacts as qa
from qpx_harness import temporal as qt
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import executioner as me
from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import options as po
from qpx_harness import augmented_jacobian_localization as issue46_legacy
from qpx_harness import electron_inventory_nullspace as issue45_inventory_legacy
from qpx_harness import fast_plasma_coupling_diagnostic as issue43_legacy
from qpx_harness import petsc_first_linear_diagnostic as issue45_legacy
from recipes import issue43_coupling_diagnostic as issue43_recipe
from recipes import issue45_first_linear as issue45_recipe
from recipes import issue45_inventory_constraint as issue45_inventory_recipe
from recipes import issue46_jacobian_localization as issue46_recipe


def _fixture() -> str:
    return """[Executioner]\n  type = Transient\n  petsc_options = '-snes_converged_reason -ksp_converged_reason'\n  petsc_options_iname = '-pc_type -pc_factor_shift_type'\n  petsc_options_value = 'lu NONZERO'\n[]\n\n[Outputs]\n  [console]\n    type = Console\n  []\n[]\n"""


def _expect_error(fn, label: str) -> None:
    try:
        fn()
    except (
        mb.MooseBlockError,
        me.MooseExecutionerError,
        mp.MooseParameterError,
        po.PetscOptionsError,
    ):
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

    ambiguous = text.replace(
        "  type = Transient\n",
        "  type = Transient\n  type = Steady\n",
        1,
    )
    _expect_error(
        lambda: mp.upsert_parameter(ambiguous, "Executioner", "type", "Transient"),
        "ambiguous parameter",
    )


def _check_moose_executioner() -> None:
    text = _fixture()
    tuned = me.apply_fixed_step_contract(text, dt=1.0e-13, steps=5)
    controls = me.executioner_controls(
        tuned,
        required=(
            "dt",
            "end_time",
            "num_steps",
            "dtmin",
            "timestep_tolerance",
            "abort_on_solve_fail",
        ),
    )
    expected = {
        "dt": 1.0e-13,
        "end_time": 5.0e-13,
        "num_steps": 5,
        "dtmin": 1.0e-14,
        "timestep_tolerance": 1.0e-16,
        "abort_on_solve_fail": True,
        "compute_scaling_once": True,
    }
    for name, value in expected.items():
        actual = controls.get(name)
        if isinstance(value, float):
            if abs(float(actual) - value) > abs(value) * 1.0e-15:
                raise AssertionError(
                    f"Executioner control drift for {name}: {actual} != {value}"
                )
        elif actual != value:
            raise AssertionError(
                f"Executioner control drift for {name}: {actual} != {value}"
            )

    duplicate = tuned.replace(
        "  num_steps = 5\n",
        "  num_steps = 5\n  num_steps = 6\n",
        1,
    )
    _expect_error(
        lambda: me.apply_fixed_step_contract(duplicate, dt=1.0e-13, steps=5),
        "ambiguous fixed-step parameter",
    )
    _expect_error(
        lambda: me.apply_fixed_step_contract(text, dt=0.0, steps=5),
        "non-positive fixed-step dt",
    )


def _check_temporal_observation() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        case_dir = Path(tmp_name)
        alternate = case_dir / "alternate.csv"
        alternate.write_text("time,value\n0,0\n1,1\n")
        preferred = case_dir / "input_out.csv"
        preferred.write_text(
            "time,value\n"
            "0,0\n"
            "1e-13,1\n"
            "bad,ignored\n"
            "2e-13,1\n"
            "5e-13,1\n"
        )

        if qt.find_temporal_csv(case_dir) != preferred:
            raise AssertionError("temporal CSV locator did not preserve preferred ownership")
        observed = qt.observe_case_trajectory(case_dir)
        expected = {
            "physical_rows": 3,
            "csv": str(preferred),
            "csv_status": "PASS",
            "first_time": 1.0e-13,
            "final_time": 5.0e-13,
            "actual_dt_min": 1.0e-13,
            "actual_dt_max": 3.0e-13,
        }
        for key, value in expected.items():
            actual = observed.get(key)
            if isinstance(value, float):
                if abs(float(actual) - value) > max(abs(value) * 1.0e-15, 1.0e-300):
                    raise AssertionError(
                        f"temporal observation drift for {key}: {actual} != {value}"
                    )
            elif actual != value:
                raise AssertionError(
                    f"temporal observation drift for {key}: {actual} != {value}"
                )

        empty = case_dir / "empty"
        empty.mkdir()
        missing = qt.observe_case_trajectory(empty)
        if missing != {"physical_rows": 0, "csv_status": "MISSING_TIME_CSV"}:
            raise AssertionError(f"missing temporal evidence drift: {missing}")

        no_time = empty / "not_temporal.csv"
        no_time.write_text("value\n1\n")
        if qt.find_temporal_csv(empty) is not None:
            raise AssertionError("CSV without requested time column was accepted")


def _check_artifact_writes() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name) / "bundle"
        paths = qa.write_json_bundle(
            root,
            {
                "p1": ("p1.json", {"status": "PASS"}),
                "contract": ("contract.json", {"b": 2, "a": 1}),
            },
        )
        if Path(paths["contract"]).parent != root:
            raise AssertionError("JSON artifact escaped declared owner directory")
        if Path(paths["p1"]).parent != root:
            raise AssertionError("JSON artifact escaped declared owner directory")
        if (root / "contract.json").read_text() != '{\n  "a": 1,\n  "b": 2\n}\n':
            raise AssertionError("JSON artifact serialization is not deterministic")
        if (root / "p1.json").read_text() != '{\n  "status": "PASS"\n}\n':
            raise AssertionError("JSON artifact payload drift")

        try:
            qa.write_json_bundle(
                root / "bad",
                {"escape": ("../escape.json", {"status": "BAD"})},
            )
        except ValueError:
            pass
        else:
            raise AssertionError("artifact path escape was not rejected")


def _check_moose_blocks() -> None:
    text = _fixture()
    with_debug = mb.append_top_level_block(
        text,
        "[Debug]\n  show_var_residual_norms = true\n[]",
    )
    if not mb.has_block(with_debug, "Debug"):
        raise AssertionError("top-level block append did not create Debug")

    child = (
        "  [probe]\n"
        "    type = DOFMap\n"
        "    execute_on = INITIAL\n"
        "    file_base = probe\n"
        "  []"
    )
    with_child = mb.insert_child_block(text, "Outputs", child)
    if not mb.has_block(with_child, "Outputs/probe"):
        raise AssertionError("child block insertion did not create Outputs/probe")
    _expect_error(
        lambda: mb.require_absent(with_child, "Outputs/probe"),
        "existing block accepted by require_absent",
    )

    removed = mb.remove_block(with_child, "Outputs/probe")
    if mb.has_block(removed, "Outputs/probe"):
        raise AssertionError("remove_block left Outputs/probe behind")

    replaced = mb.replace_block(
        with_debug,
        "Debug",
        "[Debug]\n  show_var_residual_norms = false\n[]",
    )
    if mp.get_parameter(replaced, "Debug", "show_var_residual_norms") != "false":
        raise AssertionError("replace_block did not replace Debug")


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

    mismatch = text.replace(
        "petsc_options_value = 'lu NONZERO'",
        "petsc_options_value = 'lu'",
    )
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
        raise AssertionError("Issue45 first-linear recipe drift")

    constrained = issue45_inventory_legacy._synthetic_constrained_input()
    old_inventory = issue45_inventory_legacy.audit_constrained_quasisteady_structure(
        constrained,
        expected_macro_avg=issue45_inventory_legacy.DEFAULT_MACRO_ELECTRON_AVG,
    )
    new_inventory = issue45_inventory_recipe.audit_constrained_quasisteady_structure(
        constrained,
        expected_macro_avg=issue45_inventory_legacy.DEFAULT_MACRO_ELECTRON_AVG,
    )
    if new_inventory != old_inventory:
        raise AssertionError("Issue45 inventory-constraint recipe drift")

    old46_text, old46_meta = issue46_legacy.instrument_localization(old45_text)
    new46_text, new46_meta = issue46_recipe.instrument_localization(old45_text)
    if new46_text != old46_text or new46_meta != old46_meta:
        raise AssertionError("Issue46 recipe drift")


def _check_generality_surface() -> None:
    for rel in (
        "qpx_harness/artifacts.py",
        "qpx_harness/moose/parameters.py",
        "qpx_harness/moose/blocks.py",
        "qpx_harness/moose/executioner.py",
        "qpx_harness/petsc/options.py",
        "qpx_harness/temporal.py",
    ):
        source = (ROOT / rel).read_text()
        for forbidden in (
            "ISSUE =",
            "C0_TARGET",
            "potential_plasma",
            "r45_inventory_lambda",
            "FD_REFERENCE_QUANTIZATION_CONFIRMED",
        ):
            if forbidden in source:
                raise AssertionError(
                    f"special-case semantic leaked into {rel}: {forbidden}"
                )
        for reverse in (
            "fast_plasma",
            "electron_inventory",
            "jacobian_fd_reference_audit",
            "petsc_first_linear_diagnostic",
            "augmented_jacobian_localization",
        ):
            if reverse in source:
                raise AssertionError(
                    f"reverse dependency leaked into {rel}: {reverse}"
                )

    recipe_paths = (
        "recipes/issue43_coupling_diagnostic.py",
        "recipes/issue45_first_linear.py",
        "recipes/issue45_inventory_constraint.py",
        "recipes/issue46_jacobian_localization.py",
    )
    legacy_names = (
        "fast_plasma_coupling_diagnostic",
        "electron_inventory_nullspace",
        "petsc_first_linear_diagnostic",
        "augmented_jacobian_localization",
        "jacobian_fd_reference_audit",
    )
    for rel in recipe_paths:
        source = (ROOT / rel).read_text()
        if "qpx_harness.moose" not in source and "qpx_harness.petsc" not in source:
            raise AssertionError(f"recipe does not compose generic primitives: {rel}")
        leaked = [name for name in legacy_names if name in source]
        if leaked:
            raise AssertionError(
                f"recipe reverse-imports legacy module {rel}: {leaked}"
            )


def _check_script_surface() -> dict[str, list[str]]:
    scripts = sorted(
        path.name for path in (ROOT / "scripts").iterdir() if path.is_file()
    )
    if scripts != ["qpx.py"]:
        raise AssertionError(f"scripts must expose only qpx.py after cleanup: {scripts}")

    qpx_source = (ROOT / "scripts/qpx.py").read_text()
    for command in ('"preflight"', '"temporal-csv"', '"self-test"'):
        if command not in qpx_source:
            raise AssertionError(f"unified qpx CLI missing command {command}")

    # User-local QPX mirrors intentionally carry executable harness/test
    # surfaces without necessarily carrying repository governance files such as
    # .github/ and docs/. Those missing repository-only surfaces must not turn
    # a portable P0 into a false failure. When a canonical surface is present,
    # however, still enforce that it no longer references the retired wrappers.
    canonical_refs = (
        ROOT / ".github/workflows/qpx-regression.yml",
        ROOT / "docs/protocols/validation.md",
        ROOT / "tests/README.md",
    )
    obsolete = ("scripts/validate_parser_symbols.py", "scripts/temporal_csv.py")
    checked: list[str] = []
    skipped: list[str] = []
    for path in canonical_refs:
        if not path.is_file():
            skipped.append(str(path.relative_to(ROOT)))
            continue
        source = path.read_text()
        leaked = [item for item in obsolete if item in source]
        if leaked:
            raise AssertionError(
                f"obsolete compatibility command remains in {path}: {leaked}"
            )
        checked.append(str(path.relative_to(ROOT)))
    return {"checked": checked, "skipped": skipped}


def main() -> int:
    try:
        _check_moose_parameters()
        print("ISSUE48_GENERALITY_CHECK: moose-parameter-primitives=PASS")
        _check_moose_executioner()
        print("ISSUE48_GENERALITY_CHECK: moose-executioner-primitives=PASS")
        _check_temporal_observation()
        print("ISSUE48_GENERALITY_CHECK: temporal-observation-primitives=PASS")
        _check_artifact_writes()
        print("ISSUE48_GENERALITY_CHECK: artifact-write-primitives=PASS")
        _check_moose_blocks()
        print("ISSUE48_GENERALITY_CHECK: moose-block-primitives=PASS")
        _check_petsc_options()
        print("ISSUE48_GENERALITY_CHECK: petsc-option-primitives=PASS")
        _check_recipe_equivalence()
        print("ISSUE48_GENERALITY_CHECK: issue43-45-46-recipe-equivalence=PASS")
        _check_generality_surface()
        print("ISSUE48_GENERALITY_CHECK: recipe-reverse-dependency=NONE")
        print("ISSUE48_GENERALITY_CHECK: primitive-boundary=PASS")
        script_surface = _check_script_surface()
        print("ISSUE48_GENERALITY_CHECK: scripts-entrypoint=PASS")
        if script_surface["skipped"]:
            print(
                "ISSUE48_GENERALITY_CHECK: repository-only-surfaces=SKIP_LOCAL_MIRROR "
                + "missing="
                + ",".join(script_surface["skipped"])
            )
        else:
            print("ISSUE48_GENERALITY_CHECK: repository-only-surfaces=PASS")
    except Exception as exc:
        print(f"ISSUE48_GENERALITY_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_GENERALITY_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
