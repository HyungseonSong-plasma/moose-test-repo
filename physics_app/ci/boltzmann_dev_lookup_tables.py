"""DEV-ONLY bridge: candidate EEPF transport JSON -> MOOSE-compatible lookup rows.

This DOES NOT install, load, approve or mutate any PhysicsApp production
material. It does not certify BOLSIG+ parity; that separate science gate
must be passed before these rows can be promoted to production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


class DevelopmentTableError(ValueError):
    pass


COEFFICIENTS = (
    "mobility_times_N_per_m_V_s",
    "diffusion_times_N_per_m_s",
    "energy_mobility_times_N_per_m_V_s",
    "energy_diffusion_times_N_per_m_s",
)


def _positive(value: Any, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DevelopmentTableError(f"invalid nonnumeric {label}")
    result = float(value)
    if not math.isfinite(result) or (result < 0 if nonnegative else result <= 0):
        raise DevelopmentTableError(f"invalid nonpositive/nonfinite {label}")
    return result


def make_dev_lookup_tables(
    source: Path, inputs: list[Path], output_directory: Path
) -> dict[str, str]:
    if len(inputs) < 2:
        raise DevelopmentTableError("at least two distinct E/N candidate results required")
    raw_bytes = source.read_bytes()
    if not raw_bytes:
        raise DevelopmentTableError("collision source must be nonempty")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    common: dict[str, Any] | None = None
    rows: list[tuple[float, float, float, float, float, float]] = []
    provenance: list[dict[str, Any]] = []
    for candidate in inputs:
        payload = candidate.read_bytes()
        blob_hash = hashlib.sha256(payload).hexdigest()
        try:
            obj = json.loads(payload)
        except (ValueError, UnicodeError) as exc:
            raise DevelopmentTableError("candidate JSON must be valid UTF-8") from exc
        if not isinstance(obj, dict) or obj.get("schema_version") != 1:
            raise DevelopmentTableError("unsupported candidate result schema")
        conditions = obj.get("conditions")
        if not isinstance(conditions, dict) or (
            conditions.get("collision_source_sha256") != digest
        ):
            raise DevelopmentTableError("candidate does not match raw source SHA-256")
        model = conditions.get("model")
        if model not in {
            "elastic_dc_transport_moments",
            "elastic_excitation_superelastic_transport_moments",
        }:
            raise DevelopmentTableError("candidate is not stationary collision transport output")
        mixture = conditions.get("mixture")
        if not isinstance(mixture, dict) or not mixture:
            raise DevelopmentTableError("gas mixture is required")
        if any(not isinstance(k, str) or not k for k in mixture):
            raise DevelopmentTableError("invalid gas species name")
        if abs(sum(_positive(v, "mole fraction") for v in mixture.values()) - 1) > 1e-12:
            raise DevelopmentTableError("gas mole fractions must sum to one")
        gas_temperature = _positive(conditions.get("gas_temperature_K"), "gas temperature")
        e_over_n = _positive(conditions.get("reduced_field_Td"), "E/N", nonnegative=True)
        identity = {"mixture": mixture, "gas_temperature_K": gas_temperature, "model": model}
        if common is None:
            common = identity
        elif identity != common:
            raise DevelopmentTableError("candidate mixture, gas T or collision model changed")

        mean = _positive(obj.get("mean_energy_eV"), "mean energy")
        transport = obj.get("elastic_transport")
        if not isinstance(transport, dict):
            raise DevelopmentTableError("candidate missing four transport moments")
        values = tuple(_positive(transport.get(k), k) for k in COEFFICIENTS)
        tail = _positive(transport.get("tail_ratio"), "tail ratio", nonnegative=True)
        if tail > 1e-3:
            raise DevelopmentTableError("high-energy EEPF tail is unresolved")
        rows.append((mean, *values, e_over_n))
        provenance.append({"candidate": candidate.name, "sha256": blob_hash,
                           "E_over_N_Td": e_over_n, "mean_energy_eV": mean})

    rows.sort()
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise DevelopmentTableError("mean-energy lookup coordinates must be distinct")
    sorted_en = [r[-1] for r in rows]
    if sorted_en != sorted(sorted_en) or len(set(sorted_en)) != len(sorted_en):
        raise DevelopmentTableError("E/N vs mean energy must be strictly monotonic")

    # A normal three-column PhysicsApp particle transport lookup table.
    # Energy transport remains separate; existing production materials
    # still apply a hardcoded 5/3 factor and DO NOT consume the sidecar.
    particle = "".join(f"{m:.17g} {mu:.17g} {diff:.17g}\n"
                       for m, mu, diff, emu, ediff, en in rows)
    energy = "".join(f"{m:.17g} {emu:.17g} {ediff:.17g}\n"
                     for m, mu, diff, emu, ediff, en in rows)
    output_directory.mkdir(parents=True, exist_ok=True)
    p = output_directory / "DEVELOPMENT_ONLY_particle_transport.txt"
    e = output_directory / "DEVELOPMENT_ONLY_energy_transport.txt"
    if p.exists() or e.exists():
        raise DevelopmentTableError("refuse to overwrite existing development lookup rows")
    p.write_text(particle, encoding="utf-8")
    e.write_text(energy, encoding="utf-8")
    hashes = {"particle_sha256": hashlib.sha256(particle.encode()).hexdigest(),
              "energy_sha256": hashlib.sha256(energy.encode()).hexdigest()}
    manifest = {
        "status": "DEV_ONLY_NOT_PHYSICS_VALIDATED",
        "source_sha256": digest,
        "conditions": common,
        "candidate_artifacts": provenance,
        "source_file": source.name,
        "file_hashes": hashes,
        "limits": [
            "No independently captured BOLSIG+ raw reference validated",
            "No production energy-transport material reads sidecar",
            "Actual physics-opt coupling and scientific P2/P3 are absent",
        ],
    }
    (output_directory / "DEVELOPMENT_ONLY_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, action="append", required=True)
    parser.add_argument("--confirm-development-only", action="store_true")
    opts = parser.parse_args()
    if not opts.confirm_development_only:
        parser.error("explicit --confirm-development-only required; no production promotion")
    try:
        print(json.dumps(make_dev_lookup_tables(opts.source, opts.candidate, opts.out),
                         sort_keys=True))
    except (OSError, DevelopmentTableError) as exc:
        print("BOLTZMANN_TABLE_PREFLIGHT_HOLD:", str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
