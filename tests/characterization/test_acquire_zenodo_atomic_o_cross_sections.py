"""Synthetic-only test of Zenodo O collision source selector. No external data here."""
import importlib.util
from pathlib import Path
import sys

import pytest

FILE = (
    Path(__file__).resolve().parents[2] /
    "experiments/Issue395_powered_chemistry_ladder/acquire_zenodo_atomic_o_cross_sections.py"
)
spec = importlib.util.spec_from_file_location("oxygen_zenodo_atomic_candidate", FILE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def synthetic() -> str:
    blocks = []
    for key, (cat, product, process, threshold) in m.EXPECTED.items():
        blocks.append(
            "\n" + cat + "\n" + product + "\n"
            + f"  {threshold:.5e}\n"
            + "SPECIES: e / O\n"
            + "PROCESS: " + process + "\n"
            + f"PARAM.: Eth={threshold} eV\n"
            + "COMMENT: SYNTHETIC TEST ONLY\n"
            + "UPDATED: 2026-10-30\n"
            + "COLUMNS:  Energy (eV) | Cross Section (m2)\n"
            + "-------------------------------\n"
            + f"{threshold} 0.0\n"
            + f"{threshold + 0.1} 1.0e-22\n"
            + f"{threshold + 0.2} 2.0e-22\n"
            + "-------------------------------\n"
        )
    return "".join(blocks)


def test_four_processes_selected_and_no_extra_chemistry():
    out = m.select(synthetic())
    assert set(out) == {"KIN-EL-O", "EI-935", "EI-936", "EI-941"}
    assert all(v["num_points"] == 3 for v in out.values())
    assert out["EI-935"]["threshold_eV"] == 1.967
    assert out["EI-936"]["threshold_eV"] == 4.19
    assert out["EI-941"]["threshold_eV"] == 13.6
    assert "KIN-EL-O2" not in out
    assert "KIN-R01" not in out
    assert "attachment_three_body" not in out


def test_missing_or_changed_process_fails_closed():
    changed = synthetic().replace(
        "E + O -> E + O*((2p4)1D), Electronic",
        "E + O -> E + O*(WRONG), Electronic",
    )
    with pytest.raises(ValueError, match="EI-935"):
        m.select(changed)


def test_bad_threshold_and_duplicate_fail_closed():
    src = synthetic().replace("PARAM.: Eth=4.19 eV", "PARAM.: Eth=4.20 eV")
    with pytest.raises(ValueError, match="EI-936"):
        m.select(src)
    out = synthetic()
    # Extra duplicate exact block must be rejected.
    duplicate = out[out.index("\nEXCITATION\nO -> O*((2p4)1D)"):]
    with pytest.raises(ValueError, match="duplicate"):
        m.select(out + duplicate)


def test_nonmonotonic_and_negative_sigma_fail_closed():
    src = synthetic().replace("1.967 0.0\n2.067 1.0e-22", "1.967 0.0\n1.967 1.0e-22")
    with pytest.raises(ValueError, match="nonincreasing energy"):
        m.select(src)
    src = synthetic().replace("0.1 1.0e-22", "0.1 -1.0e-22")
    with pytest.raises(ValueError, match="negative"):
        m.select(src)


def test_download_security_pinning_and_zero_bundled_cross_sections():
    assert m.EXPECTED_MD5 == "c0c1073f5ea940568ce4925b8b242e1a"
    assert m.URL.startswith("https://zenodo.org/records/8192503/files/")
    assert m.DOI.endswith("8192503")
    assert len(m.EXPECTED) == 4
    assert "solver_ready" in FILE.read_text(encoding="utf-8")
