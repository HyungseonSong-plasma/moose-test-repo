#!/usr/bin/env python3
"""Issue #652 G6: exact-source registered-owner trace and bounded 3 ns Native probe.

Never uses 100us or time-step/semantic equivalence as an implicit pass.
Original source, pinned historical archive and G5 staged public layers are
read-only. Protected EI tables exist only inside private /dev/shm scratch.
Public receipts contain no private EI table bytes or unredacted solver logs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue652_g5_native_p2 import (  # noqa: E402
    ROOT, C0, OCI, file_sha, secure_tmpfs_cleanup,
)

CASES = ("417", "941")
EXPECTED_OWNERS = {
    "Variable": {"potential": "MooseVariable"},
    "Kernel": {
        "Poisson_diffusion": "ADMatDiffusion",
        "Poisson_charge_source": "FunctorKernel",
    },
    "Material": {
        "Poisson_eps_plasma": "ADGenericConstantMaterial",
        "Poisson_eps_cover": "ADGenericConstantMaterial",
        "Poisson_eps_wafer": "ADGenericConstantMaterial",
        "Poisson_eps_focus_ring": "ADGenericConstantMaterial",
        "Poisson_eps_vacuum": "ADGenericConstantMaterial",
    },
    "BC": {
        "Poisson_grounded_potential": "DirichletBC",
        "Poisson_surface_charge_plasma_cover": "PhysicsADSurfaceChargePoissonBC",
        "Poisson_surface_charge_plasma_wafer": "PhysicsADSurfaceChargePoissonBC",
        "Poisson_surface_charge_plasma_focus_ring": "PhysicsADSurfaceChargePoissonBC",
    },
    "FunctorMaterial": {
        "plasma_charge_number_density": "ADParsedFunctorMaterial",
        "plasma_charge_density_C_m3": "ADParsedFunctorMaterial",
        "plasma_poisson_source": "ADParsedFunctorMaterial",
    },
}
REQUIRED_CSV = (
    "potential_min", "potential_max", "charge_integral",
    "charge_number_min", "charge_number_max",
    "cover_surface_charge_total", "wafer_surface_charge_total",
    "focus_ring_surface_charge_total", "ne_min", "ne_max",
)
G6_SOURCE_ENV = "G6_EXPECTED_SOURCE_SHA"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exact_source() -> str:
    expected = os.environ.get(G6_SOURCE_ENV, "")
    head = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected) or head != expected:
        raise ValueError("G6_EXACT_SOURCE_IDENTITY_MISMATCH")
    return expected


def registration_receipt(raw: bytes) -> dict:
    lines = raw.decode("utf-8").splitlines()
    if lines.count("G6_PRELOAD_READY") < 1:
        raise ValueError("G6_REGISTRATION_OBSERVER_NOT_LOADED")
    rows = []
    for line in lines:
        if line == "G6_PRELOAD_READY":
            continue
        fields = line.split("\t")
        if len(fields) != 4 or fields[0] != "G6_OWNER":
            raise ValueError("G6_REGISTRATION_TRACE_MALFORMED")
        rows.append((fields[1], fields[2], fields[3]))
    if len(rows) < 20:
        raise ValueError("G6_REGISTRATION_TRACE_TOO_FEW_REAL_OBJECTS")
    matches = {}
    for family, types in EXPECTED_OWNERS.items():
        for suffix, expected_type in types.items():
            matched = [item for item in rows
                       if item[0] == family
                       and (item[1] == suffix if family == "Variable"
                            or family == "FunctorMaterial"
                            else item[1].endswith(suffix))]
            if len(matched) != 1 or matched[0][2] != expected_type:
                raise ValueError("G6_EXPECTED_SINGLE_OWNER_MISSING_OR_WRONG_TYPE:" +
                                 family + ":" + suffix)
            matches[family + "/" + suffix] = {
                "name": matched[0][1], "type": matched[0][2],
            }
    if len(matches) != 15:
        raise ValueError("G6_EXPECTED_FIFTEEN_GENERATED_OWNERS_NOT_PROVEN")
    # "ADGenericConstantMaterial" is a Material, not a FunctorMaterial;
    # the three G3 charge names are the only expected new charge producers.
    for family, name, kind in rows:
        if (family in ("Kernel", "Material", "BC", "FunctorMaterial") and
                name in {"phi_diffusion", "phi_source", "eps_cover",
                         "grounded_potential", "charge_number_density",
                         "charge_density", "poisson_source"}):
            raise ValueError("G6_RETIRED_NATIVE_OBJECT_RE_REGISTERED:" + name)
    return {
        "status": "EXPECTED_15_GENERATED_OWNERS_TRACE_PASS",
        "rows_total": len(rows),
        "preload_marker_count": lines.count("G6_PRELOAD_READY"),
        "observer_sha256": sha(raw),
        "observed_expected_owners": matches,
        "global_consumer_closure": "UNPROVEN",
        "dynamic_functor_value": "NOT_TESTED_BY_REGISTRATION",
    }


def three_ns_input(original: bytes) -> tuple[bytes, dict]:
    """Only three exact source-line changes within disposable private C0."""
    if b"\r" in original:
        raise ValueError("G6_INPUT_CRLF_DRIFT")
    text = original.decode("utf-8")
    def patch(pattern, value):
        nonlocal text
        text, count = re.subn(pattern, value, text, flags=re.MULTILINE)
        if count != 1:
            raise ValueError("G6_EXPECTED_ONE_TRANSIENT_SETTING")
    patch(r"^  end_time = 1e-4$", "  end_time = 3e-9")
    patch(r"^    time_sequence = '[^\n]*'$",
          "    time_sequence = '0 1e-9 2e-9 3e-9'")
    patch(r"^  checkpoint = true$", "  checkpoint = false")
    result = text.encode()
    if result.count(b"[Executioner]") != 1 or result.count(b"[Outputs]") != 1:
        raise ValueError("G6_TRANSIENT_SECTION_COUNT_CHANGED")
    if len(result) >= len(original):
        raise ValueError("G6_SHORT_RUNTIME_INPUT_NOT_REDUCED")
    return result, {
        "input_g5_sha256": sha(original),
        "output_private_3ns_sha256": sha(result),
        "end_time_seconds": 3e-9,
        "time_sequence_seconds": [0.0, 1e-9, 2e-9, 3e-9],
        "checkpoint_disabled_only_in_private_scratch": True,
    }


def metrics_for_p3(case_work: Path) -> dict:
    found = []
    for p in case_work.rglob("*.csv"):
        if "private_rates" in p.parts or p.is_symlink() or p.stat().st_size > 80_000_000:
            continue
        with p.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(REQUIRED_CSV).issubset(reader.fieldnames):
                continue
            if "time" not in reader.fieldnames:
                continue
            data = []
            for row in reader:
                values = {key: float(row[key]) for key in ("time",) + REQUIRED_CSV}
                if not all(math.isfinite(v) for v in values.values()):
                    raise ValueError("G6_NONFINITE_P3_POSTPROCESSOR")
                data.append(values)
            if data:
                found.append((p, data))
    if len(found) != 1:
        raise ValueError("G6_EXPECTED_ONE_NUMERIC_CSV_WITH_CHARGE_AND_SIGMA")
    _, rows = found[0]
    times = [x["time"] for x in rows]
    if len(rows) < 4 or any(y <= x for x, y in zip(times, times[1:])) or abs(times[-1] - 3e-9) > 1e-12:
        raise ValueError("G6_THREE_NS_TIME_SEQUENCE_NOT_COMPLETED")
    extrema = {}
    for key in REQUIRED_CSV:
        extrema[key] = {
            "initial": rows[0][key], "final": rows[-1][key],
            "min_over_time": min(row[key] for row in rows),
            "max_over_time": max(row[key] for row in rows),
        }
    if any(row["ne_min"] <= 0 or row["ne_max"] <= 0 for row in rows):
        raise ValueError("G6_ELECTRON_DENSITY_NONPOSITIVE")
    if any(row["potential_min"] > row["potential_max"] for row in rows):
        raise ValueError("G6_POTENTIAL_EXTREMA_INVERTED")
    return {
        "status": "SHORT_3NS_POSTPROCESSORS_FINITE",
        "time_rows": len(rows), "initial_seconds": times[0],
        "final_seconds": times[-1], "metrics": extrema,
        "baseline_semantic_parity": "NOT_EVALUATED",
        "charge_conservation_residual": "NOT_MEASURED",
    }


def docker_cmd(folder: Path, ordered: list[str], *, observe: bool) -> list[str]:
    executable = "/workspace/physics_app/physics-opt"
    if observe:
        executable = ("G6_OWNER_TRACE=/case/g6_owners.tsv "
                      "LD_PRELOAD=/workspace/physics_app/g6_owner_tracer.so " +
                      executable + " --check-input")
    return [
        "docker", "run", "--rm", "--network", "none",
        "--entrypoint", "/bin/bash", "--user", "0:0", "--workdir", "/case",
        "--env", "OXYGEN_RESEARCH_400=1",
        "--env", "OXYGEN_RESEARCH_FULL24=0",
        "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
        "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
        "--mount", "type=bind,src=" + str(ROOT) + ",dst=/workspace,readonly",
        "--mount", "type=bind,src=" + str(folder) + ",dst=/case",
        OCI, "-lc",
        "set -euo pipefail; source /environment; " + executable + " -i " +
        " ".join(shlex.quote(s) for s in ordered),
    ]


def execute(command: list[str], timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False,
            env={key: value for key, value in os.environ.items()
                 if key != "PROTECTED_ARCHIVE_B64"},
        )
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "G6_EXECUTION_EXPLICIT_TIMEOUT"


def selected_cases(case: str | None) -> tuple[str, ...]:
    """One CI lane selects one case; absence preserves the historical dual-case mode."""
    if case is None:
        return CASES
    if case not in CASES:
        raise ValueError("G6_CASE_NOT_IN_APPROVED_ALLOWLIST")
    return (case,)


def run(staged: Path, output: Path, *, registration_only: bool,
        cases: tuple[str, ...] = CASES) -> dict:
    if (not isinstance(cases, tuple) or not cases
            or len(set(cases)) != len(cases)
            or any(case not in CASES for case in cases)):
        raise ValueError("G6_INVALID_SELECTED_CASES")
    source_sha = exact_source()
    source_receipt = json.loads((staged.parent / "g5-result/g5_stage_receipt.json").read_text()) if (
        staged.parent / "g5-result/g5_stage_receipt.json").is_file() else None
    if source_receipt is None:
        raise ValueError("G6_G5_EXACT_SOURCE_RECEIPT_REQUIRED")
    if source_receipt["source_sha"] != source_sha or set(source_receipt["cases"]) != set(CASES):
        raise ValueError("G6_G5_SOURCE_PIN_MISMATCH")
    binary = ROOT / "physics_app/physics-opt"
    tracer = ROOT / "physics_app/g6_owner_tracer.so"
    if not binary.is_file() or not tracer.is_file() or binary.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("G6_BINARY_OR_OBSERVER_MISSING")
    sys.path.insert(0, str(ROOT / "ci/guards"))
    from issue671_secure_ei_rate_scratch import (  # noqa: E402
        EXPECTED, REQUIRED, read_hashed_rows, validate_rows,
    )
    _, tables = read_hashed_rows()
    os.environ.pop("PROTECTED_ARCHIVE_B64", None)
    if set(tables) != set(EXPECTED):
        raise ValueError("G6_PRIVATE_RATE_SET_INCOMPLETE")
    protected = Path(tempfile.mkdtemp(prefix="issue652-g5-", dir="/dev/shm"))
    os.chmod(protected, 0o700)
    result = {
        "schema": "issue652.g6.registration_p3.v1",
        "source_sha": source_sha, "binary_sha256": file_sha(binary),
        "observer_sha256": file_sha(tracer),
        "oci": OCI, "cases": {}, "registration": "HOLD",
        "P3_3ns": "NOT_RUN" if registration_only else "HOLD",
        "P4_100us": "NOT_RUN", "G6_semantic_parity": "UNPROVEN",
        "science": "SCIENCE_HOLD", "raw_private_rates_in_artifact": False,
    }
    try:
        for case in cases:
            public = staged / "scratch" / case
            private = protected / case
            for path in public.rglob("*"):
                if path.is_symlink():
                    raise ValueError("G6_PUBLIC_STAGE_SYMLINK_DENIED")
            shutil.copytree(public, private)
            rate_dir = private / "experiments/Issue395_powered_chemistry_ladder/private_rates"
            if rate_dir.exists() or rate_dir.is_symlink():
                raise ValueError("G6_RATE_DEST_ALREADY_EXISTS")
            rate_dir.mkdir(mode=0o700)
            for name in sorted(REQUIRED[case]):
                blob = tables[name]
                if sha(blob) != EXPECTED[name] or validate_rows(blob) != 100:
                    raise ValueError("G6_PROTECTED_RATE_DIGEST_OR_ROWS_CHANGED")
                dest = rate_dir / name
                fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             getattr(os, "O_NOFOLLOW", 0), 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(blob)
                if file_sha(dest) != EXPECTED[name]:
                    raise ValueError("G6_PROTECTED_RATE_COPY_DRIFT")
            ordered = source_receipt["cases"][case]["ordered"]
            expected = source_receipt["cases"][case]["layer_sha256"]
            root = private / "experiments/Issue395_powered_chemistry_ladder"
            if {Path(p).name: file_sha(root / Path(p).name) for p in ordered} != expected:
                raise ValueError("G6_G5_LAYER_SHA_MISMATCH")
            code, log = execute(docker_cmd(private, ordered, observe=True), timeout=360)
            # Repair only our own private /dev/shm subtree, so trace can be read
            # and later securely removed despite OCI root-owned .jitcache.
            subprocess.run(
                ["sudo", "chown", "-Rh", f"{os.getuid()}:{os.getgid()}", "--", str(private)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=90, check=True,
            )
            trace = private / "g6_owners.tsv"
            case_result = {
                "P2_trace_return_code": code,
                "P2_trace_raw_output_sha256": sha(log.encode()),
                "P2_trace_raw_output_bytes": len(log),
                "P2_syntax_ok": code == 0 and "Syntax OK" in log,
                "P3_3ns": "NOT_RUN",
            }
            if not case_result["P2_syntax_ok"] or not trace.is_file():
                case_result["registration"] = "HOLD_OBSERVER_OR_NATIVE_FAILURE"
            else:
                trace_bytes = trace.read_bytes()
                case_result["preload_marker_count"] = trace_bytes.count(b"G6_PRELOAD_READY\n")
                case_result["observed_trace_rows"] = trace_bytes.count(b"G6_OWNER\t")
                # Diagnostic-only narrow public names/types. Never store raw
                # trace, paths or protected rate input values in artifacts.
                target_candidates = []
                for raw_line in trace_bytes.decode("utf-8").splitlines():
                    fields = raw_line.split("\t")
                    if (len(fields) == 4 and fields[0] == "G6_OWNER"
                            and (fields[2] == "potential" or
                                 "Poisson" in fields[2] or
                                 fields[2].startswith("plasma_charge_"))):
                        target_candidates.append({
                            "family": fields[1], "name": fields[2], "type": fields[3]})
                case_result["bounded_target_registration_candidates"] = target_candidates[:80]
                case_result["target_candidates_truncated"] = len(target_candidates) > 80
                try:
                    case_result["registration"] = registration_receipt(trace_bytes)
                except ValueError as err:
                    case_result["registration"] = "HOLD_" + str(err)
            if not registration_only and isinstance(case_result["registration"], dict):
                c0 = root / C0
                before = c0.read_bytes()
                modified, patch = three_ns_input(before)
                if sha(before) != expected[C0]:
                    raise ValueError("G6_G5_C0_CHANGED_BEFORE_P3")
                c0.write_bytes(modified)
                case_result["P3_input_patch"] = patch
                rc, out = execute(docker_cmd(private, ordered, observe=False), timeout=600)
                case_result["P3_return_code"] = rc
                case_result["P3_raw_output_sha256"] = sha(out.encode())
                case_result["P3_raw_output_bytes"] = len(out)
                case_result["P3_diagnostic_flags"] = {
                    "moose_error": "*** ERROR ***" in out,
                    "segfault": "Segmentation fault" in out,
                    "nonlinear_divergence": "DIVERGED" in out,
                    "exception": "Exception" in out,
                    "timeout": rc == 124,
                }
                if rc == 0:
                    try:
                        case_result["P3_3ns"] = metrics_for_p3(private)
                    except ValueError as err:
                        case_result["P3_3ns"] = "HOLD_" + str(err)
                else:
                    case_result["P3_3ns"] = "HOLD_RUNTIME_NONZERO_OR_TIMEOUT"
            result["cases"][case] = case_result
            secure_tmpfs_cleanup(private)
        result["registration"] = (
            "PASS_TYPED_15_OWNERS" if all(
                isinstance(result["cases"][c]["registration"], dict)
                for c in cases) else "HOLD"
        )
        if not registration_only:
            result["P3_3ns"] = (
                "PASS_FINITE_3NS_NO_BASELINE_PARITY" if all(
                    isinstance(result["cases"][c]["P3_3ns"], dict)
                    for c in cases) else "HOLD"
            )
    finally:
        secure_tmpfs_cleanup(protected)
        tables.clear()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("G6_TYPED_REGISTRATION", result["registration"],
          "G6_SHORT_P3", result["P3_3ns"], "SCIENCE_HOLD")
    if result["registration"] != "PASS_TYPED_15_OWNERS":
        raise ValueError("G6_REGISTRATION_GATE_HOLD")
    if not registration_only and result["P3_3ns"] != "PASS_FINITE_3NS_NO_BASELINE_PARITY":
        raise ValueError("G6_SHORT_P3_GATE_HOLD")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registration-only", action="store_true")
    parser.add_argument("--case", choices=CASES,
                        help="Run exactly one matrix case; absent preserves both cases")
    args = parser.parse_args()
    run(args.staged, args.output, registration_only=args.registration_only,
        cases=selected_cases(args.case))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
