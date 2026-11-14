#!/usr/bin/env python3
"""Bounded native P3 discriminator for the JSON+Physics electron equations.

Two isolated one-shot lanes use identical source and synthetic coefficients:
zero-flux (JSON boundaries absent) and existing JSON electron sheath BCs.
This is real native time integration, NOT an S6 scientific parity claim.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "physics_app/ci"
DATA_NAME = "dd_plasma_boundary_json_p2.json"
DECK_NAME = "dd_plasma_boundary_json_p3_smoke.i"
FIELDS = ("avg_log_e", "avg_log_e_energy", "avg_e_energy_eV")
DT = 1e-10
STEPS = 2


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def execute(cmd: list[str], cwd: Path, log: Path, seconds: int) -> int:
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as out:
        out.write("command: " + " ".join(cmd) + "\n")
        out.flush()
        try:
            proc = subprocess.run(cmd, cwd=cwd, stdout=out,
                                  stderr=subprocess.STDOUT, text=True,
                                  timeout=seconds, check=False)
            status = proc.returncode
        except subprocess.TimeoutExpired:
            status = 124
            out.write("\nP3_SOLVER_TIMEOUT\n")
        out.write(f"\nexit_code={status} elapsed_s={time.monotonic()-start:.3f}\n")
    return status


def inspect_csv(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("P3_CSV_MISSING")
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    if len(rows) < 2:
        raise ValueError("P3_NO_REAL_TIMESTEPS")
    if not {"time", *FIELDS}.issubset(set(rows[0])):
        raise ValueError("P3_MISSING_ELECTRON_OR_ENERGY_POSTPROCESSORS")
    samples = []
    for row in rows:
        values = {name: float(row[name]) for name in ("time", *FIELDS)}
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("P3_NONFINITE_TIME_OR_ELECTRON_STATE")
        if values["avg_e_energy_eV"] <= 0:
            raise ValueError("P3_NONPOSITIVE_MEAN_ELECTRON_ENERGY")
        samples.append(values)
    if abs(samples[-1]["time"] - DT * STEPS) > DT * 1e-5:
        raise ValueError("P3_INCOMPLETE_TRANSIENT_TIME_WINDOW")
    return {
        "samples": len(samples),
        "first": samples[0],
        "last": samples[-1],
        "delta": {key: samples[-1][key] - samples[0][key] for key in FIELDS},
    }


def lane(binary: Path, root: Path, name: str, json_data: dict, deck: str) -> dict:
    work = root / name
    work.mkdir(parents=True, exist_ok=False)
    (work / DATA_NAME).write_text(json.dumps(json_data, sort_keys=True, indent=2) + "\n")
    (work / "input.i").write_text(deck)
    receipt = {
        "lane": name,
        "input_sha256": digest(work / "input.i"),
        "json_sha256": digest(work / DATA_NAME),
        "status": "UNRESOLVED",
        "p2": "NOT_RUN",
        "p3": "NOT_RUN",
    }
    try:
        check = execute([str(binary), "--check-input", "-i", "input.i"],
                        work, work / "check_input.log", 120)
        check_text = (work / "check_input.log").read_text(errors="replace")
        if check or "Syntax OK" not in check_text:
            raise ValueError("P3_NATIVE_INPUT_PRECHECK_FAILED")
        receipt["p2"] = "PASS"
        exit_code = execute([str(binary), "-i", "input.i"],
                            work, work / "native_p3.log", 180)
        receipt["solver_exit"] = exit_code
        if exit_code:
            raise ValueError("P3_NATIVE_TRANSIENT_SOLVER_NONZERO")
        if not (work / "plasma.e").is_file() or (work / "plasma.e").stat().st_size <= 100:
            raise ValueError("P3_EXODUS_MISSING")
        receipt["observables"] = inspect_csv(work / "plasma.csv")
        receipt["exodus_sha256"] = digest(work / "plasma.e")
        receipt["csv_sha256"] = digest(work / "plasma.csv")
        receipt["p3"] = "EXECUTED"
        receipt["status"] = "P3_NATIVE_INTEGRATION_PASS"
    except Exception as exc:
        receipt["status"] = "P3_UNRESOLVED_OR_FAIL"
        receipt["blocker"] = str(exc)[:180]
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(name + ": " + receipt["status"] +
          (" " + receipt["blocker"] if "blocker" in receipt else ""), flush=True)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file() or not binary.stat().st_size:
        parser.error("P3_NATIVE_BINARY_MISSING")
    output = args.output.resolve()
    if output.exists():
        parser.error("Refusing to overwrite a previous native P3 evidence directory")
    output.mkdir(parents=True)
    deck = (CI / DECK_NAME).read_text()
    data = json.loads((CI / DATA_NAME).read_text())
    if (not data["species"]["e"]["energy_transport_coef"] == "fluid" or
        data["species"]["e"]["transport_coef"] != "constant" or
        not data["boundaries"]["left"]["bcs"] or
        not data["boundaries"]["bottom"]["bcs"]):
        parser.error("P3_SYNTHETIC_JSON_OR_SHEATH_CONTRACT_MISSING")
    if any(s in deck for s in ("solve = false", "kernel_coverage_check = false",
                               "fem_species = 'e 1e15'")):
        parser.error("P3_DECK_RETAINS_CONSTRUCTION_ONLY_OR_RETIRED_INPUT")
    no_wall = json.loads(json.dumps(data))
    no_wall.pop("boundaries")
    all_receipts = {
        "schema": "issue402_json_dd_p3_smoke_v1",
        "source_sha": args.source_sha,
        "binary_sha256": digest(binary),
        "deck_sha256": digest(CI / DECK_NAME),
        "json_sha256": digest(CI / DATA_NAME),
        "time_step_s": DT,
        "num_steps": STEPS,
        "science_acceptance": "HOLD",
        "s6_full_parity": "NOT_EVALUATED",
        "lanes": {},
    }
    for label, json_input in (("no_wall_control", no_wall),
                              ("json_sheath_wall", data)):
        all_receipts["lanes"][label] = lane(binary, output, label, json_input, deck)
        (output / "status.json").write_text(
            json.dumps(all_receipts, indent=2, sort_keys=True) + "\n"
        )
    control = all_receipts["lanes"]["no_wall_control"]
    wall = all_receipts["lanes"]["json_sheath_wall"]
    if control["p3"] == wall["p3"] == "EXECUTED":
        c = control["observables"]["delta"]
        w = wall["observables"]["delta"]
        all_receipts["zero_wall_control"] = (
            abs(c["avg_log_e"]) < 1e-5 and
            abs(c["avg_log_e_energy"]) < 1e-5
        )
        all_receipts["sheath_loss_discriminator"] = (
            w["avg_log_e"] < -1e-10 and
            w["avg_log_e_energy"] < -1e-10
        )
        all_receipts["status"] = (
            "P3_BOUNDED_SMOKE_PASS" if all_receipts["zero_wall_control"]
            and all_receipts["sheath_loss_discriminator"]
            else "P3_OBSERVABLE_DISCRIMINATOR_FAILED"
        )
    else:
        all_receipts["status"] = "P3_NATIVE_SOLVE_UNRESOLVED"
    (output / "status.json").write_text(
        json.dumps(all_receipts, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "source_sha": args.source_sha,
        "status": all_receipts["status"],
        "science_acceptance": "HOLD",
        "lanes": {k: v["status"] for k, v in all_receipts["lanes"].items()},
    }, sort_keys=True), flush=True)
    return 0 if all_receipts["status"] == "P3_BOUNDED_SMOKE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
