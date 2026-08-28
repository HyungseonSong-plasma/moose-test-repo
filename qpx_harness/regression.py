"""Reusable manifest-driven QPX regression execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .preflight import validate_input_preflight, validate_temporal_manifest_preflight
from .runtime import resolve_executable, run_qpx, validate_executable
from .temporal import normalize_from_manifest

VALID_TEST_TYPES = {"canonical", "diagnostic"}


@dataclass(frozen=True)
class SuiteResult:
    requested_type: str
    total: int
    passed: int
    failed: tuple[str, ...]

    @property
    def returncode(self) -> int:
        return 1 if self.failed else 0


def harness_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_manifest(case_dir: Path) -> dict:
    manifest = case_dir / "test.json"
    if not manifest.is_file():
        raise SystemExit(f"missing test manifest: {manifest}")
    return json.loads(manifest.read_text())


def manifest_type(manifest: Path) -> str:
    cfg = json.loads(manifest.read_text())
    test_type = cfg.get("type", "canonical")
    if test_type not in VALID_TEST_TYPES:
        raise SystemExit(f"invalid test type {test_type!r} in {manifest}")
    return test_type


def discover_manifests(roots: Iterable[Path]) -> list[Path]:
    manifests: list[Path] = []
    seen: set[str] = set()
    for raw_root in roots:
        root = Path(raw_root).expanduser().resolve()
        if not root.exists():
            print(f"TEST_ROOT_SKIP: {root} (not found)")
            continue
        for manifest in sorted(root.rglob("test.json")):
            key = str(manifest.resolve())
            if key not in seen:
                seen.add(key)
                manifests.append(manifest.resolve())
    return manifests


def _case_result_key(case_dir: Path, namespace_root: Path | None) -> Path:
    if namespace_root is not None:
        try:
            return case_dir.relative_to(namespace_root.resolve())
        except ValueError:
            pass

    root = harness_root()
    default_tests = root / "tests"
    try:
        return case_dir.relative_to(default_tests)
    except ValueError:
        pass

    try:
        return case_dir.relative_to(root)
    except ValueError:
        return Path("__".join(case_dir.parts[-6:]))


def prepare_temporal_outputs(case_dir: Path, cfg: dict) -> None:
    for spec in cfg.get("temporal_csv", []):
        try:
            summary = normalize_from_manifest(case_dir, spec)
        except Exception as exc:
            print("TEMPORAL_ROWS: FAIL")
            raise SystemExit(f"temporal CSV normalization failed: {exc}") from exc

        print("TEMPORAL_ROWS: PASS")
        print(f"  SOURCE              : {spec['source']}")
        print(f"  PHYSICAL            : {spec['physical']}")
        print(f"  POLICY              : {summary['initial_row_policy']}")
        print(f"  SOURCE_ROWS         : {summary['source_rows']}")
        print(f"  INITIALIZATION_ROWS : {summary['initialization_rows']}")
        print(f"  PHYSICAL_ROWS       : {summary['physical_rows']}")


def run_case(
    case_dir: Path,
    *,
    results_root: Path | None = None,
    namespace_root: Path | None = None,
    executable: str | Path | None = None,
) -> int:
    case_dir = Path(case_dir).expanduser().resolve()
    cfg = load_manifest(case_dir)
    exe = resolve_executable(executable)
    validate_executable(exe)

    input_name = cfg["input"]
    checker = cfg.get("checker")
    checker_args = cfg.get("checker_args", [])
    test_type = cfg.get("type", "canonical")

    input_path = case_dir / input_name
    validate_input_preflight(input_path)
    validate_temporal_manifest_preflight(input_path, cfg)

    out_root = (results_root or (harness_root() / "results")).expanduser().resolve()
    result_dir = out_root / _case_result_key(case_dir, namespace_root)
    result_dir.mkdir(parents=True, exist_ok=True)
    log_path = result_dir / "run.log"

    print(f"CASE       : {case_dir}")
    print(f"TYPE       : {test_type}")
    print(f"EXECUTABLE : {exe}")
    print(f"INPUT      : {input_name}")
    print(f"LOG        : {log_path}")

    solve = run_qpx(exe, cwd=case_dir, input_name=input_name, log_path=log_path)
    if solve.returncode != 0:
        print("SOLVE      : FAIL")
        return solve.returncode or 1

    print("SOLVE      : PASS")
    prepare_temporal_outputs(case_dir, cfg)

    if not checker:
        print("CHECK      : SKIP")
        return 0

    check = subprocess.run([sys.executable, checker, *checker_args], cwd=case_dir)
    print("CHECK      :", "PASS" if check.returncode == 0 else "FAIL")
    return check.returncode


def run_suite(
    roots: Iterable[Path],
    *,
    requested_type: str = "canonical",
    results_root: Path | None = None,
    executable: str | Path | None = None,
) -> SuiteResult:
    if requested_type not in {"canonical", "diagnostic", "all"}:
        raise SystemExit(f"unsupported requested type: {requested_type}")

    roots = [Path(root).expanduser().resolve() for root in roots]
    manifests = discover_manifests(roots)
    selected: list[tuple[Path, str, Path]] = []

    for manifest in manifests:
        test_type = manifest_type(manifest)
        if requested_type == "all" or test_type == requested_type:
            owner_root = next(
                (root for root in roots if root == manifest or root in manifest.parents),
                manifest.parent,
            )
            selected.append((manifest, test_type, owner_root))

    if not selected:
        print(f"No {requested_type} tests found.")
        return SuiteResult(requested_type, 0, 0, ())

    failures: list[str] = []
    for manifest, test_type, owner_root in selected:
        case_dir = manifest.parent
        print("\n" + "=" * 80)
        print(case_dir, f"[{test_type}]")
        print("=" * 80)
        rc = run_case(
            case_dir,
            results_root=results_root,
            namespace_root=owner_root,
            executable=executable,
        )
        if rc != 0:
            failures.append(str(case_dir))

    total = len(selected)
    passed = total - len(failures)
    print("\n" + "=" * 80)
    print(f"TYPE: {requested_type}  TOTAL: {total}  PASS: {passed}  FAIL: {len(failures)}")
    if failures:
        print("Failed cases:")
        for case in failures:
            print(f"  - {case}")

    return SuiteResult(requested_type, total, passed, tuple(failures))


def cli_run_test(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir")
    parser.add_argument("--results-root")
    parser.add_argument("--namespace-root")
    parser.add_argument("--qpx")
    args = parser.parse_args(argv)
    return run_case(
        Path(args.case_dir),
        results_root=Path(args.results_root) if args.results_root else None,
        namespace_root=Path(args.namespace_root) if args.namespace_root else None,
        executable=args.qpx,
    )


def cli_run_all(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=("canonical", "diagnostic", "all"), default="canonical")
    parser.add_argument("--tests-root", action="append", default=[])
    parser.add_argument("--results-root")
    parser.add_argument("--qpx")
    args = parser.parse_args(argv)

    roots = [Path(p) for p in args.tests_root]
    if not roots:
        default = harness_root() / "tests"
        if not default.exists():
            raise SystemExit(
                f"default tests root does not exist: {default}; provide --tests-root"
            )
        roots = [default]

    result = run_suite(
        roots,
        requested_type=args.type,
        results_root=Path(args.results_root) if args.results_root else None,
        executable=args.qpx,
    )
    return result.returncode
