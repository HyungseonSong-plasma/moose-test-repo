"""Controlled Step0 chemistry knockout: only O2 electron-impact dissociation absent."""
import importlib.util
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CHEM = ROOT / "experiments/Issue395_powered_chemistry_ladder"
SCRIPT = CHEM / "issue397_l1_power_scan_replay.sh"
BUILDER = CHEM / "build_o2_dissociation_overlay.py"
AUDIT = CHEM / "analyze_ground_state_power_scan.py"


def test_p0_off_overlay_has_no_active_blocks(tmp_path):
    base = tmp_path / "base.i"
    base.write_text("[Variables]\n  [w_O]\n  []\n[]\n")
    off = tmp_path / "off.i"
    command = ["python3", str(BUILDER), "--base-input", str(base),
               "--channel", "off", "--output", str(off)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    assert "ISSUE395_O2_DISSOCIATION_BOTH_OFF_PASS" in result.stdout
    assert off.read_text() == "# Controlled Step0 knockout: ground and mixed O2 dissociation OFF.\n"
    for name in ("R_diss_O2", "R_diss_O2_mixed", "S_O_mass_diss", "[Kernels]", "[FVKernels]"):
        assert name not in off.read_text()


def test_off_rejects_inherited_progress(tmp_path):
    base = tmp_path / "base.i"
    base.write_text("property_name = R_diss_O2_mixed\n")
    proc = subprocess.run(
        ["python3", str(BUILDER), "--base-input", str(base), "--channel", "off",
         "--output", str(tmp_path / "off.i")], capture_output=True, text=True
    )
    assert proc.returncode != 0
    assert "inherited" in proc.stderr


def test_replay_isolated_and_exclusive():
    s = SCRIPT.read_text()
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0
    assert 'case "$DISS_CHANNEL" in ground|mixed|off)' in s
    assert 'export RESULT="${RESULT}_both_diss_off_step0_control"' in s
    assert 'ISSUE395_O2_DISSOCIATION_BOTH_OFF_PASS' in s
    assert s.count("'$DISS'") == 2
    assert s.count("  --channel \"$DISS_CHANNEL\"") == 1
    for name in ('"$ION"', '"$ION_O"', '"$ATTACH"', '"$ELASTIC"', '"$OELASTIC"'):
        assert s.count(name) >= 3


def test_invalid_channel_rejected_before_side_effects():
    p = subprocess.run(["bash", str(SCRIPT), "prepare", "400"], cwd=ROOT,
                       env={**os.environ, "DISS_CHANNEL": "both"},
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert "unsupported O2 dissociation channel" in p.stderr


def test_audit_no_diss_fields(tmp_path):
    spec = importlib.util.spec_from_file_location("step0_audit", AUDIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = tmp_path / "case"
    (result / "run").mkdir(parents=True)
    (result / "run/plasma.csv").write_text(
        "time,rf_drive_scale_t6,P_rf_scaled_W_t6,P_abs_maxwell_t6\n"
        "0,1,400,400\n0.0001,2,400,400\n"
    )
    report = mod.audit(result, 400, "source", "success", "skipped", "off")
    assert report["checks"]["dissociation_sources"]["status"] == "PASS"
    assert report["checks"]["dissociation_sources"]["reaction_progress_owner"] == "NONE"
    assert report["checks"]["wafer_D1_integrity"]["status"] == "INCOMPLETE"
    assert report["status"] == "NOT_PASS"
    (result / "run/plasma.csv").write_text(
        "time,mixed_R_integral\n0,0\n0.0001,0\n"
    )
    neg = mod.audit(result, 400, "source", "success", "skipped", "off")
    assert neg["checks"]["dissociation_sources"]["status"] == "FAIL"
