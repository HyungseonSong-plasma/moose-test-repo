"""Canonical QPX executable resolution and process execution helpers."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RunResult:
    returncode: int
    wall_seconds: float


def _resolve_candidate(raw: str | os.PathLike[str], *, source: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"{source} does not exist: {path}")
    return path


def resolve_executable(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the canonical user-local qpx-opt.

    Resolution order:
      1. explicit path supplied by the caller
      2. QPX_EXECUTABLE
      3. qpx-opt from PATH

    Repository-local binary fallbacks are deliberately unsupported.
    """

    if explicit is not None:
        return _resolve_candidate(explicit, source="explicit qpx-opt")

    env = os.environ.get("QPX_EXECUTABLE")
    if env:
        return _resolve_candidate(env, source="QPX_EXECUTABLE")

    found = shutil.which("qpx-opt")
    if found:
        return Path(found).resolve()

    raise SystemExit(
        "qpx-opt not found. Set QPX_EXECUTABLE or add the canonical user-local "
        "qpx-opt to PATH."
    )


def validate_executable(exe: Path) -> None:
    """Detect a truncated/corrupted ELF before reporting a solver failure."""

    size = exe.stat().st_size
    with exe.open("rb") as handle:
        header = handle.read(64)

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


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    stream: bool = False,
) -> RunResult:
    """Run a command while preserving a canonical wall-time/logging path.

    ``stream=False`` preserves the historical regression-runner behavior: child
    stdout/stderr are written only to the log. ``stream=True`` additionally tees
    lines to the current stdout for long-running diagnostic/profiling use.
    """

    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()

    if not stream:
        with log_path.open("w") as log:
            proc = subprocess.run(
                list(cmd),
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        return RunResult(proc.returncode, time.perf_counter() - start)

    with log_path.open("w", buffering=1) as log:
        proc = subprocess.Popen(
            list(cmd),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write(line)
                log.flush()
            rc = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            try:
                rc = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = proc.wait()
            raise

    return RunResult(rc, time.perf_counter() - start)


def run_qpx(
    exe: Path,
    *,
    cwd: Path,
    input_name: str,
    log_path: Path,
    extra_args: Iterable[str] = (),
    stream: bool = False,
) -> RunResult:
    return run_command(
        [str(exe), "-i", input_name, *[str(arg) for arg in extra_args]],
        cwd=cwd,
        log_path=log_path,
        stream=stream,
    )
