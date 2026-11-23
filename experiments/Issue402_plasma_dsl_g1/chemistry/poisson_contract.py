"""S6 New-only Poisson JSON G1 validation; no MOOSE objects are created here.

The static contract deliberately matches the native 8-block/11+3 boundaries.
Runtime ownership and numerical equivalence remain separate G2-G6 gates.
"""
from __future__ import annotations

import json
import math

BLOCK_EPS = {
    "plasma": 1.0,
    "cover": 3.6,
    "wafer": 12.5,
    "focus_ring": 8.0,
    "vacuum": 1.0,
    "coil1": 1.0,
    "coil2": 1.0,
    "coil3": 1.0,
}
GROUND = (
    "inlet", "outlet", "plasma_electrode", "plasma_metal", "plasma_right",
    "cover_outer_right", "wafer_electrode", "focus_ring_ground",
    "vacuum_outer_ground", "cover_coil_ground", "vacuum_coil_ground",
)
SURFACE = {
    "plasma_cover": "sigma_s",
    "plasma_wafer": "sigma_wafer",
    "plasma_focus_ring": "sigma_focus_ring",
}
ROOT_KEYS = {
    "species", "equations", "reactions", "ion_surface_current",
    "drift_diffusion_boundaries", "poisson",
}


class PoissonContractError(ValueError):
    """Reject malformed or physically different S6 Poisson declarations."""


def _object_without_duplicate_keys(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise PoissonContractError("POISSON_JSON_DUPLICATE_KEY:" + key)
        output[key] = value
    return output


def parse_strict_json(payload: bytes | str):
    """Reject repeated keys and JSON NaN/Infinity before Python dictionaries hide them."""
    def _nonfinite(token):
        raise PoissonContractError("POISSON_JSON_NONFINITE:" + token)

    try:
        return json.loads(
            payload, object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PoissonContractError("POISSON_JSON_SYNTAX_INVALID") from exc


def validate_poisson(root: dict) -> None:
    """Validate a single unified New-only JSON; intentionally no G4 activation."""
    if not isinstance(root, dict) or set(root) != ROOT_KEYS:
        raise PoissonContractError("POISSON_ROOT_KEYS_INVALID")
    if not isinstance(root["species"], dict) or not isinstance(root["reactions"], list):
        raise PoissonContractError("POISSON_ROOT_CHEMISTRY_INVALID")
    payload = root["poisson"]
    if not isinstance(payload, dict) or set(payload) != {
        "relative_permittivity", "boundaries",
    }:
        raise PoissonContractError("POISSON_FIELDS_INVALID")
    eps = payload["relative_permittivity"]
    if not isinstance(eps, dict) or set(eps) != set(BLOCK_EPS):
        raise PoissonContractError("POISSON_EPS_BLOCKS_INVALID")
    for block, expected in BLOCK_EPS.items():
        actual = eps[block]
        if (type(actual) not in (int, float) or not math.isfinite(actual)
                or actual <= 0 or actual != expected):
            raise PoissonContractError("POISSON_EPS_VALUE_INVALID:" + block)
    boundary = payload["boundaries"]
    if not isinstance(boundary, dict) or set(boundary) != {
        "ground", "surface_charge",
    }:
        raise PoissonContractError("POISSON_BOUNDARY_FIELDS_INVALID")
    ground = boundary["ground"]
    if (not isinstance(ground, list) or
            any(not isinstance(b, str) for b in ground) or
            len(ground) != len(GROUND) or
            len(set(ground)) != len(GROUND) or set(ground) != set(GROUND)):
        raise PoissonContractError("POISSON_GROUND_BOUNDARIES_INVALID")
    surface = boundary["surface_charge"]
    if not isinstance(surface, dict) or surface != SURFACE:
        raise PoissonContractError("POISSON_SURFACE_CHARGE_INVALID")
    charges = {name: entry.get("charge_number")
               for name, entry in root["species"].items()
               if isinstance(entry, dict)}
    if {name: charges.get(name) for name in ("e", "O2p", "Om", "Op")} != {
        "e": -1, "O2p": 1, "Om": -1, "Op": 1,
    }:
        raise PoissonContractError("POISSON_CHARGED_SPECIES_SIGNS_INVALID")


__all__ = [
    "BLOCK_EPS", "GROUND", "SURFACE", "ROOT_KEYS", "PoissonContractError",
    "parse_strict_json", "validate_poisson",
]
