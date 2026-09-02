"""Canonical manifest-driven QPX regression orchestration."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from ..moose.preflight import validate_input_preflight, validate_temporal_manifest_preflight
from .reporting import ConsoleReporter, Reporter
from .runtime import TelemetryCallback, TelemetrySample, resolve_executable, run_command, run_qpx, validate_executable
from .status import ExecutionState, LivenessClassifier
from ..analysis.temporal import normalize_from_manifest
from .workspace import discover_manifests, load_manifest, manifest_type

StateCallback = Callable[[ExecutionState, float], None]


@dataclass(frozen=True)
class CaseSummary:
    name: str
    path: str
    status: ExecutionState
    wall_seconds: float


@dataclass(frozen=True)
class SuiteResult:
    requested_type: str
    total: int
    passed: int
    failed: tuple[str, ...]
    wall_seconds: float = 0.0
    cases: tuple[CaseSummary, ...] = ()

    @property
    def returncode(self) -> int:
        return 1 if self.failed else 0


def harness_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def _telemetry_adapter(
    state_callback: StateCallback | None,
    *,
    stall_after_seconds: float,
) -> TelemetryCallback | None:
    if state_callback is None:
        return None

    classifier = LivenessClassifier(stall_after_seconds=stall_after_seconds)

    def emit(sample: TelemetrySample) -> None:
        state_callback(classifier.classify(sample), sample.elapsed_seconds)

    return emit


def prepare_temporal_outputs(
    case_dir: Path,
    cfg: dict,
    *,
    reporter: Reporter,
) -> None:
    for spec in cfg.get("temporal_csv", []):
        try:
            summary = normalize_from_manifest(case_dir, spec)
        except Exception as exc:
            raise SystemExit(f"temporal CSV normalization failed: {exc}") from exc
        reporter.temporal_finished(spec, summary)


def _run_prepare(
    case_dir: Path,
    cfg: dict,
    *,
    result_dir: Path,
    executable_path: Path,
    reporter: Reporter,
    state_callback: StateCallback | None,
    heartbeat_seconds: float,
    stall_after_seconds: float,
) -> int:
    """Execute manifest-declared prepare before parser/preflight and solve."""

    prepare = cfg.get("prepare")
    if not prepare:
        return 0

    prepare_args = cfg.get("prepare_args", [])
    prepare_path = (case_dir / prepare).resolve()
    prepare_log = result_dir / "prepare.log"
    if not prepare_path.is_file():
        prepare_log.write_text(f"missing prepare script: {prepare_path}\n")
        reporter.prepare_finished(1, prepare_log)
        return 1

    prepare_env = os.environ.copy()
    prepare_env.setdefault("QPX_ROOT", str(executable_path.parent))

    result = run_command(
        [sys.executable, str(prepare_path), *[str(arg) for arg in prepare_args]],
        cwd=case_dir,
        log_path=prepare_log,
        telemetry_callback=_telemetry_adapter(
            state_callback,
            stall_after_seconds=stall_after_seconds,
        ),
        heartbeat_seconds=heartbeat_seconds,
        env=prepare_env,
    )
    reporter.prepare_finished(result.returncode, prepare_log)
    return result.returncode


def _run_checker(
    case_dir: Path,
    *,
    checker: str,
    checker_args: list,
    result_dir: Path,
    reporter: Reporter,
) -> int:
    checker_path = (case_dir / checker).resolve()
    check_log = result_dir / "check.log"

    if not checker_path.is_file():
        check_log.write_text(f"missing checker: {checker_path}\n")
        reporter.check_finished(1, check_log)
        return 1

    with check_log.open("w") as log:
        check = subprocess.run(
            [sys.executable, str(checker_path), *[str(arg) for arg in checker_args]],
            cwd=case_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    reporter.check_finished(check.returncode, check_log)
    return check.returncode


def run_case(
    case_dir: Path,
    *,
    results_root: Path | None = None,
    namespace_root: Path | None = None,
    executable: str | Path | None = None,
    reporter: Reporter | None = None,
    state_callback: StateCallback | None = None,
    heartbeat_seconds: float = 10.0,
    stall_after_seconds: float = 60.0,
) -> int:
    case_dir = Path(case_dir).expanduser().resolve()
    cfg = load_manifest(case_dir)
    active_reporter = reporter or ConsoleReporter(detailed=True)

    input_name = cfg["input"]
    checker = cfg.get("checker")
    checker_args = cfg.get("checker_args", [])
    test_type = cfg.get("type", "canonical")

    out_root = (results_root or (harness_root() / "results")).expanduser().resolve()
    result_dir = out_root / _case_result_key(case_dir, namespace_root)
    result_dir.mkdir(parents=True, exist_ok=True)
    log_path = result_dir / "run.log"

    active_reporter.case_started(
        case_dir=case_dir,
        test_type=test_type,
        input_name=input_name,
        log_path=log_path,
    )

    exe = resolve_executable(executable)
    validate_executable(exe)

    prepare_rc = _run_prepare(
        case_dir,
        cfg,
        result_dir=result_dir,
        executable_path=exe,
        reporter=active_reporter,
        state_callback=state_callback,
        heartbeat_seconds=heartbeat_seconds,
        stall_after_seconds=stall_after_seconds,
    )
    if prepare_rc != 0:
        return prepare_rc or 1

    input_path = case_dir / input_name
    validate_input_preflight(input_path)
    validate_temporal_manifest_preflight(input_path, cfg)
    active_reporter.executable_resolved(exe)

    solve = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_name,
        log_path=log_path,
        telemetry_callback=_telemetry_adapter(
            state_callback,
            stall_after_seconds=stall_after_seconds,
        ),
        heartbeat_seconds=heartbeat_seconds,
    )
    active_reporter.solve_finished(solve.returncode)
    if solve.returncode != 0:
        return solve.returncode or 1

    prepare_temporal_outputs(case_dir, cfg, reporter=active_reporter)

    if not checker:
        active_reporter.check_finished(None, None, skipped=True)
        return 0

    return _run_checker(
        case_dir,
        checker=checker,
        checker_args=checker_args,
        result_dir=result_dir,
        reporter=active_reporter,
    )


def run_suite(
    roots: Iterable[Path],
    *,
    requested_type: str = "canonical",
    results_root: Path | None = None,
    executable: str | Path | None = None,
    heartbeat_seconds: float = 10.0,
    stall_after_seconds: float = 60.0,
    reporter: Reporter | None = None,
) -> SuiteResult:
    if requested_type not in {"canonical", "diagnostic", "all"}:
        raise SystemExit(f"unsupported requested type: {requested_type}")

    active_reporter = reporter or ConsoleReporter(detailed=False)
    roots = [Path(root).expanduser().resolve() for root in roots]
    manifests = discover_manifests(
        roots,
        on_missing_root=active_reporter.root_skipped,
    )
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
        active_reporter.suite_empty(requested_type)
        return SuiteResult(requested_type, 0, 0, ())

    total = len(selected)
    failures: list[str] = []
    cases: list[CaseSummary] = []
    suite_start = time.perf_counter()
    active_reporter.suite_started(requested_type, total)

    for index, (manifest, _test_type, owner_root) in enumerate(selected, start=1):
        case_dir = manifest.parent
        cfg = load_manifest(case_dir)
        case_name = cfg.get("name", case_dir.name)

        def emit(state: ExecutionState, elapsed: float, *, _index: int = index) -> None:
            active_reporter.case_progress(_index, total, state, elapsed)

        emit(ExecutionState.CALCULATING, 0.0)
        case_start = time.perf_counter()
        rc = run_case(
            case_dir,
            results_root=results_root,
            namespace_root=owner_root,
            executable=executable,
            reporter=active_reporter,
            state_callback=emit,
            heartbeat_seconds=heartbeat_seconds,
            stall_after_seconds=stall_after_seconds,
        )
        wall_seconds = time.perf_counter() - case_start
        status = ExecutionState.PASS if rc == 0 else ExecutionState.FAIL
        emit(status, wall_seconds)

        cases.append(
            CaseSummary(
                name=case_name,
                path=str(case_dir),
                status=status,
                wall_seconds=wall_seconds,
            )
        )
        if rc != 0:
            failures.append(str(case_dir))

    wall_seconds = time.perf_counter() - suite_start
    passed = total - len(failures)
    result = SuiteResult(
        requested_type=requested_type,
        total=total,
        passed=passed,
        failed=tuple(failures),
        wall_seconds=wall_seconds,
        cases=tuple(cases),
    )
    active_reporter.suite_finished(result, results_root=results_root)
    return result


def cli_run_test(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir")
    parser.add_argument("--results-root")
    parser.add_argument("--namespace-root")
    parser.add_argument("--qpx")
    parser.add_argument("--heartbeat-seconds", type=float, default=10.0)
    parser.add_argument("--stall-seconds", type=float, default=60.0)
    args = parser.parse_args(argv)
    return run_case(
        Path(args.case_dir),
        results_root=Path(args.results_root) if args.results_root else None,
        namespace_root=Path(args.namespace_root) if args.namespace_root else None,
        executable=args.qpx,
        heartbeat_seconds=args.heartbeat_seconds,
        stall_after_seconds=args.stall_seconds,
    )


def cli_run_all(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--type",
        choices=("canonical", "diagnostic", "all"),
        default="canonical",
    )
    parser.add_argument("--tests-root", action="append", default=[])
    parser.add_argument("--results-root")
    parser.add_argument("--qpx")
    parser.add_argument("--heartbeat-seconds", type=float, default=10.0)
    parser.add_argument("--stall-seconds", type=float, default=60.0)
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
        heartbeat_seconds=args.heartbeat_seconds,
        stall_after_seconds=args.stall_seconds,
    )
    return result.returncode
