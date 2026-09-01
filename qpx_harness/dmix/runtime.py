"""External build/run orchestration for D_mix equivalence validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..runtime import resolve_executable, validate_executable
from .analysis import REL_TOL, compare, read_dmix, trace_input
from .source_transform import EquivalenceError, legacy_source_transform

SOURCE_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
BASE_CASE_RELATIVE = Path(
    "tests/Issue20_full_oxygen_canonical_promotion/dmix_oracle_ne_sensitivity"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def stream(command: list[str], cwd: Path, log: Path) -> int:
    print("DMIX_EQ_COMMAND:", shlex.join(command))
    with log.open("w", buffering=1) as f:
        p = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert p.stdout is not None
        for line in p.stdout:
            print(line, end="")
            f.write(line)
            f.flush()
        return p.wait()


def prepare_case(base: Path, target: Path, trace: bool) -> None:
    shutil.copytree(base, target)
    for stale in target.glob("input_out*"):
        if stale.is_file():
            stale.unlink()
    if trace:
        inp = target / "input.i"
        inp.write_text(trace_input(inp.read_text()))


def run_case(exe: Path, case: Path, label: str, root: Path) -> dict[str, Any]:
    for stale in case.glob("input_out*"):
        if stale.is_file():
            stale.unlink()
    if stream(
        [str(exe), "-i", "input.i", "--check-input"],
        case,
        root / f"{label}_p2.log",
    ):
        raise EquivalenceError(f"{label} P2 failed")
    if stream(
        [str(exe), "-i", "input.i"],
        case,
        root / f"{label}_p3.log",
    ):
        raise EquivalenceError(f"{label} P3 failed")
    return {
        "input_sha256": sha256(case / "input.i"),
        "csv_sha256": sha256(case / "input_out.csv"),
        "values": read_dmix(case / "input_out.csv"),
    }


def _create_result_root(results: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = results / f"dmix_equivalence_Issue32_{stamp}"
    index = 1
    while root.exists():
        root = results / f"dmix_equivalence_Issue32_{stamp}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def validate(args: argparse.Namespace) -> int:
    from .characterization import self_test

    if self_test():
        return 2
    if not math.isfinite(args.rel_tol) or args.rel_tol <= 0:
        raise EquivalenceError("--rel-tol must be finite and positive")

    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    qpx_root = exe.parent.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    source = args.source.resolve() if args.source else qpx_root / SOURCE_RELATIVE
    base = args.base_case.resolve() if args.base_case else repo_root / BASE_CASE_RELATIVE
    if not source.is_file() or not base.is_dir():
        raise EquivalenceError(f"missing source/base case: source={source} base={base}")

    source_original = source.read_bytes()
    source_sha = hashlib.sha256(source_original).hexdigest()
    source_legacy_text, source_parse = legacy_source_transform(source_original.decode())
    source_legacy = source_legacy_text.encode()

    jobs = args.jobs or max(1, min(8, os.cpu_count() or 1))
    build = shlex.split(args.build_command) if args.build_command else ["make", f"-j{jobs}"]

    results = qpx_root / "temp" / "results"
    results.mkdir(parents=True, exist_ok=True)
    root = _create_result_root(results)
    print("DMIX_EQ_ROOT:", root)

    shutil.copy2(exe, root / "qpx-opt.production")
    shutil.copy2(source, root / "QPXThermalDiffusionMaterial.production.C")
    exe_sha = sha256(exe)

    cases: dict[str, Path] = {}
    for branch in ("candidate", "legacy"):
        for name, is_trace in (("ordinary", False), ("trace", True)):
            case = root / "cases" / f"{branch}_{name}"
            prepare_case(base, case, is_trace)
            cases[f"{branch}_{name}"] = case

    for name in ("ordinary", "trace"):
        if sha256(cases[f"candidate_{name}"] / "input.i") != sha256(
            cases[f"legacy_{name}"] / "input.i"
        ):
            raise EquivalenceError(f"candidate/legacy {name} input mismatch")

    summary: dict[str, Any] = {
        "relative_tolerance": args.rel_tol,
        "production_source_sha256": source_sha,
        "production_executable_sha256": exe_sha,
        "source_parse": source_parse,
    }
    source_ok = binary_ok = False
    try:
        candidate = {
            name: run_case(exe, cases[f"candidate_{name}"], f"candidate_{name}", root)
            for name in ("ordinary", "trace")
        }
        summary["candidate"] = candidate

        source.write_bytes(source_legacy)
        os.utime(source, None)
        if stream(build, qpx_root, root / "build_legacy.log"):
            raise EquivalenceError("legacy build failed")
        summary["legacy_executable_sha256"] = sha256(exe)

        legacy = {
            name: run_case(exe, cases[f"legacy_{name}"], f"legacy_{name}", root)
            for name in ("ordinary", "trace")
        }
        summary["legacy"] = legacy
        summary["comparisons"] = {
            name: compare(candidate[name]["values"], legacy[name]["values"], args.rel_tol)
            for name in ("ordinary", "trace")
        }
        summary["validation_status"] = (
            "PASS"
            if all(value["status"] == "PASS" for value in summary["comparisons"].values())
            else "FAIL"
        )
    except Exception as exc:
        summary["validation_status"] = "FAIL"
        summary["error"] = str(exc)
        print("DMIX_EQ_ERROR:", exc, file=sys.stderr)
    finally:
        source.write_bytes(source_original)
        os.utime(source, None)
        source_ok = sha256(source) == source_sha
        restore_rc = stream(build, qpx_root, root / "build_restored.log") if source_ok else 1
        try:
            shutil.copy2(root / "qpx-opt.production", exe)
            binary_ok = sha256(exe) == exe_sha
        except OSError:
            binary_ok = False
        summary["restore_build_returncode"] = restore_rc
        summary["source_restored"] = source_ok
        summary["binary_restored"] = binary_ok
        write_json(root / "summary.json", summary)
        print("DMIX_EQ_RESTORE:", "PASS" if source_ok and binary_ok else "FAIL")

    for name in ("ordinary", "trace"):
        result = summary.get("comparisons", {}).get(name, {})
        print(f"DMIX_EQ_{name.upper()}:", result.get("status", "NOT_RUN"))
        if "max_relative_error" in result:
            print(f"DMIX_EQ_{name.upper()}_MAX_REL: {result['max_relative_error']:.6e}")
    print("DMIX_EQ_VALIDATION:", summary.get("validation_status", "FAIL"))
    print("DMIX_EQ_SUMMARY:", root / "summary.json")
    return (
        0
        if summary.get("validation_status") == "PASS" and source_ok and binary_ok
        else 2
    )
