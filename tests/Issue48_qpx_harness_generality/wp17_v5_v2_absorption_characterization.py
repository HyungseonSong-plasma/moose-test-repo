#!/usr/bin/env python3
"""P0 characterization for the final fast_plasma_relaxation_v2 absorption into v5."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import artifacts
from qpx_harness import cases
from qpx_harness import evidence
from qpx_harness import preflight
from qpx_harness import runtime
from qpx_harness import scale_audit
from qpx_harness import fast_plasma_relaxation_v2 as v2
from recipes import issue43_fast_relaxation as recipe

V5 = ROOT / "qpx_harness" / "fast_plasma_relaxation_v5.py"

V5_GENUINE_V2_RUNTIME_TOKENS = (
    "_RAW_BUILD_ELECTRON_300K = v2._build_electron_300k",
    "_V2_BUILD_ONEWAY = v2._build_oneway",
    "_V2_BUILD_FEEDBACK = v2._build_feedback",
    "_RAW_RUN_CASE = v2._run_case",
    "_RAW_CLASSIFY = v2.classify",
    "v2._attach_residual(",
    "v2._physics_pass(",
    "v2.self_test()",
)

V5_RETIRED_STALE_V1_TOKENS = (
    "v2.v1._find_csv(",
    "v2.v1.BASE_CASE_RELATIVE",
    "v2.v1._copy_case(",
    "v2.v1._validate_assets(",
    "v2.v1._create_root(",
    "v2.v1._run_known_good(",
    "v2.v1.FastPlasmaRelaxationError",
)

V5_STALE_V1_CUTOVER_TOKENS = (
    "from recipes import issue43_fast_relaxation as relaxation_recipe",
    "except v2.FastPlasmaRelaxationError as exc:",
    "relaxation_recipe.find_relaxation_csv(case_dir)",
    "base_case = repo_root / v2.BASE_CASE_RELATIVE",
    "v2._stage_case(base_case, case_dir, input_text)",
    "v2._validate_assets(case_dir)",
    "root = v2._create_root(results_root)",
    "known_good = v2._run_known_good(",
)

V5_GENERIC_INFRA_TOKENS = (
    "v2.resolve_executable(",
    "v2.validate_executable(",
    "v2.mesh_stats(",
    "v2.anchor_scales(",
    "v2.validate_parser_symbols_text(",
    "v2._write_json(",
    "v2._stage_case(",
    "v2._validate_assets(",
    "v2._create_root(",
)

ISSUE43_POLICY_TOKENS = (
    '"KNOWN_GOOD_ELECTRON_CONTROL_FAIL"',
    '"ELECTRON_300K_CONTROL_FAIL"',
    '"POISSON_OR_BLOCK_SCALING_FAIL"',
    '"FEEDBACK_CASE_MISSING"',
    '"FEEDBACK_IMPLICIT_COUPLING_RECOVERS_NEAR_TAU_DR"',
    '"DIELECTRIC_TIMESTEP_STIFFNESS_CONFIRMED"',
    '"FEEDBACK_RECOVERS_BELOW_TAU_DR"',
    '"DIELECTRIC_TIMESTEP_STIFFNESS_STRONG"',
    '"FEEDBACK_JACOBIAN_SCALING_OR_INITIALIZATION_FAIL"',
    '"FEEDBACK_DISCRIMINATOR_INCOMPLETE"',
)


def _text(path: Path) -> str:
    return path.read_text()


def _check_sole_runtime_consumer() -> None:
    tokens = (
        "from . import fast_plasma_relaxation_v2 as v2",
        "import qpx_harness.fast_plasma_relaxation_v2 as v2",
    )
    observed: set[str] = set()
    for path in (ROOT / "qpx_harness").glob("*.py"):
        if path.name == "fast_plasma_relaxation_v2.py":
            continue
        source = _text(path)
        if any(token in source for token in tokens):
            observed.add(path.name)
    if observed != {"fast_plasma_relaxation_v5.py"}:
        raise AssertionError(f"v2 sole-consumer topology drift: {sorted(observed)}")


def _check_v5_current_surface() -> None:
    source = _text(V5)
    for token in V5_GENUINE_V2_RUNTIME_TOKENS:
        if token not in source:
            raise AssertionError(f"v5 genuine v2 runtime surface drift: {token}")
    for token in V5_RETIRED_STALE_V1_TOKENS:
        if token in source:
            raise AssertionError(f"v5 stale-v1 surface returned: {token}")
    for token in V5_STALE_V1_CUTOVER_TOKENS:
        if token not in source:
            raise AssertionError(f"v5 stale-v1 cutover drift: {token}")
    for token in V5_GENERIC_INFRA_TOKENS:
        if token not in source:
            raise AssertionError(f"v5 generic-infra dependency drift: {token}")
    for token in (
        "def _install_v2_repairs(",
        "def _install_v5_repairs(",
        "v2._build_electron_300k =",
        "v2._run_case =",
    ):
        if token not in source:
            raise AssertionError(f"v5 monkey-patch compatibility surface drift: {token}")


def _check_v1_alias_is_already_retired() -> None:
    if not hasattr(v2.v1, "FastPlasmaRelaxationError"):
        raise AssertionError("v2 error compatibility alias missing")
    for name in (
        "BASE_CASE_RELATIVE",
        "_find_csv",
        "_copy_case",
        "_validate_assets",
        "_create_root",
        "_run_known_good",
    ):
        if hasattr(v2.v1, name):
            raise AssertionError(f"historical v1 runtime surface unexpectedly returned: {name}")


def _check_destination_readiness() -> None:
    for owner, name in (
        (cases, "stage_case"),
        (cases, "validate_case_references"),
        (runtime, "resolve_executable"),
        (runtime, "validate_executable"),
        (artifacts, "write_json_bundle"),
        (evidence, "create_collision_safe_directory"),
        (scale_audit, "mesh_stats"),
        (scale_audit, "anchor_scales"),
        (preflight, "validate_parser_symbols_text"),
        (recipe, "find_relaxation_csv"),
        (recipe, "build_fast_input"),
        (recipe, "classify"),
    ):
        if not callable(getattr(owner, name, None)):
            raise AssertionError(f"canonical destination missing: {owner.__name__}.{name}")


def _check_collision_safe_directory_primitive() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        parent = Path(tmp_name) / "results"
        stem = "issue43_probe_20260831T120000Z"
        first = evidence.create_collision_safe_directory(parent, stem)
        second = evidence.create_collision_safe_directory(parent, stem)
        third = evidence.create_collision_safe_directory(parent, stem)
        if [path.name for path in (first, second, third)] != [
            stem,
            f"{stem}_01",
            f"{stem}_02",
        ]:
            raise AssertionError("collision-safe directory suffix contract drift")
        if not all(path.is_dir() for path in (first, second, third)):
            raise AssertionError("collision-safe directory primitive did not create directories")

        try:
            evidence.create_collision_safe_directory(parent, "../escape")
        except ValueError:
            pass
        else:
            raise AssertionError("collision-safe directory primitive accepted path traversal")


def _check_scientific_policy_boundary() -> None:
    v2_source = _text(Path(v2.__file__))
    recipe_source = _text(Path(recipe.__file__))

    if "def classify(" not in recipe_source:
        raise AssertionError("recipe does not own Issue43 scientific classification")
    for token in ISSUE43_POLICY_TOKENS:
        if token not in recipe_source:
            raise AssertionError(f"recipe Issue43 policy class drift: {token}")

    # The v2 copy remains temporarily as the compatibility/equivalence oracle.
    # It is removed only after v5 binds the recipe directly.
    if "def classify(" not in v2_source:
        raise AssertionError("v2 compatibility classification moved before v5 cutover")
    for token in ISSUE43_POLICY_TOKENS:
        if token not in v2_source:
            raise AssertionError(f"v2 compatibility policy class drift: {token}")

    for forbidden in (
        "fast_plasma_relaxation_v2",
        "fast_plasma_relaxation_v5",
        "qpx_harness.runtime",
        "qpx_harness.cases",
    ):
        if forbidden in recipe_source:
            raise AssertionError(f"recipe reverse dependency leaked: {forbidden}")


def main() -> int:
    try:
        _check_sole_runtime_consumer()
        _check_v5_current_surface()
        _check_v1_alias_is_already_retired()
        _check_destination_readiness()
        _check_collision_safe_directory_primitive()
        _check_scientific_policy_boundary()
    except Exception as exc:
        print(f"ISSUE48_V5_V2_ABSORPTION_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_V5_V2_ABSORPTION_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
