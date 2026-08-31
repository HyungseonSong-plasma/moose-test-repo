#!/usr/bin/env python3
"""P0 characterization for PF-3 transport-probe runtime orchestration."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import performance_transport_probe as legacy
from qpx_harness import performance_transport_probe_direct as direct
from qpx_harness import performance_transport_probe_runtime as runtime


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
    for name in (
        "ACCEPTED_SOURCE_SHA256",
        "ACCEPTED_HEADER_SHA256",
        "SOURCE_RELATIVE",
        "HEADER_RELATIVE",
    ):
        if getattr(runtime, name) != getattr(legacy, name):
            raise AssertionError(f"runtime constant drift: {name}")


def _check_parity_equivalence() -> None:
    baseline = _sample_result()
    same = json.loads(json.dumps(baseline))
    mutated = _sample_result(linear_iterations=5)
    if runtime._parity_checks(baseline, same) != legacy._parity_checks(baseline, same):
        raise AssertionError("equal parity-check behavior drift")
    if runtime._parity_checks(baseline, mutated) != legacy._parity_checks(
        baseline, mutated
    ):
        raise AssertionError("mutated parity-check behavior drift")
    if runtime._parity_checks(baseline, mutated)["same_linear_iterations"]:
        raise AssertionError("linear-iteration negative control passed")


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
        if runtime._resolve_case_manifest(smoke) != legacy._resolve_case_manifest(smoke):
            raise AssertionError("manifest resolution drift")

        (case_dir / "input.i").unlink()
        try:
            runtime._resolve_case_manifest(smoke)
        except runtime.ProbeRuntimeError:
            pass
        else:
            raise AssertionError("missing-case negative control passed")


def _check_restore_equivalence() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        source = root / "source.C"
        exe = root / "qpx-opt"
        source.write_bytes(b"mutated")
        exe.write_bytes(b"mutated-exe")

        for label, restore in (("legacy", legacy.restore_probe), ("runtime", runtime.restore_probe)):
            run_root = root / label
            run_root.mkdir()
            original_source = b"original-source"
            original_exe = b"original-exe"
            (run_root / "source_original.C").write_bytes(original_source)
            (run_root / "qpx-opt.original").write_bytes(original_exe)
            source.write_bytes(b"mutated")
            exe.write_bytes(b"mutated-exe")
            state = {
                "source_path": str(source),
                "source_sha_before": runtime.sha256_bytes(original_source),
                "executable_path": str(exe),
                "executable_sha_before": runtime.sha256_bytes(original_exe),
            }
            (run_root / "probe_state.json").write_text(json.dumps(state))
            if restore(run_root, exe) != 0:
                raise AssertionError(f"{label} restore failed")
            if source.read_bytes() != original_source or exe.read_bytes() != original_exe:
                raise AssertionError(f"{label} restore content drift")


def _check_callback_routing() -> None:
    if runtime.self_test() != 0:
        raise AssertionError("runtime self-test failed")

    def backend_pass() -> int:
        return 0

    def backend_fail() -> int:
        return 1

    unused_instrument = lambda text: (text, {})
    unused_analyze = lambda result, path: {}
    if runtime.main(
        ["--self-test"],
        instrument_source=unused_instrument,
        analyze_probe=unused_analyze,
        backend_self_test=backend_pass,
    ) != 0:
        raise AssertionError("backend positive self-test callback was not propagated")
    if runtime.main(
        ["--self-test"],
        instrument_source=unused_instrument,
        analyze_probe=unused_analyze,
        backend_self_test=backend_fail,
    ) != 1:
        raise AssertionError("backend negative self-test callback was not propagated")


def _check_direct_cutover() -> None:
    source = Path(direct.__file__).read_text()
    if "probe_runtime.main(" not in source:
        raise AssertionError("direct probe does not route through runtime owner")
    if "legacy.main(" in source or "def _activate" in source:
        raise AssertionError("legacy orchestration remains active in direct probe")
    if direct.main(["--self-test"]) != 0:
        raise AssertionError("direct runtime-routed self-test failed")

    original_main = direct.probe_runtime.main

    def raise_backend_error(*args, **kwargs):
        raise direct.ProbeError("negative-control")

    direct.probe_runtime.main = raise_backend_error
    try:
        if direct.main([]) != 2:
            raise AssertionError("direct ProbeError compatibility guard drift")
    finally:
        direct.probe_runtime.main = original_main


def _check_boundary() -> None:
    source = Path(runtime.__file__).read_text()
    for forbidden in (
        "performance_transport_probe_direct",
        "performance_transport_probe as",
        "performance_transport_probe import",
    ):
        if forbidden in source:
            raise AssertionError(f"runtime reverse dependency leaked: {forbidden}")


def main() -> int:
    try:
        _check_constants()
        _check_parity_equivalence()
        _check_manifest_resolution()
        _check_restore_equivalence()
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
