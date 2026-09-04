"""Pytest owns the qpx-free self-tests for current canonical QPX capabilities."""
from __future__ import annotations

import pytest

from qpx_harness.analysis.stats_builder import self_test as stats_builder_self_test
from qpx_harness.moose.preflight import parser_symbol_self_test
from qpx_harness.analysis.temporal import self_test as temporal_self_test
from qpx_harness.execution.workspace import self_test as workspace_self_test
from qpx_harness.analysis.scale_audit import self_test as scale_audit_self_test
from qpx_harness.inventory.characterization import self_test as inventory_nullspace_self_test
from qpx_harness.inventory.first_linear_characterization import self_test as first_linear_self_test
from qpx_harness.execution.contract import self_test as execution_contract_self_test
from qpx_harness.dmix.characterization import self_test as dmix_equivalence_self_test
from qpx_harness.performance.runner import self_test as performance_self_test
from qpx_harness.performance.smoke import self_test as performance_smoke_self_test
from qpx_harness.analysis.performance.investigation import self_test as performance_investigation_self_test
from qpx_harness.analysis.performance.profile import self_test as performance_profile_self_test
from qpx_harness.performance.probes.transport import self_test as performance_transport_probe_self_test
from qpx_harness.cli.commands.performance import cache_audit_self_test

ENTRYPOINTS = (
    ("analysis.stats_builder", stats_builder_self_test),
    ("moose.preflight.parser_symbols", parser_symbol_self_test),
    ("analysis.temporal", temporal_self_test),
    ("execution.workspace", workspace_self_test),
    ("analysis.scale_audit", scale_audit_self_test),
    ("inventory.characterization", inventory_nullspace_self_test),
    ("inventory.first_linear_characterization", first_linear_self_test),
    ("execution.contract", execution_contract_self_test),
    ("dmix.characterization", dmix_equivalence_self_test),
    ("performance.runner", performance_self_test),
    ("performance.smoke", performance_smoke_self_test),
    ("analysis.performance.investigation", performance_investigation_self_test),
    ("analysis.performance.profile", performance_profile_self_test),
    ("performance.probes.transport", performance_transport_probe_self_test),
    ("cli.performance.cache_audit", cache_audit_self_test),
)


@pytest.mark.parametrize("name,selftest", ENTRYPOINTS, ids=[name for name, _ in ENTRYPOINTS])
def test_qpx_free_selftest_entrypoints(name: str, selftest) -> None:
    assert selftest() == 0, name
