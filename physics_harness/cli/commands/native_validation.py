"""Canonical CLI for strict Native P1 -> P2 input-validation sequence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from physics_harness.execution.native_gates import (
    P1GateError, record_p1_success, run_p2_checked,
)


def _shared_p1_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--source-root', type=Path, required=True,
                        help='exact Git checkout that produced the executable')
    parser.add_argument('--source-sha', required=True, help='independently pinned 40-character Git SHA')
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--oci-ref', required=True, help='digest-pinned OCI image used in P1')


def native_p1_record_cli(argv: list[str]) -> int:
    """Called only after the current CI build step completed successfully."""
    parser = argparse.ArgumentParser(prog='physics native-p1-record')
    _shared_p1_args(parser)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-report', type=Path, required=True,
                        help='PASS report emitted by canonical physics native-build harness')
    args = parser.parse_args(argv)
    try:
        evidence = record_p1_success(
            args.output, source_root=args.source_root, source_sha=args.source_sha,
            binary=args.binary, image_ref=args.oci_ref, build_report=args.build_report,
        )
    except (OSError, P1GateError) as exc:
        print(f'NATIVE_P1_RECORD: HOLD ({exc})', file=sys.stderr)
        return 3
    print('NATIVE_P1_RECORD: PASS')
    print(json.dumps(evidence, sort_keys=True))
    return 0


def validate_input_cli(argv: list[str]) -> int:
    """Direct host-side P2; inside OCI use the same gate via Python API."""
    parser = argparse.ArgumentParser(prog='physics validate-input')
    _shared_p1_args(parser)
    parser.add_argument('--p1-evidence', type=Path, required=True)
    parser.add_argument('--case-dir', type=Path, required=True)
    parser.add_argument('--input', required=True, help='MOOSE input filename relative to case directory')
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=1200)
    args = parser.parse_args(argv)
    try:
        report = run_p2_checked(
            [str(args.binary.resolve()), '--check-input', '-i', args.input],
            evidence=args.p1_evidence, source_root=args.source_root,
            binary=args.binary, source_sha=args.source_sha, image_ref=args.oci_ref,
            cwd=args.case_dir, log_path=args.log, timeout_seconds=args.timeout,
            success_marker='Syntax OK',
        )
    except (OSError, ValueError, P1GateError) as exc:
        print(f'NATIVE_P2: HOLD ({exc})', file=sys.stderr)
        return 3
    print('NATIVE_P2: ' + report['P2'])
    print(json.dumps(report, sort_keys=True))
    return 0 if report['P2'] == 'PASS' else 3
