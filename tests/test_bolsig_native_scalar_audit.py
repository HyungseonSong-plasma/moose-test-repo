"""Native BOLSIG+ run-by-run reference self-consistency, without raw data fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from physics_app.ci.bolsig_native_scalar_audit import (
    NativeBolsigError,
    parse_native_scalar_reference,
)


def _native(tmp_path: Path) -> tuple[Path, Path]:
    rows = [
        ("Electric field / N (Td)", 10.0),
        ("Gas temperature (K)", 300.0),
        ("Gas particle density (1/m3)", 1e18),
        ("Growth model", 1.0),
        ("# of grid points", 200.0),
        ("Maximum energy", 15.83),
        ("Mole fraction Ar", 0.7),
        ("Mole fraction He", 0.2),
        ("Mole fraction N2", 0.08),
        ("Mole fraction O2", 0.02),
        ("Mean energy (eV)", 1.3),
        ("Mobility *N (1/m/V/s)", 4e24),
        ("Diffusion coefficient *N (1/m/s)", 5e24),
        ("Energy mobility *N (1/m/V/s)", 6e24),
        ("Energy diffusion coef. *N (1/m/s)", 6.1e24),
        ("Total ionization freq. /N (m3/s)", 4e-22),
        ("Total attachment freq. /N (m3/s)", 2e-39),
        ("Townsend ioniz. coef. alpha/N (m2)", 1e-26),
        ("Townsend attach. coef. eta/N (m2)", 5e-44),
        ("Power /N (eV m3/s)", 4e-16),
        ("Elastic power loss /N (eV m3/s)", 1e-17),
        ("Inelastic power loss /N (eV m3/s)", 3.9e-16),
        ("Growth power /N (eV m3/s)", 0.0),
    ]
    output = tmp_path / "example4.dat"
    lines = [
        "BOLSIG+ version: 07/2024", "Original synthetic fixture, not LXCat",
        "R1  ", "------------------------------------------------------------",
    ]
    lines += [f"{label:<46}{value:.8E}" for label, value in rows]
    lines += [
        "Rate coefficients (m3/s)",
        "C1    Ar    Effective (momentum)          1.0E-14",
        "C2    He    Elastic                       3.0E-14",
        "C3    N2    Excitation    0.20 eV        2.0E-15",
        "C4    O2    Ionization    12.06 eV       2.0E-20",
        "C5    O2    Attachment                    1.0E-37",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script = tmp_path / "input-examples.dat"
    script.write_text(
        "CONDITIONS\n10\nRUN\nSAVERESULTS\nexample4.dat\n"
        "1\n1\n1\n1\n0\n0\n0\n0\n1\nEND\n",
        encoding="utf-8",
    )
    return output, script


def test_native_rate_and_transport_internal_identities(tmp_path: Path) -> None:
    native, script = _native(tmp_path)
    result = parse_native_scalar_reference(native, script)
    assert result["status"] == "NATIVE_REFERENCE_SCALAR_SELFCONSISTENCY_PASS"
    assert result["scientific_acceptance"].startswith("HOLD_")
    assert result["number_of_collision_processes"] == 5
    assert result["process_census"]["O2"] == {"Ionization": 1, "Attachment": 1}
    assert result["conditions"]["mixture"] == {
        "Ar": 0.7, "He": 0.2, "N2": 0.08, "O2": 0.02
    }
    assert not result["eepf_in_native_result"]
    assert result["input_save_options"]["cross_sections"] == 1
    assert all(v < 1e-12 for v in result["identity_relative_errors"].values())


def test_inconsistent_bolsig_rates_are_not_silent_science_pass(tmp_path: Path) -> None:
    native, script = _native(tmp_path)
    text = native.read_text(encoding="utf-8")
    native.write_text(text.replace(
        "Total ionization freq. /N (m3/s)", "Total ionization freq. /N (m3/s)"
    ).replace("4.00000000E-22", "8.00000000E-22"), encoding="utf-8")
    result = parse_native_scalar_reference(native, script)
    assert result["status"] == "NATIVE_REFERENCE_SCALAR_SELFCONSISTENCY_FAIL"
    assert result["identity_relative_errors"]["ionization_weighted_rate_relative"] > 0.4


def test_corrupted_native_data_or_missing_input_controls_rejected(tmp_path: Path) -> None:
    native, script = _native(tmp_path)
    data = native.read_text()
    native.write_text(data.replace("BOLSIG+ version:", "not BOLSIG version:"))
    with pytest.raises(NativeBolsigError, match="not a native"):
        parse_native_scalar_reference(native, script)
    native.write_text(data)
    native.write_text(data.replace(
        "C5    O2    Attachment", "C4    O2    Attachment"))
    with pytest.raises(NativeBolsigError, match="duplicate"):
        parse_native_scalar_reference(native, script)
    native.write_text(data)
    script.write_text("SAVERESULTS\nunrelated.dat\n1\n1\n1\n1\n0\n0\n0\n0\n1\nEND\n")
    with pytest.raises(NativeBolsigError, match="not found"):
        parse_native_scalar_reference(native, script)
