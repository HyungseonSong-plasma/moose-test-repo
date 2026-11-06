"""Regression: C0 construction must not import unrelated scientific analysis packages."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_oxygen_c0_help_without_site_packages():
    # -S disables site packages entirely. This can run before polars/pyarrow/
    # duckdb or their transitive scientific dependencies are installed.
    result = subprocess.run(
        [sys.executable, "-S", str(ROOT / "bin" / "physics.py"), "oxygen-c0", "--help"],
        cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "--base-input" in result.stdout
    assert "--rf-parent" in result.stdout


def test_physics_cli_help_does_not_load_analysis_engine():
    result = subprocess.run(
        [sys.executable, "-S", str(ROOT / "bin" / "physics.py"), "--help"],
        cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "oxygen-c0" in result.stdout
