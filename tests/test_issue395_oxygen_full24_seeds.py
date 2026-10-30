"""Charged seed transform must keep all neutral IC and separate variable blocks."""
import importlib.util
import math
from pathlib import Path

import pytest

FOLDER=Path(__file__).resolve().parents[1]/"experiments/Issue395_powered_chemistry_ladder"

def _load():
    spec=importlib.util.spec_from_file_location("oxygen_seeds",FOLDER/"apply_oxygen_24_initial_seeds.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _fixture():
    return ("[Variables]\n"
            + "".join(f"  [{s}]\n    type = MooseVariableFVReal\n    initial_condition = -15.0\n  []\n"
                      for s in ("log_ne","log_ni","log_nm","log_nop"))
            + "  [w_O2s]\n    initial_condition = 0.002\n  []\n[]\n")

def test_four_existing_log_initial_conditions_and_block_boundaries():
    m=_load()
    original=_fixture()
    output=m.apply(original)
    assert output.count("initial_condition = ")==5
    assert output.count("  []\n")==5
    assert "  []\n  [w_O2s]" in output
    assert "    initial_condition = 0.002" in output
    for species,n in m.SEEDS_M3.items():
        block=output.split(f"  [{species}]\n",1)[1].split("  []",1)[0]
        expected=math.log(n/m.N_A)
        got=float(block.split("initial_condition = ",1)[1].splitlines()[0])
        assert math.isclose(got,expected,rel_tol=1e-14)

def test_seed_transform_missing_or_duplicate_fails():
    m=_load()
    with pytest.raises(ValueError, match="missing or duplicate"):
        m.apply(_fixture().replace("  [log_nm]","  [another]"))
    with pytest.raises(ValueError, match="require exactly one"):
        m.apply(_fixture().replace("    initial_condition = -15.0\n","",1))
