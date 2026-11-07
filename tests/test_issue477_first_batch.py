"""Issue 477 first-batch fail-closed independent chemistry inventory tests."""
from pathlib import Path

import pytest

from experiments.Issue477_electron_shape.prepare_first_batch import (
    CASES, PRIVATE, PROGRESS, verify_inventory, verify_private_rate,
)


def test_first_batch_is_three_cases_not_full_fourteen_or_nine():
    assert list(CASES) == ["S1", "S2-415", "S2-417"]
    assert CASES["S1"] == ("EI-02", "EI-17")
    assert CASES["S2-415"] == ("EI-02", "EI-17", "EI-415")
    assert CASES["S2-417"] == ("EI-02", "EI-17", "EI-417")
    assert set(PRIVATE) == {"EI-415", "EI-417"}
    assert len(set(PROGRESS.values())) == 4


@pytest.mark.parametrize("case", CASES)
def test_exact_progress_inventory_accepts_only_selected(tmp_path, case):
    files = []
    for index, channel in enumerate(CASES[case]):
        path = tmp_path / f"case_{index}.i"
        path.write_text(f"[FunctorMaterials]\n  [r]\n    reaction_progress = {PROGRESS[channel]}\n  []\n[]\n")
        files.append(path)
    verify_inventory(files, CASES[case])
    files[0].write_text(files[0].read_text() + "reaction_progress = R_unapproved\n")
    with pytest.raises(ValueError, match="Unexpected active"):
        verify_inventory(files, CASES[case])


def test_original_private_lookup_must_have_100_monotonic_positive_rows(tmp_path):
    path = tmp_path / "rate.txt"
    path.write_text("".join(f"{i + 1} {i / 100}\n" for i in range(100)))
    digest = verify_private_rate(path)
    assert len(digest) == 64
    with pytest.raises(ValueError, match="Wrong pinned"):
        verify_private_rate(path, "f" * 64)
    path.write_text("1 2\n2 4\n")
    with pytest.raises(ValueError, match="100-row"):
        verify_private_rate(path)
