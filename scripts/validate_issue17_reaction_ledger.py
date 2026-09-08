#!/usr/bin/env python3
"""Validate the Issue #17/#176 R0 oxygen reaction ledger.

This validator is deliberately qpx-free. It checks reaction bookkeeping before any
volumetric chemistry is enabled in the solver:
  * heavy-species mass conservation;
  * oxygen-atom conservation;
  * charge conservation including electrons;
  * required rate/source metadata;
  * the frozen prohibition on using the 9.97 eV O2 excitation table for O2s.

R0 may remain AUDIT_IN_PROGRESS while unresolved rate metadata exists. Use
--require-r0-pass only when every blocker is expected to be closed.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path("docs/development/2026-09-07_issue17_r0_reaction_ledger.json")


class LedgerError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"cannot read valid ledger {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LedgerError("ledger root must be an object")
    return data


def _species_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    species = data.get("species")
    if not isinstance(species, list) or not species:
        raise LedgerError("species must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for item in species:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise LedgerError("each species entry requires string id")
        sid = item["id"]
        if sid in result:
            raise LedgerError(f"duplicate species id {sid}")
        for key in ("molar_mass_kg_per_mol", "charge", "oxygen_atoms"):
            if key not in item:
                raise LedgerError(f"species {sid} missing {key}")
        result[sid] = item
    return result


def _net_stoich(reaction: dict[str, Any], species: dict[str, dict[str, Any]]) -> dict[str, float]:
    net = {sid: 0.0 for sid in species}
    for side, sign in (("reactants", -1.0), ("products", 1.0)):
        terms = reaction.get(side)
        if not isinstance(terms, dict) or not terms:
            raise LedgerError(f"reaction {reaction.get('id')} missing non-empty {side}")
        for sid, coeff in terms.items():
            if sid not in species:
                raise LedgerError(f"reaction {reaction.get('id')} uses unknown species {sid}")
            try:
                value = float(coeff)
            except (TypeError, ValueError) as exc:
                raise LedgerError(f"reaction {reaction.get('id')} has nonnumeric coefficient") from exc
            if not math.isfinite(value) or value <= 0.0:
                raise LedgerError(f"reaction {reaction.get('id')} has invalid coefficient {coeff}")
            net[sid] += sign * value
    return net


def _close(value: float, scale: float = 1.0) -> bool:
    return abs(value) <= 1.0e-12 * max(1.0, abs(scale))


def validate(path: Path, *, require_r0_pass: bool) -> None:
    data = _load(path)
    species = _species_map(data)
    reactions = data.get("electron_impact_reactions")
    if not isinstance(reactions, list) or not reactions:
        raise LedgerError("electron_impact_reactions must be a non-empty list")

    failures: list[str] = []
    for reaction in reactions:
        rid = reaction.get("id", "<missing-id>")
        if not isinstance(rid, str):
            failures.append("reaction has non-string id")
            continue
        try:
            net = _net_stoich(reaction, species)
        except LedgerError as exc:
            failures.append(str(exc))
            continue

        heavy_mass = 0.0
        oxygen_atoms = 0.0
        charge = 0.0
        mass_scale = 0.0
        for sid, nu in net.items():
            meta = species[sid]
            kind = str(meta.get("kind", ""))
            molar_mass = float(meta["molar_mass_kg_per_mol"])
            if kind.startswith("heavy"):
                heavy_mass += nu * molar_mass
                mass_scale += abs(nu) * molar_mass
            oxygen_atoms += nu * float(meta["oxygen_atoms"])
            charge += nu * float(meta["charge"])

        if not _close(heavy_mass, mass_scale):
            failures.append(f"{rid}: heavy mass imbalance {heavy_mass:.17g} kg/mol-event")
        if not _close(oxygen_atoms):
            failures.append(f"{rid}: oxygen-atom imbalance {oxygen_atoms:.17g}")
        if not _close(charge):
            failures.append(f"{rid}: charge imbalance {charge:.17g} e/event")

        if not isinstance(reaction.get("rate_model"), str):
            failures.append(f"{rid}: missing rate_model")
        source_paths = reaction.get("source_paths")
        if not isinstance(source_paths, list) or not source_paths:
            failures.append(f"{rid}: missing source_paths")

    not_used = data.get("explicitly_not_used", [])
    frozen_9p97 = any(
        isinstance(item, dict)
        and item.get("data_source") == "user_supplied:o2_excitation_9p97"
        for item in not_used
    )
    if not frozen_9p97:
        failures.append("9.97 eV O2 excitation table prohibition is not recorded")

    blockers = data.get("R0_blockers", [])
    if not isinstance(blockers, list):
        failures.append("R0_blockers must be a list")
    elif require_r0_pass and blockers:
        failures.append(f"R0 still has {len(blockers)} blocker(s)")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise SystemExit(1)

    print(f"ISSUE17_R0_REACTION_LEDGER_INVARIANTS=PASS reactions={len(reactions)}")
    print(f"ISSUE17_R0_BLOCKERS={len(blockers) if isinstance(blockers, list) else 'INVALID'}")
    if blockers:
        print("ISSUE17_R0_STATUS=AUDIT_IN_PROGRESS")
    else:
        print("ISSUE17_R0_STATUS=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", nargs="?", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--require-r0-pass", action="store_true")
    args = parser.parse_args()
    validate(args.ledger, require_r0_pass=args.require_r0_pass)


if __name__ == "__main__":
    main()
