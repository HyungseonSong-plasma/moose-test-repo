"""Issue 397 serial governed replay manifest and authorized one-shot contract."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHEM = ROOT / "experiments" / "Issue395_powered_chemistry_ladder"
RUNNER = CHEM / "issue397_l1_power_scan_replay.sh"
MANIFEST = ROOT / "automation/manifests/experiments/Issue_397_experiments01.json"
CONTRACT = CHEM / "issue397_final_l1_200_250_300w_power_scan_contract.json"
TEMPLATE = CHEM / "issue397_l1_final_replay_once.template.yml.txt"


class Issue397SamuelReplayTests(unittest.TestCase):
    def test_bash_syntax_and_required_phases(self):
        subprocess.run(["bash", "-n", str(RUNNER)], check=True)
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("case \"$PHASE\" in", source)
        self.assertIn("200|250|300", source)
        for phase in ("prepare", "build", "check", "solve", "audit"):
            self.assertIn(f"  {phase})", source)
        self.assertIn("ISSUE397_REPLAY_PHASE_PASS=", source)
        self.assertIn('test "$(git rev-parse HEAD)" = "$CHATGPT_WORK_BASE_SHA"', source)
        self.assertRegex(source, r"(?m)^PY$")  # original exact-source heredoc

    def test_science_gates_retained_from_historical_workflow(self):
        source = RUNNER.read_text(encoding="utf-8")
        for item in (
            "EXPECTED_STEPS=460",
            "ISSUE397_BASELINE_L1_MESH_PASS",
            "ISSUE397_D1_NATIVE_DIAGNOSTICS_INPUT_PASS",
            "nl_abs_tol = 1e-11",
            "ISSUE397_MAXWELL_SINGLE_TOLERANCE_CHANGE_PASS",
            "PID_max_drive_unmodified",
            "ISSUE395_EI17_O_ELASTIC_OVERLAY_BUILD_PASS",
            "make -C physics_app -j2",
            "physics_app/physics-opt --check-input",
            "Outputs/file_base=",
            "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS",
        ):
            with self.subTest(contract=item):
                self.assertIn(item, source)
        # Historical alternatives must stay inactive in the generated input.
        self.assertIn('! grep -q "use_bohm_ion_collection = true"', source)
        self.assertIn('! grep -q "use_negative_ion_sheath_barrier = true"', source)

    def test_serial_governed_manifest_and_timeout_contract(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual((data["schema_version"], data["issue"], data["kind"], data["sequence"]), (1, 397, "experiments", 1))
        self.assertEqual([stage["id"] for stage in data["stages"]], ["P0", "P1", "P2", "P3"])
        self.assertTrue(all(1 <= stage["timeout_seconds"] <= 7200 for stage in data["stages"]))
        commands = "\n".join(" ".join(stage["command"]) for stage in data["stages"])
        self.assertIn("for power in 200 250 300", commands)
        self.assertIn(" prepare", commands)
        self.assertIn(" build 200", commands)
        self.assertIn(' check "$power"', commands)
        self.assertNotIn(' solve "$power"', commands)
        self.assertNotIn(' audit "$power"', commands)

    def test_approved_workflow_surface_unchanged(self):
        forbidden = ROOT / ".github/workflows/issue397-graded-l1-power-scan-200-250-300w-100us.yml"
        self.assertFalse(forbidden.exists())
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("branches: [main]", template)
        self.assertIn("paths: [.github/workflows/issue397-l1-final-replay-once.yml]", template)
        self.assertIn("timeout-minutes: 360", template)
        self.assertIn("fail-fast: false", template)
        self.assertIn("power_w: [200, 250, 300]", template)
        self.assertIn('if: always()', template)
        self.assertIn("audit \"${{ matrix.power_w }}\"", template)
        self.assertFalse((ROOT / ".github/workflows/issue397-l1-final-replay-once.yml").exists())

    def test_contract_identifies_historical_and_future_evidence(self):
        data = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual([x["target_power_W"] for x in data["cases"]], [200, 250, 300])
        self.assertEqual(data["controls"]["maxwell_child"]["selected_abs_tol"], 1e-11)
        self.assertEqual(data["controls"]["time_grid"]["steps"], 460)
        self.assertEqual(data["controls"]["wafer_faces"], 27)
        self.assertTrue(data["safety_and_evidence"]["never_claim_preflight_as_100us_solver_pass"])
        self.assertEqual(data["execution"]["samuel_manifest"], MANIFEST.relative_to(ROOT).as_posix())
        self.assertEqual(data["historical_outcomes"]["original_run_39617859962"]["power_300"], "P3 cancelled near 58ns under nl_abs_tol=1e-12")


if __name__ == "__main__":
    unittest.main()
