#!/usr/bin/env python3
"""Static contract checker for Issue #395 chemistry activation ladder.

This is a P0/P1 construction guard only. It proves that the staged activation
sets are monotonic, that A8 matches the canonical accepted S5-R-v1 ledger, that
A1 is exactly the intended EI02+EI16 minimal sustaining set, and that the two
required A1 rate tables are present with the accepted lookup domain.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LADDER = HERE / "chemistry_sets.json"
CANONICAL = ROOT / "docs/development/2026-09-11_issue192_stage5_s5r_representative_contract.json"

EXPECTED_STAGES = [f"A{i}" for i in range(9)]
EXPECTED_A1 = {"EI02", "EI16"}
EXPECTED_DOMAIN = (1.40991, 22.1378)


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise AssertionError(f"missing required file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_two_column_table(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        fields = s.replace(",", " ").split()
        if len(fields) != 2:
            raise AssertionError(f"{path.relative_to(ROOT)}:{line_no}: expected exactly two columns")
        rows.append((float(fields[0]), float(fields[1])))
    if len(rows) < 2:
        raise AssertionError(f"insufficient rows: {path.relative_to(ROOT)}")
    for (x0, _), (x1, _) in zip(rows, rows[1:]):
        if not x1 > x0:
            raise AssertionError(f"non-monotonic lookup coordinate: {path.relative_to(ROOT)}")
    return rows


def check() -> None:
    ladder = load_json(LADDER)
    canonical = load_json(CANONICAL)

    if ladder.get("schema_version") != 1 or ladder.get("issue") != 395:
        raise AssertionError("Issue #395 ladder identity/schema changed")

    sets = ladder.get("sets", {})
    if list(sets) != EXPECTED_STAGES:
        raise AssertionError(f"expected stages {EXPECTED_STAGES}, got {list(sets)}")

    for stage in EXPECTED_STAGES:
        values = sets[stage]
        if len(values) != len(set(values)):
            raise AssertionError(f"duplicate reaction in {stage}")

    if sets["A0"] != []:
        raise AssertionError("A0 must be chemistry OFF")
    if set(sets["A1"]) != EXPECTED_A1 or len(sets["A1"]) != 2:
        raise AssertionError("A1 must contain exactly EI02 + EI16")

    # Promotion must be monotonic: no accepted reaction disappears at a later stage.
    for prev, cur in zip(EXPECTED_STAGES, EXPECTED_STAGES[1:]):
        if not set(sets[prev]).issubset(sets[cur]):
            raise AssertionError(f"non-monotonic activation: {prev} -> {cur}")

    admitted = canonical.get("admitted_channels")
    if canonical.get("admitted_ledger_version") != "S5-R-v1" or not isinstance(admitted, list):
        raise AssertionError("unexpected canonical S5-R contract")
    if set(sets["A8"]) != set(admitted) or len(sets["A8"]) != len(admitted):
        raise AssertionError("A8 does not exactly match canonical S5-R-v1 admitted ledger")

    blocked = set(ladder.get("explicitly_blocked", []))
    canonical_excluded = {
        row["channel"]
        for row in canonical.get("explicit_exclusions", [])
        if row.get("disposition") == "BLOCKED_SOURCE_REFERENCE_ONLY"
    }
    if blocked != canonical_excluded:
        raise AssertionError("blocked-channel set drifted from canonical S5-R contract")

    # A1 source identity / table availability checks.
    a1 = ladder.get("A1_contract", {})
    if set(a1) != EXPECTED_A1:
        raise AssertionError("A1 contract keys must be EI02 and EI16")

    for rid in ("EI02", "EI16"):
        table_path = ROOT / a1[rid]["rate_table"]
        if not table_path.is_file():
            raise AssertionError(f"missing A1 rate table: {table_path.relative_to(ROOT)}")
        rows = read_two_column_table(table_path)
        domain = (rows[0][0], rows[-1][0])
        if domain != EXPECTED_DOMAIN:
            raise AssertionError(f"{rid} lookup domain changed: {domain}")

    if a1["EI02"].get("particle_stoichiometry_change") is not False:
        raise AssertionError("EI02 must remain particle-neutral / energy-only")
    if a1["EI16"].get("net_electron_source_per_event") != 1:
        raise AssertionError("EI16 net electron source changed")
    if float(a1["EI16"].get("energy_loss_eV_per_event")) != 12.06:
        raise AssertionError("EI16 12.06 eV energy-loss contract changed")

    rules = ladder.get("rules", {})
    required_true = (
        "monotonic_activation",
        "exactly_one_progress_owner",
        "duplicate_kinetic_reevaluation_forbidden",
        "strict_lookup_bounds",
        "synthetic_rate_data_forbidden",
        "rf_and_electrostatic_heating_owners_separate",
    )
    for key in required_true:
        if rules.get(key) is not True:
            raise AssertionError(f"required rule disabled: {key}")

    if rules.get("physical_electron_density") != "N_A * exp(log_ne)":
        raise AssertionError("physical electron-density bridge changed")
    if rules.get("physical_mean_energy_eV") != "exp(log_energy - log_ne)":
        raise AssertionError("mean-energy bridge changed")

    print("ISSUE395_CHEMISTRY_LADDER_CONTRACT_PASS")
    print("initial_runtime_scope=A0,A1")
    print("A1=EI02,EI16")
    print(f"A8_channels={len(sets['A8'])}")
    print(f"lookup_domain_eV={EXPECTED_DOMAIN[0]},{EXPECTED_DOMAIN[1]}")
    print("claim=static activation/source contract only")


if __name__ == "__main__":
    check()
