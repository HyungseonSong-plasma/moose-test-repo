"""QPX-free guard for canonical package dependency direction."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "qpx_harness"
CANONICAL_PACKAGES = {
    "evidence", "analysis", "diagnose", "execution", "application", "cli",
    "validation", "inventory", "dmix",
}
TRANSITIONAL_EXCEPTIONS = {
    ("qpx_harness.evidence.transform", "qpx_harness.analysis.green_gauss"),
}
CHECKS = {"all", "evidence", "analysis", "execution", "presentation", "cycle"}


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return {name for name in imports if name.startswith("qpx_harness")}


def top_package(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "qpx_harness":
        return None
    return parts[1] if parts[1] in CANONICAL_PACKAGES else None


def violation(src: str, dst: str) -> tuple[str, str] | None:
    if (src, dst) in TRANSITIONAL_EXCEPTIONS:
        return None
    if src.startswith("qpx_harness.evidence") and dst.startswith("qpx_harness.diagnose"):
        return "evidence", "Evidence must not depend on Diagnose"
    if src.startswith("qpx_harness.evidence") and dst.startswith("qpx_harness.analysis"):
        return "evidence", "Evidence must not depend on Analysis except documented compatibility facade"
    if src.startswith("qpx_harness.analysis") and (
        dst.startswith("qpx_harness.cli") or dst.startswith("qpx_harness.validation")
    ):
        return "analysis", "Analysis must not depend on CLI/Validation"
    if src.startswith("qpx_harness.execution") and (
        dst.startswith("qpx_harness.inventory") or dst.startswith("qpx_harness.dmix")
    ):
        return "execution", "Execution must not depend on domain science"
    if not src.startswith("qpx_harness.cli") and dst.startswith("qpx_harness.cli"):
        return "presentation", "Production subsystems must not depend on CLI"
    if not src.startswith("qpx_harness.validation") and dst.startswith("qpx_harness.validation"):
        return "presentation", "Production subsystems must not depend on Validation"
    return None


def find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        if node in visiting:
            idx = stack.index(node)
            return stack[idx:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for target in sorted(graph.get(node, ())):
            cycle = dfs(target)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in sorted(graph):
        cycle = dfs(node)
        if cycle:
            return cycle
    return None


def audit() -> tuple[list[tuple[str, str]], list[str] | None]:
    violations: list[tuple[str, str]] = []
    graph: dict[str, set[str]] = {name: set() for name in CANONICAL_PACKAGES}
    for path in sorted(PKG.rglob("*.py")):
        src = module_name(path)
        src_pkg = top_package(src)
        for dst in sorted(imported_modules(path)):
            item = violation(src, dst)
            if item:
                category, why = item
                violations.append((category, f"{src} -> {dst}: {why}"))
            if (src, dst) not in TRANSITIONAL_EXCEPTIONS:
                dst_pkg = top_package(dst)
                if src_pkg and dst_pkg and src_pkg != dst_pkg:
                    graph[src_pkg].add(dst_pkg)
    return violations, find_cycle(graph)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx-dependency-guard")
    parser.add_argument("--check", choices=sorted(CHECKS), default="all")
    args = parser.parse_args(argv)
    violations, cycle = audit()
    failures: list[str] = []
    if args.check in {"all", "evidence", "analysis", "execution", "presentation"}:
        failures.extend(
            message for category, message in violations
            if args.check == "all" or category == args.check
        )
    if args.check in {"all", "cycle"} and cycle:
        failures.append("canonical package cycle: " + " -> ".join(cycle))
    marker = args.check.upper()
    if failures:
        print(f"ARCHITECTURE_DEPENDENCY_{marker}_FAIL")
        print("\n".join(failures))
        return 1
    print(f"ARCHITECTURE_DEPENDENCY_{marker}_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
