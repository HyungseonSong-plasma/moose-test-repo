import sys
from pathlib import Path

from qpx_harness.execution.runtime import run_command


def test_run_command_timeout_is_bounded_and_reported(tmp_path: Path):
    log = tmp_path / "sleep.log"
    result = run_command(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        log_path=log,
        timeout_seconds=0.2,
    )
    assert result.returncode == 124
    assert result.timed_out is True
    assert result.wall_seconds < 3.0
