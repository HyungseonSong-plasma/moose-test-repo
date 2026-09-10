#!/usr/bin/env python3
"""P0 characterization for generic case staging and asset validation."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.execution import cases


V1_PURGE_DIRS = (".jitcache",)
V1_PURGE_PATTERNS = (
    "input_out*",
    "r43_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


def _assert_boundary() -> None:
    source = (Path(cases.__file__).resolve()).read_text()
    for forbidden in (
        "Issue43",
        "ISSUE43",
        "r43_",
        "fast_plasma",
        "electron_inventory",
        "jacobian_fd_reference_audit",
        "petsc_first_linear_diagnostic",
        "augmented_jacobian_localization",
    ):
        if forbidden in source:
            raise AssertionError(f"special-case or reverse dependency leaked: {forbidden}")


def _positive_stage_and_validate() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        source = root / "source"
        source.mkdir()
        assets = source / "assets"
        assets.mkdir()
        (assets / "table.dat").write_text("table\n")
        (source / "mesh.msh").write_text("mesh\n")
        (source / "input.i").write_text(
            "mesh_file = mesh.msh\n"
            "table_file = 'assets/table.dat'\n"
        )
        (source / "input_out.csv").write_text("stale\n")
        (source / "metrics-old").mkdir()
        nested = source / "nested"
        nested.mkdir()
        (nested / ".jitcache").mkdir()
        (nested / ".jitcache" / "jit.o").write_text("stale\n")
        (nested / "petsc_log.txt").write_text("stale\n")

        target = root / "target"
        replacement = (
            "mesh_file = mesh.msh\n"
            "table_file = \"assets/table.dat\"\n"
        )
        report = cases.stage_case(
            source,
            target,
            input_text=replacement,
            purge_directory_names=V1_PURGE_DIRS,
            purge_patterns=V1_PURGE_PATTERNS,
        )

        if (source / "input_out.csv").read_text() != "stale\n":
            raise AssertionError("source case was mutated")
        if (target / "input.i").read_text() != replacement:
            raise AssertionError("staged input replacement drift")
        for stale in (
            target / "input_out.csv",
            target / "metrics-old",
            target / "nested" / ".jitcache",
            target / "nested" / "petsc_log.txt",
        ):
            if stale.exists():
                raise AssertionError(f"generated artifact survived staging: {stale}")

        purged = set(report["purged"])
        required_purged = {
            "input_out.csv",
            "metrics-old",
            "nested/.jitcache",
            "nested/petsc_log.txt",
        }
        if not required_purged.issubset(purged):
            raise AssertionError(
                f"staging purge evidence drift: missing {required_purged - purged}"
            )

        refs = cases.validate_case_references(target)
        observed = {(item["parameter"], item["raw"]) for item in refs}
        expected = {
            ("mesh_file", "mesh.msh"),
            ("table_file", "assets/table.dat"),
        }
        if observed != expected:
            raise AssertionError(f"referenced-file parse drift: {observed}")


def _negative_controls() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        source = root / "source"
        source.mkdir()
        (source / "input.i").write_text("mesh_file = missing.msh\n")

        try:
            cases.validate_case_references(source)
        except cases.CaseError as exc:
            if "missing referenced input file(s)" not in str(exc):
                raise AssertionError(f"missing-asset error drift: {exc}")
        else:
            raise AssertionError("missing referenced asset was accepted")

        try:
            cases.stage_case(source, root / "target", input_name="../input.i")
        except cases.CaseError:
            pass
        else:
            raise AssertionError("input path escape was accepted")

        existing = root / "existing"
        existing.mkdir()
        try:
            cases.stage_case(source, existing)
        except cases.CaseError:
            pass
        else:
            raise AssertionError("existing target was overwritten")

        dynamic = cases.referenced_file_parameters(
            "table_file = '${TABLE_FILE}'\n",
            source,
            skip_dynamic=True,
        )
        if dynamic:
            raise AssertionError("dynamic reference skip contract drift")


def main() -> int:
    try:
        _assert_boundary()
        _positive_stage_and_validate()
        _negative_controls()
    except Exception as exc:
        print(f"ISSUE48_CASE_PRIMITIVES_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_CASE_PRIMITIVES_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())