#!/usr/bin/env python3
"""P0 characterization for the canonical Issue31 EVR1 runtime owner."""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue31_coupling as recipe
from qpx_harness.coupling_evr1 import characterization as runtime_characterization
from qpx_harness.coupling_evr1 import classification as runtime_classification
from qpx_harness.coupling_evr1 import orchestration as runtime_owner
from qpx_harness.evidence import create_collision_safe_directory
from qpx_harness.performance.smoke import build_smoke_manifest


EXPECTED_EXPERIMENT_ID = "issue31-evr1-optimized-monolithic"
EXPECTED_PURGE_DIRECTORIES = (".jitcache",)
EXPECTED_PURGE_PATTERNS = (
    "input_out*",
    "r29_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


def _imports_module(path: Path, module: str) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base == module:
                return True
            if base == "qpx_harness" and module.startswith("qpx_harness."):
                leaf = module.split(".", 1)[1]
                if any(alias.name == leaf for alias in node.names):
                    return True
    return False


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


def _check_constants() -> None:
    if runtime_owner.EXPERIMENT_ID != EXPECTED_EXPERIMENT_ID:
        raise AssertionError("EVR1 experiment id drift")
    if runtime_owner.PURGE_DIRECTORY_NAMES != EXPECTED_PURGE_DIRECTORIES:
        raise AssertionError("EVR1 purge directory policy drift")
    if runtime_owner.PURGE_PATTERNS != EXPECTED_PURGE_PATTERNS:
        raise AssertionError("EVR1 purge pattern policy drift")


def _check_manifest_contract() -> None:
    case = Path("/tmp/issue31-case")
    actual = runtime_owner._manifest(
        mode="BENCHMARK",
        case_dir=case,
        case_id="Issue31_transport_only",
    )
    expected = build_smoke_manifest(
        mode="BENCHMARK",
        case_dir=case,
        input_name="input.i",
        experiment_id=EXPECTED_EXPERIMENT_ID,
        case_id="Issue31_transport_only",
        num_steps=1,
        species=list(recipe.SPECIES),
    )
    if actual != expected:
        raise AssertionError("EVR1 PF-1 manifest contract drift")


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
    actual = runtime_classification.preliminary_classification(
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
        (
            "PC_FACTORIZATION",
            15.0,
            "MONOLITHIC_LINEAR_ALGEBRA_BOUND_CANDIDATE",
        ),
        (
            "JACOBIAN_AD",
            14.0,
            "MONOLITHIC_APPLICATION_OR_JACOBIAN_BOUND_CANDIDATE",
        ),
        (None, 12.0, "MONOLITHIC_VIABILITY_REVIEW"),
    )
    for bottleneck, wall, label in candidates:
        mono = _pair("P2_PASS_P3_PASS", wall=wall, bottleneck=bottleneck)
        classification = (
            {"bottleneck_class": bottleneck} if bottleneck is not None else {}
        )
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
    this_path = Path(__file__)
    runtime_path = Path(runtime_owner.__file__)
    for historical in (
        "qpx_harness.coupling_evr1_safe",
    ):
        if _imports_module(this_path, historical):
            raise AssertionError(f"WP11 retained historical oracle import: {historical}")
        if _imports_module(runtime_path, historical):
            raise AssertionError(f"canonical EVR1 runtime imports historical owner: {historical}")

    source = runtime_path.read_text()
    for required in (
        "from recipes import issue31_coupling as recipe",
        "stage_case",
        "validate_referenced_files",
        "sha256_file",
        "utc_timestamp",
        "write_json_bundle",
        "recipe.transport_only_input",
        "recipe.physics_check",
    ):
        if required not in source:
            raise AssertionError(f"canonical EVR1 runtime missing owner composition: {required}")
    for forbidden in (
        "shutil.copytree",
        "hashlib.sha256",
        "def _referenced_files",
        "def _validate_referenced_files",
        "def transport_only_input",
        "def physics_check",
    ):
        if forbidden in source:
            raise AssertionError(f"canonical EVR1 runtime duplicated lower owner: {forbidden}")


def _check_cli_route() -> None:
    source = (ROOT / "qpx_harness" / "cli" / "app.py").read_text()
    required = (
        "from qpx_harness.cli.commands.coupling import coupling_evr1_main, coupling_evr2_main",
        '"coupling-evr1": coupling_evr1_main',
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"EVR1 CLI route missing canonical runtime token: {token}")
    for historical in (
        "from qpx_harness.coupling_evr1 import",
        "from qpx_harness.coupling_evr1_safe import",
    ):
        if historical in source:
            raise AssertionError(f"EVR1 CLI retained historical route: {historical}")


def main() -> int:
    try:
        _check_constants()
        _check_manifest_contract()
        _check_root_contract()
        _check_classification_contract()
        _check_boundary()
        _check_cli_route()
        if runtime_characterization.self_test() != 0:
            raise AssertionError("canonical EVR1 runtime self-test failed")
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_EVR1_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_EVR1_RUNTIME_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
