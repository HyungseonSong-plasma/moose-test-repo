"""P0 guards for exclusive mixed O3P/O1D 400/1000W production replay."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh"


def test_script_syntax_and_default_contract():
    run = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    s = SCRIPT.read_text(encoding="utf-8")
    assert 'DISS_CHANNEL="${DISS_CHANNEL:-ground}"' in s
    assert 'case "$POWER_W" in 200|250|300|400|600|1000)' in s
    assert '--channel "$DISS_CHANNEL"' in s
    assert 'if [[ "$DISS_CHANNEL" == "mixed" ]]; then' in s
    assert 'export RESULT="${RESULT}_mixed_o3p_o1d"' in s
    assert "grep -Fqx '    property_name = R_diss_O2_mixed' \"$DISS\"" in s
    assert "grep -Fqx '    property_name = R_diss_O2' \"$DISS\"" in s
    assert "! grep -Fqx '    property_name = R_diss_O2' \"$DISS\"" in s
    assert "grep -Fqx '    variable = w_Os' \"$DISS\"" in s
    assert "grep -Fqx '    variable = w_O' \"$DISS\"" in s
    assert "ISSUE395_O2_MIXED_DISSOCIATION_OVERLAY_BUILD_PASS" in s
    assert "DISS_CHANNEL=$DISS_CHANNEL" in s
    # The production solver consumes only the selected overlay.
    assert s.count("'$DISS'") == 2  # check and solve


def test_invalid_power_or_channel_exits_before_execution():
    for power, channel in ((401, "mixed"), (400, "both"), (1000, "neither")):
        proc = subprocess.run(
            ["bash", str(SCRIPT), "prepare", str(power)],
            env={**os.environ, "DISS_CHANNEL": channel},
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode != 0
        assert "unsupported" in proc.stderr.lower()
        assert "ISSUE397_REPLAY_PHASE=prepare" not in proc.stdout
