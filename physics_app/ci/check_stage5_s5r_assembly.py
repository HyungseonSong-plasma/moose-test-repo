#!/usr/bin/env python3
"""Governed S5-R assembly/static/input-validation checker for issue #192.

This gate establishes the executable representative assembly surface and
`physics-opt --check-input`. It deliberately does not execute a representative
time step and therefore does not claim representative runtime accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
CONTRACT = ROOT / "docs/development/2026-09-11_issue192_stage5_s5r_representative_contract.json"
EI01_RECOVERY = ROOT / "docs/development/2026-09-11_issue192_s5r_ei01_attachment_recovery.json"
EI16_RECOVERY = ROOT / "docs/development/2026-09-11_issue192_s5r_ei16_ionization_recovery.json"
ELECTRON_DATA = ROOT / "physics_app/data/electron_impact"
HEAVY_DATA = ROOT / "physics_app/data/heavy_reactions"

from experiments.historical_recipe_support.issue192_s5r import (  # noqa: E402
    ADMITTED_CHANNELS,
    DEFERRED_TOKENS,
    H01_H04_ACTIVE,
    H05_ACTIVE,
    OWNER_BLOCKS,
    PROGRESS,
    RATE_TABLES,
    audit_s5r_input,
    build_s5r_input,
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise AssertionError(f"missing required contract: {path.relative_to(ROOT)}")
    return json.loads(path.read_text())


def _build() -> tuple[str, dict]:
    base = (SOURCE / "heavy_base.i").read_text()
    text, meta = build_s5r_input(base)
    audit = audit_s5r_input(text)
    if audit["status"] != "PASS":
        raise AssertionError(f"S5-R assembled audit failed: {audit['failed_checks']}")
    if meta["audit"]["status"] != "PASS":
        raise AssertionError("builder metadata did not retain PASS audit")
    return text, meta


def static_check() -> dict:
    contract = _load_json(CONTRACT)
    ei01 = _load_json(EI01_RECOVERY)
    ei16 = _load_json(EI16_RECOVERY)
    text, meta = _build()
    audit = meta["audit"]

    if contract.get("status") != "ASSEMBLY_CONTRACT_FROZEN":
        raise AssertionError("S5-R assembly contract is not frozen")
    if contract.get("admitted_channels") != list(ADMITTED_CHANNELS):
        raise AssertionError("S5-R admitted ledger differs from builder ledger")
    if ei01.get("status") != "PRODUCTION_RATE_OWNER_RECOVERED":
        raise AssertionError("EI01 production rate owner is not recovered")
    if ei16.get("status") != "PRODUCTION_RATE_OWNER_RECOVERED":
        raise AssertionError("EI16 production rate owner is not recovered")

    if set(audit["owner_map"]) != set(ADMITTED_CHANNELS):
        raise AssertionError("assembled owner map is missing or adding admitted channels")
    if set(audit["progress_map"]) != set(ADMITTED_CHANNELS):
        raise AssertionError("assembled progress map is missing or adding admitted channels")
    if len(set(PROGRESS.values())) != len(PROGRESS):
        raise AssertionError("canonical progress names are not unique")
    if set(OWNER_BLOCKS) != set(ADMITTED_CHANNELS):
        raise AssertionError("owner block registry does not cover the admitted ledger")

    for token in DEFERRED_TOKENS:
        if token in text:
            raise AssertionError(f"deferred/out-of-scope channel leaked into assembly: {token}")

    if "PhysicsFVElectronReactionEnergySource" in text:
        raise AssertionError("forbidden custom electron reaction energy projector instantiated")
    if "bounds_policy = clamp" in text or "bounds_policy = floor" in text:
        raise AssertionError("non-strict solved-energy lookup policy leaked into assembly")
    if "gas_temperature = T_gas" in text or "temperature = T_gas" in text:
        raise AssertionError("controlled discriminator T_gas leaked into representative assembly")

    h14 = (HEAVY_DATA / "stage5_s5d_oxygen_heavy.txt").read_text()
    h05 = (HEAVY_DATA / "stage5_s5e_h05_oxygen_heavy.txt").read_text()
    for reaction in H01_H04_ACTIVE:
        if f"reaction {reaction} " not in h14:
            raise AssertionError(f"missing frozen heavy reaction database entry: {reaction}")
    if f"reaction {H05_ACTIVE} " not in h05:
        raise AssertionError("missing frozen H05 reaction database entry")

    result = {
        "schema_version": 1,
        "stage": "STAGE_5",
        "slice": "S5_R_REPRESENTATIVE_ASSEMBLY",
        "decision": "ASSEMBLED_OWNER_COVERAGE",
        "result": "PASS",
        "representative_runtime": "NOT_EXECUTED",
        "integrated_physics_accuracy": "NOT_ESTABLISHED",
        "admitted_channels": list(ADMITTED_CHANNELS),
        "progress_map": dict(PROGRESS),
        "owner_map": dict(OWNER_BLOCKS),
        "audit": audit,
        "common_heavy_temperature": "T_g",
        "solved_mean_energy": "mean_en_solved",
        "strict_lookup": True,
        "deferred_channels": list(DEFERRED_TOKENS),
    }
    print("S5R_ASSEMBLED_OWNER_LEDGER_STATIC_PASS")
    print(f"admitted_channels={len(ADMITTED_CHANNELS)}")
    print("exactly_one_progress_owner=PASS")
    print("zero_missing_admitted_channels=PASS")
    print("zero_unintended_channels=PASS")
    print("common_production_Tg=PASS")
    print("strict_mean_en_solved=PASS")
    print("representative_runtime=NOT_EXECUTED")
    return result


def self_test() -> None:
    text, _ = _build()
    assert audit_s5r_input(text)["status"] == "PASS"

    mutations = (
        ("wrong EI01 progress", "reaction_progress = R_attachment", "reaction_progress = R_attachment_BAD"),
        ("wrong common T_g", "temperature = T_g\n    species = 'O2 O2p O Om Op'", "temperature = 600\n    species = 'O2 O2p O Om Op'"),
        ("wrong transport bounds", "bounds_policy = error", "bounds_policy = clamp"),
        ("wrong EI20 table", "rate_table_file = o_ionization.txt", "rate_table_file = o_excitation_1d.txt"),
    )
    for label, old, new in mutations:
        if old not in text:
            raise AssertionError(f"self-test mutation anchor missing: {label}")
        bad = text.replace(old, new, 1)
        if audit_s5r_input(bad)["status"] == "PASS":
            raise AssertionError(f"negative mutation unexpectedly passed: {label}")

    print("S5R_ASSEMBLY_CHECKER_SELFTEST_PASS")


def _stage(work: Path) -> tuple[Path, dict]:
    text, meta = _build()

    for source in SOURCE.iterdir():
        if source.is_file():
            shutil.copy2(source, work / source.name)

    for name in RATE_TABLES.values():
        shutil.copy2(ELECTRON_DATA / name, work / name)
    for name in ("stage5_s5d_oxygen_heavy.txt", "stage5_s5e_h05_oxygen_heavy.txt"):
        shutil.copy2(HEAVY_DATA / name, work / name)

    input_path = work / "s5r_representative.i"
    input_path.write_text(text)
    return input_path, meta


def check_input(
    executable: str,
    *,
    evidence_out: str | None = None,
    repository_sha: str | None = None,
    build_base_ref: str | None = None,
) -> dict:
    static = static_check()
    executable_path = Path(executable).resolve()
    if not executable_path.is_file():
        raise AssertionError(f"Physics executable does not exist: {executable_path}")

    with tempfile.TemporaryDirectory(prefix="stage5-s5r-assembly-") as td:
        work = Path(td)
        input_path, meta = _stage(work)

        subprocess.run(
            [sys.executable, str(ROOT / "bin/physics.py"), "preflight", str(input_path)],
            cwd=ROOT,
            check=True,
        )
        proc = subprocess.run(
            [str(executable_path), "--check-input", "-i", input_path.name],
            cwd=work,
            text=True,
            capture_output=True,
        )
        if proc.returncode:
            raise AssertionError(proc.stdout + proc.stderr)

    evidence = {
        **static,
        "decision": "ASSEMBLY_INPUT_VALIDATION",
        "result": "PASS",
        "physics_preflight": "PASS",
        "physics_opt_check_input": "PASS",
        "runtime_executed": False,
        "representative_runtime": "NOT_EXECUTED",
        "runtime_executable": str(executable_path),
        "runtime_executable_sha256": _sha256(executable_path),
        "assembly_model": meta["model"],
    }
    if repository_sha:
        evidence["repository_sha"] = repository_sha
    if build_base_ref:
        evidence["build_base_ref"] = build_base_ref
    if evidence_out:
        Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    print("S5R_REPRESENTATIVE_ASSEMBLY_CHECK_INPUT_PASS")
    print("representative_runtime=NOT_EXECUTED")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--executable")
    parser.add_argument("--evidence-out")
    parser.add_argument("--repository-sha")
    parser.add_argument("--build-base-ref")
    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.static:
        static_check()
    elif args.executable:
        check_input(
            args.executable,
            evidence_out=args.evidence_out,
            repository_sha=args.repository_sha,
            build_base_ref=args.build_base_ref,
        )
    else:
        parser.error("--self-test, --static, or --executable is required")


if __name__ == "__main__":
    main()
