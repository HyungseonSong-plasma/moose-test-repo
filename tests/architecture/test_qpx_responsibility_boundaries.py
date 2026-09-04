from __future__ import annotations

import ast
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QPX = ROOT / "qpx_harness"


def _python_files(root: Path):
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_canonical_responsibility_packages_exist():
    expected = {
        "specification", "ontology", "planning", "execution", "adapters",
        "observation", "analysis", "reasoning", "validation", "provenance",
        "domains", "application", "cli",
    }
    actual = {path.name for path in QPX.iterdir() if path.is_dir()}
    assert expected <= actual


def test_domains_do_not_import_z3_cli_or_moose_adapter():
    forbidden_prefixes = (
        "z3",
        "qpx_harness.reasoning.engines.z3",
        "qpx_harness.cli",
        "qpx_harness.adapters.moose",
    )
    for path in _python_files(QPX / "domains"):
        imports = _imports(path)
        assert not any(
            item == prefix or item.startswith(prefix + ".")
            for item in imports
            for prefix in forbidden_prefixes
        ), f"{path} has forbidden domain dependency: {sorted(imports)}"


def test_semantic_layers_do_not_import_moose_adapter():
    for package in ("specification", "ontology", "planning"):
        for path in _python_files(QPX / package):
            imports = _imports(path)
            assert not any(item.startswith("qpx_harness.adapters.moose") for item in imports), path


def test_new_canonical_code_does_not_import_legacy_cpp_or_diagnose():
    for package in (
        "specification", "ontology", "planning", "execution", "adapters",
        "observation", "reasoning", "domains",
    ):
        for path in _python_files(QPX / package):
            imports = _imports(path)
            assert not any(item.startswith("qpx_harness.cpp") for item in imports), path
            assert not any(item.startswith("qpx_harness.diagnose") for item in imports), path


def test_root_recipes_is_bounded_compatibility_namespace():
    recipes = importlib.import_module("recipes")
    assert recipes.COMPATIBILITY_ONLY is True
    assert recipes.SEMANTIC_AUTHORITY_RETIRED is True
    assert recipes.NEW_CALLERS_FORBIDDEN is True
    assert isinstance(recipes.REMOVAL_CONDITION, str)
    assert recipes.REMOVAL_CONDITION.strip()


def test_canonical_capabilities_do_not_import_root_recipes():
    canonical_packages = (
        "specification",
        "ontology",
        "planning",
        "execution",
        "adapters",
        "observation",
        "reasoning",
        "domains",
    )
    for package in canonical_packages:
        for path in _python_files(QPX / package):
            imports = _imports(path)
            assert not any(
                item == "recipes" or item.startswith("recipes.")
                for item in imports
            ), f"{path} imports retired recipe authority: {sorted(imports)}"

    gateway_imports = _imports(QPX / "application" / "gateway.py")
    assert not any(
        item == "recipes" or item.startswith("recipes.")
        for item in gateway_imports
    )
    assert not any(
        item.startswith("qpx_harness.application.protocols")
        for item in gateway_imports
    )


def test_no_separate_qpx_run_executable():
    assert not (ROOT / "qpx-run").exists()
    assert not (ROOT / "bin" / "qpx-run").exists()
    assert (ROOT / "bin" / "qpx.py").is_file()


def test_root_qpx_is_bounded_launcher():
    launcher = (ROOT / "qpx").read_text(encoding="utf-8")
    assert len(launcher.splitlines()) <= 20
    assert "bin/qpx.py" in launcher or "bin/qpx" in launcher
