"""Issue477 S6 combined chemistry: two 8-channel branches with native audit gates."""
from pathlib import Path

import pytest

from experiments.Issue477_electron_shape import prepare_s6_combined_consumers as s6
from experiments.Issue477_electron_shape import prepare_s4_o2_consumers as s5


def test_only_two_approved_combined_cases_and_three_additions():
    assert s6.CASE_PARENTS == {
        "S6-417-407-2069-H25": "417", "S6-941-407-2069-H25": "941"}
    assert s6.ADDED == ("EI-407", "EI-2069", "H25")
    assert s6.EXPECTED_EXTRA_OWNERS == {"R_EI407", "R_EI2069", "R_H25"}
    assert s5.EXTRAS["407"]["rate_sha256"] == (
        "2565be45b9a13204583b6714a7d1b581cf29c157c78ac502d665649e4065b359")
    assert s5.EXTRAS["2069"]["rate_sha256"] == (
        "5eba74c1870e0635a3e316e143961e9f04e259675ddad00fd8653de28980644a")


def synthetic_files(tmp_path: Path, parent: str) -> list[Path]:
    """Minimal owner/projection fixture; no private source or target invocation."""
    texts = [
        "# unchanged C0 chemistry off",
        "# unchanged parent RF",
        "reaction_progress = R_elastic_O2",
        "reaction_progress = R_elastic_O",
        "reaction_progress = R_ion_O2",
        "reaction_progress = R_EI401",
        f"reaction_progress = R_EI{parent}",
        "\n".join([
            "type = ElectronImpactRateMaterial",
            "rate_table_file = 'private_rates/EI-407_O2_X.txt'",
            "reaction_progress = R_EI407",
            "variable = w_O2s",
            "property_name = S_O2_implicit_EI407",
            "expression = '-0.977*R'",
            "variable = log_energy",
        ]),
        "\n".join([
            "type = ElectronImpactRateMaterial",
            "rate_table_file = 'private_rates/EI-2069_O2_a1Delta.txt'",
            "reaction_progress = R_EI2069",
            "variable = w_O2s",
            "variable = w_O",
            "variable = log_energy",
            "expression = '-5.02*R'",
            "expression = '-0.032*R'",
            "expression = '0.032*R'",
        ]),
        "\n".join([
            "property_name = R_H25",
            "variable = log_nop",
            "variable = log_ni",
            "variable = w_O",
            "variable = p",
            "expression = '1.204428152e7*(300.0/tg)^0.4*cp*c2'",
            "expression = '-0.032*R'",
        ]),
    ]
    paths = []
    for idx, text in enumerate(texts):
        file = tmp_path / f"{idx}.i"
        file.write_text(text + "\n")
        paths.append(file)
    return paths


@pytest.mark.parametrize("case,parent", sorted(s6.CASE_PARENTS.items()))
def test_8_reaction_owners_and_all_three_inputs(case, parent, tmp_path):
    inputs = synthetic_files(tmp_path, parent)
    s6.validate_inventory(inputs, case)
    assert len(inputs) == 10
    assert len({p.read_text() for p in inputs}) == 10


@pytest.mark.parametrize("case,parent", sorted(s6.CASE_PARENTS.items()))
def test_missing_or_unapproved_channel_fails_closed(case, parent, tmp_path):
    inputs = synthetic_files(tmp_path, parent)
    s6.validate_inventory(inputs, case)
    inputs[8].write_text(inputs[8].read_text().replace("R_EI2069", "R_EI2259"))
    with pytest.raises(ValueError, match="ownership"):
        s6.validate_inventory(inputs, case)
    inputs = synthetic_files(tmp_path, parent)
    inputs[9].write_text(inputs[9].read_text() + "variable = log_ne\n")
    with pytest.raises(ValueError, match="may not directly mutate electrons"):
        s6.validate_inventory(inputs, case)
    inputs = synthetic_files(tmp_path, parent)
    with pytest.raises(ValueError, match="exactly 7 parent plus 3"):
        s6.validate_inventory(inputs[:-1], case)


def test_s6_governed_one_shot_two_native_jobs():
    path = Path(".github/workflows/issue477-s6-combined-407-2069-h25-once.yml")
    source = path.read_text()
    assert "paths: [.github/workflows/issue477-s6-combined-407-2069-h25-once.yml]" in source
    assert "branches: [main]" in source
    assert source.count("max-parallel: 2") == 1
    assert "case: [S6-417-407-2069-H25, S6-941-407-2069-H25]" in source
    assert "prepare_s6_combined_consumers.py" in source
    assert f'test "{chr(36)}{{#INPUTS[@]}}" -eq 10' in source
    assert "issue477_s6_combined_consumers" in source
    assert "workflow_dispatch" not in source
