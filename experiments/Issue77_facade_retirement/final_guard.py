#!/usr/bin/env python3
"""P0 guard for Issue #77 compatibility-facade retirement."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import evidence, execution
from qpx_harness.evidence import artifacts
from qpx_harness.execution import cases, runtime, workspace

RETIRED = {
    "qpx_harness.artifacts": ROOT / "qpx_harness" / "artifacts.py",
    "qpx_harness.cases": ROOT / "qpx_harness" / "cases.py",
    "qpx_harness.runtime": ROOT / "qpx_harness" / "runtime.py",
    "qpx_harness.workspace": ROOT / "qpx_harness" / "workspace.py",
}
CENSUS = ROOT / "docs" / "development" / "2026-09-02_issue77_facade_census.json"


def _absolute_from(path: Path, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    relative_to = path.relative_to(ROOT).with_suffix("")
    package = list(relative_to.parts[:-1])
    keep = len(package) - node.level + 1
    base = package[: max(keep, 0)]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _consumer_census() -> dict[str, list[str]]:
    hits = {module: [] for module in RETIRED}
    roots = (ROOT / "qpx_harness", ROOT / "recipes", ROOT / "bin", ROOT / "tests", ROOT / "tools")
    for source_root in roots:
        for path in sorted(source_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    module = _absolute_from(path, node)
                    imported.add(module)
                    imported.update(f"{module}.{alias.name}" for alias in node.names)
            for retired in RETIRED:
                if retired in imported:
                    hits[retired].append(str(path.relative_to(ROOT)))
    return hits


def main() -> int:
    for module, path in RETIRED.items():
        assert not path.exists(), f"retired facade exists: {module}"

    data = json.loads(CENSUS.read_text(encoding="utf-8"))
    assert data["issue"] == 77
    assert len(data["facades"]) == 4
    for row in data["facades"]:
        assert row["unique_behavior_removed"] == 0
        assert row["consumers_after"] == 0
        assert row["terminal_state"] == "RETIRED"
        assert not (ROOT / row["path"]).exists()
        assert (ROOT / row["canonical_owner"]).exists()

    hits = _consumer_census()
    assert not any(hits.values()), hits

    import qpx_harness

    assert "execution" in qpx_harness.__all__
    assert "evidence" in qpx_harness.__all__
    assert not ({"artifacts", "cases", "runtime", "workspace"} & set(qpx_harness.__all__))
    assert execution.run_qpx is runtime.run_qpx
    assert execution.stage_case is cases.stage_case
    assert execution.discover_manifests is workspace.discover_manifests
    assert evidence.write_json_bundle is artifacts.write_json_bundle
    print("Issue77 facade-retirement guard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
