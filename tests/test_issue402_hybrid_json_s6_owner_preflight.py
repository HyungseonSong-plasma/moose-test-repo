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
from chemistry.prepare_hybrid_json_s6 import PINNED_INITIAL_LOG, prepare
from chemistry.prepare_s6_run_input import canonicalize_staged_electron_lookup


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
    assert set(report["changed_staged_layers"]) == {
        names[0], names[-1]
    }
    assert report["native_owner_preservation"] == (
        "ALL_NON_GENERATED_PHYSICS_INPUTS_UNCHANGED"
    )
    data = json.loads((stage / "hybrid_s6_transport.json").read_text())
    assert set(data["species"]) == {"e", "O2p", "Om", "Op"}
    assert data["species"]["e"]["transport_coef"] == "lookup"
    assert data["species"]["e"]["energy_transport_coef"] == "fluid"
    assert data["species"]["e"]["table_units"] == "reduced"
    assert data["species"]["e"]["bounds_policy"] == "clamp"
    assert data["species"]["O2p"]["mobility"] == "ion_mobility"
    assert all(data["species"][name]["initial_number_density"] > 0
               for name in ("e", "O2p", "Om", "Op"))
    base = (stage / names[0]).read_text()
    assert "[log_e_energy]" not in base
    assert "[electron_transport]" not in base
    assert "[energy_time]" not in base
    for native in ("[potential]", "[phi_diffusion]", "[phi_source]",
                   "[sigma_surface_current]", "[electron_wall_flux]",
                   "[ion_molar_density]", "[ni_time]"):
        assert native in base and native in original
    for name in names[1:-1]:
        assert (stage / name).read_text() == "# Historical untouched Native layer\n"
    overlay = (stage / names[-1]).read_text()
    assert "hybrid_s6_transport.json" in overlay
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
    assert not (stage / "hybrid_s6_transport.json").exists()
