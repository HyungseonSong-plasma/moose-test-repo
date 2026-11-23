#!/usr/bin/env python3
"""#774 D12: two real Public D 100-row Native P2 input-construction checks.

Reuse exact immutable D10 W1; stage *public* S6 417/941 inputs using the
already-tested D11 real generator. Access protected rates only in a private
0700 /dev/shm scratch with 0600 rate files. No physics recompilation, no
science time stepping, no negative mutation, no secret output artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

from issue774_d11_public_generation_rollback import (
    CASES, replay_generated_public_d, sha, need,
)

W1_SOURCE_HEAD = "05a3cf85bc5ed7d9c258b1377bd66d68d70f4e3e"
W1_RUN = "45199787795"
W1_ELF_SHA = "6afd05d4a4d356fe5132ca28076ba27e06bea93d485ac8a6b39d334bb9a9465b"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:"
       "2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
MEMBERS = {
    "physics-opt": "physics_app/physics-opt",
    "lib/libphysics-opt.so.0": "physics_app/lib/libphysics-opt.so.0",
    "lib/libphysics_test-opt.so.0": "physics_app/test/lib/libphysics_test-opt.so.0",
}
SAFE_ERROR_LABELS = {
    "unregistered_factory": re.compile(r"not a registered object|not registered", re.I),
    "missing_file": re.compile(r"cannot open|not found|No such file or directory", re.I),
    "native_error": re.compile(r"\*\*\* ERROR \*\*\*", re.I),
    "timeout": re.compile(r"TIMEOUT", re.I),
    "syntax_ok": re.compile(r"Syntax OK"),
    "unknown_parameter": re.compile(r"unknown parameter|unused parameter|unrecognized parameter", re.I),
    "duplicate_object": re.compile(r"already exists|duplicate|already defined", re.I),
    "missing_functor": re.compile(r"functor[^\n]{0,120}(missing|not found|unknown|does not exist)", re.I),
    "missing_variable": re.compile(r"variable[^\n]{0,120}(missing|not found|unknown|does not exist)", re.I),
    "chemistry_contract": re.compile(r"chemistry|reaction|species|equation", re.I),
    "transport_lookup": re.compile(r"transport|lookup|interpolation|mobility|diffusivity", re.I),
    "material_contract": re.compile(r"material|property|functor", re.I),
    "unsupported_action": re.compile(r"unsupported|unimplemented|invalid (action|physics|block)", re.I),
    "parameter_required": re.compile(r"required parameter|missing required|not supplied", re.I),
    "boundary_contract": re.compile(r"boundary|sideset|\bFVBC\b", re.I),
}
ERROR_CONTEXT_MARKERS = (
    "Syntax OK", "*** ERROR ***", "Error while", "Failed to",
    "error occurred", "Exception", "invalid", "moose",
)
# Only these explicitly selected public contract terms may be emitted, never
# arbitrary error lines, file paths, private rate identifiers or numbers.
SAFE_ERROR_TOKENS = (
    "FunctorMaterial", "ADGenericFunctorMaterial", "ChemicalReaction",
    "Equation", "Physics", "Chemistry", "Transport", "Continuity",
    "Energy", "Functor", "Material", "variable", "boundary", "parameter",
    "Executioner", "kernel", "Flux", "coefficient", "EOS", "unit",
    "thermal", "reaction", "species", "lookup", "pressure", "temperature",
)


def stage_W1(bundle: Path, target: Path) -> dict:
    doc = json.loads((bundle / "identity.json").read_text())
    expected = {
        "source_head": W1_SOURCE_HEAD, "run_id": W1_RUN,
        "binary_sha256": W1_ELF_SHA, "oci": OCI, "build_count": 1,
        "archive_member_count": 3, "archive_roundtrip_check": "PASS",
        "private_data_bundled": False, "native_check_input": "NOT_RUN",
    }
    need(all(doc.get(k) == v for k, v in expected.items()),
         "W1_SOURCE_AND_BUILD_PROVENANCE_MISMATCH")
    blob = (bundle / "physics-opt-and-app-libs.tar.gz").read_bytes()
    need(sha(blob) == doc.get("archive_sha256"), "W1_ARCHIVE_SHA_MISMATCH")
    records = {r["stored_path"]: r for r in doc["file_records"]}
    need(set(records) == set(MEMBERS), "W1_APP_LIB_MEMBER_SET_MISMATCH")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        need(set(archive.getnames()) == set(MEMBERS), "W1_TAR_CONTENT_SET_MISMATCH")
        for source, dest in sorted(MEMBERS.items()):
            member = archive.getmember(source)
            need(member.isfile() and member.size == records[source]["bytes"],
                 "W1_TAR_MEMBER_SIZE_MISMATCH")
            stream = archive.extractfile(member)
            need(stream is not None, "W1_TAR_MEMBER_READ_MISMATCH")
            content = stream.read()
            need(sha(content) == records[source]["sha256"], "W1_MEMBER_SHA_MISMATCH")
            output = target / dest
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
            if source == "physics-opt":
                output.chmod(0o755)
    binary = target / MEMBERS["physics-opt"]
    need(sha(binary.read_bytes()) == W1_ELF_SHA and binary.read_bytes()[:4] == b"\x7fELF",
         "W1_ELF_SHA_MISMATCH")
    return {
        "source_head": W1_SOURCE_HEAD, "build_run_id": W1_RUN,
        "W1_elf_sha256": W1_ELF_SHA, "archive_sha256": doc["archive_sha256"],
        "app_library_shas": {r["stored_path"]: r["sha256"] for r in doc["file_records"]},
        "one_build": True, "no_rebuild": True,
    }


def classify_native(rc: int, log: str) -> dict:
    # Restrict diagnostics to an explicit non-secret token whitelist.
    # Even the first ERROR line may embed sensitive paths or values.
    error_section = log.split("*** ERROR ***", 1)[-1] if "*** ERROR ***" in log else log
    safe_token_hits = sorted(
        token for token in SAFE_ERROR_TOKENS
        if re.search(r"\\b" + re.escape(token) + r"\\b", error_section, re.I)
    )
    return {
        "returncode": rc,
        "syntax_ok": rc == 0 and "Syntax OK" in log,
        "log_sha256": sha(log.encode("utf-8")),
        "log_bytes": len(log.encode("utf-8")),
        "safe_error_categories": {name: bool(rx.search(error_section))
                                  for name, rx in SAFE_ERROR_LABELS.items()},
        "public_error_vocab_hits": safe_token_hits,
        "error_section_sha256": sha(error_section.encode("utf-8")),
        "error_section_line_count": len(error_section.splitlines()),
    }


def stage_private_rates(work: Path, case: str, rates: dict, expected: dict, required: dict,
                        validate_rows) -> int:
    target_dir = work / "experiments/Issue395_powered_chemistry_ladder/private_rates"
    need(not target_dir.exists() and not target_dir.is_symlink(),
         "PRIVATE_RATE_DEST_ALREADY_PRESENT")
    target_dir.mkdir(mode=0o700)
    need(target_dir.stat().st_mode & 0o777 == 0o700, "PRIVATE_DIR_MODE")
    for name in sorted(required[case]):
        need(name in rates and name in expected and
             "/" not in name and name not in {".", ".."},
             "PRIVATE_RATE_NAME_UNEXPECTED")
        content = rates[name]
        need(sha(content) == expected[name] and validate_rows(content) == 100,
             "PRIVATE_RATE_HASH_OR_SHAPE_MISMATCH")
        file = target_dir / name
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(file, flags, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(content)
        need(sha(file.read_bytes()) == expected[name] and
             file.stat().st_mode & 0o777 == 0o600, "PRIVATE_RATE_READBACK")
    return len(required[case])


def run_one(root: Path, w1_root: Path, work: Path, names: list[str]) -> dict:
    need(len(names) == 11 and all(isinstance(x, str) and x.endswith(".i")
                                   and ".." not in Path(x).parts
                                   and not Path(x).is_absolute() for x in names),
         "ELEVEN_SAFE_INPUT_PATHS_REQUIRED")
    for name in names:
        need((work / name).is_file() and not (work / name).is_symlink(),
             "NATIVE_INPUT_NOT_STAGED")
    command = [
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash",
        "--user", "0:0", "--workdir", "/case",
        "--env", "OXYGEN_RESEARCH_400=1",
        "--env", "OXYGEN_RESEARCH_FULL24=0",
        "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
        "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
        "--mount", f"type=bind,src={w1_root},dst=/workspace,readonly",
        "--mount", f"type=bind,src={work},dst=/case",
        OCI, "-lc", "set -euo pipefail; source /environment; "
        "/workspace/physics_app/physics-opt --check-input -i " +
        " ".join(shlex.quote(n) for n in names),
    ]
    safe_env = {k: v for k, v in os.environ.items()
                if k not in {"PROTECTED_ARCHIVE_B64", "GH_TOKEN", "GITHUB_TOKEN"}}
    try:
        run = subprocess.run(command, capture_output=True, text=True, check=False,
                             timeout=480, env=safe_env)
        return classify_native(run.returncode, run.stdout + "\n" + run.stderr)
    except subprocess.TimeoutExpired:
        return {"returncode": 124, "syntax_ok": False, "timeout": True,
                "log_sha256": None, "safe_error_categories": {"timeout": True}}


def execute(root: Path, stage: Path, gen_dir: Path, w1: Path, temp_root: Path,
            *, source_head: str) -> dict:
    result = {
        "schema": "issue774.d12.public_d_100row_actual_native_p2.v0.1",
        "source_head": source_head, "W1": {}, "cases": {}, "generated": {},
        "native_P2_status": "HOLD", "protected_rate_cleanup_verified": False,
        "protected_data_in_artifacts": False, "legacy_input_supported": False,
        "all_generators_or_external_consumers_closed": False,
        "science_P3_P4": "NOT_RUN", "main_merge": False, "safe_to_delete": False,
    }
    protected: Path | None = None
    try:
        need(source_head == subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
            "SOURCE_HEAD_MISMATCH")
        need(not (root / "physics_app/physics-opt").exists(),
             "WORKSPACE_ALREADY_HAS_BINARY")
        result["generated"] = replay_generated_public_d(root, stage, gen_dir)
        need(set(result["generated"]) == set(CASES),
             "GENERATED_TWO_CASES_REQUIRED")
        w1_root = temp_root / "W1"
        result["W1"] = stage_W1(w1, w1_root)
        sys.path.insert(0, str(root / "ci/guards"))
        from issue671_secure_ei_rate_scratch import (
            read_hashed_rows, EXPECTED, REQUIRED, validate_rows,
        )
        meta, rates = read_hashed_rows()
        need(set(rates) == set(EXPECTED) and all(
            meta[key]["sha256_match"] and meta[key]["numeric_shape_pass"]
            for key in EXPECTED), "PROTECTED_RATE_SOURCE_ATTESTATION")
        os.environ.pop("PROTECTED_ARCHIVE_B64", None)
        protected = Path(tempfile.mkdtemp(prefix="issue774-d12-", dir="/dev/shm"))
        need(protected.stat().st_mode & 0o777 == 0o700, "PRIVATE_SCRATCH_MODE")
        stages = json.loads((stage / "readiness.json").read_text())["stage_cases"]
        for case in CASES:
            generated_root = gen_dir / case
            target = protected / case
            shutil.copytree(generated_root, target, symlinks=False)
            names = stages[case]["ordered"]
            expected_shas = result["generated"][case]["output"]["output_layer_sha256"]
            chem_folder = target / "experiments/Issue395_powered_chemistry_ladder"
            need(all(sha((chem_folder / n).read_bytes()) == expected_shas[n]
                     for n in expected_shas), "STAGED_PUBLIC_OUTPUT_SHA_DRIFT")
            protected_files = stage_private_rates(target, case, rates, EXPECTED,
                                                   REQUIRED, validate_rows)
            response = run_one(root, w1_root, target, names)
            result["cases"][case] = {
                **response, "case": case,
                "generated_mechanism_sha256": result["generated"][case]["output"]["mechanism_sha256"],
                "input_layer_shas": expected_shas,
                "protected_rate_file_count": protected_files,
                "protected_rate_content_published": False,
            }
        result["native_P2_status"] = (
            "PASS_BOTH_PUBLIC_D_INPUTS"
            if set(result["cases"]) == set(CASES)
            and all(result["cases"][k]["syntax_ok"] for k in CASES)
            else "HOLD_PUBLIC_D_NATIVE_P2_CONSTRUCTION_FAILED"
        )
    except Exception as exc:
        result["native_P2_status"] = "HOLD_NATIVE_OR_SETUP"
        result["error_class"] = type(exc).__name__
        value = str(exc)
        result["error_code"] = value[:200] if value.startswith("ISSUE774_D11_") or value.startswith("ISSUE774_D12_") else "UNEXPECTED"
    finally:
        os.environ.pop("PROTECTED_ARCHIVE_B64", None)
        if protected is not None and protected.exists():
            cleanup = subprocess.run(["sudo", "chown", "-R",
                                       f"{os.getuid()}:{os.getgid()}",
                                       str(protected)],
                                      capture_output=True, check=False)
            if cleanup.returncode == 0:
                shutil.rmtree(protected)
        result["protected_rate_cleanup_verified"] = protected is not None and not protected.exists()
        if not result["protected_rate_cleanup_verified"]:
            result["native_P2_status"] = "HOLD_PROTECTED_SCRATCH_NOT_CLEANED"
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    for key in ("root", "stage", "generated-scratch", "w1", "temp-root", "receipt"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--expected-head", required=True)
    args = p.parse_args()
    result = execute(args.root, args.stage, args.generated_scratch,
                     args.w1, args.temp_root, source_head=args.expected_head)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("D12_PUBLIC_D_NATIVE_P2=" + result["native_P2_status"])
    print("D12_PRIVATE_SCRATCH_CLEANUP=" + str(result["protected_rate_cleanup_verified"]))
    return 0 if (result["native_P2_status"] == "PASS_BOTH_PUBLIC_D_INPUTS"
                 and result["protected_rate_cleanup_verified"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
