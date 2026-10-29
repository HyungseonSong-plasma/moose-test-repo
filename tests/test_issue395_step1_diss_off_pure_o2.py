"""Step1 single-factor inlet variation on the high-O, both-DISS-OFF Step0 baseline."""
import importlib.util
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CHEM = ROOT / "experiments/Issue395_powered_chemistry_ladder"
REPLAY = CHEM / "issue397_l1_power_scan_replay.sh"
AUDIT = CHEM / "analyze_ground_state_power_scan.py"


def test_step1_is_opt_in_and_protects_diss_knockout():
    script = REPLAY.read_text()
    assert subprocess.run(["bash", "-n", str(REPLAY)], capture_output=True).returncode == 0
    assert 'PURE_O2_INLET="${PURE_O2_INLET:-0}"' in script
    assert 'case "$PURE_O2_INLET" in 0|1)' in script
    assert 'export RESULT="${RESULT}_pure_o2_inlet_step1"' in script
    assert "ISSUE395_O2_DISSOCIATION_BOTH_OFF_PASS" in script
    assert '--channel "$DISS_CHANNEL"' in script
    assert 'set_pure_o2_inlet.py" --input "$INPUT" --verify' in script


def test_step1_audit_fails_nonzero_atomic_inlet(tmp_path):
    spec = importlib.util.spec_from_file_location("step1_audit", AUDIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = tmp_path / "case"
    (root / "run").mkdir(parents=True)
    csv = root / "run" / "plasma.csv"
    head = "time,neutral_inlet_mdot,neutral_inlet_mdot_O2,neutral_inlet_mdot_O2s,neutral_inlet_mdot_O,neutral_inlet_mdot_Os"
    valid = "0.0001,1.9395986970295842e-6,1.9395986970295842e-6,0,0,0"
    csv.write_text(head + "\n" + valid + "\n")
    result = mod.audit(root, 400, "head", "success", "skipped", "off", True)
    assert result["checks"]["dissociation_sources"]["status"] == "PASS"
    assert result["checks"]["inlet_pure_O2_X"]["status"] == "PASS"
    assert result["status"] == "NOT_PASS"  # D1/power required before scientific verdict
    csv.write_text(head + "\n" + valid + "\n" +
                   "0.0001,1.9395986970295842e-6,1.9395986970295842e-6,0,1e-9,0\n")
    bad = mod.audit(root, 400, "head", "success", "skipped", "off", True)
    assert bad["checks"]["inlet_pure_O2_X"]["status"] == "FAIL"
    csv.write_text(head + ",mixed_R_integral\n" + valid + ",0\n")
    forbidden = mod.audit(root, 400, "head", "success", "skipped", "off", True)
    assert forbidden["checks"]["dissociation_sources"]["status"] == "FAIL"
