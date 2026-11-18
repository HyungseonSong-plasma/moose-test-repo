#!/usr/bin/env python3
"""Required New-only S6-417/941 P2 gate: exact-HEAD, one PhysicsApp ELF, no P3/P4.

The historical Hybrid runners MUST NOT call this module. Protected EI original
rates exist only in per-case 0700 tmpfs; no raw rates are uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
CASES = ("417", "941")
OCI = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
C0_SHA = "2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490"
MESH_SHA = "ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc"
JSON_SHA = {
    "417": "ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef",
    "941": "2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean_log(text: str) -> str:
    # Rate contents must never enter public output; even private paths are redacted.
    return re.sub(r"/dev/shm/[^ \n'\"\t]+", "[PROTECTED_SCRATCH]", text)


def check_one(case: str, stage: Path, source_head: str, binary_sha: str,
              source_tree: str, rates: dict, required: dict,
              expected: dict, validate_rows, out: Path) -> dict:
    p4 = json.loads((stage.parent / "p4_receipt.json").read_text())[case]
    record = {
        "case": f"S6-{case}", "source_head": source_head, "source_tree": source_tree,
        "binary_sha256": binary_sha, "oci": OCI,
        "native_exit": None, "syntax_ok": False, "P2": "HOLD",
        "P3": "NOT_RUN", "P4": "NOT_RUN", "science": "SCIENCE_HOLD",
        "protected_rate_data_uploaded": False, "protected_scratch_removed": False,
    }
    scratch = None
    try:
        assert p4["post_p4_C0_sha256"] == C0_SHA
        assert p4["parent_mesh_sha256"] == MESH_SHA
        assert p4["JSON_sha256"] == JSON_SHA[case]
        assert len(p4["ordered_inputs"]) == len(p4["11_layer_sha256"]) == 11
        assert p4["retired_old_ion_FV"] == 26
        assert p4["retired_old_electron"] == 10
        assert p4["retired_old_duplicate_materials"] == 6
        assert p4["carrier_one_preserved"] is True
        base = stage / "scratch" / case
        root = base / CHEM
        for name, hashvalue in p4["11_layer_sha256"].items():
            assert sha(root / name) == hashvalue
        assert sha(root / "chemistry" / f"unified_s6_{case}_newonly.json") == JSON_SHA[case]
        assert sha(root / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh") == MESH_SHA
        assert sha(root / p4["ordered_inputs"][0]) == C0_SHA
        with tempfile.TemporaryDirectory(prefix=f"ci-newonly-{case}-", dir="/dev/shm") as d:
            scratch = Path(d)
            assert (scratch.stat().st_mode & 0o777) == 0o700
            work = scratch / "case"
            shutil.copytree(base, work, symlinks=False)
            chem = work / CHEM
            private = chem / "private_rates"
            assert not private.exists() and not private.is_symlink()
            private.mkdir(mode=0o700)
            for name in sorted(required[case]):
                assert hashlib.sha256(rates[name]).hexdigest() == expected[name]
                assert validate_rows(rates[name]) == 100
                target = private / name
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(target, flags, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(rates[name])
                assert sha(target) == expected[name]
                assert (target.stat().st_mode & 0o777) == 0o600
            assert len(list(private.iterdir())) == 5
            assert sha(ROOT / "physics_app/physics-opt") == binary_sha
            ordered = p4["ordered_inputs"]
            binary_args = ["/workspace/physics_app/physics-opt", "--check-input", "-i", *ordered]
            runcommand = (
                "source /environment; "
                "export LD_LIBRARY_PATH=/workspace/physics_app/lib:/workspace/physics_app/test/lib:$LD_LIBRARY_PATH; "
                "exec " + " ".join(shlex.quote(word) for word in binary_args)
            )
            cmd = [
                "docker", "run", "--rm", "--network", "none",
                "--entrypoint", "/bin/bash", "--user", "0:0", "--workdir", "/case",
                "--env", "OXYGEN_RESEARCH_400=1",
                "--env", "OXYGEN_RESEARCH_FULL24=0",
                "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
                "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
                "--mount", f"type=bind,src={ROOT},dst=/workspace,readonly",
                "--mount", f"type=bind,src={work},dst=/case", OCI, "-lc", runcommand,
            ]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=720,
                    env={key: val for key, val in os.environ.items()
                         if key != "PROTECTED_ARCHIVE_B64"},
                    check=False,
                )
                code = proc.returncode
                log = clean_log(proc.stdout + "\n" + proc.stderr)
            except subprocess.TimeoutExpired:
                code, log = 124, "NEWONLY_P2_CHECK_INPUT_TIMEOUT"
            finally:
                # OCI root may own generated files; guarantee private-rate removal.
                subprocess.run(
                    ["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(scratch)],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            log_path = out / f"S6-{case}-native-P2.log"
            log_path.write_text(log)
            record.update({
                "native_exit": code, "syntax_ok": code == 0 and "Syntax OK" in log,
                "log_sha256": sha(log_path),
                "input_count": 11, "input_sha256": p4["11_layer_sha256"],
                "newonly_json_sha256": JSON_SHA[case],
                "original_parent_mesh_sha256": MESH_SHA,
                "original_ei_rate_count": len(required[case]),
                "p05_owner_guard_reached": code == 0 and "Syntax OK" in log,
                "first_error": next(
                    (ln[:220] for ln in log.splitlines()
                     if "*** ERROR ***" in ln or "Error" in ln),
                    "NONE" if code == 0 else "CHECK_INPUT_FAILED",
                ),
            })
            if record["syntax_ok"] and sha(ROOT / "physics_app/physics-opt") == binary_sha:
                record["P2"] = "PASS_NATIVE_CHECK_INPUT"
        record["protected_scratch_removed"] = not scratch.exists()
        assert record["protected_scratch_removed"]
    except Exception as exc:
        record["failure_class"] = type(exc).__name__
        record["P2"] = "HOLD"
        if scratch is not None:
            record["protected_scratch_removed"] = not scratch.exists()
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    actual_head = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    actual_tree = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    assert actual_head == args.expected_head
    assert os.environ.get("GITHUB_SHA") in (None, actual_head)
    binary = ROOT / "physics_app/physics-opt"
    assert binary.is_file() and not binary.is_symlink()
    binary_sha = sha(binary)
    sys.path.insert(0, str(ROOT / "ci/guards"))
    from issue671_secure_ei_rate_scratch import (
        read_hashed_rows, REQUIRED, EXPECTED, validate_rows
    )
    rate_meta, rates = read_hashed_rows()
    assert set(rates) == set(EXPECTED) and len(EXPECTED) == 6
    assert all(rate_meta[n]["sha256_match"] and rate_meta[n]["numeric_shape_pass"]
               for n in EXPECTED)
    os.environ.pop("PROTECTED_ARCHIVE_B64", None)
    result = {
        "schema": "issue633.ci.required_newonly_s6_dual_native_p2.v1",
        "source_head": actual_head, "source_tree": actual_tree,
        "binary_sha256": binary_sha, "oci": OCI,
        "is_historical_hybrid": False, "P3": "NOT_RUN", "P4": "NOT_RUN",
        "science": "SCIENCE_HOLD", "cases": {},
    }
    for case in CASES:
        result["cases"][case] = check_one(
            case, args.stage.resolve(), actual_head, binary_sha, actual_tree,
            rates, REQUIRED, EXPECTED, validate_rows, out,
        )
        print("REQUIRED_NEWONLY_NATIVE", case, result["cases"][case]["P2"], flush=True)
    result["verdict"] = "PASS" if all(
        result["cases"][case]["P2"] == "PASS_NATIVE_CHECK_INPUT"
        and result["cases"][case]["protected_scratch_removed"]
        for case in CASES
    ) and sha(binary) == binary_sha else "HOLD"
    (out / "status.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("ISSUE633_REQUIRED_NEWONLY_417_941_NATIVE_P2", result["verdict"], flush=True)
    return 0 if result["verdict"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
