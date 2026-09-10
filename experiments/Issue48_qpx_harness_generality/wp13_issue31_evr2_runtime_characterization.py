#!/usr/bin/env python3
"""P0 characterization for the retired Issue31 EVR2 runtime contract."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue31_coupling as recipe
from physics_harness.adapters.moose.nonlinear_solver import artifact_failure_signature
from physics_harness.application.performance import result_status, validate_experiment_manifest
from physics_harness.execution.cases import stage_case


HISTORICAL_EXPERIMENT_ID = "issue31-evr2-timestep-scaling"
HISTORICAL_PURGE_DIRECTORY_NAMES = (".jitcache",)
HISTORICAL_PURGE_PATTERNS = (
    "input_out*",
    "r29_csv*",
    "qpxperf*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


def _case(
    status: str,
    *,
    physics: str | None = None,
    signature: str | None = None,
    checker: str | None = None,
) -> dict:
    value = {
        "result": {"validation": {"status": status}},
        "failure": {"signature": signature},
    }
    if physics is not None:
        value["physics"] = {"status": physics}
    if checker is not None:
        value["canonical_checker"] = {"status": checker}
    return value


def _historical_manifest(
    *, case_dir: Path, case_id: str, species: list[str] | None = None
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": HISTORICAL_EXPERIMENT_ID,
        "case_id": case_id,
        "mode": "BENCHMARK",
        "case": {
            "directory": str(Path(case_dir).expanduser().resolve()),
            "input": "input.i",
        },
        "runtime": {"num_steps": 1},
        "collectors": {
            "work_counters": True,
            "perfgraph": False,
            "petsc_log": False,
        },
        "stream_output": True,
    }
    if species:
        manifest["physics"] = {"species": list(species)}
    validate_experiment_manifest(manifest)
    return manifest


def _stage_kg_e(repo_root: Path, cases_root: Path) -> Path:
    """Frozen pre-retirement EVR2 wrapper over generic case staging."""
    source_parent = repo_root / recipe.KG_E_PARENT_RELATIVE
    if not source_parent.is_dir():
        raise RuntimeError(f"missing accepted electron control tree: {source_parent}")
    target_parent = cases_root / "kg_e_parent"
    stage_case(
        source_parent,
        target_parent,
        purge_directory_names=HISTORICAL_PURGE_DIRECTORY_NAMES,
        purge_patterns=HISTORICAL_PURGE_PATTERNS,
    )
    case = target_parent / "qvt_prepoisson"
    if not case.is_dir():
        raise RuntimeError(f"copied electron control missing qvt_prepoisson: {case}")
    return case


def _check_state_helper_contract() -> None:
    scenarios = (
        (None, None, False, False),
        ({}, None, False, False),
        (_case("HARNESS_OR_CONSTRUCTION_FAIL"), "HARNESS_OR_CONSTRUCTION_FAIL", False, False),
        (
            _case("RUNTIME_FAIL_OR_NONCONVERGENCE", signature="DIVERGED_MAX_IT"),
            "RUNTIME_FAIL_OR_NONCONVERGENCE",
            True,
            False,
        ),
        (
            _case("RUNTIME_FAIL_OR_NONCONVERGENCE", signature="OTHER"),
            "RUNTIME_FAIL_OR_NONCONVERGENCE",
            False,
            False,
        ),
        (_case("P2_PASS_P3_PASS", physics="PASS"), "P2_PASS_P3_PASS", False, True),
        (_case("P2_PASS_P3_PASS", physics="FAIL"), "P2_PASS_P3_PASS", False, False),
    )
    for case, status, nonconvergence, case_pass in scenarios:
        if result_status((case or {}).get("result")) != status:
            raise AssertionError("EVR2 result-status helper contract drift")
        if recipe._runtime_nonconvergence(case) is not nonconvergence:
            raise AssertionError("EVR2 runtime-nonconvergence helper contract drift")
        if recipe._case_pass(case) is not case_pass:
            raise AssertionError("EVR2 case-pass helper contract drift")

    kg_scenarios = (
        (_case("P2_PASS_P3_PASS", checker="PASS"), True),
        (_case("P2_PASS_P3_PASS", checker="FAIL"), False),
        (_case("RUNTIME_FAIL_OR_NONCONVERGENCE", checker="PASS"), False),
    )
    for case, expected in kg_scenarios:
        if recipe._kg_e_pass(case) is not expected:
            raise AssertionError("EVR2 KG-E pass helper contract drift")


def _check_manifest_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        case_dir = Path(tmp_name)
        (case_dir / "input.i").write_text("[Mesh]\n[]\n")
        actual = _historical_manifest(
            case_dir=case_dir,
            case_id="Issue31_T3_dt1e8",
            species=list(recipe.SPECIES),
        )
        expected = {
            "schema_version": 1,
            "experiment_id": HISTORICAL_EXPERIMENT_ID,
            "case_id": "Issue31_T3_dt1e8",
            "mode": "BENCHMARK",
            "case": {"directory": str(case_dir.resolve()), "input": "input.i"},
            "runtime": {"num_steps": 1},
            "collectors": {
                "work_counters": True,
                "perfgraph": False,
                "petsc_log": False,
            },
            "stream_output": True,
            "physics": {"species": list(recipe.SPECIES)},
        }
        if actual != expected:
            raise AssertionError("EVR2 BENCHMARK manifest contract drift")


def _check_failure_signature_contract() -> None:
    if artifact_failure_signature(None) != {"signature": "NO_RESULT"}:
        raise AssertionError("EVR2 no-result signature contract drift")

    samples = (
        ("DIVERGED_MAX_IT iterations 80", "DIVERGED_MAX_IT", 80),
        ("DIVERGED_LINE_SEARCH", "DIVERGED_LINE_SEARCH", None),
        ("DIVERGED_FNORM_NAN", "DIVERGED_FNORM_NAN", None),
        ("Nonlinear solve did not converge", "NONLINEAR_DID_NOT_CONVERGE", None),
        ("ordinary runtime output", None, None),
    )
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        for index, (text, signature, iterations) in enumerate(samples):
            log = root / f"sample_{index}.log"
            log.write_text(text + "\n")
            result = {"evidence": {"p3_log": str(log)}}
            actual = artifact_failure_signature(result)
            expected = {
                "signature": signature,
                "iterations": iterations,
                "log": str(log),
            }
            if actual != expected:
                raise AssertionError(
                    f"EVR2 failure-signature contract drift for {text!r}: {actual} != {expected}"
                )


def _check_generic_staging() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        asset = root / "asset"
        asset.mkdir()
        (asset / "input.i").write_text("old input\n")
        (asset / "qvt.msh").write_text("mesh\n")
        (asset / "input_out_old.csv").write_text("stale\n")
        (asset / ".jitcache").mkdir()
        (asset / ".jitcache" / "cache").write_text("stale\n")
        nested = asset / "nested"
        nested.mkdir()
        (nested / "qpxperf_old").write_text("stale\n")

        target = root / "transport"
        stage_case(
            asset,
            target,
            input_text="new input\n",
            purge_directory_names=HISTORICAL_PURGE_DIRECTORY_NAMES,
            purge_patterns=HISTORICAL_PURGE_PATTERNS,
        )
        if (target / "input.i").read_text() != "new input\n":
            raise AssertionError("EVR2 transport staging did not replace input")
        if not (target / "qvt.msh").is_file():
            raise AssertionError("EVR2 transport staging lost case asset")
        if (target / "input_out_old.csv").exists():
            raise AssertionError("EVR2 transport staging retained generated CSV")
        if (target / ".jitcache").exists():
            raise AssertionError("EVR2 transport staging retained .jitcache")
        if (target / "nested" / "qpxperf_old").exists():
            raise AssertionError("EVR2 transport staging retained nested qpxperf artifact")

    with tempfile.TemporaryDirectory() as tmp_name:
        repo_root = Path(tmp_name) / "repo"
        source_parent = repo_root / recipe.KG_E_PARENT_RELATIVE
        case = source_parent / "qvt_prepoisson"
        case.mkdir(parents=True)
        (case / "test.json").write_text("{}\n")
        (case / "petsc_log_stale").write_text("stale\n")
        cases_root = Path(tmp_name) / "cases"
        cases_root.mkdir()
        staged = _stage_kg_e(repo_root, cases_root)
        if staged != cases_root / "kg_e_parent" / "qvt_prepoisson":
            raise AssertionError("EVR2 KG-E staging path drift")
        if not (staged / "test.json").is_file():
            raise AssertionError("EVR2 KG-E staging lost canonical checker manifest")
        if (staged / "petsc_log_stale").exists():
            raise AssertionError("EVR2 KG-E staging retained generated artifact")


def _check_runtime_boundary() -> None:
    for relative in (
        "qpx_harness/coupling_evr2",
        "qpx_harness/coupling_evr2_runtime.py",
        "qpx_harness/coupling_evr2_timestep.py",
        "physics_harness/coupling_evr2",
        "physics_harness/coupling_evr2_runtime.py",
        "physics_harness/coupling_evr2_timestep.py",
    ):
        if (ROOT / relative).exists():
            raise AssertionError(f"retired EVR2 runtime owner resurrected: {relative}")

    for relative in (
        "physics_harness/adapters/moose/nonlinear_solver.py",
        "physics_harness/application/performance.py",
        "physics_harness/execution/cases.py",
        "physics_harness/execution/runtime.py",
        "physics_harness/evidence",
    ):
        if not (ROOT / relative).exists():
            raise AssertionError(f"canonical EVR2 generic capability missing: {relative}")

    if "qpx_harness" in Path(recipe.__file__).read_text():
        raise AssertionError("Issue31 recipe retained legacy runtime dependency")


def _check_production_route() -> None:
    source = (ROOT / "physics_harness" / "cli" / "app.py").read_text()
    for retired in ("coupling-evr2", "coupling_evr2_main", "coupling_evr2_timestep"):
        if retired in source:
            raise AssertionError(f"retired EVR2 CLI route resurrected: {retired}")


def main() -> int:
    try:
        _check_state_helper_contract()
        _check_manifest_contract()
        _check_failure_signature_contract()
        _check_generic_staging()
        _check_runtime_boundary()
        _check_production_route()
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_EVR2_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_EVR2_RUNTIME_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
