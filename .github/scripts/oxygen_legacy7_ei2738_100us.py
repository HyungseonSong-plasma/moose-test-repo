#!/usr/bin/env python3
"""Bounded Legacy7 experiment adapter: Legacy6 + only EI-2738, 0-100 us.

Uses the original six-reaction preparation and native replay unchanged.
The extra electron-detachment formula is experimental, not EEDF-integrated
nor an accepted chemistry-rate source.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path

BASE_IDS = ["EI-01", "EI-02", "DISS-G", "EI-16", "EI-17", "EI-20"]
SEVEN_IDS = BASE_IDS + ["EI-2738"]
RESERVED = {"x", "y", "z", "t", "pi", "e"}


def legacy6():
    path = Path(os.environ.get(
        "HARNESS", "_legacy7_control/.github/scripts/oxygen_legacy6_latest_100us.py"
    ))
    spec = importlib.util.spec_from_file_location("original_legacy6", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot resolve pinned original Legacy6 harness")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def overlay_path(module, power):
    return module.CHEM / (
        f"ei2738_detachment_formula_{power}w_100us_dt1000ns_overlay.i"
    )


def repair_parser_alias(source):
    # Original research overlay uses 'e', a reserved MOOSE FunctionParser constant.
    old = "functor_symbols = 'e om'"
    expression = "expression = 'e+om'"
    if source.count(old) != 1 or source.count(expression) != 1:
        raise ValueError("EI2738 source alias identity changed: do not guess repair")
    return (source.replace(old, "functor_symbols = 'Se Om'", 1)
                  .replace(expression, "expression = 'Se+Om'", 1))


def validate_overlay(source):
    required = [
        "property_name = R_EI2738",
        "expression = '2.0e-13*exp(-5.5/te)'",
        "property_name = S_e_molar_EI2738",
        "property_name = S_Om_molar_EI2738",
        "property_name = S_O_mass_EI2738",
        "property_name = S_energy_EI2738",
        "variable = log_ne",
        "variable = log_nm",
        "variable = w_O",
        "functor_symbols = 'Se Om'",
        "expression = 'Se+Om'",
    ]
    missing = [value for value in required if value not in source]
    if missing:
        raise ValueError(f"EI2738 source incomplete: {missing}")
    if source.count("property_name = R_EI2738") != 1:
        raise ValueError("EI2738 reaction progress must have one owner")
    if source.count("functor_on_rhs = true") != 2:
        raise ValueError("Expected electron source and energy sink exactly once")
    if source.count("source = S_O_mass_EI2738") != 1:
        raise ValueError("Atomic-O mass source owner missing or duplicate")
    for symbols in re.findall(r"(?m)^\s*functor_symbols\s*=\s*'([^']+)'", source):
        words = symbols.split()
        if len(words) != len(set(words)) or RESERVED.intersection(words):
            raise ValueError(f"EI2738 forbidden/duplicate parser alias: {symbols}")


def verify(power):
    if os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA") != "1":
        raise ValueError("EI2738 research flag must be explicitly enabled")
    if os.environ.get("OXYGEN_RESEARCH_FULL24") != "0":
        raise ValueError("Full24 source is incompatible with Legacy7")
    module = legacy6()
    module.check_input(power)
    overlay = overlay_path(module, power)
    validate_overlay(overlay.read_text())
    record = module.result(power) / "legacy6_latest_variant.json"
    variant = json.loads(record.read_text())
    if variant["chemistry_channels"] != SEVEN_IDS:
        raise ValueError(f"Wrong Legacy7 chemistry list: {variant['chemistry_channels']}")
    if variant["variant"] != "LEGACY7_EI2738_with_latest_Oxygen25_operating_settings":
        raise ValueError("Wrong experimental provenance variant")
    if variant.get("scientific_acceptance") != "HOLD":
        raise ValueError("Experiment must retain SCIENCE_HOLD")
    if variant.get("ei2738_rate_origin") != "published_maxwellian_temperature_fit_not_EEDF_integral":
        raise ValueError("Uncontrolled EI2738 rate source")
    print("OXYGEN_LEGACY7_EI2738_P0_PASS", power)
    return module, overlay


def prepare_variant(power):
    module = legacy6()
    module.check_input(power)
    if os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA") != "1":
        raise ValueError("EI2738 source generation was not enabled")
    overlay = overlay_path(module, power)
    overlay.write_text(repair_parser_alias(overlay.read_text()))
    validate_overlay(overlay.read_text())
    record = module.result(power) / "legacy6_latest_variant.json"
    variant = json.loads(record.read_text())
    if variant["chemistry_channels"] != BASE_IDS or variant["scientific_acceptance"] != "HOLD":
        raise ValueError("Original Legacy6 provenance is not as expected")
    variant.update({
        "variant": "LEGACY7_EI2738_with_latest_Oxygen25_operating_settings",
        "chemistry_channels": SEVEN_IDS,
        "rate_origin": "six original public rates plus EI2738 research temperature fit",
        "ei2738_rate_origin": "published_maxwellian_temperature_fit_not_EEDF_integral",
        "ei2738_rate_prefactor_m3_s": 2.0e-13,
        "ei2738_fit_exponent_eV": 5.5,
        "ei2738_model_energy_loss_eV": 2.70,
        "scientific_acceptance": "HOLD",
        "native_initialization": "fresh_not_restarted",
    })
    record.write_text(json.dumps(variant, indent=2, sort_keys=True) + "\n")
    verify(power)
    print("OXYGEN_LEGACY7_EI2738_PREPARED", power)


def archive(power):
    module, overlay = verify(power)
    # Preserve the additional formula overlay with the original native run/input
    # archives; otherwise a resulting checkpoint could not reproduce Legacy7.
    module.PERSIST = tuple(module.PERSIST) + (overlay.name,)
    module.verify_and_archive(power)
    manifest_file = module.result(power) / "legacy6_restart_100000ns_manifest.json"
    manifest = json.loads(manifest_file.read_text())
    files = [entry["path"] for entry in manifest["inventory"]["inputs"]]
    if not any(path.endswith("/" + overlay.name) for path in files):
        raise ValueError("EI2738 exact overlay missing from restart archive")
    if (manifest["chemistry_channels"] != SEVEN_IDS
            or manifest["native_endpoint_s"] != 1e-4
            or not manifest["verified_full_native_100us_checkpoint"]):
        raise ValueError("Legacy7 100us postcondition failed")
    print("OXYGEN_LEGACY7_EI2738_100US_NATIVE_PASS", power)


def self_test():
    example = "functor_symbols = 'e om'\nexpression = 'e+om'"
    repaired = repair_parser_alias(example)
    assert "functor_symbols = 'Se Om'" in repaired
    assert "expression = 'Se+Om'" in repaired
    try:
        repair_parser_alias(repaired)
    except ValueError:
        pass
    else:
        raise AssertionError("Source mutation must fail closed")
    try:
        validate_overlay(repaired)
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete overlay must fail closed")
    print("OXYGEN_LEGACY7_EI2738_HARNESS_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--prepare-variant", action="store_true")
    group.add_argument("--verify-seven", action="store_true")
    group.add_argument("--verify-and-archive", action="store_true")
    parser.add_argument("--power-w", type=int, choices=(400, 1000))
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.power_w is None:
        parser.error("--power-w required")
    elif args.prepare_variant:
        prepare_variant(args.power_w)
    elif args.verify_seven:
        verify(args.power_w)
    elif args.verify_and_archive:
        archive(args.power_w)


if __name__ == "__main__":
    main()
