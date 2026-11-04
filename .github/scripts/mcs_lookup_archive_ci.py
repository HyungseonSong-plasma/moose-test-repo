#!/usr/bin/env python3
"""Fail-closed approval and archive boundaries for the Issue #432 runner.

This module has no Lookup data. Its tests use generated archives and mocked
GitHub responses. Private inputs and all derived numeric diagnostics stay inside
the approved runner; exception messages intentionally exclude their contents.
"""
from __future__ import annotations

import argparse
import base64
import csv
import math
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
from urllib.request import Request, urlopen

REPOSITORY = "HyungseonSong-plasma/moose-test-repo"
ENVIRONMENT = "mcs-lookup-comparison"
SHA = re.compile(r"[0-9a-f]{40}")
RECORD = re.compile(
    r"https://github\.com/HyungseonSong-plasma/moose-test-repo/issues/432#issuecomment-[1-9][0-9]*"
)
CODE_RECORD = re.compile(
    r"https://github\.com/HyungseonSong-plasma/moose-test-repo/"
    r"(?:issues/432#issuecomment-|pull/[1-9][0-9]*#pullrequestreview-)[1-9][0-9]*"
)
TABLE_NAME = re.compile(r"EI-[1-9][0-9]*_[A-Za-z0-9_]+\.txt")
MAX_ENCODED_BYTES = 128 * 1024 * 1024
MAX_UNPACKED_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 128
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class BoundaryError(ValueError):
    """A public error containing no private input values."""


def github_environment(token: str) -> dict:
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/environments/{ENVIRONMENT}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except Exception:
        # Includes 403/404, unavailable API, malformed response and transport errors.
        raise BoundaryError("Protected Environment could not be verified") from None


def verify_approvals(environ: dict[str, str], environment: dict) -> str:
    """Verify maintainer attestation bindings, not linked review semantics.

    Before setting repository variables, maintainers must verify record authors,
    scope, and exact commit. The helper checks URLs and SHA bindings; it does not
    infer a review decision from comment text or independently establish authors.
    """
    sha = environ.get("GITHUB_SHA", "")
    if (
        environ.get("GITHUB_REPOSITORY") != REPOSITORY
        or environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or SHA.fullmatch(sha) is None
        or any(
            environ.get(name) != sha
            for name in ("EXPECTED_SHA", "MCS_CODE_REVIEWED_SHA", "MCS_PNG_PUBLIC_DISCLOSURE_SHA")
        )
    ):
        raise BoundaryError("Exact-head code and PNG disclosure approvals are required")
    for name in ("MCS_CODE_REVIEW_RECORD_URL", "MCS_PNG_PUBLIC_DISCLOSURE_RECORD_URL"):
        record = environ.get(name, "")
        pattern = CODE_RECORD if name == "MCS_CODE_REVIEW_RECORD_URL" else RECORD
        if pattern.fullmatch(record) is None:
            raise BoundaryError("Code review and Issue #432 disclosure records are required")
        # The original comment approves processing, neither code nor PNG release.
        if record.endswith("6631358844"):
            raise BoundaryError("Processing approval does not approve code or PNG disclosure")
    if not isinstance(environment, dict) or environment.get("name") != ENVIRONMENT:
        raise BoundaryError("Protected Environment could not be verified")
    rules = environment.get("protection_rules")
    if not isinstance(rules, list):
        raise BoundaryError("Required independent Environment review is missing")
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "required_reviewers":
            continue
        reviewers = rule.get("reviewers")
        if rule.get("prevent_self_review") is not True or not isinstance(reviewers, list):
            continue
        valid = [
            row
            for row in reviewers
            if isinstance(row, dict)
            and row.get("type") in {"User", "Team"}
            and isinstance(row.get("reviewer"), dict)
            and isinstance(row["reviewer"].get("id"), int)
            and not isinstance(row["reviewer"].get("id"), bool)
            and row["reviewer"]["id"] > 0
        ]
        if valid:
            return sha
    raise BoundaryError("Required independent Environment review is missing")


def restore_archive(encoded: str, destination: Path) -> None:
    """Restore existing base64/tar.xz package, accepting only regular rate files.

    The supported expected layout is root-level EI-<id>_<target>.txt files,
    matching the existing runner's direct-root validator. No private archive was
    inspected to implement this boundary. Reject paths, links, device files,
    duplicate names and oversized inputs before writing.
    """
    created = False
    try:
        if not encoded or len(encoded) > MAX_ENCODED_BYTES:
            raise BoundaryError("Private Lookup package unavailable or invalid")
        # The established shell base64 decoder permits wrapped secret values.
        normalized = encoded.translate(str.maketrans("", "", " \t\r\n\v\f"))
        payload = base64.b64decode(normalized, validate=True)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as archive:
            files = []
            seen = set()
            total = 0
            for count, member in enumerate(archive, start=1):
                if count > MAX_MEMBERS:
                    raise BoundaryError("Private Lookup package unavailable or invalid")
                name = member.name
                if member.isdir() and name in {".", "./"}:
                    continue
                if name.startswith("./"):
                    name = name[2:]
                if (
                    not member.isfile()
                    or TABLE_NAME.fullmatch(name) is None
                    or name in seen
                    or member.size < 0
                ):
                    raise BoundaryError("Private Lookup package unavailable or invalid")
                seen.add(name)
                total += member.size
                if total > MAX_UNPACKED_BYTES:
                    raise BoundaryError("Private Lookup package unavailable or invalid")
                files.append((member, name))
            if not files:
                raise BoundaryError("Private Lookup package unavailable or invalid")
            destination.mkdir(mode=0o700, parents=False, exist_ok=False)
            created = True
            for member, name in files:
                source = archive.extractfile(member)
                if source is None:
                    raise BoundaryError("Private Lookup package unavailable or invalid")
                with source, (destination / name).open("xb") as output:
                    os.chmod(output.name, 0o600)
                    shutil.copyfileobj(source, output)
    except Exception:
        if created:
            shutil.rmtree(destination, ignore_errors=True)
        raise BoundaryError("Private Lookup package unavailable or invalid") from None


def check_png(path: Path) -> None:
    if path.name != "MCS_MOOSE_3x3_LINEAR.png" or path.is_symlink() or not path.is_file():
        raise BoundaryError("Approved PNG is missing or invalid")
    with path.open("rb") as stream:
        if stream.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
            raise BoundaryError("Approved PNG is missing or invalid")


def verify_ratio_disclosure(environ: dict[str, str]) -> str:
    """A distinct public release attestation is required for reversible ratios.

    The maintainer must inspect record author, scope and current exact SHA.
    This guard binds the record URL to the SHA, not the comment's semantics.
    """
    sha = environ.get("GITHUB_SHA", "")
    record = environ.get("MCS_RATIO_PUBLIC_DISCLOSURE_RECORD_URL", "")
    if (
        SHA.fullmatch(sha) is None
        or environ.get("MCS_RATIO_PUBLIC_DISCLOSURE_SHA") != sha
        or RECORD.fullmatch(record) is None
        or record.endswith(("6631358844", "6633659857"))
    ):
        raise BoundaryError("Current-commit numeric ratio publication approval is missing")
    return sha


RATIO_COLUMNS = (
    "reaction", "case", "mean_energy_eV", "moose_over_mcs",
    "comparison_status", "scientific_status",
)
RATIO_CHANNELS = (401, 411, 412, 417, 935, 941, 943, 2738, 407)


def check_ratios(path: Path) -> None:
    """Approve only 9x24 ratio-only CSV, never a private coefficient dump."""
    if (
        path.name != "MCS_MOOSE_9_reaction_ratios.csv"
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 65536
        or sorted(item.name for item in path.parent.iterdir()) != [path.name]
    ):
        raise BoundaryError("Ratio output allowlist failed")
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != RATIO_COLUMNS:
            raise BoundaryError("Ratio output allowlist failed")
        rows = list(reader)
    if len(rows) != 9 * 24:
        raise BoundaryError("Ratio output allowlist failed")
    for i, row in enumerate(rows):
        expected_rid = RATIO_CHANNELS[i // 24]
        try:
            mean_energy = float(row["mean_energy_eV"])
            value = row["moose_over_mcs"]
            ratio = None if not value else float(value)
        except (ValueError, TypeError, OverflowError):
            raise BoundaryError("Ratio output allowlist failed") from None
        if (
            row["reaction"] != f"EI-{expected_rid}"
            or row["case"] != str(i % 24 + 1)
            or not math.isfinite(mean_energy)
            or mean_energy <= 0
            or (ratio is not None and (not math.isfinite(ratio) or ratio < 0))
            or row["comparison_status"] not in {
                "MATCHED", "ZERO_MCS_NO_RATIO", "OUTSIDE_LOOKUP_OR_FORMULA_DOMAIN"
            }
            or (row["comparison_status"] == "MATCHED") != (ratio is not None)
            or row["scientific_status"] != (
                "REACTION_IDENTITY_HOLD" if expected_rid in (411, 412)
                else "MCS_UNIT_CONFIRMATION_HOLD"
            )
        ):
            raise BoundaryError("Ratio output allowlist failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-approvals", action="store_true")
    mode.add_argument("--check-ratio-disclosure", action="store_true")
    mode.add_argument("--restore", type=Path)
    mode.add_argument("--check-png", type=Path)
    mode.add_argument("--check-ratios", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.check_approvals:
            token = os.environ.get("GH_TOKEN", "")
            if not token:
                raise BoundaryError("Protected Environment could not be verified")
            sha = verify_approvals(dict(os.environ), github_environment(token))
            output = os.environ.get("GITHUB_OUTPUT")
            if not output:
                raise BoundaryError("Approval output channel is unavailable")
            with Path(output).open("a") as stream:
                stream.write(f"approved_sha={sha}\n")
            print("MCS_COMPARISON_APPROVAL_GATE=PASS")
        elif args.check_ratio_disclosure:
            verify_ratio_disclosure(dict(os.environ))
            print("MCS_RATIO_DISCLOSURE_GATE=PASS")
        elif args.restore is not None:
            restore_archive(os.environ.get("PRIVATE_RATES_B64", ""), args.restore)
            print("PRIVATE_LOOKUP_PACKAGE_RESTORED")
        elif args.check_png is not None:
            check_png(args.check_png)
            print("APPROVED_PNG_OUTPUT=PASS")
        else:
            check_ratios(args.check_ratios)
            print("APPROVED_RATIO_OUTPUT=PASS")
    except BoundaryError as error:
        print(f"::error::{error}")
        return 1
    except Exception:
        print("::error::Comparison security boundary failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
