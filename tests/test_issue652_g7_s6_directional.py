"""G7 proof parser controls: no false PASS or promotion from missing evidence."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"ci/guards"))
import issue652_g7_s6_directional as g7


def receipt(err="1e-10",conv="1e-11",restore="0"):
    return "G7_FIXED_STATE 6000 5\n"+"".join(
        f"G7_JVP 6000 {i} {err} {conv} {err}\n" for i in range(3)
    )+f"G7_RESTORE 6000 1 {restore}\n"


def test_pass_only_with_three_directions_and_restoration():
    assert g7.interpret(receipt(),5000)["status"]=="PASS_FIXED_STATE_DIRECTIONAL"


@pytest.mark.parametrize("log",["",receipt().replace("G7_JVP 6000 2","G7_JVP 6000 1"),
    receipt().replace("G7_RESTORE 6000 1","G7_RESTORE 6000 0"),receipt(restore="1e-4"),
    receipt().replace("G7_FIXED_STATE 6000 5","G7_FIXED_STATE 100 5")])
def test_incomplete_invalid_receipt(log):
    assert g7.interpret(log,5000)["status"]=="HOLD_PROBE_MISSING_OR_INVALID"


@pytest.mark.parametrize("log",[receipt(err="1e-7"),receipt(conv="1e-7")])
def test_strict_numeric_gate(log):
    assert g7.interpret(log,5000)["status"]=="HOLD_DIRECTIONAL_TOLERANCE"


def test_contract_unchanged():
    assert g7.LIMIT==1e-8 and g7.STEPS==(1e-4,5e-5,2.5e-5)
