#!/usr/bin/env python3
"""P0 characterization for PF-3 transport-probe runtime orchestration."""
from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.execution.performance.probes import runtime
from qpx_harness.execution.performance.probes import transport as direct
from qpx_harness.cli.commands import performance as performance_cli

EXPECTED_SOURCE_SHA256 = "4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e"
EXPECTED_HEADER_SHA256 = "8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5"
EXPECTED_SOURCE_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
EXPECTED_HEADER_RELATIVE = Path("include/materials/QPXThermalDiffusionMaterial.h")
EXPECTED_TIMER_NAMES = {
    "evaluate": "qpx_transport_evaluate",
    "collision_pairs": "qpx_transport_collision_pairs",
    "dmix": "qpx_transport_dmix",
    "functor_DT": "qpx_transport_functor_DT",
    "functor_kT": "qpx_transport_functor_kT",
    "functor_Dmix": "qpx_transport_functor_Dmix",
}


def _sample_result(*, linear_iterations: int = 3) -> dict:
    return {
        "identity": {"input_sha256": "abc"},
        "problem": {"dofs": 10},
        "work": {
            "nonlinear_iterations": 2,
            "linear_iterations": linear_iterations,
            "residual_evaluations": 4,
        },
    }


def _check_constants() -> None:
    expected = {
        "ACCEPTED_SOURCE_SHA256": EXPECTED_SOURCE_SHA256,
        "ACCEPTED_HEADER_SHA256": EXPECTED_HEADER_SHA256,
        "SOURCE_RELATIVE": EXPECTED_SOURCE_RELATIVE,
        "HEADER_RELATIVE": EXPECTED_HEADER_RELATIVE,
    }
    for name, value in expected.items():
        if getattr(runtime, name) != value:
            raise AssertionError(f"runtime frozen constant drift: {name}")


def _check_parity_contract() -> None:
    baseline = _sample_result()
    same = json.loads(json.dumps(baseline))
    mutated = _sample_result(linear_iterations=5)
    expected_same = {
        "same_input_sha": True,
        "same_dofs": True,
        "same_nonlinear_iterations": True,
        "same_linear_iterations": True,
        "same_residual_evaluations": True,
    }
    expected_mutated = dict(expected_same)
    expected_mutated["same_linear_iterations"] = False
    if runtime._parity_checks(baseline, same) != expected_same:
        raise AssertionError("equal parity-check contract drift")
    if runtime._parity_checks(baseline, mutated) != expected_mutated:
        raise AssertionError("mutated parity-check contract drift")


def _check_manifest_resolution() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        case_dir = root / "case"
        case_dir.mkdir()
        (case_dir / "input.i").write_text("[Mesh]\n[]\n")
        smoke = root / "smoke"
        (smoke / "profile").mkdir(parents=True)
        manifest = {
            "case_id": "fixture",
            "case": {"directory": str(case_dir), "input": "input.i"},
        }
        baseline = _sample_result()
        (smoke / "profile_manifest.json").write_text(json.dumps(manifest))
        (smoke / "profile" / "result.json").write_text(json.dumps(baseline))
        resolved_manifest, resolved_baseline = runtime._resolve_case_manifest(smoke)
        if resolved_manifest != manifest or resolved_baseline != baseline:
            raise AssertionError("manifest resolution contract drift")

        (case_dir / "input.i").unlink()
        try:
            runtime._resolve_case_manifest(smoke)
        except runtime.ProbeRuntimeError:
            pass
        else:
            raise AssertionError("missing-case negative control passed")


def _check_restore_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        source = root / "source.C"
        exe = root / "qpx-opt"
        original_source = b"original-source"
        original_exe = b"original-exe"
        source.write_bytes(b"mutated")
        exe.write_bytes(b"mutated-exe")

        run_root = root / "runtime"
        run_root.mkdir()
        (run_root / "source_original.C").write_bytes(original_source)
        (run_root / "qpx-opt.original").write_bytes(original_exe)
        state = {
            "source_path": str(source),
            "source_sha_before": runtime.sha256_bytes(original_source),
            "executable_path": str(exe),
            "executable_sha_before": runtime.sha256_bytes(original_exe),
        }
        (run_root / "probe_state.json").write_text(json.dumps(state))
        if runtime.restore_probe(run_root, exe) != 0:
            raise AssertionError("runtime restore failed")
        if source.read_bytes() != original_source or exe.read_bytes() != original_exe:
            raise AssertionError("runtime restore content drift")

        missing_backup = root / "missing-backup"
        missing_backup.mkdir()
        (missing_backup / "probe_state.json").write_text(json.dumps(state))
        try:
            runtime.restore_probe(missing_backup, exe)
        except runtime.ProbeRuntimeError:
            pass
        else:
            raise AssertionError("missing-backup negative control passed")


def _check_callback_routing() -> None:
    if runtime.self_test() != 0:
        raise AssertionError("runtime self-test failed")

    original_runtime_self_test = runtime.self_test
    original_backend_self_test = direct.self_test
    try:
        runtime.self_test = lambda: 0
        direct.self_test = lambda: 0
        if performance_cli.transport_probe_main(["--self-test"]) != 0:
            raise AssertionError("backend positive self-test callback was not propagated")
        direct.self_test = lambda: 1
        if performance_cli.transport_probe_main(["--self-test"]) != 1:
            raise AssertionError("backend negative self-test callback was not propagated")
    finally:
        runtime.self_test = original_runtime_self_test
        direct.self_test = original_backend_self_test


def _check_direct_cutover() -> None:
    source = Path(direct.__file__).read_text()
    cli_source = Path(performance_cli.__file__).read_text()
    if "probe_runtime.run_managed_probe(" not in cli_source:
        raise AssertionError("transport command does not route through runtime owner")
    if "transport.instrument_source" not in cli_source or "transport.analyze_probe" not in cli_source:
        raise AssertionError("transport command callback binding drift")
    if "argparse" in source or "def main(" in source:
        raise AssertionError("direct capability retained CLI presentation")
    for forbidden in (
        "legacy.main(",
        "def _activate",
        "performance_transport_probe as legacy",
        "from . import performance_transport_probe\n",
        "legacy.",
    ):
        if forbidden in source:
            raise AssertionError(f"direct legacy dependency remains: {forbidden}")
    if "CppSource" not in source or "perfgraph." not in source:
        raise AssertionError("direct probe is not composed from generic C++/PerfGraph primitives")
    if direct.TIMER_NAMES != EXPECTED_TIMER_NAMES:
        raise AssertionError("direct timer-name contract drift")
    if direct.MARKER_PREFIX != "qpx_transport_":
        raise AssertionError("direct marker-prefix contract drift")
    if performance_cli.transport_probe_main(["--self-test"]) != 0:
        raise AssertionError("direct runtime-routed self-test failed")

    original_run = runtime.run_managed_probe

    def raise_backend_error(*args, **kwargs):
        raise direct.ProbeError("negative-control")

    runtime.run_managed_probe = raise_backend_error
    try:
        if performance_cli.transport_probe_main([]) != 2:
            raise AssertionError("direct ProbeError compatibility guard drift")
    finally:
        runtime.run_managed_probe = original_run


def _imports_legacy_probe(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "qpx_harness" and any(
                alias.name == "performance_transport_probe" for alias in node.names
            ):
                return True
            if node.module == "qpx_harness.performance_transport_probe":
                return True
        elif isinstance(node, ast.Import):
            if any(
                alias.name == "qpx_harness.performance_transport_probe"
                for alias in node.names
            ):
                return True
    return False


def _check_boundary() -> None:
    source = Path(runtime.__file__).read_text()
    for forbidden in (
        "from .transport",
        "from qpx_harness.execution.performance.probes.transport",
    ):
        if forbidden in source:
            raise AssertionError(f"runtime reverse dependency leaked: {forbidden}")

    if _imports_legacy_probe(Path(__file__)):
        raise AssertionError("WP8 still imports the retired legacy oracle")


def main() -> int:
    try:
        _check_constants()
        _check_parity_contract()
        _check_manifest_resolution()
        _check_restore_contract()
        _check_callback_routing()
        _check_direct_cutover()
        _check_boundary()
    except Exception as exc:
        print(f"ISSUE48_TRANSPORT_PROBE_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_TRANSPORT_PROBE_RUNTIME_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
