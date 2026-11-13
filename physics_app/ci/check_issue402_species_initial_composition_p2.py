#!/usr/bin/env python3
"""Pinned-native P2 positive and fail-closed JSON species initial-composition tests.

Uses --check-input; not a numerical-science parity test.
"""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import sys


def run_case(exe: Path, work: Path, name: str, data: dict,
             *, expected_error: str | None = None,
             second: dict | None = None,
             input_rewrite=None) -> None:
    mechanism = work / f"{name}.json"
    mechanism.write_text(json.dumps(data, indent=2))
    files = mechanism.name
    if second is not None:
        extra = work / f"{name}_other.json"
        extra.write_text(json.dumps(second, indent=2))
        files += " " + extra.name

    template = Path(__file__).with_name("json_surface_rate_p2.i").read_text()
    template = template.replace(
        "files = json_surface_rate_p2.json", f"files = '{files}'"
    ).replace(
        "chemistry_file = json_surface_rate_p2.json",
        f"chemistry_file = {mechanism.name}",
    )
    if input_rewrite is not None:
        template = input_rewrite(template)
    source = work / f"{name}.i"
    source.write_text(template)
    proc = subprocess.run(
        [str(exe), "--check-input", "-i", source.name], cwd=work,
        text=True, capture_output=True, check=False,
    )
    output = proc.stdout + proc.stderr
    if expected_error is None:
        if proc.returncode != 0 or "Syntax OK" not in output:
            raise AssertionError(f"{name}: expected success: {output[-5000:]}")
    else:
        if proc.returncode == 0 or expected_error not in output:
            raise AssertionError(
                f"{name}: expected rejection containing {expected_error!r}, "
                f"rc={proc.returncode}: {output[-5000:]}"
            )
    print(f"SPECIES_COMPOSITION_NATIVE_P2_{name.upper()}_PASS")


def main():
    exe = Path(sys.argv[1]).resolve()
    base = json.loads(Path(__file__).with_name("json_surface_rate_p2.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        run_case(exe, work, "valid_distinct_volume_inlet", base)

        # A missing sccm does NOT turn off the required solved-species ICs.
        # It only turns off the inlet Dirichlet boundary condition.
        def no_sccm(text: str) -> str:
            return text.replace("    sccm = 100\\n", "").replace(
                "    inlet_boundaries = left\\n", ""
            )
        run_case(exe, work, "mandatory_ic_without_sccm", base,
                 input_rewrite=no_sccm)

        def no_inlet_sideset(text: str) -> str:
            return text.replace("    inlet_boundaries = left\\n", "")
        run_case(exe, work, "sccm_requires_inlet_boundary", base,
                 expected_error="sccm requires explicit inlet sidesets",
                 input_rewrite=no_inlet_sideset)

        def orphan_inlet_sideset(text: str) -> str:
            return text.replace("    sccm = 100\\n", "")
        run_case(exe, work, "inlet_sideset_requires_sccm", base,
                 expected_error="inlet_boundaries requires sccm",
                 input_rewrite=orphan_inlet_sideset)

        for label, value in (("zero_sccm", "0"), ("negative_sccm", "-1")):
            run_case(exe, work, label, base,
                     expected_error="SCCM feed rate must be finite and strictly positive",
                     input_rewrite=lambda text, v=value: text.replace(
                         "sccm = 100", f"sccm = {v}"
                     ))


        derived = deepcopy(base)
        del derived["species"]["O2"]["mass_fraction_variable"]
        derived["species"]["O2"]["mass_fraction_functor"] = "w_O2_constraint"
        def rewrite_derived(text: str) -> str:
            text = text.replace(
                "  [w_O2]\\n    type = MooseVariableFVReal\\n  []\\n", ""
            )
            return text.replace("[FunctorMaterials]\\n",
                "[FunctorMaterials]\\n"
                "  [O2_constraint]\\n"
                "    type = ADParsedFunctorMaterial\\n"
                "    property_name = w_O2_constraint\\n"
                "    functor_names = 'w_O'\\n"
                "    functor_symbols = 'wo'\\n"
                "    expression = '1-wo'\\n"
                "  []\\n",
            )
        run_case(exe, work, "derived_species_read_only", derived,
                 input_rewrite=rewrite_derived)

        duplicate = deepcopy(base)
        duplicate["species"]["O2"]["mass_fraction_functor"] = "w_O2_constraint"
        run_case(exe, work, "duplicate_live_owner", duplicate,
                 expected_error="must select a solved mass_fraction_variable OR a derived mass_fraction_functor")

        no_live = deepcopy(base)
        del no_live["species"]["O2"]["mass_fraction_variable"]
        run_case(exe, work, "missing_live_owner", no_live,
                 expected_error="Root ideal_gas requires one live mass_fraction_variable or")

        invalid_name = deepcopy(base)
        invalid_name["species"]["O2"]["mass_fraction_variable"] = "not-a-variable"
        run_case(exe, work, "invalid_live_state_name", invalid_name,
                 expected_error="invalid mass-fraction state name")

        retired = deepcopy(base)
        retired["gas_state"] = {"species": ["O2", "O"], "mass_fractions": ["Y_O2", "Y_O"]}
        run_case(exe, work, "retired_top_level_gas_state", retired,
                 expected_error="top-level gas_state is retired")

        invalid_volume = deepcopy(base)
        invalid_volume["species"]["O2"]["initial_vol_mass_fraction"] = 0.8
        run_case(exe, work, "volume_sum_not_one", invalid_volume,
                 expected_error="must each sum to 1")

        invalid_inlet = deepcopy(base)
        invalid_inlet["species"]["O2"]["initial_inlet_mass_fraction"] = 0.8
        run_case(exe, work, "inlet_sum_not_one", invalid_inlet,
                 expected_error="must each sum to 1")

        incomplete = deepcopy(base)
        del incomplete["species"]["O2"]["initial_inlet_mass_fraction"]
        run_case(exe, work, "missing_inlet_fraction", incomplete,
                 expected_error="must declare both initial_vol_mass_fraction")

        missing = deepcopy(base)
        del missing["species"]["O2"]["initial_vol_mass_fraction"]
        del missing["species"]["O2"]["initial_inlet_mass_fraction"]
        run_case(exe, work, "missing_species_composition", missing,
                 expected_error="requires molar_mass_kg_mol")

        negative = deepcopy(base)
        negative["species"]["O2"]["initial_vol_mass_fraction"] = -0.1
        run_case(exe, work, "negative_volume_fraction", negative,
                 expected_error="must be finite and within [0,1]")

        electron = deepcopy(base)
        electron["species"]["e"] = {
            "elements": {}, "charge_number": -1,
            "initial_vol_mass_fraction": 0.0,
            "initial_inlet_mass_fraction": 0.0,
        }
        run_case(exe, work, "electron_cannot_have_heavy_mass_fraction", electron,
                 expected_error="electron 'e' cannot declare heavy mass fractions")

        second = {"species": {
            "O2": {"elements": {"O": 2}, "charge_number": 0,
                   "molar_mass_kg_mol": 0.032,
                   "initial_vol_mass_fraction": 0.5,
                   "initial_inlet_mass_fraction": 0.9}},
                  "equations": {}, "reactions": []}
        run_case(exe, work, "conflicting_species_across_files", base,
                 second=second, expected_error="conflicting species identity")

    print("ISSUE402_SPECIES_INITIAL_COMPOSITION_NATIVE_P2_PASS_P3_NOT_RUN")


if __name__ == "__main__":
    main()
