"""Issue #774 D7: replay exact D5 W1 ELF archives against a synthetic legacy input.

Never confuses construction compatibility with old physics or global consumer closure.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

OCI = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
TARGET = "PhysicsFVThermalDiffusion"
UNKNOWN = "Issue774NonexistentKernelControl"
COHORTS = {
    "A": ("6c4eef073038ad69a0710e7c8555b5e03b9ad6ba", "45177303119", "6e0d04e48886a7897fa69aa85528c4aba41a9381451aa67f5477443c30df7f15"),
    "B": ("c77d2f773eee96c30eeca49d7486fea22ea8e557", "45177755891", "d6a87b61f7e3e8d06767f7a245c51e846293af740653609492d2e3f9714ac62c"),
}
MEMBERS = {
    "physics-opt": "physics_app/physics-opt",
    "lib/libphysics-opt.so.0": "physics_app/lib/libphysics-opt.so.0",
    "lib/libphysics_test-opt.so.0": "physics_app/test/lib/libphysics_test-opt.so.0",
}
MISSING = re.compile(r"(?i)(not registered|not recognized|not known|unknown|not found|not a valid|invalid.{0,40}type|does not exist|doesn't exist)")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def stage(bundle: Path, target: Path, cohort: str) -> dict:
    head, run, elf = COHORTS[cohort]
    doc = json.loads((bundle / "identity.json").read_text())
    expected = {"source_head": head, "run_id": run, "oci": OCI,
                "binary_sha256": elf, "archive_member_count": 3,
                "build_count": 1, "archive_roundtrip_check": "PASS",
                "native_check_input": "NOT_RUN"}
    if any(doc.get(k) != v for k, v in expected.items()):
        raise ValueError("D7_W1_PROVENANCE_MISMATCH_" + cohort)
    blob = (bundle / "physics-opt-and-app-libs.tar.gz").read_bytes()
    if sha(blob) != doc["archive_sha256"]:
        raise ValueError("D7_W1_ARCHIVE_SHA_MISMATCH_" + cohort)
    records = {x["stored_path"]: x for x in doc["file_records"]}
    if set(records) != set(MEMBERS):
        raise ValueError("D7_W1_RECORD_SET_MISMATCH_" + cohort)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        if set(archive.getnames()) != set(MEMBERS):
            raise ValueError("D7_W1_TAR_MEMBER_SET_MISMATCH_" + cohort)
        for name, path in MEMBERS.items():
            member = archive.getmember(name)
            if not member.isfile() or member.size != records[name]["bytes"]:
                raise ValueError("D7_W1_MEMBER_SIZE_MISMATCH_" + cohort)
            inp = archive.extractfile(member)
            if inp is None:
                raise ValueError("D7_W1_MEMBER_MISSING_" + cohort)
            content = inp.read()
            if sha(content) != records[name]["sha256"]:
                raise ValueError("D7_W1_MEMBER_SHA_MISMATCH_" + cohort)
            dest = target / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            if name == "physics-opt":
                dest.chmod(0o755)
    binary = (target / MEMBERS["physics-opt"]).read_bytes()
    if sha(binary) != elf or binary[:4] != b"\x7fELF":
        raise ValueError("D7_W1_ELF_IDENTITY_MISMATCH_" + cohort)
    return {"source_head": head, "run_id": run, "binary_sha256": elf,
            "archive_sha256": doc["archive_sha256"], "build_count": 1}


def classify(rc: int, log: str, target: str) -> str:
    if rc == 0 and "Syntax OK" in log:
        return "SYNTAX_OK"
    if rc != 0 and target in log and MISSING.search(log):
        return "FACTORY_NOT_AVAILABLE"
    return "UNEXPECTED_NATIVE_RESULT"


def make_cases(input_file: Path, output: Path) -> dict:
    base = input_file.read_text()
    if base.count("type = " + TARGET) != 1 or base.count("include_thermal_diffusion = true") != 1:
        raise ValueError("D7_FIXTURE_NOT_UNIQUE")
    cases = {
        "on.i": base,
        "off.i": base.replace("include_thermal_diffusion = true", "include_thermal_diffusion = false"),
        "unknown.i": base.replace("type = " + TARGET, "type = " + UNKNOWN),
    }
    output.mkdir(parents=True, exist_ok=True)
    for path, content in cases.items():
        (output / path).write_text(content)
    return {name: sha(content.encode()) for name, content in cases.items()}


def native(binary: Path, cases: Path, name: str) -> dict:
    command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash",
               "--user", "0:0", "--workdir", "/case",
               "--mount", f"type=bind,src={binary},dst=/workspace,readonly",
               "--mount", f"type=bind,src={cases},dst=/case,readonly",
               OCI, "-lc",
               "set -euo pipefail; source /environment; "
               f"/workspace/physics_app/physics-opt --check-input -i /case/{name}"]
    try:
        r = subprocess.run(command, capture_output=True, check=False, text=True, timeout=240)
        log = r.stdout + "\n" + r.stderr
        return {
            "rc": r.returncode, "status": classify(r.returncode, log,
                UNKNOWN if name == "unknown.i" else TARGET),
            "stdout_stderr_sha256": sha(log.encode()),
            "safe_excerpt": "\n".join(
                line[:240] for line in log.splitlines()
                if any(word in line.lower() for word in
                       ("syntax ok", "error", "not registered", "unknown", "kernel", "cannot")))[:1200],
        }
    except subprocess.TimeoutExpired:
        return {"rc": 124, "status": "TIMEOUT"}


def main() -> int:
    cli = argparse.ArgumentParser()
    for name in ("a-artifact", "b-artifact", "scratch", "input", "receipt"):
        cli.add_argument("--" + name, type=Path, required=True)
    args = cli.parse_args()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema": "issue774.legacy_thermal_binary_ab.v0.1",
              "scope": "SYNTHETIC_INPUT_CONSTRUCTION_ONLY",
              "binary": {}, "cases": {}, "input_sha256": {},
              "legacy_compatibility": "HOLD", "physics_parity": "NOT_TESTED",
              "external_callers": "NOT_VERIFIED", "science": "SCIENCE_HOLD",
              "safe_to_delete": False, "private_rates_accessed": False}
    try:
        result["input_sha256"] = make_cases(args.input, args.scratch / "cases")
        for cohort, source in (("A", args.a_artifact), ("B", args.b_artifact)):
            dest = args.scratch / cohort
            result["binary"][cohort] = stage(source, dest, cohort)
        for cohort in ("A", "B"):
            result["cases"][cohort] = {
                name: native(args.scratch / cohort, args.scratch / "cases", name)
                for name in ("on.i", "off.i", "unknown.i")
            }
        accepted = (
            all(result["cases"]["A"][name]["status"] == "SYNTAX_OK"
                for name in ("on.i", "off.i")) and
            all(result["cases"]["B"][name]["status"] == "FACTORY_NOT_AVAILABLE"
                for name in ("on.i", "off.i")) and
            all(result["cases"][c]["unknown.i"]["status"] == "FACTORY_NOT_AVAILABLE"
                for c in ("A", "B"))
        )
        result["legacy_compatibility"] = (
            "FACTORY_INTERFACE_BREAK_CONFIRMED_IN_SYNTHETIC_INPUT" if accepted
            else "HOLD_NATIVE_RESULTS_UNEXPECTED")
    except (ValueError, OSError, KeyError, tarfile.TarError, json.JSONDecodeError) as exc:
        result["legacy_compatibility"] = "HOLD_PROVENANCE_OR_SETUP"
        result["error_type"] = type(exc).__name__
    args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("D7_COMPAT_VERDICT=" + result["legacy_compatibility"])
    return 0 if result["legacy_compatibility"] == "FACTORY_INTERFACE_BREAK_CONFIRMED_IN_SYNTHETIC_INPUT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
