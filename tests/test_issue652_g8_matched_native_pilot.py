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
