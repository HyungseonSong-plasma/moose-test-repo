#!/usr/bin/env python3
"""P0 characterization for the canonical Issue31 EVR2 runtime owner."""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue31_coupling as recipe
from qpx_harness.coupling_evr2 import orchestration as runtime
from qpx_harness.evidence import measurement_failure_signature
from qpx_harness.execution.cases import stage_case
from qpx_harness.performance.runner import result_status
from qpx_harness.performance.smoke import build_smoke_manifest


def _case(
    status: str,
    *,
    physics: str | None = None,
    signature: str | None = None,
    checker: str | None = None,
) -> dict:
    value = {
        "result": {"validation": {"status": status}},
        "failure": {"signature": signature},
    }
    if physics is not None:
        value["physics"] = {"status": physics}
    if checker is not None:
        value["canonical_checker"] = {"status": checker}
    return value


def _check_state_helper_contract() -> None:
    scenarios = (
        (None, None, False, False),
        ({}, None, False, False),
        (_case("HARNESS_OR_CONSTRUCTION_FAIL"), "HARNESS_OR_CONSTRUCTION_FAIL", False, False),
        (
            _case("RUNTIME_FAIL_OR_NONCONVERGENCE", signature="DIVERGED_MAX_IT"),
            "RUNTIME_FAIL_OR_NONCONVERGENCE",
            True,
            False,
        ),
        (
            _case("RUNTIME_FAIL_OR_NONCONVERGENCE", signature="OTHER"),
            "RUNTIME_FAIL_OR_NONCONVERGENCE",
            False,
            False,
        ),
        (_case("P2_PASS_P3_PASS", physics="PASS"), "P2_PASS_P3_PASS", False, True),
        (_case("P2_PASS_P3_PASS", physics="FAIL"), "P2_PASS_P3_PASS", False, False),
    )
    for case, status, nonconvergence, case_pass in scenarios:
        if result_status((case or {}).get("result")) != status:
            raise AssertionError("EVR2 result-status helper contract drift")
        if runtime._runtime_nonconvergence(case) is not nonconvergence:
            raise AssertionError("EVR2 runtime-nonconvergence helper contract drift")
        if runtime._case_pass(case) is not case_pass:
            raise AssertionError("EVR2 case-pass helper contract drift")

    kg_scenarios = (
        (_case("P2_PASS_P3_PASS", checker="PASS"), True),
        (_case("P2_PASS_P3_PASS", checker="FAIL"), False),
        (_case("RUNTIME_FAIL_OR_NONCONVERGENCE", checker="PASS"), False),
    )
    for case, expected in kg_scenarios:
        if runtime._kg_e_pass(case) is not expected:
            raise AssertionError("EVR2 KG-E pass helper contract drift")


def _check_manifest_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        case_dir = Path(tmp_name)
        (case_dir / "input.i").write_text("[Mesh]\n[]\n")
        expected = build_smoke_manifest(
            mode="BENCHMARK",
            case_dir=case_dir,
            input_name="input.i",
            experiment_id=runtime.EXPERIMENT_ID,
            case_id="Issue31_T3_dt1e8",
            num_steps=1,
            species=list(recipe.SPECIES),
        )
        actual = runtime._manifest(
            case_dir=case_dir,
            case_id="Issue31_T3_dt1e8",
            species=list(recipe.SPECIES),
        )
        if actual != expected:
            raise AssertionError("EVR2 BENCHMARK manifest contract drift")


def _check_failure_signature_contract() -> None:
    if measurement_failure_signature(None) != {"signature": "NO_RESULT"}:
        raise AssertionError("EVR2 no-result signature contract drift")

    samples = (
        ("DIVERGED_MAX_IT iterations 80", "DIVERGED_MAX_IT", 80),
        ("DIVERGED_LINE_SEARCH", "DIVERGED_LINE_SEARCH", None),
        ("DIVERGED_FNORM_NAN", "DIVERGED_FNORM_NAN", None),
        ("Nonlinear solve did not converge", "NONLINEAR_DID_NOT_CONVERGE", None),
        ("ordinary runtime output", None, None),
    )
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        for index, (text, signature, iterations) in enumerate(samples):
            log = root / f"sample_{index}.log"
            log.write_text(text + "\n")
            result = {"evidence": {"p3_log": str(log)}}
            actual = measurement_failure_signature(result)
            expected = {
                "signature": signature,
                "iterations": iterations,
                "log": str(log),
            }
            if actual != expected:
                raise AssertionError(
                    f"EVR2 failure-signature contract drift for {text!r}: {actual} != {expected}"
                )


def _check_generic_staging() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        asset = root / "asset"
        asset.mkdir()
        (asset / "input.i").write_text("old input\n")
        (asset / "qvt.msh").write_text("mesh\n")
        (asset / "input_out_old.csv").write_text("stale\n")
        (asset / ".jitcache").mkdir()
        (asset / ".jitcache" / "cache").write_text("stale\n")
        nested = asset / "nested"
        nested.mkdir()
        (nested / "qpxperf_old").write_text("stale\n")

        target = root / "transport"
        stage_case(
            asset,
            target,
            input_text="new input\n",
            purge_directory_names=runtime.PURGE_DIRECTORY_NAMES,
            purge_patterns=runtime.PURGE_PATTERNS,
        )
        if (target / "input.i").read_text() != "new input\n":
            raise AssertionError("EVR2 transport staging did not replace input")
        if not (target / "qvt.msh").is_file():
            raise AssertionError("EVR2 transport staging lost case asset")
        if (target / "input_out_old.csv").exists():
            raise AssertionError("EVR2 transport staging retained generated CSV")
        if (target / ".jitcache").exists():
            raise AssertionError("EVR2 transport staging retained .jitcache")
        if (target / "nested" / "qpxperf_old").exists():
            raise AssertionError("EVR2 transport staging retained nested qpxperf artifact")

    with tempfile.TemporaryDirectory() as tmp_name:
        repo_root = Path(tmp_name) / "repo"
        source_parent = repo_root / recipe.KG_E_PARENT_RELATIVE
        case = source_parent / "qvt_prepoisson"
        case.mkdir(parents=True)
        (case / "test.json").write_text("{}\n")
        (case / "petsc_log_stale").write_text("stale\n")
        cases_root = Path(tmp_name) / "cases"
        cases_root.mkdir()
        staged = runtime._stage_kg_e(repo_root, cases_root)
        if staged != cases_root / "kg_e_parent" / "qvt_prepoisson":
            raise AssertionError("EVR2 KG-E staging path drift")
        if not (staged / "test.json").is_file():
            raise AssertionError("EVR2 KG-E staging lost canonical checker manifest")
        if (staged / "petsc_log_stale").exists():
            raise AssertionError("EVR2 KG-E staging retained generated artifact")


def _imports_module(path: Path, module: str) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base == module:
                return True
            if base == "qpx_harness" and module.startswith("qpx_harness."):
                leaf = module.split(".", 1)[1]
                if any(alias.name == leaf for alias in node.names):
                    return True
    return False


def _check_runtime_boundary() -> None:
    path = Path(runtime.__file__)
    source = path.read_text()
    for required in (
        "from recipes import issue31_coupling as recipe",
        "from ..evidence.artifacts import write_json_bundle",
        "stage_case",
        "validate_referenced_files",
        "create_collision_safe_directory",
        "run_managed_measurement",
        "measurement_failure_signature",
        "run_command",
        "recipe.configured_transport_input",
        "recipe.classify_evr2",
    ):
        if required not in source:
            raise AssertionError(f"EVR2 runtime owner missing required composition: {required}")

    for forbidden in (
        "coupling_evr2_timestep",
        "import hashlib",
        "import shutil",
        "from datetime import",
        "hashlib.sha256",
        "shutil.copytree",
        "datetime.now",
        "def _write_json",
        "def _load_json",
        "def _create_root",
        "def _stage_transport_case",
        "def _failure_signature",
        "subprocess.run",
        "run_measurement(",
        "def _purge_runtime_artifacts",
    ):
        if forbidden in source:
            raise AssertionError(f"EVR2 runtime owner retained duplicate mechanics: {forbidden}")
    if _imports_module(path, "qpx_harness.coupling_evr2_timestep"):
        raise AssertionError("EVR2 runtime owner reverse-imports legacy EVR2 owner")


def _check_production_route() -> None:
    source = (ROOT / "qpx_harness/cli/app.py").read_text()
    if "from qpx_harness.cli.commands.coupling import" not in source:
        raise AssertionError("EVR2 canonical CLI adapter is not routed by CLI")
    if "from qpx_harness.coupling_evr2_timestep import" in source:
        raise AssertionError("EVR2 legacy timestep owner remains routed by CLI")
    if '"coupling-evr2": coupling_evr2_main' not in source:
        raise AssertionError("EVR2 command dispatch no longer uses canonical alias")


def _check_oracle_retirement() -> None:
    this_path = Path(__file__)
    if _imports_module(this_path, "qpx_harness.coupling_evr2_timestep"):
        raise AssertionError("WP13 retained legacy EVR2 oracle import")


def main() -> int:
    try:
        _check_state_helper_contract()
        _check_manifest_contract()
        _check_failure_signature_contract()
        _check_generic_staging()
        _check_runtime_boundary()
        _check_production_route()
        _check_oracle_retirement()
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_EVR2_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_EVR2_RUNTIME_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
