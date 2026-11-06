#!/usr/bin/env python3
"""Issue471 native runtime-closure discriminator. NOT scientific acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.Issue282_e2a_rz_bridge.probe_parser_family import mini_input
from experiments.Issue282_e2a_rz_bridge.run_native import IMAGE

BASE = ("ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:"
        "2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
MODES = ("mini_base", "mini_generic", "mini_ad", "mini_ad_jitoff", "mini_nested_jitoff")
DEFAULT = ROOT / "experiments" / "Issue471_ad_parser_runtime" / "evidence"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def persist(root: Path, data: dict) -> None:
    (root / "manifest.json").write_text(
        json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def prepare(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    cases = {}
    for mode in MODES:
        folder = root / mode
        folder.mkdir(exist_ok=True)
        path = folder / "input.i"
        source = mini_input(mode).encode()
        if path.exists() and path.read_bytes() != source:
            raise ValueError("stale diagnostic input: " + mode)
        path.write_bytes(source)
        cases[mode] = {"sha256": digest(path)}
    report = {
        "issue": 471, "kind": "RUNTIME_JIT_CLOSURE_DIAGNOSTIC",
        "science_acceptance": "NOT_EVALUATED",
        "runtime": IMAGE, "build_base": BASE,
        "source_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "cases": cases, "runs": {}, "verdict": "PREPARED_ONLY",
    }
    persist(root, report)
    return report


def capture(cmd: list[str], log: Path, timeout: int = 180) -> int:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log.write_text(
            "returncode: " + str(p.returncode) + "\nstdout:\n" + p.stdout
            + "\nstderr:\n" + p.stderr, encoding="utf-8",
        )
        return p.returncode
    except subprocess.TimeoutExpired:
        log.write_text("TIMED_OUT\n", encoding="utf-8")
        return 124
    except Exception as exc:
        log.write_text("EXCEPTION " + repr(exc) + "\n", encoding="utf-8")
        return 125


def info(image: str) -> dict:
    p = subprocess.run(
        ["docker", "image", "inspect", image], check=True,
        capture_output=True, text=True,
    )
    doc = json.loads(p.stdout)[0]
    labels = doc.get("Config", {}).get("Labels") or {}
    return {
        "id": doc.get("Id"), "os": doc.get("Os"), "arch": doc.get("Architecture"),
        "repo_digests": doc.get("RepoDigests"),
        "labels": {k: labels.get(k) for k in (
            "io.physics.build-base.ref", "io.physics.moose.sha",
            "org.opencontainers.image.revision", "io.physics.runtime.base",
        )},
    }


def original_command(case: Path, args: list[str]) -> list[str]:
    return [
        "docker", "run", "--rm", "--network", "none", "-w", "/work",
        "-v", str(case) + ":/work", IMAGE, *args,
    ]


def build_command(case: Path, physics: Path, args: list[str]) -> list[str]:
    return [
        "docker", "run", "--rm", "--network", "none",
        "--entrypoint", "/bin/bash", "-w", "/work",
        "-v", str(case) + ":/work",
        "-v", str(physics) + ":/opt/physics:ro",
        BASE, "-lc",
        'source /environment; '
        'export LD_LIBRARY_PATH="/opt/physics/lib:/opt/physics/test/lib:$LD_LIBRARY_PATH"; '
        'exec /opt/physics/physics-opt "$@"',
        "physics-opt", *args,
    ]


def copy_binary(dest: Path) -> Path:
    cid = subprocess.check_output(["docker", "create", IMAGE], text=True).strip()
    try:
        subprocess.run(["docker", "cp", cid + ":/opt/physics", str(dest)], check=True)
        physics = dest / "physics"
        if not (physics / "physics-opt").is_file():
            raise ValueError("original executable missing from immutable image")
        return physics
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)


def loader_probe(physics: Path, root: Path) -> int:
    return capture([
        "docker", "run", "--rm", "--network", "none",
        "--entrypoint", "/bin/bash",
        "-v", str(physics) + ":/opt/physics:ro", BASE, "-lc",
        'source /environment; '
        'export LD_LIBRARY_PATH="/opt/physics/lib:/opt/physics/test/lib:$LD_LIBRARY_PATH"; '
        'printf "CXX_PROBES\\n"; for c in c++ g++ clang++ mpicxx; do command -v "$c" || true; done; '
        'printf "DYNAMIC_LIBRARIES\\n"; ldd /opt/physics/physics-opt; '
        'if ldd /opt/physics/physics-opt | grep -q "not found"; then exit 4; fi',
    ], root / "build-base-loader.txt")


def run_modes(root: Path, report: dict, label: str, physics: Path | None) -> None:
    rows = report["runs"][label] = {}
    for mode in MODES:
        case = root / mode
        if digest(case / "input.i") != report["cases"][mode]["sha256"]:
            raise ValueError("changed diagnostic input " + mode)
        def command(args: list[str]) -> list[str]:
            if physics is None:
                return original_command(case, args)
            return build_command(case, physics, args)
        p2 = capture(
            command(["--check-input", "-i", "input.i"]),
            root / (label + "-" + mode + "-p2.log"),
        )
        p3 = None
        if p2 == 0:
            p3 = capture(
                command(["-i", "input.i"]),
                root / (label + "-" + mode + "-p3.log"),
            )
        rows[mode] = {"p2": p2, "p3": p3}
        persist(root, report)


def passed(data: dict, mode: str) -> bool:
    return data.get(mode, {}).get("p2") == 0 and data.get(mode, {}).get("p3") == 0


def verdict(report: dict) -> str:
    old = report["runs"].get("scratch", {})
    base = report["runs"].get("build_base_with_original_binary", {})
    if not all(passed(old, x) for x in ("mini_base", "mini_generic")):
        return "INCONCLUSIVE_SCRATCH_CONTROLS"
    if not (
        old.get("mini_ad", {}).get("p2") not in (None, 0)
        and old.get("mini_ad_jitoff", {}).get("p2") == 0
        and old.get("mini_ad_jitoff", {}).get("p3") in (139, -11)
    ):
        return "INCONCLUSIVE_SCRATCH_FAILURE_NOT_REPRODUCED"
    if base.get("status") == "INCOMPARABLE":
        return "INCONCLUSIVE_BUILD_BASE_LOADER"
    if all(passed(base, mode) for mode in MODES):
        return "BUILD_ENV_RESTORED_PATH__LIBRARY_IDENTITY_AUDIT_REQUIRED"
    if all(passed(base, x) for x in ("mini_base", "mini_generic")):
        return "BUILD_ENV_AD_STILL_UNRESOLVED"
    return "INCONCLUSIVE_BUILD_BASE_CONTROLS"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--results", type=Path, default=DEFAULT)
    args = parser.parse_args()
    root = args.results.resolve()
    if not root.is_relative_to(ROOT):
        raise ValueError("evidence must remain in checkout")
    report = prepare(root)
    if args.prepare_only:
        return 0
    try:
        for key, ref in (("runtime", IMAGE), ("build_base", BASE)):
            rc = capture(["docker", "pull", ref], root / (key + "-pull.log"), timeout=900)
            if rc:
                raise RuntimeError("immutable " + key + " pull failed: " + str(rc))
            report[key + "_image"] = info(ref)
            persist(root, report)
        labels = report["runtime_image"]["labels"]
        if labels.get("io.physics.build-base.ref") != BASE:
            raise ValueError("runtime image does not pin expected build base")
        if labels.get("io.physics.moose.sha") != "9f388366ccf38b9c34542ec5561198249fde0ac9":
            raise ValueError("unexpected MOOSE source revision")
        with TemporaryDirectory(prefix="physics471-") as dirname:
            original = copy_binary(Path(dirname))
            report["original_binary_sha256"] = digest(original / "physics-opt")
            rc = loader_probe(original, root)
            report["build_base_loader_rc"] = rc
            run_modes(root, report, "scratch", None)
            if rc == 0:
                run_modes(root, report, "build_base_with_original_binary", original)
            else:
                report["runs"]["build_base_with_original_binary"] = {"status": "INCOMPARABLE"}
        report["verdict"] = verdict(report)
    except Exception as exc:
        report["verdict"] = "INCONCLUSIVE_SETUP"
        report["error"] = repr(exc)
    finally:
        persist(root, report)
    print(json.dumps({"verdict": report["verdict"]}, sort_keys=True))
    return 0 if report["verdict"] in (
        "BUILD_ENV_RESTORED_PATH__LIBRARY_IDENTITY_AUDIT_REQUIRED",
        "BUILD_ENV_AD_STILL_UNRESOLVED",
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
