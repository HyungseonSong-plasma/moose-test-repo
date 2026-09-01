"""Characterization owner for Issue31 EVR1 runtime composition."""
from __future__ import annotations

import tempfile
from pathlib import Path

from recipes import issue31_coupling as recipe

from .classification import preliminary_classification
from .orchestration import _create_root


def self_test() -> int:
    try:
        base = """
[Variables]
  [n_e_solved]
  []
  [potential_plasma]
  []
[]
[FunctorMaterials]
  [r30_charge_density]
  []
[]
[FVKernels]
  [r30_e_time]
  []
  [r30_e_diffusion]
  []
  [r30_phi_diffusion]
  []
  [r30_phi_charge_source]
  []
[]
[FVBCs]
  [r30_phi_plasma_metal]
  []
  [r30_phi_plasma_electrode]
  []
  [r30_phi_plasma_right]
  []
  [r30_phi_inlet]
  []
  [r30_phi_outlet]
  []
[]
[Postprocessors]
  [r29_phi_min]
  []
  [r29_phi_max]
  []
  [r29_phi_integral]
  []
[]
"""
        transformed, meta = recipe.transport_only_input(base)
        if "potential_plasma" in transformed:
            raise AssertionError("recipe transform left potential_plasma")
        if len(meta["removed_paths"]) != len(recipe.TRANSPORT_REMOVE_PATHS):
            raise AssertionError("recipe transform removal count drift")

        transport = {
            "benchmark": {
                "validation": {"status": "P2_PASS_P3_PASS"},
                "performance": {"wall_seconds": 10.0},
            }
        }
        monolithic = {
            "benchmark": {
                "validation": {"status": "P2_PASS_P3_PASS"},
                "performance": {"wall_seconds": 15.0},
            },
            "investigation": {
                "classification": {"bottleneck_class": "PC_FACTORIZATION"}
            },
        }
        physics = {"status": "PASS"}
        decision = preliminary_classification(transport, monolithic, physics, physics)
        if decision["class"] != "MONOLITHIC_LINEAR_ALGEBRA_BOUND_CANDIDATE":
            raise AssertionError("EVR1 classifier drift")
        if decision["monolithic_to_transport_wall_ratio"] != 1.5:
            raise AssertionError("EVR1 wall-ratio drift")

        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            first = _create_root(root, timestamp="20000101T000000Z")
            second = _create_root(root, timestamp="20000101T000000Z")
            if first.name != "coupling_evr1_Issue31_20000101T000000Z":
                raise AssertionError("EVR1 root naming drift")
            if second.name != "coupling_evr1_Issue31_20000101T000000Z_01":
                raise AssertionError("EVR1 root collision policy drift")
    except Exception as exc:
        print(f"ISSUE31_EVR1_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE31_EVR1_RUNTIME_SELFTEST: PASS")
    return 0
