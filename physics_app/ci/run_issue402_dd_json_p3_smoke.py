#!/usr/bin/env python3
"""Bounded real native transient smoke for JSON sheath electron equations.

Only JSON sheath boundary conditions are exercised. No no-wall control:
without boundary loss, sustained RF electron heating would not be a relevant
comparison. This fixture does NOT supply RF; it is sheath/numerical wiring
qualification, NOT an S6 or powered-plasma scientific parity claim.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "physics_app/ci"
DATA_NAME = "dd_plasma_boundary_json_p2.json"
DECK_NAME = "dd_plasma_boundary_json_p3_smoke.i"
FIELDS = ("avg_log_e", "avg_log_e_energy", "avg_e_energy_eV")
DT = 1e-10
STEPS = 2
PINNED_OCI_REF = ("ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:"
                  "2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")


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
    if len(rows) != STEPS + 1:
        raise ValueError("P3_MISSING_OR_EXTRA_TIMESTEP")
    if not {"time", *FIELDS}.issubset(set(rows[0])):
        raise ValueError("P3_MISSING_ELECTRON_OR_ENERGY_POSTPROCESSORS")
    samples = []
    for step, row in enumerate(rows):
        values = {name: float(row[name]) for name in ("time", *FIELDS)}
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("P3_NONFINITE_TIME_OR_ELECTRON_STATE")
        if values["avg_e_energy_eV"] <= 0:
            raise ValueError("P3_NONPOSITIVE_MEAN_ELECTRON_ENERGY")
        if abs(values["time"] - step * DT) > DT * 1e-5:
            raise ValueError("P3_INCOMPLETE_OR_DUPLICATE_TIMESTEP_GRID")
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
        "native_p3_attempted": False,
    }
    try:
        check = execute([str(binary), "--check-input", "-i", "input.i"],
                        work, work / "check_input.log", 120)
        check_text = (work / "check_input.log").read_text(errors="replace")
        if check or "Syntax OK" not in check_text:
            raise ValueError("P3_NATIVE_INPUT_PRECHECK_FAILED")
        receipt["p2"] = "PASS"
        receipt["native_p3_attempted"] = True
        receipt["p3"] = "ATTEMPTED_UNVERIFIED"
        exit_code = execute([str(binary), "-i", "input.i"],
                            work, work / "native_p3.log", 180)
        receipt["solver_exit"] = exit_code
        receipt["native_log_sha256"] = digest(work / "native_p3.log")
        if exit_code:
            receipt["p3"] = "ATTEMPTED_FAILED"
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
        # The original P3 archive omitted the inner Native log. Future failed
        # attempts must report a bounded diagnostic and retain the full log
        # in the existing visible, always-upload evidence directory.
        native_log = work / "native_p3.log"
        if native_log.is_file():
            receipt["native_log_sha256"] = digest(native_log)
            receipt["native_failure_tail"] = native_log.read_text(
                encoding="utf-8", errors="replace")[-2048:]
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(name + ": " + receipt["status"] +
          (" " + receipt["blocker"] if "blocker" in receipt else ""), flush=True)
    return receipt


def self_test() -> None:
    """Mock-only failure classifications; no Physics app or P3 solve."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        binary = root / "fake-physics-opt"
        binary.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "if '--check-input' in sys.argv:\n"
            "    print('Syntax OK: synthetic P2 only')\n"
            "    sys.exit(0)\n"
            "print('SYNTHETIC_FAILURE_42: no real P3 was run')\n"
            "sys.exit(42)\n")
        binary.chmod(0o755)
        result = lane(binary, root / "failure", "json_sheath_wall",
                      {"synthetic": True}, "[Mesh]\n[]\n")
        assert result["status"] == "P3_UNRESOLVED_OR_FAIL"
        assert result["p2"] == "PASS"
        assert result["native_p3_attempted"] is True
        assert result["p3"] == "ATTEMPTED_FAILED"
        assert result["solver_exit"] == 42
        assert result["blocker"] == "P3_NATIVE_TRANSIENT_SOLVER_NONZERO"
        assert "SYNTHETIC_FAILURE_42" in result["native_failure_tail"]
        native = root / "failure" / "json_sheath_wall" / "native_p3.log"
        assert native.is_file() and digest(native) == result["native_log_sha256"]

        precheck = root / "fake-precheck-rejection"
        precheck.write_text(
            "#!/usr/bin/env python3\n"
            "print('SYNTHETIC_P2_REJECTION')\n"
            "raise SystemExit(23)\n")
        precheck.chmod(0o755)
        no_p3 = lane(precheck, root / "precheck", "json_sheath_wall",
                     {"synthetic": True}, "[Mesh]\n[]\n")
        assert no_p3["status"] == "P3_UNRESOLVED_OR_FAIL"
        assert no_p3["p2"] == "NOT_RUN" and no_p3["p3"] == "NOT_RUN"
        assert no_p3["native_p3_attempted"] is False
        assert no_p3["blocker"] == "P3_NATIVE_INPUT_PRECHECK_FAILED"
        assert not (root / "precheck" / "json_sheath_wall" / "native_p3.log").exists()
    # Independent two-step time-grid checks: no actual Native P3 is run here.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "synthetic.csv"
        samples = [
            {"time": i * DT, "avg_log_e": 1.0 + .1 * i,
             "avg_log_e_energy": 2.0 + .1 * i,
             "avg_e_energy_eV": 3.0 + .1 * i}
            for i in range(STEPS + 1)
        ]
        def write_rows(rows):
            with target.open("w", newline="", encoding="utf-8") as out:
                w = csv.DictWriter(out, fieldnames=["time", *FIELDS])
                w.writeheader()
                w.writerows(rows)
        write_rows(samples)
        assert inspect_csv(target)["samples"] == STEPS + 1
        for label, rows, expected in (
            ("missing_midpoint", [samples[0], samples[2]],
             "P3_MISSING_OR_EXTRA_TIMESTEP"),
            ("duplicate_midpoint", [samples[0], samples[0], samples[2]],
             "P3_INCOMPLETE_OR_DUPLICATE_TIMESTEP_GRID"),
            ("out_of_order", [samples[0], samples[2], samples[1]],
             "P3_INCOMPLETE_OR_DUPLICATE_TIMESTEP_GRID"),
        ):
            write_rows(rows)
            try:
                inspect_csv(target)
            except ValueError as exc:
                assert str(exc) == expected, (label, str(exc))
            else:
                raise AssertionError("P3_TIMESTEP_NEGATIVE_UNREJECTED:" + label)
    print("ISSUE541_DD_P3_TIMESTEP_NEGATIVE_3_PASS_NO_NATIVE")
    print("ISSUE541_DD_P3_FAILURE_DIAGNOSTIC_NEGATIVE_2_PASS_NO_NATIVE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--oci-ref", help="OCI digest actually selected by the DD P3 job")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not (args.binary and args.output and args.source_sha and args.oci_ref):
        parser.error("--binary, --output, --source-sha and --oci-ref are required for real P3")
    if re.fullmatch(r"[0-9a-f]{40}", args.source_sha) is None:
        parser.error("P3_EXACT_SOURCE_SHA_FORMAT")
    if args.oci_ref != PINNED_OCI_REF:
        parser.error("P3_PINNED_OCI_PROVENANCE_MISMATCH")
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
    all_receipts = {
        "schema": "issue402_json_dd_p3_sheath_only_v2",
        "source_sha": args.source_sha,
        "binary_sha256": digest(binary),
        "oci_ref": args.oci_ref,
        "deck_sha256": digest(CI / DECK_NAME),
        "json_sha256": digest(CI / DATA_NAME),
        "time_step_s": DT,
        "num_steps": STEPS,
        "science_acceptance": "HOLD",
        "s6_full_parity": "NOT_EVALUATED",
        "rf_heating_active": False,
        "scope": "only JSON sheath electron particle and energy transport",
        "lanes": {},
    }
    wall = lane(binary, output, "json_sheath_wall", data, deck)
    all_receipts["lanes"]["json_sheath_wall"] = wall
    if wall["p3"] == "EXECUTED":
        changes = wall["observables"]["delta"]
        all_receipts["continuity_evolution_observed"] = (
            abs(changes["avg_log_e"]) > 1e-12
        )
        all_receipts["energy_evolution_observed"] = (
            abs(changes["avg_log_e_energy"]) > 1e-12
        )
        # These are two independent P3 obligations. Either one alone is not
        # enough to claim a coupled continuity+energy transient passed.
        all_receipts["time_evolution_observed"] = (
            all_receipts["continuity_evolution_observed"] and
            all_receipts["energy_evolution_observed"]
        )
        all_receipts["status"] = (
            "P3_BOUNDED_SHEATH_SMOKE_PASS"
            if all_receipts["time_evolution_observed"]
            else "P3_NO_ELECTRON_STATE_EVOLUTION"
        )
    else:
        all_receipts["status"] = "P3_NATIVE_SHEATH_SOLVE_UNRESOLVED"
    (output / "status.json").write_text(
        json.dumps(all_receipts, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "source_sha": args.source_sha,
        "status": all_receipts["status"],
        "science_acceptance": "HOLD",
        "lanes": {k: v["status"] for k, v in all_receipts["lanes"].items()},
    }, sort_keys=True), flush=True)
    return 0 if all_receipts["status"] == "P3_BOUNDED_SHEATH_SMOKE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
