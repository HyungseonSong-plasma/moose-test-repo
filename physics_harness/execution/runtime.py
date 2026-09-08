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
    timed_out: bool = False


@dataclass(frozen=True)
class TelemetrySample:
    """Raw process telemetry with no semantic liveness classification."""

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


def resolve_results_root(
    executable: str | os.PathLike[str] | None,
    configured: str | os.PathLike[str] | None = None,
) -> Path:
    """Resolve the reusable mechanical results root for a QPX workflow.

    Experiment-relative configured paths should be resolved by the application
    layer before they are passed here. Without an explicit root, preserve the
    established QPX sibling ``temp/results`` convention.
    """
    if configured not in (None, ""):
        return Path(configured).expanduser().resolve()
    return resolve_executable(executable).parent / "temp" / "results"


def validate_executable(exe: Path) -> None:
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


def _stop_process(proc: subprocess.Popen, *, grace_seconds: float = 10.0) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    stream: bool = False,
    telemetry_callback: TelemetryCallback | None = None,
    heartbeat_seconds: float = 10.0,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> RunResult:
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive when provided")
    if stream and timeout_seconds is not None:
        raise ValueError("timeout_seconds is not supported with stream=True")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    if stream:
        with log_path.open("w", buffering=1) as log:
            proc = subprocess.Popen(
                list(cmd), cwd=cwd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1, env=env,
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
                _stop_process(proc)
                raise
        return RunResult(rc, time.perf_counter() - start, False)

    with log_path.open("w", buffering=1) as log:
        proc = subprocess.Popen(
            list(cmd), cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=env,
        )
        next_heartbeat = time.perf_counter() + max(0.5, heartbeat_seconds)
        deadline = start + timeout_seconds if timeout_seconds is not None else None
        timed_out = False
        try:
            while True:
                rc = proc.poll()
                if rc is not None:
                    break
                now = time.perf_counter()
                if deadline is not None and now >= deadline:
                    timed_out = True
                    _stop_process(proc)
                    rc = 124
                    break
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
            _stop_process(proc)
            raise
    return RunResult(int(rc), time.perf_counter() - start, timed_out)


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
    timeout_seconds: float | None = None,
) -> RunResult:
    return run_command(
        [str(exe), "-i", input_name, *[str(arg) for arg in extra_args]],
        cwd=cwd,
        log_path=log_path,
        stream=stream,
        telemetry_callback=telemetry_callback,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )
