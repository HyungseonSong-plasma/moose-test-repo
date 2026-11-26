"""Issue 518 artifact upload retries and receipt checks; no Native/P3 execution."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/issue402-canonical-s6-d-once.yml"
RECEIPT = ROOT / "ci/guards/verify_issue518_artifact_receipt.py"


def test_independent_retries_only_upload_artifacts_not_solver():
    text = WORKFLOW.read_text()
    assert "  push:\n    branches: [main]\n" in text
    assert "paths: [.github/workflows/issue402-canonical-s6-d-once.yml]" in text
    assert "workflow_dispatch" not in text
    assert text.count("run_canonical_s6_p3_once.py") == 1
    assert text.count("actions/upload-artifact@v4") == 3
    assert text.count("if-no-files-found: error") == 3
    assert "actions: read" in text
    assert "GITHUB_STEP_SUMMARY" in text
    assert "receipt_1.outcome != 'success'" in text
    assert "receipt_2.outcome != 'success'" in text
    assert "steps.receipt_3.outcome" in text
    for retry in ("r1", "r2", "r3"):
        assert "-D-${{ github.sha }}-" + retry in text
    assert "Verify P3 evidence receipt (attempt 3)" in text
    assert "if: always()" in text
    assert "No files found" not in text


def test_receipt_matching_is_scoped_to_name_id_and_expiry():
    tree = ast.parse(RECEIPT.read_text())
    f = next(n for n in tree.body
             if isinstance(n, ast.FunctionDef) and n.name == "has_receipt")
    scope = {}
    exec(compile(ast.Module(body=[f], type_ignores=[]), str(RECEIPT), "exec"), scope)
    match = scope["has_receipt"]
    doc = {"artifacts": [
        {"id": 123, "name": "wanted", "expired": True},
        {"id": 124, "name": "wanted", "expired": False},
        {"id": 125, "name": "other", "expired": False},
    ]}
    assert match(doc, 124, "wanted")
    assert not match(doc, 123, "wanted")
    assert not match(doc, 125, "wanted")
    assert not match(doc, 126, "wanted")
