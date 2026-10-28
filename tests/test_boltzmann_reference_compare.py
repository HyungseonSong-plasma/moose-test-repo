"""Synthetic independent BOLSIG+ comparison contract controls (not real parity)."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from physics_app.ci.boltzmann_reference_compare import (
    ReferenceContractError,
    compare_case,
)


def _write_bytes(root: Path, name: str, payload: bytes) -> str:
    (root / name).write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _write_json(root: Path, name: str, payload: dict) -> str:
    return _write_bytes(root, name, json.dumps(payload, sort_keys=True).encode())


def _fixture(root: Path) -> tuple[dict, dict, dict]:
    # Manufactured two-cell isotropic EEPF. It is not a BOLSIG+ run.
    raw_sha = _write_bytes(root, "input.txt", b"SYNTHETIC-DATA-NO-LXCAT\n")
    ref_raw_sha = _write_bytes(root, "raw-bolsig-output.txt",
                               b"SYNTHETIC GOLDEN ORACLE, NOT FROM BOLSIG+\n")
    state = {
        "reduced_field_Td": 10.0,
        "gas_temperature_K": 300.0,
        "mixture": {"Ar": 1.0},
        "model": "synthetic-analytical-regression-only",
        "collision_source_sha256": raw_sha,
    }
    e = [0.0, 1.0, 2.0]
    weights = [(2.0 / 3) * (b**1.5 - a**1.5) for a, b in zip(e, e[1:])]
    a = 1.0 / sum(weights)
    f = [a, a]
    mean = sum(v * (2 / 5) * (hi**2.5 - lo**2.5)
               for v, lo, hi in zip(f, e, e[1:]))
    reference = {
        "schema_version": 1,
        "conditions": state.copy(),
        "energy_cell_edges_eV": e,
        "eepf_eV_minus_3_halves": f,
        "mean_energy_eV": mean,
        "rates_m3_per_s": {"Ar:excitation:1": 1e-14, "Ar:inactive:2": 0.0},
    }
    candidate = json.loads(json.dumps(reference))
    ref_sha = _write_json(root, "reference.json", reference)
    cand_sha = _write_json(root, "candidate.json", candidate)
    case = {
        "schema_version": 1,
        "source": {
            "path": "input.txt",
            "sha256": raw_sha,
            "database": "AUTHOR-SYNTHETIC",
            "source_url": "https://example.invalid/independent-synthetic",
            "retrieved_utc": "2026-10-28T00:00:00Z",
            "process_ids": ["Ar:excitation:1", "Ar:inactive:2"],
            "rate_process_ids": ["Ar:excitation:1", "Ar:inactive:2"],
        },
        "reference": {
            "path": "reference.json",
            "sha256": ref_sha,
            "solver": "BOLSIG+",
            "version": "SYNTHETIC_TEST_NOT_BOLSIG",
            "raw_export_path": "raw-bolsig-output.txt",
            "raw_export_sha256": ref_raw_sha,
        },
        "candidate": {
            "path": "candidate.json",
            "sha256": cand_sha,
            "code_revision": "test-only-sha",
        },
        "tolerances": {
            "mean_energy_relative": 0.02,
            "eepf_weighted_l1": 0.05,
            "rate_relative": 0.1,
            "zero_rate_absolute_m3_per_s": 1e-25,
        },
    }
    _write_json(root, "case.json", case)
    return case, reference, candidate


def _candidate(root: Path, case: dict, state: dict) -> None:
    case["candidate"]["sha256"] = _write_json(root, "candidate.json", state)
    _write_json(root, "case.json", case)


def test_manufactured_reference_pass_and_controls(tmp_path: Path) -> None:
    case, reference, candidate = _fixture(tmp_path)
    passed = compare_case(tmp_path)
    assert passed["decision"] == "BOLSIG_REFERENCE_SELFTEST_PASS"
    assert passed["mean_energy_relative_error"] < 1e-14

    # Negative scientific discrimination: same provenance with a different
    # (still-normalized) EEPF and moment must fail quantitatively.
    e = candidate["energy_cell_edges_eV"]
    weights = [(2 / 3) * (b**1.5 - a**1.5) for a, b in zip(e, e[1:])]
    f0, f1 = reference["eepf_eV_minus_3_halves"]
    candidate["eepf_eV_minus_3_halves"] = [
        f0 * 1.2,
        f1 - 0.2 * f0 * weights[0] / weights[1],
    ]
    candidate["mean_energy_eV"] = sum(
        v * (2 / 5) * (hi**2.5 - lo**2.5)
        for v, lo, hi in zip(candidate["eepf_eV_minus_3_halves"], e, e[1:])
    )
    _candidate(tmp_path, case, candidate)
    decision = compare_case(tmp_path)
    assert decision["decision"] == "BOLSIG_REFERENCE_SELFTEST_FAIL"
    assert "eepf" in decision["failures"]

    # Rate mismatch independently fails even when the EEPF is identical.
    candidate = json.loads(json.dumps(reference))
    candidate["rates_m3_per_s"]["Ar:excitation:1"] = 1.3e-14
    _candidate(tmp_path, case, candidate)
    assert "rate:Ar:excitation:1" in compare_case(tmp_path)["failures"]

    candidate = json.loads(json.dumps(reference))
    candidate["rates_m3_per_s"]["Ar:inactive:2"] = 1e-22
    _candidate(tmp_path, case, candidate)
    assert "rate:Ar:inactive:2" in compare_case(tmp_path)["failures"]

    # Structural/preflight negative controls must be classified as HOLD, not
    # a passing or failing physical reference comparison.
    candidate = json.loads(json.dumps(reference))
    candidate["conditions"]["reduced_field_Td"] = 99.0
    _candidate(tmp_path, case, candidate)
    with pytest.raises(ReferenceContractError, match="physical state mismatch"):
        compare_case(tmp_path)

    candidate = json.loads(json.dumps(reference))
    candidate["eepf_eV_minus_3_halves"][0] *= 1.5
    _candidate(tmp_path, case, candidate)
    with pytest.raises(ReferenceContractError, match="normalization"):
        compare_case(tmp_path)

    candidate = json.loads(json.dumps(reference))
    candidate["rates_m3_per_s"].pop("Ar:inactive:2")
    _candidate(tmp_path, case, candidate)
    with pytest.raises(ReferenceContractError, match="inventories differ"):
        compare_case(tmp_path)

    candidate = json.loads(json.dumps(reference))
    _candidate(tmp_path, case, candidate)
    (tmp_path / "raw-bolsig-output.txt").write_bytes(b"CORRUPTED REFERENCE\n")
    with pytest.raises(ReferenceContractError, match="SHA256 mismatch"):
        compare_case(tmp_path)

    # Restore authentic bytes before testing the independent rate ledger.
    _write_bytes(tmp_path, "raw-bolsig-output.txt",
                 b"SYNTHETIC GOLDEN ORACLE, NOT FROM BOLSIG+\n")

    # An altered source-to-rate ledger cannot silently omit a reaction.
    case["source"]["rate_process_ids"] = ["Ar:excitation:1"]
    _write_json(tmp_path, "case.json", case)
    with pytest.raises(ReferenceContractError, match="numeric rate inventory"):
        compare_case(tmp_path)
    case["source"]["rate_process_ids"] = ["Ar:excitation:1", "Ar:inactive:2"]
    _write_json(tmp_path, "case.json", case)

    # Tampered raw collision source must also fail before any numeric decision.
    _write_bytes(tmp_path, "raw-bolsig-output.txt",
                 b"SYNTHETIC GOLDEN ORACLE, NOT FROM BOLSIG+\n")
    (tmp_path / "input.txt").write_text("ALTERED SOURCE\n")
    with pytest.raises(ReferenceContractError, match="SHA256 mismatch"):
        compare_case(tmp_path)
