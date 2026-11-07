"""Issue477: SECOND_BASE + current Oxygen14 lookup channel guards."""
import json
from pathlib import Path

import pytest

from experiments.Issue477_electron_shape import prepare_second_base_sinks as m


def test_scope_is_exactly_approved_three_single_channel_variants():
    assert m.BASE == ("EI-02", "EI-17", "EI-415")
    assert set(m.EXTRAS) == {"S3-415-401", "S3-415-412", "S3-415-407"}
    assert set(v[0] for v in m.EXTRAS.values()) == {"EI-401", "EI-412", "EI-407"}
    assert m.EXPECTED_BASE_OWNERS == {"R_elastic_O2", "R_elastic_O", "R_ion_O2"}
    assert all(x not in m.EXTRAS for x in ("EI-2259", "EI-2058"))
    assert m.PARTICLE_DELTA == {"EI-401": -1, "EI-412": 0, "EI-407": 0}
    assert m.ENERGY_EV == {"EI-401": 0, "EI-412": 6.0, "EI-407": 0.977}
    assert m.SECOND_BASE_ACTION == 42315463971
    assert m.SECOND_BASE_ARTIFACT == 13559307611


def test_rate_grid_requires_exact_monotonic_positive_energy_100_rows(tmp_path):
    p = tmp_path / "rate.txt"
    p.write_text("\n".join(f"{i/10:.6f} {i*.1}" for i in range(1, 101)))
    assert len(m.rate_grid(p)) == 100
    p.write_text("\n".join(f"{i/10:.6f} {i*.1}" for i in range(1, 100)))
    with pytest.raises(ValueError, match="100"):
        m.rate_grid(p)
    p.write_text("\n".join(f"{i/10:.6f} {-1 if i == 15 else i*.1}" for i in range(1, 101)))
    with pytest.raises(ValueError, match="negative"):
        m.rate_grid(p)


@pytest.mark.parametrize("extra,progress,token", [
    ("EI-401", "R_EI401", "functor = S_electron_molar_EI401"),
    ("EI-412", "R_diss_O2", "expression = '-6*R'"),
    ("EI-407", "R_EI407", "expression = '-0.977*R'"),
])
def test_inventory_requires_single_extra_owner_with_expected_electron_energy_projection(tmp_path, extra, progress, token):
    sources = [
        "reaction_progress = R_elastic_O2\n",
        "reaction_progress = R_elastic_O\n",
        "reaction_progress = R_ion_O2\n",
    ]
    if extra == "EI-401":
        sources.append(f"reaction_progress = {progress}\nexpression = '-R'\n{token}\n")
    elif extra == "EI-412":
        sources.append(f"reaction_progress = {progress}\n{token}\nvariable = log_energy\n")
    else:
        sources.append(f"reaction_progress = {progress}\n{token}\nvariable = log_energy\nvariable = w_O2s\n")
    ps = []
    for i, s in enumerate(sources):
        p = tmp_path / f"{i}.i"
        p.write_text(s)
        ps.append(p)
    m.validate_case_inventory(ps, extra, progress)
    ps[-1].write_text(sources[-1].replace(f"reaction_progress = {progress}", "reaction_progress = R_ion_O2"))
    with pytest.raises(ValueError, match="ownership mismatch"):
        m.validate_case_inventory(ps, extra, progress)
