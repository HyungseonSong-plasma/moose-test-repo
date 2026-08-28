#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qpx_harness.preflight import (  # noqa: E402
    validate_input_preflight,
    validate_temporal_manifest_preflight,
)
from qpx_harness.runtime import resolve_executable, run_qpx, validate_executable  # noqa: E402
from qpx_harness.temporal import normalize_from_manifest  # noqa: E402


def load_test(case_dir: Path):
    manifest = case_dir / "test.json"
    if not manifest.is_file():
        raise SystemExit(f"missing test manifest: {manifest}")
    return json.loads(manifest.read_text())


def prepare_temporal_outputs(case_dir: Path, cfg: dict) -> None:
    specs = cfg.get("temporal_csv", [])
    if not specs:
        return

    for spec in specs:
        try:
            summary = normalize_from_manifest(case_dir, spec)
        except Exception as exc:
            print("TEMPORAL_ROWS: FAIL")
            raise SystemExit(f"temporal CSV normalization failed: {exc}") from exc

        print("TEMPORAL_ROWS: PASS")
        print(f"  SOURCE              : {spec['source']}")
        print(f"  PHYSICAL            : {spec['physical']}")
        print(f"  POLICY              : {summary['initial_row_policy']}")
        print(f"  SOURCE_ROWS         : {summary['source_rows']}")
        print(f"  INITIALIZATION_ROWS : {summary['initialization_rows']}")
        print(f"  PHYSICAL_ROWS       : {summary['physical_rows']}")


def run_case(case_dir: Path) -> int:
    repo_root = REPO_ROOT
    case_dir = case_dir.resolve()
    cfg = load_test(case_dir)
    exe = resolve_executable()
    validate_executable(exe)

    input_name = cfg["input"]
    checker = cfg.get("checker")
    checker_args = cfg.get("checker_args", [])
    test_type = cfg.get("type", "canonical")

    input_path = case_dir / input_name
    validate_input_preflight(input_path)
    validate_temporal_manifest_preflight(input_path, cfg)

    result_dir = repo_root / "results" / str(case_dir.relative_to(repo_root / "tests"))
    result_dir.mkdir(parents=True, exist_ok=True)

    log_path = result_dir / "run.log"
    print(f"CASE       : {case_dir.relative_to(repo_root)}")
    print(f"TYPE       : {test_type}")
    print(f"EXECUTABLE : {exe}")
    print(f"INPUT      : {input_name}")
    print(f"LOG        : {log_path.relative_to(repo_root)}")

    solve = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_name,
        log_path=log_path,
    )

    if solve.returncode != 0:
        print("SOLVE      : FAIL")
        return solve.returncode or 1

    print("SOLVE      : PASS")

    prepare_temporal_outputs(case_dir, cfg)

    if not checker:
        print("CHECK      : SKIP")
        return 0

    check_cmd = [sys.executable, checker, *checker_args]
    check = subprocess.run(check_cmd, cwd=case_dir)
    print("CHECK      :", "PASS" if check.returncode == 0 else "FAIL")
    return check.returncode


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 scripts/run_test.py tests/<area>/<case>")
    raise SystemExit(run_case(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
