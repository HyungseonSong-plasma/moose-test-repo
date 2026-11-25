"""Thin read-only CLI over the existing Code Diagnostics API."""
from __future__ import annotations

import argparse
from pathlib import Path

from libs.command_execution import Command, dispatch, write_json


def _configure_scan(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository", required=True,
                        help="Repository label for source provenance")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--revision", required=True)
    parser.add_argument("--include", action="append", required=True)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--collector", action="append", required=True)
    parser.add_argument("--max-files", type=int, default=100)
    parser.add_argument("--max-bytes", type=int, default=5_000_000)
    parser.add_argument("--max-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True,
                        help="New JSON result file; must not exist")


def _scan(args: argparse.Namespace) -> int:
    from .diagnostics import GitSourceProvider, ScanBudget, ScanRequest, run_scan

    request = ScanRequest(
        repository=args.repository, revision=args.revision,
        includes=tuple(args.include), excludes=tuple(args.exclude),
        collectors=tuple(args.collector),
        budget=ScanBudget(max_files=args.max_files, max_bytes=args.max_bytes,
                          max_seconds=args.max_seconds),
    )
    provider = GitSourceProvider(args.root)
    result = run_scan(request, provider)
    provider.assert_head(request.revision)
    verification = result.verification
    if verification is None or verification.status not in {
        "VERIFIED", "UNVERIFIED", "FAILED"
    }:
        raise ValueError("MISSING_OR_INVALID_VERIFICATION_RECEIPT")
    write_json({
        "schema_version": 1, "command": "code.scan",
        "source_revision": request.revision, "status": result.status,
        "request": request, "graph": result.graph, "receipt": result.receipt,
        "verification": verification,
        "semantic_compatibility_proven": False,
        "safe_delete_authorized": False,
    }, args.output)
    if verification.status == "FAILED":
        return 4
    # Zero proves bounded source coverage/metadata only, not task completion.
    return 0 if result.status == "COMPLETE" and verification.status == "VERIFIED" else 3


def main(argv: list[str] | None = None) -> int:
    return dispatch("code", {
        "scan": Command("Bounded exact-HEAD source scan", _configure_scan, _scan),
    }, argv)


if __name__ == "__main__":
    raise SystemExit(main())
