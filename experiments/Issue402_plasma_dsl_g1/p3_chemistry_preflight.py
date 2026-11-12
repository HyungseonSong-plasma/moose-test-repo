#!/usr/bin/env python3
"""Static, zero-solver-cost readiness audit for Issue402 S6 Chemistry P3.

This does not build binaries, run Docker, stage historical inputs or start P3.
P1/P2 provenance and science parity must be checked independently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
COMMON = PILOT / "chemistry/oxygen_s6_common.json"
CASES = ("417", "941")
COMMON_IDS = {"EI-02", "EI-17", "EI-415", "EI-401", "EI-407", "EI-2069", "H25"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root: Path = ROOT) -> dict:
    pilot = root / "experiments/Issue402_plasma_dsl_g1"
    common_path = pilot / "chemistry/oxygen_s6_common.json"
    common = json.loads(common_path.read_text())
    if set(common["species"]) != {"e", "O2", "O", "O2p", "Om", "Op", "O2a"}:
        raise ValueError("P3_COMMON_SPECIES_CONTRACT_MISMATCH")
    if set(common["equations"]) != COMMON_IDS or len(common["reactions"]) != 7:
        raise ValueError("P3_COMMON_REACTION_CONTRACT_MISMATCH")
    if "transport_coefficients" in common:
        raise ValueError("P3_UNVERIFIED_TRANSPORT_COEFFICIENT_OVERRIDE")
    files = {
        "chemistry/oxygen_s6_common.json": sha256(common_path),
    }
    cases = {}
    for case in CASES:
        mechanism = pilot / f"chemistry/oxygen_s6_{case}.json"
        variant = json.loads(mechanism.read_text())
        reactions = common["reactions"] + variant["reactions"]
        ids = [r["id"] for r in reactions]
        if set(ids) != COMMON_IDS | {"EI-" + case} or len(ids) != 8 or len(set(ids)) != 8:
            raise ValueError(f"P3_REACTION_SET_MISMATCH_{case}")
        if any("progress" in r or r.get("units") != "mol/(m^3 s)"
               for r in reactions):
            raise ValueError(f"P3_PROGRESS_OR_UNIT_MISMATCH_{case}")
        if any("provenance" not in r for r in reactions):
            raise ValueError(f"P3_PROVENANCE_UNPINNED_{case}")
        if variant["species"] or "transport_coefficients" in variant:
            raise ValueError(f"P3_UNVERIFIED_SPECIES_OR_TRANSPORT_{case}")
        template = pilot / f"s6_{case}_chemistry_run.template.i"
        text = template.read_text()
        required = f"files = 'chemistry/oxygen_s6_common.json chemistry/oxygen_s6_{case}.json'"
        if required not in text:
            raise ValueError(f"P3_MECHANISM_FILES_MISMATCH_{case}")
        if any(text.count(f"[{name}]") != 1 for name in ("Chemistry", "Continuity", "Energy")):
            raise ValueError(f"P3_MISSING_OR_DUPLICATE_PHYSICS_OWNER_{case}")
        if "fem_species = 'e'" not in text or "fvm_species = 'O2p Om Op'" not in text:
            raise ValueError(f"P3_LEGACY_EXTERNAL_VARIABLE_OWNER_MISMATCH_{case}")
        if any(f"[{name}]" in text for name in ("Variables", "Poisson", "NavierStokes")):
            raise ValueError(f"P3_DUPLICATE_NATIVE_PHYSICS_OWNER_{case}")
        if any(token in text for token in ("initial_number_density",
                                          "initial_molar_energy_density_eV",
                                          "initial_potential_V",
                                          "ei02_progress_alias",
                                          "ei17_progress_alias",
                                          "ei415_progress_alias",
                                          "R_elastic_O2", "R_elastic_O",
                                          "R_ion_O2")):
            raise ValueError(f"P3_UNVERIFIED_SOURCE_OR_IC_OVERRIDE_{case}")
        # Physics-owned material generation replaces the explicit S6 overlay.
        # Original Native ion and electron-rate Functors remain upstream.
        if "[FunctorMaterials]" in text or "signed_delta_epsilon" in text:
            raise ValueError(f"P3_MANUAL_FUNCTOR_MATERIAL_REMAINS_{case}")
        if any("energy_loss_eV" not in rx or "electron_energy_change_eV" in rx
               for rx in reactions):
            raise ValueError(f"P3_ENERGY_LOSS_SCHEMA_MISMATCH_{case}")
        files[f"chemistry/oxygen_s6_{case}.json"] = sha256(mechanism)
        files[template.name] = sha256(template)
        cases[case] = {
            "reaction_ids": ids,
            "reaction_count": len(ids),
            "scratch_native_layers": 10,
            "overlay_layers": 1,
            "superseded_electron_source_kernels": 9,
            "native_fvm_ions_and_rf_preserved": True,
        }

    # No existing main-push workflow may accidentally select the new runner.
    old_workflow = (root / ".github/workflows/issue402-canonical-s6-d-once.yml").read_text()
    if "run_chemistry_s6_p3_once.py" in old_workflow:
        raise ValueError("P3_CHEMISTRY_RUNNER_UNEXPECTEDLY_AUTO_TRIGGERED")
    new_runner = (pilot / "run_chemistry_s6_p3_once.py").read_text()
    canonical = (pilot / "run_canonical_s6_p3_once.py").read_text()
    if "--authorize-p3" not in new_runner or "chemistry_mode=True" not in new_runner:
        raise ValueError("P3_EXECUTION_AUTHORIZATION_GUARD_MISSING")
    if "prepare(staged / option.p2.CHEM, ordered, case)" not in canonical:
        raise ValueError("P3_CHEMISTRY_SCRATCH_CUTOVER_NOT_WIRED")
    if "option.run_one(" not in canonical or "P3_NATIVE_BINARY_CHANGED_AFTER_P2" not in canonical:
        raise ValueError("P3_EXACT_BINARY_P2_GATE_MISSING")
    if "        import shutil" in canonical:
        raise ValueError("P3_UNBOUND_LOCAL_SHUTIL_REGRESSION")
    files["run_chemistry_s6_p3_once.py"] = sha256(pilot / "run_chemistry_s6_p3_once.py")
    files["run_canonical_s6_p3_once.py"] = sha256(pilot / "run_canonical_s6_p3_once.py")
    files["chemistry/prepare_s6_run_input.py"] = sha256(
        pilot / "chemistry/prepare_s6_run_input.py")
    return {
        "schema": "issue402_s6_chemistry_p3_static_readiness_v1",
        "status": "STATIC_INPUTS_READY_P3_NOT_AUTHORIZED",
        "checks": {
            "static_chemistry_catalogues_and_owners": "PASS",
            "historical_immutable_mesh_and_public_rates": "P0_REQUIRED",
            "exact_head_cpp_binary": "P1_REQUIRED",
            "real_s6_417_941_scratch_chemistry": "P2_REQUIRED",
            "full_semantic_and_numerical_parity": "NOT_ACCEPTED",
            "artifact_upload_and_rest_receipt": "REQUIRED",
            "P3": "NOT_RUN",
            "P4": "NOT_RUN",
        },
        "cases": cases,
        "sha256": files,
        "excluded_from_new_chemistry_p3": [
            "transport-only plasma_species_only.json sidecar",
            "synthetic P2 reaction-rate and coefficient fixtures",
            "unverified DD/NV transport substitutions",
            "extra Native electron sources retired by guarded scratch cutover",
            "legacy reaction progress compatibility aliases",
            "B rerun and immutable archive mutation",
        ],
        "science": "SCIENCE_HOLD",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = audit()
    data = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("Refusing to overwrite an existing readiness report")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data)
    print(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
