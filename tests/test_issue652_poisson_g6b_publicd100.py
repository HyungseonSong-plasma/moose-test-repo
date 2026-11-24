"""#652 G6-B: original 100-row / 460-interval fail-closed contract tests."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import issue652_g6b_publicd100_stage as g6b  # noqa: E402

C0 = ROOT / "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i"


def test_original_public_d_lookup_has_pinned_100row_identity():
    blob = g6b.checked_bytes(
        g6b.SOURCE_100, g6b.PUBLIC_D_100_SHA256, "ORIGINAL_PUBLICD")
    receipt = g6b.lookup_contract(blob, 100)
    assert receipt == {"rows": 100, "columns": 3,
                       "sha256": g6b.PUBLIC_D_100_SHA256}


def test_lookup_rejects_wrong_row_count_columns_and_nonfinite():
    good = g6b.SOURCE_100.read_bytes()
    with pytest.raises(g6b.PublicD100Hold, match="CARDINALITY"):
        g6b.lookup_contract(b"\n".join(good.splitlines()[:42]) + b"\n", 100)
    short = good.splitlines()
    short[0] = b"\t".join(short[0].split()[:2])
    with pytest.raises(g6b.PublicD100Hold, match="COLUMNS"):
        g6b.lookup_contract(b"\n".join(short) + b"\n", 100)
    with pytest.raises(g6b.PublicD100Hold, match="NONPOSITIVE"):
        g6b.lookup_contract(good.replace(b"1.40991", b"nan", 1), 100)


def test_lookup_rejects_nonmonotonic_energy_grid():
    rows = g6b.SOURCE_100.read_bytes().splitlines()
    rows[1] = rows[0]
    with pytest.raises(g6b.PublicD100Hold, match="ENERGY_NOT_STRICTLY_INCREASING"):
        g6b.lookup_contract(b"\n".join(rows) + b"\n", 100)


def test_native_100us_time_contract_has_460_intervals():
    receipt = g6b.time_contract(C0.read_bytes())
    assert receipt["end_time_seconds"] == 1e-4
    assert receipt["time_points"] == 461
    assert receipt["intervals"] == 460
    assert sum(receipt["dt_counts"].values()) == 460
    assert receipt["checkpoint"] is True


@pytest.mark.parametrize("before,after,expected", [
    (b"  end_time = 1e-4\n", b"  end_time = 3e-9\n", "EXECUTIONER"),
    (b"  checkpoint = true\n", b"  checkpoint = false\n", "EXECUTIONER"),
    (b"  scheme = implicit-euler\n", b"  scheme = explicit-euler\n", "EXECUTIONER"),
])
def test_time_contract_rejects_runtime_regime_drift(before, after, expected):
    original = C0.read_bytes()
    assert original.count(before) == 1
    with pytest.raises(g6b.PublicD100Hold, match=expected):
        g6b.time_contract(original.replace(before, after))


def test_time_contract_rejects_shortened_three_ns_grid():
    before = C0.read_bytes()
    changed = before.replace(b"  end_time = 1e-4\n", b"  end_time = 3e-9\n")
    with pytest.raises(g6b.PublicD100Hold, match="100US_TIME_ENDPOINT"):
        g6b.time_contract(changed.replace(
            next(line for line in changed.splitlines(keepends=True)
                 if line.startswith(b"    time_sequence = '")),
            b"    time_sequence = '0 1e-9 2e-9 3e-9'\n"))


def test_no_unapproved_native_execution_or_automatic_parity_promotion():
    script = (ROOT / "ci/guards/issue652_g6b_publicd100_stage.py").read_text()
    assert '"P3_100us": "NOT_RUN"' in script
    assert '"science": "SCIENCE_HOLD"' in script
    assert '"main_merge": "NOT_AUTHORIZED"' in script
    assert "G6B_REFUSE_RECEIPT_OVERWRITE" in script
    assert "G6B_UNEXPECTED_JSON_EDIT" in script


def test_g6b_uses_canonical_g5_chemistry_c0_not_research_template():
    assert g6b.C0.endswith("__C0_chemistry_off.i")
    assert g6b.C0 != C0.name
