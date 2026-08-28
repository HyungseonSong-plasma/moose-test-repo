"""Canonical QPX executable resolution, process execution, and raw telemetry."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class RunResult:
    returncode: int
    wall_seconds: float


@dataclass(frozen=True)
class TelemetrySample:
    """Raw process telemetry sampled by the runtime layer.

    This model intentionally contains no semantic liveness state or display text.
    """

    elapsed_seconds: float
    cpu_seconds: float | None
    log_size: int


TelemetryCallback = Callable[[TelemetrySample], None]


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


def _linux_process_cpu_seconds(pid: int) -> float | None:
    """Return process user+system CPU time from /proc, or None when unavailable."""

    stat_path = Path(f"/proc/{pid}/stat")
    try:
        text = stat_path.read_text()
        tail = text[text.rfind(")") + 2 :].split()
        utime_ticks = int(tail[11])
        stime_ticks = int(tail[12])
        ticks_per_second = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        return (utime_ticks + stime_ticks) / float(ticks_per_second)
    except (OSError, ValueError, IndexError, KeyError):
        return None


def _log_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    stream: bool = False,
    telemetry_callback: TelemetryCallback | None = None,
    heartbeat_seconds: float = 10.0,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Run a command with canonical logging and optional raw telemetry sampling.

    ``stream=False`` keeps child stdout/stderr in ``log_path`` and can emit raw
    ``TelemetrySample`` objects. Semantic liveness classification and terminal
    presentation are deliberately outside this module.
    """

    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()

    if stream:
        with log_path.open("w", buffering=1) as log:
            proc = subprocess.Popen(
                list(cmd),
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
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

    with log_path.open("w", buffering=1) as log:
        proc = subprocess.Popen(
            list(cmd),
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
        )
        next_heartbeat = time.perf_counter() + max(0.5, heartbeat_seconds)

        try:
            while True:
                rc = proc.poll()
                if rc is not None:
                    break

                now = time.perf_counter()
                if telemetry_callback is not None and now >= next_heartbeat:
                    telemetry_callback(
                        TelemetrySample(
                            elapsed_seconds=now - start,
                            cpu_seconds=_linux_process_cpu_seconds(proc.pid),
                            log_size=_log_size(log_path),
                        )
                    )
                    next_heartbeat = now + max(0.5, heartbeat_seconds)

                time.sleep(0.25)
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise

    return RunResult(proc.returncode, time.perf_counter() - start)


def run_qpx(
    exe: Path,
    *,
    cwd: Path,
    input_name: str,
    log_path: Path,
    extra_args: Iterable[str] = (),
    stream: bool = False,
    telemetry_callback: TelemetryCallback | None = None,
    heartbeat_seconds: float = 10.0,
) -> RunResult:
    return run_command(
        [str(exe), "-i", input_name, *[str(arg) for arg in extra_args]],
        cwd=cwd,
        log_path=log_path,
        stream=stream,
        telemetry_callback=telemetry_callback,
        heartbeat_seconds=heartbeat_seconds,
    )
