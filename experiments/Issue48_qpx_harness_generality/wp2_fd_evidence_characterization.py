#!/usr/bin/env python3
"""P0 characterization for generic FD representability and artifact checks."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.evidence import artifacts
from experiments.historical_recipe_support import issue46_fd_reference as legacy
from physics_harness.adapters.petsc import fd_reference


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


def _generic_provenance_summary(
    *,
    root: Path,
    case: Path,
    input_path: Path,
    source: Path,
    input_before: str,
    input_after: str,
    log: Path,
    log_preexisting: bool,
    log_exists: bool,
    dofmap: Path,
    dofmap_preexisting: bool,
    dofmap_exists: bool,
    source_before: tuple[str, ...],
    source_after: tuple[str, ...],
) -> dict[str, object]:
    return artifacts.summarize_checks(
        {
            "runner-owned-case": artifacts.is_direct_child(case, root),
            "runner-owned-input": artifacts.is_direct_child(input_path, case),
            "source-case-isolated": artifacts.paths_distinct(case, source),
            "input-identity-stable": artifacts.identity_stable(input_before, input_after),
            "current-run-log": artifacts.current_run_artifact(
                log,
                expected_parent=root,
                existed_before=log_preexisting,
                exists_after=log_exists,
            ),
            "current-run-dofmap": artifacts.current_run_artifact(
                dofmap,
                expected_parent=case,
                existed_before=dofmap_preexisting,
                exists_after=dofmap_exists,
            ),
            "canonical-source-output-unchanged": artifacts.snapshot_unchanged(
                source_before, source_after
            ),
        }
    )


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
        dofmap = case / "dofmap.json"

        positive = _generic_provenance_summary(
            root=root,
            case=case,
            input_path=input_path,
            source=source,
            input_before="abc",
            input_after="abc",
            log=log,
            log_preexisting=False,
            log_exists=True,
            dofmap=dofmap,
            dofmap_preexisting=False,
            dofmap_exists=True,
            source_before=("a", "b"),
            source_after=("a", "b"),
        )
        if not positive["ok"] or positive["blockers"]:
            raise AssertionError(f"positive artifact checks failed: {positive}")

        stale = _generic_provenance_summary(
            root=root,
            case=case,
            input_path=input_path,
            source=source,
            input_before="abc",
            input_after="abc",
            log=log,
            log_preexisting=True,
            log_exists=True,
            dofmap=dofmap,
            dofmap_preexisting=False,
            dofmap_exists=True,
            source_before=("a", "b"),
            source_after=("a", "b"),
        )
        if stale["ok"] or stale["blockers"] != ["current-run-log"]:
            raise AssertionError(f"stale artifact negative control failed: {stale}")


def _check_legacy_provenance_equivalence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        case = root / "case"
        source = root / "source"
        case.mkdir()
        source.mkdir()
        input_path = case / "input.i"
        log = root / "run.log"
        dofmap = case / "dofmap.json"

        scenarios = (
            {
                "input_before": "abc",
                "input_after": "abc",
                "log_preexisting": False,
                "log_exists": True,
                "dofmap_preexisting": False,
                "dofmap_exists": True,
                "source_before": ("a",),
                "source_after": ("a",),
            },
            {
                "input_before": "abc",
                "input_after": "abc",
                "log_preexisting": True,
                "log_exists": True,
                "dofmap_preexisting": False,
                "dofmap_exists": True,
                "source_before": ("a",),
                "source_after": ("a",),
            },
            {
                "input_before": "abc",
                "input_after": "def",
                "log_preexisting": False,
                "log_exists": True,
                "dofmap_preexisting": False,
                "dofmap_exists": True,
                "source_before": ("a",),
                "source_after": ("a", "new"),
            },
        )
        for scenario in scenarios:
            old = legacy.evidence_provenance_status(
                root=root,
                case_dir=case,
                input_path=input_path,
                source_case=source,
                input_sha_before=scenario["input_before"],
                input_sha_after=scenario["input_after"],
                log_path=log,
                log_preexisting=scenario["log_preexisting"],
                log_exists=scenario["log_exists"],
                dofmap_path=dofmap,
                dofmap_preexisting=scenario["dofmap_preexisting"],
                dofmap_exists=scenario["dofmap_exists"],
                source_dofmaps_before=scenario["source_before"],
                source_dofmaps_after=scenario["source_after"],
            )
            new = _generic_provenance_summary(
                root=root,
                case=case,
                input_path=input_path,
                source=source,
                input_before=scenario["input_before"],
                input_after=scenario["input_after"],
                log=log,
                log_preexisting=scenario["log_preexisting"],
                log_exists=scenario["log_exists"],
                dofmap=dofmap,
                dofmap_preexisting=scenario["dofmap_preexisting"],
                dofmap_exists=scenario["dofmap_exists"],
                source_before=scenario["source_before"],
                source_after=scenario["source_after"],
            )
            if new["blockers"] != old["blockers"]:
                raise AssertionError(
                    f"provenance blocker drift: generic={new['blockers']} legacy={old['blockers']}"
                )
            if bool(new["ok"]) != (old["status"] == "PASS"):
                raise AssertionError("provenance pass/fail drift")


def _check_policy_boundary() -> None:
    for rel in (
        "physics_harness/adapters/petsc/fd_reference.py",
        "physics_harness/evidence/artifacts.py",
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
        _check_legacy_provenance_equivalence()
        print("ISSUE48_WP2_FD_EVIDENCE_CHECK: legacy-provenance-equivalence=PASS")
        _check_policy_boundary()
        print("ISSUE48_WP2_FD_EVIDENCE_CHECK: policy-boundary=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP2_FD_EVIDENCE_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP2_FD_EVIDENCE_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())