"""Public EI candidate binds exact case-specific lookup paths, not science."""
from pathlib import Path
import sys

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
