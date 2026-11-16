#!/usr/bin/env python3
"""Readonly Issue #402 legacy symbol inventory, migrated from the historical one-shot.

This is a *reporting* gate, not proof that a symbol is unused or that
Native P2/P3 or scientific parity passes. Keep the exact historical terms and
tracked-file counting semantics while moving ownership into canonical CI.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

TERMS = ("log_energy", "mean_en_solved", "PhysicsElectronMeanEnergyMaterial", "PhysicsElectronWallFluxMaterial", "PhysicsElectronAdjacentSheathWallFluxMaterial", "ElectronWallFluxMaterial", "ESWallFluxMaterial", "normalized",)


def inventory(root: Path, paths: list[str]) -> dict[str, dict[str, list[int]]]:
    result: dict[str, dict[str, list[int]]] = {}
    for term in TERMS:
        hits: dict[str, list[int]] = defaultdict(list)
        for path in paths:
            if not path:
                continue
            try:
                with (root / path).open(encoding="utf-8") as stream:
                    for number, line in enumerate(stream, 1):
                        if term in line:
                            hits[path].append(number)
            except (UnicodeError, OSError):
                continue
        result[term] = dict(hits)
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "sample.txt"
        path.write_text("mean_en_solved\nlog_energy and mean_en_solved\n", encoding="utf-8")
        original = inventory(root, ["sample.txt", "missing.txt"])
        assert original["mean_en_solved"] == {"sample.txt": [1, 2]}
        assert original["log_energy"] == {"sample.txt": [2]}
        path.write_text("log_energy\n", encoding="utf-8")
        mutated = inventory(root, ["sample.txt"])
        assert mutated["mean_en_solved"] == {}
        assert mutated["log_energy"] == {"sample.txt": [1]}
    print("ISSUE402_LEGACY_SYMBOL_INVENTORY_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.check:
        parser.error("select --self-test or --check")
    root = Path(__file__).resolve().parents[2]
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root
    ).decode().split("\0")
    report = inventory(root, tracked)
    for term in TERMS:
        hits = report[term]
        print("SYMBOL", term, "FILES", len(hits),
              "HITS", sum(map(len, hits.values())), flush=True)
        for path, numbers in sorted(hits.items()):
            print("REF", term, path, ",".join(map(str, numbers[:40])), flush=True)
    print("ISSUE402_LEGACY_SYMBOL_INVENTORY_PASS")


if __name__ == "__main__":
    main()
