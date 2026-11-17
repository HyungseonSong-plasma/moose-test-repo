"""Issue #633: fail-closed retirement of the 26 archived ion FV objects.

Operates only on a disposable, canonicalized S6-417/941 11-layer directory.
The historical 10-layer source, archived ZIP and non-ion objects are immutable.
This is an ownership handoff, not Physics generation or Native P2 evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

NATIVE_VARIABLE = {"log_O2p": "O2p", "log_Om": "Om", "log_Op": "Op"}
RETIRED_ALIASES = {"log_ni", "log_nm", "log_nop"}
EXPECTED = {
    "O2p": {"FVKernels": 5, "FVBCs": 4},
    "Om": {"FVKernels": 4, "FVBCs": 4},
    "Op": {"FVKernels": 5, "FVBCs": 4},
}
ALLOWED = {
    "FVKernels": {
        "PhysicsFVLogMolarElectronTimeDerivative",
        "PhysicsFVLogMolarElectronDiffusion",
        "PhysicsFVLogMolarElectrostaticDrift",
        "FVLogMolarTimeDerivative", "FVLogMolarDiffusion",
        "FVLogMolarElectrostaticDrift", "FVCoupledForce",
    },
    "FVBCs": {"FVFunctorNeumannBC", "PhysicsFVLogMolarDielectricFluxBC",
              "FVLogMolarDielectricFluxBC"},
}
BLOCK = re.compile(
    r"(?m)^  \[(?P<name>[A-Za-z0-9_]+)\][ \t]*\r?\n"
    r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
    r"^  \[\][ \t]*(?:\r?\n|$)"
)
ROOT = re.compile(r"(?m)^\[([A-Za-z0-9_]+)\][ \t]*$")
PARAM = re.compile(r"^    ([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


class CutoverError(ValueError):
    """An input owner was not exactly characterized; no writes are permitted."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parsed_parameters(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = PARAM.fullmatch(line)
        if not match or match[1] in result:
            raise CutoverError("ION26_MALFORMED_OR_DUPLICATE_PARAMETER:" + repr(line))
        result[match[1]] = match[2].strip().strip("'\"")
    return result


def cutover_texts(layers: dict[str, str]) -> tuple[dict[str, str], dict]:
    """Inspect all owners first, then return new bytes and a source-bound receipt.

    No attempt to modify uncharacterized classes or non-ion FV objects.
    Source order is caller-supplied and every source file is scanned.
    """
    if len(layers) != 11 or "migrated_continuity.i" not in layers:
        raise CutoverError("ION26_REQUIRES_EXACTLY_ELEVEN_CANONICAL_LAYERS")
    counts = {s: {section: 0 for section in ("FVKernels", "FVBCs")}
              for s in EXPECTED}
    names = {section: set() for section in ALLOWED}
    receipts: list[dict] = []
    rewritten = {}
    for filename, source in layers.items():
        if not filename.endswith(".i") or Path(filename).name != filename:
            raise CutoverError("ION26_UNSAFE_LAYER_NAME:" + filename)
        roots = list(ROOT.finditer(source))
        objects = []
        for obj in BLOCK.finditer(source):
            parent = next((root[1] for root in reversed(roots)
                           if root.start() < obj.start()), "")
            if parent not in ALLOWED:
                continue
            params = parsed_parameters(obj["body"])
            variable = params.get("variable", "")
            if variable in RETIRED_ALIASES:
                raise CutoverError("ION26_UNCANONICALIZED_VARIABLE:" + variable)
            if variable not in NATIVE_VARIABLE:
                continue
            species = NATIVE_VARIABLE[variable]
            kind = params.get("type", "")
            if kind not in ALLOWED[parent]:
                raise CutoverError(
                    f"ION26_UNCHARACTERIZED_{parent}_{obj['name']}_{kind}"
                )
            if parent == "FVKernels":
                if params.get("block") != "plasma":
                    raise CutoverError("ION26_NONPLASMA_ION_KERNEL:" + obj["name"])
                if kind == "FVCoupledForce" and not params.get("v"):
                    raise CutoverError("ION26_SOURCE_FUNCTOR_MISSING:" + obj["name"])
            else:
                if not params.get("boundary"):
                    raise CutoverError("ION26_ION_FVBC_BOUNDARY_MISSING:" + obj["name"])
                if kind == "FVFunctorNeumannBC" and not all(
                    key in params for key in ("functor", "factor")
                ):
                    raise CutoverError("ION26_NEUMANN_FLUX_OR_FACTOR_MISSING:" + obj["name"])
                if kind != "FVFunctorNeumannBC" and not params.get("signed_number_flux"):
                    raise CutoverError("ION26_DIELECTRIC_FLUX_MISSING:" + obj["name"])
            if obj["name"] in names[parent]:
                raise CutoverError(f"ION26_DUPLICATE_{parent}_NAME:{obj['name']}")
            names[parent].add(obj["name"])
            counts[species][parent] += 1
            before = obj.group(0).encode("utf-8")
            receipts.append({
                "file": filename, "section": parent, "name": obj["name"],
                "variable": variable, "species": species, "type": kind,
                "old_block_sha256": digest(before),
            })
            objects.append(obj)
        after = source
        for obj in reversed(objects):
            after = after[:obj.start()] + after[obj.end():]
        rewritten[filename] = after
    if counts != EXPECTED:
        raise CutoverError("ION26_OWNER_CENSUS_CHANGED:" + repr(counts))
    if len(receipts) != 26 or len([r for r in receipts if r["section"] == "FVKernels"]) != 14:
        raise CutoverError("ION26_NOT_EXACT_14_KERNELS_12_BCS")
    for text in rewritten.values():
        roots = list(ROOT.finditer(text))
        for obj in BLOCK.finditer(text):
            parent = next((root[1] for root in reversed(roots)
                           if root.start() < obj.start()), "")
            if parent in ALLOWED and parsed_parameters(obj["body"]).get(
                "variable"
            ) in NATIVE_VARIABLE:
                raise CutoverError("ION26_NATIVE_FV_OWNER_REMAINS")
    return rewritten, {
        "schema": "issue633.s6_scratch_ion_native_26_retirement.v1",
        "status": "NATIVE_ION_26_CUTOVER_PLAN_VALIDATED_P2_NOT_RUN",
        "old_native_fv_kernels": 14, "old_native_fv_bcs": 12,
        "expected_generated_fv_kernels": 12, "expected_generated_fv_bcs": 12,
        "per_species_old_owners": counts,
        "retired_owners": sorted(receipts, key=lambda x: (x["file"], x["section"], x["name"])),
        "P2": "NOT_RUN", "P3": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


def retire_in_disposable_scratch(
    folder: Path, ordered: list[str], *, exact_manifest: dict, expected_source_head: str
) -> dict:
    """Prevalidate the entire staged 11-layer set before ANY scratch write."""
    directory = Path(folder).resolve(strict=True)
    marker = directory / ".issue633_disposable_scratch"
    if (marker.is_symlink() or not marker.is_file() or
            marker.read_text(encoding="utf-8").strip() != "issue633-scratch-only"):
        raise CutoverError("ION26_REFUSE_UNMARKED_OR_NONDISPOSABLE_INPUT_DIRECTORY")
    names = [Path(n).name for n in ordered]
    if (len(names) != 11 or names[-1] != "migrated_continuity.i"
            or len(set(names)) != 11
            or any(n != raw.split("/")[-1] for raw, n in zip(ordered, names))):
        raise CutoverError("ION26_UNEXPECTED_STAGED_ORDER")
    paths = [directory / n for n in names]
    if any(p.is_symlink() or not p.is_file() or p.resolve().parent != directory
           for p in paths):
        raise CutoverError("ION26_STAGED_PATH_NOT_PLAIN_FILE")
    original = {p.name: p.read_bytes() for p in paths}
    if any(b"\r" in b for b in original.values()):
        raise CutoverError("ION26_INPUT_CRLF_NOT_ACCEPTED")
    # Exact immutable 11-layer source/owner identity is mandatory before mutation.
    if not isinstance(exact_manifest, dict) or exact_manifest.get("source_head") != expected_source_head:
        raise CutoverError("ION26_SOURCE_HEAD_PIN_MISMATCH")
    expected_layers = exact_manifest.get("layers", [])
    expected_owners = exact_manifest.get("ion_native_blocks", [])
    if len(expected_layers) != 11 or len(expected_owners) != 26:
        raise CutoverError("ION26_EXACT_PIN_MANIFEST_INCOMPLETE")
    pinned_names = [Path(entry["file_path"]).name for entry in expected_layers]
    if names != pinned_names:
        raise CutoverError("ION26_PINNED_ORDER_MISMATCH")
    for entry in expected_layers:
        name = Path(entry["file_path"]).name
        if digest(original[name]) != entry["file_sha256"]:
            raise CutoverError("ION26_PINNED_FILE_SHA_MISMATCH:" + name)
    after, receipt = cutover_texts({n: original[n].decode("utf-8") for n in names})
    expected_blocks = sorted(
        (Path(x["file_path"]).name, x["section"], x["object_name"], x["block_sha256"])
        for x in expected_owners
    )
    actual_blocks = sorted(
        (x["file"], x["section"], x["name"], x["old_block_sha256"])
        for x in receipt["retired_owners"]
    )
    if actual_blocks != expected_blocks:
        raise CutoverError("ION26_PINNED_BLOCK_SHA_OR_OWNER_MISMATCH")
    receipt["source_head"] = expected_source_head
    receipt["exact_pin_verified"] = True

    changes = {n: source.encode("utf-8") for n, source in after.items()
               if source.encode("utf-8") != original[n]}
    if not changes:
        raise CutoverError("ION26_NO_NATIVE_OWNERS_REMOVED")
    # The directory is disposable; check that it is still the same input before
    # applying validated changes. A failed source identity check never writes.
    if any(p.read_bytes() != original[p.name] for p in paths):
        raise CutoverError("ION26_SOURCE_CHANGED_DURING_PREFLIGHT")
    receipt["changed_staged_files"] = sorted(changes)
    receipt["files"] = {
        name: {"before_sha256": digest(original[name]),
               "after_sha256": digest(after[name].encode("utf-8"))}
        for name in names
    }
    for name, data in changes.items():
        (directory / name).write_bytes(data)
    if any((directory / name).read_bytes() != after[name].encode("utf-8")
           for name in names):
        raise CutoverError("ION26_SCRATCH_READBACK_MISMATCH")
    receipt["status"] = "SCRATCH_NATIVE_ION_26_RETIRED_NEW24_PENDING_P2"
    return receipt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--staged-chem-dir", type=Path, required=True)
    p.add_argument("--ordered-file", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--case-manifest", type=Path, required=True)
    p.add_argument("--expected-source-head", required=True)
    args = p.parse_args()
    if args.receipt.exists():
        raise CutoverError("ION26_RECEIPT_ALREADY_EXISTS")
    report = retire_in_disposable_scratch(
        args.staged_chem_dir, json.loads(args.ordered_file.read_text()),
        exact_manifest=json.loads(args.case_manifest.read_text()),
        expected_source_head=args.expected_source_head,
    )
    args.receipt.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in (
        "status", "old_native_fv_kernels", "old_native_fv_bcs", "P2", "P3"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
