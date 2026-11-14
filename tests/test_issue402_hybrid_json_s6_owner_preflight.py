"""Reproduce the real S6 source-owner cutover before an expensive native build.

This P0 test uses the frozen, prebuilt C0 native base and the exact archived
electron-lookup conversion. No private rate files and no solver are required.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import pytest

PILOT = Path(__file__).resolve().parents[1] / "experiments/Issue402_plasma_dsl_g1"
sys.path.insert(0, str(PILOT))
from chemistry.prepare_hybrid_json_s6 import (
    PINNED_INITIAL_LOG, NATIVE_COEFFICIENT_RENAME, prepare
)
from chemistry.prepare_s6_run_input import (
    canonicalize_staged_electron_lookup, canonicalize_staged_wall_inputs
)


def canonical_staged_base() -> str:
    """Reproduce exactly the relevant old C/D type and state name migrations."""
    original = (PILOT / "native/s6_c0_physics_base_no_d1.i").read_text()
    replacements = {
        "log_ne": "log_e",
        "log_ni": "log_O2p",
        "log_nm": "log_Om",
        "log_nop": "log_Op",
        "log_energy": "log_e_energy",
        "mean_en_solved": "e_energy_eV",
        "PhysicsElectronMeanEnergyMaterial": "ElectronEnergyMaterial",
        "PhysicsFEMLogMolarTimeDerivative": "FEMLogMolarTimeDerivative",
        "PhysicsFEMLogMolarDriftDiffusion": "FEMLogMolarDriftDiffusion",
        "PhysicsFEMLogMolarElectronJouleHeating": "FEMLogMolarElectronJouleHeating",
    }
    converted, owner = canonicalize_staged_electron_lookup(
        {Path("synthetic_canonical_s6_base.i"): original}
    )
    assert owner["to_type"] == "DDTransportMaterial"
    converted, wall = canonicalize_staged_wall_inputs(converted)
    assert wall["owner_count"] == 4
    source = converted[Path("synthetic_canonical_s6_base.i")]
    for old, new in replacements.items():
        source = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(old) +
                        r"(?![A-Za-z0-9_])", new, source)
    return source


def prepare_scratch(tmp_path: Path, case: str, *,
                    damage_energy_ic: bool = False) -> tuple[Path, list[str], str]:
    stage = tmp_path / "experiments" / "Issue395_powered_chemistry_ladder"
    stage.mkdir(parents=True)
    source = canonical_staged_base()
    if damage_energy_ic:
        source = source.replace(
            "initial_condition = -18.829829186913098",
            "initial_condition = -18.829829186913097",
            1,
        )
    names = ["synthetic_canonical_s6_base.i"] + [
        f"unused_native_layer_{i}.i" for i in range(1, 10)
    ] + ["migrated_continuity.i"]
    (stage / names[0]).write_text(source)
    for name in names[1:-1]:
        (stage / name).write_text("# Historical untouched Native layer\n")
    (stage / names[-1]).write_text(
        (PILOT / f"s6_{case}_chemistry_run.template.i").read_text()
    )
    (stage / "chemistry").mkdir()
    for file in ("oxygen_s6_common.json", f"oxygen_s6_{case}.json"):
        (stage / "chemistry" / file).write_bytes(
            (PILOT / "chemistry" / file).read_bytes()
        )
    table = stage.parent / "Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
    table.parent.mkdir(parents=True)
    table.write_text("# public transport fixture path presence (not a solver table)\n")
    return stage, names, source


@pytest.mark.parametrize("case", ["417", "941"])
def test_approved_hybrid_owner_cutover_is_exact_and_native_fallback_untouched(
    tmp_path: Path, case: str
) -> None:
    stage, names, original = prepare_scratch(tmp_path, case)
    assert PINNED_INITIAL_LOG["log_e_energy"] == "-18.829829186913098"
    assert isinstance(PINNED_INITIAL_LOG["log_e_energy"], str)
    report = prepare(stage, names, case)
    assert report["removed_generated_owner_count"] == 10
    assert report["integrated_mechanism_json"] == f"unified_s6_{case}.json"
    assert report["integrated_species_count"] == 7
    assert report["integrated_reaction_count"] == 8
    rename = report["native_species_coefficient_binding_migration"]
    assert rename["old_to_species_names"] == NATIVE_COEFFICIENT_RENAME
    assert rename["physics_equations_unchanged"] is True
    assert rename["constant_values_unchanged"] is True
    assert all(v >= 2 for v in rename["substitution_counts"].values())
    assert report["rebound_native_sheath_bc_count"] == 8
    assert sum(x["new_type"] == "FEMElectronSheathBC"
               for x in report["rebound_native_sheath_bcs"]) == 4
    assert sum(x["new_type"] == "FEMElectronEnergySheathBC"
               for x in report["rebound_native_sheath_bcs"]) == 4
    assert set(report["changed_staged_layers"]) == {
        names[0], names[-1]
    }
    assert report["native_owner_preservation"] == (
        "NATIVE_EQUATIONS_UNCHANGED_WITH_SPECIES_CANONICAL_COEFFICIENT_BINDINGS"
    )
    data = json.loads((stage / f"unified_s6_{case}.json").read_text())
    assert set(data) == {"species", "equations", "reactions"}
    assert set(data["species"]) == {"e", "O2", "O", "O2p", "Om", "Op", "O2a"}
    assert set(data["equations"]) == {
        "EI-02", "EI-17", "EI-415", "EI-401", "EI-407", "EI-2069",
        "H25", f"EI-{case}",
    }
    assert len(data["reactions"]) == len(data["equations"]) == 8
    assert [reaction["id"] for reaction in data["reactions"]][-1] == f"EI-{case}"
    assert data["species"]["e"]["transport_coef"] == "lookup"
    assert data["species"]["e"]["energy_transport_coef"] == "fluid"
    assert data["species"]["e"]["table_units"] == "reduced"
    assert data["species"]["e"]["bounds_policy"] == "clamp"
    for species in ("O2p", "Om", "Op"):
        assert data["species"][species]["transport_coef"] == "functor"
        assert data["species"][species]["mobility"] == f"{species}_mobility"
        assert data["species"][species]["diffusivity"] == f"{species}_diffusivity"
    assert all(data["species"][name]["initial_number_density"] > 0
               for name in ("e", "O2p", "Om", "Op"))
    assert report["hybrid_json_sha256"] == report["integrated_json_source_sha256"]
    base = (stage / names[0]).read_text()
    assert "[log_e_energy]" not in base
    assert "[electron_transport]" not in base
    assert "[energy_time]" not in base
    assert base.count("type = FEMElectronSheathBC") == 4
    assert base.count("type = FEMElectronEnergySheathBC") == 4
    assert "PhysicsFEMLogMolarElectronFieldLimitedFluxBC" not in base
    assert "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC" not in base
    assert "wall_number_flux = e_wall_number_flux" in base
    assert "prop_names = 'p_fixed T_g_fixed O2p_mobility O2p_diffusivity Om_mobility Om_diffusivity Op_mobility Op_diffusivity carrier_one'" in base
    assert "prop_values = '1.333223684 300 10 0.25851999786435537 10 0.25851999786435537 10 0.25851999786435537 1.0'" in base
    for original_name, canonical_name in NATIVE_COEFFICIENT_RENAME.items():
        assert original_name in original
        assert original_name not in base
        assert canonical_name in base
    assert "mobility = Op_mobility" in base
    assert "coeff = Op_diffusivity" in base
    for native in ("[potential]", "[phi_diffusion]", "[phi_source]",
                   "[sigma_surface_current]", "[electron_wall_flux]",
                   "[ion_molar_density]", "[ni_time]"):
        assert native in base and native in original
    for name in names[1:-1]:
        assert (stage / name).read_text() == "# Historical untouched Native layer\n"
    overlay = (stage / names[-1]).read_text()
    assert f"files = 'unified_s6_{case}.json'" in overlay
    assert "oxygen_s6_common.json" not in overlay
    assert "initial_molar_energy_density_eV" in overlay


def test_hybrid_rejects_changed_archived_ic_before_any_file_write(
    tmp_path: Path,
) -> None:
    stage, names, modified = prepare_scratch(
        tmp_path, "417", damage_energy_ic=True
    )
    overlay = (stage / names[-1]).read_bytes()
    with pytest.raises(ValueError, match="HYBRID_OWNER_IDENTITY_Variables_log_e_energy"):
        prepare(stage, names, "417")
    assert (stage / names[0]).read_text() == modified
    assert (stage / names[-1]).read_bytes() == overlay
    assert not (stage / "unified_s6_417.json").exists()


def test_hybrid_rejects_changed_archived_sheath_flux_before_write(tmp_path: Path):
    stage, names, original = prepare_scratch(tmp_path, "941")
    mutated = original.replace(
        "wall_number_flux = e_wall_number_flux",
        "wall_number_flux = unverified_wall_flux",
        1,
    )
    assert mutated != original
    (stage / names[0]).write_text(mutated)
    preserved_overlay = (stage / names[-1]).read_bytes()
    with pytest.raises(ValueError, match="HYBRID_SHEATH_BC_IDENTITY_"):
        prepare(stage, names, "941")
    assert (stage / names[0]).read_text() == mutated
    assert (stage / names[-1]).read_bytes() == preserved_overlay
    assert not (stage / "unified_s6_417.json").exists()


def test_hybrid_rejects_changed_native_ion_constant_before_write(tmp_path: Path):
    stage, names, original = prepare_scratch(tmp_path, "941")
    mutated = original.replace(
        "10 0.25851999786435537 10 0.25851999786435537",
        "10 0.25851999786435537 11 0.25851999786435537",
        1,
    )
    assert mutated != original
    (stage / names[0]).write_text(mutated)
    overlay = (stage / names[-1]).read_bytes()
    with pytest.raises(ValueError, match="HYBRID_NATIVE_ION_CONSTANTS_SIGNATURE_CHANGED"):
        prepare(stage, names, "941")
    assert (stage / names[0]).read_text() == mutated
    assert (stage / names[-1]).read_bytes() == overlay
    assert not (stage / "unified_s6_941.json").exists()


def test_case_reactions_are_not_cross_mixed(tmp_path: Path):
    stage, names, source = prepare_scratch(tmp_path, "417")
    swapped = (PILOT / "chemistry/oxygen_s6_941.json").read_bytes()
    (stage / "chemistry/oxygen_s6_417.json").write_bytes(swapped)
    with pytest.raises(ValueError, match="HYBRID_INTEGRATED_VARIANT_REACTION_IDENTITY_CHANGED"):
        prepare(stage, names, "417")
    assert (stage / names[0]).read_text() == source
    assert not (stage / "unified_s6_417.json").exists()
