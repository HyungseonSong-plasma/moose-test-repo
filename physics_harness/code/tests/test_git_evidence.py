"""Shared evidence primitives and compatibility regression tests (no network)."""
from io import BytesIO
from zipfile import ZipFile
import importlib

import pytest

from libs.git_evidence import (
    ActionsReadSource, GitHubActionsRestReader, read_actions_archive_members,
)
from libs.git_evidence import actions
from physics_harness.code.verification import naming_actions, generated_input_actions


def test_legacy_and_generated_input_share_exact_objects():
    for name in ("ActionsReadSource", "GitHubActionsRestReader",
                 "read_actions_archive_members"):
        canonical = globals()[name]
        assert getattr(naming_actions, name) is canonical
        assert getattr(generated_input_actions, name) is canonical


def test_shared_library_has_no_domain_imports():
    for name in ("libs.git_evidence.actions", "libs.git_evidence.artifacts"):
        module = importlib.import_module(name)
        assert not any(getattr(value, "__module__", "").startswith("physics_harness")
                       for value in vars(module).values())


def test_bounded_multi_page_read(monkeypatch):
    reader = GitHubActionsRestReader()
    pages = []
    def read(endpoint):
        pages.append(endpoint)
        records = [{"id": i} for i in range(100)] if len(pages) == 1 else [{"id": 100}]
        return {"total_count": 101, "jobs": records}
    monkeypatch.setattr(reader, "_json", read)
    assert len(reader.jobs("owner/repo", 1)) == 101
    assert pages[0].endswith("jobs?per_page=100&page=1")
    assert pages[1].endswith("jobs?per_page=100&page=2")


def test_artifact_redirect_strips_bearer_and_rejects_http(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def geturl(self):
            return "https://artifact.example.invalid/signed"
        def read(self, limit):
            return b"zip"
    class Opener:
        def __init__(self, redirect):
            self.redirect = redirect
        def open(self, request, timeout):
            assert request.get_header("Authorization") == "Bearer fixture-token"
            safe = self.redirect.redirect_request(
                request, None, 302, "", {}, "https://artifact.example.invalid/signed")
            assert safe.get_header("Authorization") is None
            with pytest.raises(ValueError, match="UNEXPECTED_GITHUB_REDIRECT"):
                self.redirect.redirect_request(
                    request, None, 302, "", {}, "http://artifact.example.invalid")
            return Response()
    monkeypatch.setattr(actions, "build_opener", Opener)
    assert GitHubActionsRestReader("fixture-token").archive("owner/repo", 1) == b"zip"


def test_zip_exact_members_and_ambiguous_suffix():
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr("a/report.xml", b"a")
        archive.writestr("b/report.xml", b"b")
    assert read_actions_archive_members(data.getvalue(), entries=("a/report.xml",)) == {
        "a/report.xml": b"a"
    }
    with pytest.raises(ValueError, match="ARCHIVE_MEMBER_AMBIGUOUS_OR_MISSING"):
        read_actions_archive_members(data.getvalue(), suffix=".xml")
