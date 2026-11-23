"""Public-safe build identity and case receipt contracts; never upload raw rates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from physics_harness.workflow.validator import WorkflowValidationError


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _elf_files(directory: Path) -> list[dict[str, str]]:
    """Only permit ELF binary closure, never input decks, rate tables or logs."""
    if not directory.is_dir() or directory.is_symlink():
        raise WorkflowValidationError("BUILD_BUNDLE_MISSING")
    records = []
    root = directory.resolve()
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise WorkflowValidationError("BUILD_BUNDLE_SYMLINK")
        if not path.is_file() or path.name == "shared-build-manifest.json":
            continue
        if not path.resolve().is_relative_to(root):
            raise WorkflowValidationError("BUILD_BUNDLE_PATH_ESCAPE")
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                raise WorkflowValidationError("BUILD_BUNDLE_NON_ELF_FILE")
        records.append({"path": path.relative_to(directory).as_posix(), "sha256": sha256(path)})
    if not records:
        raise WorkflowValidationError("BUILD_BUNDLE_EMPTY")
    return records


def record_build(directory: Path, spec) -> dict:
    root = Path(directory)
    manifest_path = root / "shared-build-manifest.json"
    if manifest_path.exists():
        raise WorkflowValidationError("BUILD_BUNDLE_ALREADY_MANIFESTED")
    manifest = {
        "schema_version": 1, "source_sha": spec.source_sha,
        "oci_ref": spec.oci_ref, "files": _elf_files(root),
        "science_status": "HOLD",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def verify_build(directory: Path, spec) -> str:
    root = Path(directory)
    manifest_path = root / "shared-build-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        raise WorkflowValidationError("BUILD_MANIFEST_MISSING") from exc
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or manifest.get("source_sha") != spec.source_sha
            or manifest.get("oci_ref") != spec.oci_ref
            or manifest.get("science_status") != "HOLD"):
        raise WorkflowValidationError("BUILD_IDENTITY_MISMATCH")
    if manifest.get("files") != _elf_files(root):
        raise WorkflowValidationError("BUILD_PAYLOAD_HASH_MISMATCH")
    return sha256(manifest_path)


def record_case(path: Path, *, spec, case_id: str, exit_code: int,
                build_manifest_sha256: str) -> dict:
    receipt = {
        "schema_version": 1,
        "case_id": case_id,
        "source_sha": spec.source_sha,
        "oci_ref": spec.oci_ref,
        "build_manifest_sha256": build_manifest_sha256,
        "execution_status": "EXIT_ZERO_UNVERIFIED" if exit_code == 0 else "FAIL",
        "exit_code": exit_code,
        "end_time_s_contract": spec.end_time_s,
        "intervals_contract": spec.intervals,
        "solver_time_coverage_verified": False,
        "scientific_status": "HOLD",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt
