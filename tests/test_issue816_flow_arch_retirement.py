"""#816 legacy FLOW/ARCH positive P2 retirement and mutation regressions."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ci/guards/issue816_flow_arch_retirement_p0.py"
spec = importlib.util.spec_from_file_location("issue816_flow_arch_p0", SCRIPT)
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


def test_retired_flow_arch_current_scope_and_archives():
    guard.validate(*guard.load())


def test_retired_flow_arch_negative_mutations():
    guard.self_test()
