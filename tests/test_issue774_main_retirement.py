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

def test_retirement_workflow_requires_independent_checks_and_receipt():
    import pytest

    good = (module.ROOT / ".github/workflows/physics-code-ci.yml").read_text()
    module.verify_retirement_workflow(good)
    for before, after, error in (
        ("--self-test --expected-head", "--expected-head",
         "RETIRED_FACTORY_CHECKS_MISSING_OR_CHANGED"),
        ("ci.guards.issue817_code3_production_migration", "ci.guards.not_the_migration",
         "RETIRED_FACTORY_CHECKS_MISSING_OR_CHANGED"),
        ('head="$(git rev-parse HEAD)"', 'head="stale"',
         "RETIRED_FACTORY_CHECKS_MISSING_OR_CHANGED"),
        ("name: Verify retired Factory archives and consumer invariants",
         "name: Verify retired Factory archives and consumer invariants\n        if: false",
         "RETIRED_FACTORY_CHECKS_MISSING_OR_CHANGED"),
        ("name: Verify retired Factory archives and consumer invariants",
         "name: Verify retired Factory archives and consumer invariants\n        continue-on-error: true",
         "RETIRED_FACTORY_CHECKS_MISSING_OR_CHANGED"),
        ("name: Upload retired Factory evidence", "name: Removed upload",
         "RETIRED_FACTORY_RECEIPT_UPLOAD_MISSING_OR_CHANGED"),
    ):
        assert before in good
        with pytest.raises(ValueError, match=error):
            module.verify_retirement_workflow(good.replace(before, after, 1))
