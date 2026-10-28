"""Extract independently auditable scalar reference from native BOLSIG+ output.

Never relabel a native scalar self-consistency check as candidate-solver parity.
Does NOT decode EEPF, modify/extract/re-upload cross-section tables, or run BOLSIG+.
Inputs are user-local and may be subject to third-party source licensing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


class NativeBolsigError(ValueError):
    pass


PROCESS = re.compile(
    r"^C(\d+)\s+(\S+)\s+"
    r"(Effective \(momentum\)|Excitation|Ionization|Elastic|Attachment)"
    r"\s*(?:(\d+(?:\.\d+)?)\s+eV)?"
    r"\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[+-]?\d+)?)\s*$"
)
FLOAT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[+-]?\d+)?"
SCALAR = re.compile(r"^(.+?)\s{2,}(" + FLOAT + r")\s*$")
REQUIRED = (
    "Electric field / N (Td)", "Gas temperature (K)",
    "Gas particle density (1/m3)", "Growth model", "# of grid points",
    "Mean energy (eV)", "Mobility *N (1/m/V/s)",
    "Diffusion coefficient *N (1/m/s)",
    "Energy mobility *N (1/m/V/s)",
    "Energy diffusion coef. *N (1/m/s)",
    "Total ionization freq. /N (m3/s)",
    "Total attachment freq. /N (m3/s)",
    "Townsend ioniz. coef. alpha/N (m2)",
    "Townsend attach. coef. eta/N (m2)",
    "Power /N (eV m3/s)",
    "Elastic power loss /N (eV m3/s)",
    "Inelastic power loss /N (eV m3/s)",
    "Growth power /N (eV m3/s)",
    "Maximum energy",
)
SAVED_OPTIONS = (
    "conditions", "transport", "rates", "reverse_rates",
    "energy_losses", "distribution", "skip_failed", "cross_sections",
)


def _check_positive_float(value: float, label: str, *, allow_zero: bool = True) -> None:
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        raise NativeBolsigError(f"invalid {label} value")


def _extract_options(raw: str, output_basename: str) -> dict[str, int]:
    lines = raw.splitlines()
    for i, original in enumerate(lines):
        if original.strip() != "SAVERESULTS":
            continue
        tokens = []
        for line in lines[i + 1:]:
            stripped = line.split("/", 1)[0].strip()
            if not stripped:
                continue
            if stripped == "SAVERESULTS" or stripped == "END":
                break
            tokens.append(stripped)
            if len(tokens) == 10:
                break
        if len(tokens) != 10 or Path(tokens[0]).name != output_basename:
            continue
        try:
            fmt, *values = (int(x) for x in tokens[1:])
        except ValueError as exc:
            raise NativeBolsigError("malformed SAVERESULTS control fields") from exc
        if fmt not in (1, 2, 3, 4, 5, 6) or len(values) != 8 or any(x not in (0, 1) for x in values):
            raise NativeBolsigError("unsupported SAVERESULTS format or boolean controls")
        return {"format": fmt, **dict(zip(SAVED_OPTIONS, values))}
    raise NativeBolsigError(f"SAVERESULTS for {output_basename} not found in input script")


def parse_native_scalar_reference(
    output: Path,
    source_input: Path | None = None,
) -> dict[str, Any]:
    raw = output.read_bytes()
    if not raw:
        raise NativeBolsigError("empty native BOLSIG+ output")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise NativeBolsigError("native output is not UTF-8 text") from exc
    if not lines[0].startswith("BOLSIG+ version:"):
        raise NativeBolsigError("not a native BOLSIG+ run-by-run file")
    version = lines[0].split(":", 1)[1].strip()
    indices = [i for i, line in enumerate(lines) if re.fullmatch(r"R\d+\s*", line)]
    if len(indices) != 1 or not re.fullmatch(r"R1\s*", lines[indices[0]]):
        raise NativeBolsigError("expected exactly one native R1 run")
    block = lines[indices[0] + 1:]
    if "Rate coefficients (m3/s)" not in block:
        raise NativeBolsigError("native run has no process rate block")
    split = block.index("Rate coefficients (m3/s)")
    scalars = {}
    for line in block[:split]:
        match = SCALAR.fullmatch(line.strip())
        if match:
            value = float(match.group(2))
            if math.isfinite(value):
                scalars[match.group(1).strip()] = value
    for key in REQUIRED:
        if key not in scalars:
            raise NativeBolsigError(f"missing native scalar: {key}")
    for key in ("Mean energy (eV)", "Mobility *N (1/m/V/s)",
                "Diffusion coefficient *N (1/m/s)",
                "Energy mobility *N (1/m/V/s)",
                "Energy diffusion coef. *N (1/m/s)"):
        _check_positive_float(scalars[key], key, allow_zero=False)
    fractions = {key.replace("Mole fraction ", ""): val
                 for key, val in scalars.items() if key.startswith("Mole fraction ")}
    if not fractions or abs(sum(fractions.values()) - 1.0) > 1e-6:
        raise NativeBolsigError("native species fractions missing or nonunit")
    for gas, val in fractions.items():
        _check_positive_float(val, f"mole fraction {gas}")

    rates = []
    for line in block[split + 1:]:
        m = PROCESS.fullmatch(line.strip())
        if m:
            rates.append({
                "id": "C" + m.group(1), "gas": m.group(2), "kind": m.group(3),
                "threshold_eV": float(m.group(4)) if m.group(4) else None,
                "rate_m3_per_s": float(m.group(5)),
            })
    if not rates:
        raise NativeBolsigError("native process rates missing")
    ids = [x["id"] for x in rates]
    if len(ids) != len(set(ids)):
        raise NativeBolsigError("duplicate native process IDs")
    if any(r["gas"] not in fractions for r in rates):
        raise NativeBolsigError("rate target outside gas mixture")
    for r in rates:
        _check_positive_float(r["rate_m3_per_s"], f'{r["id"]} rate')

    counts = {gas: {
        kind: sum(x["gas"] == gas and x["kind"] == kind for x in rates)
        for kind in ("Elastic", "Effective (momentum)", "Excitation",
                     "Ionization", "Attachment")
        if any(x["gas"] == gas and x["kind"] == kind for x in rates)
    } for gas in fractions}
    weighted_ion = sum(fractions[x["gas"]] * x["rate_m3_per_s"]
                       for x in rates if x["kind"] == "Ionization")
    weighted_att = sum(fractions[x["gas"]] * x["rate_m3_per_s"]
                       for x in rates if x["kind"] == "Attachment")
    energy_threshold = sum(fractions[x["gas"]] * x["rate_m3_per_s"] * x["threshold_eV"]
                           for x in rates if x["kind"] in ("Excitation", "Ionization"))
    field = scalars["Electric field / N (Td)"] * 1e-21
    mobility = scalars["Mobility *N (1/m/V/s)"]
    drift = mobility * field
    input_power = mobility * field * field
    output_power = scalars["Power /N (eV m3/s)"]
    ion_report = scalars["Total ionization freq. /N (m3/s)"]
    att_report = scalars["Total attachment freq. /N (m3/s)"]
    if not (drift > 0 and ion_report > 0 and att_report >= 0 and output_power > 0):
        raise NativeBolsigError("native scalar drift, ionization or power invalid")
    def relative(computed: float, reference: float) -> float:
        return abs(computed - reference) / max(abs(reference), 1e-100)

    residuals = {
        "ionization_weighted_rate_relative": relative(weighted_ion, ion_report),
        "attachment_weighted_rate_relative": relative(weighted_att, att_report),
        "field_power_from_mobility_relative": relative(input_power, output_power),
        "townsend_ionization_relative": relative(
            weighted_ion / drift, scalars["Townsend ioniz. coef. alpha/N (m2)"]),
        "townsend_attachment_relative": relative(
            weighted_att / drift, scalars["Townsend attach. coef. eta/N (m2)"]),
        "power_loss_budget_relative": relative(
            scalars["Elastic power loss /N (eV m3/s)"] +
            scalars["Inelastic power loss /N (eV m3/s)"] +
            scalars["Growth power /N (eV m3/s)"], output_power),
    }
    # Not a hard physical equality: BOLSIG+ includes thermal reverse
    # transitions and its own inelastic power definitions.
    threshold_loss_difference = relative(
        energy_threshold, scalars["Inelastic power loss /N (eV m3/s)"])
    consistency_pass = all(v < 1e-3 for v in residuals.values())

    input_options = None
    if source_input:
        inp = source_input.read_bytes()
        input_options = _extract_options(inp.decode("utf-8"), output.name)
    cross_section_blocks = sum(bool(re.fullmatch(r"C\d+ Input cross section", ln.strip()))
                               for ln in lines[:indices[0]])
    if cross_section_blocks and cross_section_blocks != len(rates):
        raise NativeBolsigError("native cross-section/rate inventory mismatch")
    return {
        "status": ("NATIVE_REFERENCE_SCALAR_SELFCONSISTENCY_PASS" if consistency_pass else
                   "NATIVE_REFERENCE_SCALAR_SELFCONSISTENCY_FAIL"),
        "scientific_acceptance": "HOLD_CANDIDATE_AND_NATIVE_EEPF_PARITY_NOT_TESTED",
        "bolsig_version": version,
        "native_output_sha256": hashlib.sha256(raw).hexdigest(),
        "input_script_sha256": (
            hashlib.sha256(source_input.read_bytes()).hexdigest()
            if source_input else None),
        "conditions": {
            "E_over_N_Td": scalars["Electric field / N (Td)"],
            "gas_temperature_K": scalars["Gas temperature (K)"],
            "gas_number_density_m_minus_3": scalars["Gas particle density (1/m3)"],
            "growth_model_code": scalars["Growth model"],
            "energy_cells": int(scalars["# of grid points"]),
            "actual_maximum_energy_eV": scalars["Maximum energy"],
            "mixture": fractions,
        },
        "metrics": {
            "mean_energy_eV": scalars["Mean energy (eV)"],
            "mobility_times_N": mobility,
            "diffusion_times_N": scalars["Diffusion coefficient *N (1/m/s)"],
            "energy_mobility_times_N": scalars["Energy mobility *N (1/m/V/s)"],
            "energy_diffusion_times_N": scalars["Energy diffusion coef. *N (1/m/s)"],
            "ionization_reduced_m3_per_s": ion_report,
            "attachment_reduced_m3_per_s": att_report,
            "inelastic_power_loss_reduced_eV_m3_per_s":
                scalars["Inelastic power loss /N (eV m3/s)"],
            "power_input_reduced_eV_m3_per_s": output_power,
        },
        "number_of_collision_processes": len(rates),
        "number_of_embedded_cross_section_blocks": cross_section_blocks,
        "process_census": counts,
        "weighted_ionization_by_gas_m3_per_s": {
            gas: sum(fractions[gas] * r["rate_m3_per_s"] for r in rates
                     if r["gas"] == gas and r["kind"] == "Ionization")
            for gas in fractions
        },
        "identity_relative_errors": residuals,
        "threshold_rate_sum_vs_inelastic_power_relative_difference":
            threshold_loss_difference,
        "input_save_options": input_options,
        "eepf_in_native_result": (
            None if input_options is None
            else bool(input_options["distribution"])),
        "comparison_blockers": [
            "No self-consistent candidate C++ solution on all native collision processes",
            "EFFECTIVE Ar/He/O2 is not an ELASTIC-only momentum-transfer input",
            "O2 attachment includes density-normalized three-body chemistry",
            "Native file contains no EEPF when SAVERESULTS distribution=0",
        ],
    }



def compare_native_collision_ledger(
    native_output: Path,
    collision_source: Path,
) -> dict[str, Any]:
    """Cross-check the *whole* raw collision census against a native BOLSIG+ run.

    This checks source-process provenance, not EEPF/operator equivalence.
    Only counts and SHA-256 are emitted; no LXCat cross-section rows are
    copied into an artifact or a repository.
    """
    try:
        from .boltzmann_collision_coverage_audit import (
            CollisionAuditError, audit_local_collision_file,
        )
    except ImportError:
        from boltzmann_collision_coverage_audit import (
            CollisionAuditError, audit_local_collision_file,
        )

    native = parse_native_scalar_reference(native_output)
    fractions = native["conditions"]["mixture"]
    try:
        source = audit_local_collision_file(collision_source, tuple(fractions))
    except (OSError, UnicodeError, CollisionAuditError) as exc:
        raise NativeBolsigError("invalid independently supplied collision source") from exc

    type_map = {
        "Elastic": "ELASTIC",
        "Effective (momentum)": "EFFECTIVE",
        "Excitation": "EXCITATION",
        "Ionization": "IONIZATION",
        "Attachment": "ATTACHMENT",
    }
    native_census = {
        gas: {type_map[kind]: count for kind, count in kinds.items()}
        for gas, kinds in native["process_census"].items()
    }
    source_census = {
        gas: {("EFFECTIVE" if k == "MOMENTUM" else k): v
              for k, v in kinds.items()}
        for gas, kinds in source["process_counts"].items()
    }
    missing: dict[str, dict[str, int]] = {}
    excess: dict[str, dict[str, int]] = {}
    for gas in fractions:
        a = native_census.get(gas, {})
        b = source_census.get(gas, {})
        for kind in sorted(set(a) | set(b)):
            gap = a.get(kind, 0) - b.get(kind, 0)
            if gap > 0:
                missing.setdefault(gas, {})[kind] = gap
            elif gap < 0:
                excess.setdefault(gas, {})[kind] = -gap

    count_equal = native["number_of_collision_processes"] == source["total_processes"]
    census_equal = count_equal and not missing and not excess
    # The census is necessary but not sufficient for matched collision
    # physics: threshold/tabulation, units, target states, superelastic
    # populations, third-body attachment and growth must still be audited.
    status = (
        "HOLD_NATIVE_REFERENCE_SELFCONSISTENCY"
        if not native["status"].endswith("_PASS") else
        "HOLD_SOURCE_NATIVE_PROCESS_CENSUS_MISMATCH"
        if not census_equal else
        "PROCESS_CENSUS_MATCH_PHYSICAL_PARITY_NOT_ESTABLISHED"
    )
    return {
        "status": status,
        "scientific_acceptance": "HOLD_COMPLETE_COLLISION_OPERATOR_AND_EEPF",
        "native_bolsig_version": native["bolsig_version"],
        "native_output_sha256": native["native_output_sha256"],
        "collision_source_sha256": source["source_sha256"],
        "native_process_count": native["number_of_collision_processes"],
        "source_process_count": source["total_processes"],
        "native_process_census": native_census,
        "source_process_census": source_census,
        "missing_source_processes_by_type": missing,
        "extra_source_processes_by_type": excess,
        "source_model_gaps": source["model_gaps"],
        "limitations": [
            "Does not establish threshold or cross-section table equivalence",
            "Does not establish energy-grid/growth/three-body/e-e model parity",
            "Does not establish numerical EEPF, rate or transport agreement",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-output", type=Path, required=True)
    parser.add_argument("--input-script", type=Path)
    parser.add_argument("--cross-sections", type=Path)
    args = parser.parse_args()
    try:
        report = parse_native_scalar_reference(args.native_output, args.input_script)
        if args.cross_sections:
            report["external_collision_ledger"] = compare_native_collision_ledger(
                args.native_output, args.cross_sections)
    except (OSError, UnicodeError, NativeBolsigError) as exc:
        print("BOLSIG_NATIVE_REFERENCE_PREFLIGHT_HOLD:", exc)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"].endswith("_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
