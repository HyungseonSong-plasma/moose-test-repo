#!/usr/bin/env python3
"""P0 characterization for generic FD representability and artifact checks."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import artifacts
from qpx_harness import jacobian_fd_reference_audit as legacy
from qpx_harness.petsc import fd_reference


def _check_fd_predictor() -> None:
    states = (
        (3.2e17, 1.0e16),
        (7.5, 2.0),
        (0.0, -3.0),
    )
    for vector_norm, component_value in states:
        old = legacy.predict_fd_step_quantization(
            vector_norm=vector_norm,
            component_value=component_value,
        )
        new = fd_reference.predict_wp_ds_representability(
            vector_norm=vector_norm,
            component_value=component_value,
        )
        if new != old:
            raise AssertionError(
                f"FD predictor drift for state {(vector_norm, component_value)}: {new} != {old}"
            )

    step = fd_reference.representable_increment(
        component_value=1.0e16,
        requested_dx=10.37276731735,
    )
    if step["representable_dx"] != 10.0:
        raise AssertionError("explicit representable increment did not quantize as expected")

    for bad in (
        lambda: fd_reference.representable_increment(component_value=1.0, requested_dx=0.0),
        lambda: fd_reference.predict_wp_ds_representability(vector_norm=-1.0, component_value=1.0),
        lambda: fd_reference.predict_wp_ds_representability(vector_norm=1.0, component_value=0.0),
    ):
        try:
            bad()
        except fd_reference.FDReferenceError:
            pass
        else:
            raise AssertionError("invalid FD state unexpectedly passed")


def _check_artifact_primitives() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        case = root / "case"
        case.mkdir()
        source = root / "source"
        source.mkdir()
        input_path = case / "input.i"
        input_path.write_text("[Mesh]\n[]\n")
        log = root / "run.log"
        generated = case / "dofmap.json"

        checks = {
            "runner-owned-case": artifacts.is_direct_child(case, root),
            "runner-owned-input": artifacts.is_direct_child(input_path, case),
            "source-case-isolated": artifacts.paths_distinct(case, source),
            "input-identity-stable": artifacts.identity_stable("abc", "abc"),
            "current-run-log": artifacts.current_run_artifact(
                log,
                expected_parent=root,
                existed_before=False,
                exists_after=True,
            ),
            "current-run-generated": artifacts.current_run_artifact(
                generated,
                expected_parent=case,
                existed_before=False,
                exists_after=True,
            ),
            "source-output-unchanged": artifacts.snapshot_unchanged(
                ("a", "b"), ("a", "b")
            ),
        }
        result = artifacts.summarize_checks(checks)
        if not result["ok"] or result["blockers"]:
            raise AssertionError(f"positive artifact checks failed: {result}")

        stale = dict(checks)
        stale["current-run-log"] = artifacts.current_run_artifact(
            log,
            expected_parent=root,
            existed_before=True,
            exists_after=True,
        )
        stale_result = artifacts.summarize_checks(stale)
        if stale_result["ok"] or stale_result["blockers"] != ["current-run-log"]:
            raise AssertionError(f"stale artifact negative control failed: {stale_result}")


def _check_policy_boundary() -> None:
    for rel in (
        "qpx_harness/petsc/fd_reference.py",
        "qpx_harness/artifacts.py",
    ):
        source = (ROOT / rel).read_text()
        forbidden = (
            "ISSUE =",
            "C0_TARGET",
            "HISTORICAL_EVR1",
            "FD_REFERENCE_QUANTIZATION_CONFIRMED",
            "EVIDENCE_PROVENANCE_HOLD",
            "n_e",
            "potential_plasma",
            "r45_inventory_lambda",
        )
        for token in forbidden:
            if token in source:
                raise AssertionError(f"special-case policy leaked into {rel}: {token}")
        if "recipes" in source or "jacobian_fd_reference_audit" in source:
            raise AssertionError(f"reverse dependency leaked into {rel}")


def main() -> int:
    try:
        _check_fd_predictor()
        print("ISSUE48_WP2_FD_EVIDENCE_CHECK: fd-representability=PASS")
        _check_artifact_primitives()
        print("ISSUE48_WP2_FD_EVIDENCE_CHECK: artifact-binding-primitives=PASS")
        _check_policy_boundary()
        print("ISSUE48_WP2_FD_EVIDENCE_CHECK: policy-boundary=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP2_FD_EVIDENCE_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP2_FD_EVIDENCE_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
