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
from qpx_harness import coupling_evr1 as legacy
from qpx_harness import coupling_evr1_runtime as runtime
from qpx_harness.performance_smoke import build_smoke_manifest


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
    return {
        "validation": {"status": status},
        "performance": performance,
    }


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
    if runtime.EXPERIMENT_ID != EXPECTED_EXPERIMENT_ID:
        raise AssertionError("EVR1 experiment id drift")
    if runtime.PURGE_DIRECTORY_NAMES != EXPECTED_PURGE_DIRECTORIES:
        raise AssertionError("EVR1 purge directory policy drift")
    if runtime.PURGE_PATTERNS != EXPECTED_PURGE_PATTERNS:
        raise AssertionError("EVR1 purge pattern policy drift")


def _check_manifest_contract() -> None:
    case = Path("/tmp/issue31-case")
    actual = runtime._manifest(
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
        first = runtime._create_root(root, timestamp="20000101T000000Z")
        second = runtime._create_root(root, timestamp="20000101T000000Z")
        if first.name != "coupling_evr1_Issue31_20000101T000000Z":
            raise AssertionError("EVR1 result-root naming drift")
        if second.name != "coupling_evr1_Issue31_20000101T000000Z_01":
            raise AssertionError("EVR1 result-root collision policy drift")


def _assert_classification_equivalent(
    transport: dict,
    monolithic: dict,
    transport_physics: dict | None,
    monolithic_physics: dict | None,
) -> None:
    expected = legacy.preliminary_classification(
        transport,
        monolithic,
        transport_physics,
        monolithic_physics,
    )
    actual = runtime.preliminary_classification(
        transport,
        monolithic,
        transport_physics,
        monolithic_physics,
    )
    if actual != expected:
        raise AssertionError(
            f"EVR1 preliminary classification equivalence drift: {actual} != {expected}"
        )


def _check_classification_equivalence() -> None:
    ok_physics = {"status": "PASS"}
    bad_physics = {"status": "FAIL"}

    transport_pass = _pair("P2_PASS_P3_PASS", wall=10.0)
    mono_linear = _pair(
        "P2_PASS_P3_PASS",
        wall=15.0,
        bottleneck="PC_FACTORIZATION",
    )
    mono_app = _pair(
        "P2_PASS_P3_PASS",
        wall=14.0,
        bottleneck="JACOBIAN_AD",
    )
    mono_review = _pair("P2_PASS_P3_PASS", wall=12.0)

    for mono in (mono_linear, mono_app, mono_review):
        _assert_classification_equivalent(
            transport_pass,
            mono,
            ok_physics,
            ok_physics,
        )

    _assert_classification_equivalent(
        _pair("HARNESS_OR_CONSTRUCTION_FAIL"),
        mono_linear,
        None,
        ok_physics,
    )
    _assert_classification_equivalent(
        transport_pass,
        mono_linear,
        bad_physics,
        ok_physics,
    )
    _assert_classification_equivalent(
        transport_pass,
        _pair("HARNESS_OR_CONSTRUCTION_FAIL"),
        ok_physics,
        None,
    )
    _assert_classification_equivalent(
        transport_pass,
        _pair("P2_PASS_P3_PASS"),
        ok_physics,
        bad_physics,
    )

    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        log_dir = root / "benchmark"
        log_dir.mkdir()
        (log_dir / "p3_run.log").write_text("DIVERGED_MAX_IT\n")
        _assert_classification_equivalent(
            transport_pass,
            _pair("RUNTIME_FAIL_OR_NONCONVERGENCE", root=str(root)),
            ok_physics,
            None,
        )


def _check_boundary() -> None:
    path = Path(runtime.__file__)
    if _imports_module(path, "qpx_harness.coupling_evr1"):
        raise AssertionError("canonical EVR1 runtime imports legacy base")
    if _imports_module(path, "qpx_harness.coupling_evr1_safe"):
        raise AssertionError("canonical EVR1 runtime imports safe adapter")

    source = path.read_text()
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


def main() -> int:
    try:
        _check_constants()
        _check_manifest_contract()
        _check_root_contract()
        _check_classification_equivalence()
        _check_boundary()
        if runtime.self_test() != 0:
            raise AssertionError("canonical EVR1 runtime self-test failed")
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_EVR1_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_EVR1_RUNTIME_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
