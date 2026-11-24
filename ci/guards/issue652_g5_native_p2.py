#!/usr/bin/env python3
"""#652 G5: exact-source P4 -> G5 Scratch handoff and bounded real Native P2.

Public P3-X staging is supplied by the independently pinned #671 stager.
Source layers and original historical input are never changed. Private EI tables
are hash-verified in memory, staged only to protected tmpfs, never artifacted.
No solver time steps, numerical acceptance or automated owner deletion.
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
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CHEM = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"
sys.path.insert(0, str(CHEM))

from poisson_contract import parse_strict_json, validate_poisson  # noqa: E402
from retire_s6_p4_duplicate_owners import (  # noqa: E402
    C0, BEFORE_SHA as P4_BEFORE_SHA, AFTER_SHA as P4_AFTER_SHA,
    retire_p4_duplicate_owners,
)
from retire_s6_poisson_charge_owners import (  # noqa: E402
    G5_OUTPUT_C0_SHA, G5_OVERLAY_SHA, retire_g5_in_disposable_scratch,
)
from prepare_s6_newonly import JSON_SHA, TEMPLATE_SHA  # noqa: E402

OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
EXPECTED_HEAD = os.environ.get("G5_EXPECTED_SOURCE_HEAD", "")
CASES = ("417", "941")
PRE_G5_JSON_SHA = {
    "417": "ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef",
    "941": "2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde",
}
LOOKUP_SHA = {
    42: "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b",
    100: "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387",
}
LOOKUP_REL = Path("experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt")


def checked_lookup(case_root: Path, rows: int) -> str:
    path = case_root / LOOKUP_REL
    if (rows not in LOOKUP_SHA or path.is_symlink() or not path.is_file()
            or file_sha(path) != LOOKUP_SHA[rows]
            or len(path.read_bytes().splitlines()) != rows):
        raise ValueError("G5_LOOKUP_IDENTITY_DRIFT")
    return LOOKUP_SHA[rows]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_source_head():
    observed = subprocess.check_output(["git", "-C", str(ROOT),
                                        "rev-parse", "HEAD"], text=True).strip()
    if (not re.fullmatch(r"[0-9a-f]{40}", EXPECTED_HEAD) or
            observed != EXPECTED_HEAD):
        raise ValueError("G5_ACTIVE_SOURCE_SHA_DRIFT")


def stage_public(p3x_stage: Path, receipt_output: Path) -> dict:
    """Precheck existing P3-X source; change only marked disposable stages."""
    assert_source_head()
    original = json.loads((p3x_stage / "readiness.json").read_text())
    cases = original["stage_cases"]
    if set(cases) != set(CASES) or original["source_head"] != EXPECTED_HEAD:
        raise ValueError("G5_REAL_PUBLIC_STAGE_HEAD_MISMATCH")
    receipt = {
        "schema": "issue652.g5.real_s6_public_stage.v1",
        "source_sha": EXPECTED_HEAD, "cases": {},
        "P1": "NOT_RUN", "Native_P2": "NOT_RUN",
        "science": "SCIENCE_HOLD", "private_rate_data_in_receipt": False,
    }
    for case in CASES:
        base = p3x_stage / "scratch" / case
        chem = base / "experiments/Issue395_powered_chemistry_ladder"
        if not chem.is_dir() or chem.is_symlink():
            raise ValueError("G5_REAL_STAGE_SOURCE_NOT_FOUND:" + case)
        ordered = [Path(n).name for n in cases[case]["ordered"]]
        if len(ordered) != 11 or ordered[0] != C0 or len(set(ordered)) != 11:
            raise ValueError("G5_REAL_ELEVEN_LAYERS_INVALID:" + case)
        actual = {name: chem / name for name in ordered}
        if any((p.is_symlink() or not p.is_file()) for p in actual.values()):
            raise ValueError("G5_UNSAFE_REAL_LAYER:" + case)
        pinned = cases[case]["layer_sha256"]
        before = {name: file_sha(path) for name, path in actual.items()}
        if before != pinned or before[C0] != P4_BEFORE_SHA:
            raise ValueError("G5_REAL_P3X_INPUT_SHA_DRIFT:" + case)
        marker = chem / ".issue633_disposable_scratch"
        if marker.is_symlink():
            raise ValueError("G5_REAL_MARKER_SYMLINK")
        if not marker.exists():
            marker.write_text("issue633-scratch-only\n")
        if marker.read_text().strip() != "issue633-scratch-only":
            raise ValueError("G5_REAL_MARKER_INVALID")

        jsrc = CHEM / f"unified_s6_{case}_newonly.json"
        t_src = CHEM.parent / f"issue633_newonly_s6_{case}_continuity.template.i"
        jblob = jsrc.read_bytes()
        tblob = t_src.read_bytes()
        if sha(jblob) != JSON_SHA[case] or sha(tblob) != TEMPLATE_SHA[case]:
            raise ValueError("G5_REAL_JSON_TEMPLATE_SHA_DRIFT:" + case)
        mechanism = parse_strict_json(jblob)
        validate_poisson(mechanism)
        dest = chem / "chemistry" / jsrc.name
        if (dest.is_symlink() or not dest.is_file()
                or file_sha(dest) != PRE_G5_JSON_SHA[case]):
            raise ValueError("G5_REAL_PRE_G5_JSON_IDENTITY_DRIFT")
        if {k: v for k, v in mechanism.items() if k != "poisson"} != parse_strict_json(dest.read_bytes()):
            raise ValueError("G5_NON_POISSON_JSON_CHANGE")
        checked_lookup(base, 42)
        previous_10 = {name: before[name] for name in ordered[1:-1]}
        p4 = retire_p4_duplicate_owners(
            chem, ordered, mechanism, post_p3_layer_sha=before,
        )
        if p4["output_c0_sha256"] != P4_AFTER_SHA:
            raise ValueError("G5_REAL_P4_C0_SHA_CHANGED")
        post_p4 = dict(before)
        post_p4[C0] = p4["output_c0_sha256"]
        g5 = retire_g5_in_disposable_scratch(
            chem, ordered, mechanism, post_p4_layer_sha=post_p4,
            original_overlay=tblob, variant=case,
        )
        dest = chem / "chemistry" / jsrc.name
        if dest.is_symlink() or not dest.is_file():
            raise ValueError("G5_REAL_JSON_TARGET_UNSAFE")
        dest.write_bytes(jblob)
        after = {name: file_sha(path) for name, path in actual.items()}
        if (after[C0] != G5_OUTPUT_C0_SHA or
                after["migrated_continuity.i"] != G5_OVERLAY_SHA[case] or
                file_sha(dest) != JSON_SHA[case] or
                {name: after[name] for name in ordered[1:-1]} != previous_10):
            raise ValueError("G5_REAL_SOURCE_HANDOFF_READBACK_FAILED:" + case)
        receipt["cases"][case] = {
            "ordered": cases[case]["ordered"],
            "layer_sha256": after,
            "p3x_c0_sha256": before[C0],
            "p4": p4,
            "g5": g5,
            "newonly_json_sha256": file_sha(dest),
            "source_overlay_template_sha256": sha(tblob),
            "other_9_layers_preserved": True,
        }
    receipt_output.parent.mkdir(parents=True, exist_ok=True)
    receipt_output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("POISSON_G5_REAL_PUBLIC_STAGE_EXACT_417_941_PASS")
    return receipt


def secure_tmpfs_cleanup(path: Path) -> None:
    """Clear root-owned OCI JIT cache AND private EI inputs; no silent skips."""
    root = Path("/dev/shm")
    if (path.is_symlink() or not path.is_relative_to(root)
            or not any(part.startswith("issue652-g5-")
                       for part in path.relative_to(root).parts)):
        raise ValueError("G5_UNSAFE_PRIVATE_CLEANUP_PATH")
    if not path.exists():
        return
    # OCI uses uid 0 and can create root-owned .jitcache. Host ownership is
    # intentionally repaired only on our own exact /dev/shm scratch subtree.
    subprocess.run(
        ["sudo", "chown", "-Rh", f"{os.getuid()}:{os.getgid()}", "--", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        timeout=90,
    )
    shutil.rmtree(path)


def native_check(p3x_stage: Path, stage_receipt: Path, output: Path, lookup_rows: int = 42) -> dict:
    """Run only real 11-layer check-input with protected EI rates in tmpfs."""
    assert_source_head()
    data = json.loads(stage_receipt.read_text())
    if data["source_sha"] != EXPECTED_HEAD or set(data["cases"]) != set(CASES):
        raise ValueError("G5_NATIVE_STAGE_PROVENANCE_MISMATCH")
    binary = ROOT / "physics_app/physics-opt"
    if not binary.is_file() or binary.is_symlink() or binary.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("G5_NATIVE_EXACT_BINARY_NOT_PRESENT")
    binary_sha = file_sha(binary)
    if lookup_rows not in LOOKUP_SHA:
        raise ValueError("G5_LOOKUP_ROWS_INVALID")
    for case in CASES:
        public = p3x_stage / "scratch" / case
        chem = public / "experiments/Issue395_powered_chemistry_ladder"
        entry = data["cases"][case]
        names = [Path(x).name for x in entry["ordered"]]
        if (len(names) != 11 or len(set(names)) != 11 or names[0] != C0
                or names[-1] != "migrated_continuity.i"
                or any(Path(x).is_absolute() or ".." in Path(x).parts for x in entry["ordered"])
                or entry["layer_sha256"].get(C0) != G5_OUTPUT_C0_SHA
                or entry["layer_sha256"].get("migrated_continuity.i") != G5_OVERLAY_SHA[case]):
            raise ValueError("G5_NATIVE_ORDER_OR_OWNER_IDENTITY_DRIFT")
        mechanism = chem / "chemistry" / f"unified_s6_{case}_newonly.json"
        if (mechanism.is_symlink() or file_sha(mechanism) != JSON_SHA[case]
                or entry["newonly_json_sha256"] != JSON_SHA[case]):
            raise ValueError("G5_NATIVE_JSON_IDENTITY_DRIFT")
        checked_lookup(public, lookup_rows)
    sys.path.insert(0, str(ROOT / "ci/guards"))
    from issue671_secure_ei_rate_scratch import (  # noqa: E402
        EXPECTED, REQUIRED, read_hashed_rows, validate_rows,
    )
    metadata, tables = read_hashed_rows()
    os.environ.pop("PROTECTED_ARCHIVE_B64", None)
    if set(tables) != set(EXPECTED) or not all(
            record["sha256_match"] and record["numeric_shape_pass"]
            for record in metadata.values()):
        raise ValueError("G5_NATIVE_PROTECTED_RATE_VERIFICATION_FAILED")
    work_tmp = Path(tempfile.mkdtemp(prefix="issue652-g5-", dir="/dev/shm"))
    os.chmod(work_tmp, 0o700)
    results = {
        "schema": "issue652.g5.exact_s6_native_p2.v1",
        "source_sha": EXPECTED_HEAD, "oci": OCI,
        "binary_sha256": binary_sha, "cases": {},
        "lookup_rows": lookup_rows, "lookup_sha256": LOOKUP_SHA[lookup_rows],
        "Native_P2": "HOLD", "G6": "NOT_RUN", "science": "SCIENCE_HOLD",
        "private_rate_data_in_artifacts": False,
    }
    try:
        for case in CASES:
            public = p3x_stage / "scratch" / case
            case_private = work_tmp / case
            for path in public.rglob("*"):
                if path.is_symlink():
                    raise ValueError("G5_NATIVE_PUBLIC_SYMLINK_DENIED")
            shutil.copytree(public, case_private, symlinks=False)
            target = (case_private / "experiments/Issue395_powered_chemistry_ladder" /
                      "private_rates")
            if target.exists() or target.is_symlink():
                raise ValueError("G5_NATIVE_PROTECTED_RATE_DEST_CONFLICT")
            target.mkdir(mode=0o700)
            for name in sorted(REQUIRED[case]):
                blob = tables[name]
                if sha(blob) != EXPECTED[name] or validate_rows(blob) != 100:
                    raise ValueError("G5_NATIVE_PROTECTED_RATE_PIN_CHANGED")
                f = target / name
                fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             getattr(os, "O_NOFOLLOW", 0), 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(blob)
                if file_sha(f) != EXPECTED[name] or (f.stat().st_mode & 0o777) != 0o600:
                    raise ValueError("G5_NATIVE_PROTECTED_RATE_READBACK_FAILED")
            ordered = data["cases"][case]["ordered"]
            expected = data["cases"][case]["layer_sha256"]
            chem = case_private / "experiments/Issue395_powered_chemistry_ladder"
            if {Path(x).name: file_sha(chem / Path(x).name) for x in ordered} != expected:
                raise ValueError("G5_NATIVE_LAYER_SOURCE_CHANGED")
            cmd = [
                "docker", "run", "--rm", "--network", "none",
                "--entrypoint", "/bin/bash", "--user", "0:0",
                "--workdir", "/case",
                "--env", "OXYGEN_RESEARCH_400=1",
                "--env", "OXYGEN_RESEARCH_FULL24=0",
                "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
                "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
                "--mount", "type=bind,src=" + str(ROOT) + ",dst=/workspace,readonly",
                "--mount", "type=bind,src=" + str(case_private) + ",dst=/case",
                OCI, "-lc",
                "set -euo pipefail; source /environment; "
                "/workspace/physics_app/physics-opt --check-input -i " +
                " ".join(shlex.quote(x) for x in ordered)
            ]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, check=False, timeout=480,
                    env={k: v for k, v in os.environ.items()
                         if k != "PROTECTED_ARCHIVE_B64"},
                )
                combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
                code = proc.returncode
            except subprocess.TimeoutExpired:
                combined = "G5_NATIVE_INPUT_TIMEOUT"
                code = 124
            successful = code == 0 and "Syntax OK" in combined
            # Never persist full solver output, private paths, or unredacted
            # names of protected inputs. Only diagnostic categories remain.
            flags = {
                label: token in combined
                for label, token in {
                    "syntax_ok": "Syntax OK", "missing_property": "not found",
                    "duplicate": "already exists", "moose_error": "*** ERROR ***",
                    "undefined_functor": "functor", "mpi_abort": "MPI_ABORT",
                    "segfault": "Segmentation fault",
                }.items()
            }
            results["cases"][case] = {
                "passed": successful, "return_code": code,
                "raw_output_sha256": sha(combined.encode()),
                "raw_output_bytes": len(combined),
                "diagnostic_flags": flags,
                "source_layer_sha256": expected,
                "newonly_json_sha256": JSON_SHA[case],
                "lookup_sha256": checked_lookup(case_private, lookup_rows),
                "protected_table_rows_verified": len(REQUIRED[case]),
                "private_data_in_artifacts": False,
            }
            # Release case-specific secret-bearing scratch immediately.
            secure_tmpfs_cleanup(case_private)
        results["Native_P2"] = (
            "PASS_SYNTAX_ONLY" if all(results["cases"][c]["passed"]
                                      for c in CASES) else "HOLD_NATIVE_FAILURE"
        )
    finally:
        secure_tmpfs_cleanup(work_tmp)
        tables.clear()
    results["private_cleanup_verified"] = not work_tmp.exists()
    if not results["private_cleanup_verified"] or file_sha(binary) != binary_sha:
        raise ValueError("G5_NATIVE_CLEANUP_OR_BINARY_DRIFT")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print("POISSON_G5_NATIVE_P2", results["Native_P2"])
    if results["Native_P2"] != "PASS_SYNTAX_ONLY":
        raise ValueError("G5_NATIVE_INPUT_SYNTAX_HOLD")
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--stage-only", action="store_true")
    ap.add_argument("--native-only", action="store_true")
    ap.add_argument("--lookup-rows", type=int, choices=(42, 100), default=42)
    args = ap.parse_args()
    if args.stage_only == args.native_only:
        raise ValueError("G5_EXACT_ONE_OPERATION_REQUIRED")
    if args.stage_only:
        stage_public(args.staged, args.output / "g5_stage_receipt.json")
    else:
        native_check(args.staged, args.output / "g5_stage_receipt.json",
                     args.output / "g5_native_receipt.json", args.lookup_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
