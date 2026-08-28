"""Reusable evidence identity and output-directory utilities."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_fresh_directory(path: Path) -> Path:
    """Create an evidence directory or reject an existing non-empty one."""

    if path.exists() and any(path.iterdir()):
        raise SystemExit(f"refusing non-empty evidence directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def identity_record(*, executable: Path, input_path: Path) -> dict[str, str]:
    return {
        "qpx_realpath": str(executable.resolve()),
        "input_realpath": str(input_path.resolve()),
        "input_sha256": sha256_file(input_path),
    }
