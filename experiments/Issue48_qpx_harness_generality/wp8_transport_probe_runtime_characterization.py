#!/usr/bin/env python3
"""P0 characterization for the retired PF-3 transport-probe runtime contract."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

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
HISTORICAL_EXPERIMENT_ID = "pf3-transport-targeted-probe"


class HistoricalProbeRuntimeError(RuntimeError):
    """Test-only error preserving the retired PF-3 runtime contract."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise HistoricalProbeRuntimeError(f"missing {label}: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise HistoricalProbeRuntimeError(f"{label} must be a JSON object: {path}")
    return payload


def _parity_checks(baseline: dict[str, Any], probe: dict[str, Any]) -> dict[str, bool]:
    """Frozen pre-retirement PF-3/PF-1 parity policy."""
    return {
        "same_input_sha": baseline.get("identity", {}).get("input_sha256")
        == probe.get("identity", {}).get("input_sha256"),
        "same_dofs": baseline.get("problem", {}).get("dofs")
        == probe.get("problem", {}).get("dofs"),
        "same_nonlinear_iterations": baseline.get("work", {}).get("nonlinear_iterations")
        == probe.get("work", {}).get("nonlinear_iterations"),
        "same_linear_iterations": baseline.get("work", {}).get("linear_iterations")
        == probe.get("work", {}).get("linear_iterations"),
        "same_residual_evaluations": baseline.get("work", {}).get("residual_evaluations")
        == probe.get("work", {}).get("residual_evaluations"),
    }


def _resolve_case_manifest(smoke_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Frozen direct-path portion of the retired PF-1 manifest resolver."""
    smoke_root = Path(smoke_root)
    profile_manifest = _load_json(
        smoke_root / "profile_manifest.json", "PF-1 profile manifest"
    )
    baseline_profile = _load_json(
        smoke_root / "profile" / "result.json", "PF-1 profile result"
    )
    case = profile_manifest.get("case")
    if not isinstance(case, dict):
        raise HistoricalProbeRuntimeError("PF-1 profile manifest has no case object")
    case_dir = Path(str(case.get("directory", ""))).expanduser()
    input_name = str(case.get("input", "input.i"))
    if case_dir.is_dir() and (case_dir / input_name).is_file():
        return profile_manifest, baseline_profile
    raise HistoricalProbeRuntimeError(
        "PF-1 case directory is unavailable and no matching current tests/<case_id> exists"
    )


def _restore_probe(run_root: Path, executable: Path | None = None) -> int:
    """Frozen emergency-restore contract; no build or Physics execution occurs."""
    run_root = Path(run_root).expanduser().resolve()
    state = _load_json(run_root / "probe_state.json", "probe state")
    source_path = Path(state["source_path"])
    backup_source = run_root / "source_original.C"
    if not backup_source.is_file():
        raise HistoricalProbeRuntimeError(f"missing source backup: {backup_source}")
    source_path.write_bytes(backup_source.read_bytes())
    os.utime(source_path, None)
    source_ok = _sha256_file(source_path) == state.get("source_sha_before")

    exe_path = (
        Path(executable).resolve()
        if executable is not None
        else Path(state["executable_path"])
    )
    backup_exe = run_root / "qpx-opt.original"
    binary_ok = True
    if backup_exe.is_file():
        shutil.copy2(backup_exe, exe_path)
        binary_ok = _sha256_file(exe_path) == state.get("executable_sha_before")
    return 0 if source_ok and binary_ok else 2


def _probe_manifest(profile_manifest: dict[str, Any]) -> dict[str, Any]:
    """Preserve the historical PF-3 PROFILE mutation without reviving its runner."""
    manifest = json.loads(json.dumps(profile_manifest))
    manifest["experiment_id"] = HISTORICAL_EXPERIMENT_ID
    manifest["mode"] = "PROFILE"
    manifest.setdefault("collectors", {})["perfgraph"] = True
    manifest["collectors"]["petsc_log"] = True
    manifest["stream_output"] = True
    return manifest


def _sample_result(*, linear_iterations: int = 3) -> dict[str, Any]:
    return {
        "identity": {"input_sha256": "abc"},
        "problem": {"dofs": 10},
        "work": {
            "nonlinear_iterations": 2,
            "linear_iterations": linear_iterations,
            "residual_evaluations": 4,
        },
    }


def _check_frozen_contract() -> None:
    if len(EXPECTED_SOURCE_SHA256) != 64 or len(EXPECTED_HEADER_SHA256) != 64:
        raise AssertionError("PF-3 frozen SHA contract drift")
    if EXPECTED_SOURCE_RELATIVE != Path("src/materials/QPXThermalDiffusionMaterial.C"):
        raise AssertionError("PF-3 source path contract drift")
    if EXPECTED_HEADER_RELATIVE != Path("include/materials/QPXThermalDiffusionMaterial.h"):
        raise AssertionError("PF-3 header path contract drift")
    if EXPECTED_TIMER_NAMES != {
        "evaluate": "qpx_transport_evaluate",
        "collision_pairs": "qpx_transport_collision_pairs",
        "dmix": "qpx_transport_dmix",
        "functor_DT": "qpx_transport_functor_DT",
        "functor_kT": "qpx_transport_functor_kT",
        "functor_Dmix": "qpx_transport_functor_Dmix",
    }:
        raise AssertionError("PF-3 timer vocabulary drift")


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
    if _parity_checks(baseline, same) != expected_same:
        raise AssertionError("equal parity-check contract drift")
    if _parity_checks(baseline, mutated) != expected_mutated:
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
        resolved_manifest, resolved_baseline = _resolve_case_manifest(smoke)
        if resolved_manifest != manifest or resolved_baseline != baseline:
            raise AssertionError("manifest resolution contract drift")

        (case_dir / "input.i").unlink()
        try:
            _resolve_case_manifest(smoke)
        except HistoricalProbeRuntimeError:
            pass
        else:
            raise AssertionError("missing-case negative control passed")


def _check_profile_manifest_contract() -> None:
    baseline = {
        "schema_version": 1,
        "experiment_id": "pf1-runtime-smoke",
        "case_id": "fixture",
        "mode": "BENCHMARK",
        "case": {"directory": "/tmp/case", "input": "input.i"},
        "collectors": {"work_counters": True, "perfgraph": False, "petsc_log": False},
        "stream_output": False,
    }
    actual = _probe_manifest(baseline)
    if actual["experiment_id"] != "pf3-transport-targeted-probe":
        raise AssertionError("PF-3 experiment identity drift")
    if actual["mode"] != "PROFILE":
        raise AssertionError("PF-3 profile mode drift")
    if actual["collectors"] != {
        "work_counters": True,
        "perfgraph": True,
        "petsc_log": True,
    }:
        raise AssertionError("PF-3 collector mutation drift")
    if actual["stream_output"] is not True:
        raise AssertionError("PF-3 stream-output contract drift")
    if baseline["mode"] != "BENCHMARK" or baseline["collectors"]["perfgraph"] is not False:
        raise AssertionError("PF-3 manifest mutation modified the baseline object")


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
            "source_sha_before": _sha256_bytes(original_source),
            "executable_path": str(exe),
            "executable_sha_before": _sha256_bytes(original_exe),
        }
        (run_root / "probe_state.json").write_text(json.dumps(state))
        if _restore_probe(run_root, exe) != 0:
            raise AssertionError("historical runtime restore failed")
        if source.read_bytes() != original_source or exe.read_bytes() != original_exe:
            raise AssertionError("historical runtime restore content drift")

        missing_backup = root / "missing-backup"
        missing_backup.mkdir()
        (missing_backup / "probe_state.json").write_text(json.dumps(state))
        try:
            _restore_probe(missing_backup, exe)
        except HistoricalProbeRuntimeError:
            pass
        else:
            raise AssertionError("missing-backup negative control passed")


def _check_current_generic_boundaries() -> None:
    required_files = {
        "physics_harness/application/performance.py": (
            "def run_measurement(",
            "def validate_experiment_manifest(",
        ),
        "physics_harness/execution/runtime.py": (
            "def resolve_executable(",
            "def run_physics(",
            "def validate_executable(",
        ),
        "physics_harness/evidence/identity.py": (
            "def sha256_file(",
            "def create_collision_safe_directory(",
        ),
        "physics_harness/observation/source_code/cpp.py": ("class CppSource",),
        "physics_harness/adapters/moose/performance/perfgraph.py": (
            "def rows_from_payload(",
            "def sum_timer(",
        ),
    }
    for relative, tokens in required_files.items():
        path = ROOT / relative
        if not path.is_file():
            raise AssertionError(f"canonical generic owner missing: {relative}")
        source = path.read_text()
        for token in tokens:
            if token not in source:
                raise AssertionError(f"canonical generic owner contract missing: {relative}: {token}")


def _check_retirement_boundary() -> None:
    retired_paths = (
        "qpx_harness/execution/performance/probes/runtime.py",
        "qpx_harness/execution/performance/probes/transport.py",
        "qpx_harness/performance_transport_probe.py",
        "physics_harness/execution/performance/probes/runtime.py",
        "physics_harness/execution/performance/probes/transport.py",
        "physics_harness/performance_transport_probe.py",
    )
    for relative in retired_paths:
        if (ROOT / relative).exists():
            raise AssertionError(f"retired PF-3 campaign owner resurrected: {relative}")

    cli_source = (ROOT / "physics_harness/cli/app.py").read_text()
    performance_cli = (ROOT / "physics_harness/cli/commands/performance.py").read_text()
    for token in (
        "transport-probe",
        "transport_probe_main",
        "PF3_TRANSPORT",
        "performance_transport_probe",
    ):
        if token in cli_source or token in performance_cli:
            raise AssertionError(f"retired PF-3 CLI surface resurrected: {token}")


def main() -> int:
    try:
        _check_frozen_contract()
        print("ISSUE48_TRANSPORT_PROBE_RUNTIME_CHECK: frozen-contract=PASS")
        _check_parity_contract()
        print("ISSUE48_TRANSPORT_PROBE_RUNTIME_CHECK: parity=PASS")
        _check_manifest_resolution()
        print("ISSUE48_TRANSPORT_PROBE_RUNTIME_CHECK: manifest-resolution=PASS")
        _check_profile_manifest_contract()
        print("ISSUE48_TRANSPORT_PROBE_RUNTIME_CHECK: profile-manifest=PASS")
        _check_restore_contract()
        print("ISSUE48_TRANSPORT_PROBE_RUNTIME_CHECK: restore=PASS")
        _check_current_generic_boundaries()
        print("ISSUE48_TRANSPORT_PROBE_RUNTIME_CHECK: generic-owners=PASS")
        _check_retirement_boundary()
        print("ISSUE48_TRANSPORT_PROBE_RUNTIME_CHECK: retired-campaign-surface=ABSENT")
    except Exception as exc:
        print(f"ISSUE48_TRANSPORT_PROBE_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_TRANSPORT_PROBE_RUNTIME_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
