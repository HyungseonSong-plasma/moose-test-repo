"""Public EI candidate binds exact case-specific lookup paths, not science."""
from pathlib import Path
import sys
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import issue898_public_ei_candidate as public


def test_public_rate_data_and_both_case_sets():
    rates = public.load_rates(ROOT)
    assert len(rates) == 6
    assert len(public.REQUIRED["417"]) == len(public.REQUIRED["941"]) == 5
    assert public.REQUIRED["417"] ^ public.REQUIRED["941"] == {
        "EI-417_O2_X.txt", "EI-941_O_3P.txt"}


@pytest.mark.parametrize("case", public.CASES)
def test_rebind_only_expected_five_path_tokens(case):
    names = sorted(public.REQUIRED[case])
    source = {f"layer{i}.i": (
        f"[Materials]\n  rate_table_file = 'private_rates/{name}' # keep\n"
        "  type = PhysicsLookupTable1D\n[]\n").encode()
        for i, name in enumerate(names)}
    source["unrelated.i"] = b"other = 123\n"
    result = public.rebind(case, source)
    assert result == {n: raw.replace(b"private_rates/", b"../../physics_app/database/")
                      for n, raw in source.items()}
    bad = dict(source)
    bad["extra.i"] = source["layer0.i"]
    with pytest.raises(ValueError, match="EXACT_CASE_BINDING"):
        public.rebind(case, bad)
    bad = dict(source)
    del bad["layer0.i"]
    with pytest.raises(ValueError, match="EXACT_CASE_BINDING"):
        public.rebind(case, bad)
    bad = dict(source)
    bad["extra.i"] = b"other = private_rates/unknown.txt\n"
    with pytest.raises(ValueError, match="UNRECOGNIZED"):
        public.rebind(case, bad)



def test_canonical_transport_tables_and_disposable_path_only_cutover(tmp_path):
    tables = public.load_transport_tables(ROOT)
    source = tmp_path / "source"
    chem = source / public.CHEM
    (chem / "chemistry").mkdir(parents=True)
    legacy = source / "experiments/Issue91_real_qvt_r3/r3_e0"
    legacy.mkdir(parents=True)
    old_e = legacy / "electron_moments.txt"
    old_n = legacy / "transport_data.txt"
    old_e.write_bytes(tables["electron_moments.txt"])
    old_n.write_bytes(b"# historical header\n" + tables["neutral_transport.txt"])
    original = {"species": {"e": {"transport_coef": {
        "type": "lookup", "file": public.OLD_ELECTRON,
        "unit": "reduced", "bounds_policy": "clamp"}}}}
    mechanism = json.dumps(original).encode()
    raw = (b"  transport_data_file = '../Issue91_real_qvt_r3/r3_e0/"
           b"transport_data.txt' # keep\n  other = 123\n")
    changed, candidate, retired, counts = public.rebind_database(
        source, {"c0.i": raw}, mechanism, tables)
    assert changed["c0.i"] == (
        b"  transport_data_file = '../../physics_app/database/"
        b"neutral_transport.txt' # keep\n  other = 123\n")
    original["species"]["e"]["transport_coef"]["file"] = (
        "../../../physics_app/database/electron_moments.txt")
    assert json.loads(candidate) == original
    assert counts == {"electron_moments.txt": 1, "neutral_transport.txt": 1}
    assert retired == {old_e.relative_to(source), old_n.relative_to(source)}
    assert old_e.read_bytes() == tables["electron_moments.txt"]
    # Wrong underlying coefficient must not be silently replaced.
    old_n.write_bytes(b"species O2 0.05 O2\n")
    with pytest.raises(ValueError, match="SOURCE_DATA_MISMATCH"):
        public.rebind_database(source, {"c0.i": raw}, mechanism, tables)
    old_n.write_bytes(tables["neutral_transport.txt"])
    old_e.write_bytes(b"1 2 3\n" * 42)
    with pytest.raises(ValueError, match="SOURCE_DATA_MISMATCH"):
        public.rebind_database(source, {"c0.i": raw}, mechanism, tables)
    old_e.write_bytes(tables["electron_moments.txt"])
    with pytest.raises(ValueError, match="NEUTRAL_BINDING_MISSING"):
        public.rebind_database(source, {"c0.i": b"other = 123\n"}, mechanism, tables)
