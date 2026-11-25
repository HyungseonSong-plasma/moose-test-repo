"""Exercise the real CLI subprocess, Git source provider and Diagnostics API."""
import json
from pathlib import Path
import subprocess
import sys

from physics_harness.code.diagnostics import (
    GitSourceProvider, ScanBudget, ScanRequest, run_scan,
)

ROOT = Path(__file__).resolve().parents[3]


def test_exact_scan_cli_reads_committed_source_and_preserves_evidence(tmp_path):
    source = tmp_path / "source"
    source.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args],
                                       stderr=subprocess.PIPE, text=True).strip()

    git("init", "-q")
    (source / "a.py").write_text("value = 1\n", encoding="utf-8")
    (source / "b.py").write_text("value = 2\n", encoding="utf-8")
    git("add", "a.py", "b.py")
    git("-c", "user.name=CLI test", "-c", "user.email=cli@example.invalid",
        "commit", "-qm", "fixture")
    sha = git("rev-parse", "HEAD")
    blob = git("rev-parse", "HEAD:a.py")
    # Invalid worktree text must not be used as source evidence.
    (source / "a.py").write_text("def invalid(\n", encoding="utf-8")
    request = ScanRequest(repository="owner/repo", revision=sha,
                          includes=("a.py",), collectors=("python_ast",),
                          budget=ScanBudget())
    api = run_scan(request, GitSourceProvider(source))
    assert api.status == "COMPLETE"
    assert api.verification.status == "VERIFIED"

    def invoke(revision, output, pattern="a.py", extra=()):
        return subprocess.run([
            sys.executable, "-m", "physics_harness.code.cli", "scan",
            "--repository", "owner/repo", "--root", str(source),
            "--revision", revision, "--include", pattern,
            "--collector", "python_ast", "--output", str(output), *extra,
        ], cwd=ROOT, capture_output=True, text=True, check=False, timeout=30)

    output = tmp_path / "receipt.json"
    result = invoke(sha, output)
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["source_revision"] == sha
    assert payload["status"] == api.status
    assert payload["verification"]["status"] == api.verification.status
    assert payload["receipt"]["scope_id"] == api.receipt.scope_id
    assert payload["graph"]["scope"]["revision"] == sha
    assert any(f["path"] == "a.py" and f["blob_sha"] == blob
               for f in payload["receipt"]["files"])
    original = output.read_bytes()
    assert invoke(sha, output).returncode == 2
    assert output.read_bytes() == original

    partial = tmp_path / "partial.json"
    result = invoke(sha, partial, "*.py", ("--max-files", "1"))
    assert result.returncode == 3, result.stderr
    partial_payload = json.loads(partial.read_text())
    assert partial_payload["status"] == "PARTIAL"
    assert partial_payload["verification"]["status"] == "UNVERIFIED"
    assert any(f["status"] == "SKIPPED_BUDGET"
               for f in partial_payload["receipt"]["files"])

    wrong = "0" * 40 if sha != "0" * 40 else "1" * 40
    invalid = tmp_path / "invalid.json"
    assert invoke(wrong, invalid).returncode == 2
    assert not invalid.exists()
