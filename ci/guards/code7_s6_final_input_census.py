#!/usr/bin/env python3
"""Code7 G2: read-only census of the exact S6-417/941 Native P2 input layers.

Only emits source-bound declared type evidence, never runtime/caller-zero or science PASS.
No staged .i, mesh, rate tables, or historical inputs are copied to artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
TARGET = "PhysicsFVThermalDiffusion"
HISTORICAL = "QPXFVThermalDiffusion"
DECKS = "experiments/Issue493_s6_boltzmann/public_p2_decks/manifest.json"
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
CASES = ("417", "941")
TYPE = re.compile(r"(?m)^[ \t]*type\s*=\s*([^#\n]+?)\s*(?:#.*)?$")
INCLUDE = re.compile(r"(?m)^[ \t]*!include\s+([^\n#]+)")
SIMPLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_path(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or not value.parts:
        raise ValueError("G2_UNSAFE_LAYER_PATH:" + relative)
    path = root.joinpath(*value.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("G2_LAYER_OUTSIDE_STAGE:" + relative)
    return path


def census_layers(stage: Path, layer_names: list[str]) -> dict:
    """Scan each exact Native -i layer and its literal !include closure."""
    todo = [(pinned_path(stage, str(CHEM / name)), str(CHEM / name))
            for name in layer_names]
    seen: set[Path] = set()
    inputs, declarations, unresolved = [], [], []
    while todo:
        path, label = todo.pop(0)
        if path in seen:
            continue
        if not path.is_file():
            raise ValueError("G2_INPUT_MISSING:" + label)
        seen.add(path)
        raw = path.read_text(encoding="utf-8")
        inputs.append({"path": path.relative_to(stage).as_posix(),
                       "sha256": sha256(path)})
        for match in TYPE.finditer(raw):
            value = match.group(1).strip().strip("'\"")
            line = raw.count("\n", 0, match.start()) + 1
            if SIMPLE.fullmatch(value):
                declarations.append({"path": path.relative_to(stage).as_posix(),
                                     "line": line, "type": value})
            else:
                unresolved.append({"path": path.relative_to(stage).as_posix(),
                                   "line": line, "reason": "NONLITERAL_TYPE"})
        for match in INCLUDE.finditer(raw):
            token = match.group(1).strip().strip("'\"")
            line = raw.count("\n", 0, match.start()) + 1
            if not token or any(char in token for char in "$`{}"):
                unresolved.append({"path": path.relative_to(stage).as_posix(),
                                   "line": line, "reason": "DYNAMIC_INCLUDE"})
                continue
            included = pinned_path(stage, str(path.parent.relative_to(stage) / token))
            todo.append((included, included.relative_to(stage).as_posix()))
    current = [x for x in declarations if x["type"] == TARGET]
    history = [x for x in declarations if x["type"] == HISTORICAL]
    return {"files": sorted(inputs, key=lambda x: x["path"]),
            "file_count": len(inputs),
            "declared_type_count": len(declarations),
            "declared_current": current,
            "declared_historical_qpx": history,
            "unresolved_type_or_include": sorted(
                unresolved, key=lambda x: (x["path"], x["line"]))}


def audit(root: Path, source_sha: str, evidence: Path) -> dict:
    if subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                               text=True).strip() != source_sha:
        raise ValueError("G2_EXACT_HEAD_MISMATCH")
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain",
                                "--untracked-files=no"], text=True).strip():
        raise ValueError("G2_TRACKED_WORKTREE_DIRTY")
    manifest = json.loads((root / DECKS).read_text(encoding="utf-8"))
    receipt = {"schema": "code7.s6_final_input_census.v0.1", "source_head": source_sha,
               "target": TARGET, "cases": {}, "verified_no_declared_target": False,
               "native_instantiation": "NOT_OBSERVED", "external_caller_zero": "NOT_PROVEN",
               "safe_delete": "HOLD", "status": "HOLD"}
    binary_shas = set()
    for case in CASES:
        folder = evidence / ("S6-" + case)
        status_path = folder / "status.json"
        if not status_path.is_file():
            raise ValueError("G2_NATIVE_STATUS_MISSING:" + case)
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if (status.get("case") != case or status.get("source_sha") != source_sha
                or status.get("P2") != "PASS" or status.get("P3") != "NOT_RUN"
                or status.get("native_check", {}).get("syntax_ok") is not True):
            raise ValueError("G2_S6_NATIVE_P2_NOT_SOURCE_PINNED_PASS:" + case)
        if status.get("native_check", {}).get("exit_code") != 0:
            raise ValueError("G2_S6_NATIVE_P2_NONZERO:" + case)
        binary = status.get("binary_sha256")
        if not isinstance(binary, str) or len(binary) != 64:
            raise ValueError("G2_NATIVE_BINARY_IDENTITY_MISSING:" + case)
        binary_shas.add(binary)
        names = manifest["cases"][case]["input_order"] + ["migrated_continuity.i"]
        if len(names) != 11 or len(set(names)) != 11:
            raise ValueError("G2_S6_NATIVE_11_LAYER_CONTRACT:" + case)
        stage = folder / "scratch_hybrid"
        result = census_layers(stage, names)
        result.update({"native_p2": "PASS", "binary_sha256": binary,
                       "ordered_layers": names,
                       "ordered_layer_sha256": [
                           {"path": str(CHEM / n),
                            "sha256": sha256(pinned_path(stage, str(CHEM / n)))}
                           for n in names]})
        receipt["cases"][case] = result
    if len(binary_shas) != 1:
        raise ValueError("G2_CASES_DO_NOT_SHARE_EXACT_BINARY")
    receipt["binary_sha256"] = next(iter(binary_shas))
    blockers = []
    for case, result in receipt["cases"].items():
        if result["declared_current"]:
            blockers.append(case + ":DECLARED_TARGET_PRESENT")
        if result["unresolved_type_or_include"]:
            blockers.append(case + ":UNRESOLVED_TYPE_OR_INCLUDE")
    receipt["blocking_reasons"] = blockers
    receipt["verified_no_declared_target"] = not blockers
    receipt["status"] = ("SCOPED_DECLARED_ABSENCE_OBSERVED"
                         if not blockers else "HOLD_INPUT_UNRESOLVED")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    try:
        result = audit(Path(args.root).resolve(), args.expected_head,
                       Path(args.evidence_root).resolve())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        result = {"schema": "code7.s6_final_input_census.v0.1",
                  "source_head": args.expected_head, "status": "HOLD",
                  "verified_no_declared_target": False,
                  "safe_delete": "HOLD", "error": str(exc)[:400]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print("CODE7_G2_INPUT_CENSUS=" + result["status"])
    print("CODE7_SAFE_DELETE=HOLD")
    return 0 if result["verified_no_declared_target"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
