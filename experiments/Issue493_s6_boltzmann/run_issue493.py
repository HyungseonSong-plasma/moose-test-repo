#!/usr/bin/env python3
"""Issue #493: reproducible isolated S6 old-template / partial-migration native runs.

Requires a TRUSTED Docker host with two already checked-out source trees:
* candidate: reviewed PR #491 commit (builds physics_app/physics-opt)
* historical: original S6 source with its mesh/material dependencies prepared

The original private-rate secret is never read by this tool. New research
rates are read from the user-owned ZIP, staged to local restricted workspaces,
and are never sent to GitHub or OCI registries by this tool.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PACKAGE_SHA256 = "bde3ab04b2cc80762e1ad25931a25f42b0f295c8695917f2e52041e0755adba6"
CANDIDATE_SHA = "bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947"
HISTORICAL_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
IMAGE = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
N_A = 6.02214076e23
CASES = {"417": "S6-417-407-2069-H25", "941": "S6-941-407-2069-H25"}
VARIANTS = ("old_template_new_rates", "partial_new_template_new_rates")
EXPECTED_IDS = {"417": {"401", "407", "415", "2069", "417"}, "941": {"401", "407", "415", "2069", "941"}}


class RunError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fail_if(condition: bool, message: str) -> None:
    if condition:
        raise RunError(message)


def preflight(zip_path: Path, unpack_dir: Path) -> dict:
    fail_if(sha256(zip_path) != PACKAGE_SHA256, "research package SHA-256 mismatch")
    fail_if(unpack_dir.exists(), "unpack target already exists (refusing overwrite)")
    unpack_dir.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            dest = (unpack_dir / info.filename).resolve()
            fail_if(not dest.is_relative_to(unpack_dir.resolve()), "unsafe path in ZIP")
        archive.extractall(unpack_dir)
    data = json.loads((unpack_dir / "experiment_manifest.json").read_text())
    fail_if(data.get("schema") != "s6_newrate_partial_plasma_dsl_experiment_v1", "unexpected manifest schema")
    fail_if(data.get("baseline_science_status") != "SCIENCE_HOLD", "science contract not HOLD")
    fail_if(data.get("table_count") != 19 or len(data.get("table_provenance", [])) != 19, "unexpected table count")
    fail_if(data.get("new_tables_unit_transform") != "N_A * physical_m3_s", "rate conversion changed")
    fail_if(data.get("avogadro") != N_A, "Avogadro constant changed")
    table_dir = unpack_dir / "new_rate_tables_moose_raw"
    fail_if(len(list(table_dir.glob("EI-*.txt"))) != 19, "unexpected rate directory contents")
    for rec in data["table_provenance"]:
        table = table_dir / rec["file"]
        fail_if(not table.is_file() or sha256(table) != rec["moose_sha256"], "rate file hash mismatch: " + rec["file"])
        rows = []
        for line in table.read_text().splitlines():
            a = line.split()
            fail_if(len(a) != 2, "rate row is not 2 columns: " + rec["file"])
            x, k = map(float, a)
            fail_if(not all(map(math.isfinite, (x, k))) or k < 0, "invalid finite or negative coefficient")
            rows.append((x, k))
        fail_if(len(rows) != 100 or rec["rows"] != 100, "rate grid is not 100 rows")
        fail_if(any(b[0] <= a[0] for a, b in zip(rows, rows[1:])), "non-monotonic energy grid")
        x_min, x_max = rec["mean_energy_range_eV"]
        fail_if(not (math.isclose(rows[0][0], x_min, abs_tol=1e-10) and math.isclose(rows[-1][0], x_max, abs_tol=1e-10)), "lookup domain mismatch")
    fail_if(len(data.get("cases", [])) != 2, "two cases required")
    migration_by_case = {r["case"]: r for r in data.get("migration_provenance", [])}
    fail_if(set(migration_by_case) != {"417", "941"}, "migration provenance does not cover both cases")
    for key, case in CASES.items():
        rec = next((r for r in data["cases"] if r["case"] == case), None)
        fail_if(rec is None or rec["source_sha"] != HISTORICAL_SHA, "historical source mismatch: " + case)
        fail_if(rec["archive_reference_timepoints"] != 461, "not 461 archive frames")
        fail_if(rec.get("native_candidate_run") != "NOT_RUN", "unexpected run status in immutable package")
        expected = set(rec["active_replaced_lookup_files"])
        fail_if(len(expected) != 5 or {f.split("_")[0].split("-")[1] for f in expected} != EXPECTED_IDS[key], "wrong active channel mapping")
        archived = unpack_dir / "archived_reference" / case / "plasma.csv"
        fail_if(sha256(archived) != rec["reference_csv_sha256"], "baseline CSV hash mismatch")
        verify_native_csv(archived)
        order = json.loads((unpack_dir / "cases" / case / "input_order.json").read_text())
        fail_if(len(order) != 10 or len(set(order)) != 10 or not all(n.endswith(".i") and "/" not in n for n in order), "invalid ordered input layers")
        for variant in VARIANTS:
            root = unpack_dir / "cases" / case / variant
            inputs = {p.name for p in root.glob("*.i")}
            expected_inputs = set(order) | ({"migrated_continuity.i"} if variant == VARIANTS[1] else set())
            fail_if(inputs != expected_inputs, "unexpected input layer set: " + case + "/" + variant)
            active = set(p.name for p in (root / "private_rates").glob("EI-*.txt"))
            fail_if(active != expected, "unreviewed active rate owner")
            for name in active:
                fail_if(sha256(root / "private_rates" / name) != sha256(table_dir / name), "variant rate does not equal validated new table")
        old_dir = unpack_dir / "cases" / case / VARIANTS[0]
        new_dir = unpack_dir / "cases" / case / VARIANTS[1]
        for name in order[1:]:
            fail_if(sha256(old_dir / name) != sha256(new_dir / name), "unapproved overlay difference: " + name)
        fail_if(sha256(new_dir / "migrated_continuity.i") != migration_by_case[key]["new_template_overlay_sha256"],
                "migrated ContinuityEq overlay hash mismatch")
    return {"package_sha256": PACKAGE_SHA256, "table_count": 19,
            "cases": [CASES[k] for k in CASES], "preflight": "PASS", "science": "HOLD"}


def verify_native_csv(path: Path) -> None:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        fail_if(not reader.fieldnames or "time" not in reader.fieldnames, "CSV has no time")
        times = []
        for row in reader:
            for key, value in row.items():
                fail_if(value is None or not value.strip(), "missing CSV value: " + str(key))
                fail_if(not math.isfinite(float(value)), "nonfinite CSV diagnostic: " + str(key))
            times.append(float(row["time"]))
    fail_if(len(times) != 461, "not 461 native time points: " + str(path))
    fail_if(not math.isclose(times[0], 0, abs_tol=1e-15) or not math.isclose(times[-1], 1e-4, abs_tol=1e-9), "time range is not 0–100us")
    fail_if(any(b <= a for a, b in zip(times, times[1:])), "native timestamps not increasing")


def git_head(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def docker_cmd(mounts: list[tuple[Path, str, str]], workdir: str, command: str) -> list[str]:
    args = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash", "--user", "0:0", "--workdir", workdir,
            "--env", "OXYGEN_RESEARCH_400=1", "--env", "OXYGEN_RESEARCH_FULL24=0",
            "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0", "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0"]
    for path, dst, mode in mounts:
        args.extend(["--mount", f"type=bind,src={path.resolve()},dst={dst},{mode}"])
    return args + [IMAGE, "-lc", "set -euo pipefail; source /environment; " + command]


def run_step(command: list[str], logfile: Path, timeout_s: int) -> None:
    with logfile.open("w") as f:
        f.write("RUN_ATTEMPT_STARTED\n")
        f.flush()
        try:
            ret = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise RunError(f"timeout after {timeout_s}s; see restricted {logfile}") from exc
        fail_if(ret.returncode != 0, f"step failed exit={ret.returncode}; see restricted {logfile}")


def build(candidate: Path, log: Path, expected_sha: str) -> tuple[Path, str]:
    fail_if(git_head(candidate) != expected_sha, "candidate checkout SHA does not match reviewed build source")
    dirty = subprocess.check_output(["git", "-C", str(candidate), "status", "--porcelain", "--untracked-files=all", "--", "physics_app"], text=True)
    fail_if(bool(dirty.strip()), "candidate physics_app working tree is dirty; exact-source build cannot be proven")
    binary = candidate / "physics_app" / "physics-opt"
    fail_if(binary.exists(), "candidate already has a physics-opt; use clean isolated build checkout")
    # Build policy belongs to the reusable Physics harness, not this experiment.
    # The reviewed candidate source can predate the harness; mount the harness
    # checkout read-only, while building only the exact candidate app at /app.
    harness_root = Path(__file__).resolve().parents[2]
    fail_if(not (harness_root / "physics_harness/execution/native_build.py").is_file(),
            "canonical native build harness is missing")
    script = (
        "export MOOSE_DIR=/opt/physics_vendor/moose "
        "CRANE_DIR=/opt/physics_vendor/crane "
        "SQUIRREL_DIR=/opt/physics_vendor/squirrel "
        "ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; "
        "python3 /harness/physics_harness/execution/native_build.py "
        f"--source-root /app --expected-sha {expected_sha} "
        "--profile auto --max-jobs 4 --max-attempts 3 --timeout-seconds 1800 "
        "--log-dir /app/.issue493_p1_build "
        "--report /app/.issue493_p1_build/report.json"
    )
    run_step(docker_cmd([(candidate, "/app", "rw"), (harness_root, "/harness", "ro")],
                        "/app", script), log, 5700)
    fail_if(not binary.is_file(), "Docker returned success without native physics-opt")
    return binary, sha256(binary)


def run_case(key: str, package_dir: Path, candidate: Path, historical: Path,
             run_dir: Path, attempt: str, expected_binary_sha: str, timeout_s: int) -> dict:
    case = CASES[key]
    result = {"case": case, "attempt": attempt, "status": "NOT_STARTED", "science": "HOLD"}
    for variant in VARIANTS:  # IMPORTANT: B then C, sequential within each case
        arm = "B" if variant == VARIANTS[0] else "C"
        target = run_dir / case / variant / attempt
        target.mkdir(parents=True, exist_ok=False)
        workspace = target / "workspace"
        result[arm] = {"status": "NOT_STARTED", "directory": str(target)}
        try:
            args = [sys.executable, str(package_dir / "scripts" / "stage_isolated_workspace.py"),
                    "--prepared-source", str(historical), "--case", key, "--variant", variant,
                    "--out-workspace", str(workspace)]
            proc = subprocess.run(args, capture_output=True, text=True, check=True, timeout=1800)
            description = json.loads(proc.stdout)
            raw = description["input_arg"]
            fail_if(raw[0] != "-i" or len(raw) != (11 if arm == "B" else 12), "bad MOOSE input layer count")
            layers = [str(Path(p).relative_to(workspace)) for p in raw[1:]]
            fail_if(sha256(candidate / "physics_app" / "physics-opt") != expected_binary_sha, "binary mutated after build")
            mounts = [(candidate, "/app", "ro"), (workspace, "/case", "rw")]
            out = workspace / "issue493_outputs" / "run"
            out.mkdir(parents=True)
            exe = "/app/physics_app/physics-opt"
            cmd_in = " ".join(__import__("shlex").quote(x) for x in layers)
            run_step(docker_cmd(mounts, "/case", f"{exe} --check-input -i {cmd_in}"), target / "P2_check_input.log", 1200)
            result[arm]["P2"] = "PASS"
            run_step(docker_cmd(mounts, "/case", f"{exe} -i {cmd_in} Outputs/file_base=issue493_outputs/run/plasma"),
                     target / "P3_solve.log", timeout_s)
            exodus = out / "plasma.e"
            csv_path = out / "plasma.csv"
            fail_if(not exodus.is_file() or exodus.stat().st_size == 0, "missing native Exodus")
            fail_if(not csv_path.is_file(), "missing native CSV")
            verify_native_csv(csv_path)
            result[arm].update({"status": "SOLVED_461_TIMES", "native_exodus_sha256": sha256(exodus),
                                "native_csv_sha256": sha256(csv_path), "P3": "PASS"})
        except Exception as exc:
            result[arm].update({"status": "FAILED", "error": str(exc)})
            result["status"] = "BLOCKED_AFTER_" + arm
            break  # do not hide a failed B by running C
    else:
        result["status"] = "B_C_NATIVE_COMPLETED"
        compare = run_dir / case / "comparison" / attempt
        compare.mkdir(parents=True, exist_ok=False)
        a = package_dir / "archived_reference" / case / "plasma.csv"
        b = run_dir / case / VARIANTS[0] / attempt / "workspace" / "issue493_outputs" / "run" / "plasma.csv"
        c = run_dir / case / VARIANTS[1] / attempt / "workspace" / "issue493_outputs" / "run" / "plasma.csv"
        try:
            run_step([sys.executable, str(package_dir / "scripts" / "compare_native_runs.py"),
                      "--case", key, "--archived", str(a), "--native-old-template-new-rates", str(b),
                      "--native-partial-dsl-new-rates", str(c), "--out", str(compare)],
                     compare / "P4_compare.log", 900)
            result["P4_csv"] = "PASS"
            result["caveat"] = "A-vs-B is not table-only parity unless A' runs on same executable. Full Exodus physics comparison separately required."
        except Exception as exc:
            result["P4_csv"] = "FAILED"
            result["P4_error"] = str(exc)
    status_dir = run_dir / case
    (status_dir / f"status_{attempt}.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    os.umask(0o077)  # protect locally staged candidate coefficients and raw native fields
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-zip", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("preflight", "run"), default="preflight")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--historical", type=Path)
    parser.add_argument("--attempt", default="attempt001")
    parser.add_argument("--candidate-sha", default=CANDIDATE_SHA)
    parser.add_argument("--timeout-seconds", type=int, default=19800)
    parser.add_argument("--cases", nargs="+", choices=("417", "941"), default=["417", "941"])
    opts = parser.parse_args()
    if not opts.attempt.isalnum() or opts.timeout_seconds < 1:
        parser.error("attempt must be alphanumeric; timeout must be positive")
    try:
        root = opts.output.resolve()
        root.mkdir(parents=True, exist_ok=True)
        package = root / "verified_package"
        result = preflight(opts.package_zip, package)
        (root / "P0_preflight.json").write_text(json.dumps(result, indent=2) + "\n")
        if opts.mode == "preflight":
            print(json.dumps(result))
            return 0
        fail_if(shutil.which("docker") is None, "Docker is not available on THIS execution host (this does not establish any GitHub Actions runner limitation)")
        fail_if(not opts.candidate or not opts.historical, "run mode needs candidate and historical checkouts")
        candidate, historical = opts.candidate.resolve(), opts.historical.resolve()
        fail_if(git_head(candidate) != opts.candidate_sha, "candidate head mismatch")
        fail_if(git_head(historical) != HISTORICAL_SHA, "historical source head mismatch")
        run_step(["docker", "pull", IMAGE], root / "P1_docker_pull.log", 1800)
        binary, executable_hash = build(candidate, root / "P1_native_build.log", opts.candidate_sha)
        (root / "P1_build.json").write_text(json.dumps({"candidate_sha": opts.candidate_sha,
              "historical_sha": HISTORICAL_SHA, "build_base": IMAGE,
              "executable_sha256": executable_hash, "status": "BUILT", "science": "HOLD"}, indent=2) + "\n")
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(2, len(opts.cases))) as pool:
            futures = [pool.submit(run_case, c, package, candidate, historical,
                                   root / "native_runs", opts.attempt, executable_hash, opts.timeout_seconds)
                       for c in opts.cases]
            cases = [f.result() for f in futures]
        print(json.dumps({"case_status": cases, "science": "HOLD"}, indent=2))
        return 0 if all(c["status"] == "B_C_NATIVE_COMPLETED" and c.get("P4_csv") == "PASS" for c in cases) else 3
    except (OSError, ValueError, subprocess.CalledProcessError, RunError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc), "science": "HOLD"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())