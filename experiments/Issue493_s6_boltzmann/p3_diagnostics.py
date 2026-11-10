#!/usr/bin/env python3
"""Sanitized native-solver heartbeat and fail-closed execution monitoring.

This module processes the *public-only* Issue #493 B/C diagnostic logs while
the full MOOSE stdout, Exodus and CSV remain on the ephemeral execution host.
The emitted status has no raw log lines, paths, rate rows or private inputs.
Unrecognized solver output yields UNKNOWN progress, never fabricated steps.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Sequence

# Only observed step numbers are reported, not the surrounding solver text.
STEP_PATTERN = re.compile(
    r"(?im)^\s*time\s*step\s*[:#]?\s*(\d{1,6})"
    r"(?:\s*[,;:]\s*time\s*=\s*([0-9.eE+-]+))?"
)
PROGRESS_CAP = 460
MB = 1024 * 1024
CPU_PERCENT = re.compile(r"^(\d{1,5}(?:\.\d{1,2})?)%$")
MEMORY_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(B|KiB|MiB|GiB|TiB)$")
MEM_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2,
             "GiB": 1024**3, "TiB": 1024**4}


def parse_step_progress(text: str) -> dict[str, int | float | None]:
    max_step: int | None = None
    max_time: float | None = None
    for match in STEP_PATTERN.finditer(text):
        step = int(match.group(1))
        if not 0 <= step <= PROGRESS_CAP:
            continue
        max_step = step if max_step is None else max(max_step, step)
        if match.group(2):
            try:
                time_value = float(match.group(2))
            except ValueError:
                continue
            if 0 <= time_value <= 1e-4 * (1 + 1e-6):
                max_time = time_value if max_time is None else max(max_time, time_value)
    return {"last_reported_step": max_step, "last_reported_time_seconds": max_time}


def read_progress_tail(log: Path) -> dict[str, int | float | None]:
    if not log.is_file():
        return {"last_reported_step": None, "last_reported_time_seconds": None}
    with log.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - 2 * MB))
        raw = handle.read(2 * MB)
    if size > 2 * MB:
        raw = raw.partition(b"\n")[2]  # discard partial leading line
    return parse_step_progress(raw.decode("utf-8", errors="replace"))


def _pct(text: str) -> float | None:
    match = CPU_PERCENT.fullmatch(text.strip())
    return float(match.group(1)) if match else None


def _memory_bytes(text: str) -> int | None:
    match = MEMORY_RE.fullmatch(text.strip())
    if not match:
        return None
    return round(float(match.group(1)) * MEM_UNITS[match.group(2)])


def docker_resources(container_name: str) -> dict[str, int | float | None]:
    if not re.fullmatch(r"issue493-p3-(417|941)-[bc]", container_name):
        raise ValueError("INVALID_MONITOR_CONTAINER_NAME")
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{.CPUPerc}}|{{.MemUsage}}", container_name],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {"cpu_percent": None, "memory_bytes": None}
    if result.returncode != 0:
        return {"cpu_percent": None, "memory_bytes": None}
    pieces = result.stdout.strip().split("|")
    if len(pieces) != 2:
        return {"cpu_percent": None, "memory_bytes": None}
    used = pieces[1].split("/")[0].strip()
    return {"cpu_percent": _pct(pieces[0]), "memory_bytes": _memory_bytes(used)}


def _stop_container(name: str, proc: subprocess.Popen[Any]) -> None:
    try:
        subprocess.run(["docker", "rm", "-f", name], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        pass


def _emit_heartbeat(case: str, variant: str, state: dict[str, Any]) -> None:
    fields = {
        "event": "PUBLIC_P3_HEARTBEAT",
        "case": case, "variant": variant,
        "elapsed_seconds": state["elapsed_seconds"],
        "last_reported_step": state["last_reported_step"],
        "last_reported_time_seconds": state["last_reported_time_seconds"],
        "cpu_percent": state["cpu_percent"],
        "memory_bytes": state["memory_bytes"],
    }
    print(__import__("json").dumps(fields, sort_keys=True), flush=True)


def monitor_solver(command: Sequence[str], *, cwd: Path, log: Path,
                   case: str, variant: str, timeout_seconds: int,
                   heartbeat_seconds: int = 60) -> dict[str, Any]:
    """Run the process and monitor bounded telemetry; never publish its raw logs."""
    if timeout_seconds < 1 or heartbeat_seconds < 1:
        raise ValueError("NONPOSITIVE_EXECUTION_BUDGET")
    if case not in {"417", "941"} or variant not in {"B", "C"}:
        raise ValueError("UNRECOGNIZED_DIAGNOSTIC_CASE")
    if log.exists():
        raise ValueError("P3_LOG_ALREADY_EXISTS")
    name = f"issue493-p3-{case}-{variant.lower()}"
    start = time.monotonic()
    last: dict[str, Any] = {
        "last_reported_step": None, "last_reported_time_seconds": None,
        "cpu_percent": None, "memory_bytes": None,
    }
    max_memory: int | None = None
    max_cpu: float | None = None
    heartbeat_samples = 0
    elapsed: float = 0.0
    returncode: int | None = None
    timed_out = False
    launched = False
    with log.open("x", encoding="utf-8") as sink:
        try:
            proc = subprocess.Popen(command, cwd=cwd, stdout=sink,
                                    stderr=subprocess.STDOUT)
            launched = True
        except OSError:
            elapsed = time.monotonic() - start
        else:
            try:
                while True:
                    elapsed = time.monotonic() - start
                    remaining = timeout_seconds - elapsed
                    if remaining <= 0:
                        timed_out = True
                        _stop_container(name, proc)
                        break
                    try:
                        returncode = proc.wait(timeout=min(heartbeat_seconds, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        observed = read_progress_tail(log)
                        for key in ("last_reported_step", "last_reported_time_seconds"):
                            value = observed[key]
                            if value is not None and (
                                last[key] is None or value > last[key]
                            ):
                                last[key] = value
                        last.update(docker_resources(name))
                        heartbeat_samples += 1
                        current_cpu = last["cpu_percent"]
                        if current_cpu is not None:
                            max_cpu = (current_cpu if max_cpu is None
                                       else max(max_cpu, current_cpu))
                        current_mem = last["memory_bytes"]
                        if current_mem is not None:
                            max_memory = (current_mem if max_memory is None
                                          else max(max_memory, current_mem))
                        last["elapsed_seconds"] = round(time.monotonic() - start, 2)
                        _emit_heartbeat(case, variant, last)
            finally:
                if proc.poll() is None:
                    _stop_container(name, proc)
            elapsed = time.monotonic() - start
    observed = read_progress_tail(log)
    for key in ("last_reported_step", "last_reported_time_seconds"):
        value = observed[key]
        if value is not None and (last[key] is None or value > last[key]):
            last[key] = value
    return {
        "launched": launched, "returncode": returncode,
        "timed_out": timed_out,
        "wall_seconds": round(elapsed, 3),
        "timeout_budget_seconds": timeout_seconds,
        "last_reported_step": last["last_reported_step"],
        "last_reported_time_seconds": last["last_reported_time_seconds"],
        "last_cpu_percent": last["cpu_percent"],
        "max_observed_memory_bytes": max_memory,
        "max_observed_cpu_percent": max_cpu,
        "heartbeat_samples": heartbeat_samples,
        "native_log_bytes": log.stat().st_size,
        # No exit code is invented when timeout killed the process.
        "termination": ("TIMEOUT" if timed_out else "EXIT" if launched
                        else "LAUNCH_ERROR"),
    }
