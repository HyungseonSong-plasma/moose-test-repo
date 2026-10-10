#!/usr/bin/env python3
"""Apply the one-sided FEM energy BC to the pinned practical cover pilot."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = "9055b1fa55c8e17206ec5ab2304ecbd47fd15603b51c91cb7b118ee75752a2ed"
TARGET_SHA256 = "140c74f511b67157793a0ba392a8be4c3235e44a834049d6a74a721c2b340d93"

OLD = """  [electron_energy_cover]\n    type = PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = plasma_cover\n  []"""
NEW = """  [electron_energy_cover]\n    type = PhysicsFEMLogMolarElectronEnergyDielectricBC\n    variable = log_energy\n    log_electron_density = log_ne\n    boundary = plasma_cover\n  []"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    final = text.replace(OLD, NEW, 1).encode("utf-8")

    target_digest = digest(final)
    if target_digest != TARGET_SHA256:
        raise RuntimeError(
            f"final pilot SHA256 mismatch: {target_digest} != {TARGET_SHA256}"
        )

    args.input.write_bytes(final)
    print(
        "BASELINE_COVER_PILOT_FINALIZE_PASS "
        f"source_sha256={SOURCE_SHA256} target_sha256={TARGET_SHA256}"
    )


if __name__ == "__main__":
    main()
