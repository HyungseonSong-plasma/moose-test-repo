#!/usr/bin/env python3
"""Prepare genuine 1ns O(ex) 25-reaction MOOSE checkpoint and portable restart archives.

This preserves the *complete* run/ output directory (not only plasma_cp):
MOOSE may reopen plasma.e or other output files during a subsequent --recover.
No private numeric rate tables or build binaries are packaged.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import tarfile
from pathlib import Path

from oxygen24_checkpoint_restart import (
    END_RE, EXEC_RE, OUTPUT_RE, SEQ_RE, _one, enable_checkpoint,
    checkpoint_manifest,
)

END_TIME = 1e-9
TIME_VALUES = (0.0, 1e-9)
BUILD_REF = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
             "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")


def one_ns_input(text: str) -> str:
    """Only transform the verified existing 2ns full-physics smoke input."""
    source = enable_checkpoint(text)
    match = _one(EXEC_RE, source, "Executioner")
    body = match.group("body")
    if len(list(END_RE.finditer(body))) != 1 or len(list(SEQ_RE.finditer(body))) != 1:
        raise ValueError("non-unique time grid")
    body = END_RE.sub(lambda m: m.group(1) + "1e-9", body, count=1)
    body = SEQ_RE.sub(lambda m: m.group(1) + "'0 1e-9'", body, count=1)
    result = source[:match.start("body")] + body + source[match.end("body"):]
    verify_input(result)
    return result


def verify_input(text: str) -> None:
    body = _one(EXEC_RE, text, "Executioner").group("body")
    ends = list(END_RE.finditer(body))
    grids = list(SEQ_RE.finditer(body))
    if len(ends) != 1 or len(grids) != 1:
        raise ValueError("missing or non-unique execution time grid")
    end = float(ends[0].group().split("=", 1)[1])
    values = [float(s) for s in grids[0].group().split("'", 2)[1].split()]
    if end != END_TIME or values != list(TIME_VALUES):
        raise ValueError(f"not exact 1ns input: end={end}; grid={values}")
    out = _one(OUTPUT_RE, text, "Outputs").group("body")
    if len(re.findall(r"(?m)^\s*checkpoint\s*=\s*true\s*$", out)) != 1:
        raise ValueError("checkpoint = true missing or duplicated")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def inventory(paths: list[Path], root: Path) -> list[dict]:
    root = root.resolve()
    rows = []
    for f in paths:
        if f.is_symlink():
            raise ValueError(f"unexpected symlink in packaged evidence: {f}")
        # Some libMesh/MOOSE checkpoint metadata files intentionally contain
        # zero bytes. Preserve them byte-for-byte; only explicitly required
        # state/header/Exodus/CSV files must be nonempty (checked above).
        if not f.is_file():
            raise ValueError(f"missing restart archive file: {f}")
        resolved = f.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"unsafe archive path: {f}")
        rows.append({
            "path": resolved.relative_to(root).as_posix(),
            "bytes": f.stat().st_size,
            "sha256": sha(f),
        })
    return sorted(rows, key=lambda x: x["path"])


def tar_paths(destination: Path, files: list[Path], root: Path) -> None:
    with tarfile.open(destination, "w:gz", dereference=False) as archive:
        for p in files:
            if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"unsafe tar member: {p}")
            archive.add(p, arcname=p.relative_to(root).as_posix(), recursive=False)
    with tarfile.open(destination, "r:gz") as archive:
        actual = sorted(m.name for m in archive.getmembers())
        expected = sorted(p.relative_to(root).as_posix() for p in files)
        if actual != expected:
            raise ValueError("tar member inventory mismatch")


def verify_and_archive(root: Path, result: Path, power: int, source_sha: str) -> dict:
    root = root.resolve()
    result = (root / result).resolve()
    if not result.is_relative_to(root) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("invalid source location or SHA")
    chem = root / "experiments/Issue395_powered_chemistry_ladder"
    run = result / "run"
    input_name = f"rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
    inputs = [
        chem / input_name,
        chem / f"rf_elastic_multiapp_parent_{power}w_100us_dt1000ns_overlay.i",
        chem / f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_overlay.i",
        chem / f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_child.i",
        chem / f"o2_elastic_{power}w_100us_dt1000ns_overlay.i",
        chem / f"o_elastic_ei17_{power}w_100us_dt1000ns_overlay.i",
        chem / f"full24_{power}w_100us_dt1000ns_overlay.i",
        chem / "issue397_maxwell_steady_abs1e11.i",
        chem / "a0_full_icp.i",
        chem / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh",
        chem / "o2_elastic.txt",
        chem / "o_elastic.txt",
    ]
    verify_input(inputs[0].read_text())
    for file in (run / "plasma.csv", run / "plasma.e", result / "runtime.log",
                 result / "check_input.log", chem / "chem24_manifest.json"):
        if not file.is_file() or not file.stat().st_size:
            raise ValueError(f"required runtime/restart evidence absent: {file}")
    rows = list(csv.DictReader((run / "plasma.csv").open(newline="", encoding="utf-8")))
    if len(rows) != 2:
        raise ValueError(f"expected INITIAL and 1ns rows, got {len(rows)}")
    times = [float(row["time"]) for row in rows]
    if not all(math.isclose(t, target, rel_tol=1e-12, abs_tol=1e-16)
               for t, target in zip(times, TIME_VALUES)):
        raise ValueError(f"invalid one-nanosecond endpoint: {times}")
    for key in ("n_O_ex_avg", "n_O_3P_avg", "chem24_monitor_R_936"):
        if key not in rows[-1] or not math.isfinite(float(rows[-1][key])):
            raise ValueError(f"missing/nonfinite EI936/Oex result: {key}")
    log = (result / "runtime.log").read_text(errors="replace")
    if not re.search(r"Time Step\s+1,\s*time\s*=\s*1(?:\.0*)?e-0?9", log):
        raise ValueError("actual native solver 1ns timestep absent")
    cp = run / "plasma_cp"
    cpm = checkpoint_manifest(cp)
    checkpoint_number = "0001"
    must = [
        cp / f"{checkpoint_number}-restart-0.rd/data",
        cp / f"{checkpoint_number}-restart-0.rd/header",
        cp / f"{checkpoint_number}-mesh.cpa.gz/1/header.gz",
    ]
    for f in must:
        if not f.is_file() or f.stat().st_size == 0:
            raise ValueError(f"1ns checkpoint state/mesh missing: {f}")
    rate_manifest = json.loads((chem / "chem24_manifest.json").read_text())
    if rate_manifest["active"] != 25 or rate_manifest["atoms_charge_mass"] != "PASS":
        raise ValueError("chemistry is not the 25-reaction effective Oex model")
    if rate_manifest["ei936_rate_mode"] not in ("lookup", "analytic_maxwellian_fallback"):
        raise ValueError("EI936 rate owner missing")
    private_rate_hashes = rate_manifest["lookup_sha256"]
    if len(private_rate_hashes) not in (19, 20):
        raise ValueError("invalid mandatory/optional rate inventory")
    if (936 in (int(k) for k in private_rate_hashes)) != (rate_manifest["ei936_rate_mode"] == "lookup"):
        raise ValueError("EI936 manifest inconsistency")

    # Every output in the original run directory is retained: parent checkpoint,
    # Exodus history (previous cross-run omitted plasma.e), CSV, child/output pieces.
    run_files = sorted(p for p in run.rglob("*") if p.is_file())
    if len(run_files) < 5:
        raise ValueError("run/ output inventory unexpectedly small")
    files = inventory(run_files, root)
    source_inputs = inventory(inputs, root)
    forbid = ("private_rates", "OXYGEN24_RATES_TAR_XZ_B64")
    if any(term in x["path"] for x in (files + source_inputs) for term in forbid):
        raise ValueError("private rate data cannot be archived")
    run_tar = result / "restart_run_1ns.tar.gz"
    input_tar = result / "restart_inputs_1ns.tar.gz"
    tar_paths(run_tar, run_files, root)
    tar_paths(input_tar, inputs, root)
    manifest = {
        "schema": 1,
        "power_w": power, "source_sha": source_sha,
        "final_time_s": END_TIME, "time_sequence_s": list(TIME_VALUES),
        "actual_moose_step": 1,
        "chemistry": "25-effective-O(ex)-EI936",
        "ei936_mode": rate_manifest["ei936_rate_mode"],
        "ei936_energy_loss_eV": 4.19,
        "rate_sha256_private_rehydrate_required": private_rate_hashes,
        "physics_build_base": BUILD_REF,
        "restart_output_base_relative": (run / "plasma").relative_to(root).as_posix(),
        "run_files": files,
        "input_files": source_inputs,
        "checkpoint_files": cpm["files"],
        "archives": {
            run_tar.name: {"bytes": run_tar.stat().st_size, "sha256": sha(run_tar)},
            input_tar.name: {"bytes": input_tar.stat().st_size, "sha256": sha(input_tar)},
        },
        "recovery_requirements": {
            "same_source_sha": True,
            "same_container_image_and_native_app": True,
            "verify_private_rates_against_hashes": True,
            "restore_all_run_outputs_including_plasma_e": True,
            "same_input_overlays_and_mesh_paths": True,
            "no_prepare_after_restoring_state": True,
            "native_recover_prefix": (cp / checkpoint_number).relative_to(root).as_posix(),
            "note": "Do not resume a 24-reaction checkpoint under this 25-reaction configuration",
        },
    }
    (result / "restart_1ns_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("OXYGEN25_EI936_REAL_1NS_CHECKPOINT_AND_FULL_RESTART_BUNDLE_PASS", power)
    return manifest


def self_test() -> None:
    source = (
        "[Executioner]\n  type = Transient\n  end_time = 2e-9\n"
        "  [TimeStepper]\n    type = TimeSequenceStepper\n"
        "    time_sequence = '0 1e-9 2e-9'\n  []\n[]\n"
        "[Outputs]\n  csv = true\n  exodus = true\n[]\n"
    )
    one = one_ns_input(source)
    verify_input(one)
    for bad in (source, one.replace("1e-9'", "2e-9'"),
                one.replace("checkpoint = true", "checkpoint = false")):
        try:
            verify_input(bad)
        except ValueError:
            continue
        raise AssertionError("broken checkpoint/grid accepted")
    print("OXYGEN25_EI936_ONE_NS_BUNDLE_SELFTEST_PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--set-1ns", type=Path)
    modes.add_argument("--verify-and-archive", type=Path)
    modes.add_argument("--self-test", action="store_true")
    p.add_argument("--root", type=Path)
    p.add_argument("--power-w", type=int, choices=(400, 1000))
    p.add_argument("--source-sha")
    a = p.parse_args()
    if a.self_test:
        self_test()
    elif a.set_1ns:
        a.set_1ns.write_text(one_ns_input(a.set_1ns.read_text(encoding="utf-8")),
                             encoding="utf-8")
        print("OXYGEN25_EI936_REAL_1NS_CHECKPOINT_INPUT_READY")
    else:
        if a.root is None or a.power_w is None or a.source_sha is None:
            p.error("--root, --power-w, --source-sha are required")
        verify_and_archive(a.root, a.verify_and_archive, a.power_w, a.source_sha)


if __name__ == "__main__":
    main()
