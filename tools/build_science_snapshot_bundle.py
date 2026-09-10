#!/usr/bin/env python3
"""Materialize the accepted Physics science checkpoints as standalone input/data cases.

This is packaging, not a new cross-case physics integration.  Generated cases
preserve their original acceptance status; #176 R2 remains a runtime-pending
candidate until its JIT-capable science-lane acceptance is completed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = "c971440dfa4a274896c773969c39c9ac14eb68c9"
BUNDLE_DATE = "2026-09-10"
SOURCE_CASE = "experiments/Issue91_real_qvt_r3/r3_e0"
SOURCE_ASSETS = {
    "qvt.msh": f"{SOURCE_CASE}/qvt.msh",
    "transport_data.txt": f"{SOURCE_CASE}/transport_data.txt",
    "electron_moments.txt": f"{SOURCE_CASE}/electron_moments.txt",
}
QPX_TYPE_RE = re.compile(r"(?m)^(?P<prefix>\s*type\s*=\s*)QPX(?P<suffix>[A-Za-z_][A-Za-z0-9_]*)\s*$")
TYPE_RE = re.compile(r"(?m)^\s*type\s*=\s*(?P<type>[A-Za-z_][A-Za-z0-9_]*)\s*$")


class BundleError(RuntimeError):
    pass


def _run(*args: str) -> str:
    cp = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if cp.returncode != 0:
        raise BundleError(f"command failed ({cp.returncode}): {' '.join(args)}\n{cp.stderr.strip()}")
    return cp.stdout


def _git_bytes(revision: str, path: str) -> bytes:
    cp = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if cp.returncode != 0:
        raise BundleError(f"cannot read {revision}:{path}: {cp.stderr.decode(errors='replace').strip()}")
    return cp.stdout


def _git_blob(revision: str, path: str) -> str:
    return _run("git", "rev-parse", f"{revision}:{path}").strip()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_clean_science_delta(baseline: str) -> None:
    changed = _run(
        "git", "diff", "--name-only", f"{baseline}..HEAD", "--",
        "physics_app", "physics_harness", "experiments"
    ).splitlines()
    if changed:
        raise BundleError(
            "science source changed after the requested baseline; refuse to package a mixed state: "
            + ", ".join(changed)
        )


def _baseline_text(baseline: str, path: str) -> str:
    return _git_bytes(baseline, path).decode("utf-8")


def _canonicalize_object_types(text: str) -> tuple[str, list[dict[str, str]]]:
    replacements: list[dict[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        old = "QPX" + match.group("suffix")
        new = "Physics" + match.group("suffix")
        replacements.append({"old": old, "new": new})
        return match.group("prefix") + new

    updated = QPX_TYPE_RE.sub(repl, text)
    remaining = sorted({m.group("type") for m in TYPE_RE.finditer(updated) if m.group("type").startswith("QPX")})
    if remaining:
        raise BundleError(f"retired QPX MOOSE object type remains after canonicalization: {remaining}")

    missing: list[str] = []
    for item in sorted({entry["new"] for entry in replacements}):
        if not any((ROOT / "physics_app").rglob(f"{item}.h")):
            missing.append(item)
    if missing:
        raise BundleError(
            "namespace translation produced object types not owned by current physics_app: "
            + ", ".join(missing)
        )
    return updated, replacements


def _write_baseline_asset(baseline: str, repo_path: str, target: Path) -> dict[str, Any]:
    data = _git_bytes(baseline, repo_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "bundle_path": target.name,
        "source_path": repo_path,
        "git_blob": _git_blob(baseline, repo_path),
        "sha256": _sha256_bytes(data),
        "bytes": len(data),
    }


def _validate_case(case_dir: Path) -> dict[str, Any]:
    from physics_harness.adapters.moose.preflight import validate_parser_symbols_text
    from physics_harness.execution.cases import referenced_file_parameters

    input_path = case_dir / "input.i"
    text = input_path.read_text(encoding="utf-8")
    parser_errors = validate_parser_symbols_text(text, str(input_path))
    if parser_errors:
        raise BundleError("parser-symbol preflight failed:\n" + "\n".join(parser_errors))

    refs = referenced_file_parameters(text, case_dir, skip_dynamic=False)
    root = case_dir.resolve()
    normalized: list[dict[str, str]] = []
    for ref in refs:
        raw = ref["raw"]
        if "${" in raw:
            raise BundleError(f"dynamic external file reference is not standalone: {raw}")
        resolved = Path(ref["resolved"]).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise BundleError(f"external file reference escapes case directory: {raw} -> {resolved}") from exc
        if not resolved.is_file():
            raise BundleError(f"missing standalone referenced file: {raw} -> {resolved}")
        normalized.append({"parameter": ref["parameter"], "raw": raw, "sha256": _sha256_file(resolved)})

    return {
        "parser_symbol_preflight": "PASS",
        "referenced_file_closure": "PASS",
        "referenced_files": normalized,
        "input_sha256": _sha256_file(input_path),
        "contains_adparsed_functor": "type = ADParsedFunctorMaterial" in text,
        "contains_retired_qpx_object_type": bool(re.search(r"(?m)^\s*type\s*=\s*QPX", text)),
    }


def _materialize_r4(baseline: str, root: Path) -> dict[str, Any]:
    from experiments.historical_recipe_support.issue31_r4_qf1 import build_r4_qf1_input

    base_path = f"{SOURCE_CASE}/heavy_base.i"
    text, construction = build_r4_qf1_input(_baseline_text(baseline, base_path))
    text, renamed = _canonicalize_object_types(text)
    case_dir = root / "accepted" / "r4_solved_poisson_qf1"
    case_dir.mkdir(parents=True)
    (case_dir / "input.i").write_text(text, encoding="utf-8")
    assets = [_write_baseline_asset(baseline, path, case_dir / name) for name, path in SOURCE_ASSETS.items()]
    validation = _validate_case(case_dir)
    return {
        "id": "r4_solved_poisson_qf1",
        "issue": 31,
        "status": "ACCEPTED",
        "accuracy": {"contract": "PASS", "local_runtime": "PASS", "integrated_physics": "PASS_FOR_RECORDED_R4_SCOPE"},
        "scope": "accepted real-QVT monolithic solved-Poisson heavy+electron feedback checkpoint",
        "path": case_dir.relative_to(root).as_posix(),
        "recipe": base_path,
        "namespace_normalization": renamed,
        "construction_model": construction.get("model"),
        "assets": assets,
        "validation": validation,
        "runtime": {"jit_capable_required": validation["contains_adparsed_functor"]},
    }


def _materialize_a7(baseline: str, root: Path) -> list[dict[str, Any]]:
    from experiments.Issue27_surface_reactions.controlled_wall import electron_wall_stable as a7

    base_path = f"{SOURCE_CASE}/heavy_base.i"
    config_path = "experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json"
    params = json.loads(_baseline_text(baseline, config_path))["parameters"]
    results: list[dict[str, Any]] = []
    for mode in ("control", "electron_thermal_only", "combined_thermal"):
        text, construction = a7._build_a7_case_input(
            _baseline_text(baseline, base_path), parameters=params, mode=mode
        )
        text, renamed = _canonicalize_object_types(text)
        case_dir = root / "accepted" / "wall_phase_a_a7" / mode
        case_dir.mkdir(parents=True)
        (case_dir / "input.i").write_text(text, encoding="utf-8")
        assets = [_write_baseline_asset(baseline, path, case_dir / name) for name, path in SOURCE_ASSETS.items()]
        validation = _validate_case(case_dir)
        results.append({
            "id": f"wall_phase_a_a7_{mode}",
            "issue": 27,
            "status": "ACCEPTED",
            "accuracy": {"contract": "PASS", "local_runtime": "PASS", "integrated_physics": "PASS_FOR_RECORDED_A7_DISCRIMINATOR_SCOPE"},
            "scope": f"accepted A7 COMSOL-style electron wall discriminator mode={mode}; SEE=0; electron-energy wall coupling deferred",
            "path": case_dir.relative_to(root).as_posix(),
            "recipe": config_path,
            "namespace_normalization": renamed,
            "a7_discriminator_timestep_s": construction.get("a7_discriminator_timestep_s"),
            "assets": assets,
            "validation": validation,
            "runtime": {"jit_capable_required": validation["contains_adparsed_functor"]},
        })
    return results


def _materialize_e7(baseline: str, root: Path) -> dict[str, Any]:
    source_path = "physics_app/ci/electron_energy_real_qvt_inventory_smoke.i"
    text = _baseline_text(baseline, source_path)
    text = text.replace("'../../experiments/Issue91_real_qvt_r3/r3_e0/qvt.msh'", "'qvt.msh'")
    text = text.replace("'../../experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt'", "'electron_moments.txt'")
    text, renamed = _canonicalize_object_types(text)
    case_dir = root / "accepted" / "electron_energy_e7"
    case_dir.mkdir(parents=True)
    (case_dir / "input.i").write_text(text, encoding="utf-8")
    assets = [
        _write_baseline_asset(baseline, SOURCE_ASSETS["qvt.msh"], case_dir / "qvt.msh"),
        _write_baseline_asset(baseline, SOURCE_ASSETS["electron_moments.txt"], case_dir / "electron_moments.txt"),
    ]
    validation = _validate_case(case_dir)
    return {
        "id": "electron_energy_e7",
        "issue": 26,
        "status": "ACCEPTED",
        "accuracy": {"contract": "PASS", "local_runtime": "PASS", "integrated_physics": "PASS_FOR_RECORDED_E7_CHEMISTRY_OFF_SCOPE"},
        "scope": "accepted bounded real-QVT solved electron-energy chemistry-OFF checkpoint; #26 E8 remains downstream",
        "path": case_dir.relative_to(root).as_posix(),
        "recipe": source_path,
        "namespace_normalization": renamed,
        "assets": assets,
        "validation": validation,
        "runtime": {"jit_capable_required": validation["contains_adparsed_functor"]},
    }


def _materialize_r2(baseline: str, root: Path) -> dict[str, Any]:
    checker_path = "physics_app/ci/check_r2_o2_ionization_implementation.py"
    current_blob = _run("git", "rev-parse", f"HEAD:{checker_path}").strip()
    baseline_blob = _git_blob(baseline, checker_path)
    if current_blob != baseline_blob:
        raise BundleError("R2 checker changed after science baseline; refuse to package stale candidate input")
    sys.path.insert(0, str(ROOT))
    from physics_app.ci import check_r2_o2_ionization_implementation as r2

    case_dir = root / "candidate" / "r2_o2_ionization"
    case_dir.mkdir(parents=True)
    text, renamed = _canonicalize_object_types(r2.RUNTIME_INPUT)
    (case_dir / "input.i").write_text(text, encoding="utf-8")
    table = "\n".join(f"{energy:.17g} {rate:.17g}" for energy, rate in r2.RATE_TABLE) + "\n"
    (case_dir / "r2_o2_ionization_runtime_table.txt").write_text(table, encoding="utf-8")
    validation = _validate_case(case_dir)
    return {
        "id": "r2_o2_ionization",
        "issue": 176,
        "status": "CANDIDATE_RUNTIME_PENDING",
        "accuracy": {"contract": "PASS", "production_static_implementation": "PASS", "local_runtime": "NOT_TESTED", "integrated_physics": "NOT_TESTED"},
        "scope": "controlled Stage-3 O2-ionization runtime discriminator; synthetic lookup table is a discriminator input, not physical rate provenance",
        "path": case_dir.relative_to(root).as_posix(),
        "recipe": checker_path,
        "namespace_normalization": renamed,
        "assets": [{
            "bundle_path": "r2_o2_ionization_runtime_table.txt",
            "source_path": "generated from RATE_TABLE in checker",
            "git_blob": baseline_blob,
            "sha256": _sha256_file(case_dir / "r2_o2_ionization_runtime_table.txt"),
            "bytes": (case_dir / "r2_o2_ionization_runtime_table.txt").stat().st_size,
        }],
        "validation": validation,
        "runtime": {
            "jit_capable_required": True,
            "minimal_public_scratch_runtime_is_science_authority": False,
            "cold_jitcache_preferred": True,
        },
    }


def _all_files(root: Path, *, exclude: Iterable[str] = ()) -> list[Path]:
    excluded = set(exclude)
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and path.relative_to(root).as_posix() not in excluded),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _write_readme(root: Path, baseline: str) -> None:
    text = f"""# Physics science standalone input/data snapshot — {BUNDLE_DATE}

Science baseline: `{baseline}`

This archive materializes previously recorded science checkpoints into self-contained
MOOSE input/data case directories. It does **not** claim that the cases have been
combined into one newly accepted multiphysics model.

## Case status

- `accepted/r4_solved_poisson_qf1`: accepted #31 real-QVT solved-Poisson feedback checkpoint.
- `accepted/wall_phase_a_a7/*`: accepted #27 A7 wall discriminator modes; SEE=0 and electron-energy wall coupling deferred in this scope.
- `accepted/electron_energy_e7`: accepted #26 E7 real-QVT chemistry-OFF solved electron-energy checkpoint; E8 is not included.
- `candidate/r2_o2_ionization`: #176 R2 controlled O2-ionization candidate. Contract/static implementation passed, but Local Runtime Accuracy and Integrated Physics Accuracy remain unaccepted.

## Running a case

Run from inside the selected case directory so every `*_file`/mesh path remains local:

```bash
/path/to/physics-opt -i input.i
```

R4/A7 and R2 contain `ADParsedFunctorMaterial`. Use a JIT-capable Physics/QPX-equivalent
science environment with compatible MOOSE/libMesh FParser support. For R2 acceptance,
a cold `.jitcache` state is preferred. The minimal public scratch runtime is not the
scientific authority for these ADParsed-heavy cases.

## Integrity

`manifest.json` records source paths, acceptance scope, runtime requirements, and
SHA-256 identities. `checksums.sha256` covers every archive payload except itself.
Retired `QPX*` MOOSE object type spellings are mechanically normalized to their current
`Physics*` names only when the corresponding current `physics_app` header exists.
"""
    (root / "README.md").write_text(text, encoding="utf-8")


def _write_checksums(root: Path) -> None:
    lines = [f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in _all_files(root, exclude=("checksums.sha256",))]
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _deterministic_zip(root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = root.name
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in _all_files(root):
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(f"{prefix}/{rel}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes())


def build(output_dir: Path, baseline: str) -> tuple[Path, Path]:
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise BundleError(f"science baseline must be a full 40-hex SHA: {baseline!r}")
    _run("git", "cat-file", "-e", f"{baseline}^{{commit}}")
    _ensure_clean_science_delta(baseline)

    bundle_name = f"physics-science-snapshot-{BUNDLE_DATE}-{baseline[:8]}"
    root = output_dir / bundle_name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    cases: list[dict[str, Any]] = []
    cases.append(_materialize_r4(baseline, root))
    cases.extend(_materialize_a7(baseline, root))
    cases.append(_materialize_e7(baseline, root))
    cases.append(_materialize_r2(baseline, root))

    accepted = [case for case in cases if case["status"] == "ACCEPTED"]
    candidates = [case for case in cases if case["status"] != "ACCEPTED"]
    if not candidates or any(case["id"] == "r2_o2_ionization" and case["status"] == "ACCEPTED" for case in cases):
        raise BundleError("R2 status guard failed: runtime-pending candidate must not be promoted by packaging")
    if any(case["validation"]["contains_retired_qpx_object_type"] for case in cases):
        raise BundleError("retired QPX MOOSE object type escaped bundle normalization")

    manifest = {
        "schema_version": 1,
        "bundle_id": bundle_name,
        "created_utc": f"{BUNDLE_DATE}T00:00:00Z",
        "science_baseline": baseline,
        "builder_head": _run("git", "rev-parse", "HEAD").strip(),
        "source_repository": "HyungseonSong-plasma/moose-test-repo",
        "purpose": "standalone input/data materialization of recorded science checkpoints",
        "non_claim": "Packaging does not establish a new cross-case Integrated Physics Accuracy PASS.",
        "case_counts": {"accepted": len(accepted), "candidate": len(candidates), "total": len(cases)},
        "canonical_species": ["O2", "O2s", "O2p", "O", "Om", "Op", "Os"],
        "accuracy_rails": ["Contract Accuracy", "Local Runtime Accuracy", "Integrated Physics Accuracy"],
        "runtime_policy": {
            "adparsed_science_lane": "JIT-capable science runtime required where case validation flags contains_adparsed_functor=true",
            "minimal_public_scratch_runtime": "bounded deployment/smoke runtime; not sole scientific authority for ADParsed-heavy inputs",
        },
        "cases": cases,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_readme(root, baseline)
    _write_checksums(root)

    zip_path = output_dir / f"{bundle_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    _deterministic_zip(root, zip_path)
    return root, zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--science-baseline", default=DEFAULT_BASELINE)
    args = parser.parse_args()
    try:
        root, zip_path = build(args.output_dir.resolve(), args.science_baseline)
    except (BundleError, OSError, ValueError, KeyError) as exc:
        print(f"SCIENCE_BUNDLE: FAIL: {exc}", file=sys.stderr)
        return 1
    print("SCIENCE_BUNDLE: PASS")
    print(f"BUNDLE_ROOT={root}")
    print(f"BUNDLE_ZIP={zip_path}")
    print(f"BUNDLE_SHA256={_sha256_file(zip_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
