"""Scientific preflight: classify COMPLETE local BOLSIG/LXCat collision inventory.

Never filters away processes just to make the model "pass". Reads external
source *locally* and emits only SHA, process census and missing-physics
evidence, not cross-section tables or other licensed raw bytes.

STRUCTURALLY_SUPPORTED is NOT numerical or physical BOLSIG+ agreement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

KINDS = frozenset({
    "ELASTIC", "EFFECTIVE", "MOMENTUM", "EXCITATION",
    "IONIZATION", "ATTACHMENT", "ROTATION",
})


class CollisionAuditError(ValueError):
    pass


def _decimal(value: str, label: str) -> float:
    try:
        result = float(value.replace("D", "E").replace("d", "e"))
    except ValueError as exc:
        raise CollisionAuditError(f"invalid {label} numeric value") from exc
    if not math.isfinite(result):
        raise CollisionAuditError(f"nonfinite {label}")
    return result


def _processes(lines: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        kind = lines[i].strip()
        if kind not in KINDS:
            i += 1
            continue
        line = i + 1
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i == len(lines):
            raise CollisionAuditError(f"missing target after {kind} line {line}")
        target_line = lines[i].strip()
        reversible = "<->" in target_line
        target = target_line.split("<->", 1)[0].split("->", 1)[0].strip()
        if not target or any(ch.isspace() for ch in target):
            raise CollisionAuditError(f"malformed {kind} target at line {line}")
        i += 1
        # BOLSIG+ ATTACHMENT has NO parameter line; all other supported types
        # expect third-line numeric data. ROTATION may use special conventions.
        threshold: float | None = None
        if kind != "ATTACHMENT":
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i == len(lines):
                raise CollisionAuditError(f"missing {kind} parameters at line {line}")
            parts = lines[i].strip().split()
            threshold = _decimal(parts[0], f"{kind} parameter")
            i += 1
        while i < len(lines) and not (
            len(lines[i].strip()) >= 5 and
            set(lines[i].strip()) == {"-"}
        ):
            i += 1
        if i >= len(lines):
            raise CollisionAuditError(f"opening delimiter missing: {kind} line {line}")
        i += 1
        table: list[tuple[float, float]] = []
        while i < len(lines) and not (
            len(lines[i].strip()) >= 5 and
            set(lines[i].strip()) == {"-"}
        ):
            row = lines[i].strip()
            i += 1
            if not row:
                continue
            tokens = row.split()
            if len(tokens) != 2:
                raise CollisionAuditError(f"invalid numeric table: {kind} line {line}")
            energy, sigma = _decimal(tokens[0], "energy"), _decimal(tokens[1], "cross section")
            if sigma < 0:
                raise CollisionAuditError(f"negative cross section: {kind} line {line}")
            table.append((energy, sigma))
            if len(table) > 1000000:
                raise CollisionAuditError("collision data exceeds configured row limit")
        if i >= len(lines) or not table:
            raise CollisionAuditError(f"incomplete table: {kind} line {line}")
        i += 1
        is_power_law = len(table) == 1
        if is_power_law:
            if not (table[0][0] > -2 and table[0][1] >= 0):
                raise CollisionAuditError("invalid power-law cross section")
        elif any(e < 0 or (j and e <= table[j - 1][0])
                 for j, (e, _) in enumerate(table)):
            raise CollisionAuditError(f"nonascending collision energy: {kind} line {line}")
        if kind in {"EXCITATION", "IONIZATION"} and (
            threshold is None or threshold <= 0
        ):
            raise CollisionAuditError(f"nonpositive {kind} threshold")
        records.append({
            "kind": kind,
            "target": target,
            "reversible": reversible,
            "source_line": line,
            "points": len(table),
            "power_law": is_power_law,
            "min_energy_eV": None if is_power_law else table[0][0],
            "max_energy_eV": None if is_power_law else table[-1][0],
            "threshold_eV": threshold if kind in {"EXCITATION", "IONIZATION"} else None,
        })
        if len(records) > 10000:
            raise CollisionAuditError("too many collision processes")
    if not records:
        raise CollisionAuditError("no collision processes recognized")
    return records


def audit_local_collision_file(
    source: Path,
    species: tuple[str, ...] = ("Ar", "He", "N2", "O2"),
    required_energy_eV: float | None = None,
) -> dict[str, Any]:
    if not species or len(species) != len(set(species)) or (
        any(not x or any(ch.isspace() for ch in x) for x in species)
    ):
        raise CollisionAuditError("invalid species inventory")
    if required_energy_eV is not None and (
        not math.isfinite(required_energy_eV) or required_energy_eV <= 0
    ):
        raise CollisionAuditError("invalid required energy bound")
    raw = source.read_bytes()
    if not raw:
        raise CollisionAuditError("empty collision input")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise CollisionAuditError("source must be UTF-8 BOLSIG text") from exc
    processes = [r for r in _processes(lines) if r["target"] in species]
    reasons: list[str] = []
    if not processes:
        reasons.append("NO_RELEVANT_PROCESSES")
    any_particle_changing = any(
        r["kind"] in {"IONIZATION", "ATTACHMENT"} for r in processes
    )
    for gas in species:
        local = [r for r in processes if r["target"] == gas]
        providers = [r for r in local
                     if r["kind"] in {"ELASTIC", "EFFECTIVE", "MOMENTUM"}]
        if not local:
            reasons.append(f"MISSING_SPECIES:{gas}")
        if not providers:
            reasons.append(f"MISSING_MOMENTUM_PROVIDER:{gas}")
        elif len(providers) != 1:
            reasons.append(f"DUPLICATE_MOMENTUM_PROVIDER:{gas}")
        if (any(r["kind"] in {"EFFECTIVE", "MOMENTUM"} for r in providers)
                and any_particle_changing):
            # S7's EFFECTIVE-to-elastic reconstruction only applies when
            # excitation is the full nonelastic process inventory. The
            # M6b temporal-growth importer still rejects EFFECTIVE alongside
            # ionization or attachment. This is not a statement that the
            # user's source data are physically incorrect.
            reasons.append(f"EFFECTIVE_GROWTH_COUPLING_UNSUPPORTED:{gas}")
    for record in processes:
        line = record["source_line"]
        kind = record["kind"]
        if kind == "ROTATION":
            reasons.append(f"ROTATION_UNSUPPORTED:line{line}")
        if record["power_law"]:
            reasons.append(f"POWER_LAW_UNSUPPORTED:line{line}")
        elif required_energy_eV is not None and (
            record["min_energy_eV"] > 0 or
            record["max_energy_eV"] < required_energy_eV
        ):
            reasons.append(f"CROSS_SECTION_COVERAGE_GAP:line{line}")
        if (required_energy_eV is not None
                and record["threshold_eV"] is not None
                and record["threshold_eV"] >= required_energy_eV):
            reasons.append(f"INELASTIC_THRESHOLD_OUTSIDE_GRID:line{line}")
        if record["reversible"]:
            reasons.append(f"REVERSE_POPULATION_MODEL_REVIEW:line{line}")
    # Preserve only metadata, never raw table entries in the result.
    census = {gas: {
        kind: sum(r["target"] == gas and r["kind"] == kind for r in processes)
        for kind in sorted(KINDS)
        if any(r["target"] == gas and r["kind"] == kind for r in processes)
    } for gas in species}
    return {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "status": ("STRUCTURALLY_SUPPORTED_NOT_BOLSIG_VALIDATED"
                   if not reasons else "PHYSICS_MODEL_HOLD"),
        "species": list(species),
        "process_counts": census,
        "total_processes": len(processes),
        "model_gaps": sorted(set(reasons)),
        "important_limitation": (
            "Structure-only census; no collision-data rights, quantitative "
            "BOLSIG+ EEPF parity, or P2/P3 acceptance implied"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cross-sections", required=True, type=Path)
    parser.add_argument("--species", nargs="+", default=["Ar", "He", "N2", "O2"])
    parser.add_argument("--energy-max-eV", type=float)
    options = parser.parse_args()
    try:
        outcome = audit_local_collision_file(
            options.cross_sections, tuple(options.species), options.energy_max_eV)
    except (OSError, CollisionAuditError) as exc:
        print("BOLSIG_COLLISION_PREFLIGHT_HOLD:", exc)
        return 2
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome["status"] == "STRUCTURALLY_SUPPORTED_NOT_BOLSIG_VALIDATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
