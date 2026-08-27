#!/usr/bin/env python3

import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from temporal_csv import normalize_from_manifest
from validate_parser_symbols import validate_file as validate_parser_symbol_file


TEMPORAL_RAW_POLICIES = {
    "include_initial_as_physics",
    "not_applicable_no_temporal_csv",
}


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


def is_transient_input(input_path: Path) -> bool:
    text = input_path.read_text()
    return bool(re.search(r"^\s*type\s*=\s*Transient\b", text, re.MULTILINE))


def validate_temporal_manifest_preflight(input_path: Path, cfg: dict) -> None:
    """Require explicit temporal-row semantics for schema-v2 transient cases.

    Schema-v1 cases are grandfathered so historical regressions are not silently
    reinterpreted. New or modified transient cases must use validation_schema=2.
    """

    checker = cfg.get("checker")
    if not checker or not is_transient_input(input_path):
        return

    schema = int(cfg.get("validation_schema", 1))
    if schema < 2:
        print("TEMPORAL_P0: LEGACY_SCHEMA_WARNING")
        return

    specs = cfg.get("temporal_csv", [])
    raw_policy = cfg.get("temporal_csv_policy")

    if not specs and raw_policy not in TEMPORAL_RAW_POLICIES:
        print("TEMPORAL_P0: FAIL")
        raise SystemExit(
            "validation_schema=2 transient test with checker must declare either "
            "test.json temporal_csv normalization or an explicit temporal_csv_policy; "
            "silent initialization-row semantics are forbidden"
        )

    if raw_policy is not None and raw_policy not in TEMPORAL_RAW_POLICIES:
        print("TEMPORAL_P0: FAIL")
        raise SystemExit(
            f"unsupported temporal_csv_policy={raw_policy!r}; "
            f"expected one of {sorted(TEMPORAL_RAW_POLICIES)}"
        )

    checker_args = [str(x) for x in cfg.get("checker_args", [])]
    for spec in specs:
        for key in ("source", "physical", "initial_row_policy"):
            if key not in spec:
                print("TEMPORAL_P0: FAIL")
                raise SystemExit(f"temporal_csv entry missing required key {key!r}")

        source = str(spec["source"])
        physical = str(spec["physical"])
        if source == physical:
            print("TEMPORAL_P0: FAIL")
            raise SystemExit(
                "temporal_csv source and physical paths must differ; raw runtime evidence "
                "must be preserved"
            )

        if source in checker_args and spec["initial_row_policy"] == "exclude_observation":
            print("TEMPORAL_P0: FAIL")
            raise SystemExit(
                f"checker_args references raw temporal CSV {source!r}; use normalized "
                f"physical CSV {physical!r} instead"
            )

        csv_args = [arg for arg in checker_args if arg.lower().endswith(".csv")]
        if csv_args and physical not in csv_args:
            print("TEMPORAL_P0: FAIL")
            raise SystemExit(
                f"checker_args contains CSV paths {csv_args} but not normalized temporal "
                f"CSV {physical!r}"
            )

    print("TEMPORAL_P0: PASS")


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
    validate_temporal_manifest_preflight(input_path, cfg)

    result_dir = repo_root / "results" / str(case_dir.relative_to(repo_root / "tests"))
    result_dir.mkdir(parents=True, exist_ok=True)

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
