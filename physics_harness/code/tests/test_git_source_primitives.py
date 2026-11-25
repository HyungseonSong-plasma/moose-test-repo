"""Pure Git evidence helpers and real-checkout compatibility."""
import subprocess

import pytest

from libs.command_execution.git import run_git
from libs.git_evidence import git_blob_sha1, parse_long_tree_row, regular_tree_paths
from physics_harness.code.diagnostics import GitSourceProvider


def test_exact_blob_identity_and_dirty_checkout(git_factory):
    original = b"tracked\x00bytes\n"
    root, head = git_factory({"data.bin": original})
    sha = run_git(root, "rev-parse", "HEAD:data.bin").decode().strip()
    assert git_blob_sha1(original) == sha
    (root / "data.bin").write_bytes(b"dirty")
    assert GitSourceProvider(root).read_at_revision(head, "data.bin").content == original


def test_long_tree_preserves_gitlink_and_path_spelling():
    sha = "a" * 40
    assert parse_long_tree_row(
        f"160000 commit {sha} -\tchild module".encode()
    ) == ("160000", "commit", sha, "-", "child module")
    assert parse_long_tree_row(
        f"100644 blob {sha} 12\tspace\nfile.py".encode()
    ) == ("100644", "blob", sha, "12", "space\nfile.py")


def test_regular_tree_preserves_order_and_excludes_nonregular():
    sha = "a" * 40
    rows = [
        f"100755 blob {sha}\tz.py",
        f"120000 blob {sha}\tlink.py",
        f"160000 commit {sha}\tchild",
        f"100644 blob {sha}\ta space.py",
    ]
    assert list(regular_tree_paths(("\0".join(rows) + "\0").encode())) == [
        "z.py", "a space.py"
    ]
    with pytest.raises(ValueError):
        list(regular_tree_paths(b"malformed\0"))
    with pytest.raises(UnicodeDecodeError):
        list(regular_tree_paths(f"100644 blob {sha}\t".encode() + b"\xff\0"))


def test_local_git_runner_retains_failure_and_timeout_contract(git_factory, monkeypatch):
    root, _ = git_factory({"a.py": "pass\n"})
    with pytest.raises(ValueError, match="GIT_SOURCE_UNAVAILABLE"):
        run_git(root, "cat-file", "-t", "0" * 40)
    def timed_out(*args, **kwargs):
        assert kwargs["timeout"] == 30
        raise subprocess.TimeoutExpired(args[0], 30)
    monkeypatch.setattr(subprocess, "run", timed_out)
    with pytest.raises(subprocess.TimeoutExpired):
        GitSourceProvider(root)._git("rev-parse", "HEAD")
