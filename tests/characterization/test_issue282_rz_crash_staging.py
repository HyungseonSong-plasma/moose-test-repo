"""Offline fail-closed staging regression for Issue282 2D RZ crash discriminator.

No QPX/MOOSE execution or science acceptance; check exact generated input,
reversible registration-only projection and idempotence guard.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from experiments.Issue282_e2a_rz_bridge.diagnose_segv import CASES, make_case


@pytest.mark.parametrize("name", CASES)
def test_staging_creates_own_unique_directory(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    assert not path.exists()
    evidence = make_case(path, name)
    assert path.is_dir()
    assert (path / "input.i").is_file()
    assert (path / "input.historical.i").is_file()
    assert (path / "qvt.msh").is_file()
    assert evidence["historical_sha256"] != evidence["projected_sha256"]
    assert evidence["not_scientific_parity"] is True
    runtime_text = (path / "input.i").read_text(encoding="utf-8")
    assert "enable_jit = false" in runtime_text
    assert "exodus = true" in runtime_text
    assert "type = QPX" not in runtime_text
    with pytest.raises(Exception, match="already exists"):
        make_case(path, name)
