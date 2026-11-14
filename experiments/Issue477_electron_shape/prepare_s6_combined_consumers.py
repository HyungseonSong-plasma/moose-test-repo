#!/usr/bin/env python3
"""Issue #477 S6: exactly two independent combined-chemistry perturbations.

Each new 400 W fresh t=0 run retains the archived 5-channel S4 parent and
activates EI-407 + EI-2069 + H25 *together* (8 total channels). Never accept
extra reactions, altered private lookup hashes, or silent scientific approval.

Reuse the already native-validated S5 EI-407 producer and provenance pipeline,
then stage the exact EI-2069 and H25 overlays from the immutable Oxygen14 source.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from typing import Any

# Loaded via source-root on CI; no modification of pinned Physics source.
from experiments.Issue477_electron_shape import prepare_s4_o2_consumers as s5

CHEM = s5.CHEM
ADDED = ("EI-407", "EI-2069", "H25")
CASE_PARENTS = {
    "S6-417-407-2069-H25": "417",
    "S6-941-407-2069-H25": "941",
}
EXPECTED_EXTRA_OWNERS = {"R_EI407", "R_EI2069", "R_H25"}


def validate_inventory(inputs: list[Path], case: str) -> None:
    """Exact 8 distinct chemistry owners, from 7 historical and 3 new overlays."""
    if case not in CASE_PARENTS or len(inputs) != 10:
        raise ValueError("S6 requires exactly 7 parent plus 3 added overlays")
    parent_id = CASE_PARENTS[case]
    s5.validate_inventory(inputs[:8], f"S5-{parent_id}-407")
    source = "\n".join(path.read_text() for path in inputs)
    owners = re.findall(
        r"(?m)^\s*(?:reaction_progress|property_name)\s*=\s*(R_[A-Za-z0-9_]+)\s*$",
        source,
    )
    expected = s5.BASE_OWNERS | {f"R_EI{parent_id}"} | EXPECTED_EXTRA_OWNERS
    if len(owners) != 8 or set(owners) != expected:
        raise ValueError(f"wrong combined chemistry ownership: {owners!r} vs {sorted(expected)!r}")
    if set(owners) & s5.PROHIBITED_OWNER:
        raise ValueError("unapproved oxygen chemistry reaction owner")
    if any(x in source for x in (
        "EI-2259_O2", "EI-2058_O2", "rate_table_file = o2_attachment.txt",
        "rate_table_file = o_ionization.txt",
    )):
        raise ValueError("unsupported legacy chemistry")
    new_2069 = inputs[-2].read_text()
    new_h25 = inputs[-1].read_text()
    for required in (
        "type = RateCoeffMaterial",
        "rate_table_file = 'private_rates/EI-2069_O2_a1Delta.txt'",
        "reaction_progress = R_EI2069",
        "variable = w_O2s",
        "variable = w_O",
        "variable = log_energy",
        "expression = '-5.02*R'",
        "expression = '-0.032*R'",
        "expression = '0.032*R'",
    ):
        if required not in new_2069:
            raise ValueError(f"EI2069 source projection missing: {required}")
    for required in (
        "property_name = R_H25",
        "variable = log_nop",
        "variable = log_ni",
        "variable = w_O",
        "variable = p",
        "expression = '1.204428152e7*(300.0/tg)^0.4*cp*c2'",
        "expression = '-0.032*R'",
    ):
        if required not in new_h25:
            raise ValueError(f"H25 source projection missing: {required}")
    for new_overlay in inputs[7:]:
        if "variable = log_ne" in new_overlay.read_text():
            raise ValueError("extra neutral reactions may not directly mutate electrons")
    if "rate_table_file = 'private_rates/EI-407_O2_X.txt'" not in inputs[7].read_text():
        raise ValueError("EI407 original lookup not activated")
    if "reaction_progress = R_EI407" not in inputs[7].read_text():
        raise ValueError("EI407 rate progress not activated")


def prepare(case: str, *, private_dir: Path, control_root: Path) -> dict[str, Any]:
    if case not in CASE_PARENTS:
        raise ValueError("only two explicitly approved combined S6 cases are supported")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != s5.SOURCE_SHA:
        raise ValueError("original Oxygen14 source pin changed")
    parent_id = CASE_PARENTS[case]
    s5_case = f"S5-{parent_id}-407"

    # S5 P0 reconstructs exact S4 parent hashes, audits original EI407 100-row
    # private lookup and generates a known-good 8-input single-addition case.
    s5_report = s5.prepare(s5_case, private_dir=private_dir, control_root=control_root)
    if s5_report["chemistry_channels"] != [
        "EI-02", "EI-17", "EI-415", "EI-401", f"EI-{parent_id}", "EI-407"
    ]:
        raise ValueError("the isolated EI407 control does not have expected channels")
    if s5_report["science_acceptance"] != "HOLD" or s5_report["fresh_t0"] is not True:
        raise ValueError("unfrozen S4/S5 starting conditions")
    parent_provenance = s5.PARENTS[parent_id]
    if s5_report["parent_manifest_sha256"] != parent_provenance["manifest_sha256"]:
        raise ValueError("S4 source manifest SHA mismatch")

    # Stage EI2069 directly from exact original secret kinetic inventory.
    reaction = s5.EXTRAS["2069"]
    input_rate = private_dir / reaction["rate"]
    if not input_rate.is_file() or s5.sha(input_rate) != reaction["rate_sha256"]:
        raise ValueError("missing or noncanonical EI2069 private reaction lookup")
    a = s5.rate_grid(input_rate)
    b = s5.rate_grid(private_dir / "EI-415_O2_X.txt")
    if len(a) != len(b) or not all(
        math.isclose(x, y, rel_tol=1e-10, abs_tol=1e-10) for x, y in zip(a, b)
    ):
        raise ValueError("EI2069 and EI415 rate energy grids differ")
    dest_rate = CHEM / "private_rates" / reaction["rate"]
    if dest_rate.exists():
        raise ValueError("refuse existing EI2069 private rate overwrite")
    dest_rate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_rate, dest_rate)
    if s5.sha(dest_rate) != reaction["rate_sha256"]:
        raise ValueError("EI2069 copied kinetics SHA mismatch")

    mod_2069 = s5.import_script(Path(reaction["source"]), "issue477_S6_EI2069")
    mod_h25 = s5.import_script(Path(s5.EXTRAS["H25"]["source"]), "issue477_S6_H25")
    src_2069 = mod_2069.CONTENT
    src_h25 = mod_h25.CONTENT
    mod_2069.validate_text(src_2069)
    mod_h25.validate(src_h25)

    new_overlays = [
        CHEM / f"issue477_{case}_EI2069_overlay.i",
        CHEM / f"issue477_{case}_H25_overlay.i",
    ]
    if any(file.exists() for file in new_overlays):
        raise ValueError("S6 overlay output already exists; no overwrite")
    for file, source in zip(new_overlays, (src_2069, src_h25), strict=True):
        file.write_text(source)

    inputs = [*map(Path, s5_report["input_paths"]), *new_overlays]
    validate_inventory(inputs, case)
    for p in inputs[:8]:
        if s5.sha(p) != s5_report["input_sha256"][str(p)]:
            raise ValueError(f"S5 control overlay changed: {p}")

    target = CHEM / "issue477_s6_combined_consumers" / case
    if target.exists():
        raise ValueError("S6 target already exists; no silent rerun/restart")
    (target / "run").mkdir(parents=True)
    (target / "plots").mkdir()
    channels = ["EI-02", "EI-17", "EI-415", "EI-401", f"EI-{parent_id}", *ADDED]
    record = {
        "schema": "issue477_s6_combined_407_2069_h25_v1",
        "issue": 477, "status": "P0_STATIC_ONLY", "science_acceptance": "HOLD",
        "case": case, "parent_case": parent_provenance["case"],
        "parent_manifest_sha256": parent_provenance["manifest_sha256"],
        "parent_artifact_id": parent_provenance["artifact_id"],
        "parent_artifact_sha256": parent_provenance["artifact_sha256"],
        "parent_inputs_sha256": s5_report["parent_inputs_sha256"],
        "single_EI407_control": s5_case,
        "source_sha": s5.SOURCE_SHA,
        "physics_sha": s5_report["physics_sha"],
        "source_eedf_sha256": s5.EEDF_SHA,
        "power_W": 400,
        "native_end_s": 0.0001,
        "expected_native_steps": 460,
        "expected_native_timepoints": 461,
        "fresh_t0": True,
        "chemistry_channels": channels,
        "added_channels": list(ADDED),
        "expected_progress_owners": sorted(s5.BASE_OWNERS | {f"R_EI{parent_id}"} | EXPECTED_EXTRA_OWNERS),
        "private_rate_sha256_no_bytes": {
            **s5_report["private_rate_sha256_no_bytes"],
            "EI-2069": reaction["rate_sha256"],
        },
        "private_rate_bytes_published": False,
        "input_paths": [str(p) for p in inputs],
        "input_sha256": {str(p): s5.sha(p) for p in inputs},
        "rf_mesh_transport_charged_wall": "PINNED_UNCHANGED_FROM_S4",
        "reactive_wall": "OFF_UNCHANGED_FROM_S4",
        "science_limits": [
            "8 distinct oxygen chemistry owners: S4 5 + EI407 + EI2069 + H25",
            "EI407 populates excited O2(a1Delta), which EI2069 consumes in same solve",
            "H25 consumes O+ and O2(X) and transfers charge to O2+",
            "H25 provisional 300K source; ion-neutral energy partition unmodelled",
            "O2(X) is constrained remainder, not an independent species state",
            "Strict original EI02 EEDF domain; no extrapolation or retries",
            "Fresh t=0, no checkpoint continuation; numerical success not scientific PASS",
        ],
    }
    (target / "case_manifest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print("ISSUE477_S6_COMBINED_P0_PASS", case, channels)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASE_PARENTS), required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--control-root", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.case, private_dir=args.private_dir, control_root=args.control_root)


if __name__ == "__main__":
    main()
