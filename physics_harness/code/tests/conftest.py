"""Hermetic Git fixtures for diagnostics acceptance tests."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def git_factory(tmp_path):
    counter = 0

    def create(files: dict[str, str | bytes]):
        nonlocal counter
        counter += 1
        root = tmp_path / f"repo_{counter}"
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.email", "harness@example.invalid")
        git(root, "config", "user.name", "Harness Tests")
        for relative, value in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                value if isinstance(value, bytes) else value.encode("utf-8")
            )
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "test fixture")
        return root, git(root, "rev-parse", "HEAD")

    return create
