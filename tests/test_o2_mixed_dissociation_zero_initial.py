"""P0: mixed 400/1000 W, exact zero O(3P), nonzero O(1D) preserved."""
import importlib.util
import math
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
CHEM = ROOT / "experiments/Issue395_powered_chemistry_ladder"
PATCHER = CHEM / "set_zero_initial_atomic_o.py"
REPLAY = CHEM / "issue397_l1_power_scan_replay.sh"

def load_patch():
    spec = importlib.util.spec_from_file_location("initial_o3p_patch", PATCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def generated_base() -> str:
    return """[Variables]
  [w_O]
    initial_condition = 0.10309278350515465
  []
  [w_Os]
    initial_condition = 0.12371134020618557
  []
  [w_O2s]
    initial_condition = 0.051546391752577324
  []
  [log_ne][]
  [log_ni][]
  [log_energy][]
[]
[FunctorMaterials]
  [q1]
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O w_Os'
    expression = '1.0-s-o-a'
  []
[]
"""

def test_only_O3P_ic_changes_and_residual_O2_increases():
    p = load_patch()
    orig = generated_base()
    mod = p.change_generated_input(orig)
    p.verify_generated_input(mod)
    assert orig.replace("initial_condition = 0.10309278350515465",
                        "initial_condition = 0.0",1) == mod
    assert "initial_condition = 0.12371134020618557" in mod
    assert "initial_condition = 0.051546391752577324" in mod
    initial_O2 = 1 - 0.10309278350515465 - 0.12371134020618557 - 0.051546391752577324
    zero_O2 = 1 - 0.12371134020618557 - 0.051546391752577324
    assert math.isclose(zero_O2, 0.8247422680412371, abs_tol=1e-15)
    assert math.isclose(zero_O2-initial_O2, 0.10309278350515465, abs_tol=1e-15)
    with pytest.raises(ValueError):
        p.change_generated_input(mod)

def test_zero_and_mixed_flags_are_opt_in_and_outputs_isolated():
    s=REPLAY.read_text(encoding="utf-8")
    assert 'DISS_CHANNEL="${DISS_CHANNEL:-ground}"' in s
    assert 'O_INITIAL_ZERO="${O_INITIAL_ZERO:-0}"' in s
    assert 'case "$O_INITIAL_ZERO" in 0|1)' in s
    assert 'export RESULT="${RESULT}_initial_o3p_zero"' in s
    assert '--channel "$DISS_CHANNEL"' in s
    assert s.count('python3 "$CHEM/set_zero_initial_atomic_o.py" --input "$INPUT" --verify') == 3
    assert "ZERO_O_VI_SOLVER_BUILD_PASS" not in s
    assert 'O_INITIAL_ZERO=$O_INITIAL_ZERO' in s
    proc=subprocess.run(["bash","-n",str(REPLAY)],capture_output=True,text=True)
    assert proc.returncode==0, proc.stderr

@pytest.mark.parametrize(("power","ch","o_zero"),[
    (400,"mixed","bad"),
    (1000,"mixed","-1"),
    (400,"both","1"),
    (1001,"mixed","1"),
])
def test_invalid_selectors_refused_before_prepare(power,ch,o_zero):
    p = subprocess.run(["bash",str(REPLAY),"prepare",str(power)],
            cwd=ROOT,env={**os.environ,"DISS_CHANNEL":ch,"O_INITIAL_ZERO":o_zero},
            capture_output=True,text=True,timeout=15)
    assert p.returncode != 0
    assert "unsupported" in p.stderr.lower()

def test_cli_positive_verify_and_negative_control(tmp_path):
    p=tmp_path/"input.i"
    p.write_text(generated_base())
    r=subprocess.run([sys.executable,str(PATCHER),"--input",str(p)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert "INITIAL_O_ZERO_EXACT_ONE_LINE_PASS" in r.stdout
    r=subprocess.run([sys.executable,str(PATCHER),"--input",str(p),"--verify"],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert "INITIAL_O_ZERO_VERIFICATION_PASS" in r.stdout
    p.write_text(generated_base().replace("0.10309278350515465","0.2"))
    r=subprocess.run([sys.executable,str(PATCHER),"--input",str(p)],capture_output=True,text=True)
    assert r.returncode != 0
