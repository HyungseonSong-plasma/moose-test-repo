"""Source-bound 461-frame checks and negative controls for full100 CI."""
from pathlib import Path
import csv
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import issue652_g6b_full100_case as full
import issue652_g6b_full100_aggregate as aggregate
from issue652_g6_runtime_gate import REQUIRED_CSV
from issue652_g6b_parallel_evidence import ParallelEvidenceHold

SOURCE_SHA = "a" * 40
MANIFEST_SHA = "b" * 64
BINARY_SHA = "c" * 64


def c0():
    increments = ([1e-9] * 100 + [1e-8] * 190
                  + [1e-7] * 80 + [1e-6] * 90)
    times = [0.]
    for dt in increments:
        times.append(times[-1] + dt)
    assert len(times) == 461 and abs(times[-1] - 1e-4) < 1e-15
    sequence = " ".join(format(x, ".17g") for x in times)
    return (f"[Executioner]\n  scheme = implicit-euler\n"
            f"  end_time = 1e-4\n    type = TimeSequenceStepper\n"
            f"    time_sequence = '{sequence}'\n"
            f"[Outputs]\n  checkpoint = true\n").encode(), times


def full_csv(path: Path, times: list[float]):
    fields = ["time", *REQUIRED_CSV]
    with path.open("w", newline="") as sink:
        writer = csv.DictWriter(sink, fieldnames=fields)
        writer.writeheader()
        for t in times:
            values = dict.fromkeys(REQUIRED_CSV, 1.0)
            values.update({"time": t, "potential_min": -1., "potential_max": 1.,
                           "ne_min": 2., "ne_max": 3.})
            writer.writerow(values)


def test_full100_461_rows_and_100us_cadence(tmp_path: Path):
    deck, times = c0()
    path = tmp_path / "plasma.csv"
    full_csv(path, times)
    result = full.verify_full_csv(path, deck)
    assert result["time_points"] == 461
    assert result["intervals"] == 460
    assert result["t_end_seconds"] == 1e-4
    assert result["charge_conservation_budget"] == "NOT_EVALUATED"


def test_full100_rejects_missing_final_and_time_drift(tmp_path: Path):
    deck, times = c0()
    path = tmp_path / "plasma.csv"
    full_csv(path, times[:-1])
    with pytest.raises(full.Full100Hold, match="461"):
        full.verify_full_csv(path, deck)
    drifted = list(times)
    drifted[225] += 2e-8
    full_csv(path, drifted)
    with pytest.raises(full.Full100Hold, match="GRID"):
        full.verify_full_csv(path, deck)


def test_full100_rejects_nonfinite_postprocessor(tmp_path: Path):
    deck, times = c0()
    path = tmp_path / "plasma.csv"
    full_csv(path, times)
    text = path.read_text()
    path.write_text(text.replace("-1.0", "nan", 1))
    with pytest.raises(full.Full100Hold, match="NONFINITE"):
        full.verify_full_csv(path, deck)


def test_exodus_header_only_not_science_pass(tmp_path: Path):
    exodus = tmp_path / "plasma.e"
    exodus.write_bytes(b"CDF\x02" + b"\x00" * 8192)
    report = full.verify_exodus(exodus)
    assert report["nodal_field_parity"] == "NOT_EVALUATED"
    exodus.write_bytes(b"PROTECTED_RATE" + b"\x00" * 8192)
    with pytest.raises(full.Full100Hold, match="NETCDF"):
        full.verify_exodus(exodus)


def valid_receipt(case: str):
    return {
        "schema": "issue652.g6b.native_100us_case.v1",
        "source_sha": SOURCE_SHA, "case_id": case,
        "build_manifest_sha256": MANIFEST_SHA,
        "binary_sha256": BINARY_SHA,
        "original_publicd_lookup_sha256": full.d100.PUBLIC_D_100_SHA256,
        "P1": "PASS", "P2": "PASS_TYPED_15_OWNERS",
        "P3_100us": "PASS_NATIVE_FINITE_461_FRAMES",
        "P4": "NOT_RUN", "science": "SCIENCE_HOLD",
        "conservation": "UNVERIFIED",
        "raw_protected_rates_in_artifact": False,
        "native_solver_log_in_artifact": False,
        "native_input_deck_in_artifact": False,
        "original_s6_input_unchanged": True,
        "public_outputs_ready": True,
        "original_time_grid": {
            "time_points": 461, "intervals": 460,
            "end_time_seconds": 1e-4,
            "scheme": "implicit-euler", "checkpoint": True,
        },
        "time_series": {
            "status": "PASS_NATIVE_FINITE_EXACT_461_TIME_POINTS",
            "time_points": 461, "intervals": 460,
            "t0_seconds": 0., "t_end_seconds": 1e-4,
            "charge_conservation_budget": "NOT_EVALUATED",
            "semantic_parity": "NOT_EVALUATED",
        },
        "solver": {"status": "EXIT_ZERO", "exit_code": 0},
        "native_csv": {"sha256": "d" * 64, "bytes": 12345},
        "native_exodus": {
            "sha256": "e" * 64, "bytes": 123456,
            "format_header_verified": True,
            "nodal_field_parity": "NOT_EVALUATED",
        },
    }


def test_aggregate_full100_fail_closed_for_incomplete_or_wrong_case():
    for case in ("417", "941"):
        rec = valid_receipt(case)
        assert aggregate.validate_case(rec, case, SOURCE_SHA,
                                       MANIFEST_SHA, BINARY_SHA)["frame_count"] == 461
        rec["time_series"]["time_points"] = 460
        with pytest.raises(ParallelEvidenceHold, match="NOT_PROVEN"):
            aggregate.validate_case(rec, case, SOURCE_SHA,
                                    MANIFEST_SHA, BINARY_SHA)
    with pytest.raises(ParallelEvidenceHold, match="NOT_PROVEN"):
        aggregate.validate_case(valid_receipt("417"), "941",
                                SOURCE_SHA, MANIFEST_SHA, BINARY_SHA)


def test_no_implicit_full100_execution(monkeypatch, tmp_path: Path):
    with pytest.raises(full.Full100Hold, match="AUTHORIZATION"):
        full.run(case="417", staged=tmp_path, p0=tmp_path / "p0",
                 registration=tmp_path / "reg", manifest=tmp_path / "m",
                 source_sha=SOURCE_SHA, output=tmp_path / "out",
                 export=tmp_path / "raw", timeout_seconds=60, authorize=False)


def test_full100_never_shortens_original_s6_input():
    source = (ROOT / "ci/guards/issue652_g6b_full100_case.py").read_text()
    assert "d100.time_contract(c0)" in source
    assert "three_ns_input(" not in source
    assert '"Outputs/file_base=issue652_outputs/plasma"' in source
    assert "secure_tmpfs_cleanup(private)" in source
    assert "read_hashed_rows()" in source
    assert "--authorize-full-100us" in source
    assert '"P4": "NOT_RUN"' in source
    assert '"science": "SCIENCE_HOLD"' in source
