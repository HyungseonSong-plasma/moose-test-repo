"""Capture caller-supplied commands using only the Python standard library.

The caller owns executable selection, environment, authorization, and cleanup.
No shell, tool discovery, or implicit retry. This is not a security sandbox;
timeout controls the direct child and captured output may consume disk.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess
import tempfile


@dataclass(frozen=True, slots=True)
class CommandObservation:
    command: tuple[str, ...]
    exit_code: int | None
    stdout_sha256: str
    stderr_sha256: str
    stdout_preview: bytes
    stderr_preview: bytes
    timed_out: bool
    output_truncated: bool


def _validate_command(command: tuple[str, ...], timeout_seconds: int) -> None:
    if (not isinstance(command, tuple) or not command or not command[0]
            or any(not isinstance(arg, str) or "\0" in arg for arg in command)):
        raise ValueError("INVALID_COMMAND")
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise ValueError("INVALID_COMMAND_TIMEOUT")


def run_command_bytes(command: tuple[str, ...], *, timeout_seconds: int,
                      cwd: Path | None = None,
                      env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    """Return complete stdout/stderr; caller owns tool selection and memory budget.

    Unlike capture_command, this is for binary data that must not be truncated.
    Nonzero exit and timeout retain subprocess semantics; no retry or shell.
    None inherits the caller's environment or working directory.
    """
    _validate_command(command, timeout_seconds)
    return subprocess.run(command, cwd=cwd, env=env, shell=False,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=False, timeout=timeout_seconds)


def capture_command(command: tuple[str, ...], *, cwd: Path,
                    env: Mapping[str, str], timeout_seconds: int,
                    max_output_bytes: int) -> CommandObservation:
    """Execute exactly the supplied argv; retain hashes and bounded previews."""
    _validate_command(command, timeout_seconds)
    if not isinstance(env, Mapping) or any(
        not isinstance(k, str) or not k or "=" in k or "\0" in k
        or not isinstance(v, str) or "\0" in v for k, v in env.items()
    ):
        raise ValueError("INVALID_COMMAND_ENVIRONMENT")
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 5_000_000:
        raise ValueError("INVALID_COMMAND_OUTPUT_LIMIT")
    code, timed_out = None, False
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            result = subprocess.run(command, cwd=str(cwd), env=dict(env), shell=False,
                                    stdout=stdout_file, stderr=stderr_file,
                                    timeout=timeout_seconds, check=False)
            code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out = True

        def digest_and_preview(stream):
            stream.flush()
            stream.seek(0)
            digest = hashlib.sha256()
            preview = bytearray()
            size = 0
            for chunk in iter(lambda: stream.read(65536), b""):
                size += len(chunk)
                digest.update(chunk)
                if len(preview) < max_output_bytes:
                    preview.extend(chunk[:max_output_bytes - len(preview)])
            return digest.hexdigest(), bytes(preview), size > max_output_bytes

        out_hash, out_preview, out_large = digest_and_preview(stdout_file)
        err_hash, err_preview, err_large = digest_and_preview(stderr_file)
    return CommandObservation(command, code, out_hash, err_hash, out_preview,
                              err_preview, timed_out, out_large or err_large)


__all__ = ["CommandObservation", "capture_command", "run_command_bytes"]
