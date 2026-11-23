#!/usr/bin/env python3
"""Exact PR-665 source-only P2 New-only stage integration CI; no Native runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile


HEAD = "9c15a4f0e2cf8042cb0d4b2f18af31511021d168"
BASE_ARTIFACT_SHA = "97333b09ca3017edb04a35b2ceb82398894ddb61f256fee10e4e8cb7ede623db"
MAXWELL_ARTIFACT_SHA = "f940af496d12a4cf87903237a912922d42dd1308a38915dd38cb3ca2da0dd6a4"
ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py"
STAGE = "experiments/Issue395_powered_chemistry_ladder/"
RF_EXTRA = [
    "rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_child.i",
    "issue397_maxwell_steady_abs1e11.i",
    "rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_overlay.i",
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def verify_zip(path: Path, expected: str) -> zipfile.ZipFile:
    if sha(path.read_bytes()) != expected:
        raise AssertionError("Artifact ZIP checksum mismatch " + path.name)
    return zipfile.ZipFile(path)


def no_weird_path(rel: str) -> None:
    if rel.startswith("/") or ".." in Path(rel).parts or "\\" in rel:
        raise AssertionError("Unsafe artifact path: " + rel)


def materialize_case(base: zipfile.ZipFile, maxwell: zipfile.ZipFile, root: Path, case: str) -> tuple[Path, Path, list[str], dict]:
    folder = root / "experiments/Issue395_powered_chemistry_ladder"
    folder.mkdir(parents=True)
    manifest = json.loads(base.read(f"cases/{case}/case_manifest.json"))
    if manifest["source_head"] != HEAD or str(manifest["case"]) != case:
        raise AssertionError("Manifest pin mismatch " + case)
    ordered = manifest["ordered_input_paths"]
    assert len(ordered) == 11
    for entry in manifest["layers"]:
        rel = entry["file_path"]
        no_weird_path(rel)
        name = Path(rel).name
        data = base.read(f"cases/{case}/final_11_inputs/{name}")
        if sha(data) != entry["file_sha256"]:
            raise AssertionError("Input layer SHA mismatch " + name)
        (folder / name).write_bytes(data)
    if [Path(x).name for x in ordered] != [Path(x["file_path"]).name for x in manifest["layers"]]:
        raise AssertionError("Layer order mismatch")
    for name in RF_EXTRA:
        rel = f"cases/{case}/{STAGE}{name}"
        (folder / name).write_bytes(maxwell.read(rel))
    mesh_rel = "experiments/Issue18_qvt_plasma_mapping/qvt.msh"
    mesh = root / mesh_rel
    mesh.parent.mkdir(parents=True, exist_ok=True)
    mesh.write_bytes(maxwell.read(f"cases/{case}/{mesh_rel}"))
    (folder / ".issue633_disposable_scratch").write_text("issue633-scratch-only\n")
    mpath = root / "case_manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n")
    opath = root / "ordered.json"
    opath.write_text(json.dumps(ordered) + "\n")
    return folder, mpath, ordered, manifest


def run_case(folder: Path, mpath: Path, case: str, moments: Path, receipt: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER),
         "--newonly", "--variant", case, "--staged-chem-dir", str(folder),
         "--case-manifest", str(mpath),
         "--ordered-file", str(folder.parent.parent / "ordered.json"),
         "--moments-source", str(moments),
         "--report", str(receipt)],
        capture_output=True, text=True, timeout=90,
    )


def postcheck(folder: Path, manifest: dict, report: dict, baseline: zipfile.ZipFile, case: str) -> dict:
    assert report["status"] == "P2_NEWONLY_JSON_AND_LAYER11_STAGE_STATIC_PASS_RUNTIME_HOLD"
    retirement = report["retirement"]
    assert retirement["exact_pin_verified"] is True
    assert len(retirement["retired_owners"]) == 26
    assert report["remaining_native_ion_fv_owners"] == 0
    ecut = report["p3_x_electron"]
    assert ecut["removed_native_electron_owners"] == 10
    assert ecut["remaining_native_electron_FEM_BCs"] == 0
    assert ecut["remaining_native_electron_FunctorMaterials_for_generated_properties"] == 0
    assert len(ecut["retired_owner_receipts"]) == 10
    from importlib.util import module_from_spec, spec_from_file_location
    script = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/retire_s6_ion_fv_owners.py"
    spec = spec_from_file_location("ion26_verify", script)
    assert spec and spec.loader
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    actual_orig = {}
    expected_after = {}
    for layer in manifest["layers"]:
        name = Path(layer["file_path"]).name
        orig = baseline.read(f"cases/{case}/final_11_inputs/{name}")
        actual_orig[name] = orig
        if name != "migrated_continuity.i":
            original_text = orig.decode()
            roots = list(mod.ROOT.finditer(original_text))
            all_objects = list(mod.BLOCK.finditer(original_text))
            def identity(obj):
                section = next((r.group(1) for r in reversed(roots)
                                if r.start() < obj.start()), "")
                return section, obj["name"]
            retired_by_section_name = {
                (o["section"], o["name"]): o
                for o in retirement["retired_owners"] if o["file"] == name
            }
            if name == Path(manifest["layers"][0]["file_path"]).name:
                for o in ecut["retired_owner_receipts"]:
                    key = (o["section"], o["name"])
                    assert key not in retired_by_section_name, key
                    retired_by_section_name[key] = o
            selected = [x for x in all_objects if identity(x) in retired_by_section_name]
            assert len(selected) == len(retired_by_section_name)
            converted = original_text
            for x in reversed(selected):
                converted = converted[:x.start()] + converted[x.end():]
            expected_after[name] = converted.encode()
            assert folder.joinpath(name).read_bytes() == expected_after[name], name
            for match in selected:
                obj = retired_by_section_name[identity(match)]
                assert sha(match.group().encode()) == obj["old_block_sha256"]
    assert len([o for o in ecut["retired_owner_receipts"] if o["section"] == "BCs"]) == 8
    assert len([o for o in ecut["retired_owner_receipts"] if o["section"] == "FunctorMaterials"]) == 2
    all_files = [folder / Path(entry["file_path"]).name for entry in manifest["layers"]]
    changed = [p.name for p in all_files if sha(p.read_bytes()) != sha(actual_orig[p.name])]
    assert len(changed) == 6, changed
    assert len([p for p in all_files if p.name not in changed]) == 5
    assert all(sha(p.read_bytes()) == report["layers_after_sha256"][p.name] for p in all_files)
    staged_json = folder / "chemistry" / f"unified_s6_{case}_newonly.json"
    staged_e = folder.parent / "Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
    assert sha(staged_json.read_bytes()) == report["json_sha256"]
    assert sha(staged_e.read_bytes()) == report["electron_moments_sha256"]
    assert staged_e.samefile((staged_json.parent / "../../Issue91_real_qvt_r3/r3_e0/electron_moments.txt").resolve())
    assert report["native_p2"] == "NOT_RUN"
    assert ecut["non_target_byte_preservation"] == "PASS_EXACT_DELETION_ONLY"
    return {"case": case, "old_native_ion_owners": 26, "after_native_ion_owners": 0,
            "old_native_electron_owners_retired": 10,
            "retired_block_sha_matched": 36, "changed_staged_layers": sorted(changed),
            "json_sha256": report["json_sha256"],
            "overlay_sha256": report["newonly_overlay_sha256"],
            "electron_moments_sha256": report["electron_moments_sha256"]}


def assert_no_write_failure(folder: Path, root: Path, case: str, moments: Path, tweak: str, manifest: dict) -> str:
    before = {x.name: sha(x.read_bytes()) for x in folder.glob("*.i")}
    bad_moments = moments
    mpath = root / "case_manifest.json"
    if tweak == "wrong_head":
        m = dict(manifest, source_head="0" * 40)
        mpath.write_text(json.dumps(m))
    elif tweak == "file_tamper":
        (folder / Path(manifest["layers"][0]["file_path"]).name).write_bytes(
            (folder / Path(manifest["layers"][0]["file_path"]).name).read_bytes() + b"#tampered\n")
        before = {x.name: sha(x.read_bytes()) for x in folder.glob("*.i")}
    elif tweak == "wrong_moments":
        bad_moments = root / "wrong_moments.txt"
        bad_moments.write_text("synthetic 0.1 1e20\n")
    elif tweak == "missing_marker":
        (folder / ".issue633_disposable_scratch").unlink()
    else:
        raise AssertionError(tweak)
    proc = run_case(folder, mpath, case, bad_moments, root / "bad_receipt.json")
    if proc.returncode == 0:
        raise AssertionError("Negative unexpectedly accepted " + tweak)
    if (root / "bad_receipt.json").exists():
        raise AssertionError("Negative wrote a receipt " + tweak)
    if any(sha(p.read_bytes()) != before[p.name] for p in folder.glob("*.i")):
        raise AssertionError("Negative mutated input " + tweak)
    return tweak + ":REJECTED_NO_WRITE"


def p3x_exact_owner_negative_controls(base: zipfile.ZipFile, case: str, folder: Path) -> list[str]:
    """Exercise the *actual* P3-X preflight on real source bytes before mutation.

    These are in-memory, fail-closed structural mutations; separate P2 CLI
    negative controls prove that bad inputs do not write staged scratch files.
    """
    import copy
    sys.path.insert(0, str(RUNNER.parent))
    from retire_s6_electron_newonly_owners import (
        inspect_electron_contract, objects, CutoverError, C0
    )
    manifest = json.loads(base.read(f"cases/{case}/case_manifest.json"))
    ordered = manifest["ordered_input_paths"]
    layers = {Path(x).name: base.read(f"cases/{case}/final_11_inputs/{Path(x).name}")
              for x in ordered}
    js = json.loads((folder / "chemistry" / f"unified_s6_{case}_newonly.json").read_text())
    assert inspect_electron_contract(layers, ordered, js)["retired_electron_FEM_BCs"] == 8

    def modify_object(section: str, name: str, transformation):
        source = layers[C0].decode()
        matched = [m for s, m in objects(source) if s == section and m["name"] == name]
        assert len(matched) == 1, (section, name)
        m = matched[0]
        old = m.group(0)
        new = transformation(old)
        assert old != new, (section, name)
        result = dict(layers)
        result[C0] = (source[:m.start()] + new + source[m.end():]).encode()
        return result

    sample = [
        ("bad_e_bc_factory", modify_object("BCs", "electron_sheath",
            lambda b: b.replace("FEMElectronSheathBC", "InvalidFEMElectronSheathBC")), js),
        ("bad_e_bc_variable", modify_object("BCs", "electron_sheath",
            lambda b: b.replace("variable = log_e", "variable = log_O2p")), js),
        ("bad_e_bc_flux", modify_object("BCs", "electron_sheath",
            lambda b: b.replace("wall_number_flux = e_wall_number_flux",
                                "wall_number_flux = old_e_wall_number_flux")), js),
        ("bad_e_bc_boundary", modify_object("BCs", "electron_sheath",
            lambda b: b.replace("plasma_electrode plasma_metal plasma_right", "plasma_wrong")), js),
        ("bad_energy_mean", modify_object("BCs", "electron_energy_sheath",
            lambda b: b.replace("mean_energy = e_energy_eV", "mean_energy = unknown_energy")), js),
        ("duplicate_e_bc", modify_object("BCs", "electron_sheath", lambda b: b + b), js),
        ("missing_e_bc", modify_object("BCs", "electron_sheath", lambda b: ""), js),
        ("bad_e_density_property", modify_object("FunctorMaterials", "electron_physical_density",
            lambda b: b.replace("property_name = n_e_physical", "property_name = duplicate_density")), js),
        ("bad_e_wall_species", modify_object("FunctorMaterials", "electron_wall_flux",
            lambda b: b.replace("species_id = e", "species_id = O2p")), js),
        ("bad_solved_pressure", modify_object("Variables", "pressure",
            lambda b: b.replace("type = INSFVPressureVariable", "type = MooseVariableFVReal")), js),
        ("missing_e_functor", modify_object("FunctorMaterials", "electron_wall_flux", lambda b: ""), js),
    ]
    no_wall = copy.deepcopy(js)
    no_wall["drift_diffusion_boundaries"]["plasma_electrode plasma_metal plasma_right"].pop("e_wall")
    sample.append(("missing_json_e_wall", layers, no_wall))
    wrong_energy = copy.deepcopy(js)
    wrong_energy["drift_diffusion_boundaries"]["plasma_wafer"]["e_energy_wafer_dielectric"]["type"] = "WrongFEMEnergyBC"
    sample.append(("wrong_json_e_energy_factory", layers, wrong_energy))
    duplicate_e = copy.deepcopy(js)
    duplicate_e["drift_diffusion_boundaries"]["plasma_cover"]["e_wall"] = {"type": "FEMElectronSheathBC"}
    sample.append(("duplicate_json_e_wall_region", layers, duplicate_e))
    rejected = []
    for name, candidate_layers, candidate_json in sample:
        try:
            inspect_electron_contract(candidate_layers, ordered, candidate_json)
        except CutoverError:
            rejected.append(name + ":REJECTED_BEFORE_ANY_WRITE")
        else:
            raise AssertionError("P3X negative unexpectedly accepted: " + name)
    assert len(rejected) == 14
    return rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-zip", type=Path, required=True)
    parser.add_argument("--maxwell-zip", type=Path, required=True)
    parser.add_argument("--moments", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    base = verify_zip(args.base_zip, BASE_ARTIFACT_SHA)
    maxwell = verify_zip(args.maxwell_zip, MAXWELL_ARTIFACT_SHA)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = {}
    neg = {}
    p3x_neg = {}
    for case in ("417", "941"):
        root = out / "cases" / case
        root.mkdir(parents=True)
        folder, mpath, order, manifest = materialize_case(base, maxwell, root, case)
        receipt = root / "newonly_stage_receipt.json"
        run = run_case(folder, mpath, case, args.moments, receipt)
        if run.returncode:
            raise AssertionError(f"New-only {case} failed: {run.stderr[-1800:]}")
        report = json.loads(receipt.read_text())
        rows[case] = postcheck(folder, manifest, report, base, case)
        p3x_neg[case] = p3x_exact_owner_negative_controls(base, case, folder)
        neg[case] = []
        for tweak in ("wrong_head", "file_tamper", "wrong_moments", "missing_marker"):
            negroot = out / "negatives" / (case + "_" + tweak)
            negroot.mkdir(parents=True)
            badfolder, _, _, badmanifest = materialize_case(base, maxwell, negroot, case)
            neg[case].append(assert_no_write_failure(
                badfolder, negroot, case, args.moments, tweak, badmanifest))
    receipt = {
        "schema": "issue668.p2_production_runner_newonly_source_stage.v1",
        "status": "PASS_417_941_P2_PLUS_P3X_10_ELECTRON_OWNER_SOURCE_ONLY",
        "source_pr": 665, "source_pr_head": HEAD,
        "runner": "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py --newonly",
        "p1_0_artifact_sha256": BASE_ARTIFACT_SHA,
        "p2_maxwell_artifact_sha256": MAXWELL_ARTIFACT_SHA,
        "cases": rows, "negative_tests": neg,
        "negative_rejected": sum(map(len, neg.values())),
        "p3_x_negative_controls": p3x_neg,
        "p3_x_negative_controls_rejected": sum(map(len, p3x_neg.values())),
        "p3_x_electron_source_only": "PASS_EXACT_TEN_OLD_BC_FUNCTOR_OWNERS_RETIRED_PER_CASE",
        "scope": "P2+P3-X source-only static stage, excludes dynamic/liveness/MOOSE runtime",
        "d8_historical_and_physical_child_stage": "PASS_BOUNDED",
        "d8_newonly_dynamic_warehouse": "HOLD",
        "physics_generated_24": "NOT_RUN",
        "native_p2": "NOT_RUN", "native_p3": "NOT_RUN", "native_p4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }
    (out / "p2_newonly_integration_receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in (
        "status", "negative_rejected", "d8_newonly_dynamic_warehouse", "native_p2")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
