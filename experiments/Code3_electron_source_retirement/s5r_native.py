"""Code3 #817: exact-head source-locked normalized S5-R old/new Native P2.

This intentionally executes NO long S5-R runtime, no P3, no AD Jacobian.
Only sanitized status/identity/digest evidence is uploaded.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from experiments.Code3_electron_source_retirement import consumer_pairs as pairs
from experiments.Code3_electron_source_retirement import run as code3
from experiments.Code3_electron_source_retirement import s5r_controls as controls
from physics_app.ci import check_stage5_s5r_assembly as assembler

ROOT = Path(__file__).resolve().parents[2]
PINNED = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def native_check(work: Path, arm: str, oci: str) -> dict:
    command = ("set -euo pipefail; source /environment; export HOME=/case; "
               "/workspace/physics_app/physics-opt --check-input -i " + arm + ".i")
    r = subprocess.run([
        "docker", "run", "--rm", "--platform", "linux/amd64",
        "--entrypoint", "/bin/bash", "--user", f"{os.getuid()}:{os.getgid()}",
        "--workdir", "/case", "-v", str(ROOT) + ":/workspace",
        "-v", str(work) + ":/case", oci, "-lc", command],
        capture_output=True, text=True, timeout=600, check=False)
    combined = r.stdout + r.stderr
    lines = combined.splitlines()
    index = next((i for i, s in enumerate(lines) if
                  ("*** ERROR ***" in s or "ERROR:" in s or
                   "not registered" in s)), None)
    # Preserve a bounded, public-asset-only explanation after the ERROR marker,
    # never the entire Native output or staged mesh/input in the artifact.
    snippet = None if index is None else "\\n".join(lines[index:index + 16])[:1800]
    return {
        "returncode": r.returncode,
        "syntax_ok": r.returncode == 0 and "Syntax OK" in combined,
        "combined_log_sha256": digest(combined.encode()),
        "diagnostic": snippet,
    }


def execute() -> dict:
    head = os.environ.get("SOURCE_HEAD", "")
    oci = os.environ.get("OCI", "")
    if not re.fullmatch(r"[a-f0-9]{40}", head):
        raise ValueError("NO_EXACT_HEAD")
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if actual != head:
        raise ValueError("SOURCE_HEAD_MISMATCH")
    if oci != PINNED:
        raise ValueError("OCI_NOT_PINNED")
    binary = ROOT / "physics_app/physics-opt"
    if binary.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("NO_EXACT_ELF")
    report = {
        "schema": "issue817.s5r.normalized_native_p2.v0.1",
        "source_head": head,
        "elf_sha256": digest(binary.read_bytes()),
        "oci": oci,
        "original_factory_kept": True,
        "source_file_removed": False,
        "current_generators_migrated": False,
        "full_AD_Jacobian": "NOT_EVALUATED",
        "P3_representative_science": "NOT_RUN",
        "EI18_EI19_runtime_chemistry_oracle": "NOT_RUN",
        "safe_delete": False,
        "P2": {"original": {}, "candidate": {}},
        "status": "P2_NOT_RUN",
    }
    output = ROOT / "evidence/code3_s5r_native_p2.json"
    output.parent.mkdir(exist_ok=True)
    try:
        old, new, meta = pairs.s5r_pair()
        ledger = controls.assert_s5r_electron_ledger(old, new)
        if (code3._outside_target(old, pairs.S5R_TARGET) !=
                code3._outside_target(new, pairs.S5R_TARGET)):
            raise ValueError("NON_TARGET_BYTES_CHANGED")
        report.update({
            "state_mode": meta["mode"],
            "source_functor": meta["source_functor"],
            "coef": meta["coefficient"],
            "ledger_negative_controls": ledger,
            "original_input_sha256": digest(old.encode()),
            "candidate_input_sha256": digest(new.encode()),
            "one_electron_block_only": True,
        })
        with tempfile.TemporaryDirectory(prefix="issue817-s5r-native-") as temp:
            work = Path(temp)
            source_path, _ = assembler._stage(work)
            if source_path.read_text() != old:
                raise ValueError("ACTUAL_STAGED_S5R_INPUT_NOT_IDENTICAL")
            source_path.rename(work / "original.i")
            (work / "candidate.i").write_text(new)
            for arm in ("original", "candidate"):
                report["P2"][arm] = native_check(work, arm, oci)
                output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            both = all(report["P2"][arm]["syntax_ok"]
                       for arm in ("original", "candidate"))
            report["status"] = "PASS_BOUNDED_S5R_P2_ONLY" if both else "HOLD_S5R_NATIVE_P2"
    except Exception as exc:
        report["status"] = "HOLD_S5R_GENERATOR_OR_NATIVE_EXCEPTION"
        report["exception"] = type(exc).__name__ + ":" + str(exc)[:500]
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("ISSUE817_S5R_NORMALIZED_NATIVE=" + report["status"])
    return report


def main() -> int:
    result = execute()
    return 0 if result["status"] == "PASS_BOUNDED_S5R_P2_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
