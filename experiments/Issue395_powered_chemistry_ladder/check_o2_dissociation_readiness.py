#!/usr/bin/env python3
"""Static source-resolution checker for Issue #395 O2 electron-impact dissociation.

This checker verifies the frozen provenance/source/channel-energy contract. It
does not admit the reaction to production and does not substitute for a real
physics-opt runtime discriminator.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

NA = 6.02214076e23
EXPECTED_SHA256 = "bcd0cc004ea8657c5b77d684065acfad4fce02a497efbc0e231d7d3cf3727568"
EXPECTED_ROWS = 16
EXPECTED_FLOOR = 1.0e-20
EXPECTED_FLOOR_MAX_E = 5.1


def read_table(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            energy, rate = next(csv.reader([line]))
            rows.append((float(energy), float(rate)))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    a = ap.parse_args()

    raw = a.table.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rows = read_table(a.table)
    contract = json.loads(a.contract.read_text(encoding="utf-8"))

    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    hist = contract["historical_rate_artifact"]
    require(sha == EXPECTED_SHA256, "historical SHA256 mismatch")
    require(hist["sha256"] == EXPECTED_SHA256, "contract SHA256 mismatch")
    require(len(rows) == EXPECTED_ROWS, "unexpected row count")
    require(
        all(math.isfinite(e) and math.isfinite(k) and k >= 0.0 for e, k in rows),
        "non-finite or negative table entry",
    )
    require(
        all(rows[i + 1][0] > rows[i][0] for i in range(len(rows) - 1)),
        "mean-energy grid is not strictly increasing",
    )
    require(
        hist["scientific_source_status"] == "NO_DIRECT_SOURCE_ESTABLISHED",
        "historical CSV must remain without invented direct provenance",
    )
    require(
        hist["disposition"] == "HISTORICAL_PROVENANCE_ONLY_DO_NOT_USE_FOR_PRODUCTION",
        "historical CSV production disposition changed",
    )

    floor = hist["floor_signature"]
    floor_rows = [(e, k) for e, k in rows if e <= EXPECTED_FLOOR_MAX_E]
    require(
        bool(floor_rows) and all(k == EXPECTED_FLOOR for _, k in floor_rows),
        "historical low-energy floor signature changed",
    )
    require(max(e for e, _ in floor_rows) == EXPECTED_FLOOR_MAX_E, "historical floor boundary changed")
    require(
        floor["disposition"] == "HISTORICAL_NUMERICAL_SENTINEL_PROVENANCE_ONLY",
        "historical floor must remain provenance-only",
    )

    source = contract["source_backed_replacement_candidate"]
    require(source["reaction"] == "e + O2 -> 2O + e", "source-backed reaction changed")
    require(
        source["rate_coefficient_particle_m3_per_s"]
        == "1.41e-15 * Te_eV^0.22 * exp(-12.62/Te_eV)",
        "source-backed SI rate law changed",
    )
    require(
        source["canonical_temperature_mapping"] == "Te_eV=(2/3)*mean_en_solved_eV",
        "canonical Te mapping changed",
    )
    require(
        source["domain_policy"] == "Evaluate only finite Te_eV > 0; no artificial rate floor or clamp.",
        "analytic-model floor/clamp policy changed",
    )
    require(
        source["primary_attribution"]["doi"] == "10.1088/0963-0252/22/4/045010",
        "Murakami attribution changed",
    )
    verify = source["independent_reaction_set_verification"]
    require(verify["doi"] == "10.1088/1361-6595/acd57f", "Brisset verification DOI changed")
    require(verify["reaction_id"] == "R44", "Brisset reaction identity changed")
    require(verify["energy_cost_eV"] == 12.62, "source-backed energy cost changed")
    require(
        source["relationship_to_historical_csv"]
        == "REPLACEMENT_CANDIDATE_NOT_A_SOURCE_IDENTIFICATION_FOR_THE_CSV",
        "historical/source relationship changed",
    )

    # Ensure the new source-backed law is not silently treated as provenance for
    # the recovered table. At mean energy 6 eV, canonical Te is 4 eV.
    rate_by_mean_energy = dict(rows)
    probe_mean_energy = 6.0
    probe_te = (2.0 / 3.0) * probe_mean_energy
    source_k = 1.41e-15 * probe_te**0.22 * math.exp(-12.62 / probe_te)
    historical_k = rate_by_mean_energy[probe_mean_energy]
    ratio = historical_k / source_k
    require(ratio > 10.0, "source-backed law unexpectedly matches historical CSV")

    channel = contract["channel_and_energy_resolution"]
    require(
        channel["historical_csv_fragment_channel"] == "NOT_PROVABLE_FROM_RECOVERED_ARTIFACT",
        "historical CSV fragment-state claim became over-specific",
    )
    thermo = channel["thermochemical_ground_state_threshold"]
    require(
        thermo["role"] == "THERMOCHEMICAL_THRESHOLD_ONLY_NOT_MODEL_ENERGY_COST",
        "5.12 eV thermochemical/model-energy distinction changed",
    )
    require(abs(thermo["dissociation_energy_eV_approx"] - 5.1156) < 1.0e-6, "thermochemical threshold changed")
    require(channel["state_resolution_caveat"]["doi"] == "10.1063/1.464387", "Cosby channel evidence changed")
    lumped = channel["source_backed_lumped_model"]
    require(
        lumped["effective_electron_energy_cost_eV_per_event"] == 12.62
        and lumped["energy_cost_status"] == "FROZEN_FOR_BOUNDED_IMPLEMENTATION",
        "12.62 eV bounded model energy cost is not frozen",
    )
    require(
        lumped["five_point_12_eV_disposition"]
        == "THERMOCHEMICAL_THRESHOLD_ONLY_NOT_ELECTRON_ENERGY_LOSS_FOR_THIS_MODEL",
        "5.12 eV was promoted to model energy loss",
    )

    impl = contract["implementation_contract"]
    require(
        impl["canonical_progress"] == "R_diss_O2"
        and impl["planned_progress_owner"] == "PhysicsElectronImpactRateMaterial",
        "single progress-owner contract changed",
    )
    require(
        "must not interpolate the historical CSV" in impl["owner_rate_policy"],
        "historical CSV was not excluded from the production rate owner",
    )
    require(
        impl["stoichiometry_per_event"] == {"O2": -1, "O": 2, "electron_particle": 0},
        "dissociation stoichiometry changed",
    )
    require(
        impl["closures"] == {"heavy_mass": 0, "oxygen_nuclei": 0, "charge": 0},
        "mass/oxygen/charge closure changed",
    )
    require(
        impl["electron_energy_projection"] == "-12.62 * N_A * R_diss_O2 [eV/(m^3 s)]",
        "electron-energy projection changed",
    )

    n_e = 2.4e16
    c_e = n_e / NA
    c_o2 = 3.0e-4
    particle_form = source_k * n_e * c_o2
    molar_form = (NA * source_k) * c_e * c_o2
    require(
        math.isclose(particle_form, molar_form, rel_tol=1.0e-14, abs_tol=0.0),
        "particle-to-molar progress conversion mismatch",
    )

    require(
        contract["status"] == "SOURCE_MODEL_FROZEN_NOT_PRODUCTION_ADMITTED",
        "contract status changed",
    )
    require("RF-OFF" in contract["next_obligation"], "next discriminator is not RF-OFF")

    report = {
        "issue": 395,
        "classification": (
            "ISSUE395_O2_DISSOCIATION_SOURCE_RESOLUTION_PASS"
            if not failures
            else "ISSUE395_O2_DISSOCIATION_SOURCE_RESOLUTION_FAIL"
        ),
        "status": "PASS" if not failures else "FAIL",
        "production_admitted": False,
        "contract_status": contract["status"],
        "historical_table": {
            "sha256": sha,
            "rows": len(rows),
            "source_status": hist["scientific_source_status"],
            "disposition": hist["disposition"],
            "floor_disposition": floor["disposition"],
        },
        "source_backed_candidate": {
            "primary_doi": source["primary_attribution"]["doi"],
            "verification_doi": verify["doi"],
            "reaction": source["reaction"],
            "energy_cost_eV": verify["energy_cost_eV"],
            "probe_mean_energy_eV": probe_mean_energy,
            "probe_Te_eV": probe_te,
            "probe_rate_m3_s": source_k,
            "historical_probe_rate_m3_s": historical_k,
            "historical_to_source_ratio": ratio,
        },
        "channel_energy": {
            "historical_fragment_state": channel["historical_csv_fragment_channel"],
            "ground_state_threshold_eV": thermo["dissociation_energy_eV_approx"],
            "model_energy_cost_eV": lumped["effective_electron_energy_cost_eV_per_event"],
        },
        "resolved_items": contract["resolved_items"],
        "next_obligation": contract["next_obligation"],
        "failures": failures,
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
