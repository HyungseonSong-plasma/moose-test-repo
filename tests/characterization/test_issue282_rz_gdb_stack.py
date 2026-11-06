"""Offline exact-input characterization of the Track A stack-trace experiment.

The tests do not launch any backend or grant Physics #282 science acceptance.
"""
from __future__ import annotations

import pytest

from experiments.Issue282_e2a_rz_bridge.diagnose_gdb_stack import (
    CASES,
    IMAGE,
    INPUT_SHA256,
    MESH_SHA256,
    debug_dockerfile,
    debug_gdb_command,
    docker_entrypoint,
    sha256,
)
from experiments.Issue282_e2a_rz_bridge.diagnose_segv import make_case


def test_gdb_contract_is_exact_and_nonpackaging() -> None:
    assert CASES == ("r4_qf1_predecessor", "e2a_zero_diffusion")
    assert len(INPUT_SHA256) == len(CASES)
    assert IMAGE.startswith("ghcr.io/hyungseonsong-plasma/physics-runtime@sha256:")
    assert "FROM " + IMAGE in debug_dockerfile()
    assert "FROM ubuntu:24.04 AS debugger" in debug_dockerfile()
    assert "COPY --from=debugger / /opt/physics282_debugroot/" in debug_dockerfile()
    assert "USER 0" in debug_dockerfile()
    assert "gdb" in debug_dockerfile()
    assert debug_gdb_command("--version")[-1] == "--version"
    assert debug_gdb_command("--version")[0] == "--entrypoint"
    assert "lib/x86_64-linux-gnu/ld-linux-x86-64.so.2" in debug_gdb_command("--version")[1]
    assert "sol-adapter-moose" not in debug_dockerfile()
    assert len(MESH_SHA256) == 64


@pytest.mark.parametrize("name", CASES)
def test_the_exact_historical_rz_projected_input_is_preserved(tmp_path, name: str) -> None:
    case_dir = tmp_path / name
    evidence = make_case(case_dir, name)
    assert evidence["automatic_scaling_enabled"] is False
    assert evidence["JIT_enabled"] is False
    assert evidence["not_scientific_parity"] is True
    assert sha256(case_dir / "input.i") == INPUT_SHA256[name]
    assert sha256(case_dir / "qvt.msh") == MESH_SHA256
    historical = (case_dir / "input.historical.i").read_text(encoding="utf-8")
    projected = (case_dir / "input.i").read_text(encoding="utf-8")
    assert historical != projected
    assert "automatic_scaling = false" in projected


def test_invalid_image_entrypoint_fails_closed() -> None:
    assert docker_entrypoint({"Config": {"Entrypoint": ["/usr/bin/physics-opt"]}}) == [
        "/usr/bin/physics-opt"
    ]
    with pytest.raises(ValueError, match="no explicit"):
        docker_entrypoint({"Config": {"Entrypoint": None}})
    with pytest.raises(ValueError, match="shell entrypoint"):
        docker_entrypoint({"Config": {"Entrypoint": ["/bin/sh", "-c", "physics-opt"]}})
