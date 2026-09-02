"""Managed runtime orchestration for the PF-3 transport probe.

This module owns source backup/mutation, rebuild, PROFILE execution, parity
checks, and restoration. Instrumentation construction and evidence analysis are
backend callbacks supplied by the caller so runtime orchestration does not
import a particular probe implementation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ACCEPTED_SOURCE_SHA256 = "4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e"
ACCEPTED_HEADER_SHA256 = "8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5"
SOURCE_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
HEADER_RELATIVE = Path("include/materials/QPXThermalDiffusionMaterial.h")

InstrumentSource = Callable[[str], tuple[str, dict[str, Any]]]
AnalyzeProbe = Callable[[dict[str, Any], Path], dict[str, Any]]
SelfTest = Callable[[], int]


class ProbeRuntimeError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise ProbeRuntimeError(f"missing {label}: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ProbeRuntimeError(f"{label} must be a JSON object: {path}")
    return payload


def _stream_command(command: list[str], *, cwd: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("PF3_TRANSPORT_COMMAND:", shlex.join(command))
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log.write(line)
            log.flush()
        return process.wait()


def _create_probe_root(results_root: Path, case_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", case_id).strip("_") or "case"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(results_root) / f"pf3_transport_probe_{safe}_{stamp}"
    index = 1
    while root.exists():
        root = Path(results_root) / f"pf3_transport_probe_{safe}_{stamp}_{index:02d}"
        index += 1
    root.mkdir(parents=True)
    return root


def _resolve_case_manifest(smoke_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    smoke_root = Path(smoke_root)
    profile_manifest = _load_json(
        smoke_root / "profile_manifest.json", "PF-1 profile manifest"
    )
    baseline_profile = _load_json(
        smoke_root / "profile" / "result.json", "PF-1 profile result"
    )
    case = profile_manifest.get("case")
    if not isinstance(case, dict):
        raise ProbeRuntimeError("PF-1 profile manifest has no case object")
    case_dir = Path(str(case.get("directory", ""))).expanduser()
    input_name = str(case.get("input", "input.i"))
    if case_dir.is_dir() and (case_dir / input_name).is_file():
        return profile_manifest, baseline_profile

    repo_root = Path(__file__).resolve().parents[3]
    case_id = str(profile_manifest.get("case_id", ""))
    candidate = repo_root / "tests" / case_id
    if candidate.is_dir() and (candidate / input_name).is_file():
        profile_manifest = json.loads(json.dumps(profile_manifest))
        profile_manifest["case"]["directory"] = str(candidate.resolve())
        return profile_manifest, baseline_profile
    raise ProbeRuntimeError(
        "PF-1 case directory is unavailable and no matching current tests/<case_id> exists"
    )


def _parity_checks(baseline: dict[str, Any], probe: dict[str, Any]) -> dict[str, bool]:
    return {
        "same_input_sha": baseline.get("identity", {}).get("input_sha256")
        == probe.get("identity", {}).get("input_sha256"),
        "same_dofs": baseline.get("problem", {}).get("dofs")
        == probe.get("problem", {}).get("dofs"),
        "same_nonlinear_iterations": baseline.get("work", {}).get(
            "nonlinear_iterations"
        )
        == probe.get("work", {}).get("nonlinear_iterations"),
        "same_linear_iterations": baseline.get("work", {}).get("linear_iterations")
        == probe.get("work", {}).get("linear_iterations"),
        "same_residual_evaluations": baseline.get("work", {}).get(
            "residual_evaluations"
        )
        == probe.get("work", {}).get("residual_evaluations"),
    }


def restore_probe(run_root: Path, executable: Path | None = None) -> int:
    """Emergency recovery for a probe interrupted before its finally block."""
    run_root = Path(run_root).expanduser().resolve()
    state = _load_json(run_root / "probe_state.json", "probe state")
    source_path = Path(state["source_path"])
    backup_source = run_root / "source_original.C"
    if not backup_source.is_file():
        raise ProbeRuntimeError(f"missing source backup: {backup_source}")
    source_path.write_bytes(backup_source.read_bytes())
    os.utime(source_path, None)
    source_ok = sha256_file(source_path) == state.get("source_sha_before")

    exe_path = (
        Path(executable).resolve()
        if executable is not None
        else Path(state["executable_path"])
    )
    backup_exe = run_root / "qpx-opt.original"
    binary_ok = True
    if backup_exe.is_file():
        shutil.copy2(backup_exe, exe_path)
        binary_ok = sha256_file(exe_path) == state.get("executable_sha_before")

    state["emergency_restore"] = {
        "source_restored": source_ok,
        "binary_restored": binary_ok,
        "restored_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(run_root / "probe_state.json", state)
    print("PF3_TRANSPORT_RESTORE:", "PASS" if source_ok and binary_ok else "FAIL")
    return 0 if source_ok and binary_ok else 2


def run_managed_probe(
    *,
    executable_arg: str | Path | None,
    instrument_source: InstrumentSource,
    analyze_probe: AnalyzeProbe,
    smoke_root_arg: Path | None = None,
    source_arg: Path | None = None,
    build_command_arg: str | None = None,
    jobs: int | None = None,
    allow_source_sha_mismatch: bool = False,
) -> int:
    from ..runner import run_measurement
    from ...analysis.performance.investigation import discover_latest_smoke
    from ..smoke import default_results_root
    from ...execution.runtime import resolve_executable, validate_executable

    exe = resolve_executable(executable_arg)
    validate_executable(exe)
    qpx_root = exe.parent.resolve()
    results_root = default_results_root(exe)
    results_root.mkdir(parents=True, exist_ok=True)
    smoke_root = (
        Path(smoke_root_arg).expanduser().resolve()
        if smoke_root_arg is not None
        else discover_latest_smoke(results_root)
    )
    profile_manifest, baseline_profile = _resolve_case_manifest(smoke_root)
    case_id = str(profile_manifest.get("case_id") or smoke_root.name)
    run_root = _create_probe_root(results_root, case_id)
    print(f"PF3_TRANSPORT_PROBE_ROOT: {run_root}")
    print(f"PF3_TRANSPORT_BASELINE_ROOT: {smoke_root}")

    source_path = (
        Path(source_arg).expanduser().resolve()
        if source_arg is not None
        else qpx_root / SOURCE_RELATIVE
    )
    header_path = qpx_root / HEADER_RELATIVE
    if not source_path.is_file():
        raise ProbeRuntimeError(f"transport source does not exist: {source_path}")
    if not header_path.is_file():
        raise ProbeRuntimeError(f"transport header does not exist: {header_path}")

    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    source_sha = sha256_bytes(source_bytes)
    header_sha = sha256_file(header_path)
    if not allow_source_sha_mismatch and source_sha != ACCEPTED_SOURCE_SHA256:
        raise ProbeRuntimeError(
            "QPXThermalDiffusionMaterial.C SHA does not match the accepted frozen source; "
            f"expected={ACCEPTED_SOURCE_SHA256} actual={source_sha}"
        )
    if not allow_source_sha_mismatch and header_sha != ACCEPTED_HEADER_SHA256:
        raise ProbeRuntimeError(
            "QPXThermalDiffusionMaterial.h SHA does not match the accepted frozen source; "
            f"expected={ACCEPTED_HEADER_SHA256} actual={header_sha}"
        )

    instrumented_text, instrumentation = instrument_source(source_text)
    instrumented_bytes = instrumented_text.encode("utf-8")
    instrumented_sha = sha256_bytes(instrumented_bytes)
    shutil.copy2(source_path, run_root / "source_original.C")
    (run_root / "source_instrumented.C").write_bytes(instrumented_bytes)
    shutil.copy2(exe, run_root / "qpx-opt.original")

    before_exe_sha = sha256_file(exe)
    state: dict[str, Any] = {
        "schema_version": 1,
        "status": "PREPARED",
        "source_path": str(source_path),
        "source_sha_before": source_sha,
        "source_sha_instrumented": instrumented_sha,
        "header_path": str(header_path),
        "header_sha": header_sha,
        "accepted_source_sha": ACCEPTED_SOURCE_SHA256,
        "accepted_header_sha": ACCEPTED_HEADER_SHA256,
        "executable_path": str(exe),
        "executable_sha_before": before_exe_sha,
        "smoke_root": str(smoke_root),
        "instrumentation": instrumentation,
    }
    _write_json(run_root / "probe_state.json", state)

    jobs_value = jobs if jobs is not None else max(1, min(8, os.cpu_count() or 1))
    build_command = (
        shlex.split(build_command_arg)
        if build_command_arg
        else ["make", f"-j{jobs_value}"]
    )
    if not build_command:
        raise ProbeRuntimeError("build command is empty")

    instrument_build_rc: int | None = None
    profile_rc: int | None = None
    restore_build_rc: int | None = None
    restored_source_ok = False
    restored_binary_ok = False
    summary: dict[str, Any] = {
        "schema_version": 1,
        "case_id": case_id,
        "probe_root": str(run_root),
        "baseline_smoke_root": str(smoke_root),
    }

    try:
        source_path.write_bytes(instrumented_bytes)
        state["status"] = "SOURCE_INSTRUMENTED"
        _write_json(run_root / "probe_state.json", state)
        print(f"PF3_TRANSPORT_SOURCE_SHA: {source_sha}")
        print(f"PF3_TRANSPORT_INSTRUMENTED_SHA: {instrumented_sha}")

        instrument_build_rc = _stream_command(
            build_command,
            cwd=qpx_root,
            log_path=run_root / "build_instrumented.log",
        )
        if instrument_build_rc != 0:
            raise ProbeRuntimeError(
                f"instrumented QPX build failed with return code {instrument_build_rc}"
            )
        state["status"] = "INSTRUMENTED_BUILD_PASS"
        state["executable_sha_instrumented"] = sha256_file(exe)
        _write_json(run_root / "probe_state.json", state)
        print("PF3_TRANSPORT_BUILD: PASS")

        probe_manifest = json.loads(json.dumps(profile_manifest))
        probe_manifest["experiment_id"] = "pf3-transport-targeted-probe"
        probe_manifest["mode"] = "PROFILE"
        probe_manifest.setdefault("collectors", {})["perfgraph"] = True
        probe_manifest["collectors"]["petsc_log"] = True
        probe_manifest["stream_output"] = True
        manifest_path = run_root / "profile_manifest.json"
        _write_json(manifest_path, probe_manifest)
        profile_rc = run_measurement(
            manifest_path, executable=exe, out_dir=run_root / "profile"
        )
        if profile_rc != 0:
            raise ProbeRuntimeError(
                f"instrumented PROFILE run failed with return code {profile_rc}"
            )
        probe_result = _load_json(
            run_root / "profile" / "result.json", "probe profile result"
        )
        if probe_result.get("validation", {}).get("status") != "P2_PASS_P3_PASS":
            raise ProbeRuntimeError("instrumented PROFILE result is not P2_PASS_P3_PASS")
        perfgraph_value = probe_result.get("evidence", {}).get("perfgraph_json")
        if not isinstance(perfgraph_value, str) or not perfgraph_value:
            raise ProbeRuntimeError("instrumented PROFILE result has no PerfGraph JSON evidence")

        analysis = analyze_probe(probe_result, Path(perfgraph_value))
        parity = _parity_checks(baseline_profile, probe_result)
        baseline_wall = float(
            baseline_profile.get("performance", {}).get("wall_seconds") or 0.0
        )
        probe_wall = float(probe_result.get("performance", {}).get("wall_seconds") or 0.0)
        profile_ratio = probe_wall / baseline_wall if baseline_wall > 0 else None
        analysis["parity_checks"] = parity
        analysis["instrumented_to_baseline_profile_ratio"] = profile_ratio
        analysis["instrumentation_overhead_warning"] = (
            profile_ratio is not None and profile_ratio > 1.25
        )
        if not all(parity.values()):
            analysis["analysis_status"] = "EVIDENCE_PARITY_FAIL"
        summary.update(
            {
                "analysis": analysis,
                "profile_returncode": profile_rc,
                "profile_result": str(run_root / "profile" / "result.json"),
                "source_sha_before": source_sha,
                "source_sha_instrumented": instrumented_sha,
                "executable_sha_before": before_exe_sha,
                "executable_sha_instrumented": state.get("executable_sha_instrumented"),
            }
        )
        state["status"] = "PROFILE_ANALYZED"
        _write_json(run_root / "probe_state.json", state)
    except Exception as exc:
        summary["error"] = str(exc)
        print(f"PF3_TRANSPORT_PROBE_ERROR: {exc}", file=sys.stderr)
    finally:
        source_path.write_bytes(source_bytes)
        os.utime(source_path, None)
        restored_source_ok = sha256_file(source_path) == source_sha
        print(
            "PF3_TRANSPORT_SOURCE_RESTORE:",
            "PASS" if restored_source_ok else "FAIL",
        )
        if restored_source_ok:
            restore_build_rc = _stream_command(
                build_command,
                cwd=qpx_root,
                log_path=run_root / "build_restored.log",
            )
        if restore_build_rc == 0:
            restored_binary_ok = True
        else:
            try:
                shutil.copy2(run_root / "qpx-opt.original", exe)
                restored_binary_ok = sha256_file(exe) == before_exe_sha
            except OSError:
                restored_binary_ok = False
        state["status"] = (
            "RESTORED"
            if restored_source_ok and restored_binary_ok
            else "RESTORE_FAIL"
        )
        state["restore_build_returncode"] = restore_build_rc
        state["source_restored"] = restored_source_ok
        state["binary_restored_or_rebuilt"] = restored_binary_ok
        state["executable_sha_after_restore"] = (
            sha256_file(exe) if exe.is_file() else None
        )
        _write_json(run_root / "probe_state.json", state)
        summary["instrumented_build_returncode"] = instrument_build_rc
        summary["restore_build_returncode"] = restore_build_rc
        summary["source_restored"] = restored_source_ok
        summary["binary_restored_or_rebuilt"] = restored_binary_ok
        _write_json(run_root / "probe_summary.json", summary)
        print(
            "PF3_TRANSPORT_RESTORE:",
            "PASS" if restored_source_ok and restored_binary_ok else "FAIL",
        )

    analysis = summary.get("analysis")
    if not isinstance(analysis, dict):
        print(f"PF3_TRANSPORT_SUMMARY: {run_root / 'probe_summary.json'}")
        return 2
    print("PF3_TRANSPORT_ANALYSIS_STATUS:", analysis.get("analysis_status"))
    print("PF3_TRANSPORT_OUTCOME:", analysis.get("outcome"))
    print("PF3_TRANSPORT_CONFIDENCE:", analysis.get("confidence"))
    print("PF3_TRANSPORT_REASON:", analysis.get("reason"))
    fraction_jac = analysis.get("evaluate_fraction_of_jacobian")
    fraction_wall = analysis.get("evaluate_fraction_of_wall")
    print(
        "PF3_TRANSPORT_EVALUATE_JACOBIAN_FRACTION:",
        f"{fraction_jac:.4f}" if isinstance(fraction_jac, float) else fraction_jac,
    )
    print(
        "PF3_TRANSPORT_EVALUATE_WALL_FRACTION:",
        f"{fraction_wall:.4f}" if isinstance(fraction_wall, float) else fraction_wall,
    )
    print(
        "PF3_TRANSPORT_COLLISION_SECONDS:", analysis.get("collision_pair_seconds")
    )
    print("PF3_TRANSPORT_DMIX_SECONDS:", analysis.get("dmix_seconds"))
    print(
        "PF3_TRANSPORT_EVALUATE_SELF_SECONDS:", analysis.get("evaluate_self_seconds")
    )
    print(
        "PF3_TRANSPORT_FUNCTOR_CALLS:",
        json.dumps(analysis.get("functor_call_counts", {}), sort_keys=True),
    )
    print(
        "PF3_TRANSPORT_PROFILE_RATIO:",
        analysis.get("instrumented_to_baseline_profile_ratio"),
    )
    print(f"PF3_TRANSPORT_SUMMARY: {run_root / 'probe_summary.json'}")
    ok = (
        analysis.get("analysis_status") == "PASS"
        and restored_source_ok
        and restored_binary_ok
    )
    return 0 if ok else 2


def self_test() -> int:
    """Characterize runtime-only helpers without executing QPX or a build."""
    try:
        baseline = {
            "identity": {"input_sha256": "abc"},
            "problem": {"dofs": 10},
            "work": {
                "nonlinear_iterations": 2,
                "linear_iterations": 3,
                "residual_evaluations": 4,
            },
        }
        if not all(_parity_checks(baseline, json.loads(json.dumps(baseline))).values()):
            raise AssertionError("equal probe parity did not pass")
        mutated = json.loads(json.dumps(baseline))
        mutated["work"]["linear_iterations"] = 5
        checks = _parity_checks(baseline, mutated)
        if checks["same_linear_iterations"] or not all(
            ok for name, ok in checks.items() if name != "same_linear_iterations"
        ):
            raise AssertionError("parity mutation was not isolated")

        if sha256_bytes(b"abc") != hashlib.sha256(b"abc").hexdigest():
            raise AssertionError("byte hashing drift")
    except Exception as exc:
        print(f"QPX_TRANSPORT_PROBE_RUNTIME_SELFTEST: FAIL: {exc}")
        return 1
    print("QPX_TRANSPORT_PROBE_RUNTIME_SELFTEST: PASS")
    return 0

