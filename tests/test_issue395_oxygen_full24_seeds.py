"""P0 proof: chemistry neutral initial states use number fraction x=1e-5."""
import importlib.util
import math
from pathlib import Path

import pytest

FOLDER = Path(__file__).resolve().parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "oxygen_seeds", FOLDER.parent / "experiments" / "Issue395_powered_chemistry_ladder"
        / "apply_oxygen_24_initial_seeds.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture():
    charged = ("log_ne", "log_ni", "log_nm", "log_nop")
    neutral = ("w_O2s", "w_O", "w_Os")
    return "[Variables]\n" + "".join(
        f"  [{s}]\n    type = INSFVScalarFieldVariable\n"
        f"    initial_condition = {'-15.0' if s in charged else '0.1'}\n"
        "    block = plasma\n  []\n"
        for s in (*charged, *neutral)
    ) + "[]\n"


def _block(text, name):
    return text.split(f"  [{name}]\n", 1)[1].split("  []", 1)[0]


def test_seven_initial_seeds_and_mass_to_number_fraction():
    m = _load()
    output = m.apply(_fixture())
    assert output.count("initial_condition = ") == 7
    assert output.count("block = plasma") == 7
    assert m.apply(output) == output
    for species, n in m.SEEDS_M3.items():
        got = float(_block(output, species).split("initial_condition = ", 1)[1].splitlines()[0])
        assert math.isclose(got, math.log(n / m.N_A), rel_tol=1e-14)
    for name, target in m.NEUTRAL_MASS_FRACTIONS.items():
        got = float(_block(output, name).split("initial_condition = ", 1)[1].splitlines()[0])
        assert math.isclose(got, target, rel_tol=1e-14)
    inferred = m.verify_neutrals(output)
    assert all(math.isclose(inferred[name], 1e-5, rel_tol=1e-12)
               for name in m.MINOR_NUMBER_FRACTIONS)
    assert math.isclose(inferred["O2_X"], 0.99997, abs_tol=1e-12)
    assert math.isclose(sum(inferred.values()), 1.0, abs_tol=1e-12)
    m.verify_charged(output)


@pytest.mark.parametrize("name", ["w_O2s", "w_O", "w_Os"])
def test_p0_rejects_mutated_neutral_number_fraction(name):
    m = _load()
    valid = m.apply(_fixture())
    expected = f"initial_condition = {m.NEUTRAL_MASS_FRACTIONS[name]:.17g}"
    mutated = valid.replace(expected, "initial_condition = 0.1", 1)
    # The two atomic-O mass fractions have the same literal; modifying either
    # causes P0 rejection regardless of target identity.
    assert mutated != valid
    with pytest.raises(ValueError, match="P0 number fraction mismatch"):
        m.verify_neutrals(mutated)


@pytest.mark.parametrize("name", ["w_O2s", "w_O", "w_Os"])
def test_p0_rejects_missing_or_duplicate_neutral_blocks(name):
    m = _load()
    valid = m.apply(_fixture())
    with pytest.raises(ValueError, match="missing or duplicate variable blocks"):
        m.verify_neutrals(valid.replace(f"  [{name}]", "  [removed]", 1))
    block = f"  [{name}]\n" + _block(valid, name) + "  []\n"
    with pytest.raises(ValueError, match="missing or duplicate variable blocks"):
        m.verify_neutrals("[Variables]\n" + block + valid[len("[Variables]\n"):])


def test_original_charged_seeds_still_guarded():
    m = _load()
    valid = m.apply(_fixture())
    with pytest.raises(ValueError, match="P0 charged seed mismatch"):
        m.verify_charged(valid.replace(
            f"initial_condition = {math.log(m.SEEDS_M3['log_ne']/m.N_A):.17g}",
            "initial_condition = -15.0", 1
        ))
    with pytest.raises(ValueError, match="missing or duplicate variable blocks"):
        m.apply(_fixture().replace("  [log_ne]", "  [removed]", 1))


def test_p0_mutation_selftest():
    _load().self_test()
