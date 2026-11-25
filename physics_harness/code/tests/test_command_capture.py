"""Synthetic controls for tool-independent process capture."""
import hashlib
import os
import sys

import pytest

from libs.command_execution.runner import capture_command


def test_command_captures_complete_hash_and_bounded_previews(tmp_path):
    argv = (sys.executable, "-c", "import sys;sys.stdout.write('abcdef');sys.stderr.write('xyz')")
    result = capture_command(argv, cwd=tmp_path, env=dict(os.environ),
                             timeout_seconds=10, max_output_bytes=4)
    assert result.command == argv and result.exit_code == 0
    assert result.stdout_preview == b"abcd" and result.stderr_preview == b"xyz"
    assert result.stdout_sha256 == hashlib.sha256(b"abcdef").hexdigest()
    assert result.stderr_sha256 == hashlib.sha256(b"xyz").hexdigest()
    assert result.output_truncated and not result.timed_out


def test_command_preserves_nonzero_exit(tmp_path):
    result = capture_command((sys.executable, "-c", "raise SystemExit(7)"),
                             cwd=tmp_path, env=dict(os.environ),
                             timeout_seconds=10, max_output_bytes=1024)
    assert result.exit_code == 7 and not result.timed_out


def test_command_timeout_is_not_success(tmp_path):
    result = capture_command((sys.executable, "-c", "import time;time.sleep(20)"),
                             cwd=tmp_path, env=dict(os.environ),
                             timeout_seconds=1, max_output_bytes=1024)
    assert result.timed_out and result.exit_code is None


def test_command_rejects_non_argv_input(tmp_path):
    with pytest.raises(ValueError, match="INVALID_COMMAND"):
        capture_command("echo hello", cwd=tmp_path, env={}, timeout_seconds=1,
                        max_output_bytes=1024)


def test_full_binary_command_result_is_not_a_preview(tmp_path):
    import sys
    from libs.command_execution.runner import run_command_bytes

    result = run_command_bytes(
        (sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 5000001); sys.stderr.buffer.write(b'err'); sys.exit(3)"),
        cwd=tmp_path, timeout_seconds=30,
    )
    assert result.returncode == 3
    assert result.stdout == b"x" * 5000001
    assert result.stderr == b"err"
