"""P6-D1 exact-owner Scratch cutover controls; no MOOSE solve or private EI rates."""
from __future__ import annotations
import ast
import base64
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
import zlib

REPO = Path(__file__).resolve().parents[1]
PILOT = REPO / "experiments/Issue402_plasma_dsl_g1"
SOURCE = PILOT / "public_option_s6_p2.py"
DONOR = PILOT / "chemistry/prepare_hybrid_json_s6.py"
# Source-archived, PUBLIC 42-row electron moments (not protected EI rate data).
# SHA must equal the pinned historical table, else the fixture is unusable.
TABLE = zlib.decompress(base64.b64decode("eNpFlEsO4zAMQ/c9RfcDGPp/DjT3v8JQidVZFCiSF1uiKPIJL2Fpqq8eIhOvEJW/f8TwIMUDQDnPg48d5Rb+8knr5mzwDxmH2Eo7KOoh/eAQF5DWeCGhHJeUosiOZL9kqmSA1IpOwQl8Sa00i5D3008cFqocks1dtXTPNK8OVjy9pKHuqRPtSIgBvqSzU5e49SUzyB6S0U9ycy85F1fzW84nD7g2kIwiqR2/SwapmFK8soHE/6whNVk9jGlJI2Jil7qkO7QdkoLEuWh7j1RXL+q+ZHaHg6QscrSlSyaZaVbZ23sdwpBGT2CWwv2fVFWCUG2XtHTpISmhkkKaJWECLsjxKt8HdUD5Pk7uuIseUkGWR1KG3Ln3iaoKkKTa1Oodl4SyGel7JhOGw/qtA29USzf5kpmu6D90ycR7kFJiXRz2kjmtonVvf1XisUY2XnQ6B7WxLQmXx0hVS5bUkEkcDKEeQwzJOsJx6iXlKO7FC7irBR4vXTKjGUZsWrI4Ey9EFRdBer6kCMMJpXePWA/6feonx4Deux4wXNiMr5wAM5VHZ8MqEGltQwrVOQ2VvqQd/OXHOVIWgvVc0pq5oq7pQCbOeXYBx6lIbZlaXfAh/PSSfjjEZxPDod1M9pKwO3EW7LQkipHZbkk1DIW2TosOhXvonomoiB6SOnEKJNlhOuGCWSxfEgvhX3+GWWxIjSUtxyLOtiR2o0DCCljhct86kWaG1Ii+pkM92HOQ6SQNJ8sOEykBjagil4S1BWTYHNEIwSUnzDD0uGOvGebcjrLgETNZPeEtRThk/0gMbDpCIOFVpW6dqY2PRfPW2QetK0jFABCMCJglcxJL1GnJkDSQksgS8/4tR7FD6RZ5SaFRfnpHhlshf3V7x1UlOPhNtCGdZXpnHuOW/KaJRcXcrT2XbEQpSFIMWtHAOrmVJAnzeDsSrGaXfg0fjCEEQbBkoD9D5b5kIWlBwm6NGcFSD1mTU5QT/q+XBKupKFTnWDgHXia7eQMYVZp1Xjv9A6A0Zgo="))
assert hashlib.sha256(TABLE).hexdigest() == (
    "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b")


def extract_option() -> tuple[object, str]:
    tree = ast.parse(SOURCE.read_text())
    fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and
              x.name == "cutover_staged_D_transport_owners")
    overlay = next(ast.literal_eval(x.value) for x in tree.body
                   if isinstance(x, ast.Assign) and any(
                       isinstance(t, ast.Name) and t.id == "OVERLAY"
                       for t in x.targets))
    return compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), "exec"), overlay


class TestExactCutover(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture_module = self.root / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py"
        fixture_module.parent.mkdir(parents=True)
        shutil.copyfile(DONOR, fixture_module)
        self.folder = self.root / "experiments/Issue395_powered_chemistry_ladder"
        self.folder.mkdir(parents=True)
        self.ordered = ["chem/c0.i"] + [f"chem/side{i}.i" for i in range(9)] + [
            "chem/migrated_continuity.i"]
        donor_spec = importlib.util.spec_from_file_location("p6_d1_fixture", DONOR)
        donor = importlib.util.module_from_spec(donor_spec)
        donor_spec.loader.exec_module(donor)
        text = "[FunctorMaterials]\n  [electron_transport]\n" + "".join(
            f"    {key} = {val}\n"
            for key, val in donor.SOURCE_MATERIAL["electron_transport"].items()
        ) + "  []\n[]\n"
        self.first = self.folder / "c0.i"
        self.first.write_text(text)
        for i in range(9):
            (self.folder / f"side{i}.i").write_text(f"# side {i}\n")
        code, overlay = extract_option()
        self.overlay = self.folder / "migrated_continuity.i"
        self.overlay.write_text(overlay)
        self.js = self.folder / "plasma_species_only.json"
        self.js.write_text(json.dumps({
            "species": {
                **{s: {"elements": {}, "charge_number": -1 if s in ("e", "Om") else 1,
                       "initial_number_density": 1e15 if s == "e" else 1e12}
                   for s in ("e", "O2p", "Om", "Op")},
                "O2": {"elements": {"O": 2}, "charge_number": 0},
                "O": {"elements": {"O": 1}, "charge_number": 0},
            }, "equations": {}, "reactions": []}, indent=2))
        self.table = self.root / "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
        self.table.parent.mkdir(parents=True)
        self.table.write_bytes(TABLE)
        ns = {"ROOT": self.root, "Path": Path, "hashlib": hashlib, "json": json, "math": math}
        exec(code, ns)
        self.cutover = ns["cutover_staged_D_transport_owners"]

    def snapshot(self):
        return tuple(p.read_bytes() for p in (self.first, self.overlay, self.js))

    def fail_atomic(self, regex):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, regex):
            self.cutover(self.folder, self.ordered)
        self.assertEqual(before, self.snapshot())

    def test_both_case_contracts_are_source_invariant(self):
        for variant in ("417", "941"):
            with self.subTest(variant=variant):
                before = self.snapshot()
                receipt = self.cutover(self.folder, self.ordered)
                self.assertEqual(receipt["retired_material_count"], 4)
                self.assertEqual(receipt["native_P05"], "NOT_RUN")
                self.assertEqual(receipt["science"], "SCIENCE_HOLD")
                self.assertNotIn("[electron_transport]", self.first.read_text())
                for species in ("O2p", "Om", "Op"):
                    self.assertNotIn(f"[{species}_species_transport_alias]",
                                     self.overlay.read_text())
                result = json.loads(self.js.read_text())["species"]
                self.assertEqual(result["e"]["energy_transport_coef"], "fluid")
                self.assertEqual(result["e"]["table_file"],
                                 "../Issue91_real_qvt_r3/r3_e0/electron_moments.txt")
                self.assertEqual(result["e"]["gas_temperature"], "T_g_fixed")
                self.assertEqual(result["e"]["pressure"], "p")
                self.assertEqual(result["O2p"]["mobility"], "ion_mobility")
                self.assertEqual(result["Op"]["diffusivity"],
                                 "atomic_positive_ion_diffusion")
                self.assertNotEqual(before, self.snapshot())
                # This is not an idempotent/unsafe auto-rewriting migration.
                self.fail_atomic("OWNER_COUNT")
                self.setUp()

    def test_negative_owner_and_data_mutations(self):
        failures = [
            ("missing_e", lambda: self.first.write_text(self.first.read_text().replace(
                "[electron_transport]", "[missing_e]")), "OWNER_COUNT"),
            ("wrong_fluid", lambda: self.first.write_text(self.first.read_text().replace(
                "fluid_energy = true", "fluid_energy = false")), "OWNER_IDENTITY"),
            ("wrong_table", lambda: self.first.write_text(self.first.read_text().replace(
                "electron_moments.txt", "other_table.txt")), "OWNER_IDENTITY"),
            ("wrong_gas", lambda: self.first.write_text(self.first.read_text().replace(
                "T_g_fixed", "T_g_fake")), "OWNER_IDENTITY"),
            ("missing_ion", lambda: self.overlay.write_text(self.overlay.read_text().replace(
                "[Om_species_transport_alias]", "[missing_Om]")), "OWNER_COUNT"),
            ("wrong_ion_coefficient", lambda: self.overlay.write_text(
                self.overlay.read_text().replace("negative_ion_diffusion",
                                                 "unproven_diffusion")), "OWNER_IDENTITY"),
            ("charge_sign", lambda: self.change_json("Om", "charge_number", 1),
             "PRECUTOVER_INITIAL_IDENTITY"),
            ("invalid_density", lambda: self.change_json("e", "initial_number_density", -1),
             "PRECUTOVER_INITIAL_IDENTITY"),
            ("preexisting_json_owner", lambda: self.change_json("e", "transport_coef", "lookup"),
             "PRECUTOVER_INITIAL_IDENTITY"),
            ("table_mutation", lambda: self.table.write_bytes(b"tampered"),
             "TABLE_SHA_MISMATCH"),
            ("table_missing", lambda: self.table.unlink(), "TABLE_SHA_MISMATCH"),
        ]
        for name, change, diagnostic in failures:
            with self.subTest(mutation=name):
                change()
                self.fail_atomic(diagnostic)
                self.setUp()

    def change_json(self, species, key, value):
        data = json.loads(self.js.read_text())
        data["species"][species][key] = value
        self.js.write_text(json.dumps(data))

    def test_cpp_historical_5_over_3_is_faithful(self):
        source = (REPO / "physics_app/src/physics/plasma/DDContinuityEq.C").read_text()
        self.assertIn("mechanism.fluidElectronEnergyTransport()", source)
        self.assertIn('params.set<bool>("fluid_energy") = fluid || legacy_fluid;', source)
        self.assertIn('if (legacy_fluid && !energy.empty() && !fluid)', source)

    def test_flow_executes_exact_arch_hybrid_transport_handoff(self):
        source = (PILOT / "run_chemistry_s6_p2_only.py").read_text()
        self.assertIn("prepare as prepare_hybrid_transport", source)
        self.assertIn("hybrid_transport = prepare_hybrid_transport(", source)
        self.assertIn("chemistry, ordered, case, chemistry_cutover=cutover", source)


if __name__ == "__main__":
    unittest.main()
