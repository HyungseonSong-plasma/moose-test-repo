"""G8 Native old/new Poisson pilot checks: thresholds fixed before execution."""
from pathlib import Path
import importlib.util
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ci/guards"))
spec=importlib.util.spec_from_file_location(
    "issue652_g8_matched_native_pilot",
    ROOT/"ci/guards/issue652_g8_matched_native_pilot.py")
assert spec and spec.loader
g8=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g8)


def test_same_exodus_fields_have_zero_normalized_error():
    np=pytest.importorskip("numpy")
    x=np.array([[1.0,2.0],[-1.5,0]])
    a=g8.normalized_rms(x,x.copy())
    assert a["relative_rms"]==0.0 and a["relative_max"]==0.0
    b=g8.normalized_rms(x,x*1.002)
    assert b["relative_rms"]>0.0
    with pytest.raises(g8.MatchedHold):
        g8.normalized_rms(x,np.array([1.0,2.0]))


def test_nonfinite_and_dimension_drift_fail_closed():
    np=pytest.importorskip("numpy")
    with pytest.raises(g8.MatchedHold):
        g8.normalized_rms(np.array([float("nan")]),np.array([1.0]))
    with pytest.raises(g8.MatchedHold):
        g8.normalized_rms(np.array([1.0]),np.array([1.0,2.0]))


def test_source_sha_and_physical_difference_are_only_poisson_handoff():
    assert g8.SOURCE_SHA=="26e84a4a33cf93d9e278a4f0b2d78c53cae2d6ce"
    assert g8.MAX_SECONDS_PER_ARM==900
    assert g8.REL_RMS_LIMIT=={
        "potential":1e-3,"electron_density":1e-3,"charge_density":1e-2,
    }
    assert g8.NA==pytest.approx(6.02214076e23)
    assert g8.ELEMENTARY_CHARGE==pytest.approx(1.602176634e-19)


def test_protected_native_requires_explicit_authorization(tmp_path):
    with pytest.raises(g8.MatchedHold,match="AUTHORIZATION"):
        g8.run(
            before_g5=tmp_path,after_g5=tmp_path,
            stage_receipt=tmp_path/"stage.json",build_manifest=tmp_path/"build.json",
            output=tmp_path/"receipt.json",cases=("417",),authorize=False)
    assert not (tmp_path/"receipt.json").exists()


def test_private_log_never_overwritten(tmp_path):
    log=tmp_path/"private_native.log"
    log.write_text("Existing native/private log")
    with pytest.raises(g8.MatchedHold,match="LOG_REUSE"):
        g8.execute_privately(
            ["false"],tmp_path,log,10)
    assert log.read_text()=="Existing native/private log"


def test_output_is_not_allowed_to_be_raw_exodus_or_private_input():
    code=(ROOT/"ci/guards/issue652_g8_matched_native_pilot.py").read_text()
    assert '"private_input_artifact": False' in code
    assert '"private_log_artifact": False' in code
    assert '"raw_exodus_artifact": False' in code
    assert '"P3_100us": "NOT_RUN"' in code
    assert '"P4": "NOT_RUN"' in code
    assert '"science": "SCIENCE_HOLD"' in code
    assert "secure_tmpfs_cleanup(private)" in code
    assert "read_hashed_rows()" in code
    assert "compare_exodus(" in code


def test_split_checkout_imports_frozen_native_code_when_source_env_defined():
    import os
    expected=os.environ.get("G8_NATIVE_SOURCE_ROOT")
    if expected:
        assert g8.g6.ROOT.resolve()==Path(expected).resolve()
        assert g8.g6.__file__.startswith(str(Path(expected).resolve()))


@pytest.mark.parametrize("phase", sorted(g8.PREFLIGHT_PHASES))
def test_preflight_phase_reports_fixed_code_without_exception_text(phase, capsys):
    with pytest.raises(g8.MatchedHold, match="G8_PREFLIGHT_"+phase+"_HOLD") as err:
        with g8.preflight_phase(phase):
            raise ValueError("SENSITIVE_EXAMPLE_SENTINEL")
    assert str(err.value) == "G8_PREFLIGHT_"+phase+"_HOLD"
    assert "SENSITIVE_EXAMPLE_SENTINEL" not in capsys.readouterr().out


def test_preflight_success_reports_only_fixed_phase(capsys):
    with g8.preflight_phase("SHARED_ELF"):
        pass
    assert capsys.readouterr().out.strip() == "G8_PREFLIGHT_SHARED_ELF_PASS"


def _synthetic_exodus(path, centering="elemental", omit=None, electron_shift=0.0, large=False):
    import numpy as np
    from netCDF4 import Dataset
    if large:
        # Match the observed production support counts without using private mesh bytes.
        x, y = np.meshgrid(np.linspace(0, 1, 53), np.linspace(0, 1, 19))
        x, y = x.ravel(), y.ravel()
        first, second = [], []
        for j in range(18):
            for i in range(52):
                a = 53*j+i+1
                first.append([a, a+1, a+53])
                second.append([a+1, a+54, a+53])
        dropped = {j*52+i for j in (1,2) for i in range(1,38)}
        conn = first + [cell for i, cell in enumerate(second) if i not in dropped]
        assert len(x) == 1007 and len(conn) == 1798 and len(np.unique(conn)) == 1007
    else:
        x, y, conn = [0,1,1,0], [0,0,1,1], [[1,2,3],[1,3,4]]
    n, m = len(x), len(conn)
    with Dataset(path, "w") as ds:
        for name, size in (("time_step", 4), ("num_nodes", n), ("num_el_blk", 1),
                           ("num_el_in_blk1", m), ("num_nod_per_el1", 3), ("len_name", 33)):
            ds.createDimension(name, size)
        def put(name, dtype, dims, data):
            ds.createVariable(name, dtype, dims)[:] = data
        def names(name, dim, values):
            ds.createDimension(dim, len(values))
            # Explicit byte rows avoid library-version-dependent stringtochar.
            rows = np.zeros((len(values), 33), dtype="S1")
            for i, value in enumerate(values):
                rows[i, :len(value)] = np.frombuffer(value.encode("ascii"), dtype="S1")
            put(name, "S1", (dim, "len_name"), rows)
        put("time_whole", "f8", ("time_step",), [0, 1e-9, 2e-9, 3e-9])
        put("coordx", "f8", ("num_nodes",), x)
        put("coordy", "f8", ("num_nodes",), y)
        put("eb_names", "S1", ("num_el_blk", "len_name"),
            np.array([list(b"plasma".decode()) + [""]*27], dtype="S1"))
        put("connect1", "i4", ("num_el_in_blk1", "num_nod_per_el1"), conn)
        ds.variables["connect1"].elem_type = "TRI3"
        logs = [key for key in g8.REQUIRED_LOGS if key != omit]
        nodal = ["potential"] + (logs if centering == "nodal" else
                                  [key for key in logs if key == "log_e"] if centering == "mixed" else [])
        names("name_nod_var", "num_nod_var", nodal)
        for i, key in enumerate(nodal, 1):
            values = np.full((4,n), electron_shift if key == "log_e" else 0.0)
            put("vals_nod_var"+str(i), "f8", ("time_step","num_nodes"), values)
        if centering in ("elemental", "mixed"):
            if centering == "mixed":
                logs = [key for key in logs if key != "log_e"]
            names("name_elem_var", "num_elem_var", logs)
            put("elem_var_tab", "i4", ("num_el_blk","num_elem_var"), np.ones((1,len(logs)),dtype=int))
            for i, key in enumerate(logs, 1):
                values = np.full((4,m), electron_shift if key == "log_e" else 0.0)
                put("vals_elem_var"+str(i)+"eb1", "f8", ("time_step","num_el_in_blk1"), values)


@pytest.mark.parametrize("centering", ["nodal", "elemental"])
def test_real_exodus_same_support_parity(tmp_path, centering):
    a, b = tmp_path/"a.e", tmp_path/"b.e"
    _synthetic_exodus(a, centering)
    _synthetic_exodus(b, centering)
    result = g8.compare_exodus(a, b)
    assert result["fieldwise_3ns_pilot"] == "PASS_PROVISIONAL_3NS"
    assert result["field_centering"]["electron_density"] == centering
    assert result["fields"]["charge_density"]["relative_rms"] == 0


def test_elemental_difference_rejected_without_tolerance_change(tmp_path):
    a, b = tmp_path/"a.e", tmp_path/"b.e"
    _synthetic_exodus(a)
    _synthetic_exodus(b, electron_shift=0.1)
    result = g8.compare_exodus(a, b)
    assert result["fieldwise_3ns_pilot"] == "HOLD_NUMERICAL_DIFFERENCE"


def test_different_centering_rejected(tmp_path):
    a, b = tmp_path/"a.e", tmp_path/"b.e"
    _synthetic_exodus(a, "nodal")
    _synthetic_exodus(b, "elemental")
    with pytest.raises(g8.MatchedHold, match="CENTERING_MISMATCH"):
        g8.compare_exodus(a,b)


def test_missing_field_does_not_erase_native_receipts_or_block_next_comparison(tmp_path):
    a, b = tmp_path/"a.e", tmp_path/"b.e"
    _synthetic_exodus(a, omit="log_Om")
    _synthetic_exodus(b)
    record = {"old": {"P3_rc": 0}, "new": {"P3_rc": 0}}
    g8.record_comparison(record, a, b)
    assert record["old"]["P3_rc"] == record["new"]["P3_rc"] == 0
    assert record["comparison"]["fieldwise_3ns_pilot"] == "HOLD_OBSERVATION"
    assert record["observation"]["old"]["required_field_counts"]["log_Om"] == {"nodal":0,"elemental":0}
    assert record["observation"]["new"]["density_centering"] == "elemental"
    other = {}
    g8.record_comparison(other, b, b)
    assert other["comparison"]["fieldwise_3ns_pilot"] == "PASS_PROVISIONAL_3NS"


def test_observation_exception_does_not_leak_private_text(monkeypatch):
    def fail(*args):
        raise ValueError("PRIVATE_NAME_SENTINEL")
    monkeypatch.setattr(g8, "compare_exodus", fail)
    record = {}
    g8.record_comparison(record, Path("old"), Path("new"))
    assert record["comparison"]["blocker_code"] == "P3_OBSERVATION_UNCLASSIFIED_HOLD"
    assert "PRIVATE_NAME_SENTINEL" not in str(record)


def test_rz_exp_log_analytic_triangle():
    import numpy as np
    # r=x, log_e=x on the unit right triangle. The exact weighted mean
    # of exp(x) is 6*(3-exp(1)), not exp(mean(log_e)) or a nodal average.
    value, volume, error = g8.rz_electron_cell_average(
        np.array([[0.,1.,0.]]), [0.,1.,0.], [0.,0.,1.], [[0,1,2]], "TRI3")
    assert value[0,0]/g8.NA == pytest.approx(6*(3-np.e), rel=1e-12)
    assert volume[0] == pytest.approx(np.pi/3)
    assert error <= g8.RZ_QUADRATURE_REL_LIMIT


def test_rz_constant_quad_and_invalid_topology():
    import numpy as np
    args = (np.zeros((1,4)), [0.,1.,1.,0.], [0.,0.,1.,1.], [[0,1,2,3]])
    value, volume, _ = g8.rz_electron_cell_average(*args, "QUAD4")
    assert value[0,0] == pytest.approx(g8.NA)
    assert volume[0] == pytest.approx(np.pi)
    with pytest.raises(g8.MatchedHold, match="UNSUPPORTED_FIRST_ORDER_TOPOLOGY"):
        g8.rz_electron_cell_average(*args, "QUAD8")


def test_actual_support_counts_mixed_exodus(tmp_path):
    a, b = tmp_path/"a.e", tmp_path/"b.e"
    _synthetic_exodus(a, "mixed", large=True)
    _synthetic_exodus(b, "mixed", large=True)
    obs = {}
    r = g8.compare_exodus(a,b,obs)
    assert r["matched_nodes"] == 1007 and r["matched_plasma_elements"] == 1798
    assert r["fieldwise_3ns_pilot"] == "PASS_PROVISIONAL_3NS"
    assert r["field_centering"] == {"potential":"nodal", "electron_density":"nodal", "charge_density":"RZ_cell_average"}
    assert r["fields"]["charge_density"]["relative_rms"] == 0
    assert obs["old"]["charge_reconstruction"]["max_relative_quadrature_error"] <= g8.RZ_QUADRATURE_REL_LIMIT


def test_mixed_exodus_electron_difference(tmp_path):
    a, b = tmp_path/"a.e", tmp_path/"b.e"
    _synthetic_exodus(a, "mixed")
    _synthetic_exodus(b, "mixed", electron_shift=0.1)
    r = g8.compare_exodus(a,b)
    assert r["fieldwise_3ns_pilot"] == "HOLD_NUMERICAL_DIFFERENCE"
    assert r["fields"]["electron_density"]["relative_rms"] > g8.REL_RMS_LIMIT["electron_density"]
    assert r["fields"]["charge_density"]["relative_rms"] > g8.REL_RMS_LIMIT["charge_density"]


def test_mixed_exodus_missing_ion_still_fails_closed(tmp_path):
    a, b = tmp_path/"a.e", tmp_path/"b.e"
    _synthetic_exodus(a, "mixed", omit="log_Om")
    _synthetic_exodus(b, "mixed")
    receipt = {}
    g8.record_comparison(receipt, a,b)
    assert receipt["comparison"]["fieldwise_3ns_pilot"] == "HOLD_OBSERVATION"
    assert receipt["observation"]["old"]["blocker_code"] == "P3_REQUIRED_LOG_FIELDS_MISSING_OR_MIXED_CENTERING"
