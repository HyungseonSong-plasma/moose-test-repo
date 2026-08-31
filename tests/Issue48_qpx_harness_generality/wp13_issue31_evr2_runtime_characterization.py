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
from qpx_harness import coupling_evr2_runtime as runtime
from qpx_harness import coupling_evr2_timestep as legacy


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


def _check_state_helper_equivalence() -> None:
    cases = (
        None,
        {},
        _case("HARNESS_OR_CONSTRUCTION_FAIL"),
        _case("RUNTIME_FAIL_OR_NONCONVERGENCE", signature="DIVERGED_MAX_IT"),
        _case("RUNTIME_FAIL_OR_NONCONVERGENCE", signature="OTHER"),
        _case("P2_PASS_P3_PASS", physics="PASS"),
        _case("P2_PASS_P3_PASS", physics="FAIL"),
    )
    for case in cases:
        if runtime._result_status(case) != legacy._result_status(case):
            raise AssertionError("EVR2 result-status helper drift")
        if runtime._runtime_nonconvergence(case) != legacy._runtime_nonconvergence(case):
            raise AssertionError("EVR2 runtime-nonconvergence helper drift")
        if runtime._case_pass(case) != legacy._case_pass(case):
            raise AssertionError("EVR2 case-pass helper drift")

    kg_cases = (
        _case("P2_PASS_P3_PASS", checker="PASS"),
        _case("P2_PASS_P3_PASS", checker="FAIL"),
        _case("RUNTIME_FAIL_OR_NONCONVERGENCE", checker="PASS"),
    )
    for case in kg_cases:
        if runtime._kg_e_pass(case) != legacy._kg_e_pass(case):
            raise AssertionError("EVR2 KG-E pass helper drift")


def _check_manifest_equivalence() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        case_dir = Path(tmp_name)
        (case_dir / "input.i").write_text("[Mesh]\n[]\n")
        expected = legacy._manifest(
            case_dir=case_dir,
            case_id="Issue31_T3_dt1e8",
            experiment_id=runtime.EXPERIMENT_ID,
            species=list(recipe.SPECIES),
        )
        actual = runtime._manifest(
            case_dir=case_dir,
            case_id="Issue31_T3_dt1e8",
            species=list(recipe.SPECIES),
        )
        if actual != expected:
            raise AssertionError("EVR2 BENCHMARK manifest equivalence drift")


def _check_failure_signature_equivalence() -> None:
    if runtime._failure_signature(None) != legacy._failure_signature(None):
        raise AssertionError("EVR2 no-result signature drift")

    samples = (
        "DIVERGED_MAX_IT iterations 80",
        "DIVERGED_LINE_SEARCH",
        "DIVERGED_FNORM_NAN",
        "Nonlinear solve did not converge",
        "ordinary runtime output",
    )
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        for index, text in enumerate(samples):
            log = root / f"sample_{index}.log"
            log.write_text(text + "\n")
            result = {"evidence": {"p3_log": str(log)}}
            actual = runtime._failure_signature(result)
            expected = legacy._failure_signature(result)
            if actual != expected:
                raise AssertionError(
                    f"EVR2 failure-signature equivalence drift for {text!r}"
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
        runtime._stage_transport_case(asset, target, "new input\n")
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
        "from .artifacts import write_json_bundle",
        "stage_case",
        "validate_referenced_files",
        "from .evidence import sha256_file, utc_timestamp",
        "run_measurement",
        "subprocess.run",
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
        "def _purge_runtime_artifacts",
    ):
        if forbidden in source:
            raise AssertionError(f"EVR2 runtime owner retained duplicate mechanics: {forbidden}")
    if _imports_module(path, "qpx_harness.coupling_evr2_timestep"):
        raise AssertionError("EVR2 runtime owner reverse-imports legacy EVR2 owner")


def _check_checkpoint_route() -> None:
    source = (ROOT / "scripts/qpx.py").read_text()
    if "from qpx_harness.coupling_evr2_timestep import" not in source:
        raise AssertionError("EVR2 extraction checkpoint unexpectedly changed CLI route")
    if "from qpx_harness.coupling_evr2_runtime import" in source:
        raise AssertionError("EVR2 runtime owner was routed before extraction P0")


def main() -> int:
    try:
        _check_state_helper_equivalence()
        _check_manifest_equivalence()
        _check_failure_signature_equivalence()
        _check_generic_staging()
        _check_runtime_boundary()
        _check_checkpoint_route()
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_EVR2_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_EVR2_RUNTIME_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
