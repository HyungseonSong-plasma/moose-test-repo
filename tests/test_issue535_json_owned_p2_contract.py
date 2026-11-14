"""P0 evidence for Issue535 JSON-owned continuity bindings and Native P2 cutover.

This does not replace the four real physics-opt --check-input executions.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"


def test_binding_input_has_json_owned_species_and_no_external_state():
    source = (PILOT / "valid_bindings.i").read_text()
    assert "files = plasma_species_initial_p2.json" in source
    assert "fem_species = 'e'" in source
    assert "fvm_species = 'O2p'" in source
    assert "[Variables]" not in source
    assert "[ICs]" not in source
    assert "kernel_coverage_check = false" in source
    catalogue = json.loads((PILOT / "plasma_species_initial_p2.json").read_text())
    for species in ("e", "O2p"):
        assert catalogue["species"][species]["initial_number_density"] > 0


def test_no_legacy_baseline_merge_or_accidental_native_p3():
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert 'native --check-input -i "$PILOT/valid_bindings.i"' in runner
    assert 'native --check-input -i "$PILOT/baseline.i" "$PILOT/valid_bindings.i"' not in runner
    assert "--executable /workspace/physics_app/physics-opt" in runner
    assert "physics_app.ci.check_issue402_reaction_reduction_p2_only" in runner
    assert "PLASMA_REACTION_REDUCTION_FOUR_CASE_NATIVE_P2_PASS" in runner
    checker = (ROOT / "physics_app/ci/check_issue402_reaction_reduction_p2_only.py").read_text()
    assert 'command = [str(executable), "--check-input", "-i", path.name]' in checker
    assert '"R2_EI16"' in checker
    assert "P3=NOT_RUN" in checker


def test_missing_initial_density_negative_mutation():
    catalogue = json.loads((PILOT / "plasma_species_initial_p2.json").read_text())
    selected = ("e", "O2p")
    assert all(catalogue["species"][name].get("initial_number_density") for name in selected)
    changed = json.loads(json.dumps(catalogue))
    del changed["species"]["e"]["initial_number_density"]
    assert not all(changed["species"][name].get("initial_number_density") for name in selected)
    assert all(catalogue["species"][name].get("initial_number_density") for name in selected)
