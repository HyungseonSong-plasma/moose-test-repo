#!/usr/bin/env python3
"""Fail-closed proof for a completed two-step DD sheath native P3 result.

Self-tests use SYNTHETIC files and never invoke a solver. A real PASS requires
source-bound binary/input, actual saved logs, receipt and full two-step CSV.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

DT = 1e-10
STEPS = 2
LANE = "json_sheath_wall"
FIELDS = ("avg_log_e", "avg_log_e_energy", "avg_e_energy_eV")
DATA_NAME = "dd_plasma_boundary_json_p2.json"
DECK_NAME = "dd_plasma_boundary_json_p3_smoke.i"
PINNED_OCI_REF = ("ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:"
                  "2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")


def require(ok: bool, marker: str) -> None:
    if not ok:
        raise ValueError(marker)


def digest(path: Path) -> str:
    require(path.is_file() and path.stat().st_size > 0, "P3_EVIDENCE_FILE_MISSING")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify(evidence: Path, source: str, binary: Path, repository: Path,
           oci_ref: str = PINNED_OCI_REF) -> dict:
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None, "P3_SOURCE_SHA_FORMAT")
    receipt = read_json(evidence / "status.json")
    lane_dir = evidence / LANE
    lane = read_json(lane_dir / "receipt.json")
    require(set(receipt["lanes"]) == {LANE} and receipt["lanes"][LANE] == lane,
            "P3_LANE_RECEIPT_MISMATCH")
    require(receipt["schema"] == "issue402_json_dd_p3_sheath_only_v2", "P3_SCHEMA")
    require(receipt["source_sha"] == source, "P3_SOURCE_SHA_MISMATCH")
    require(oci_ref == PINNED_OCI_REF and receipt.get("oci_ref") == oci_ref,
            "P3_SOURCE_BOUND_OCI_MISMATCH")
    require(receipt["num_steps"] == STEPS and receipt["time_step_s"] == DT,
            "P3_TIMESTEP_CONTRACT")
    require(receipt["science_acceptance"] == "HOLD" and
            receipt["s6_full_parity"] == "NOT_EVALUATED" and
            receipt["rf_heating_active"] is False, "P3_SCIENCE_STATUS")
    require(receipt["status"] == "P3_BOUNDED_SHEATH_SMOKE_PASS" and
            receipt["time_evolution_observed"] is True, "P3_UNPROVEN_SOLVE")
    require(receipt.get("continuity_evolution_observed") is True and
            receipt.get("energy_evolution_observed") is True,
            "P3_BOTH_EQUATIONS_NOT_PROVEN")
    require(lane["status"] == "P3_NATIVE_INTEGRATION_PASS" and
            lane["p2"] == "PASS" and lane["p3"] == "EXECUTED" and
            lane["solver_exit"] == 0, "P3_NATIVE_STATUS")
    require(receipt["binary_sha256"] == digest(binary), "P3_BINARY_PROVENANCE")
    require(receipt["deck_sha256"] == digest(repository / "physics_app/ci" / DECK_NAME),
            "P3_DECK_PROVENANCE")
    require(receipt["json_sha256"] == digest(repository / "physics_app/ci" / DATA_NAME),
            "P3_JSON_PROVENANCE")
    require(lane["input_sha256"] == digest(lane_dir / "input.i") and
            lane["json_sha256"] == digest(lane_dir / DATA_NAME), "P3_ACTUAL_INPUT_HASH")
    require(lane["exodus_sha256"] == digest(lane_dir / "plasma.e") and
            lane["csv_sha256"] == digest(lane_dir / "plasma.csv"), "P3_OUTPUT_HASH")
    require((lane_dir / "plasma.e").stat().st_size > 100, "P3_EXODUS_TRUNCATED")
    check_log = (lane_dir / "check_input.log").read_text(errors="replace")
    solver_log = (lane_dir / "native_p3.log").read_text(errors="replace")
    require("Syntax OK" in check_log and re.search(r"\bexit_code=0\b", check_log),
            "P3_REAL_NATIVE_P2_LOG")
    require(re.search(r"\bexit_code=0\b", solver_log), "P3_REAL_NATIVE_P3_LOG")
    with (lane_dir / "plasma.csv").open(newline="", encoding="utf-8") as inp:
        reader = csv.DictReader(inp)
        require(reader.fieldnames is not None and
                {"time", *FIELDS}.issubset(reader.fieldnames), "P3_CSV_FIELDS")
        rows = list(reader)
    # INITIAL + both consecutive completed timesteps: not just the final time.
    require(len(rows) == STEPS + 1, "P3_MISSING_OR_EXTRA_TIMESTEP")
    samples = []
    for i, row in enumerate(rows):
        values = {name: float(row[name]) for name in ("time", *FIELDS)}
        require(all(math.isfinite(v) for v in values.values()), "P3_NONFINITE_CSV")
        require(values["avg_e_energy_eV"] > 0, "P3_INVALID_MEAN_ENERGY")
        require(abs(values["time"] - i * DT) <= DT * 1e-5,
                "P3_INCOMPLETE_OR_DUPLICATE_TIMESTEP_GRID")
        samples.append(values)
    observed = lane["observables"]
    require(observed["samples"] == STEPS + 1, "P3_RECEIPT_TIMESTEP_COUNT")
    for name in ("time", *FIELDS):
        for side, index in (("first", 0), ("last", -1)):
            require(math.isclose(observed[side][name], samples[index][name],
                                 rel_tol=1e-12, abs_tol=1e-14),
                    "P3_RECEIPT_CSV_DISAGREES")
    # Both independent electron continuity and energy state must evolve;
    # a continuity-only (or energy-only) two-step trace is not a coupled P3.
    require(abs(samples[-1]["avg_log_e"] - samples[0]["avg_log_e"]) > 1e-12,
            "P3_NO_CONTINUITY_EVOLUTION")
    require(abs(samples[-1]["avg_log_e_energy"] -
                samples[0]["avg_log_e_energy"]) > 1e-12,
            "P3_NO_ENERGY_EVOLUTION")
    return {"schema": "issue541.arch.dd_p3_result_gate.v1",
            "source_sha": source,
            "oci_ref": oci_ref,
            "binary_sha256": digest(binary),
            "continuity_evolution_observed": True,
            "energy_evolution_observed": True,
            "status": "DD_TWO_STEP_SOURCE_BOUND_NATIVE_P3_EVIDENCE_PASS",
            "samples": len(samples),
            "time_window_s": [samples[0]["time"], samples[-1]["time"]],
            "original_scope": "bounded sheath P3 only; S6 and science NOT evaluated",
            "science": "SCIENCE_HOLD",
            "csv_sha256": lane["csv_sha256"],
            "exodus_sha256": lane["exodus_sha256"]}


def synthetic(root: Path):
    source = "a" * 40
    repository, evidence = root / "source", root / "output"
    ci = repository / "physics_app/ci"
    ci.mkdir(parents=True)
    (ci / DECK_NAME).write_text("num_steps = 2\n")
    (ci / DATA_NAME).write_text('{"species":{"e":{"initial_number_density":1e15}}}\n')
    binary = root / "physics-opt"
    binary.write_bytes(b"SYNTHETIC-NOT-NATIVE")
    d = evidence / LANE
    d.mkdir(parents=True)
    (d / "input.i").write_text((ci / DECK_NAME).read_text())
    (d / DATA_NAME).write_text((ci / DATA_NAME).read_text())
    (d / "plasma.e").write_bytes(b"SYNTHETIC"*25)
    (d / "check_input.log").write_text("Syntax OK\nexit_code=0 elapsed_s=0.0\n")
    (d / "native_p3.log").write_text("SYNTHETIC ONLY\nexit_code=0 elapsed_s=0.0\n")
    samples = [{"time": i * DT, "avg_log_e": 1+i*.1,
                "avg_log_e_energy": 2+i*.1, "avg_e_energy_eV": 3+i*.1}
               for i in range(3)]
    write_csv(d / "plasma.csv", samples)
    lane = {"status": "P3_NATIVE_INTEGRATION_PASS", "p2": "PASS",
            "p3": "EXECUTED", "solver_exit": 0,
            "input_sha256": digest(d / "input.i"),
            "json_sha256": digest(d / DATA_NAME),
            "exodus_sha256": digest(d / "plasma.e"),
            "csv_sha256": digest(d / "plasma.csv"),
            "observables": {"samples": 3, "first": samples[0], "last": samples[-1]}}
    (d / "receipt.json").write_text(json.dumps(lane))
    receipt = {"schema": "issue402_json_dd_p3_sheath_only_v2",
               "source_sha": source, "num_steps": 2, "time_step_s": DT,
               "oci_ref": PINNED_OCI_REF,
               "science_acceptance": "HOLD", "s6_full_parity": "NOT_EVALUATED",
               "rf_heating_active": False,
               "status": "P3_BOUNDED_SHEATH_SMOKE_PASS",
               "time_evolution_observed": True,
               "continuity_evolution_observed": True,
               "energy_evolution_observed": True,
               "binary_sha256": digest(binary),
               "deck_sha256": digest(ci / DECK_NAME),
               "json_sha256": digest(ci / DATA_NAME),
               "lanes": {LANE: lane}}
    (evidence / "status.json").write_text(json.dumps(receipt))
    return evidence, source, binary, repository, samples


def write_csv(path: Path, samples: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["time", *FIELDS])
        writer.writeheader()
        writer.writerows(samples)


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        evidence, source, binary, repository, samples = synthetic(root)
        require(verify(evidence, source, binary, repository)["samples"] == 3,
                "SYNTHETIC_POSITIVE_CONTROL")
    mutations = (
        ("missing_midpoint", lambda ev, s: write_csv(ev/LANE/"plasma.csv",
                                                    [s[0], s[2]])),
        ("duplicate_midpoint", lambda ev, s: write_csv(ev/LANE/"plasma.csv",
                                                      [s[0], s[0], s[2]])),
        ("tampered_output", lambda ev, s: (ev/LANE/"plasma.e").write_bytes(b"X"*125)),
        ("nonfinite_energy", lambda ev, s: write_csv(ev/LANE/"plasma.csv",
                                                    [s[0], s[1], dict(s[2], avg_e_energy_eV=float("nan"))])),
        ("missing_native_log", lambda ev, s: (ev/LANE/"native_p3.log").unlink()),
        ("unproven_lane", lambda ev, s: (ev/LANE/"receipt.json").write_text(
            (ev/LANE/"receipt.json").read_text().replace('"EXECUTED"', '"NOT_RUN"'))),
        ("fake_science", lambda ev, s: (ev/"status.json").write_text(
            (ev/"status.json").read_text().replace('"HOLD"', '"ACCEPTED"'))),
        ("forged_source", lambda ev, s: (ev/"status.json").write_text(
            (ev/"status.json").read_text().replace("a"*40, "0"*40))),
        ("frozen_continuity", lambda ev, s: write_csv(ev/LANE/"plasma.csv",
            [dict(row, avg_log_e=s[0]["avg_log_e"]) for row in s])),
        ("frozen_energy", lambda ev, s: write_csv(ev/LANE/"plasma.csv",
            [dict(row, avg_log_e_energy=s[0]["avg_log_e_energy"]) for row in s])),
        ("forged_oci", lambda ev, s: (ev/"status.json").write_text(
            (ev/"status.json").read_text().replace(PINNED_OCI_REF,
                                                        "ghcr.io/unsafe@sha256:" + "0"*64))),
        ("forged_energy_flag", lambda ev, s: (ev/"status.json").write_text(
            (ev/"status.json").read_text().replace(
                '"energy_evolution_observed": true',
                '"energy_evolution_observed": false'))),
    )
    for label, mutation in mutations:
        with tempfile.TemporaryDirectory() as temp:
            evidence, source, binary, repository, samples = synthetic(Path(temp))
            mutation(evidence, samples)
            if label in {"missing_midpoint", "duplicate_midpoint", "nonfinite_energy",
                         "frozen_continuity", "frozen_energy"}:
                # Rehash to prevent digest failure from masking the numerical assertion.
                lane_file = evidence / LANE / "receipt.json"
                lane_data = read_json(lane_file)
                lane_data["csv_sha256"] = digest(evidence / LANE / "plasma.csv")
                if label in {"frozen_continuity", "frozen_energy"}:
                    with (evidence / LANE / "plasma.csv").open(
                            newline="", encoding="utf-8") as src:
                        changed = list(csv.DictReader(src))
                    for side, idx in (("first", 0), ("last", -1)):
                        lane_data["observables"][side] = {
                            key: float(changed[idx][key]) for key in ("time", *FIELDS)
                        }
                lane_file.write_text(json.dumps(lane_data))
                report_file = evidence / "status.json"
                report_data = read_json(report_file)
                report_data["lanes"][LANE] = lane_data
                report_file.write_text(json.dumps(report_data))
            try:
                verify(evidence, source, binary, repository)
            except (ValueError, KeyError, FileNotFoundError) as exc:
                expected = {
                    "missing_midpoint": "P3_MISSING_OR_EXTRA_TIMESTEP",
                    "duplicate_midpoint": "P3_INCOMPLETE_OR_DUPLICATE_TIMESTEP_GRID",
                    "nonfinite_energy": "P3_NONFINITE_CSV",
                    "frozen_continuity": "P3_NO_CONTINUITY_EVOLUTION",
                    "frozen_energy": "P3_NO_ENERGY_EVOLUTION",
                }.get(label)
                if expected is not None:
                    require(str(exc) == expected, "WRONG_MUTATION_IDENTITY_" + label)
                continue
            raise AssertionError("UNREJECTED_SYNTHETIC_MUTATION: " + label)
    print("ISSUE541_ARCH_DD_P3_RESULT_NEGATIVE_MUTATIONS_12_REJECTED_SYNTHETIC_ONLY")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--evidence", type=Path)
    p.add_argument("--source-sha")
    p.add_argument("--binary", type=Path)
    p.add_argument("--repository", type=Path)
    p.add_argument("--oci-ref")
    args = p.parse_args()
    if args.self_test:
        self_test()
        if args.evidence is None:
            return 0
    if not all((args.evidence, args.source_sha, args.binary, args.repository, args.oci_ref)):
        p.error("--evidence, --source-sha, --binary, --repository and --oci-ref are required")
    try:
        report = verify(args.evidence.resolve(), args.source_sha,
                        args.binary.resolve(), args.repository.resolve(),
                        args.oci_ref)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print("ISSUE541_ARCH_DD_NATIVE_P3_EVIDENCE_NOT_PROVEN:", exc)
        return 1
    (args.evidence / "issue541_arch_verified_result.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(report["status"], "SCIENCE_HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
