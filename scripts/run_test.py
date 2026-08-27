#!/usr/bin/env python3

import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from validate_parser_symbols import validate_file as validate_parser_symbol_file


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


def validate_executable(exe: Path) -> None:
    """Detect a truncated/corrupted ELF before reporting a solver failure."""
    size = exe.stat().st_size
    with exe.open("rb") as f:
        header = f.read(64)

    # Non-ELF executables are left to the operating system. This keeps the
    # runner portable while still protecting the Linux qpx-opt path.
    if not header.startswith(b"\x7fELF"):
        return

    if len(header) < 64:
        raise SystemExit(f"invalid ELF executable (header truncated): {exe}")

    elf_class = header[4]
    data_encoding = header[5]
    if elf_class != 2:
        raise SystemExit(f"unsupported/non-ELF64 qpx executable: {exe}")
    if data_encoding not in (1, 2):
        raise SystemExit(f"invalid ELF data encoding in {exe}")

    endian = "<" if data_encoding == 1 else ">"
    phoff = struct.unpack_from(endian + "Q", header, 32)[0]
    shoff = struct.unpack_from(endian + "Q", header, 40)[0]
    phentsize = struct.unpack_from(endian + "H", header, 54)[0]
    phnum = struct.unpack_from(endian + "H", header, 56)[0]
    shentsize = struct.unpack_from(endian + "H", header, 58)[0]
    shnum = struct.unpack_from(endian + "H", header, 60)[0]

    ph_end = phoff + phentsize * phnum
    if phnum and ph_end > size:
        raise SystemExit(
            "invalid/truncated ELF executable: program-header table extends "
            f"to byte {ph_end}, file size is only {size}: {exe}"
        )

    sh_end = shoff + shentsize * shnum
    if shoff and shnum and sh_end > size:
        raise SystemExit(
            "invalid/truncated ELF executable: section-header table extends "
            f"to byte {sh_end}, file size is only {size}: {exe}"
        )


def load_test(case_dir: Path):
    manifest = case_dir / "test.json"
    if not manifest.is_file():
        raise SystemExit(f"missing test manifest: {manifest}")
    return json.loads(manifest.read_text())


def validate_input_preflight(input_path: Path) -> None:
    if not input_path.is_file():
        raise SystemExit(f"missing test input: {input_path}")

    errors = validate_parser_symbol_file(input_path)
    if errors:
        print("PARSER_P0  : FAIL")
        for error in errors:
            print("  -", error)
        raise SystemExit(2)

    print("PARSER_P0  : PASS")


def run_case(case_dir: Path) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    case_dir = case_dir.resolve()
    cfg = load_test(case_dir)
    exe = resolve_executable(repo_root)
    validate_executable(exe)

    input_name = cfg["input"]
    checker = cfg.get("checker")
    checker_args = cfg.get("checker_args", [])
    test_type = cfg.get("type", "canonical")

    input_path = case_dir / input_name
    validate_input_preflight(input_path)

    result_dir = repo_root / "results" / str(case_dir.relative_to(repo_root / "tests"))
    result_dir.mkdir(parents=True, exist_ok=True)

    # MOOSE inputs generally resolve local mesh/data dependencies relative to cwd,
    # so execute in the canonical test directory and route console output to results/.
    log_path = result_dir / "run.log"
    print(f"CASE       : {case_dir.relative_to(repo_root)}")
    print(f"TYPE       : {test_type}")
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
