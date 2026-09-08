"""Reusable interpretation of MOOSE/QPX --check-input failures.

This module owns issue-agnostic construction/environment failure facts. Scientific
recipes may consume these facts, but issue-specific causality and acceptance
remain outside this module.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def classify_failure(log_path: Path, returncode: int) -> dict[str, Any]:
    if returncode == 0:
        return {
            "status": "PASS",
            "class": None,
            "reason": None,
            "detail": None,
        }
    if not log_path.is_file():
        return {
            "status": "HOLD",
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "MISSING_P2_LOG",
            "detail": None,
        }

    text = log_path.read_text(errors="replace")
    unused = re.search(r"unused parameter ['\"]([^'\"]+)['\"]", text)
    if unused:
        return {
            "status": "HOLD",
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "UNUSED_PARAMETER",
            "detail": unused.group(1),
        }
    if "ADFParser::JITCompile() failed" in text:
        return {
            "status": "HOLD",
            "class": "ENVIRONMENT_OR_BUILD_FAIL",
            "reason": "JIT_COMPILE_FAIL",
            "detail": None,
        }

    error_detail: str | None = None
    error_match = re.search(r"\*\*\* ERROR \*\*\*\s*\n([^\n]+)", text)
    if error_match:
        error_detail = error_match.group(1).strip()
    return {
        "status": "HOLD",
        "class": "HARNESS_OR_CONSTRUCTION_FAIL",
        "reason": "QPX_CHECK_INPUT_FAIL",
        "detail": error_detail,
    }


def self_test() -> int:
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.log"
            if classify_failure(missing, 2)["reason"] != "MISSING_P2_LOG":
                raise AssertionError("missing-log classification drifted")

            unused = root / "unused.log"
            unused.write_text("unused parameter 'foo'\n")
            result = classify_failure(unused, 2)
            if result["reason"] != "UNUSED_PARAMETER" or result["detail"] != "foo":
                raise AssertionError("unused-parameter classification drifted")

            jit = root / "jit.log"
            jit.write_text("ADFParser::JITCompile() failed\n")
            if classify_failure(jit, 2)["class"] != "ENVIRONMENT_OR_BUILD_FAIL":
                raise AssertionError("JIT classification drifted")

            generic = root / "generic.log"
            generic.write_text("*** ERROR ***\nconstruction failed\n")
            result = classify_failure(generic, 2)
            if result["reason"] != "QPX_CHECK_INPUT_FAIL" or result["detail"] != "construction failed":
                raise AssertionError("generic check-input classification drifted")

            if classify_failure(generic, 0)["status"] != "PASS":
                raise AssertionError("successful check-input was not PASS")
    except Exception as exc:
        print(f"QPX_CHECK_INPUT_CLASSIFIER_SELFTEST: FAIL ({exc})")
        return 1
    print("QPX_CHECK_INPUT_CLASSIFIER_SELFTEST: PASS")
    return 0
