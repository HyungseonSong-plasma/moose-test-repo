"""Regression: distinguish restart-local native steps from absolute simulation time.

Uses only the historical Oxygen14 SOURCE verifier; no native runtime, network,
checkpoint, secret rates, or scientific-validation promotion.
"""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "experiments" / "Issue395_powered_chemistry_ladder" / "base14_restart_100to300us.py"


def load_module():
    spec = importlib.util.spec_from_file_location("base14_restart_contract", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_research_base_contract_is_pinned():
    m = load_module()
    assert len(set(m.REQUIRED_CHANNELS)) == 14
    assert m.UPSTREAM_RUN == 42049066748
    assert (m.START_NS, m.END_NS, m.CAP_NS) == (100000, 300000, 1000)
    assert m.RECORD_SHA == "bc1193d3d86ceed929031e28ee832bef8ae2a43a"


def test_restarted_native_counter_and_absolute_time():
    m = load_module()
    evidence = "Time Step 0, time = 0.0001\nTime Step 1, time = 0.000100001\nTime Step 219, time = 0.0003\n"
    assert m.native_restart_progress(evidence) == (219, 3e-4)


@pytest.mark.parametrize("evidence", [
    "",
    "Time Step 0, time = 0.0001\nTime Step 0, time = 0.0003\n",
    "Time Step 460, time = 0.0001\nTime Step 461, time = 0.0003\n",
    "Time Step 0, time = 0.0\nTime Step 219, time = 0.0003\n",
    "Time Step 0, time = 0.0001\nTime Step 219, time = 0.00025\n",
    "Time Step 0, time = 0.0001\nTime Step 2, time = 0.0002\nTime Step 1, time = 0.0003\n",
])
def test_invalid_native_evidence_remains_rejected(evidence):
    m = load_module()
    with pytest.raises(ValueError):
        m.native_restart_progress(evidence)
