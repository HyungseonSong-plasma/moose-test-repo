"""#774 latest-main Thermal/Heavy retirement exact-source P0 and negatives."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "ci/guards/issue774_main_retirement.py"
spec = importlib.util.spec_from_file_location("issue774_main_retirement", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_current_registered_owner_inventory_and_archived_evidence():
    head = subprocess.check_output(
        ["git", "-C", str(module.ROOT), "rev-parse", "HEAD"],
        text=True).strip()
    receipt = module.audit(module.ROOT, head)
    assert receipt["current_newonly"]["source_files"] == 7
    assert receipt["current_newonly"]["registered_factory_types"] == 12
    assert len(receipt["historical_original_blobs"]) == 12
    assert len(receipt["code4_historical_references"]) == 4
    assert len(receipt["code4_nonexecuting_description_references"]) == 2
    assert receipt["code4_exact_tracked_text_inventory"]
    assert receipt["reviewed_code3_assertions"] == {path: 1 for path in module.CODE3_ASSERTIONS}
    assert receipt["current_active_retired_symbol_references"] == []
    assert receipt["p3_p4_scientific_parity"] == "NOT_EVALUATED"
    assert receipt["global_external_callers_zero"] == "NOT_ATTESTED"


def test_historical_archive_mutations_and_active_surface_fail_closed():
    module.self_test()

def test_fdeg_post_cut_accepts_live_capture_rejects_retired_targets():
    import pytest

    stem = "fdeg_retirement_evidence.py --mode capture --target "
    good = ("python ci/guards/issue774_main_retirement.py\\n"
            "python ci/guards/" + stem + "PhysicsFVLogMolarElectronReactionSource")
    module.verify_post_cut_fdeg_capture(good)
    for retired in module.FACTORIES:
        with pytest.raises(
                ValueError,
                match="FDEG_POST_CUT_CI_STILL_CAPTURES_REMOVED_CPP"):
            module.verify_post_cut_fdeg_capture(good + "\\npython " + stem + retired)
    with pytest.raises(
            ValueError,
            match="FDEG_POST_CUT_CI_STILL_CAPTURES_REMOVED_CPP"):
        module.verify_post_cut_fdeg_capture("python " + stem + "PhysicsFVLogMolarElectronReactionSource")
