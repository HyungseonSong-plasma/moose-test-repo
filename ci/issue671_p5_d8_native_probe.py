#!/usr/bin/env python3
"""Issue #671: source-bound actual S6 New-only P2 check-input diagnostic only.

Does NOT grant P5 Native P2 acceptance: P4-X source integration and dynamic
Functor/Warehouse evaluation must be completed separately. No time stepping.
Never publish raw private EI rate data or edit archived/root source input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import zipfile

ARCHIVED_HEAD = "9c15a4f0e2cf8042cb0d4b2f18af31511021d168"
P3X_ARTIFACT_SHA = "592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111"
P3X_ARTIFACT_SOURCE_HEAD = "c965e69cc9648a16c86cbbc194b730f18f9d95aa"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
CASES = ("417", "941")
EXPECTED_C0 = "d78a084434eca25b9ece07138c49bf93800845f5947f5ec327bfc81334daa17a"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def prepare(artifact: Path, out: Path) -> dict:
    """Extract ONLY public source-stage inputs, rejecting symlinks and traversal."""
    if sha_file(artifact) != P3X_ARTIFACT_SHA:
        raise ValueError("P5_D8_PINNED_P3X_ARTIFACT_ZIP_SHA_MISMATCH")
    if out.exists():
        raise ValueError("P5_D8_REFUSE_EXISTING_DISPOSABLE_SCRATCH")
    out.mkdir(parents=True)
    cases = {}
    with zipfile.ZipFile(artifact) as z:
        names = z.namelist()
        for case in CASES:
            prefix = f"cases/{case}/"
            manifest = json.loads(z.read(prefix + "case_manifest.json"))
            stage = json.loads(z.read(prefix + "newonly_stage_receipt.json"))
            ordered = manifest.get("ordered_input_paths", [])
            if (manifest.get("source_head") != ARCHIVED_HEAD or
                    str(manifest.get("case")) != case or len(ordered) != 11 or
                    len({Path(x).name for x in ordered}) != 11):
                raise ValueError("P5_D8_ORIGINAL_SOURCE_OR_ORDER_PIN_DRIFT_" + case)
            if (stage.get("source_head") != ARCHIVED_HEAD or
                    stage.get("variant") != case or
                    stage.get("retired_native_ion_owners") != 26 or
                    stage.get("p3_x_electron", {}).get("removed_native_electron_owners") != 10 or
                    stage.get("remaining_native_ion_fv_owners") != 0):
                raise ValueError("P5_D8_P2_P3_SOURCE_CUTOVER_NOT_VERIFIED_" + case)
            work = out / case
            work.mkdir()
            files = 0
            for info in z.infolist():
                if not info.filename.startswith(prefix + "experiments/") or info.is_dir():
                    continue
                rel = info.filename[len(prefix):]
                parts = Path(rel).parts
                if (not parts or parts[0] != "experiments" or
                    Path(rel).is_absolute() or ".." in parts or
                    (info.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError("P5_D8_UNSAFE_PUBLIC_ARTIFACT_PATH")
                target = work.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                data = z.read(info)
                target.write_bytes(data)
                files += 1
            if files < 15:
                raise ValueError("P5_D8_MISSING_CHILD_MESH_TABLE_AND_11_LAYERS_" + case)
            layer_sha = {}
            for rel in ordered:
                if Path(rel).is_absolute() or ".." in Path(rel).parts:
                    raise ValueError("P5_D8_UNSAFE_11_LAYER_PATH")
                target = work / rel
                if not target.is_file() or target.is_symlink():
                    raise ValueError("P5_D8_MISSING_EXACT_STAGE_LAYER_" + rel)
                got = sha_file(target)
                if got != stage["layers_after_sha256"][Path(rel).name]:
                    raise ValueError("P5_D8_P3X_FINAL_LAYER_SHA_MISMATCH_" + rel)
                layer_sha[Path(rel).name] = got
            if layer_sha[Path(ordered[0]).name] != EXPECTED_C0:
                raise ValueError("P5_D8_P3X_C0_RETIREMENT_SHA_MISMATCH_" + case)
            jpath = work / ("experiments/Issue395_powered_chemistry_ladder/"
                            f"chemistry/unified_s6_{case}_newonly.json")
            epath = work / "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
            if (sha_file(jpath) != stage["json_sha256"] or
                    sha_file(epath) != stage["electron_moments_sha256"] or
                    len(epath.read_bytes().splitlines()) != 42):
                raise ValueError("P5_D8_MECHANISM_OR_ELECTRON_TABLE_PIN_MISMATCH_" + case)
            child = work / ("experiments/Issue395_powered_chemistry_ladder/"
                            "rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_child.i")
            if sha_file(child) != stage["child_include_sha256"][child.name]:
                raise ValueError("P5_D8_REAL_MAXWELL_CHILD_SHA_MISMATCH_" + case)
            mesh = work / "experiments/Issue18_qvt_plasma_mapping/qvt.msh"
            if sha_file(mesh) != stage["mesh_sha256"]:
                raise ValueError("P5_D8_REAL_MAXWELL_MESH_SHA_MISMATCH_" + case)
            cases[case] = {"workspace": str(work), "ordered": ordered,
                           "source_files": files, "layer_sha256": layer_sha,
                           "child_sha256": sha_file(child), "mesh_sha256": sha_file(mesh),
                           "json_sha256": sha_file(jpath),
                           "electron_table_sha256": sha_file(epath)}
    return cases


def run_case(case: str, stage: dict, source: Path, binary_sha: str,
             output: Path, timeout: int) -> dict:
    work = Path(stage["workspace"])
    exe = source / "physics_app/physics-opt"
    if sha_file(exe) != binary_sha:
        raise ValueError("P5_D8_BINARY_CHANGED_BEFORE_CHECK_INPUT")
    # All actual 11 staged layers in original order; no fake/synthetic decks.
    command = ("/workspace/physics_app/physics-opt --check-input -i " +
               " ".join(shlex.quote(p) for p in stage["ordered"]))
    args = [
        "docker", "run", "--rm", "--network", "none",
        "--entrypoint", "/bin/bash", "--user", "0:0",
        "--workdir", "/case",
        "--env", "OXYGEN_RESEARCH_400=1",
        "--env", "OXYGEN_RESEARCH_FULL24=0",
        "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
        "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
        "--mount", f"type=bind,src={source},dst=/workspace,readonly",
        "--mount", f"type=bind,src={work},dst=/case",
        OCI, "-lc",
        "set -uo pipefail; source /environment; " +
        "trap 'rm -rf /case/.jitcache' EXIT; " + command
    ]
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              check=False, timeout=timeout)
        combined = proc.stdout + "\n" + proc.stderr
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        combined, rc = "NATIVE_P2_CHECK_INPUT_TIMEOUT_NO_SOLVE\n", 124
    log = output / f"S6-{case}_native_check_input.log"
    log.write_text(combined)
    if sha_file(exe) != binary_sha:
        raise ValueError("P5_D8_BINARY_MUTATED_DURING_RUN")
    success = rc == 0 and "Syntax OK" in combined
    # Explicitly distinguish the uncompleted P4 owner handoff.
    return {"case": case, "input_11_layers_sha_verified": 11,
            "exit_code": rc, "syntax_ok": success,
            "native_probe": "CHECK_INPUT_SYNTAX_OK_BUT_NOT_P5_ACCEPTED" if success else
                            "CHECK_INPUT_REJECTED_P4_UNINTEGRATED",
            "diagnostic_log_sha256": sha_file(log),
            "science": "SCIENCE_HOLD", "native_P3": "NOT_RUN", "native_P4": "NOT_RUN"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--repo-head", required=True)
    ap.add_argument("--timeout", type=int, default=360)
    ap.add_argument("--stage-only", action="store_true")
    args = ap.parse_args()
    source = args.source.resolve(strict=True)
    if args.timeout < 1 or args.repo_head != subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip():
        raise ValueError("P5_D8_ACTIVE_SOURCE_HEAD_PIN_MISMATCH")
    cases = prepare(args.artifact, args.output / "scratch")
    result = {
        "schema": "issue671.p5_d8_newonly_diagnostic.v1",
        "status": "SOURCE_STAGE_ONLY_P4_NOT_COMPLETED",
        "source_head": args.repo_head,
        "artifact_expected_head": P3X_ARTIFACT_SOURCE_HEAD,
        "p3x_artifact_sha256": P3X_ARTIFACT_SHA,
        "build_base": OCI, "cases": {},
        "stage_cases": {key: {k: v for k, v in stage.items() if k != "workspace"}
                        for key, stage in cases.items()},
        "P4_X": "NOT_INTEGRATED", "P5_NATIVE_P2": "HOLD",
        "D8_newonly_dynamic_liveness": "NOT_PROVED_BY_CHECK_INPUT",
        "science": "SCIENCE_HOLD",
    }
    if not args.stage_only:
        binary = source / "physics_app/physics-opt"
        if not binary.is_file():
            raise ValueError("P5_D8_EXACT_SOURCE_NATIVE_BINARY_NOT_PRESENT")
        binary_sha = sha_file(binary)
        result["binary_sha256"] = binary_sha
        for case, stage in cases.items():
            result["cases"][case] = run_case(
                case, stage, source, binary_sha, args.output, args.timeout)
        result["status"] = "DIAGNOSTIC_EXECUTED_P4_NOT_INTEGRATED_P5_HOLD"
    (args.output / "readiness.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"],
                      "cases": {k: x["native_probe"] for k, x in result["cases"].items()},
                      "P5": result["P5_NATIVE_P2"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
