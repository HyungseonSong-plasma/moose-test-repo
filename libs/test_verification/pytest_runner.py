"""Run explicitly authorized pytest code in a caller-prepared workspace.

This is not a security sandbox. The caller owns trusted test selection,
workspace creation, source identity, cleanup, and acceptance decisions.
Output preview is bounded; full captured output is written to temporary disk.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


@dataclass(frozen=True, slots=True)
class PytestRun:
    command: tuple[str, ...]
    exit_code: int | None
    passed_tests: int
    stdout_sha256: str
    stderr_sha256: str
    timed_out: bool
    output_truncated: bool
    junit_xml: bytes
    junit_sha256: str


def run_pytest(path: str, workspace: Path, home: Path, timeout_seconds: int,
               max_output_bytes: int, junit_destination: Path) -> PytestRun:
    """Execute one caller-selected relative pytest module; report observations."""
    if (not isinstance(path, str) or not path or path.startswith("-")
            or Path(path).is_absolute() or ".." in Path(path).parts
            or not path.endswith(".py")):
        raise ValueError("INVALID_PYTEST_TARGET")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
        raise ValueError("INVALID_REPLAY_TIMEOUT")
    if type(max_output_bytes) is not int or not 1024 <= max_output_bytes <= 5_000_000:
        raise ValueError("INVALID_REPLAY_OUTPUT_LIMIT")
    if junit_destination.exists() or junit_destination.is_symlink():
        raise ValueError("PYTEST_JUNIT_DESTINATION_ALREADY_EXISTS")
    command = (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
               "--disable-warnings", "--junitxml=" + str(junit_destination), path)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "PYTHONPATH": str(workspace),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_ADDOPTS": "",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    timed_out = False
    code = None
    # Store captured test output on disk, not in an unbounded process memory
    # buffer. Hash full content and retain only a bounded pytest summary view.
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            p = subprocess.run(command, cwd=str(workspace), env=env, shell=False,
                               stdout=stdout_file, stderr=stderr_file,
                               timeout=timeout_seconds, check=False)
            code = p.returncode
        except subprocess.TimeoutExpired:
            timed_out = True

        def digest_and_preview(stream):
            stream.flush()
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(0)
            digest = hashlib.sha256()
            preview = bytearray()
            for chunk in iter(lambda: stream.read(65536), b""):
                if not chunk:
                    break
                digest.update(chunk)
                if len(preview) < max_output_bytes:
                    preview.extend(chunk[:max_output_bytes - len(preview)])
            return digest.hexdigest(), bytes(preview), size > max_output_bytes

        out_hash, out_preview, out_large = digest_and_preview(stdout_file)
        err_hash, _, err_large = digest_and_preview(stderr_file)
    output_truncated = out_large or err_large
    count = 0
    if code == 0 and not output_truncated:
        match = re.search(rb"(?<!\d)(\d+) passed(?:\s|\b)", out_preview)
        count = int(match.group(1)) if match else 0
    junit = b""
    if junit_destination.is_file():
        with junit_destination.open("rb") as xml:
            junit = xml.read(8_000_001)
    return PytestRun(command, code, count, out_hash, err_hash,
                     timed_out, output_truncated, junit,
                     hashlib.sha256(junit).hexdigest() if junit else "")


__all__ = ["PytestRun", "run_pytest"]
