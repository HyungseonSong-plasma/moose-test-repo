#!/usr/bin/env python3
"""Static P0/preflight for Stage-5 S5-R representative real-QVT assembly.

This checker establishes only that the frozen S5-R ledger and its production-state
providers are internally consistent and available for assembly. It does not claim
that a representative input has been assembled, that --check-input passes, or that
representative runtime evidence exists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/development/2026-09-11_issue192_stage5_s5r_representative_contract.json"
HEAVY = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
ELECTRON = ROOT / "physics_app/ci/electron_energy_real_qvt_inventory_smoke.i"
OWNERSHIP = ROOT / "docs/development/2026-09-10_issue176_stage5_reaction_ownership_contract.json"
E8 = ROOT / "docs/development/2026-09-10_issue26_e8_closure_surface_contract.json"
E8_ELASTIC = ROOT / "docs/development/2026-09-10_issue26_e8_elastic_ei19_contract.json"
H05 = ROOT / "docs/development/2026-09-11_issue191_stage5_h05_contract.json"
EI01_RECOVERY = ROOT / "docs/development/2026-09-11_issue192_s5r_ei01_attachment_recovery.json"
EI01_TABLE = ROOT / "physics_app/data/electron_impact/o2_attachment.txt"

EXPECTED_LEDGER = [
    "EI01",
    "EI02",
    "EI10",
    "EI16",
    "EI17",
    "EI19",
    "EI18_O_TO_OS",
    "EI20_O_IONIZATION",
    "EDETACH_OM",
    "H01_OP_O2_CHARGE_TRANSFER",
    "H02_OM_OP_NEUTRALIZATION",
    "H03_OM_O2P_TO_3O",
    "H04_OM_O2P_TO_O_O2",
    "H05_OM_O_DETACHMENT",
]

EXPECTED_STAGE5 = {
    "EI18_O_TO_OS": ("R_excitation_O_1p968", "PhysicsElectronImpactRateMaterial"),
    "EI20_O_IONIZATION": ("R_ion_O", "PhysicsElectronImpactRateMaterial"),
    "EDETACH_OM": ("R_detach_Om", "ADParsedFunctorMaterial"),
    "H01_OP_O2_CHARGE_TRANSFER": ("reaction_rate_H01_Op_O2_charge_transfer", "PhysicsReactionRateMaterial"),
    "H02_OM_OP_NEUTRALIZATION": ("reaction_rate_H02_Om_Op_neutralization", "PhysicsReactionRateMaterial"),
    "H03_OM_O2P_TO_3O": ("reaction_rate_H03_Om_O2p_to_3O", "PhysicsReactionRateMaterial"),
    "H04_OM_O2P_TO_O_O2": ("reaction_rate_H04_Om_O2p_to_O_O2", "PhysicsReactionRateMaterial"),
    "H05_OM_O_DETACHMENT": ("reaction_rate_H05_Om_O_to_O2_electron", "PhysicsReactionRateMaterial"),
}

EXPECTED_EXCLUSIONS = {
    "e + O2 -> e + O + O": "BLOCKED_SOURCE_REFERENCE_ONLY",
    "e + O2 -> e + O + Os": "BLOCKED_SOURCE_REFERENCE_ONLY",
    "Om + Arp -> O + Ar": "OUT_OF_SCOPE",
}


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise AssertionError(f"missing required contract: {path.relative_to(ROOT)}")
    return json.loads(path.read_text())


def _require(text: str, token: str, label: str) -> None:
    if token not in text:
        raise AssertionError(f"{label}: missing {token!r}")


def _read_two_column_table(path: Path) -> list[tuple[float, float]]:
    if not path.is_file():
        raise AssertionError(f"missing required table: {path.relative_to(ROOT)}")
    rows = []
    for line_no, raw in enumerate(path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        fields = stripped.split()
        if len(fields) != 2:
            raise AssertionError(f"{path.relative_to(ROOT)}:{line_no}: expected two columns")
        rows.append((float(fields[0]), float(fields[1])))
    return rows


def _check_ei01_recovery() -> None:
    recovery = _load_json(EI01_RECOVERY)
    if recovery.get("schema_version") != 1:
        raise AssertionError("unexpected EI01 recovery schema")
    if recovery.get("controller_issue") != 176 or recovery.get("child_issue") != 192:
        raise AssertionError("EI01 recovery controller/child identity changed")
    if recovery.get("channel") != "EI01_O2_ATTACHMENT":
        raise AssertionError("EI01 recovery channel identity changed")
    if recovery.get("status") != "PRODUCTION_RATE_OWNER_RECOVERED":
        raise AssertionError("EI01 production rate owner is not recovered")

    provenance = recovery.get("provenance", {})
    if provenance.get("source_identity") != "user_supplied:o2_attachment":
        raise AssertionError("EI01 source identity changed")
    if provenance.get("canonical_path") != "physics_app/data/electron_impact/o2_attachment.txt":
        raise AssertionError("EI01 canonical table path changed")

    raw = EI01_TABLE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != provenance.get("sha256"):
        raise AssertionError("EI01 table SHA-256 does not match frozen recovery provenance")

    lookup = recovery.get("lookup_contract", {})
    if lookup.get("coordinate") != "mean_en_solved":
        raise AssertionError("EI01 lookup coordinate is not solved mean energy")
    if lookup.get("coordinate_unit") != "eV":
        raise AssertionError("EI01 lookup coordinate unit changed")
    if lookup.get("value_unit") != "m^3/(mol s)":
        raise AssertionError("EI01 lookup rate unit changed")
    if lookup.get("rows") != 100:
        raise AssertionError("EI01 lookup row count contract changed")
    if lookup.get("domain_eV") != [1.40991, 22.1378]:
        raise AssertionError("EI01 lookup domain changed")
    if lookup.get("bounds_policy") != "error":
        raise AssertionError("EI01 lookup must remain strict")

    rows = _read_two_column_table(EI01_TABLE)
    if len(rows) != lookup["rows"]:
        raise AssertionError("EI01 table row count does not match recovery contract")
    if rows[0][0] != lookup["domain_eV"][0] or rows[-1][0] != lookup["domain_eV"][1]:
        raise AssertionError("EI01 table domain does not match recovery contract")
    for (x0, _), (x1, _) in zip(rows, rows[1:]):
        if not x1 > x0:
            raise AssertionError("EI01 mean-energy grid must be strictly increasing")

    row_map = dict(rows)
    anchors = lookup.get("anchors_m3_per_mol_s", {})
    for x_text, expected in anchors.items():
        x = float(x_text)
        if x not in row_map or row_map[x] != expected:
            raise AssertionError(f"EI01 table anchor mismatch at {x_text} eV")

    owner = recovery.get("progress_owner", {})
    if owner.get("type") != "PhysicsElectronImpactRateMaterial":
        raise AssertionError("EI01 progress owner type changed")
    if owner.get("rate_table_file") != "physics_app/data/electron_impact/o2_attachment.txt":
        raise AssertionError("EI01 progress owner table binding changed")
    if owner.get("mean_energy") != "mean_en_solved":
        raise AssertionError("EI01 progress owner mean-energy binding changed")
    if owner.get("reaction_progress") != "R_attachment":
        raise AssertionError("EI01 canonical progress identity changed")

    projection = recovery.get("projection_contract", {})
    if projection.get("electron_energy") != "NONE_REQUIRED_ZERO_TERM":
        raise AssertionError("EI01 zero-energy convention changed")
    if projection.get("duplicate_kinetic_reevaluation") != "FORBIDDEN":
        raise AssertionError("EI01 duplicate kinetic reevaluation guard changed")


def check() -> None:
    contract = _load_json(CONTRACT)
    _load_json(OWNERSHIP)
    _load_json(E8)
    _load_json(E8_ELASTIC)
    h05 = _load_json(H05)
    _check_ei01_recovery()

    if contract.get("schema_version") != 1:
        raise AssertionError("unexpected S5-R contract schema")
    if contract.get("controller_issue") != 176 or contract.get("child_issue") != 192:
        raise AssertionError("S5-R controller/child identity changed")
    if contract.get("status") != "ASSEMBLY_CONTRACT_FROZEN":
        raise AssertionError("S5-R contract is not frozen")
    if contract.get("admitted_ledger_version") != "S5-R-v1":
        raise AssertionError("unexpected admitted-ledger version")
    if contract.get("admitted_channels") != EXPECTED_LEDGER:
        raise AssertionError("S5-R admitted ledger changed")
    if len(set(EXPECTED_LEDGER)) != len(EXPECTED_LEDGER):
        raise AssertionError("duplicate channel in expected S5-R ledger")

    exclusions = {
        item["channel"]: item["disposition"] for item in contract.get("explicit_exclusions", [])
    }
    if exclusions != EXPECTED_EXCLUSIONS:
        raise AssertionError("S5-R exclusion surface changed")
    if set(exclusions).intersection(EXPECTED_LEDGER):
        raise AssertionError("excluded channel appears in admitted ledger")

    rules = contract.get("ownership_rules", {})
    for key in (
        "exactly_one_progress_owner_per_admitted_channel",
        "downstream_kinetic_reevaluation_forbidden",
        "all_species_particle_energy_projections_consume_canonical_progress",
        "reuse_standard_moose_energy_projection_when_representable",
    ):
        if rules.get(key) is not True:
            raise AssertionError(f"required S5-R ownership rule disabled: {key}")

    owner_map = contract.get("stage5_owner_map", {})
    if set(owner_map) != set(EXPECTED_STAGE5):
        raise AssertionError("Stage-5 owner map does not match admitted Stage-5 ledger")
    progress_names = []
    for channel, (progress, owner) in EXPECTED_STAGE5.items():
        row = owner_map[channel]
        if row.get("progress") != progress or row.get("owner") != owner:
            raise AssertionError(f"owner-map mismatch for {channel}")
        progress_names.append(progress)
    if len(set(progress_names)) != len(progress_names):
        raise AssertionError("duplicate canonical Stage-5 progress name")

    h05_row = owner_map["H05_OM_O_DETACHMENT"]
    if h05_row.get("electron_particle_projection") != "PhysicsFVElectronReactionSource":
        raise AssertionError("H05 electron-particle ownership changed")
    if h05_row.get("electron_energy_projection") != "NONE":
        raise AssertionError("H05 explicit electron-energy source was reintroduced")
    if "ADMITTED" not in h05_row.get("model_decision", ""):
        raise AssertionError("H05 admitted disposition missing from S5-R owner map")
    if h05.get("status") not in {"MODEL_DECISION_FROZEN", "ACCEPTED_BOUNDED"}:
        h05_text = H05.read_text()
        _require(h05_text, "3.0e-16", "H05 contract")
        _require(h05_text, "electron", "H05 contract")

    inherited = contract.get("inherited_stage3_stage4_ownership", {})
    if inherited.get("channels") != EXPECTED_LEDGER[:6]:
        raise AssertionError("inherited Stage-3/4 channel set changed")
    if len(inherited.get("contracts", [])) != 3:
        raise AssertionError("inherited ownership contract set incomplete")

    heavy = HEAVY.read_text()
    _require(heavy, "prop_names = 'T_g T_e n_e mu_flow'", "real-QVT heavy state")
    _require(heavy, "property_name = w_O2_constraint", "real-QVT heavy state")
    _require(heavy, "property_name = rho_mat", "real-QVT heavy state")
    _require(heavy, "functor_names = 'p Mn_mix T_g'", "real-QVT density")
    _require(heavy, "temperature = T_g", "real-QVT heavy transport")
    _require(heavy, "functor_names = 'D_mix_O2p T_g'", "O2+ mobility")
    _require(heavy, "functor_names = 'D_mix_Om T_g'", "O- mobility")
    _require(heavy, "functor_names = 'D_mix_Op T_g'", "O+ mobility")

    electron = ELECTRON.read_text()
    _require(electron, "type = PhysicsElectronMeanEnergyMaterial", "electron-energy oracle")
    _require(electron, "electron_energy_density = n_epsilon", "electron-energy oracle")
    _require(electron, "electron_density = n_e", "electron-energy oracle")
    _require(electron, "type = PhysicsElectronTransportLookupMaterial", "electron transport")
    _require(electron, "mean_energy = mean_en_solved", "electron transport")
    _require(electron, "bounds_policy = error", "electron transport")
    if "bounds_policy = clamp" in electron or "bounds_policy = floor" in electron:
        raise AssertionError("non-strict electron transport lookup found")

    ident = contract.get("representative_identity", {})
    expected_identity = {
        "geometry": "experiments/Issue91_real_qvt_r3/r3_e0/qvt.msh",
        "heavy_state_reference": "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i",
        "electron_energy_reference": "physics_app/ci/electron_energy_real_qvt_inventory_smoke.i",
        "electron_transport_table": "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
        "required_heavy_temperature_functor": "T_g",
        "required_density_functor": "rho_mat",
        "required_constrained_oxygen_functor": "w_O2_constraint",
        "required_solved_mean_energy_functor": "mean_en_solved",
    }
    if ident != expected_identity:
        raise AssertionError("representative identity/state binding changed")
    for relative in (
        ident["geometry"],
        ident["heavy_state_reference"],
        ident["electron_energy_reference"],
        ident["electron_transport_table"],
    ):
        if not (ROOT / relative).is_file():
            raise AssertionError(f"missing representative dependency: {relative}")

    gate = contract.get("construction_gate", {})
    if gate.get("next_artifact") != "canonical executable S5-R representative input/checker surface":
        raise AssertionError("S5-R construction target changed")

    print("S5R_P0_PROVIDER_OWNER_PREFLIGHT_PASS")
    print("ei01_production_rate_owner=RECOVERED")
    print("claim=provider/ledger/state-binding preflight only")
    print("representative_assembly=NOT_YET_ESTABLISHED")
    print("check_input=NOT_YET_ESTABLISHED")
    print("representative_runtime=NOT_YET_ESTABLISHED")


if __name__ == "__main__":
    check()
