"""Case staging, measurement, evidence, and runtime orchestration for Issue31 EVR1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from recipes import issue31_coupling as recipe

from ..evidence.artifacts import write_json_bundle
from ..execution.cases import stage_case, validate_referenced_files
from ..dmix_equivalence import legacy_source_transform
from ..evidence import sha256_file, utc_timestamp
from ..performance_core import run_measurement
from ..performance_investigation import build_investigation_summary
from ..performance_smoke import (
    build_smoke_manifest,
    compare_smoke_results,
    default_results_root,
)
from ..preflight import validate_parser_symbols_text
from ..execution.runtime import resolve_executable, validate_executable
from .classification import _status, preliminary_classification

EXPERIMENT_ID = "issue31-evr1-optimized-monolithic"
PURGE_DIRECTORY_NAMES = (".jitcache",)
PURGE_PATTERNS = (
    "input_out*",
    "r29_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


class CouplingEVR1RuntimeError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise CouplingEVR1RuntimeError(f"expected JSON object: {path}")
    return payload


def _create_root(results_root: Path, *, timestamp: str | None = None) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or utc_timestamp()
    stem = f"coupling_evr1_Issue31_{stamp}"
    root = results_root / stem
    index = 1
    while root.exists():
        root = results_root / f"{stem}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def _manifest(*, mode: str, case_dir: Path, case_id: str) -> dict[str, Any]:
    return build_smoke_manifest(
        mode=mode,
        case_dir=case_dir,
        input_name="input.i",
        experiment_id=EXPERIMENT_ID,
        case_id=case_id,
        num_steps=1,
        species=list(recipe.SPECIES),
    )


def _run_pair(
    *,
    case_dir: Path,
    case_id: str,
    exe: Path,
    results_root: Path,
) -> dict[str, Any]:
    pair_root = results_root / case_id
    pair_root.mkdir(parents=True)
    results: dict[str, Any] = {}
    returncodes: dict[str, int | None] = {"BENCHMARK": None, "PROFILE": None}

    for mode in ("BENCHMARK", "PROFILE"):
        if mode == "PROFILE" and returncodes["BENCHMARK"] not in (0,):
            break
        manifest = _manifest(mode=mode, case_dir=case_dir, case_id=case_id)
        manifest_path = pair_root / f"{mode.lower()}_manifest.json"
        write_json_bundle(
            pair_root,
            {f"{mode.lower()}_manifest": (manifest_path.name, manifest)},
        )
        out = pair_root / mode.lower()
        print(f"ISSUE31_EVR1_CASE_START: {case_id} {mode}")
        rc = run_measurement(manifest_path, executable=exe, out_dir=out)
        print(f"ISSUE31_EVR1_CASE_END: {case_id} {mode} rc={rc}")
        returncodes[mode] = rc
        result_path = out / "result.json"
        if result_path.is_file():
            results[mode.lower()] = _load_json(result_path)

    benchmark = results.get("benchmark")
    profile = results.get("profile")
    smoke = compare_smoke_results(benchmark, profile)
    investigation = None
    if (
        benchmark
        and profile
        and benchmark.get("validation", {}).get("status") == "P2_PASS_P3_PASS"
        and profile.get("validation", {}).get("status") == "P2_PASS_P3_PASS"
    ):
        investigation = build_investigation_summary(benchmark, profile, smoke)

    return {
        "root": str(pair_root),
        "returncodes": returncodes,
        "benchmark": benchmark,
        "profile": profile,
        "smoke": smoke,
        "investigation": investigation,
    }


def run(args: argparse.Namespace) -> int:
    from .characterization import self_test

    if self_test():
        return 2

    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    qpx_root = exe.parent.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    base_input = (
        args.base_input.resolve()
        if args.base_input
        else repo_root / recipe.BASE_INPUT_RELATIVE
    )
    asset_dir = (
        args.asset_case.resolve()
        if args.asset_case
        else qpx_root / recipe.DEFAULT_ASSET_CASE_RELATIVE
    )
    source = qpx_root / recipe.SOURCE_RELATIVE

    if not base_input.is_file():
        raise CouplingEVR1RuntimeError(f"missing archived #29 Q0 reference: {base_input}")
    if not asset_dir.is_dir():
        raise CouplingEVR1RuntimeError(
            f"missing asset case: {asset_dir}; pass --asset-case with qvt.msh and transport_data.txt"
        )
    if not source.is_file():
        raise CouplingEVR1RuntimeError(f"missing QPX transport source: {source}")

    source_text = source.read_text()
    _, source_parse = legacy_source_transform(source_text)
    if source_parse.get("parser") != "CppSource+CppCallArguments":
        raise CouplingEVR1RuntimeError(
            "optimized D_mix source identity could not be structurally verified"
        )

    base_text = base_input.read_text()
    parser_errors = validate_parser_symbols_text(base_text, str(base_input))
    if parser_errors:
        raise CouplingEVR1RuntimeError(
            "base input parser-symbol preflight failed: " + " | ".join(parser_errors)
        )

    try:
        transport_text, transform_meta = recipe.transport_only_input(base_text)
    except recipe.Issue31CouplingError as exc:
        raise CouplingEVR1RuntimeError(str(exc)) from exc
    parser_errors = validate_parser_symbols_text(transport_text, "<transport-only>")
    if parser_errors:
        raise CouplingEVR1RuntimeError(
            "transport-only parser-symbol preflight failed: " + " | ".join(parser_errors)
        )

    results_root = (
        args.results_root.resolve()
        if args.results_root
        else default_results_root(exe)
    )
    root = _create_root(results_root)
    print(f"ISSUE31_EVR1_ROOT: {root}")

    cases_root = root / "cases"
    monolithic_case = cases_root / "monolithic_q0"
    transport_case = cases_root / "transport_only"
    stage_case(
        asset_dir,
        monolithic_case,
        input_text=base_text,
        purge_directory_names=PURGE_DIRECTORY_NAMES,
        purge_patterns=PURGE_PATTERNS,
    )
    stage_case(
        asset_dir,
        transport_case,
        input_text=transport_text,
        purge_directory_names=PURGE_DIRECTORY_NAMES,
        purge_patterns=PURGE_PATTERNS,
    )

    monolithic_refs = validate_referenced_files(base_text, monolithic_case, skip_dynamic=True)
    transport_refs = validate_referenced_files(transport_text, transport_case, skip_dynamic=True)

    identity = {
        "qpx_realpath": str(exe),
        "qpx_sha256": sha256_file(exe),
        "transport_source": str(source),
        "transport_source_sha256": sha256_file(source),
        "optimized_dmix_source_parse": source_parse,
        "base_input": str(base_input),
        "base_input_sha256": sha256_file(base_input),
        "asset_case": str(asset_dir),
        "referenced_files_monolithic": monolithic_refs,
        "referenced_files_transport": transport_refs,
        "transport_transform": transform_meta,
    }
    write_json_bundle(root, {"identity": ("identity.json", identity)})
    print("ISSUE31_EVR1_P0: PASS")
    print("ISSUE31_EVR1_P1: PASS")

    transport = _run_pair(
        case_dir=transport_case,
        case_id="Issue31_transport_only",
        exe=exe,
        results_root=root / "measurements",
    )
    transport_physics = None
    if _status(transport.get("benchmark")) == "P2_PASS_P3_PASS":
        try:
            transport_physics = recipe.physics_check(transport_case, monolithic=False)
        except recipe.Issue31CouplingError as exc:
            transport_physics = {"status": "FAIL", "error": str(exc)}

    monolithic = _run_pair(
        case_dir=monolithic_case,
        case_id="Issue31_monolithic_q0",
        exe=exe,
        results_root=root / "measurements",
    )
    monolithic_physics = None
    if _status(monolithic.get("benchmark")) == "P2_PASS_P3_PASS":
        try:
            monolithic_physics = recipe.physics_check(monolithic_case, monolithic=True)
        except recipe.Issue31CouplingError as exc:
            monolithic_physics = {"status": "FAIL", "error": str(exc)}

    decision = preliminary_classification(
        transport, monolithic, transport_physics, monolithic_physics
    )
    summary = {
        "schema_version": 1,
        "issue": 31,
        "work_id": "real-qvt-transport-poisson-architecture-selection",
        "evr": 1,
        "identity": identity,
        "transport_only": transport,
        "transport_physics": transport_physics,
        "monolithic_q0": monolithic,
        "monolithic_physics": monolithic_physics,
        "preliminary_classification": decision,
    }
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print(
        "ISSUE31_EVR1_TRANSPORT_PHYSICS:",
        (transport_physics or {}).get("status", "NOT_RUN"),
    )
    print(
        "ISSUE31_EVR1_MONOLITHIC_PHYSICS:",
        (monolithic_physics or {}).get("status", "NOT_RUN"),
    )
    print("ISSUE31_EVR1_PRECLASS:", decision["class"])
    if "transport_benchmark_wall_seconds" in decision:
        print(
            "ISSUE31_EVR1_TRANSPORT_WALL:",
            f"{decision['transport_benchmark_wall_seconds']:.6g}",
        )
        print(
            "ISSUE31_EVR1_MONOLITHIC_WALL:",
            f"{decision['monolithic_benchmark_wall_seconds']:.6g}",
        )
        ratio = decision.get("monolithic_to_transport_wall_ratio")
        if ratio is not None:
            print("ISSUE31_EVR1_WALL_RATIO:", f"{ratio:.6g}")
    bottleneck = decision.get("bottleneck") or {}
    if bottleneck:
        print("ISSUE31_EVR1_BOTTLENECK:", bottleneck.get("bottleneck_class"))
        print("ISSUE31_EVR1_BOTTLENECK_OUTCOME:", bottleneck.get("outcome"))
        print("ISSUE31_EVR1_BOTTLENECK_CONFIDENCE:", bottleneck.get("confidence"))
    print("ISSUE31_EVR1_SUMMARY:", root / "summary.json")

    return 0 if decision["class"] not in {
        "HARNESS_OR_CONSTRUCTION_FAIL",
        "PHYSICS_CHECK_FAIL",
    } else 2
