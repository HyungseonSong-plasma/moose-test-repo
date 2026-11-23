"""Guard the source-unit retirement *baseline*, not a deletion authorization."""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "reports/issue774/newonly_fvkernel_source_retirement_baseline_v0_1.json"
FACTORY = re.compile(
    r'register(?:AD)?MooseObject\s*\(\s*"PhysicsApp"\s*,\s*([A-Za-z_]\w*)\s*\)'
)


def test_all_twelve_cpp_source_units_and_fifteen_factories_accounted():
    report = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = report["source_files"]
    paths = {entry["path"] for entry in sources}
    assert len(sources) == len(paths) == 12
    assert paths == {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "physics_app/src/fvkernels").glob("*.C")
    }
    all_factories = set()
    for source in sources:
        cpp = ROOT / source["path"]
        header = ROOT / source["header_path"]
        assert cpp.is_file() and header.is_file()
        names = set(FACTORY.findall(cpp.read_text(encoding="utf-8")))
        assert names == set(source["registered_types"])
        assert all_factories.isdisjoint(names)
        all_factories.update(names)
    assert len(all_factories) == 15


def test_candidates_are_explicitly_provisional_and_never_delete_approved():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["schema"] == "fvkernel.newonly_source_retirement.v0.1"
    assert data["source_head"] == "9457191f4c0693ae886586edd961965867ccd5c0"
    assert data["runs"]["native_p2"] == 44366325757
    assert data["limitations"]["p05_ion_only"] is True
    assert data["limitations"]["full_unfiltered_factory_trace"] is False
    assert data["limitations"]["complete_poststage_rendered_inputs"] is False
    assert data["limitations"]["newonly_pr_unmerged"] is True
    assert data["deletion_approved"] is False
    statuses = [row["verdict"] for row in data["source_files"]]
    assert statuses.count("USED_IN_NEWONLY") == 4
    assert statuses.count("PROVISIONAL_DELETE_CANDIDATE") == 8
    assert all(not row["deletion_approved"] for row in data["source_files"])
    assert all(not row["consumer_scope_closed"] for row in data["source_files"])


def test_shared_legacy_transport_source_cannot_be_silently_retired():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    row = next(
        row for row in data["source_files"]
        if row["path"].endswith("/PhysicsFVLogMolarElectronTransport.C")
    )
    assert len(row["registered_types"]) == 4
    assert "PhysicsFVLogMolarElectronReactionSource" in row["registered_types"]
    assert row["verdict"] == "PROVISIONAL_DELETE_CANDIDATE"
    assert row["deletion_approved"] is False
