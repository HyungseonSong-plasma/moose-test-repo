"""H3 Code4 rewire: exact Native-qualified deck identity and fail-closed inputs."""
import ast
import hashlib
from pathlib import Path
import re

import pytest

from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / ".github/scripts/issue197_h3_migration_audit.py"
SOURCE = ROOT / "experiments/Issue1_reactor_o2plus_integration/migration_only_exact_phi_ic"
FIXTURE = "migration_only_exact_phi_ic.i"

# Run #45450219225, artifact 14948626850, actual FVAdvection P2/P3 inputs.
QUALIFIED = {
    (1, 1): "c74f9266aec965d1db2f8396a094dc74ddcfb4224795f3301cbf85d3055cd75e",
    (1, -1): "8b1599ba690e37168444c6e3d57a750141e5d99de76f60920bd1e09af99cb631",
    (-1, 1): "6157ac08a0db8f82835e2f66d0135100a0f170c09c3ab3b5ebd68ca065e65283",
    (-1, -1): "17e6dc32aeed79bc7d9c9860da72af5ea4bc25f30704162dca75b1789698c689",
}


def builder(source=SOURCE):
    # The legacy driver runs its audit at import time. Execute only its actual
    # construction functions, as the Native qualification did.
    names = {"sha256", "replace_scalar", "current_runtime_input"}
    functions = [
        node for node in ast.parse(DRIVER.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in functions} == names
    assert len(functions) == len(names)
    namespace = {"SOURCE": source, "hashlib": hashlib, "re": re, "mp": mp}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(DRIVER), "exec"), namespace)
    return namespace["current_runtime_input"]


@pytest.mark.parametrize("charge,field", QUALIFIED)
def test_h3_generator_matches_native_qualified_deck(charge, field):
    text, promotions = builder()(charge_number=charge, field_sign=field)
    assert hashlib.sha256(text.encode()).hexdigest() == QUALIFIED[charge, field]
    block = "FVKernels/ion_electrostatic_drift"
    assert promotions[block] == "FVAdvection"
    assert mp.get_parameter(text, block, "type") == "FVAdvection"
    assert mp.words(mp.get_parameter(text, block, "velocity")) == [str(charge * field * 200), "0", "0"]
    assert mp.words(mp.get_parameter(text, block, "boundaries_to_avoid")) == ["left", "right"]


@pytest.mark.parametrize("charge,field", [(0, 1), (1, 0), (2, -1), (-1, 2)])
def test_h3_rejects_unqualified_signs(charge, field):
    with pytest.raises(ValueError, match="four signed controls"):
        builder()(charge_number=charge, field_sign=field)


@pytest.mark.parametrize("before,after", [("rho0 = 1", "rho0 = 2"), ("mu_i = 0.01", "mu_i = 0.02"), ("xmax = 1.0", "xmax = 2.0")])
def test_h3_rejects_changed_fixture(tmp_path, before, after):
    original = (SOURCE / FIXTURE).read_bytes()
    assert before.encode() in original
    (tmp_path / FIXTURE).write_bytes(original.replace(before.encode(), after.encode(), 1))
    with pytest.raises(RuntimeError, match="fixture changed"):
        builder(tmp_path)(charge_number=1, field_sign=1)
