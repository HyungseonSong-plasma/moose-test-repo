"""Pytest owns the qpx-free self-tests for current canonical QPX capabilities."""
from __future__ import annotations

import pytest

from qpx_harness.analysis.stats_builder import self_test as stats_builder_self_test
from qpx_harness.adapters.moose.preflight import parser_symbol_self_test
from qpx_harness.analysis.temporal import self_test as temporal_self_test
from qpx_harness.execution.workspace import self_test as workspace_self_test
from qpx_harness.analysis.scale_audit import self_test as scale_audit_self_test
from qpx_harness.execution.contract import self_test as execution_contract_self_test
from qpx_harness.application.performance import self_test as performance_self_test
from qpx_harness.analysis.performance.profile import self_test as performance_profile_self_test

ENTRYPOINTS = (
    ("analysis.stats_builder", stats_builder_self_test),
    ("moose.preflight.parser_symbols", parser_symbol_self_test),
    ("analysis.temporal", temporal_self_test),
    ("execution.workspace", workspace_self_test),
    ("analysis.scale_audit", scale_audit_self_test),
    ("execution.contract", execution_contract_self_test),
    ("application.performance", performance_self_test),
    ("analysis.performance.profile", performance_profile_self_test),
)


@pytest.mark.parametrize("name,selftest", ENTRYPOINTS, ids=[name for name, _ in ENTRYPOINTS])
def test_qpx_free_selftest_entrypoints(name: str, selftest) -> None:
    assert selftest() == 0, name
