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


def create_collision_safe_directory(parent: Path, stem: str) -> Path:
    """Create a uniquely suffixed direct-child directory under ``parent``.

    The caller owns the semantic stem, including any timestamp. This primitive
    owns only collision-safe filesystem allocation: ``stem``, then ``stem_01``,
    ``stem_02``, and so on.
    """

    parent = Path(parent)
    raw_stem = str(stem)
    stem_path = Path(raw_stem)
    if not raw_stem or raw_stem in {".", ".."} or stem_path.name != raw_stem:
        raise ValueError(f"directory stem must be a direct-child name: {raw_stem!r}")

    parent.mkdir(parents=True, exist_ok=True)
    index = 0
    while True:
        name = raw_stem if index == 0 else f"{raw_stem}_{index:02d}"
        candidate = parent / name
        try:
            candidate.mkdir()
        except FileExistsError:
            index += 1
            continue
        return candidate


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def identity_record(*, executable: Path, input_path: Path) -> dict[str, str]:
    return {
        "qpx_realpath": str(executable.resolve()),
        "input_realpath": str(input_path.resolve()),
        "input_sha256": sha256_file(input_path),
    }


__all__ = [
    "create_collision_safe_directory",
    "ensure_fresh_directory",
    "identity_record",
    "sha256_file",
    "utc_timestamp",
]
