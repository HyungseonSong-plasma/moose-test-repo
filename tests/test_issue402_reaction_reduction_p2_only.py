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
    assert "type = EIRateCoefMaterial" in fixtures[0][1].read_text()
    assert "type = EIRateCoefMaterial" in fixtures[3][1].read_text()
    for old in ("ElectronImpactRateMaterial", "PhysicsElectronImpactRateMaterial"):
        assert f"type = {old}" not in fixtures[0][1].read_text()
        assert f"type = {old}" not in fixtures[3][1].read_text()
    assert "property_name = R_O2s" in fixtures[1][1].read_text()
    assert "property_name = R_O2s" in fixtures[2][1].read_text()


def test_p2_only_never_invokes_solver(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "physics-opt"
    executable.write_text("fake")
    calls = []

    def fake_run(command, **kwargs):
        assert kwargs["cwd"].is_dir()  # Check while TemporaryDirectory is alive.
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="Syntax OK", stderr="")

    monkeypatch.setattr(p2.subprocess, "run", fake_run)
    p2.check_native_p2(executable)
    assert len(calls) == 4
    for command, kwargs in calls:
        assert command == [str(executable), "--check-input", "-i", command[-1]]
        assert kwargs["timeout"] == 300


def test_missing_syntax_ok_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "physics-opt"
    executable.write_text("fake")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="parse incomplete", stderr="")

    monkeypatch.setattr(p2.subprocess, "run", fake_run)
    with pytest.raises(AssertionError, match="Native P2 failed"):
        p2.check_native_p2(executable)


def test_retired_mean_energy_mode_absent_from_current_fixture_owners() -> None:
    """The test's conserved FV states are not the Material's log-molar inputs."""
    import math
    import re
    from physics_app.ci import check_stage5_h05_runtime as h05
    from physics_app.ci import check_stage5_edetach_runtime as edetach
    from physics_app.ci import check_stage5_ei18_runtime as ei18
    from physics_app.ci import check_stage5_ei20_runtime as ei20
    from physics_app.ci import check_standard_moose_energy_projection as standard

    root = Path(__file__).resolve().parents[1] / "physics_app" / "ci"
    cases = {
        "H05": h05.runtime_input(),
        "R2": p2.r2.RUNTIME_INPUT,
        "R3": p2.r3.RUNTIME_INPUT,
        "EI10": p2.e10.RUNTIME_INPUT,
        "EI16": p2.e16.RUNTIME_INPUT,
        "EDETACH": edetach.text(),
        "EI18": ei18._runtime_input(),
        "EI20": ei20.runtime_input(),
        "EI10_STANDARD": standard.EI10_INPUT,
        "EI16_STANDARD": standard.EI16_INPUT,
    }
    for filename in (
        "electron_energy_transport_smoke.i",
        "electron_energy_lookup_response_smoke.i",
        "electron_energy_real_qvt_inventory_smoke.i",
    ):
        cases[filename] = (root / filename).read_text()
    assert len(cases) == 13
    for name, source in cases.items():
        assert "physical_eV" not in source, name
        assert re.search(r"^\s*\[n_e\]\s*$", source, re.M), name
        assert re.search(r"^\s*\[mean_en\]\s*$", source, re.M), name
        mean = re.search(
            r"^\s*type\s*=\s*ElectronEnergyMaterial\s*\n"
            r"\s*electron_energy_density\s*=\s*(\w+)\s*\n"
            r"\s*electron_density\s*=\s*(\w+)\s*\n"
            r"\s*state_form\s*=\s*log_molar_eV\s*$", source, re.M,
        )
        assert mean, name
        for property_name, raw_state, symbol in (
            (mean.group(1), "mean_en", "energy"),
            (mean.group(2), "n_e", "ne"),
        ):
            projection = re.search(
                r"^\s*type\s*=\s*ADParsedFunctorMaterial\s*\n"
                rf"\s*property_name\s*=\s*{property_name}\s*\n"
                rf"\s*functor_names\s*=\s*'{raw_state}'\s*\n"
                rf"\s*functor_symbols\s*=\s*'{symbol}'\s*\n"
                rf"\s*expression\s*=\s*'log\({symbol}/6\.02214076e23\)'\s*$",
                source, re.M,
            )
            assert projection, (name, property_name)
    for density, energy in ((1.0e16, 5.73276e16), (2.0e19, 8.0e19)):
        projected_mean = math.exp(math.log(energy / 6.02214076e23)
                                  - math.log(density / 6.02214076e23))
        assert math.isclose(projected_mean, energy / density, rel_tol=1e-13)
