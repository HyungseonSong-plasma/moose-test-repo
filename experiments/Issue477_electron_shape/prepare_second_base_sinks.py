#!/usr/bin/env python3
"""Issue #477: second-base single-channel perturbations, fail-closed P0 only.

Uses EXACTLY the already verified S2-415 staging procedure as a static input
generator, then adds one of three current Oxygen14 lookup channels.  No native
solver runs here, no rate bytes archived and no science pass asserted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import shutil
from pathlib import Path

SOURCE_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
SECOND_BASE_ACTION = 42315463971
SECOND_BASE_ARTIFACT = 13559307611
SECOND_BASE_SHA256 = "462a60c9a310300631d488bbc690cd23b41f8953575689e26488a355e1266e14"
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
BASE = ("EI-02", "EI-17", "EI-415")
EXTRAS = {
    "S3-415-401": ("EI-401", "EI-401_O2_X.txt", "R_EI401"),
    "S3-415-412": ("EI-412", "EI-412_O2_X.txt", "R_diss_O2"),
    "S3-415-407": ("EI-407", "EI-407_O2_X.txt", "R_EI407"),
}
PINNED_RATE_SHA = {
    "EI-401": "185a102beb38d5a7a91846c69933b3f4b43e9c31dc0d57d1c5fae496206782ff",
    "EI-412": "53bfaf78997b1992a5e9d34c014976b3a451ea2198b2acb2ed15505caadb1137",
    "EI-415": "9108838e43298185e71679d2fff09c74c5c601ed3ebbaa3ba02548a374db8c64",
}
EXPECTED_BASE_OWNERS = {"R_elastic_O2", "R_elastic_O", "R_ion_O2"}
PARENT_SCRIPTS = {
    "EI-401": ".github/scripts/ei401_replaces_ei01_h23_ei412_ei941_14ch.py",
    "EI-412": ".github/scripts/ei412_replaces_dissg_h23_mcs2738_ei2069_ei941_14ch.py",
    "EI-407": ".github/scripts/oxygen_legacy8_ei407_100us.py",
}
ORIGINALS = {
    "EI-401": "o2_attachment_ei01_400w_100us_dt1000ns_overlay.i",
    "EI-412": "o2_dissociation_400w_100us_dt1000ns_overlay.i",
}
ENERGY_EV = {"EI-401": 0.0, "EI-412": 6.0, "EI-407": 0.977}
PARTICLE_DELTA = {"EI-401": -1, "EI-412": 0, "EI-407": 0}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for part in iter(lambda: fh.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def rate_grid(path: Path) -> list[float]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.partition("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError("Rate table must have exactly two columns")
        e, rate = map(float, parts)
        if not (math.isfinite(e) and math.isfinite(rate) and e > 0 and rate >= 0):
            raise ValueError("Invalid or nonpositive mean energy / negative rate")
        if rows and e <= rows[-1]:
            raise ValueError("Non-monotonic energy grid")
        rows.append(e)
    if len(rows) != 100:
        raise ValueError("Expected precisely 100 rate table energy points")
    return rows


def validate_case_inventory(paths: list[Path], extra_channel: str, expected_progress: str) -> None:
    all_text = "\n".join(p.read_text() for p in paths)
    owners = re.findall(r"(?m)^\s*reaction_progress\s*=\s*(R_[A-Za-z0-9_]+)\s*$", all_text)
    expected = EXPECTED_BASE_OWNERS | {expected_progress}
    if len(owners) != 4 or set(owners) != expected:
        raise ValueError(f"Reaction progress ownership mismatch: {owners} vs {sorted(expected)}")
    if any(x in all_text for x in ("rate_table_file = o2_attachment.txt", "EI-16_O2_X.txt", "EI-2259_O2", "EI-2058_O2")):
        raise ValueError("Excluded parent chemistry or rate file detected")
    candidate = paths[-1].read_text()
    if extra_channel == "EI-401":
        if ("expression = '-R'" not in candidate or
                "functor = S_electron_molar_EI401" not in candidate or
                "variable = log_energy" in candidate):
            raise ValueError("EI401 electron sink / zero-energy convention mismatch")
    elif extra_channel == "EI-412":
        if ("expression = '-6*R'" not in candidate or "variable = log_ne" in candidate):
            raise ValueError("EI412 energy-only kernel mismatch")
    elif extra_channel == "EI-407":
        if ("expression = '-0.977*R'" not in candidate or "variable = log_ne" in candidate or
                "variable = w_O2s" not in candidate):
            raise ValueError("EI407 energy and excited species ownership mismatch")


def prepare(case: str, private_dir: Path, control_root: Path) -> dict:
    if case not in EXTRAS:
        raise ValueError("Case not in 3-way approved current-Oxygen14 matrix")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != SOURCE_SHA:
        raise ValueError("Original pinned source SHA mismatch")
    # First-batch producer is the only accepted construction of the
    # SECOND_BASE S2-415.  Prepare its input in this fresh job; do not restart
    # from the archived 100-us numerical checkpoint.
    import importlib.util
    src = control_root / "experiments/Issue477_electron_shape/prepare_first_batch.py"
    spec = importlib.util.spec_from_file_location("issue477_original_s2_415", src)
    if spec is None or spec.loader is None:
        raise ValueError("First batch producer missing")
    first = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(first)
    root_manifest = first.prepare("S2-415", private_dir=private_dir)
    if (tuple(root_manifest["chemistry_channels"]) != BASE or
            root_manifest["source_sha"] != SOURCE_SHA or
            root_manifest["science_acceptance"] != "HOLD"):
        raise ValueError("SECOND_BASE source or chemistry contract drift")
    for p, d in root_manifest["input_sha256"].items():
        if sha(Path(p)) != d:
            raise ValueError(f"Base input changed after construction: {p}")
    if root_manifest["private_rate_sha256_no_contents"].get("EI-415") != PINNED_RATE_SHA["EI-415"]:
        raise ValueError("SECOND_BASE private EI-415 mismatch")

    extra, rate_name, extra_owner = EXTRAS[case]
    src_rate = private_dir / rate_name
    expected_sha = PINNED_RATE_SHA.get(extra)
    actual_sha = first.verify_private_rate(src_rate, expected_sha)
    grid_base = rate_grid(private_dir / "EI-415_O2_X.txt")
    grid_extra = rate_grid(src_rate)
    if any(not math.isclose(a, b, abs_tol=1e-10, rel_tol=1e-10)
           for a, b in zip(grid_base, grid_extra)):
        raise ValueError("Selected rate grid is not identical to SECOND_BASE EI-415 grid")
    dest = CHEM / "private_rates" / rate_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise ValueError("Refuse to overwrite existing private rate")
    shutil.copyfile(src_rate, dest)
    if sha(dest) != actual_sha:
        raise ValueError("Private rate copy failed exact-hash audit")

    module = first.load_script(Path(PARENT_SCRIPTS[extra]), "issue477_extra_" + extra.replace("-", ""))
    if extra == "EI-401":
        parent = CHEM / ORIGINALS[extra]
        if not parent.is_file():
            raise ValueError("Original EI01 single-channel attachment source absent")
        new_source = module.transform(parent.read_text())
        module.verify_overlay(new_source)
    elif extra == "EI-412":
        parent = CHEM / ORIGINALS[extra]
        if not parent.is_file():
            raise ValueError("Original DISS-G single-channel dissociation source absent")
        new_source = module.source_text(parent.read_text())
        module.verify_source(new_source)
    else:
        new_source = module.CONTENT
        module.overlay_ok(new_source)

    extra_overlay = CHEM / f"issue477_{case}_extra_overlay.i"
    if extra_overlay.exists():
        raise ValueError("Refuse to overwrite an existing chemistry overlay")
    extra_overlay.write_text(new_source)
    inherited = [Path(x) for x in root_manifest["input_paths"]]
    all_inputs = inherited + [extra_overlay]
    validate_case_inventory(all_inputs, extra, extra_owner)
    if set(root_manifest["input_paths"]) & {str(extra_overlay)}:
        raise ValueError("Duplicate chemistry overlay")

    target = CHEM / "issue477_second_base_sinks" / case
    if target.exists():
        raise ValueError("Refuse to reuse native output directory")
    (target / "run").mkdir(parents=True)
    (target / "plots").mkdir()
    report = {
        "schema": "issue477_second_base_sinks_v1",
        "issue": 477, "case": case, "status": "P0_STATIC_ONLY",
        "base_case": "S2-415", "base_actions_run": SECOND_BASE_ACTION,
        "base_actions_artifact_id": SECOND_BASE_ARTIFACT,
        "base_actions_artifact_sha256": SECOND_BASE_SHA256,
        "base_chemistry": list(BASE), "added_channel": extra,
        "chemistry_channels": [*BASE, extra],
        "expected_progress_owners": sorted(EXPECTED_BASE_OWNERS | {extra_owner}),
        "electron_particle_change_per_added_reaction": PARTICLE_DELTA[extra],
        "added_reaction_electron_energy_loss_eV": ENERGY_EV[extra],
        "source_sha": SOURCE_SHA, "physics_sha": first.PHYSICS_SHA,
        "source_eedf_sha256": "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b",
        "power_W": 400, "fresh_t0": True, "native_end_s": 0.0001,
        "expected_native_steps": 460, "expected_native_timepoints": 461,
        "reactive_wall_chemistry": "OFF_AS_IN_SECOND_BASE",
        "charged_wall": "PRESERVED_AS_IN_SECOND_BASE",
        "rf_mesh_transport_initial_state": "PINNED_AS_SECOND_BASE",
        "input_paths": [str(p) for p in all_inputs],
        "input_sha256": {str(p): sha(p) for p in all_inputs},
        "private_rate_sha256_no_bytes": {
            "EI-415": PINNED_RATE_SHA["EI-415"], extra: actual_sha
        },
        "first_base_manifest_sha256": sha(CHEM / "issue477_first_batch" / "S2-415" / "case_manifest.json"),
        "lookup_sha_pinned": bool(expected_sha),
        "science_acceptance": "HOLD",
        "scientific_limits": [
            "Not a validated HPEM numerical cross-section comparison",
            "Existing strict EI-02/EEDF upper energy bound must not be bypassed",
            "EI-407 affects excitation and electron energy, not electron particle stoichiometry"
        ],
    }
    (target / "case_manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("SECOND_BASE_ONE_CHANNEL_P0_PASS", case, extra)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(EXTRAS), required=True)
    ap.add_argument("--private-dir", type=Path, required=True)
    ap.add_argument("--control-root", type=Path, required=True)
    args = ap.parse_args()
    prepare(args.case, args.private_dir, args.control_root)


if __name__ == "__main__":
    main()
