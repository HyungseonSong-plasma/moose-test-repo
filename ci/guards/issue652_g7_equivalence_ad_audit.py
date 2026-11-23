#!/usr/bin/env python3
"""#652 G7: Old/New P3 descriptive readback + algebraic AD charge sensitivity.

Input receipts are downloaded from immutable GitHub Actions run IDs:
  old 44426913036: approved Public D100 100us *RF coupled*, raw Exodus not retained;
  new 45216929109: G6-B New-only Poisson 100us, original CSV+Exodus retained.
These runs do NOT share every full input, so they cannot prove Old/New Poisson parity.
Also checks source G3 charge-expression identity and log-density derivatives against
central finite differences. This is NOT a PETSc assembled Jacobian verification.
Never silently upgrades science, equivalence, conserved quantities, or merge status.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

OLD_SOURCE = "9457191f4c0693ae886586edd961965867ccd5c0"
NEW_SOURCE = "26e84a4a33cf93d9e278a4f0b2d78c53cae2d6ce"
OLD_RUN = 44426913036
NEW_RUN = 45216929109
LOOKUP_SHA = "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
CASES = ("417", "941")
E_OVER_EPS = 1.8095128179727827e-08
E_CHARGE = 1.602176634e-19


class AuditHold(ValueError):
    pass


def unique_file(folder: Path, filename: str) -> Path:
    candidates = sorted(folder.rglob(filename))
    if len(candidates) != 1 or candidates[0].is_symlink() or not candidates[0].is_file():
        raise AuditHold("EVIDENCE_FILE_NOT_UNIQUE_OR_MISSING:" + filename)
    return candidates[0]


def read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditHold("EVIDENCE_NOT_READABLE_JSON") from exc
    if not isinstance(value, dict):
        raise AuditHold("EVIDENCE_NOT_OBJECT")
    return value


def finite_number(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditHold("EVIDENCE_NOT_NUMBER:" + key)
    result = float(value)
    if not math.isfinite(result):
        raise AuditHold("EVIDENCE_NOT_FINITE:" + key)
    return result


def old_observables(root: dict, case: str) -> dict:
    if (
        root.get("schema") != "issue673.p3p4.public_d_original100_100us.v1"
        or root.get("source_HEAD") != OLD_SOURCE
        or root.get("rf_enabled") is not True
        or root.get("target_physical_steps") != 460
        or root.get("target_final_time_s") != 1e-4
        or root.get("RF_FULL_S6_CASES_PASS") is not True
        or root.get("P3_P4_science") != "SCIENCE_HOLD"
        or set(root.get("cases", {})) != {case}
    ):
        raise AuditHold("OLD_EXACT_SOURCE_P3P4_PROVENANCE_MISSING:" + case)
    entry = root["cases"][case]
    if (
        entry.get("full_100us_rc") != 0
        or entry.get("P3_timegrid_pass") is not True
        or entry.get("P4_diagnostic_only") is not True
        or entry.get("P4_series_invariant_pass") is not True
        or entry.get("full_S6_original_11_layers_unchanged") is not True
        or entry.get("seven_transfers_numeric_observed") is not True
        or entry.get("P3_temporal_summary", {}).get("rows") != 461
        or entry.get("P3_temporal_summary", {}).get("physical_steps") != 460
    ):
        raise AuditHold("OLD_NATIVE_FULL100_UNVERIFIED:" + case)
    candidates = [
        row.get("values", {}) for row in entry.get("csv_observed", [])
        if isinstance(row, dict) and "P_abs_maxwell_t6" in row.get("values", {})
    ]
    if len(candidates) != 1:
        raise AuditHold("OLD_P4_PARENT_FINAL_CSV_NOT_UNIQUE:" + case)
    parent = candidates[0]
    if abs(finite_number(parent.get("time"), "old_time") - 1e-4) > 1e-9:
        raise AuditHold("OLD_P4_NOT_AT_FINAL_TIME")
    return {
        "ne_min_m_minus3": finite_number(parent.get("ne_min"), "old_ne_min"),
        "ne_max_m_minus3": finite_number(parent.get("ne_max"), "old_ne_max"),
        "rf_absorbed_power_W": finite_number(parent.get("P_abs_maxwell_t6"), "old_rf"),
        "poisson_charge_C": finite_number(
            entry.get("d8_coupled_postprocessors", {}).get("rf_d8_poisson_charge_C"),
            "old_poisson_charge"),
        "p4_status": "DIAGNOSTIC_ONLY", "rf_coupled": True,
    }


def new_observables(data: dict, case: str) -> dict:
    if (
        data.get("schema") != "issue652.g6b.native_100us_case.v1"
        or data.get("source_sha") != NEW_SOURCE
        or data.get("case_id") != case
        or data.get("original_publicd_lookup_sha256") != LOOKUP_SHA
        or data.get("P3_100us") != "PASS_NATIVE_FINITE_461_FRAMES"
        or data.get("P4") != "NOT_RUN"
        or data.get("science") != "SCIENCE_HOLD"
        or data.get("original_s6_input_unchanged") is not True
        or data.get("raw_protected_rates_in_artifact") is not False
        or data.get("time_series", {}).get("time_points") != 461
        or data.get("time_series", {}).get("intervals") != 460
        or data.get("original_time_grid", {}).get("end_time_seconds") != 1e-4
    ):
        raise AuditHold("NEW_EXACT_SOURCE_FULL100_UNVERIFIED:" + case)
    series = data["time_series"]
    if abs(finite_number(series.get("t_end_seconds"), "new_final_time") - 1e-4) > 1e-12:
        raise AuditHold("NEW_P3_NOT_AT_FINAL_TIME")
    extrema = series.get("extrema", {})
    return {
        "ne_min_m_minus3": finite_number(
            extrema.get("ne_min", {}).get("last"), "new_ne_min"),
        "ne_max_m_minus3": finite_number(
            extrema.get("ne_max", {}).get("last"), "new_ne_max"),
        "charge_integral": finite_number(
            extrema.get("charge_integral", {}).get("last"), "new_charge_integral"),
        "p4_status": "NOT_RUN_IN_G6B", "rf_coupled": "NOT_DEMONSTRATED",
    }


def relative_delta(old: float, new: float) -> dict:
    return {
        "old": old, "new": new,
        "new_minus_old": new - old,
        "relative_to_old": (new - old) / abs(old) if old != 0 else None,
    }


def verify_charge_source(cpp_source: str) -> dict:
    required = [
        '"ADParsedFunctorMaterial"',
        'add_charge_functor("charge_number_density",',
        '"ni+nop-ne-nm"',
        '"O2p_number_density", "Op_number_density"',
        '"n_e_physical", "Om_number_density"',
        'add_charge_functor("charge_density_C_m3",',
        '"1.602176634e-19*nq"',
        'add_charge_functor("poisson_source",',
        '"1.8095128179727827e-08*nq"',
    ]
    if not all(cpp_source.count(token) == 1 for token in required):
        raise AuditHold("G3_CHARGE_SOURCE_ALGEBRA_SOURCE_DRIFT")
    # Independent central-difference checks on log-number-density states
    # (not a compiled ADReal, not an assembled PETSc Jacobian).
    x = [math.log(n) for n in (8e16, 7e16, 6e16, 5e16)]
    signs = (1., 1., -1., -1.)
    def charge(state: list[float]) -> float:
        return E_OVER_EPS * sum(s * math.exp(t) for s, t in zip(signs, state))
    h = 1e-5
    residuals = []
    for i in range(4):
        u, d = list(x), list(x)
        u[i] += h
        d[i] -= h
        estimate = (charge(u) - charge(d)) / (2*h)
        analytic = E_OVER_EPS * signs[i] * math.exp(x[i])
        relative = abs(estimate - analytic) / max(abs(analytic), 1.)
        if relative >= 3e-9:
            raise AuditHold("G3_CHARGE_LOG_STATE_DERIVATIVE_DRIFT")
        residuals.append({
            "state": ("log_O2p", "log_Op", "log_e", "log_Om")[i],
            "sign": int(signs[i]),
            "analytic": analytic,
            "numerical": estimate,
            "relative_error": relative,
        })
    # This cannot be reported as "AD Jacobian PASS": that requires an
    # assembled-vs-FD test of the actual PhysicsApp discretization.
    return {
        "charge_source_expression": "e_over_eps0*(n_O2p+n_Op-n_e-n_Om)",
        "charge_density_signs": [1, 1, -1, -1],
        "unit_coefficient": E_OVER_EPS,
        "algebraic_log_density_derivatives": residuals,
        "algebraic_status": "PASS_INDEPENDENT_FORMULA_FD",
        "native_adreal_derivative": "UNVERIFIED",
        "petsc_assembled_jacobian": "NOT_RUN",
    }


def analyze(*, old417: Path, old941: Path, new417: Path, new941: Path,
            cpp: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise AuditHold("OUTPUT_ALREADY_EXISTS")
    old = {"417": old_observables(read_object(unique_file(old417, "rf_full_s6_receipt.json")), "417"),
           "941": old_observables(read_object(unique_file(old941, "rf_full_s6_receipt.json")), "941")}
    new = {"417": new_observables(read_object(unique_file(new417, "g6b-full100-417.json")), "417"),
           "941": new_observables(read_object(unique_file(new941, "g6b-full100-941.json")), "941")}
    charge = verify_charge_source(cpp.read_text(encoding="utf-8"))
    cases = {}
    for case in CASES:
        cases[case] = {
            "old_run": OLD_RUN, "new_run": NEW_RUN,
            "old": old[case], "new": new[case],
            "descriptive_differences": {
                key: relative_delta(old[case][key], new[case][key])
                for key in ("ne_min_m_minus3", "ne_max_m_minus3")
            },
            "poisson_charge_comparison": "HOLD_INCOMPATIBLE_DIAGNOSTIC_DEFINITIONS",
            "same_input_status": "HOLD_RF_AND_POISSON_OWNER_DIFFERENT",
            "physical_equivalence": "UNPROVEN",
        }
    report = {
        "schema": "issue652.g7.oldnew_ad_candidate.v1",
        "old_source": OLD_SOURCE, "new_source": NEW_SOURCE,
        "old_run": OLD_RUN, "new_run": NEW_RUN,
        "shared_public_d_lookup_sha256": LOOKUP_SHA,
        "source_input_identity": "HOLD_NOT_ALL_DYNAMICAL_COUPLINGS_IDENTICAL",
        "data_scope": "100US_FINAL_SCALAR_DIAGNOSTIC_ONLY",
        "jacobian": charge, "cases": cases,
        "old_new_poisson_semantic_parity": "HOLD",
        "full_time_charge_energy_conservation": "UNVERIFIED",
        "checkpoint_restart": "HOLD",
        "science": "SCIENCE_HOLD",
        "main_merge": "NOT_AUTHORIZED",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    compact = {
        case: {
            "ne_min_relative_delta": cases[case]["descriptive_differences"]["ne_min_m_minus3"]["relative_to_old"],
            "ne_max_relative_delta": cases[case]["descriptive_differences"]["ne_max_m_minus3"]["relative_to_old"],
        } for case in CASES
    }
    print("G7_OLDNEW_DESCRIPTIVE_JSON=" + json.dumps(compact, sort_keys=True), flush=True)
    print("G7_FORMULA_FD_PASS_NATIVE_JACOBIAN_HOLD SCIENCE_HOLD", flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("old417", "old941", "new417", "new941", "cpp", "output"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    try:
        analyze(**vars(args))
    except (AuditHold, OSError, KeyError, TypeError, ValueError) as exc:
        print("G7_AUDIT_HOLD " + type(exc).__name__ + " " + str(exc)[:180], flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
