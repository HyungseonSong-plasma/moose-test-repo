"""User-facing terminal and machine-readable reporting for the QPX harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .status import ExecutionState

if TYPE_CHECKING:
    from .regression import SuiteResult


DISPLAY_STATE = {
    ExecutionState.CALCULATING: "CALCULATING",
    ExecutionState.WAITING: "WAITING",
    ExecutionState.STALL_SUSPECTED: "STOP?",
    ExecutionState.PASS: "PASS",
    ExecutionState.FAIL: "FAIL",
}


class Reporter(Protocol):
    def root_skipped(self, root: Path) -> None: ...
    def case_started(
        self,
        *,
        case_dir: Path,
        test_type: str,
        input_name: str,
        log_path: Path,
    ) -> None: ...
    def executable_resolved(self, executable: Path) -> None: ...
    def prepare_finished(self, returncode: int, log_path: Path) -> None: ...
    def solve_finished(self, returncode: int) -> None: ...
    def temporal_finished(self, spec: dict, summary: dict) -> None: ...
    def check_finished(
        self,
        returncode: int | None,
        log_path: Path | None,
        *,
        skipped: bool = False,
    ) -> None: ...
    def suite_empty(self, requested_type: str) -> None: ...
    def suite_started(self, requested_type: str, total: int) -> None: ...
    def case_progress(
        self,
        index: int,
        total: int,
        state: ExecutionState,
        elapsed_seconds: float,
    ) -> None: ...
    def suite_finished(
        self,
        result: "SuiteResult",
        *,
        results_root: Path | None,
    ) -> None: ...


class ConsoleReporter:
    """Default console presentation.

    ``detailed=True`` is used by single-case execution; suites use compact mode.
    Runtime and regression semantics do not depend on this formatting choice.
    """

    def __init__(self, *, detailed: bool) -> None:
        self.detailed = detailed

    def root_skipped(self, root: Path) -> None:
        print(f"TEST_ROOT_SKIP: {root} (not found)")

    def case_started(
        self,
        *,
        case_dir: Path,
        test_type: str,
        input_name: str,
        log_path: Path,
    ) -> None:
        if not self.detailed:
            return
        print(f"CASE       : {case_dir}")
        print(f"TYPE       : {test_type}")
        print(f"INPUT      : {input_name}")
        print(f"LOG        : {log_path}")

    def executable_resolved(self, executable: Path) -> None:
        if self.detailed:
            print(f"EXECUTABLE : {executable}")

    def prepare_finished(self, returncode: int, log_path: Path) -> None:
        if not self.detailed:
            return
        print("PREPARE    :", "PASS" if returncode == 0 else "FAIL")
        print(f"PREPARE LOG: {log_path}")

    def solve_finished(self, returncode: int) -> None:
        if self.detailed:
            print("SOLVE      :", "PASS" if returncode == 0 else "FAIL")

    def temporal_finished(self, spec: dict, summary: dict) -> None:
        if not self.detailed:
            return
        print("TEMPORAL_ROWS: PASS")
        print(f"  SOURCE              : {spec['source']}")
        print(f"  PHYSICAL            : {spec['physical']}")
        print(f"  POLICY              : {summary['initial_row_policy']}")
        print(f"  SOURCE_ROWS         : {summary['source_rows']}")
        print(f"  INITIALIZATION_ROWS : {summary['initialization_rows']}")
        print(f"  PHYSICAL_ROWS       : {summary['physical_rows']}")

    def check_finished(
        self,
        returncode: int | None,
        log_path: Path | None,
        *,
        skipped: bool = False,
    ) -> None:
        if not self.detailed:
            return
        if skipped:
            print("CHECK      : SKIP")
            return
        if log_path is not None and log_path.is_file():
            text = log_path.read_text(errors="replace")
            if text:
                print(text, end="" if text.endswith("\n") else "\n")
        assert returncode is not None
        print("CHECK      :", "PASS" if returncode == 0 else "FAIL")

    def suite_empty(self, requested_type: str) -> None:
        print(f"No {requested_type} tests found.")

    def suite_started(self, requested_type: str, total: int) -> None:
        print(f"QPX {requested_type} suite")
        print(f"CASES: {total}")
        print()

    def case_progress(
        self,
        index: int,
        total: int,
        state: ExecutionState,
        elapsed_seconds: float,
    ) -> None:
        del elapsed_seconds
        percent = round(index * 100 / total)
        label = DISPLAY_STATE[state]
        print(f"[{index:>2}/{total:<2} | {percent:>3}%] {label}", flush=True)

    def suite_finished(
        self,
        result: "SuiteResult",
        *,
        results_root: Path | None,
    ) -> None:
        self._write_suite_summary(result, results_root=results_root)

        print("\n" + "=" * 48)
        print("QPX SUITE SUMMARY")
        print()
        print(f"TYPE    {result.requested_type}")
        print(f"TOTAL   {result.total}")
        print(f"PASS    {result.passed}")
        print(f"FAIL    {len(result.failed)}")
        print(f"RESULT  {'PASS' if not result.failed else 'FAIL'}")
        print(f"TIME    {result.wall_seconds:.1f} s")
        print("=" * 48)

        if result.failed:
            print("\nFailed cases:")
            for case in result.failed:
                print(f"  - {case}")

        print(
            f"\nTYPE: {result.requested_type}  TOTAL: {result.total}  "
            f"PASS: {result.passed}  FAIL: {len(result.failed)}"
        )

    @staticmethod
    def _write_suite_summary(
        result: "SuiteResult",
        *,
        results_root: Path | None,
    ) -> None:
        if results_root is None:
            return

        root = Path(results_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "type": result.requested_type,
            "total": result.total,
            "passed": result.passed,
            "failed": len(result.failed),
            "result": ExecutionState.PASS.value if not result.failed else ExecutionState.FAIL.value,
            "wall_seconds": result.wall_seconds,
            "cases": [
                {
                    "name": case.name,
                    "path": case.path,
                    "status": case.status.value,
                    "wall_seconds": case.wall_seconds,
                }
                for case in result.cases
            ],
        }
        (root / "suite_summary.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n"
        )
