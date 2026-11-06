"""Offline contract checks for the Issue471 runtime comparison; no native PASS claim."""
from __future__ import annotations

from experiments.Issue471_ad_parser_runtime.diagnose_closure import (
    BASE, IMAGE, MODES, build_command, original_command, verdict,
)


def test_same_five_minimal_controls_as_previous_native_reproducer(tmp_path) -> None:
    assert MODES == (
        "mini_base", "mini_generic", "mini_ad",
        "mini_ad_jitoff", "mini_nested_jitoff",
    )
    assert IMAGE.startswith("ghcr.io/hyungseonsong-plasma/physics-runtime@sha256:")
    assert BASE.startswith("ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:")
    original = original_command(tmp_path, ["--check-input", "-i", "input.i"])
    rebuilt = build_command(tmp_path, tmp_path, ["--check-input", "-i", "input.i"])
    assert "--network" in original and "none" in original
    assert "--network" in rebuilt and "none" in rebuilt
    assert IMAGE in original and BASE in rebuilt
    assert "/opt/physics/physics-opt" in rebuilt[-3]
    assert "input.i" in rebuilt


def test_incomparable_or_missing_positive_controls_fail_closed() -> None:
    assert verdict({"runs": {}}) == "INCONCLUSIVE_SCRATCH_CONTROLS"
    old = {
        "mini_base": {"p2": 0, "p3": 0},
        "mini_generic": {"p2": 0, "p3": 0},
        "mini_ad": {"p2": 1, "p3": None},
        "mini_ad_jitoff": {"p2": 0, "p3": 139},
    }
    assert verdict({"runs": {"scratch": old, "build_base_with_original_binary": {"status": "INCOMPARABLE"}}}) == "INCONCLUSIVE_BUILD_BASE_LOADER"


def test_restored_build_environment_does_not_imply_scientific_pass() -> None:
    old = {
        "mini_base": {"p2": 0, "p3": 0},
        "mini_generic": {"p2": 0, "p3": 0},
        "mini_ad": {"p2": 1, "p3": None},
        "mini_ad_jitoff": {"p2": 0, "p3": 139},
    }
    base = {name: {"p2": 0, "p3": 0} for name in MODES}
    assert verdict({"runs": {"scratch": old, "build_base_with_original_binary": base}}) == (
        "BUILD_ENV_RESTORED_PATH__LIBRARY_IDENTITY_AUDIT_REQUIRED"
    )
    base["mini_ad"]["p2"] = 1
    base["mini_ad"]["p3"] = None
    assert verdict({"runs": {"scratch": old, "build_base_with_original_binary": base}}) == (
        "BUILD_ENV_AD_STILL_UNRESOLVED"
    )
