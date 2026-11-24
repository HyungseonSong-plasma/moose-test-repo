"""Source-bound P0 proof for code4 zero-field smoke-only migration (#713).

The original Git blob is reconstructed byte-for-byte from the new fixture
using only the one approved FV flux-kernel substitution. This does NOT prove
Native equivalence, runtime activation, or science acceptance.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "electron_energy_transport_smoke.i": "b7b3850cb111cce0fed9414e75a7b2d3454d9b4e",
    "electron_energy_lookup_response_smoke.i": "12e775b24d2fb5bdfd46ba375a17d3cebca47991",
}

OLD_BLOCK = """  [energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = mean_en
    potential = phi_zero
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
  []"""
NEW_BLOCK = """  [energy_drift]
    type = FVAdvection
    variable = mean_en
    velocity = '0 0 0'
    advected_interp_method = upwind
  []"""


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def check_fixture(text: str, frozen_sha: str) -> None:
    if text.count(NEW_BLOCK) != 1:
        raise ValueError("C1_EXACT_NEW_BLOCK_REQUIRED")
    if OLD_BLOCK in text:
        raise ValueError("C1_LEGACY_KERNEL_REMAINED")
    if ("[phi_zero]\n    type = ParsedFunction\n    expression = '0*x'") not in text:
        raise ValueError("C1_ZERO_FIELD_ASSERTION_MISSING")
    if text.count("  [energy_drift]") != 1:
        raise ValueError("C1_DUPLICATE_DRIFT_BLOCK")
    original = text.replace(NEW_BLOCK, OLD_BLOCK)
    if git_blob_sha(original.encode("utf-8")) != frozen_sha:
        raise ValueError("C1_UNRELATED_INPUT_MUTATION_OR_DRIFT_SEMANTIC_CHANGE")


class Code4ZeroFieldRewireP0(unittest.TestCase):
    def test_only_approved_kernel_substitution_and_pinned_original_bytes(self) -> None:
        for filename, sha in FROZEN.items():
            with self.subTest(filename=filename):
                text = (ROOT / "physics_app" / "ci" / filename).read_text(encoding="utf-8")
                check_fixture(text, sha)

    def test_negative_mutations_fail_closed(self) -> None:
        text = (ROOT / "physics_app" / "ci" / next(iter(FROZEN))).read_text()
        sha = next(iter(FROZEN.values()))
        mutations = {
            "nonzero_field": text.replace("expression = '0*x'", "expression = '1*x'"),
            "wrong_velocity": text.replace("velocity = '0 0 0'", "velocity = '1 0 0'"),
            "changed_limiter": text.replace("advected_interp_method = upwind",
                                            "advected_interp_method = average"),
            "changed_transport": text.replace("model = lookup", "model = functor"),
            "changed_carrier": text.replace("carrier_one", "carrier_two"),
            "old_kernel": text.replace(NEW_BLOCK, OLD_BLOCK),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label):
                self.assertNotEqual(text, mutated)
                with self.assertRaises(ValueError):
                    check_fixture(mutated, sha)


if __name__ == "__main__":
    unittest.main()
