#!/usr/bin/env python3
"""Issue #633 New-only 11-layer input P0 and optional exact-head P2; never P3.

The P0 gate inspects real staged input and JSON bytes. It does not inspect the
MOOSE warehouse or claim that the 12 FV kernels / 12 FV BCs were instantiated.
P1 must build physics-opt in the same trusted job before --p2-only is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

CASES = ("417", "941")
ION_SPECIES = ("O2p", "Om", "Op")
LEGACY_STATES = {"log_ni": "O2p", "log_nm": "Om", "log_nop": "Op"}
BLOCK = re.compile(r"^\s*\[([^\]]*)\]\s*$")
ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class GateError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_blocks(text: str, filename: str) -> list[dict]:
    if re.search(r"(?m)^\s*!include\b", text):
        raise GateError(f"UNRESOLVED_INCLUDE:{filename}")
    stack: list[dict] = []
    blocks: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        match = BLOCK.fullmatch(line)
        if match:
            if match.group(1):
                name = match.group(1)
                stack.append({"path": "/".join([*(b["name"] for b in stack), name]),
                              "name": name, "params": {}, "file": filename, "line": line_no})
            elif stack:
                blocks.append(stack.pop())
            else:
                raise GateError(f"EXTRA_CLOSE:{filename}:{line_no}")
            continue
        if stack:
            param = ASSIGN.fullmatch(line)
            if param:
                name, value = param.groups()
                if name in stack[-1]["params"]:
                    raise GateError(f"DUPLICATE_PARAMETER:{filename}:{line_no}:{name}")
                stack[-1]["params"][name] = value.strip().strip("'\"")
    if stack:
        raise GateError(f"UNCLOSED_BLOCK:{filename}")
    return blocks


def inspect(layers: dict[str, str], chemistry: dict, case: str) -> dict:
    if case not in CASES or len(layers) != 11 or len(set(layers)) != 11:
        raise GateError("CASE_OR_LAYER_COUNT")
    blocks = [b for filename, content in layers.items()
              for b in parse_blocks(content, filename)]
    continuity = [b for b in blocks if b["path"] ==
                  "Physics/Plasmas/Transport/DriftDiffusion/Continuity"]
    if len(continuity) != 1:
        raise GateError(f"CONTINUITY_COUNT:{len(continuity)}")
    params = continuity[0]["params"]
    if "fvm_kernel_ownership" in params:
        raise GateError("MANUAL_OWNER_FLAG_FORBIDDEN")
    fem = params.get("fem_species", "").split()
    fvm = params.get("fvm_species", "").split()
    if fem != ["e"] or fvm != list(ION_SPECIES):
        raise GateError("NEW_ONLY_SPECIES_SELECTION_MISMATCH")
    if params.get("fem_potential") != "potential":
        raise GateError("EXPLICIT_POTENTIAL_REQUIRED")
    records = chemistry.get("species") if isinstance(chemistry, dict) else None
    if not isinstance(records, dict):
        raise GateError("JSON_SPECIES_MISSING")
    for sid in [*fem, *fvm]:
        record = records.get(sid)
        if not isinstance(record, dict):
            raise GateError(f"JSON_SPECIES_MISSING:{sid}")
        density = record.get("initial_number_density")
        if (isinstance(density, bool) or not isinstance(density, (int, float)) or
                not math.isfinite(density) or density <= 0):
            raise GateError(f"JSON_INITIAL_DENSITY_INVALID:{sid}")
        if record.get("transport_coef") not in ("constant", "lookup", "functor"):
            raise GateError(f"JSON_TRANSPORT_MISSING:{sid}")
    targets = {f"log_{sid}": sid for sid in ION_SPECIES}
    targets.update(LEGACY_STATES)
    native = [b for b in blocks if b["path"].split("/")[0] in ("FVKernels", "FVBCs")
              and b["path"].count("/") == 1
              and any(value in targets for value in b["params"].get("variable", "").split())]
    if native:
        detail = ",".join(f"{b['file']}:{b['line']}:{b['name']}" for b in native)
        raise GateError(f"NATIVE_FV_ION_OWNER_PRESENT_{len(native)}:{detail}")
    return {"status": "P0_INPUT_ONLY_PASS", "case": case,
            "selected_fem": fem, "selected_fvm": fvm,
            "native_fv_ion_owners": 0, "generated_fv_kernels": "NOT_VERIFIED",
            "generated_fv_bcs": "NOT_VERIFIED", "P1": "NOT_RUN", "P2": "NOT_RUN",
            "P3": "NOT_RUN", "science": "SCIENCE_HOLD"}


def load_layers(directory: Path, manifest: dict) -> tuple[list[str], dict[str, str]]:
    ordered = manifest.get("ordered_layers")
    if (not isinstance(ordered, list) or len(ordered) != 11 or
            any(not isinstance(p, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.i", p)
                for p in ordered) or len(set(ordered)) != 11):
        raise GateError("UNSAFE_OR_UNORDERED_11_LAYERS")
    if directory.is_symlink() or not directory.is_dir():
        raise GateError("LAYER_DIRECTORY_INVALID")
    layers = {}
    for name in ordered:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise GateError(f"STAGED_LAYER_MISSING_OR_SYMLINK:{name}")
        layers[name] = path.read_text(encoding="utf-8")
    return ordered, layers


def run(*, case: str, manifest_path: Path, layer_dir: Path, json_path: Path,
        expected_head: str, binary: Path | None = None,
        output_dir: Path | None = None) -> dict:
    if not SHA.fullmatch(expected_head):
        raise GateError("EXPECTED_HEAD_INVALID")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if current != expected_head:
        raise GateError("SOURCE_HEAD_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "issue633.new_only_11layer.v1" or
            manifest.get("mode") != "new_only" or manifest.get("case") != case or
            manifest.get("source_sha") != expected_head):
        raise GateError("MANIFEST_IDENTITY_OR_MODE_MISMATCH")
    ordered, layers = load_layers(layer_dir, manifest)
    result = inspect(layers, json.loads(json_path.read_text(encoding="utf-8")), case)
    result.update({"source_sha": expected_head, "input_layers": [
        {"name": n, "sha256": digest(layer_dir / n)} for n in ordered],
        "json_sha256": digest(json_path), "manifest_sha256": digest(manifest_path)})
    if binary is None:
        return result
    if output_dir is None or output_dir.exists():
        raise GateError("P2_EVIDENCE_OUTPUT_MUST_BE_NEW")
    if not binary.is_file() or binary.stat().st_size == 0:
        raise GateError("P1_BINARY_MISSING")
    output_dir.mkdir(parents=True)
    result["P1"] = "SOURCE_BOUND_BINARY_PRESENT_ONLY"
    result["binary_sha256"] = digest(binary)
    command = [str(binary.resolve()), "--check-input", "-i", *ordered]
    try:
        completed = subprocess.run(command, cwd=layer_dir, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, timeout=1200,
                                   check=False)
        log = completed.stdout
        ok = completed.returncode == 0 and "Syntax OK" in log
    except subprocess.TimeoutExpired:
        log, ok = "P2_TIMEOUT_NO_SOLVE\n", False
    (output_dir / "p2.log").write_text(log, encoding="utf-8")
    result["p2_log_sha256"] = digest(output_dir / "p2.log")
    result["P2"] = "PASS" if ok else "HOLD"
    result["status"] = "P2_CHECK_INPUT_ONLY_PASS" if ok else "P2_CHECK_INPUT_HOLD"
    (output_dir / "status.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if not ok:
        raise GateError("P2_CHECK_INPUT_FAILED; evidence retained")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--layers", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    a = parser.parse_args()
    try:
        result = run(case=a.case, manifest_path=a.manifest, layer_dir=a.layers,
                     json_path=a.json, expected_head=a.expected_head,
                     binary=a.binary, output_dir=a.output)
    except (GateError, OSError, ValueError, json.JSONDecodeError,
            subprocess.CalledProcessError) as exc:
        print(f"ISSUE633_NEW_ONLY_HOLD:{exc}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
