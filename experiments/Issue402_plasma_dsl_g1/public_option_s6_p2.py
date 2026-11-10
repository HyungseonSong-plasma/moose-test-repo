#!/usr/bin/env python3
"""Public-data-only S6-417/941 native P2: original B versus option-first D.

Do not execute a solver time step. Never access archived private reference rates.
The C legacy migration is only an immutable source of the 10-layer no-ne_transport
base: its old migrated_continuity.i is replaced by an independently pinned overlay.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
P2_PATH = ROOT / "experiments/Issue493_s6_boltzmann/public_p2_check.py"
SPEC = importlib.util.spec_from_file_location("issue493_public_p2", P2_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load pinned public P2 preflight")
p2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p2)

HISTORICAL_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
OVERLAY = """# Review-only new option DSL overlay; NOT pinned P3 C input.
# Pair ONLY with the C candidate base (which removes the original ne_transport).
# No Material/Functor name is modified.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          fem_potential = potential
          mobility = 'electron_mobility ion_mobility negative_ion_mobility atomic_positive_ion_mobility'
          diffusivity = 'electron_diffusion ion_diffusion negative_ion_diffusion atomic_positive_ion_diffusion'
          fem_charge_numbers = '-1'
          fvm_charge_numbers = '1 -1 1'
        []
      []
    []
  []
[]
"""
OVERLAY_SHA256 = "a64ed0f6acbb9b96bdf0de31a977de496c01cb1eccca3badfe1fe97682818831"
CASES = ("417", "941")
VARIANTS = ("B", "D")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def validate_overlay() -> None:
    if hashlib.sha256(OVERLAY.encode("utf-8")).hexdigest() != OVERLAY_SHA256:
        raise ValueError("Option-only review overlay SHA changed")
    for forbidden in ("variables =", "fem_kernel_names", "fem_mobility =",
                      "fem_diffusion =", "electron_diffusivity", "[ne_transport]"):
        if forbidden in OVERLAY:
            raise ValueError(f"Unexpected option/provider migration: {forbidden}")
    expected = {
        "fem_species": "'e'", "fvm_species": "'O2p Om Op'",
        "fem_charge_numbers": "'-1'", "fvm_charge_numbers": "'1 -1 1'",
        "fem_potential": "potential",
    }
    for k, v in expected.items():
        if not re.search(r"(?m)^\s*" + k + r"\s*=\s*" + re.escape(v) + r"\s*$", OVERLAY):
            raise ValueError(f"Missing/modified binding: {k}")
    for key in ("mobility", "diffusivity"):
        found = re.search(r"(?m)^\s*" + key + r"\s*=\s*'([^']+)'\s*$", OVERLAY)
        if not found or len(found.group(1).split()) != 4:
            raise ValueError(f"{key} must bind exactly four species")


def check_source(expected_head: str, historical: Path, binary: Path) -> dict:
    if git_head(ROOT) != expected_head or git_head(historical) != HISTORICAL_SHA:
        raise ValueError("Candidate or historical Git source HEAD mismatch")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "--",
                       "physics_app"], check=False).returncode != 0:
        raise ValueError("Candidate PhysicsApp tracked source is dirty")
    if binary.resolve() != (ROOT / "physics_app/physics-opt").resolve():
        raise ValueError("Binary path is not the exact checkout's PhysicsApp binary")
    if not binary.is_file() or binary.stat().st_size == 0:
        raise ValueError("Native build binary missing/empty")
    mesh = historical / p2.CHEM / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
    if not mesh.is_file() or not mesh.stat().st_size:
        raise ValueError("Prepared original S6 public mesh absent")
    if (historical / p2.CHEM / "private_rates").exists():
        raise ValueError("Protected rate folder must not exist in historical checkout")
    return {"source_sha": expected_head, "historical_sha": HISTORICAL_SHA,
            "binary_sha256": sha_file(binary), "historical_mesh_sha256": sha_file(mesh),
            "build_image": OCI}


def run_one(binary: Path, binary_sha: str, workspace: Path,
            inputs: list[str], log: Path, timeout_seconds: int) -> dict:
    if sha_file(binary) != binary_sha:
        raise ValueError("Native P1 executable mutated before P2")
    command = ("/workspace/physics_app/physics-opt --check-input -i " +
               " ".join(shlex.quote(x) for x in inputs))
    args = ["docker", "run", "--rm", "--network", "none",
            "--entrypoint", "/bin/bash", "--user", "0:0",
            "--workdir", "/case",
            "--env", "OXYGEN_RESEARCH_400=1",
            "--env", "OXYGEN_RESEARCH_FULL24=0",
            "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
            "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
            "--mount", f"type=bind,src={ROOT.resolve()},dst=/workspace,readonly",
            "--mount", f"type=bind,src={workspace.resolve()},dst=/case",
            OCI, "-lc", "set -euo pipefail; source /environment; "
            # MOOSE creates root-owned .jitcache during --check-input. Clean
            # only the isolated temporary workspace cache as root on exit,
            # preserving native exit status and avoiding host PermissionError.
            + "trap 'rm -rf /case/.jitcache' EXIT; " + command]
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=timeout_seconds, check=False)
        out = result.stdout + "\n" + result.stderr
        log.write_text(out)
        good = result.returncode == 0 and "Syntax OK" in out
        if good:
            classification = "NATIVE_CHECK_INPUT_PASS"
        elif result.returncode == 127 and "error while loading shared libraries" in out:
            classification = "NATIVE_RUNTIME_LINKER_ERROR"
        elif result.returncode == 127:
            classification = "NATIVE_PROCESS_FAILED_BEFORE_INPUT"
        else:
            classification = "NATIVE_CHECK_INPUT_REJECTED"
        return {"P2": "PASS" if good else "HOLD",
                "exit_code": result.returncode, "log_sha256": sha_file(log),
                "syntax_ok": "Syntax OK" in out, "classification": classification}
    except subprocess.TimeoutExpired:
        log.write_text("P2 timeout, no solve was launched\n")
        return {"P2": "HOLD", "classification": "NATIVE_CHECK_INPUT_TIMEOUT",
                "log_sha256": sha_file(log)}


def execute(historical: Path, binary: Path, expected_head: str,
            evidence: Path, timeout_seconds: int = 1200) -> dict:
    validate_overlay()
    public = p2.preflight(ROOT)
    identity = check_source(expected_head, historical, binary)
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"gate": "Issue402 S6 option-only public P2",
              "status": "HOLD", "science": "SCIENCE_HOLD", "P0": "PASS",
              "P1": "PASS_SOURCE_BOUND_BINARY",
              "P2": "HOLD", "P3": "NOT_RUN", "P4": "NOT_RUN",
              "identity": identity,
              "original_immutable_candidate_sha": p2.PINNED_CANDIDATE,
              "public_deck_manifest_sha256": sha_file(
                  ROOT / p2.DECKS / "manifest.json"),
              "option_overlay_sha256": OVERLAY_SHA256,
              "checks": {}}
    if public.get("P0") != "PASS":
        raise ValueError("Public reference P0 is not PASS")
    with tempfile.TemporaryDirectory(prefix="issue402_option_s6_p2_",
                                     dir=os.getenv("RUNNER_TEMP", None)) as tmp:
        root = Path(tmp)
        manifest = json.loads((ROOT / p2.DECKS / "manifest.json").read_text())
        for case in CASES:
            report["checks"][case] = {}
            for variant in VARIANTS:
                label = f"{case}_{variant}"
                staged = root / label
                try:
                    old_variant = "B" if variant == "B" else "C"
                    ordered = p2.stage(ROOT, historical, case, old_variant,
                                       staged, manifest)
                    if variant == "D":
                        overlay = staged / p2.CHEM / "migrated_continuity.i"
                        # Only a regenerated sidecar is changed. Never edit any
                        # archived source layer, table or preserved baseline.
                        if not overlay.is_file():
                            raise ValueError("Expected original C migration sidecar is missing")
                        overlay.write_text(OVERLAY, encoding="utf-8")
                        if sha_file(overlay) != OVERLAY_SHA256:
                            raise ValueError("Staged D sidecar SHA is incorrect")
                    log = evidence / f"S6_{label}_P2.log"
                    report["checks"][case][variant] = run_one(
                        binary, identity["binary_sha256"], staged, ordered,
                        log, timeout_seconds)
                    report["checks"][case][variant]["layers"] = len(ordered)
                except Exception as exc:
                    report["checks"][case][variant] = {
                        "P2": "HOLD", "classification": type(exc).__name__,
                        "error": str(exc)[:250]}
    checks = [report["checks"][c][v]["P2"] for c in CASES for v in VARIANTS]
    report["P2"] = "PASS" if checks == ["PASS"] * 4 else "HOLD"
    report["status"] = "PASS" if report["P2"] == "PASS" else "HOLD"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.historical.resolve(), args.binary.resolve(),
                         args.expected_head, args.evidence.resolve())
        exit_code = 0 if result["P2"] == "PASS" else 3
    except Exception as exc:
        result = {"gate": "Issue402 S6 option-only public P2",
                  "status": "HOLD", "P2": "HOLD", "P3": "NOT_RUN", "P4": "NOT_RUN",
                  "science": "SCIENCE_HOLD",
                  "classification": type(exc).__name__, "blocker": str(exc)[:400]}
        exit_code = 3
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / "issue402_option_s6_p2_status.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
