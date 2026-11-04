"""Synthetic-only tests for the nine-panel ratio writer; no private data."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from oxygen_mcs_nine_ratio_ci import ratio_rows


def generated_panels():
    return [
        {"reaction": rid,
         "energies": [float(i) for i in range(1, 25)],
         "mcs": [0.0, *([2.0] * 23)],
         "moose": [None, 4.0, *([None] * 22)]}
        for rid in (401, 411, 412, 417, 935, 941, 943, 2738, 2073)
    ]


def test_all_nine_reactions_have_twenty_four_cases_and_hold():
    rows = ratio_rows(generated_panels())
    assert len(rows) == 216
    assert all(r["moose_over_mcs"] == "2" for r in rows[1::24])
    assert all(r["moose_over_mcs"] == "" for r in rows[0::24])
    assert all(r["scientific_status"] == "REACTION_IDENTITY_HOLD"
               for r in rows if r["reaction"] in ("EI-411", "EI-412"))
    assert all(r["scientific_status"] == "PROCESS_IDENTITY_HOLD"
               for r in rows if r["reaction"] == "EI-2073")


def test_wrong_reaction_identity_fails_closed():
    panels = generated_panels()
    panels[0]["reaction"] = 999
    with pytest.raises(ValueError):
        ratio_rows(panels)


def test_missing_mcs_reference_fails_closed():
    panels = generated_panels()
    panels[0]["mcs"][1] = None
    with pytest.raises(ValueError):
        ratio_rows(panels)


def test_unavailable_model_not_misreported_as_zero():
    rows = ratio_rows(generated_panels())
    assert rows[2]["comparison_status"] == "OUTSIDE_LOOKUP_OR_FORMULA_DOMAIN"
    assert rows[2]["moose_over_mcs"] == ""
