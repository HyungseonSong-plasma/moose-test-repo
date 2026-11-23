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
    assert receipt["current_newonly"]["source_files"] == 11
    assert receipt["current_newonly"]["registered_factory_types"] == 16
    assert len(receipt["historical_original_blobs"]) == 4
    assert receipt["current_active_retired_symbol_references"] == []
    assert receipt["p3_p4_scientific_parity"] == "NOT_EVALUATED"
    assert receipt["global_external_callers_zero"] == "NOT_ATTESTED"


def test_historical_archive_mutations_and_active_surface_fail_closed():
    module.self_test()
