#!/usr/bin/env python3
"""Issue477 S5: independently add one O2-consuming Oxygen14 channel to each proven S4 parent.

8 authorized cases: first four S4-401-417 additions, then four S4-401-941
additions in the second delayed cohort. Strict original S4 input hashes,
original private reaction lookups and one extra canonical reaction owner.
Research only; native solve and scientific promotion not performed here.
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
PARENTS = {
    "417": {
        "case": "S4-401-417",
        "extra": "EI-417",
        "manifest_sha256": "39c6a12e845e2752b968d2e9de7dcbdd743744fd3bc09732c9ea202e912edf09",
        "artifact_id": 13620113498,
        "artifact_sha256": "94812530af7b4a1077356645f6c05eac169897f942f832abbbb8ddd517d1c6a8",
    },
    "941": {
        "case": "S4-401-941",
        "extra": "EI-941",
        "manifest_sha256": "d8f996405e831f94a0664f1912bff77f30b8a3318192c7848bb2b69a32a30248",
        "artifact_id": 13619558038,
        "artifact_sha256": "6e6fa7879ea872743a6994e9e2253fbf39854bf6dabcb2e2dcaca78518fc669b",
    },
}
EXTRAS = {
    "412": {
        "channel": "EI-412", "owner": "R_diss_O2",
        "rate": "EI-412_O2_X.txt",
        "rate_sha256": "53bfaf78997b1992a5e9d34c014976b3a451ea2198b2acb2ed15505caadb1137",
        "source": ".github/scripts/ei412_replaces_dissg_h23_mcs2738_ei2069_ei941_14ch.py",
        "electron_delta": 0, "loss_eV": 6.0, "o2_ground_delta": -1,
    },
    "407": {
        "channel": "EI-407", "owner": "R_EI407",
        "rate": "EI-407_O2_X.txt",
        "rate_sha256": "2565be45b9a13204583b6714a7d1b581cf29c157c78ac502d665649e4065b359",
        "source": ".github/scripts/oxygen_legacy8_ei407_100us.py",
        "electron_delta": 0, "loss_eV": 0.977, "o2_ground_delta": -1,
    },
    "2069": {
        "channel": "EI-2069", "owner": "R_EI2069",
        "rate": "EI-2069_O2_a1Delta.txt",
        "rate_sha256": "5eba74c1870e0635a3e316e143961e9f04e259675ddad00fd8653de28980644a",
        "source": ".github/scripts/ei2069_h23_no943_mcs2738_14ch.py",
        "electron_delta": 0, "loss_eV": 5.02, "o2_ground_delta": 0,
    },
    "H25": {
        "channel": "H25", "owner": "R_H25",
        "rate": None, "rate_sha256": None,
        "source": ".github/scripts/oxygen_legacy8_ei417_ei935_ei943_h24_h25_noei2259_noei2058_100us.py",
        "electron_delta": 0, "loss_eV": None, "o2_ground_delta": -1,
    },
}
CASES = {f"S5-{p}-{e}": (p, e) for p in PARENTS for e in EXTRAS}
BASE_OWNERS = {"R_elastic_O2", "R_elastic_O", "R_ion_O2", "R_EI401"}
PROHIBITED_OWNER = {"R_EI2058", "R_EI2259", "R_H23", "R_H24", "R_EI943", "R_EI20"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def import_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise ValueError(f"Missing exact pinned overlay source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rate_grid(path: Path) -> list[float]:
    rows: list[float] = []
    for raw in path.read_text().splitlines():
        raw = raw.partition("#")[0].strip()
        if not raw:
            continue
        vals = raw.split()
        if len(vals) != 2:
            raise ValueError("Original rate lookup must have two columns")
        e, rate = map(float, vals)
        if not (math.isfinite(e) and math.isfinite(rate) and e > 0 and rate >= 0):
            raise ValueError("Rate lookup contains invalid energy or rate")
        if rows and e <= rows[-1]:
            raise ValueError("Rate energies not strictly increasing")
        rows.append(e)
    if len(rows) != 100:
        raise ValueError("Expected exactly 100 original lookup nodes")
    return rows


def validate_inventory(paths: list[Path], case: str) -> None:
    if case not in CASES or len(paths) != 8:
        raise ValueError("Exact S4 seven input overlays + one extra reaction required")
    parent_id, reaction_id = CASES[case]
    expected = BASE_OWNERS | {f"R_EI{parent_id}", EXTRAS[reaction_id]["owner"]}
    text = "\n".join(p.read_text() for p in paths)
    owners = re.findall(
        r"(?m)^\s*(?:reaction_progress|property_name)\s*=\s*(R_[A-Za-z0-9_]+)\s*$",
        text,
    )
    if len(owners) != 6 or set(owners) != expected:
        raise ValueError(f"Reaction ownership mismatch: {owners} vs {sorted(expected)}")
    if set(owners) & PROHIBITED_OWNER:
        raise ValueError("Unapproved chemistry progress owner")
    if any(s in text for s in ("EI-2259_O2", "EI-2058_O2",
                               "rate_table_file = o2_attachment.txt",
                               "rate_table_file = o_ionization.txt")):
        raise ValueError("Legacy or outside-Oxygen14 rate unexpectedly activated")
    extra = paths[-1].read_text()
    x = EXTRAS[reaction_id]
    if reaction_id != "H25":
        for required in (f"rate_table_file = 'private_rates/{x['rate']}'",
                         f"reaction_progress = {x['owner']}",
                         "type = PhysicsElectronImpactRateMaterial",
                         "variable = log_energy"):
            if required not in extra:
                raise ValueError(f"Missing original electron-impact source: {required}")
        if "variable = log_ne" in extra:
            raise ValueError("O2 consuming extra must not directly create/destroy electrons")
    else:
        for required in ("property_name = R_H25",
                         "variable = log_nop", "variable = log_ni",
                         "variable = w_O", "variable = p",
                         "expression = '-R'", "expression = 'R'",
                         "expression = '1.204428152e7*(300.0/tg)^0.4*cp*c2'"):
            if required not in extra:
                raise ValueError(f"H25 source projection incomplete: {required}")
        if "variable = log_ne" in extra or "variable = log_energy" in extra:
            raise ValueError("H25 cannot create direct electron/energy source")
    if reaction_id == "412":
        for required in ("property_name = S_O2_mass_diss_implicit", "variable = w_O",
                         "expression = '-6*R'"):
            if required not in extra:
                raise ValueError(f"EI412 dissociation incomplete: {required}")
    if reaction_id == "407":
        for required in ("variable = w_O2s", "property_name = S_O2_implicit_EI407",
                         "expression = '-0.977*R'"):
            if required not in extra:
                raise ValueError(f"EI407 excitation incomplete: {required}")
    if reaction_id == "2069":
        for required in ("variable = w_O2s", "variable = w_O",
                         "expression = '-0.032*R'", "expression = '0.032*R'",
                         "expression = '-5.02*R'"):
            if required not in extra:
                raise ValueError(f"EI2069 excited-O2 dissociation incomplete: {required}")
        if re.search(r"(?m)^\s*reaction_progress\s*=\s*R_EI407\s*$", text):
            raise ValueError("EI2069 single perturbation must NOT silently enable EI407")


def prepare(case: str, private_dir: Path, control_root: Path) -> dict:
    if case not in CASES:
        raise ValueError("Only approved two four-case cohorts are permitted")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != SOURCE_SHA:
        raise ValueError("Immutable Oxygen14 harness source drift")

    parent_id, reaction_id = CASES[case]
    p = PARENTS[parent_id]
    extra = EXTRAS[reaction_id]
    parent_module = import_script(
        control_root / "experiments/Issue477_electron_shape/prepare_s3_401_op_production.py",
        "issue477_S4_parent")
    parent = parent_module.prepare(p["case"], private_dir=private_dir, control_root=control_root)
    parent_path = CHEM / "issue477_op_production" / p["case"] / "case_manifest.json"
    if sha(parent_path) != p["manifest_sha256"]:
        raise ValueError("Exact archived S4 parent manifest checksum differs")
    expected_parent_channels = ["EI-02", "EI-17", "EI-415", "EI-401", p["extra"]]
    if parent["chemistry_channels"] != expected_parent_channels or \
       parent["science_acceptance"] != "HOLD" or parent["source_sha"] != SOURCE_SHA or \
       parent["source_eedf_sha256"] != EEDF_SHA or parent["fresh_t0"] is not True:
        raise ValueError("S4 source or reaction inventory changed")
    parent_inputs = [Path(z) for z in parent["input_paths"]]
    if len(parent_inputs) != 7 or len(set(map(str, parent_inputs))) != 7:
        raise ValueError("Wrong S4 parent input inventory")
    for x in parent_inputs:
        if sha(x) != parent["input_sha256"].get(str(x)):
            raise ValueError(f"Source file modified since parent checksum: {x}")

    private_hash = None
    if extra["rate"]:
        original = private_dir / extra["rate"]
        if not original.is_file() or sha(original) != extra["rate_sha256"]:
            raise ValueError(f"Missing or changed pinned private lookup: {extra['rate']}")
        grid = rate_grid(original)
        reference = rate_grid(private_dir / "EI-415_O2_X.txt")
        if not all(math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
                   for a, b in zip(grid, reference)):
            raise ValueError("Original mean-energy lookup grid does not match native reference")
        dest = CHEM / "private_rates" / extra["rate"]
        if dest.exists():
            raise ValueError("Refuse to overwrite existing private kinetics")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, dest)
        if sha(dest) != extra["rate_sha256"]:
            raise ValueError("Private rate copied with unexpected hash")
        private_hash = sha(dest)

    mod = import_script(Path(extra["source"]), "issue477_s5_extra_"+reaction_id)
    if reaction_id == "412":
        old = CHEM / "o2_dissociation_400w_100us_dt1000ns_overlay.i"
        if not old.is_file():
            raise ValueError("Pinned DISS-G source missing for exclusive EI412 overlay extraction")
        overlay = mod.source_text(old.read_text())
        mod.verify_source(overlay)
    elif reaction_id == "407":
        overlay = mod.CONTENT
        mod.overlay_ok(overlay)
    elif reaction_id == "2069":
        overlay = mod.CONTENT
        mod.validate_text(overlay)
    else:
        overlay = mod.CONTENT
        mod.validate(overlay)

    overlay_path = CHEM / f"issue477_{case}_o2_consumer_overlay.i"
    if overlay_path.exists():
        raise ValueError("Refuse to overwrite generated extra reaction")
    overlay_path.write_text(overlay)
    all_inputs = [*parent_inputs, overlay_path]
    validate_inventory(all_inputs, case)

    target = CHEM / "issue477_s5_o2_consumers" / case
    if target.exists():
        raise ValueError("Output directory pre-exists; refuse implicit restart")
    (target / "run").mkdir(parents=True)
    (target / "plots").mkdir()
    report = {
        "schema": "issue477_s5_one_o2_consumer_v1",
        "issue": 477, "case": case, "parent_case": p["case"],
        "status": "P0_STATIC_ONLY", "science_acceptance": "HOLD",
        "parent_artifact_id": p["artifact_id"], "parent_artifact_sha256": p["artifact_sha256"],
        "parent_manifest_sha256": p["manifest_sha256"],
        "parent_inputs_sha256": parent["input_sha256"],
        "source_sha": SOURCE_SHA, "physics_sha": parent["physics_sha"],
        "source_eedf_sha256": EEDF_SHA, "power_W": 400,
        "chemistry_channels": [*expected_parent_channels, extra["channel"]],
        "added_channel": extra["channel"],
        "extra_reaction_owner": extra["owner"],
        "electron_delta_per_extra_reaction": extra["electron_delta"],
        "o2_ground_reaction_stoichiometric_delta": extra["o2_ground_delta"],
        "electron_energy_loss_eV": extra["loss_eV"],
        "private_rate_sha256_no_bytes": {
            **parent["private_rate_sha256_no_bytes"],
            **({extra["channel"]: private_hash} if private_hash else {}),
        },
        "private_rate_bytes_published": False, "fresh_t0": True,
        "native_end_s": 1e-4, "expected_native_steps": 460,
        "expected_native_timepoints": 461,
        "input_paths": list(map(str, all_inputs)),
        "input_sha256": {str(x): sha(x) for x in all_inputs},
        "expected_progress_owners": sorted(BASE_OWNERS | {f"R_EI{parent_id}", extra["owner"]}),
        "rf_mesh_transport_charged_wall": "PINNED_UNCHANGED_FROM_S4",
        "reactive_wall": "OFF_UNCHANGED_FROM_S4",
        "science_limits": [
            "S5 is one independent added channel, not four channels in one solve",
            "O2 ground-state is constrained remainder, not independently solved",
            "EI2069 without EI407 has no new O2(a) source and may have negligible flux",
            "H25 fixed 300K provisional rate and omitted ion-neutral energy partition",
            "Strict EI02 EEDF energy bound cannot be altered or extrapolated",
            "Numeric completion alone never implies scientific validation or steady state",
        ],
    }
    (target / "case_manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print("ISSUE477_S5_O2_P0_PASS", case, "parent="+p["case"], "extra="+extra["channel"])
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(CASES), required=True)
    ap.add_argument("--private-dir", type=Path, required=True)
    ap.add_argument("--control-root", type=Path, required=True)
    args = ap.parse_args()
    prepare(args.case, args.private_dir, args.control_root)
