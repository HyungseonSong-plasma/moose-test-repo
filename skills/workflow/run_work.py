#!/usr/bin/env python3
"""Deterministic fail-closed executor for experiment/refactor manifests."""
from __future__ import annotations
import argparse
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from work_manifest import ManifestError, load_manifest, validate_dispatch

def _git_head(workspace: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        text=True,
    ).strip()

def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False

def _copy_artifacts(
    workspace: Path, patterns: tuple[str, ...], target: Path
) -> list[str]:
    copied: list[str] = []
    for pattern in patterns:
        for raw in sorted(
            glob.glob(str(workspace / pattern), recursive=True)
        ):
            source = Path(raw)
            if not source.is_file() or not _under(source, workspace):
                continue
            relative = source.resolve().relative_to(workspace.resolve())
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(str(relative))
    return copied

def execute(args: argparse.Namespace) -> int:
    control_root = Path(args.control_root).resolve()
    workspace = Path(args.workspace).resolve()
    results = Path(args.results).resolve()
    manifest_path = Path(args.manifest).resolve()
    expected_dir = (
        control_root
        / "automation"
        / "manifests"
        / ("experiments" if args.kind == "experiments" else "refactors")
    )
    if not _under(manifest_path, expected_dir):
        raise ManifestError(f"manifest must be below {expected_dir}")

    manifest = load_manifest(manifest_path)
    validate_dispatch(
        manifest,
        kind=args.kind,
        issue=args.issue,
        sequence=args.sequence,
    )
    actual_head = _git_head(workspace)
    if actual_head != args.base_sha:
        raise ManifestError(
            f"workspace SHA mismatch: actual={actual_head} expected={args.base_sha}"
        )

    results.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, object] = {
        "schema_version": 1,
        "identity": manifest.identity,
        "title": manifest.title,
        "issue": manifest.issue,
        "kind": manifest.kind,
        "sequence": manifest.sequence,
        "base_sha": args.base_sha,
        "result": "FAIL",
        "stages": [],
        "artifacts": [],
    }
    env = os.environ.copy()
    env.update({
        "PHYSICS_WORK_ID": manifest.identity,
        "PHYSICS_BASE_SHA": args.base_sha,
        "PHYSICS_RESULTS_DIR": str(results),
    })

    failure = None
    for stage in manifest.stages:
        record: dict[str, object] = {
            "id": stage.stage_id,
            "name": stage.name,
            "command": list(stage.command),
            "cwd": stage.cwd,
            "timeout_seconds": stage.timeout_seconds,
            "status": "FAIL",
        }
        log_path = results / f"{stage.stage_id}.log"
        started = time.perf_counter()
        try:
            cwd = workspace if stage.cwd == "." else workspace / stage.cwd
            if not _under(cwd, workspace) or not cwd.is_dir():
                raise RuntimeError(f"invalid stage cwd: {cwd}")
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    list(stage.command),
                    cwd=cwd,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=stage.timeout_seconds,
                    check=False,
                    text=True,
                )
            record["returncode"] = completed.returncode
            if completed.returncode == 0:
                record["status"] = "PASS"
            else:
                failure = {
                    "class": "NONZERO_EXIT",
                    "stage": stage.stage_id,
                    "returncode": completed.returncode,
                }
        except subprocess.TimeoutExpired:
            record["returncode"] = 124
            failure = {
                "class": "TIMEOUT",
                "stage": stage.stage_id,
                "returncode": 124,
            }
        except Exception as exc:
            record["returncode"] = None
            failure = {
                "class": "EXECUTION_ERROR",
                "stage": stage.stage_id,
                "detail": str(exc),
            }
        record["wall_seconds"] = round(
            time.perf_counter() - started, 6
        )
        evidence["stages"].append(record)
        if failure is not None:
            break

    evidence["artifacts"] = _copy_artifacts(
        workspace,
        manifest.artifacts,
        results / "artifacts",
    )
    if (
        failure is None
        and len(evidence["stages"]) == len(manifest.stages)
    ):
        evidence["result"] = "PASS"
    else:
        evidence["failure"] = (
            failure or {"class": "INCOMPLETE_EXECUTION"}
        )
    (results / "evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"WORK_ID={manifest.identity}")
    print(f"RESULT={evidence['result']}")
    print(f"EVIDENCE={results / 'evidence.json'}")
    return 0 if evidence["result"] == "PASS" else 1

def self_test() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        control = root / "control"
        workspace = root / "workspace"
        manifests = (
            control / "automation" / "manifests" / "experiments"
        )
        manifests.mkdir(parents=True)
        workspace.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(workspace)], check=True
        )
        subprocess.run(
            [
                "git", "-C", str(workspace), "config",
                "user.email", "test@example.invalid",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(workspace), "config",
                "user.name", "test",
            ],
            check=True,
        )
        (workspace / "x.txt").write_text("x\n")
        subprocess.run(
            ["git", "-C", str(workspace), "add", "x.txt"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(workspace), "commit", "-qm", "x"],
            check=True,
        )
        sha = _git_head(workspace)
        manifest = manifests / "Issue_1_experiments01.json"
        manifest.write_text(json.dumps({
            "schema_version": 1,
            "issue": 1,
            "kind": "experiments",
            "sequence": 1,
            "title": "self-test",
            "stages": [{
                "id": "P0",
                "name": "pass",
                "command": [sys.executable, "-c", "print('ok')"],
            }],
            "artifacts": ["x.txt"],
        }))
        namespace = argparse.Namespace(
            kind="experiments",
            manifest=str(manifest),
            control_root=str(control),
            workspace=str(workspace),
            base_sha=sha,
            issue=1,
            sequence=1,
            results=str(root / "results"),
        )
        if execute(namespace) != 0:
            return 1
        data = json.loads(
            (root / "results" / "evidence.json").read_text()
        )
        assert data["result"] == "PASS"
        assert data["stages"][0]["status"] == "PASS"
    print("WORK_RUNNER_SELF_TEST=PASS")
    return 0

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--kind", choices=["experiments", "refactor"]
    )
    parser.add_argument("--manifest")
    parser.add_argument("--control-root")
    parser.add_argument("--workspace")
    parser.add_argument("--base-sha")
    parser.add_argument("--issue", type=int)
    parser.add_argument("--sequence", type=int)
    parser.add_argument("--results")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    required = (
        args.kind, args.manifest, args.control_root, args.workspace,
        args.base_sha, args.issue, args.sequence, args.results,
    )
    if any(value is None for value in required):
        parser.error("all execution arguments are required")
    try:
        return execute(args)
    except ManifestError as exc:
        print(f"WORK_MANIFEST_ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
