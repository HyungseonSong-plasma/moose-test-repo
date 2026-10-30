"""Strict external BOLSIG+ oracle comparison (developer/science validation only).

This checker does NOT parse raw BOLSIG+ output or operate the BOLSIG+ binary.
The reference and candidate must be independently converted to the declared
common-cell JSON contract with immutable source and byte-level provenance.
No real LXCat data and no BOLSIG+ golden oracle are bundled in this repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


class ReferenceContractError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReferenceContractError(f"cannot decode JSON: {path.name}") from exc
    if not isinstance(obj, dict):
        raise ReferenceContractError("expected JSON object")
    return obj


def _read_hashed(directory: Path, record: dict[str, Any]) -> bytes:
    if not isinstance(record, dict):
        raise ReferenceContractError("file record must be an object")
    name, expected = record.get("path"), record.get("sha256")
    if not isinstance(name, str) or not name or not isinstance(expected, str) or (
        len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected)
    ):
        raise ReferenceContractError("file metadata requires path and lowercase SHA256")
    selected = directory / name
    if selected.name != name or selected.is_symlink() or not selected.is_file():
        raise ReferenceContractError("case files must be regular direct-child files")
    data = selected.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ReferenceContractError(f"SHA256 mismatch for {name}")
    return data


def _finite_float(value: Any, label: str, *, zero_ok: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ReferenceContractError(f"{label} must be numeric")
    val = float(value)
    if not math.isfinite(val) or (val < 0 if zero_ok else val <= 0):
        raise ReferenceContractError(f"{label} invalid or non-finite")
    return val


def _validate_series(obj: dict[str, Any], *, name: str) -> tuple[list[float], list[float], list[float], dict[str, float]]:
    if obj.get("schema_version") != 1:
        raise ReferenceContractError(f"{name}: unsupported result schema")
    edges_raw = obj.get("energy_cell_edges_eV")
    f_raw = obj.get("eepf_eV_minus_3_halves")
    if not isinstance(edges_raw, list) or not isinstance(f_raw, list) or (
        len(edges_raw) != len(f_raw) + 1 or len(f_raw) < 2
    ):
        raise ReferenceContractError(f"{name}: invalid common energy mesh")
    edges = [_finite_float(v, "energy edge", zero_ok=True) for v in edges_raw]
    if edges[0] != 0 or any(b <= a for a, b in zip(edges, edges[1:])):
        raise ReferenceContractError(f"{name}: energy cells require increasing edges starting at zero")
    f = [_finite_float(v, "EEPF", zero_ok=True) for v in f_raw]
    weights = [(2 / 3) * (b**1.5 - a**1.5) for a, b in zip(edges, edges[1:])]
    area = sum(w * v for w, v in zip(weights, f))
    if not math.isfinite(area) or abs(area - 1.0) > 2e-5:
        raise ReferenceContractError(f"{name}: EEPF normalization is inconsistent")
    moment = sum(
        v * (2 / 5) * (b**2.5 - a**2.5)
        for v, a, b in zip(f, edges, edges[1:])
    )
    mean = _finite_float(obj.get("mean_energy_eV"), f"{name} mean energy")
    if abs(moment - mean) / mean > 2e-5:
        raise ReferenceContractError(f"{name}: EEPF moment disagrees with reported mean energy")
    rates = obj.get("rates_m3_per_s")
    if not isinstance(rates, dict) or not rates:
        raise ReferenceContractError(f"{name}: at least one reaction rate required")
    clean_rates: dict[str, float] = {}
    for key, val in rates.items():
        if not isinstance(key, str) or not key:
            raise ReferenceContractError(f"{name}: invalid reaction identifier")
        clean_rates[key] = _finite_float(val, f"{name}:{key} rate", zero_ok=True)
    return edges, weights, f, clean_rates


def compare_case(directory: Path) -> dict[str, Any]:
    """Return stable decision/evidence for an independently captured reference."""
    case = _read_object(directory / "case.json")
    if case.get("schema_version") != 1:
        raise ReferenceContractError("unsupported case schema")
    source, reference, candidate = (case.get(k) for k in ("source", "reference", "candidate"))
    if any(not isinstance(obj, dict) for obj in (source, reference, candidate)):
        raise ReferenceContractError("source/reference/candidate records are required")

    for required in ("database", "source_url", "retrieved_utc", "process_ids", "rate_process_ids"):
        if not source.get(required):
            raise ReferenceContractError(f"missing collision provenance: {required}")
    if not isinstance(source["process_ids"], list) or not all(
        isinstance(x, str) and x for x in source["process_ids"]
    ):
        raise ReferenceContractError("source process_ids must be nonempty strings")
    if len(source["process_ids"]) != len(set(source["process_ids"])):
        raise ReferenceContractError("duplicate source process identifiers")
    if not isinstance(source["rate_process_ids"], list) or not source["rate_process_ids"] or (
        any(not isinstance(x, str) or not x for x in source["rate_process_ids"])
    ):
        raise ReferenceContractError("source rate_process_ids must be nonempty strings")
    if len(source["rate_process_ids"]) != len(set(source["rate_process_ids"])) or (
        not set(source["rate_process_ids"]).issubset(source["process_ids"])
    ):
        raise ReferenceContractError("rate process identifiers must be unique and sourced")
    if reference.get("solver") != "BOLSIG+" or not reference.get("version") or (
        not reference.get("raw_export_sha256")
    ):
        raise ReferenceContractError("reference must identify BOLSIG+ version and raw export hash")
    if not candidate.get("code_revision"):
        raise ReferenceContractError("candidate must identify source code revision")

    source_bytes = _read_hashed(directory, source)
    _read_hashed(directory, {"path": reference.get("raw_export_path"),
                             "sha256": reference.get("raw_export_sha256")})
    reference_bytes = _read_hashed(directory, reference)
    candidate_bytes = _read_hashed(directory, candidate)
    if len(source_bytes) < 1:
        raise ReferenceContractError("empty source file")
    try:
        ref_obj = json.loads(reference_bytes)
        cand_obj = json.loads(candidate_bytes)
    except (ValueError, UnicodeError) as exc:
        raise ReferenceContractError("invalid series JSON file") from exc
    if not isinstance(ref_obj, dict) or not isinstance(cand_obj, dict):
        raise ReferenceContractError("series must be JSON objects")

    state_ref, state_cand = ref_obj.get("conditions"), cand_obj.get("conditions")
    if not isinstance(state_ref, dict) or state_ref != state_cand:
        raise ReferenceContractError("reference/candidate physical state mismatch")
    if state_ref.get("collision_source_sha256") != source["sha256"]:
        raise ReferenceContractError("reference source identity does not match verified raw bytes")
    if not state_ref.get("model") or not isinstance(state_ref.get("mixture"), dict):
        raise ReferenceContractError("collision model and composition must be explicit")
    _finite_float(state_ref.get("reduced_field_Td"), "reduced field", zero_ok=True)
    _finite_float(state_ref.get("gas_temperature_K"), "gas temperature")
    fractions = state_ref["mixture"]
    if not fractions or any(not isinstance(k, str) or not k for k in fractions):
        raise ReferenceContractError("invalid species names")
    if abs(sum(_finite_float(v, "mole fraction") for v in fractions.values()) - 1.0) > 1e-12:
        raise ReferenceContractError("invalid mixture mole fractions")

    edges_r, weights, eepf_r, rates_r = _validate_series(ref_obj, name="reference")
    edges_c, _, eepf_c, rates_c = _validate_series(cand_obj, name="candidate")
    if edges_c != edges_r:
        raise ReferenceContractError("energy cell edges differ: explicit separately audited regridding required")
    if rates_r.keys() != rates_c.keys():
        raise ReferenceContractError("candidate and oracle reaction inventories differ")
    if set(rates_r) != set(source["rate_process_ids"]):
        raise ReferenceContractError("numeric rate inventory does not match source process ledger")

    # Optional independent BOLSIG+ four-moment transport comparison.
    # These are genuinely independent output fields, not the same 5/3
    # Maxwellian energy-closure proxy used by existing production materials.
    transport_keys = {
        "mobility_times_N_per_m_V_s",
        "diffusion_times_N_per_m_s",
        "energy_mobility_times_N_per_m_V_s",
        "energy_diffusion_times_N_per_m_s",
    }
    ref_transport = ref_obj.get("elastic_transport")
    cand_transport = cand_obj.get("elastic_transport")
    compare_transport = ref_transport is not None or cand_transport is not None
    if compare_transport:
        if not isinstance(ref_transport, dict) or not isinstance(cand_transport, dict):
            raise ReferenceContractError("both reference and candidate need transport moments")
        if not transport_keys.issubset(ref_transport) or not transport_keys.issubset(cand_transport):
            raise ReferenceContractError("incomplete reference/candidate transport inventory")
        for key in transport_keys:
            _finite_float(ref_transport[key], f"reference {key}")
            _finite_float(cand_transport[key], f"candidate {key}")

    tol = case.get("tolerances")
    required_tol = {
        "mean_energy_relative", "eepf_weighted_l1", "rate_relative",
        "zero_rate_absolute_m3_per_s"
    }
    if compare_transport:
        required_tol.add("transport_relative")
    if not isinstance(tol, dict) or set(tol) != required_tol:
        raise ReferenceContractError("predeclared comparison tolerances incomplete or inconsistent")
    thresholds = {k: _finite_float(v, k, zero_ok=True) for k, v in tol.items()}
    mean_r = ref_obj["mean_energy_eV"]
    mean_c = cand_obj["mean_energy_eV"]
    mean_error = abs(mean_c - mean_r) / mean_r
    eepf_error = sum(w * abs(c - r) for w, c, r in zip(weights, eepf_c, eepf_r))
    rate_errors = {
        key: (abs(rates_c[key] - val) / val if val > 0.0
              else abs(rates_c[key] - val))
        for key, val in rates_r.items()
    }
    failures = []
    if mean_error > thresholds["mean_energy_relative"]:
        failures.append("mean_energy")
    if eepf_error > thresholds["eepf_weighted_l1"]:
        failures.append("eepf")
    for key, error in rate_errors.items():
        bound = thresholds["rate_relative"] if rates_r[key] > 0.0 else thresholds["zero_rate_absolute_m3_per_s"]
        if error > bound:
            failures.append("rate:" + key)

    transport_errors = {}
    if compare_transport:
        for key in sorted(transport_keys):
            error = abs(cand_transport[key] - ref_transport[key]) / ref_transport[key]
            transport_errors[key] = error
            if error > thresholds["transport_relative"]:
                failures.append("transport:" + key)

    # Mere SHA256 matching proves file identity, NOT that someone faithfully
    # transcribed the raw BOLSIG+ output into canonical cell-average EEPF
    # and its reaction/transport coefficients. Until a tested independent
    # native-output converter exists, never issue a scientific NUMERIC_PASS.
    synthetic = source["database"] == "AUTHOR-SYNTHETIC"
    decision = ("BOLSIG_REFERENCE_SELFTEST_" + ("PASS" if not failures else "FAIL")
                if synthetic else
                "BOLSIG_REFERENCE_UNVERIFIED_" +
                ("MATCH" if not failures else "MISMATCH"))
    return {
        "decision": decision,
        "scientific_acceptance": ("SELFTEST_ONLY" if synthetic else
                                  "HOLD_UNVERIFIED_RAW_TO_CANONICAL_CONVERSION"),
        "raw_to_canonical_audit_performed": False,
        "failures": failures,
        "mean_energy_relative_error": mean_error,
        "eepf_weighted_l1_error": eepf_error,
        "rate_errors": rate_errors,
        "transport_relative_errors": transport_errors,
        "collision_file_sha256": source["sha256"],
        "reference_file_sha256": reference["sha256"],
        "candidate_file_sha256": candidate["sha256"],
        "independent_raw_reference_sha256": reference["raw_export_sha256"],
        "reference_version": reference["version"],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--case", required=True, type=Path)
    args = p.parse_args()
    try:
        result = compare_case(args.case)
    except ReferenceContractError as exc:
        print("BOLSIG_REFERENCE_PREFLIGHT_HOLD: " + str(exc))
        return 2
    print(json.dumps(result, sort_keys=True))
    return (2 if result["scientific_acceptance"].startswith("HOLD_") else
            0 if result["decision"].endswith("_PASS") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
