"""P0 unit and negative mutation checks for the bounded 2 ns Oxygen24 smoke grid."""
import importlib.util
from pathlib import Path
import pytest

SOURCE = (Path(__file__).resolve().parents[1] / "experiments" /
          "Issue395_powered_chemistry_ladder" / "set_timegrid_oxygen24_2ns_smoke.py")


def _module():
    spec = importlib.util.spec_from_file_location("oxygen24_smoke", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _input():
    return ("[Executioner]\n  type = Transient\n  scheme = implicit-euler\n"
            "  end_time = 1e-4\n  [TimeStepper]\n"
            "    type = TimeSequenceStepper\n"
            "    time_sequence = '0 1e-9 2e-9 3e-9 4e-9'\n  []\n[]\n")


def test_grid_exact_two_steps_and_idempotence():
    m = _module()
    output = m.transform(_input())
    result = m.verify(output)
    assert result["steps"] == 2
    assert result["time_s"] == [0.0, 1e-9, 2e-9]
    assert output == m.transform(output)
    assert "scheme = implicit-euler" in output
    assert "type = TimeSequenceStepper" in output


@pytest.mark.parametrize("mutation", ["canonical", "wrong_end", "missing_grid", "extra_step"])
def test_grid_negative_mutations(mutation):
    m = _module()
    valid = m.transform(_input())
    bad = {
        "canonical": _input(),
        "wrong_end": valid.replace("end_time = 2.0000000000000001e-09",
                                   "end_time = 1e-4"),
        "missing_grid": valid.replace("time_sequence", "time_step_sequence"),
        "extra_step": valid.replace("1.0000000000000001e-09 2.0000000000000001e-09'",
                                    "1.0000000000000001e-09 2.0000000000000001e-09 3e-9'"),
    }[mutation]
    assert bad != valid
    with pytest.raises(ValueError):
        m.verify(bad)


def test_grid_selftest():
    _module().self_test()
