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


def test_p2_bridge_preserves_physical_linear_states_without_legacy_factory_mutation():
    from physics_app.ci import check_issue402_reaction_reduction_p2_only as p2

    from physics_app.ci import check_r2_o2_ionization_implementation as r2
    from physics_app.ci import check_r3_o2s_excitation_implementation as r3
    from physics_app.ci import check_e8_ei10_energy_runtime as e10
    from physics_app.ci import check_e8_ei16_energy_runtime as e16

    for original in (r2.RUNTIME_INPUT, r3.RUNTIME_INPUT, e10.RUNTIME_INPUT, e16.RUNTIME_INPUT):
        assert "state_form = physical_eV" in original
        adapted = p2._adapt_physical_mean_energy_for_p2(original)
        assert "state_form = physical_eV" not in adapted
        assert "state_form = log_molar_eV" in adapted
        assert adapted.count("type = ElectronEnergyMaterial") == 1
        assert "functor_names = 'n_e'" in adapted
        assert "functor_names = 'mean_en'" in adapted
        assert "expression = 'log(ne/6.02214076e23)'" in adapted
        assert "expression = 'log(energy/6.02214076e23)'" in adapted
        assert "property_name = issue402_p2_log_molar_e" in adapted
        assert "property_name = issue402_p2_log_molar_energy" in adapted
        # Exact reversible rewrite: every other operator, initial value,
        # rate table, source, postprocessor and solver parameter is unchanged.
        assert adapted.replace(p2._CANONICAL_P2_MEAN_BRIDGE,
                               p2._LEGACY_MEAN_BRIDGE) == original


def test_log_molar_bridge_preserves_energy_ratio_for_varying_physical_states():
    import math
    from physics_app.ci import check_issue402_reaction_reduction_p2_only as p2

    for ne, energy in (
        (1.0e16, 5.73276e16),
        (1.4e16, 6.3e16),
        (5.0e14, 8.0e15),
        (2.0e18, 4.2e18),
    ):
        log_density = math.log(ne / p2._N_A)
        log_energy = math.log(energy / p2._N_A)
        canonical = math.exp(log_energy - log_density)
        assert math.isclose(canonical, energy / ne, rel_tol=1e-13)


def test_p2_adapter_rejects_ambiguous_or_repeated_energy_owners():
    import pytest
    from physics_app.ci import check_issue402_reaction_reduction_p2_only as p2
    from physics_app.ci import check_r2_o2_ionization_implementation as r2

    with pytest.raises(ValueError, match="exactly one"):
        p2._adapt_physical_mean_energy_for_p2(
            r2.RUNTIME_INPUT.replace("state_form = physical_eV", "state_form = log_molar_eV")
        )
    with pytest.raises(ValueError, match="exactly one"):
        p2._adapt_physical_mean_energy_for_p2(r2.RUNTIME_INPUT + p2._LEGACY_MEAN_BRIDGE)
    with pytest.raises(ValueError, match="overwrite"):
        p2._adapt_physical_mean_energy_for_p2(
            r2.RUNTIME_INPUT.replace(
                "property_name = c_O2",
                "property_name = issue402_p2_log_molar_e",
            )
        )


def test_four_species_json_owned_p2_supersedes_legacy_external_variable_binding():
    # The historical manual log_* solver variable fixture remains byte-identical
    # but must not be passed to current JSON-owned Native Continuity.
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert 'native --check-input -i "$PILOT/generic_four_species.i"' not in runner
    assert 'native --check-input -i "$PILOT/species_density_pairs_p2.i"' in runner
    assert "PLASMA_GENERIC_SPECIES_STATE_NAMES_P2_PASS" in runner
    source = (PILOT / "species_density_pairs_p2.i").read_text()
    original = (PILOT / "generic_four_species.i").read_text()
    assert "files = plasma_species_initial_p2.json" in source
    assert "fem_species = e" in source
    assert "fvm_species = 'O2p Om Op'" in source
    assert "[Variables]" in source  # contains only independent potential
    assert "[potential]" in source
    assert "[log_e]" not in source
    for sid in ("e", "O2p", "Om", "Op"):
        assert f"[log_{sid}]" in original
        catalogue = json.loads((PILOT / "plasma_species_initial_p2.json").read_text())
        assert catalogue["species"][sid]["initial_number_density"] > 0
