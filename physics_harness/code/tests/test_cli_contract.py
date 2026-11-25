"""Regression tests for the domain-neutral CLI and adapter exit semantics."""
import argparse
from dataclasses import dataclass
import json
from types import MappingProxyType, SimpleNamespace

import pytest

from libs.command_execution import Command, dispatch, json_value, write_json
from physics_harness.code import cli, diagnostics


def test_strict_json():
    @dataclass(frozen=True)
    class Record:
        values: object

    assert json_value(Record(MappingProxyType({"a": (1, 2)}))) == {
        "values": {"a": [1, 2]}
    }
    assert json_value(frozenset({"z", "a"})) == ["a", "z"]
    for bad in (float("nan"), float("inf"), {1: "bad"}, object()):
        with pytest.raises(TypeError):
            json_value(bad)


def test_exclusive_receipt(tmp_path):
    path = tmp_path / "receipt.json"
    write_json({"value": 1}, path)
    with pytest.raises(FileExistsError):
        write_json({"value": 2}, path)
    assert json.loads(path.read_text()) == {"value": 1}
    bad = tmp_path / "invalid.json"
    with pytest.raises(TypeError):
        write_json(object(), bad)
    assert not bad.exists()


def test_dispatch_status_and_arguments(capsys):
    def configure(parser):
        parser.add_argument("--value", type=int, required=True)

    commands = {"example": Command("example", configure, lambda args: args.value)}
    assert dispatch("demo", commands, ["--help"]) == 0
    assert dispatch("demo", commands, ["unknown"]) == 2
    assert dispatch("demo", commands, ["example", "--val", "3"]) == 2
    assert dispatch("demo", commands, ["example", "--value", "3"]) == 3
    assert dispatch("demo", commands, ["example", "--value", "256"]) == 2
    assert dispatch("demo", {"bad": Command("bad", lambda _: None, lambda _: True)},
                    ["bad"]) == 2
    assert capsys.readouterr().err


@pytest.mark.parametrize("coverage,verification,expected", [
    ("COMPLETE", "VERIFIED", 0),
    ("PARTIAL", "UNVERIFIED", 3),
    ("COMPLETE", "UNVERIFIED", 3),
    ("COMPLETE", "FAILED", 4),
    ("COMPLETE", None, 2),
])
def test_scan_never_promotes_verification(monkeypatch, tmp_path, coverage,
                                          verification, expected):
    class Provider:
        def __init__(self, root):
            self.root = root

        def assert_head(self, revision):
            assert revision == "a" * 40

    def scan(request, provider):
        assert request.includes == ("src/*.py",)
        assert isinstance(provider, Provider)
        return SimpleNamespace(
            status=coverage, graph={"nodes": []},
            receipt={"completeness": coverage},
            verification=None if verification is None else
            SimpleNamespace(status=verification),
        )

    # A dataclass is required by the JSON contract, not a loose namespace.
    @dataclass
    class Verification:
        status: str

    def result(request, provider):
        output = scan(request, provider)
        if output.verification is not None:
            output.verification = Verification(verification)
        return output

    monkeypatch.setattr(diagnostics, "GitSourceProvider", Provider)
    monkeypatch.setattr(diagnostics, "run_scan", result)
    path = tmp_path / "receipt.json"
    args = ["scan", "--repository", "owner/repo", "--root", str(tmp_path),
            "--revision", "a" * 40, "--include", "src/*.py",
            "--collector", "python_ast", "--output", str(path)]
    assert cli.main(args) == expected
    if verification is None:
        assert not path.exists()
    else:
        payload = json.loads(path.read_text())
        assert payload["receipt"]["completeness"] == coverage
        assert payload["verification"]["status"] == verification
        assert payload["semantic_compatibility_proven"] is False
        assert payload["safe_delete_authorized"] is False
        assert cli.main(args) == 2
        assert json.loads(path.read_text()) == payload
