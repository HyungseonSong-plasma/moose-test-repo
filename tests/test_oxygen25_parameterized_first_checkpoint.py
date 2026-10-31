"""Regression tests for the immutable-source initial Oxygen25 checkpoint adapter."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tarfile

import pytest

from physics_harness.adapters.moose.initial_checkpoint import (
    CHEM, INPUT_PARTS, SOURCE_SHA, FirstCheckpoint, stage_input, verify_input,
    verify_and_archive,
)

PREPARED = ("[Executioner]\n  type = Transient\n  end_time = 2e-9\n"
            "  [TimeStepper]\n    type = TimeSequenceStepper\n"
            "    time_sequence = '0 1e-9 2e-9'\n  []\n[]\n"
            "[Outputs]\n  csv = true\n  exodus = true\n[]\n")


@pytest.mark.parametrize("power", [400, 1000])
@pytest.mark.parametrize("end,interval", [(1, "1"), (2, "1"), (5, "0.5")])
def test_first_run_input_staging_is_idempotent(power, end, interval):
    spec = FirstCheckpoint(power, end, interval)
    staged = stage_input(PREPARED, spec)
    verify_input(staged, spec)
    assert stage_input(staged, spec) == staged
    assert staged.count("checkpoint = true") == 1


@pytest.mark.parametrize("interval", ["0", "-1", "nan", "inf", "0.00001"])
def test_reject_unsafe_interval(interval):
    with pytest.raises(ValueError):
        FirstCheckpoint(400, 1, interval)


def test_reject_unreviewed_science_source_or_recovery():
    with pytest.raises(ValueError):
        FirstCheckpoint(400, 1, "1", "0" * 40)
    with pytest.raises(ValueError):
        stage_input(PREPARED + "[Problem]\n restart_file_base = x\n[]\n",
                    FirstCheckpoint(400, 1, "1"))
    with pytest.raises(ValueError):
        stage_input(PREPARED.replace("TimeSequenceStepper", "ConstantDT"),
                    FirstCheckpoint(400, 1, "1"))


def synthetic_native_evidence(tmp_path: Path, *, missing_checkpoint=False):
    spec = FirstCheckpoint(400, 1, "1")
    chem = tmp_path / CHEM
    result = tmp_path / spec.result
    run = result / "run"
    run.mkdir(parents=True)
    for template in INPUT_PARTS:
        name = template.format(p=400)
        target = chem / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(stage_input(PREPARED, spec) if name == spec.input.name
                          else "SAFE_INPUT\n")
    with (run / "plasma.csv").open("w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["time", "n_O_ex_avg", "n_O_3P_avg",
                         "chem24_monitor_R_936"])
        writer.writerow(["0", "1", "2", "3"])
        writer.writerow(["1e-9", "1.1", "2.2", "3.3"])
    (run / "plasma.e").write_bytes(b"native exodus fixture")
    (result / "runtime.log").write_text("Time Step 1, time = 1e-09, dt = 1e-09\n")
    (result / "check_input.log").write_text("Input file syntax OK\n")
    hashes = {str(i): "a"*64 for i in range(19)}
    (chem / "chem24_manifest.json").write_text(json.dumps({
        "active": 25, "atoms_charge_mass": "PASS",
        "ei936_rate_mode": "analytic_maxwellian_fallback",
        "lookup_sha256": hashes,
    }))
    if not missing_checkpoint:
        state = run / "plasma_cp/0001-restart-0.rd"
        state.mkdir(parents=True)
        (state / "data").write_bytes(b"genuine state fixture")
        (state / "header").write_bytes(b"genuine header fixture")
        mesh = run / "plasma_cp/0001-mesh.cpa.gz/1"
        mesh.mkdir(parents=True)
        (mesh / "header.gz").write_bytes(b"genuine mesh header fixture")
    return spec


def test_complete_native_archive_and_manifest_roundtrip(tmp_path):
    spec = synthetic_native_evidence(tmp_path)
    manifest = verify_and_archive(tmp_path, spec)
    assert manifest["actual_moose_step"] == 1
    assert manifest["checkpoint_prefix"].endswith("/plasma_cp/0001")
    assert manifest["power_w"] == 400
    assert manifest["scientific_acceptance"] == "HOLD"
    assert len(manifest["input_files"]) == 12
    assert manifest["chemistry"] == "25-effective-O(ex)-EI936"
    for filename, expected in manifest["archives"].items():
        path = tmp_path / spec.result / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]
        with tarfile.open(path) as bundle:
            names = [m.name for m in bundle.getmembers()]
        assert not any("private_rates" in name for name in names)
    assert (tmp_path / spec.result / "restart_1ns_manifest.json").is_file()


def test_missing_native_checkpoint_is_not_csv_success(tmp_path):
    spec = synthetic_native_evidence(tmp_path, missing_checkpoint=True)
    with pytest.raises(ValueError, match="native full-state checkpoint"):
        verify_and_archive(tmp_path, spec)


def test_wrong_end_time_is_not_a_checkpoint_success(tmp_path):
    spec = synthetic_native_evidence(tmp_path)
    log = tmp_path / spec.result / "runtime.log"
    log.write_text("Time Step 1, time = 5e-10, dt = 5e-10\n")
    with pytest.raises(ValueError, match="solver final time"):
        verify_and_archive(tmp_path, spec)


def test_private_rate_path_is_not_archived(tmp_path):
    spec = synthetic_native_evidence(tmp_path)
    private = tmp_path / spec.result / "run/private_rates"
    private.mkdir()
    (private / "secret.txt").write_text("restricted")
    with pytest.raises(ValueError, match="protected rates"):
        verify_and_archive(tmp_path, spec)
