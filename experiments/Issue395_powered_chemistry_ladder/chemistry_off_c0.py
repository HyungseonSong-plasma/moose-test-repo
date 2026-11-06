"""Issue 457: fail-closed preparation of a *candidate* chemistry-OFF native input.

This module never executes PhysicsApp or edits the pinned Oxygen14 input.  The
full P0→P3 science gate belongs to the issue; a clean lexical census is not a
proof of effective MOOSE residual/source ownership.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

from physics_harness.adapters.moose.input import MooseInput, MooseInputError

EXPECTED_SOURCE = "29d1acc6ef7969908b86719e4b95c73a1565136d"
EXPECTED_PHYSICS = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
EXPECTED_EEDF = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
# These are known chemistry owner signatures, not a complete source classifier.
REACTION_SIGNATURES = (
    re.compile(r"(?i)\breaction_progress\s*="),
    re.compile(r"(?i)\btype\s*=\s*\w*(?:ElectronImpact|Reaction|Ionization|Attachment|Detachment|Dissociation|Chemistry)\w*"),
    re.compile(r"(?i)\b(?:property_name|functor_names|source|functor|v)\s*=\s*['\"]?\s*(?:R_(?:EI\d+|H\d+|ion\w*|attach\w*|diss\w*|elastic\w*)|S_\w*(?:EI\d+|chem\w*|ion\w*|attach\w*|diss\w*|elastic\w*))\b"),
    re.compile(r"(?i)\bchem(?:24|25)_\w+"),
)
SURFACE_SIGNATURES = (
    re.compile(r"(?i)\b(?:stageb4_\w+_surface_loss|\w+_surface_reaction|\w+_wall_recombination)\b"),
)
# Exactly these 15 base-input objects implement neutral surface reactions and
# charged-wall to neutral inventory return in the 400W archived Oxygen14 source.
# Charged-particle wall losses, sheath closure and nonreactive transport stay.
SURFACE_BLOCKS = (
    "FunctorMaterials/stageb4_O_surface_flux",
    "FunctorMaterials/stageb4_O2s_surface_flux",
    "FunctorMaterials/stageb4_Os_surface_flux",
    "FunctorMaterials/stageb4_ion_neutral_total",
    "FunctorMaterials/stageb4_ion_O_return_material",
    "FVBCs/stageb4_O_surface_loss",
    "FVBCs/stageb4_O2s_surface_loss",
    "FVBCs/stageb4_Os_surface_loss",
    "FVBCs/stageb4_ion_total_mass_return",
    "FVBCs/stageb4_ion_O_return",
    "Postprocessors/stageb4_O_surface_loss_rate",
    "Postprocessors/stageb4_O2s_surface_loss_rate",
    "Postprocessors/stageb4_Os_surface_loss_rate",
    "Postprocessors/stageb4_ion_total_neutral_return_rate",
    "Postprocessors/stageb4_ion_O_return_rate",
)


def remove_base_surface_chemistry(source: str) -> tuple[str, list[str]]:
    """Remove the exact archived reactive-wall graph, or reject a partial graph."""
    doc = MooseInput(source)
    present = [path for path in SURFACE_BLOCKS if doc.find(path)]
    if not present:
        return source, []
    if len(present) != len(SURFACE_BLOCKS):
        missing = sorted(set(SURFACE_BLOCKS) - set(present))
        raise ChemistryOffContractError(f"partial surface reaction inventory: missing {missing}")
    try:
        candidate, removed = doc.remove_paths(SURFACE_BLOCKS)
    except MooseInputError as exc:
        raise ChemistryOffContractError(f"ambiguous surface reaction inventory: {exc}") from exc
    if set(removed) != set(SURFACE_BLOCKS):
        raise ChemistryOffContractError("surface chemistry deletion audit failed")
    # This is not permission to remove the charged-particle wall fluxes.
    for retained in ("FVBCs/ion_wall", "FVBCs/negative_ion_wall",
                     "FVBCs/atomic_positive_ion_wall"):
        doc.unique(retained)
        MooseInput(candidate).unique(retained)
    return candidate, list(SURFACE_BLOCKS)


INCLUDE = re.compile(r"^\s*!include\s+(?P<name>\S+)\s*$")
TIME_SEQUENCE = re.compile(r"(?m)^\s*time_sequence\s*=\s*'(?P<seq>[^']+)'\s*(?:#.*)?$")
END_TIME = re.compile(r"(?m)^\s*end_time\s*=\s*(?P<value>[^\s#]+)")
POWER = re.compile(r"(?m)^\s*target\s*=\s*(?P<value>[^\s#]+)")


class ChemistryOffContractError(ValueError):
    pass


def expected_grid_ns() -> list[int]:
    return (list(range(0, 101)) + list(range(110, 2001, 10))
            + list(range(2100, 10001, 100)) + list(range(11000, 100001, 1000)))


def _one(pattern: re.Pattern[str], text: str, description: str) -> str:
    hits = list(pattern.finditer(text))
    if len(hits) != 1:
        raise ChemistryOffContractError(f"expected exactly one {description}, found {len(hits)}")
    return hits[0].group("seq" if description == "time_sequence" else "value")


def _check_grid(text: str) -> None:
    values = [float(x) for x in _one(TIME_SEQUENCE, text, "time_sequence").split()]
    expected = expected_grid_ns()
    if len(values) != len(expected) or any(abs(t - ns * 1e-9) > 1e-14 for t, ns in zip(values, expected)):
        raise ChemistryOffContractError("C0 requires the exact 0–100us / 460-step baseline time grid")
    if abs(float(_one(END_TIME, text, "end_time")) - 1e-4) > 1e-14:
        raise ChemistryOffContractError("C0 requires end_time = 100 us")
    if re.search(r"(?m)^\s*restart_file_base\s*=", text):
        raise ChemistryOffContractError("C0 requires a fresh solve, not a chemistry checkpoint restart")


def _read_include_closure(root: Path, entrypoints: tuple[Path, ...]) -> dict[str, str]:
    root = root.resolve(strict=True)
    scanned: dict[str, str] = {}
    visiting: set[Path] = set()

    def scan(path: Path) -> None:
        absolute = path.resolve(strict=True)
        if not absolute.is_relative_to(root):
            raise ChemistryOffContractError(f"input include escapes repository checkout: {path}")
        if absolute in visiting:
            raise ChemistryOffContractError(f"recursive MOOSE !include cycle: {absolute}")
        rel = absolute.relative_to(root).as_posix()
        if rel in scanned:
            return
        visiting.add(absolute)
        text = absolute.read_text(encoding="utf-8")
        for line in text.splitlines():
            uncommented = line.split("#", 1)[0]
            if not uncommented.strip():
                continue
            if uncommented.lstrip().startswith("!include"):
                match = INCLUDE.fullmatch(uncommented)
                if not match or any(x in match.group("name") for x in ("'", '"', '$', '*')):
                    raise ChemistryOffContractError(f"unresolved MOOSE include syntax: {rel}: {line}")
                scan(absolute.parent / match.group("name"))
        scanned[rel] = text
        visiting.remove(absolute)

    for entry in entrypoints:
        scan(entry)
    return scanned


def _active_lines(text: str) -> list[tuple[int, str]]:
    return [(i, line.split("#", 1)[0]) for i, line in enumerate(text.splitlines(), 1)
            if line.split("#", 1)[0].strip()]


def stage(root: Path, base_input: Path, rf_parent: Path, output: Path,
          power_w: int = 400, *, surface_chemistry_off: bool = True,
          verify_git_sha: bool = True) -> dict:
    """Write a P0-only candidate command manifest or fail without claiming OFF.

    The caller must first stage the exact Oxygen14 source at EXPECTED_SOURCE.
    All reaction overlays are deliberately absent from the generated argv.
    Remaining embedded or included chemistry fails closed.
    """
    if power_w != 400:
        raise ChemistryOffContractError("Phase-0 scope is C0-400 only")
    root = root.resolve(strict=True)
    if verify_git_sha:
        try:
            actual_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ChemistryOffContractError("pinned native source Git identity unavailable") from exc
        if actual_sha != EXPECTED_SOURCE:
            raise ChemistryOffContractError(
                f"C0 requires exact Oxygen14 source {EXPECTED_SOURCE}, got {actual_sha}"
            )
    base_input = base_input.resolve(strict=True)
    rf_parent = rf_parent.resolve(strict=True)
    output = output.resolve(strict=False)
    if not output.is_relative_to(root):
        raise ChemistryOffContractError("output manifest must remain inside staged checkout")
    if output.exists():
        raise ChemistryOffContractError("refuse to overwrite prior C0 source/evidence")
    if base_input == rf_parent:
        raise ChemistryOffContractError("base input and RF overlay must be distinct")
    original_base_text = base_input.read_text(encoding="utf-8")
    base_text, surface_removed = remove_base_surface_chemistry(original_base_text)
    if not surface_chemistry_off and surface_removed:
        raise ChemistryOffContractError("C0 cannot retain or bypass surface chemistry")
    _check_grid(base_text)
    files = _read_include_closure(root, (base_input, rf_parent))
    files[base_input.relative_to(root).as_posix()] = base_text
    candidate_input = base_input.with_name(base_input.stem + "__C0_chemistry_off.i")
    if candidate_input.exists():
        raise ChemistryOffContractError("refuse to overwrite existing derived Chemistry-OFF input")
    if not re.search(r"(?m)^\s*(?:\[log_ne\]|variable\s*=\s*log_ne)\s*$", base_text):
        raise ChemistryOffContractError("C0 electron-density state log_ne not found")
    if not re.search(r"(?m)^\s*(?:\[log_energy\]|variable\s*=\s*log_energy)\s*$", base_text):
        raise ChemistryOffContractError("C0 electron-energy state log_energy not found")
    if abs(float(_one(POWER, rf_parent.read_text(encoding="utf-8"), "RF target")) - 400) > 1e-8:
        raise ChemistryOffContractError("C0 requires 400 W RF target")
    if any("\x00" in text for text in files.values()):
        raise ChemistryOffContractError("binary or malformed HIT input")
    hazards: list[str] = []
    for path, text in files.items():
        for line_num, line in _active_lines(text):
            if any(pattern.search(line) for pattern in REACTION_SIGNATURES):
                hazards.append(f"{path}:{line_num}: volumetric reaction signature: {line.strip()}")
            if surface_chemistry_off and any(pattern.search(line) for pattern in SURFACE_SIGNATURES):
                hazards.append(f"{path}:{line_num}: reactive wall signature: {line.strip()}")
    if hazards:
        raise ChemistryOffContractError("residual chemistry in active input/include closure:\n" + "\n".join(hazards[:30]))

    base_rel = candidate_input.relative_to(root).as_posix()
    parent_rel = rf_parent.relative_to(root).as_posix()
    out_rel = output.relative_to(root).as_posix()
    # Native tool is intentionally NOT executed by this P0 module.
    check_argv = ["physics_app/physics-opt", "--check-input", "-i", base_rel, parent_rel]
    solve_argv = ["physics_app/physics-opt", "-i", base_rel, parent_rel,
                  f"Outputs/file_base={out_rel}.runtime/plasma"]
    result = {
        "schema": 1, "issue": 457, "experiment": "C0-400-chemistry-off",
        "phase": "P0_STATIC_CANDIDATE_ONLY", "scientific_acceptance": "HOLD",
        "native_runtime_proved": False, "chemistry_source_ownership_proved": False,
        "source_harness_expected_sha": EXPECTED_SOURCE,
        "physics_app_expected_sha": EXPECTED_PHYSICS,
        "transport_eedf_expected_sha256": EXPECTED_EEDF,
        "power_target_W": power_w, "start_time_s": 0, "end_time_s": 1e-4,
        "expected_steps": 460, "surface_reactions_requested_off": surface_chemistry_off,
        "input_sha256": {path: hashlib.sha256(text.encode()).hexdigest() for path, text in files.items()},
        "original_source_input": base_input.relative_to(root).as_posix(),
        "original_base_sha256": hashlib.sha256(original_base_text.encode()).hexdigest(),
        "derived_base_sha256": hashlib.sha256(base_text.encode()).hexdigest(),
        "removed_reactive_wall_objects": surface_removed,
        "retained_charged_wall_flux_contract": True,
        "active_cli_input_files": [base_rel, parent_rel], "target_disabled_reaction_channel_count": 14,
        "check_argv": check_argv, "solve_argv": solve_argv,
        "warning": "P0 lexical census is incomplete evidence of solver-effective source ownership; P1/P2/native owner inventory required",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    candidate_input.write_text(base_text, encoding="utf-8")
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="physics oxygen-c0")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--base-input", type=Path, required=True)
    parser.add_argument("--rf-parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--power-w", type=int, default=400)
    args = parser.parse_args(argv)
    try:
        result = stage(args.root, args.base_input, args.rf_parent, args.output, args.power_w)
    except (OSError, ChemistryOffContractError, ValueError) as exc:
        print(f"OXYGEN_C0_P0: HOLD ({exc})")
        return 2
    print("OXYGEN_C0_P0: STATIC_CANDIDATE_ONLY")
    print("CHECK_ARGV=" + shlex.join(result["check_argv"]))
    print("SOLVE_ARGV=" + shlex.join(result["solve_argv"]))
    print(f"C0_MANIFEST={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
