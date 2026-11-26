"""Code5-B source-shape characterization; never substitutes for Native parity.

The candidate and legacy C++ implementations must remain mechanically
identical modulo deliberate type renaming and description-only changes.
Retire this source-bound comparison into an immutable provenance receipt
BEFORE removing the legacy translation unit in code5-E.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "physics_app" / "src" / "fvkernels"
HDR = ROOT / "physics_app" / "include" / "fvkernels"
OLD_C = SRC / "PhysicsFVLogMolarElectronTransport.C"
NEW_C = SRC / "FVLogMolarTransport.C"
OLD_H = HDR / "PhysicsFVLogMolarElectronTransport.h"
NEW_H = HDR / "FVLogMolarTransport.h"

OWNERS = (
    ("PhysicsFVLogMolarElectronTimeDerivative", "FVLogMolarTimeDerivative"),
    ("PhysicsFVLogMolarElectronDiffusion", "FVLogMolarDiffusion"),
    ("PhysicsFVLogMolarElectrostaticDrift", "FVLogMolarElectrostaticDrift"),
)

DESCRIPTIONS = (
    ("c_e=exp(log_e)", "c=exp(log_c)"),
    ("Orthogonal FV electron diffusion", "Orthogonal FV species diffusion"),
    ("Electron diffusion coefficient", "Species diffusion coefficient"),
    ("for electron molar concentration", "for log-molar species concentration"),
)


def implementation(body: str, name: str, next_name: str | None) -> str:
    marker = "InputParameters\n" + name + "::validParams()"
    if body.count(marker) != 1:
        raise ValueError("CLASS_IMPLEMENTATION_MISSING_OR_DUPLICATE:" + name)
    start = body.index(marker)
    stop = (body.find("InputParameters\n" + next_name + "::validParams()", start + 1)
            if next_name else -1)
    if next_name and stop < 0:
        raise ValueError("NEXT_CLASS_IMPLEMENTATION_MISSING:" + next_name)
    return body[start:stop if stop >= 0 else None].strip()


def declaration(body: str, name: str, next_name: str | None) -> str:
    hit = re.search(r"\bclass " + re.escape(name) + r"\b", body)
    if not hit:
        raise ValueError("CLASS_HEADER_MISSING:" + name)
    stop = (body.find("class " + next_name + " ", hit.end())
            if next_name else -1)
    if next_name and stop < 0:
        raise ValueError("NEXT_CLASS_HEADER_MISSING:" + next_name)
    lines = body[hit.start():stop if stop >= 0 else None].splitlines()
    return "\n".join(line for line in lines
                     if line.strip() and not line.strip().startswith("/**")).strip()


def normalize_old(body: str, old_name: str, new_name: str) -> str:
    normalized = body.replace(old_name, new_name)
    for old, new in DESCRIPTIONS:
        normalized = normalized.replace(old, new)
    return normalized.strip()


class Code5GenericP0(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_c = OLD_C.read_text(encoding="utf-8")
        cls.new_c = NEW_C.read_text(encoding="utf-8")
        cls.old_h = OLD_H.read_text(encoding="utf-8")
        cls.new_h = NEW_H.read_text(encoding="utf-8")

    def test_three_registered_factory_classes_only(self):
        for _, new in OWNERS:
            self.assertEqual(self.new_c.count(
                'registerMooseObject("PhysicsApp", ' + new + ');'), 1)
            self.assertEqual(self.new_h.count("class " + new + " : public "), 1)
        self.assertEqual(self.new_c.count("registerMooseObject("), 3)
        self.assertNotIn("PhysicsFVLogMolarElectronReactionSource", self.new_c)
        self.assertNotIn("PhysicsFVLogMolarElectronReactionSource", self.new_h)

    def test_exact_legacy_implementation_after_nonsemantic_normalization(self):
        for i, (old, new) in enumerate(OWNERS):
            old_next = (OWNERS[i + 1][0] if i + 1 < len(OWNERS)
                        else "PhysicsFVLogMolarElectronReactionSource")
            new_next = OWNERS[i + 1][1] if i + 1 < len(OWNERS) else None
            with self.subTest(class_name=new):
                incumbent = implementation(self.old_c, old, old_next)
                candidate = implementation(self.new_c, new, new_next)
                self.assertEqual(normalize_old(incumbent, old, new), candidate)
                incumbent_header = declaration(self.old_h, old, old_next)
                candidate_header = declaration(self.new_h, new, new_next)
                self.assertEqual(normalize_old(incumbent_header, old, new),
                                 candidate_header)

    def test_expected_scientific_contract_anchors_and_negative_mutations(self):
        new = self.new_c
        markers = (
            "return (exp(log_c_new) - exp(log_c_old)) / _dt;",
            "if (!_subproblem.isTransient())",
            "params.set<MultiMooseEnum>(\"vector_tags\") = \"time\";",
            "if (!_var.isInternalFace(*_face_info))",
            "return -coeff_face * (c_neighbor - c_elem) / _face_info->dCNMag();",
            "const bool elem_is_upwind = MetaPhysicL::raw_value(drift_normal) >= 0.0;",
            "_charge_number * mobility_face * (electric_field * _normal);",
            "return carrier_face * c_face * drift_normal;",
            "use_element_gradient_for_potential",
            "use_limited_linear_reconstruction",
        )
        for marker in markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, new)
                changed = new.replace(marker, "UNSAFE_NEGATIVE_MUTATION", 1)
                self.assertNotIn(marker, changed)

    def test_no_rewire_or_legacy_deletion_in_candidate(self):
        self.assertTrue(OLD_C.is_file())
        self.assertTrue(OLD_H.is_file())
        self.assertIn("PhysicsFVLogMolarElectronReactionSource", self.old_c)
        self.assertNotIn("FVCoupledForce", self.new_c)
        self.assertEqual(self.old_c.count('registerMooseObject("PhysicsApp",'), 4)


if __name__ == "__main__":
    unittest.main()
