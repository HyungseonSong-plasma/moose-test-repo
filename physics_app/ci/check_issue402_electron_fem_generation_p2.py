#!/usr/bin/env python3
"""P2 construction gate for Issue402's two JSON-owned electron FEM equations.

Only the electron continuity/energy owner graph and its Chemistry/BC
connections are in scope. Synthetic public rate-table bytes replace private
S6 rate files, preserving reaction definitions and all eight electron BCs.
An exact-head physics-opt is mandatory; --check-input is NOT a timestep.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import check_issue402_dd_json_plasma_boundary_p2 as source


def main(executable: Path, receipt: Path) -> None:
    assert executable.is_file() and executable.stat().st_size > 0
    assert not receipt.exists(), "Refusing to overwrite electron P2 evidence"
    assert "[Continuity]" in source.S6_SYNTHETIC_INPUT
    assert "[Energy]" in source.S6_SYNTHETIC_INPUT
    assert "[log_e]" not in source.S6_SYNTHETIC_INPUT
    assert "[log_e_energy]" not in source.S6_SYNTHETIC_INPUT
    assert "fem_potential = potential" in source.S6_SYNTHETIC_INPUT
    checks: list[str] = []

    def verify(root: Path, name: str, deck: str, data: dict,
               valid: bool, diagnostic: str | None = None, *,
               data_filename: str = "dd_plasma_boundary_json_p2.json") -> None:
        source.check(executable, root, name, deck, data, valid, diagnostic,
                     data_filename=data_filename)
        checks.append(name)

    with TemporaryDirectory(prefix="issue402_electron_only_") as temporary:
        root = Path(temporary)
        verify(root, "ELECTRON_CONTINUITY_ENERGY_JSON_P2",
               source.PHYSICS_AUTO_INPUT, source.DATA, True)
        verify(root, "EI415_CHEMISTRY_BOTH_ELECTRON_RHS_P2",
               source.KINETIC_INPUT, source.KINETIC_DATA, True)
        # The human-reviewable decks and synthetic JSON must remain an exact
        # materialization of the proven generator, never hand-edited physics.
        s6_inputs: dict[str, tuple[str, dict, str]] = {}
        for variant in ("417", "941"):
            stem = f"s6_{variant}_electron_fem_p2"
            json_filename = f"{stem}.json"
            deck = (source.CI / f"{stem}.i").read_text(encoding="utf-8")
            data = json.loads((source.CI / json_filename).read_text(encoding="utf-8"))
            assert data == source.synthetic_s6(variant), (
                f"{stem}: materialized JSON differs from source S6 transformation")
            expected = source.S6_SYNTHETIC_INPUT.replace(
                "    files = dd_plasma_boundary_json_p2.json\n",
                f"    files = {json_filename}\n", 1
            ).replace(
                "# GeneratedMesh sideset mapping: left=wafer, bottom=cover, right=inlet, top=outlet.",
                f"# S6-{variant} P2 synthetic sidesets: left=electrode/metal/right, bottom=cover,\n"
                "# right=wafer, top=focus_ring. No private EI rates or physical P3 solve.", 1
            )
            assert deck == expected, f"{stem}: materialized .i differs from Native P2"
            assert "[Continuity]" in deck and "[Energy]" in deck
            assert "[log_e]" not in deck and "[log_e_energy]" not in deck
            bc = [entry for group in data["boundaries"].values()
                  for entry in group["bcs"].values()]
            assert len(bc) == 8
            assert all(entry["wall_number_flux"] == "e_wall_number_flux"
                       for entry in bc)
            assert len(data["reactions"]) == 8
            assert data["species"]["e"]["transport_coef"] == "lookup"
            assert data["species"]["e"]["table_units"] == "reduced"
            assert data["species"]["e"]["table_file"] == "plasma_closures_transport_table.txt"
            s6_inputs[variant] = (deck, data, json_filename)
            verify(root, f"S6_{variant}_TWO_EQUATIONS_EIGHT_REACTIONS_EIGHT_BCS",
                   deck, data, True, data_filename=json_filename)

        # Preserve the same S6-417 .i when testing a missing table: only
        # the companion synthetic JSON is mutated. The gate must fail closed.
        deck_417, data_417, json_417 = s6_inputs["417"]
        missing_electron_transport_table = copy.deepcopy(data_417)
        missing_electron_transport_table["species"]["e"]["table_file"] = (
            "missing_electron_transport_lookup.txt")
        verify(root, "MISSING_ELECTRON_TRANSPORT_LOOKUP_REJECTED",
               deck_417, missing_electron_transport_table, False,
               data_filename=json_417)

        missing_initial = copy.deepcopy(source.DATA)
        del missing_initial["species"]["e"]["initial_number_density"]
        verify(root, "MISSING_ELECTRON_JSON_INITIAL_REJECTED",
               source.PHYSICS_AUTO_INPUT, missing_initial, False,
               "requires species.e.initial_number_density")
        no_transport = copy.deepcopy(source.DATA)
        del no_transport["species"]["e"]["transport_coef"]
        del no_transport["species"]["e"]["mobility"]
        del no_transport["species"]["e"]["diffusivity"]
        verify(root, "MISSING_ELECTRON_TRANSPORT_REJECTED",
               source.PHYSICS_AUTO_INPUT, no_transport, False)
        missing_energy_model = copy.deepcopy(source.DATA)
        del missing_energy_model["species"]["e"]["energy_transport_coef"]
        verify(root, "MISSING_ELECTRON_ENERGY_FLUID_REJECTED",
               source.PHYSICS_AUTO_INPUT, missing_energy_model, False)
        no_table = copy.deepcopy(source.KINETIC_DATA)
        no_table["reactions"][0]["table"] = "nonexistent_lookup.txt"
        verify(root, "MISSING_EI_LOOKUP_REJECTED",
               source.KINETIC_INPUT, no_table, False, "table cannot be opened")
        double_rate = copy.deepcopy(source.KINETIC_DATA)
        double_rate["reactions"][0]["rate"] = {
            "model": "constant", "A": 1.0, "basis": "molar"
        }
        verify(root, "DUPLICATE_RATE_OWNER_REJECTED",
               source.KINETIC_INPUT, double_rate, False,
               "table requires an EI volume reaction without rate")
        no_energy_deck = source.PHYSICS_AUTO_INPUT.replace(
            "        [Energy]\n          fem_species = e\n"
            "          fem_potential = potential\n"
            "          initial_molar_energy_density_eV = 8.3e-9\n"
            "        []\n", "", 1)
        assert no_energy_deck != source.PHYSICS_AUTO_INPUT
        verify(root, "ENERGY_SHEATH_WITHOUT_ENERGY_REJECTED",
               no_energy_deck, source.DATA, False,
               "JSON FEMElectronEnergySheathBC requires")
        duplicate_time = source.PHYSICS_AUTO_INPUT.replace(
            "[Executioner]\n",
            "[Kernels]\n"
            "  [native_duplicate_e_time]\n"
            "    type = FEMLogMolarTimeDerivative\n"
            "    variable = log_e\n"
            "  []\n"
            "[]\n"
            "[Executioner]\n", 1)
        assert duplicate_time != source.PHYSICS_AUTO_INPUT
        verify(root, "DUPLICATE_ELECTRON_TIME_KERNEL_REJECTED",
               duplicate_time, source.DATA, False,
               "must have exactly one owner")

    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({
        "schema": "issue402.electron_fem_generation.native_p2.v1",
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                               text=True).strip(),
        "binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "checked_cases": checks,
        "cases_count": len(checks),
        "source": "JSON and MOOSE input; synthetic public lookup bytes",
        "P2": "PASS",
        "P3": "NOT_RUN",
        "P4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }, indent=2, sort_keys=True) + "\n")
    print("ISSUE402_ELECTRON_CONTINUITY_ENERGY_JSON_NATIVE_P2_PASS "
          "P3_NOT_RUN SCIENCE_HOLD", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_issue402_electron_fem_generation_p2.py "
                         "/path/to/physics-opt /path/to/receipt.json")
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
