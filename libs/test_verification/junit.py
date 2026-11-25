"""Bounded JUnit byte validation and testcase comparison.

No producer authentication, revision binding or acceptance authority.
"""
from __future__ import annotations

from hashlib import sha256
from xml.etree import ElementTree as ET


def parse_junit(junit_xml: bytes, expected_sha256: str, *, max_bytes: int
                ) -> tuple[dict[str, str], set[str], set[str]]:
    """Return testcase outcomes, validation blockers and unresolved findings."""
    blocked: set[str] = set()
    unresolved: set[str] = set()
    if len(junit_xml) > max_bytes:
        return {}, blocked, unresolved | {"JUNIT_SIZE_LIMIT"}
    if sha256(junit_xml).hexdigest() != expected_sha256:
        return {}, blocked | {"JUNIT_DIGEST_MISMATCH"}, unresolved
    # Reject DTD/entity declarations rather than trusting XML parser configuration.
    if b"<!DOCTYPE" in junit_xml.upper() or b"<!ENTITY" in junit_xml.upper():
        return {}, blocked | {"UNTRUSTED_XML_DECLARATION"}, unresolved
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError:
        return {}, blocked | {"INVALID_JUNIT_XML"}, unresolved
    if root.tag not in {"testsuite", "testsuites"}:
        return {}, blocked | {"UNEXPECTED_JUNIT_ROOT"}, unresolved
    cases: dict[str, str] = {}
    for case in root.iter("testcase"):
        key = case.get("classname", "") + "::" + case.get("name", "")
        if not case.get("name") or key in cases:
            blocked.add("MISSING_OR_DUPLICATE_TEST_ID")
            continue
        status = "PASSED"
        for tag in ("failure", "error", "skipped"):
            if case.find(tag) is not None:
                status = tag.upper()
                break
        cases[key] = status
    if not cases:
        unresolved.add("NO_JUNIT_TESTCASES")
    return cases, blocked, unresolved


def compare_case_outcomes(before: dict[str, str], after: dict[str, str]
                          ) -> tuple[set[str], set[str]]:
    """Compare stable testcase inventories and outcomes, not semantic parity."""
    blocked: set[str] = set()
    unresolved: set[str] = set()
    for key in sorted(before.keys() - after.keys()):
        blocked.add("BASELINE_TEST_MISSING:" + key)
    for key in sorted(after.keys() - before.keys()):
        unresolved.add("NEW_CANDIDATE_TEST:" + key)
    for key, status in before.items():
        if status != "PASSED":
            unresolved.add("BASELINE_NOT_GREEN:" + key)
    for key, status in after.items():
        if status in {"FAILURE", "ERROR"}:
            blocked.add("CANDIDATE_TEST_FAILED:" + key)
        elif status == "SKIPPED":
            unresolved.add("CANDIDATE_TEST_SKIPPED:" + key)
    return blocked, unresolved


__all__ = ["parse_junit", "compare_case_outcomes"]
