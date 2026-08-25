#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_executable(repo_root: Path) -> Path:
    env = os.environ.get("QPX_EXECUTABLE")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_file():
            return p
        raise SystemExit(f"QPX_EXECUTABLE does not exist: {p}")

    local = repo_root / "bin" / "qpx-opt"
    if local.is_file():
        return local.resolve()

    found = shutil.which("qpx-opt")
    if found:
        return Path(found).resolve()

    raise SystemExit(
        "qpx-opt not found. Set QPX_EXECUTABLE, place it at bin/qpx-opt, "
        "or add qpx-opt to PATH."
    )


def load_test(case_dir: Path):
    manifest = case_dir / "test.json"
    if not manifest.is_file():
        raise SystemExit(f"missing test manifest: {manifest}")
    return json.loads(manifest.read_text())


def run_case(case_dir: Path) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    case_dir = case_dir.resolve()
    cfg = load_test(case_dir)
    exe = resolve_executable(repo_root)

    input_name = cfg["input"]
    checker = cfg.get("checker")
    checker_args = cfg.get("checker_args", [])

    result_dir = repo_root / "results" / str(case_dir.relative_to(repo_root / "tests"))
    result_dir.mkdir(parents=True, exist_ok=True)

    # MOOSE inputs generally resolve local mesh/data dependencies relative to cwd,
    # so execute in the canonical test directory and route console output to results/.
    log_path = result_dir / "run.log"
    print(f"CASE       : {case_dir.relative_to(repo_root)}")
    print(f"EXECUTABLE : {exe}")
    print(f"INPUT      : {input_name}")
    print(f"LOG        : {log_path.relative_to(repo_root)}")

    with log_path.open("w") as log:
        proc = subprocess.run(
            [str(exe), "-i", input_name],
            cwd=case_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    if proc.returncode != 0:
        print("SOLVE      : FAIL")
        return proc.returncode or 1

    print("SOLVE      : PASS")

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
