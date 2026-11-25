#!/usr/bin/env python3
"""Full Git change inventory and Physics route applicability, never a CI PASS."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from repository_ci_scope import event_paths

WORKFLOWS = (
    "physics-code-ci.yml",
    "physics-native-ci.yml",
    "issue402-flow-native-p2-regression.yml",
    "ion-fvm-hybrid-staged-dt.yml",
)
SHA = re.compile(r"[0-9a-f]{40}\Z")


def git(*args):
    return subprocess.check_output(["git", *args], timeout=120)


def require_sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value) or value == "0" * 40:
        raise ValueError("INVALID_EVENT_COMMIT")
    return value


def event_revisions(event, payload):
    if event == "pull_request":
        pr = payload["pull_request"]
        if pr["base"]["ref"] != "main":
            raise ValueError("UNEXPECTED_PR_BASE")
        return require_sha(pr["base"]["sha"]), require_sha(pr["head"]["sha"])
    if event == "push" and payload["ref"] == "refs/heads/main":
        return require_sha(payload["before"]), require_sha(payload["after"])
    raise ValueError("UNSUPPORTED_EVENT")


def inventory(event, base, head):
    if git("rev-parse", "HEAD").decode().strip() != head:
        raise ValueError("SOURCE_HEAD_MISMATCH")
    if git("rev-parse", "--is-shallow-repository").decode().strip() != "false":
        raise ValueError("SHALLOW_HISTORY")
    for sha in (base, head):
        if git("rev-parse", sha + "^{commit}").decode().strip() != sha:
            raise ValueError("EVENT_COMMIT_UNAVAILABLE")
    if event == "pull_request":
        candidates = git("merge-base", "--all", base, head).decode().splitlines()
        if len(candidates) != 1:
            raise ValueError("AMBIGUOUS_MERGE_BASE")
        start = require_sha(candidates[0])
    else:
        start = base
    raw = git("diff", "--no-ext-diff", "--name-only", "--no-renames", "-z", start, head, "--")
    if raw and not raw.endswith(b"\0"):
        raise ValueError("INCOMPLETE_PATH_LIST")
    paths = raw.decode("utf-8").split("\0")[:-1] if raw else []
    if len(paths) != len(set(paths)) or any(not p or p.startswith("/") for p in paths):
        raise ValueError("INVALID_PATH_INVENTORY")
    return start, paths, hashlib.sha256(raw).hexdigest()


def glob_regex(pattern):
    """Supported repository glob subset; reject rather than guess other syntax."""
    if not pattern or any(c in pattern for c in "[]?+\\!"):
        raise ValueError("UNSUPPORTED_PATH_GLOB")
    result = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            result += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            result += ".*"
            i += 2
        elif pattern[i] == "*":
            result += "[^/]*"
            i += 1
        else:
            result += re.escape(pattern[i])
            i += 1
    return re.compile(result + r"\Z", re.DOTALL)


def compile_patterns(patterns):
    if not patterns or not any(not p.startswith("!") for p in patterns):
        raise ValueError("MISSING_POSITIVE_PATH_FILTER")
    return [(not p.startswith("!"), glob_regex(p.removeprefix("!"))) for p in patterns]


def matches(path, compiled):
    included = False
    for include, matcher in compiled:
        if matcher.fullmatch(path):
            included = include
    return included


def classify(paths, base_filters, head_filters):
    """Conservative union of both revisions; deletions/renames count as changes."""
    left, right = compile_patterns(base_filters), compile_patterns(head_filters)
    return [p for p in paths if matches(p, left) or matches(p, right)]


def workflow_filters(revision, workflow, event):
    source = git("show", revision + ":.github/workflows/" + workflow).decode("utf-8")
    selected = event
    if event == "push" and workflow in ("physics-native-ci.yml", "issue402-flow-native-p2-regression.yml"):
        # A main push does not dispatch these PR-only checks. Report applicable
        # source impact so prior integration evidence is not confused with PASS.
        selected = "pull_request"
    patterns = event_paths(source, selected)
    if patterns is None:
        raise ValueError("WORKFLOW_FILTER_UNAVAILABLE:" + workflow)
    return patterns, selected


def evaluate(event, payload):
    base, head = event_revisions(event, payload)
    start, paths, digest = inventory(event, base, head)
    result = {}
    for name in WORKFLOWS:
        old, event_kind = workflow_filters(base, name, event)
        new, _ = workflow_filters(head, name, event)
        affected = classify(paths, old, new)
        result[name] = {
            "applicability": "REQUIRED" if affected else "NO_PATH_MATCH",
            "matching_count": len(affected),
            "examples": affected[:10],
            "route": "PR_EVIDENCE_ONLY" if event_kind != event else "AUTOMATIC",
            "execution_verified": False,
        }
    return {
        "schema_version": 1, "event": event, "base_sha": base, "head_sha": head,
        "diff_start_sha": start, "changed_file_count": len(paths),
        "changed_paths_sha256": digest, "inventory_complete": True,
        "platform_path_limit_risk": len(paths) >= 300,
        "workflow_applicability": result,
        "manual_native_execution": "NOT_OBSERVED",
        "acceptance": "EVIDENCE_REQUIRED" if any(v["matching_count"] for v in result.values()) else "NO_PATH_MATCH",
        "scientific_acceptance": False,
    }


def self_test():
    rules = ["physics_app/**", "physics_harness/execution/**",
             "!physics_harness/execution/controller_*.py", "!**/*.md"]
    unrelated = ["docs/change_" + str(i) + ".md" for i in range(350)]
    assert classify(unrelated, rules, rules) == []
    mixed = unrelated + ["physics_app/src/kernel.C"]
    assert classify(mixed, rules, rules) == [mixed[-1]]
    assert classify(["physics_harness/execution/controller_future.py"], rules, rules) == []
    assert classify(["physics_harness/execution/controller_sub/actual.py"], rules, rules)
    assert classify(["physics_app/README.md"], rules, rules) == []
    assert classify(["physics_app/old.C"], rules, ["experiments/**"])
    assert classify(["physics_app/new.C"], ["experiments/**"], rules)
    assert not matches("a/b/c", compile_patterns(["a/*"]))
    assert matches("README.md", compile_patterns(["**/*.md"]))
    assert classify(["physics_app/src/kernel.C"], rules, rules + ["!physics_app/**"])
    try:
        compile_patterns(["physics_app/[ab]"])
    except ValueError:
        pass
    else:
        raise AssertionError("UNSUPPORTED_GLOB_ACCEPTED")
    try:
        require_sha("0" * 40)
    except ValueError:
        pass
    else:
        raise AssertionError("ZERO_BASE_ACCEPTED")
    print("REPOSITORY_IMPACT_SELF_TEST=PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--event")
    parser.add_argument("--event-name")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        report = evaluate(args.event_name, json.loads(Path(args.event).read_text()))
        print(json.dumps(report, sort_keys=True, ensure_ascii=True))
        # This is a classification receipt, not attestation of any domain run.
        print("REPOSITORY_IMPACT_INVENTORY=PASS")
        return 0
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print("REPOSITORY_IMPACT=HOLD", type(exc).__name__, str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
