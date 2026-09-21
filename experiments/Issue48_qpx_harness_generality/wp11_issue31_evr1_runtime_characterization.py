#!/usr/bin/env python3
"""P0 characterization for the retired Issue31 EVR1 runtime contract."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue31_coupling as recipe
from physics_harness.application.performance import result_status, validate_experiment_manifest
from physics_harness.evidence import create_collision_safe_directory


EXPECTED_EXPERIMENT_ID = "issue31-evr1-optimized-monolithic"
EXPECTED_PURGE_DIRECTORIES = (".jitcache",)
EXPECTED_PURGE_PATTERNS = (
    "input_out*",
    "r29_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


def _historical_manifest(*, mode: str, case_dir: Path, case_id: str) -> dict[str, Any]:
    """Preserve the pre-retirement PF-1 manifest emitted by EVR1."""
    manifest = {
        "schema_version": 1,
        "experiment_id": EXPECTED_EXPERIMENT_ID,
        "case_id": case_id,
        "mode": mode,
        "case": {
            "directory": str(Path(case_dir).expanduser().resolve()),
            "input": "input.i",
        },
        "runtime": {"num_steps": 1},
        "collectors": {
            "work_counters": True,
            "perfgraph": mode == "PROFILE",
            "petsc_log": mode == "PROFILE",
        },
        "stream_output": True,
        "physics": {"species": list(recipe.SPECIES)},
    }
    validate_experiment_manifest(manifest)
    return manifest


def _result(status: str, *, wall: float | None = None) -> dict:
    performance = {} if wall is None else {"wall_seconds": wall}
    return {"validation": {"status": status}, "performance": performance}


def _pair(
    status: str,
    *,
    wall: float | None = None,
    root: str = "/tmp/issue31",
    bottleneck: str | None = None,
) -> dict:
    pair = {
        "root": root,
        "benchmark": _result(status, wall=wall),
        "profile": None,
        "investigation": None,
    }
    if bottleneck is not None:
        pair["investigation"] = {
            "classification": {"bottleneck_class": bottleneck}
        }
    return pair


def _wall(pair: dict[str, Any], mode: str = "benchmark") -> float | None:
    result = pair.get(mode)
    value = result.get("performance", {}).get("wall_seconds") if result else None
    return float(value) if isinstance(value, (int, float)) else None


def _preliminary_classification(
    transport: dict[str, Any],
    monolithic: dict[str, Any],
    transport_physics: dict[str, Any] | None,
    monolithic_physics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Frozen pre-retirement EVR1 classification policy."""
    if result_status(transport.get("benchmark")) != "P2_PASS_P3_PASS":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "transport-only known-good control did not complete",
        }
    if transport_physics is None or transport_physics.get("status") != "PASS":
        return {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "transport-only runtime completed but physics checker failed",
        }

    mono_status = result_status(monolithic.get("benchmark"))
    if mono_status == "HARNESS_OR_CONSTRUCTION_FAIL":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "monolithic Q0 failed P2/construction",
        }
    if mono_status == "RUNTIME_FAIL_OR_NONCONVERGENCE":
        log = Path(monolithic["root"]) / "benchmark" / "p3_run.log"
        text = log.read_text(errors="replace") if log.is_file() else ""
        if re.search(r"DIVERGED|did not converge|Nonlinear solve.*fail", text, re.IGNORECASE):
            return {
                "class": "MONOLITHIC_NONLINEAR_CONVERGENCE_FAIL",
                "reason": "monolithic Q0 reached runtime but nonlinear solve did not converge",
            }
        return {
            "class": "MONOLITHIC_RUNTIME_FAIL",
            "reason": "monolithic Q0 failed at runtime without a proven convergence signature",
        }
    if mono_status != "P2_PASS_P3_PASS":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": f"monolithic benchmark status is {mono_status!r}",
        }
    if monolithic_physics is None or monolithic_physics.get("status") != "PASS":
        return {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "monolithic Q0 runtime completed but physics checker failed",
        }

    investigation = monolithic.get("investigation") or {}
    classification = investigation.get("classification", {})
    bottleneck = classification.get("bottleneck_class")
    if bottleneck in {"PC_FACTORIZATION", "LINEAR_SOLVE"}:
        label = "MONOLITHIC_LINEAR_ALGEBRA_BOUND_CANDIDATE"
    elif bottleneck in {"APPLICATION_EVALUATION", "JACOBIAN_AD"}:
        label = "MONOLITHIC_APPLICATION_OR_JACOBIAN_BOUND_CANDIDATE"
    else:
        label = "MONOLITHIC_VIABILITY_REVIEW"

    t_wall = _wall(transport)
    m_wall = _wall(monolithic)
    ratio = m_wall / t_wall if t_wall and m_wall is not None else None
    return {
        "class": label,
        "reason": "monolithic one-step completed; final viability requires evidence review",
        "transport_benchmark_wall_seconds": t_wall,
        "monolithic_benchmark_wall_seconds": m_wall,
        "monolithic_to_transport_wall_ratio": ratio,
        "bottleneck": classification,
    }


def _check_constants() -> None:
    if EXPECTED_EXPERIMENT_ID != "issue31-evr1-optimized-monolithic":
        raise AssertionError("EVR1 experiment id drift")
    if EXPECTED_PURGE_DIRECTORIES != (".jitcache",):
        raise AssertionError("EVR1 purge directory policy drift")
    if EXPECTED_PURGE_PATTERNS != (
        "input_out*",
        "r29_csv*",
        "perfgraph*",
        "petsc_log*",
        "metrics*",
    ):
        raise AssertionError("EVR1 purge pattern policy drift")


def _check_manifest_contract() -> None:
    case = Path("/tmp/issue31-case")
    actual = _historical_manifest(
        mode="BENCHMARK",
        case_dir=case,
        case_id="Issue31_transport_only",
    )
    expected = {
        "schema_version": 1,
        "experiment_id": EXPECTED_EXPERIMENT_ID,
        "case_id": "Issue31_transport_only",
        "mode": "BENCHMARK",
        "case": {"directory": str(case.resolve()), "input": "input.i"},
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
        raise AssertionError("EVR1 PF-1 manifest contract drift")

    profile = _historical_manifest(
        mode="PROFILE",
        case_dir=case,
        case_id="Issue31_transport_only",
    )
    if not profile["collectors"]["perfgraph"] or not profile["collectors"]["petsc_log"]:
        raise AssertionError("EVR1 PROFILE collector contract drift")


def _check_root_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        stem = "coupling_evr1_Issue31_20000101T000000Z"
        first = create_collision_safe_directory(root, stem)
        second = create_collision_safe_directory(root, stem)
        if first.name != "coupling_evr1_Issue31_20000101T000000Z":
            raise AssertionError("EVR1 result-root naming drift")
        if second.name != "coupling_evr1_Issue31_20000101T000000Z_01":
            raise AssertionError("EVR1 result-root collision policy drift")


def _assert_decision(
    expected: dict,
    transport: dict,
    monolithic: dict,
    transport_physics: dict | None,
    monolithic_physics: dict | None,
) -> None:
    actual = _preliminary_classification(
        transport,
        monolithic,
        transport_physics,
        monolithic_physics,
    )
    if actual != expected:
        raise AssertionError(f"EVR1 classification contract drift: {actual} != {expected}")


def _check_classification_contract() -> None:
    ok = {"status": "PASS"}
    bad = {"status": "FAIL"}
    transport = _pair("P2_PASS_P3_PASS", wall=10.0)

    _assert_decision(
        {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "transport-only known-good control did not complete",
        },
        _pair("HARNESS_OR_CONSTRUCTION_FAIL"),
        _pair("P2_PASS_P3_PASS", wall=15.0),
        None,
        ok,
    )
    _assert_decision(
        {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "transport-only runtime completed but physics checker failed",
        },
        transport,
        _pair("P2_PASS_P3_PASS", wall=15.0),
        bad,
        ok,
    )
    _assert_decision(
        {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "monolithic Q0 failed P2/construction",
        },
        transport,
        _pair("HARNESS_OR_CONSTRUCTION_FAIL"),
        ok,
        None,
    )
    _assert_decision(
        {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "monolithic Q0 runtime completed but physics checker failed",
        },
        transport,
        _pair("P2_PASS_P3_PASS", wall=15.0),
        ok,
        bad,
    )

    candidates = (
        ("PC_FACTORIZATION", 15.0, "MONOLITHIC_LINEAR_ALGEBRA_BOUND_CANDIDATE"),
        ("JACOBIAN_AD", 14.0, "MONOLITHIC_APPLICATION_OR_JACOBIAN_BOUND_CANDIDATE"),
        (None, 12.0, "MONOLITHIC_VIABILITY_REVIEW"),
    )
    for bottleneck, wall, label in candidates:
        mono = _pair("P2_PASS_P3_PASS", wall=wall, bottleneck=bottleneck)
        classification = {"bottleneck_class": bottleneck} if bottleneck is not None else {}
        _assert_decision(
            {
                "class": label,
                "reason": "monolithic one-step completed; final viability requires evidence review",
                "transport_benchmark_wall_seconds": 10.0,
                "monolithic_benchmark_wall_seconds": wall,
                "monolithic_to_transport_wall_ratio": wall / 10.0,
                "bottleneck": classification,
            },
            transport,
            mono,
            ok,
            ok,
        )

    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        log_dir = root / "benchmark"
        log_dir.mkdir()
        (log_dir / "p3_run.log").write_text("DIVERGED_MAX_IT\n")
        _assert_decision(
            {
                "class": "MONOLITHIC_NONLINEAR_CONVERGENCE_FAIL",
                "reason": "monolithic Q0 reached runtime but nonlinear solve did not converge",
            },
            transport,
            _pair("RUNTIME_FAIL_OR_NONCONVERGENCE", root=str(root)),
            ok,
            None,
        )

    with tempfile.TemporaryDirectory() as tmp_name:
        _assert_decision(
            {
                "class": "MONOLITHIC_RUNTIME_FAIL",
                "reason": "monolithic Q0 failed at runtime without a proven convergence signature",
            },
            transport,
            _pair("RUNTIME_FAIL_OR_NONCONVERGENCE", root=tmp_name),
            ok,
            None,
        )


def _check_boundary() -> None:
    for relative in (
        "qpx_harness/coupling_evr1",
        "qpx_harness/coupling_evr1_runtime.py",
        "qpx_harness/coupling_evr1_safe.py",
        "physics_harness/coupling_evr1",
        "physics_harness/coupling_evr1_runtime.py",
        "physics_harness/coupling_evr1_safe.py",
    ):
        if (ROOT / relative).exists():
            raise AssertionError(f"retired EVR1 campaign owner resurrected: {relative}")

    for relative in (
        "physics_harness/evidence/identity.py",
        "physics_harness/execution/cases.py",
        "physics_harness/execution/runtime.py",
        "physics_harness/application/performance.py",
    ):
        if not (ROOT / relative).is_file():
            raise AssertionError(f"canonical EVR1 generic primitive missing: {relative}")

    recipe_source = Path(recipe.__file__).read_text()
    if "qpx_harness" in recipe_source:
        raise AssertionError("Issue31 recipe retained legacy production dependency")


def _check_cli_route() -> None:
    source = (ROOT / "physics_harness" / "cli" / "app.py").read_text()
    for retired in ("coupling-evr1", "coupling_evr1_main", "coupling_evr1_safe"):
        if retired in source:
            raise AssertionError(f"retired EVR1 CLI route resurrected: {retired}")


def main() -> int:
    try:
        _check_constants()
        _check_manifest_contract()
        _check_root_contract()
        _check_classification_contract()
        _check_boundary()
        _check_cli_route()
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_EVR1_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_EVR1_RUNTIME_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
