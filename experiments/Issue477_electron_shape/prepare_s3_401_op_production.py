#!/usr/bin/env python3
"""Issue #477: exactly two O+ generation perturbations on completed S3-415-401.

Prepare only: fresh C0+EI02+EI17+EI415+EI401 from the immutable native
source, verify bit-identical six parent input files against historical success,
then add either original EI417 or EI941, not both. Never include rate bytes in
public artifacts. Never claim science acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
SOURCE_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
EEDF_SHA = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
PARENT = "S3-415-401"
PARENT_RUN_ID = 42398716952
PARENT_ARTIFACT_ID = 13591493238
PARENT_ARTIFACT_SHA = "8b2027fb889c6520746a85d5f6c192fd2c1940d0206150aa90aef0a6b44b805f"
PARENT_MANIFEST_SHA = "8aa76a8a2fc70801fee70f1dc51850971a41d7cf48f46d090ee6653644e7d202"
BASE_CHANNELS = ("EI-02", "EI-17", "EI-415", "EI-401")
BASE_OWNERS = {"R_elastic_O2", "R_elastic_O", "R_ion_O2", "R_EI401"}
PARENT_INPUT_SHA = {
    "rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_100us_dt1000ns__C0_chemistry_off.i": "346523ee1dbaa2dfe5923d8e0c57de1c1e67615a55160a98077fcad4b0b7161d",
    "rf_elastic_multiapp_parent_400w_100us_dt1000ns_overlay.i": "f0ab39033396ffb0aa473b7ace70dbe4341e3ee6e3bc76afcc853964fb9b3682",
    "o2_elastic_400w_100us_dt1000ns_overlay.i": "83690b3c5484aa39061704ea453e93bde3c12e17674cc80b7b92c3532078a02e",
    "o_elastic_ei17_400w_100us_dt1000ns_overlay.i": "c9a38edcc377d7a698d407e9eea9e6f74b4f2072f786eda2b5a6a2b18fa0ff6f",
    "issue477_S2-415_generation_overlay.i": "ba9bf5711f8c7fcd3e48077b502212018e4dcbe0f64bd3d0d3acb733c0483c10",
    "issue477_S3-415-401_extra_overlay.i": "2a98b5331ee1fc42b4dd7ade84caad7eb8f23070acf276ed576d407ba7fc18c8",
}
CASES = {
    "S4-401-417": {
        "reaction": "EI-417", "rate": "EI-417_O2_X.txt",
        "sha256": "4e87121cad771a4ebbe272efa0b9349e527b0de782afc97b3f14556c57fc550d",
        "owner": "R_EI417", "energy_loss_eV": 17.0,
        "source": ".github/scripts/oxygen_legacy8_h05_ei417_100us.py",
    },
    "S4-401-941": {
        "reaction": "EI-941", "rate": "EI-941_O_3P.txt",
        "sha256": "ca10a223d631e04a84464649bac96ba3c7ee4ca157a1127376e04b66781e2adc",
        "owner": "R_EI941", "energy_loss_eV": 13.62,
        "source": ".github/scripts/ei941_replace_ei20_14ch.py",
    },
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def import_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise ValueError(f"Cannot import exact pinned source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rate_grid(path: Path) -> tuple[float, ...]:
    rows: list[float] = []
    for raw in path.read_text().splitlines():
        raw = raw.partition("#")[0].strip()
        if not raw:
            continue
        vals = raw.split()
        if len(vals) != 2:
            raise ValueError(f"Expected 2-column rate table: {path.name}")
        a, b = map(float, vals)
        if not (math.isfinite(a) and math.isfinite(b) and a > 0 and b >= 0):
            raise ValueError(f"Invalid energy / rate: {path.name}")
        if rows and a <= rows[-1]:
            raise ValueError(f"Unsorted energy grid: {path.name}")
        rows.append(a)
    if len(rows) != 100:
        raise ValueError(f"Expected 100-point original lookup: {path.name}")
    return tuple(rows)


def verify_inventory(inputs: list[Path], case: str) -> None:
    if case not in CASES or len(inputs) != 7:
        raise ValueError("Requires exactly six original S3-415-401 inputs plus one selected O+ producer")
    merged = "\n".join(path.read_text() for path in inputs)
    owners = re.findall(r"(?m)^\s*reaction_progress\s*=\s*(R_[A-Za-z0-9_]+)\s*$", merged)
    expected = BASE_OWNERS | {CASES[case]["owner"]}
    if len(owners) != 5 or set(owners) != expected:
        raise ValueError(f"Unexpected active reaction owners: {owners}; expected {sorted(expected)}")
    if any(x in merged for x in ("EI-2259_O2", "EI-2058_O2", "EI-16_O2_X.txt",
                                 "rate_table_file = o2_attachment.txt",
                                 "rate_table_file = o_ionization.txt")):
        raise ValueError("Excluded legacy chemistry or rate owner detected")
    added = inputs[-1].read_text()
    extra = CASES[case]
    for token in ("type = RateCoeffMaterial",
                  f"rate_table_file = 'private_rates/{extra['rate']}'",
                  f"reaction_progress = {extra['owner']}",
                  "variable = log_ne", "variable = log_energy",
                  "variable = log_nop", "expression = 'R'"):
        if token not in added:
            raise ValueError(f"O+ source projection missing: {token}")
    if case.endswith("417"):
        for x in ("functor = S_e_molar_EI417", "v = S_Op_molar_EI417",
                  "expression = '-17.0*R'"):
            if x not in added:
                raise ValueError("EI417 particle or energy projection missing")
        if "R_H05" in merged:
            raise ValueError("EI417 native overlay leaked unrelated H05 reaction")
    else:
        for x in ("functor = S_electron_molar_EI941", "v = S_Op_molar_EI941",
                  "expression = '-13.62*R'"):
            if x not in added:
                raise ValueError("EI941 particle or energy projection missing")
        if any(re.search(r"(?m)^\s*reaction_progress\s*=\s*" + owner + r"\s*$", merged)
               for owner in ("R_ion_O", "R_EI417")):
            raise ValueError("EI941 cannot coexist with legacy EI20 or EI417")
    if any(re.search(r"(?m)^\s*reaction_progress\s*=\s*"+owner+r"\s*$", merged)
           for owner in ("R_EI417" if case.endswith("941") else "R_EI941", "R_H23", "R_H24",
                         "R_H25", "R_EI2058", "R_EI2259")):
        raise ValueError("Unrequested additional chemistry owner found")


def prepare(case: str, private_dir: Path, control_root: Path) -> dict:
    if case not in CASES:
        raise ValueError("Only EI-417 and EI-941 isolated O+ production are authorized")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != SOURCE_SHA:
        raise ValueError("Pinned original Physics source changed")

    parent_module = import_script(
        control_root / "experiments/Issue477_electron_shape/prepare_second_base_sinks.py",
        "issue477_original_S3_415_401")
    parent = parent_module.prepare(PARENT, private_dir=private_dir, control_root=control_root)
    parent_path = CHEM / "issue477_second_base_sinks" / PARENT / "case_manifest.json"
    if sha(parent_path) != PARENT_MANIFEST_SHA:
        raise ValueError("S3-415-401 manifest must exactly match completed parent run")
    if (tuple(parent["chemistry_channels"]) != BASE_CHANNELS or
        parent["science_acceptance"] != "HOLD" or parent["fresh_t0"] is not True or
        parent["source_sha"] != SOURCE_SHA or parent["source_eedf_sha256"] != EEDF_SHA):
        raise ValueError("S3-415-401 parent identity mismatch")
    source_paths = [Path(s) for s in parent["input_paths"]]
    if set(map(lambda p: p.name, source_paths)) != set(PARENT_INPUT_SHA):
        raise ValueError("S3-415-401 inherited input inventory changed")
    for p in source_paths:
        expected = PARENT_INPUT_SHA[p.name]
        if parent["input_sha256"].get(str(p)) != expected or sha(p) != expected:
            raise ValueError(f"Historical S3-415-401 input SHA mismatch: {p.name}")

    extra = CASES[case]
    rate = private_dir / extra["rate"]
    parent_module.rate_grid(private_dir / "EI-415_O2_X.txt")
    # Verify exact 100-row original rate and its frozen research provenance.
    actual = parent_module.sha(rate) if rate.exists() else None
    if actual != extra["sha256"]:
        raise ValueError(f"Missing/wrong original {extra['reaction']} private lookup SHA")
    reference_grid = rate_grid(private_dir / "EI-415_O2_X.txt")
    selected_grid = rate_grid(rate)
    if len(reference_grid) != len(selected_grid) or any(
        not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
        for a, b in zip(reference_grid, selected_grid)
    ):
        raise ValueError("Added original lookup energy grid differs from pinned EI-415 grid")
    dest = CHEM / "private_rates" / extra["rate"]
    if dest.exists():
        raise ValueError("Refuse to overwrite an existing private reaction rate")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rate, dest)
    if sha(dest) != actual:
        raise ValueError("Private rate copy changed during staging")

    overlay_module = import_script(Path(extra["source"]),
                                   "issue477_"+extra["reaction"].replace("-", ""))
    if case.endswith("417"):
        text = overlay_module.CONTENT
        overlay_module.overlay_ok(text)
    else:
        old = CHEM / "o_ionization_ei20_400w_100us_dt1000ns_overlay.i"
        if not old.is_file():
            raise ValueError("Original atomic-O EI-20 source overlay missing")
        text = overlay_module.render_overlay(old.read_text())
        overlay_module.verify_overlay(text)
    new_overlay = CHEM / f"issue477_{case}_op_ionization_overlay.i"
    if new_overlay.exists():
        raise ValueError("Refuse to overwrite existing O+ ionization overlay")
    new_overlay.write_text(text)
    inputs = source_paths + [new_overlay]
    verify_inventory(inputs, case)
    target = CHEM / "issue477_op_production" / case
    if target.exists():
        raise ValueError("Native result output already exists: no implicit rerun/overwrite")
    (target / "run").mkdir(parents=True)
    (target / "plots").mkdir()
    manifest = {
        "schema": "issue477_s3_401_op_production_v1", "issue": 477,
        "status": "P0_STATIC_ONLY", "science_acceptance": "HOLD",
        "case": case, "parent_case": PARENT,
        "parent_action_run_id": PARENT_RUN_ID,
        "parent_artifact_id": PARENT_ARTIFACT_ID,
        "parent_artifact_sha256": PARENT_ARTIFACT_SHA,
        "parent_manifest_sha256": PARENT_MANIFEST_SHA,
        "parent_input_sha256": parent["input_sha256"],
        "source_sha": SOURCE_SHA, "physics_sha": parent["physics_sha"],
        "source_eedf_sha256": EEDF_SHA,
        "power_W": 400, "fresh_t0": True,
        "native_end_s": 0.0001, "expected_native_steps": 460,
        "expected_native_timepoints": 461,
        "chemistry_channels": [*BASE_CHANNELS, extra["reaction"]],
        "added_channel": extra["reaction"],
        "reaction": (
            "e + O2(X) -> O+(4S) + O(3P) + 2e" if case.endswith("417")
            else "e + O(3P) -> O+ + 2e"
        ),
        "op_birth_per_added_reaction": 1,
        "electron_birth_per_added_reaction": 1,
        "electron_energy_loss_eV": extra["energy_loss_eV"],
        "expected_progress_owners": sorted(BASE_OWNERS | {extra["owner"]}),
        "private_rate_sha256_no_bytes": {
            **parent["private_rate_sha256_no_bytes"],
            extra["reaction"]: actual,
        },
        "private_rate_bytes_published": False,
        "input_paths": [str(p) for p in inputs],
        "input_sha256": {str(p): sha(p) for p in inputs},
        "rf_mesh_transport_initial_state": "PINNED_AS_S3_415_401",
        "charged_wall": "PRESERVED_AS_S3_415_401",
        "reactive_wall_chemistry": "OFF_AS_S3_415_401",
        "excluded_additional_channels": ["EI-2259", "EI-2058", "H23", "H24", "H25"],
        "no_domain_extrapolation_or_silent_retries": True,
        "science_limits": [
            "O+ amplitude not predetermined; compare against unchanged S3-415-401",
            "Strict EI-02 mean-energy domain: fail closed on any out-of-range value",
            "No Science PASS or production promotion from P0-P4 runtime evidence",
        ],
    }
    (target / "case_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print("ISSUE477_OP_PRODUCTION_P0_PASS", case, extra["reaction"])
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--case", choices=sorted(CASES), required=True)
    p.add_argument("--private-dir", type=Path, required=True)
    p.add_argument("--control-root", type=Path, required=True)
    args = p.parse_args()
    prepare(args.case, args.private_dir, args.control_root)
