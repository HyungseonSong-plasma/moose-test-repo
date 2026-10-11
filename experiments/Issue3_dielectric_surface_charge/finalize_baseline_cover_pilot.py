#!/usr/bin/env python3
"""Finalize the pinned practical cover pilot without changing its physics."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = "9055b1fa55c8e17206ec5ab2304ecbd47fd15603b51c91cb7b118ee75752a2ed"
ENERGY_TARGET_SHA256 = "140c74f511b67157793a0ba392a8be4c3235e44a834049d6a74a721c2b340d93"

OLD = """  [electron_energy_cover]\n    type = PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = plasma_cover\n  []"""
NEW = """  [electron_energy_cover]\n    type = PhysicsFEMLogMolarElectronEnergyDielectricBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = plasma_cover\n  []"""

PLASMA_SIDE_FUNCTOR_POSTPROCESSORS = (
    "cover_net_surface_current",
    "cover_electron_primary_flux",
    "cover_O2p_flux",
    "cover_Om_flux",
    "cover_Op_flux",
)
DIAGNOSTIC_OPTION = "    restrict_to_functors_domain = true"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def restrict_functor_diagnostic(text: str, name: str) -> str:
    """Keep one internal-interface functor integral on its plasma-side domain only."""
    header = f"  [{name}]\n"
    if text.count(header) != 1:
        raise RuntimeError(f"expected exactly one {name} postprocessor")

    start = text.index(header)
    end = text.find("\n  []", start)
    if end < 0:
        raise RuntimeError(f"unterminated {name} postprocessor")

    block = text[start:end]
    if "restrict_to_functors_domain" in block:
        raise RuntimeError(f"{name} diagnostic scope already configured")

    return text[:end] + "\n" + DIAGNOSTIC_OPTION + text[end:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    original = args.input.read_bytes()
    source_digest = digest(original)
    if source_digest != SOURCE_SHA256:
        raise RuntimeError(
            f"unexpected source pilot SHA256: {source_digest} != {SOURCE_SHA256}"
        )

    text = original.decode("utf-8")
    if text.count(OLD) != 1:
        raise RuntimeError("expected exactly one electron_energy_cover block to finalize")

    energy_final = text.replace(OLD, NEW, 1).encode("utf-8")
    energy_target_digest = digest(energy_final)
    if energy_target_digest != ENERGY_TARGET_SHA256:
        raise RuntimeError(
            "energy-final pilot SHA256 mismatch: "
            f"{energy_target_digest} != {ENERGY_TARGET_SHA256}"
        )

    final_text = energy_final.decode("utf-8")
    for name in PLASMA_SIDE_FUNCTOR_POSTPROCESSORS:
        final_text = restrict_functor_diagnostic(final_text, name)

    final = final_text.encode("utf-8")
    final_digest = digest(final)

    args.input.write_bytes(final)
    print(
        "BASELINE_COVER_PILOT_FINALIZE_PASS "
        f"source_sha256={SOURCE_SHA256} "
        f"energy_target_sha256={ENERGY_TARGET_SHA256} "
        f"scoped_functor_postprocessors={len(PLASMA_SIDE_FUNCTOR_POSTPROCESSORS)} "
        f"final_sha256={final_digest}"
    )


if __name__ == "__main__":
    main()
