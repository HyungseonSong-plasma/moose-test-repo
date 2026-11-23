"""Approved source-bound Python execution adapter for generated case workflows.

No arbitrary shell command, no scientific acceptance, and no protected files
in published artifacts. Workload-specific scripts must provide native P1/P2
and scientific checks; this generic layer proves only controlled invocation.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from physics_harness.workflow.artifacts import record_build, record_case, verify_build
from physics_harness.workflow.validator import WorkflowValidationError, validate_executor_files


def source_identity(root: Path, spec) -> None:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True,
            timeout=15, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkflowValidationError("SOURCE_REVISION_UNVERIFIED") from exc
    if head != spec.source_sha:
        raise WorkflowValidationError("SOURCE_REVISION_MISMATCH")


def _invoke(script: Path, args: list[str], *, root: Path, timeout: int, log: Path) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    # Logs may contain protected transport table paths: never print or upload.
    with log.open("wb") as stream:
        try:
            return subprocess.run(
                [sys.executable, str(script), *args], cwd=root,
                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            return 124
        except OSError:
            return 127


def execute_build(spec, *, root: Path, output_dir: Path) -> int:
    root = root.resolve()
    source_identity(root, spec)
    validate_executor_files(spec, root)
    if output_dir.exists():
        raise WorkflowValidationError("BUILD_OUTPUT_ALREADY_EXISTS")
    output_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="physics-build-log-",
                                     dir=os.environ.get("RUNNER_TEMP")) as private:
        code = _invoke(root / spec.build_script, [
            "--output-dir", str(output_dir),
            "--source-sha", spec.source_sha,
            "--oci-ref", spec.oci_ref,
        ], root=root, timeout=min(spec.timeout_minutes * 60, 7200),
            log=Path(private) / "native-build.log")
    if code != 0:
        return 2
    record_build(output_dir, spec)
    return 0


def execute_case(spec, *, root: Path, case_id: str, build_dir: Path,
                 receipt: Path) -> int:
    root = root.resolve()
    source_identity(root, spec)
    validate_executor_files(spec, root)
    if case_id not in {case.id for case in spec.cases}:
        raise WorkflowValidationError("CASE_NOT_IN_APPROVED_PLAN")
    if receipt.exists():
        raise WorkflowValidationError("CASE_RECEIPT_ALREADY_EXISTS")
    build_sha = verify_build(build_dir, spec)
    with tempfile.TemporaryDirectory(prefix="physics-case-" + case_id + "-",
                                     dir=os.environ.get("RUNNER_TEMP")) as private:
        folder = Path(private)
        code = _invoke(root / spec.case_script, [
            "--case", case_id, "--build-dir", str(build_dir),
            "--workspace", str(folder / "workspace"),
            "--source-sha", spec.source_sha,
            "--oci-ref", spec.oci_ref,
        ], root=root, timeout=spec.timeout_minutes * 60,
            log=folder / "private-run.log")
    record_case(receipt, spec=spec, case_id=case_id, exit_code=code,
                build_manifest_sha256=build_sha)
    return 0 if code == 0 else 2
