"""P0 controls: EI10/EI16 Native validation is syntax-only, never a solve."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from physics_app.ci import check_issue402_reaction_reduction_p2_only as p2


def test_four_canonical_reaction_inputs_and_output_owners(tmp_path: Path) -> None:
    fixtures = p2._fixtures(tmp_path)
    assert [name for name, _ in fixtures] == [
        "R2_EI16", "R3_EI10", "E8_EI10", "E8_EI16"
    ]
    for name, path in fixtures:
        assert path.is_file(), name
        source = path.read_text()
        assert "PhysicsElectronImpactIonizationMaterial" not in source
        assert "PhysicsElectronImpactO2sExcitationMaterial" not in source
        assert "PhysicsO2IonizationSourceMaterial" not in source
        assert "PhysicsO2sExcitationSourceMaterial" not in source
        assert "ADParsedFunctorMaterial" in source
    assert "PhysicsElectronImpactRateMaterial" in fixtures[0][1].read_text()
    assert "PhysicsElectronImpactRateMaterial" in fixtures[3][1].read_text()
    assert "property_name = R_O2s" in fixtures[1][1].read_text()
    assert "property_name = R_O2s" in fixtures[2][1].read_text()


def test_p2_only_never_invokes_solver(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "physics-opt"
    executable.write_text("fake")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="Syntax OK", stderr="")

    monkeypatch.setattr(p2.subprocess, "run", fake_run)
    p2.check_native_p2(executable)
    assert len(calls) == 4
    for command, kwargs in calls:
        assert command == [str(executable), "--check-input", "-i", command[-1]]
        assert kwargs["cwd"].is_dir()
        assert kwargs["timeout"] == 300


def test_missing_syntax_ok_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "physics-opt"
    executable.write_text("fake")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="parse incomplete", stderr="")

    monkeypatch.setattr(p2.subprocess, "run", fake_run)
    with pytest.raises(AssertionError, match="Native P2 failed"):
        p2.check_native_p2(executable)
