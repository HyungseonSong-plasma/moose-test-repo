#!/usr/bin/env python3
"""Deterministic, fail-closed routing of general versus purpose-built CI.

GitHub Actions YAML is STATIC once committed. This build-time generator
selects a reviewed profile based on a constrained manifest; it never edits
workflow definitions during a running job and never dispatches an experiment.
Special one-shot workflows run only on an authorized main merge that changes
their own workflow path; general CI remains the existing mandatory check.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("ci/workflow_profiles.json")
SPECIAL_OUTPUT = re.compile(r"^issue[1-9][0-9]*-[a-z0-9][a-z0-9-]*-once\.yml$")
JOB = re.compile(r"^  ([a-z][a-z0-9-]*):\s*$", re.MULTILINE)
ISSUE_JOB = re.compile(r"^  issue[1-9][0-9]*-[a-z0-9-]*:\s*$", re.MULTILINE)


class WorkflowContractError(ValueError):
    pass


def safe_relative(value: str, *, prefix: str) -> Path:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise WorkflowContractError("WORKFLOW_PATH_OUTSIDE_APPROVED_ROOT")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or str(p) != value:
        raise WorkflowContractError("WORKFLOW_PATH_NOT_NORMALIZED")
    return Path(*p.parts)


def profiles(root: Path = ROOT) -> list[dict]:
    data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise WorkflowContractError("WORKFLOW_MANIFEST_SCHEMA")
    records = data.get("profiles")
    if not isinstance(records, list) or not records:
        raise WorkflowContractError("WORKFLOW_PROFILES_ABSENT")
    keys, outputs = set(), set()
    for item in records:
        if not isinstance(item, dict):
            raise WorkflowContractError("WORKFLOW_PROFILE_INVALID")
        key = item.get("key")
        purpose = item.get("purpose")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", key):
            raise WorkflowContractError("WORKFLOW_PROFILE_KEY")
        template = safe_relative(item.get("template"), prefix="ci/workflow_templates/")
        output = safe_relative(item.get("output"), prefix=".github/workflows/")
        if key in keys or output in outputs:
            raise WorkflowContractError("WORKFLOW_PROFILE_DUPLICATE")
        keys.add(key)
        outputs.add(output)
        if purpose == "general":
            if (item.get("trigger") != "push_pull_request" or
                    item.get("output") != ".github/workflows/ci.yml" or
                    key != "general"):
                raise WorkflowContractError("GENERAL_CI_ROUTE_INVALID")
        elif purpose == "special":
            filename = output.name
            if (item.get("trigger") != "self_path_main_once" or
                    item.get("activation") not in {"deferred", "active"} or
                    not SPECIAL_OUTPUT.fullmatch(filename) or
                    not isinstance(item.get("issue"), int) or
                    item["issue"] <= 0 or
                    not filename.startswith(f"issue{item['issue']}-")):
                raise WorkflowContractError("SPECIAL_CI_ROUTE_INVALID")
        else:
            raise WorkflowContractError("UNRECOGNIZED_WORKFLOW_PURPOSE")
        if not (root / template).is_file():
            raise WorkflowContractError("WORKFLOW_TEMPLATE_MISSING")
    if sum(item["purpose"] == "general" for item in records) != 1:
        raise WorkflowContractError("GENERAL_CI_NOT_UNIQUE")
    return records


def route(purpose: str, *, issue: int | None = None,
          records: list[dict] | None = None) -> dict:
    """Choose an explicit reviewed route; NEVER guess based on a PR title."""
    pool = records if records is not None else profiles()
    matches = [item for item in pool if item["purpose"] == purpose and
               (purpose == "general" and issue is None or
                purpose == "special" and item.get("issue") == issue)]
    if len(matches) != 1:
        raise WorkflowContractError("WORKFLOW_ROUTE_NOT_AUTHORIZED")
    return matches[0]


def render(root: Path, profile: dict) -> str:
    template = (root / profile["template"]).read_text(encoding="utf-8")
    if not template.endswith("\n"):
        raise WorkflowContractError("WORKFLOW_TEMPLATE_MISSING_NEWLINE")
    if profile["purpose"] == "general":
        if not template.startswith("name: Repository CI\n"):
            raise WorkflowContractError("GENERAL_NAME_CONTRACT")
        if ("  push:\n    branches: [main]" not in template or
                "  pull_request:\n    branches: [main]" not in template):
            raise WorkflowContractError("GENERAL_TRIGGER_CONTRACT")
        for name in ("validate", "runtime-smoke", "boltzmann-eepf-controls"):
            if not re.search(r"^  " + re.escape(name) + r":\s*$", template,
                             re.MULTILINE):
                raise WorkflowContractError("GENERAL_REQUIRED_JOB_MISSING")
        if ISSUE_JOB.search(template) or re.search(
                r"github\.event\.pull_request\.number\s*==", template):
            raise WorkflowContractError("GENERAL_CONTAINS_PR_SPECIFIC_JOB")
        # General remains exactly what is checked in, with mandatory job names.
        return template
    if template.startswith("jobs:") or template.startswith("on:"):
        raise WorkflowContractError("SPECIAL_TEMPLATE_NOT_JOB_ONLY")
    job_names = JOB.findall(template)
    if len(job_names) != 1 or job_names[0] != "issue493-public-p3-native":
        raise WorkflowContractError("SPECIAL_JOB_ALLOWLIST_MISMATCH")
    if (not re.search(r"^    strategy:\n      fail-fast: false\n      max-parallel: 2", template, re.MULTILINE)
            or "public_p3_run.py" not in template
            or "github.sha" not in template
            or "github.event.pull_request." in template
            or "secrets." in template
            or re.search(r"^    if:", template, re.MULTILINE)):
        raise WorkflowContractError("SPECIAL_EXECUTION_POLICY")
    name, output = profile["name"], profile["output"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9 _-]{4,100}", name):
        raise WorkflowContractError("SPECIAL_WORKFLOW_NAME")
    return (
        f"name: {name}\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        f"    paths: [{output}]\n"
        "permissions:\n"
        "  contents: read\n"
        "jobs:\n" + template
    )


def outputs(root: Path = ROOT) -> dict[Path, str]:
    return {
        root / record["output"]: render(root, record)
        for record in profiles(root)
        if record["purpose"] == "general" or record.get("activation") == "active"
    }


def check(root: Path = ROOT) -> list[str]:
    issues = []
    for record in profiles(root):
        path = root / record["output"]
        if record.get("activation") == "deferred":
            if path.exists():
                issues.append(f"WORKFLOW_DEFERRED_OUTPUT_PRESENT: {path.relative_to(root)}")
            continue
        expected = render(root, record)
        if not path.is_file():
            issues.append(f"WORKFLOW_GENERATED_OUTPUT_MISSING: {path.relative_to(root)}")
        elif path.read_text(encoding="utf-8") != expected:
            issues.append(f"WORKFLOW_GENERATED_OUTPUT_DRIFT: {path.relative_to(root)}")
    return issues


def self_test() -> None:
    entries = profiles()
    assert route("general", records=entries)["output"] == ".github/workflows/ci.yml"
    assert route("special", issue=493, records=entries)["trigger"] == "self_path_main_once"
    assert route("special", issue=493, records=entries)["activation"] == "deferred"
    assert not any("issue493" in str(p) for p in outputs())
    for purpose, issue in (("special", 492), ("unsupported", None),
                           ("general", 493)):
        try:
            route(purpose, issue=issue, records=entries)
        except WorkflowContractError:
            pass
        else:
            raise AssertionError("unknown workflow intent was accepted")
    for record in entries:
        out = render(ROOT, record)
        if record["purpose"] == "special":
            assert "paths: [.github/workflows/" in out
            assert "  pull_request:" not in out
            assert not re.search(r"^    if:", out, re.MULTILINE)
        elif record["purpose"] == "general":
            assert not ISSUE_JOB.search(out)
    print("WORKFLOW_HARNESS_SELF_TEST=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--route", choices=["general", "special"])
    parser.add_argument("--issue", type=int)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        elif args.route:
            result = route(args.route, issue=args.issue,
                           records=profiles(args.root))
            print(json.dumps(result, sort_keys=True))
        elif args.generate:
            for path, content in outputs(args.root).items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                print("GENERATED", path.relative_to(args.root))
        else:
            problems = check(args.root)
            if problems:
                for problem in problems:
                    print(problem, file=sys.stderr)
                return 1
            print("WORKFLOW_HARNESS_CHECK=PASS")
    except (WorkflowContractError, OSError, ValueError) as exc:
        print(f"WORKFLOW_HARNESS_HOLD: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
