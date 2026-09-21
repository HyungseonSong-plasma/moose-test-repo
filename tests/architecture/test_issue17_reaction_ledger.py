from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_issue17_reaction_ledger.py"
LEDGER = ROOT / "docs" / "development" / "2026-09-07_issue17_r0_reaction_ledger.json"


def test_issue17_r0_reaction_ledger_invariants() -> None:
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(LEDGER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "ISSUE17_R0_REACTION_LEDGER_INVARIANTS=PASS" in completed.stdout
    assert "ISSUE17_R0_STATUS=AUDIT_IN_PROGRESS" in completed.stdout
