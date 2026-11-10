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
    keys, outputs, special_variants = set(), set(), set()
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
            variant = item.get("variant", "full")
            if variant not in {"full", "diagnostic", "completion", "archive"}:
                raise WorkflowContractError("SPECIAL_CI_VARIANT_INVALID")
            selector = (item.get("issue"), variant)
            if selector in special_variants:
                raise WorkflowContractError("SPECIAL_CI_VARIANT_DUPLICATE")
            special_variants.add(selector)
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
          variant: str = "full", records: list[dict] | None = None) -> dict:
    """Choose an explicit reviewed route; NEVER guess based on a PR title."""
    pool = records if records is not None else profiles()
    matches = [item for item in pool if item["purpose"] == purpose and
               (purpose == "general" and issue is None and variant == "full" or
                purpose == "special" and item.get("issue") == issue and
                item.get("variant", "full") == variant)]
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
        for name in ("validate", "runtime-smoke", "boltzmann-eepf-controls", "plasma_native_regression"):
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
    variant = profile.get("variant", "full")
    allowed_job = {
        "full": "issue493-public-p3-native",
        "diagnostic": "issue493-public-p3-diagnostic",
        "completion": "issue493-public-p3-b-completion",
        "archive": "issue493-public-p3-archive-b",
    }[variant]
    if variant == "archive":
        if job_names != ["issue493-public-p3-archive-b", "issue493-public-p3-archive-c",
                         "issue493-public-p4-bc-compare"]:
            raise WorkflowContractError("SPECIAL_ARCHIVE_JOB_ALLOWLIST_MISMATCH")
    elif len(job_names) != 1 or job_names[0] != allowed_job:
        raise WorkflowContractError("SPECIAL_JOB_ALLOWLIST_MISMATCH")
    common = (re.search(r"^    strategy:\n      fail-fast: false\n      max-parallel: 2", template, re.MULTILINE)
              and "public_p3_run.py" in template
              and "github.sha" in template
              and "github.event.pull_request." not in template
              and "secrets." not in template
              and not re.search(r"^    if:", template, re.MULTILINE))
    if not common:
        raise WorkflowContractError("SPECIAL_EXECUTION_POLICY")
    if variant == "full":
        if "--mode full --authorize-full-p3" not in template:
            raise WorkflowContractError("SPECIAL_FULL_AUTHORIZATION_MISSING")
    elif variant == "diagnostic":
        if ("--mode diagnostic --timeout-seconds 600" not in template
                or "--authorize-full-p3" in template
                or "--mode full" in template
                or "--timeout-seconds 8100" in template
                or "check_public_p3_diagnostic.py" not in template
                or "case: ['417', '941']" not in template):
            raise WorkflowContractError("SPECIAL_DIAGNOSTIC_BOUNDARY")
    elif variant == "completion":
        if ("--mode complete-b --authorize-full-p3 --timeout-seconds 20400" not in template
                or "check_public_p3_b_completion.py" not in template
                or "case: ['417', '941']" not in template
                or "timeout-minutes: 360" not in template
                or "--mode full" in template
                or "--mode diagnostic" in template
                or "--timeout-seconds 8100" in template):
            raise WorkflowContractError("SPECIAL_COMPLETION_BOUNDARY")
    elif variant == "archive":
        if (template.count("--mode complete-b --authorize-full-p3 --timeout-seconds 20400") != 1
                or template.count("--mode complete-c --authorize-full-p3 --timeout-seconds 20400") != 1
                or "archive_public_p3_results.py" not in template
                or "p4_compare_public_bc.py" not in template
                or "actions/download-artifact@v4" not in template
                or "retention-days: 90" not in template
                or "source-bound-binary" not in template
                or "needs: [issue493-public-p3-archive-b, issue493-public-p3-archive-c]" not in template
                or "timeout-minutes: 360" not in template
                or "--mode full" in template or "secrets." in template):
            raise WorkflowContractError("SPECIAL_ARCHIVE_PROVENANCE_OR_DATA_BOUNDARY")
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
    assert route("special", issue=493, variant="diagnostic", records=entries)["trigger"] == "self_path_main_once"
    assert route("special", issue=493, variant="completion", records=entries)["trigger"] == "self_path_main_once"
    for selected in ("full", "diagnostic", "completion", "archive"):
        special = route("special", issue=493, variant=selected, records=entries)
        assert special["activation"] in {"deferred", "active"}
        assert (ROOT / special["output"] in outputs()) == (special["activation"] == "active")
    # Regression: preserve the new required Physics PR native validation gate.
    assert re.search(r"^  plasma_native_regression:\s*$",
                     render(ROOT, route("general", records=entries)), re.MULTILINE)
    # Reject path escape and noncanonical path spellings before writing YAML.
    for unsafe in ("ci/workflow_templates/../workflow.yml",
                   "ci/workflow_templates/sub//workflow.yml"):
        try:
            safe_relative(unsafe, prefix="ci/workflow_templates/")
        except WorkflowContractError:
            pass
        else:
            raise AssertionError("unsafe workflow template path was accepted")
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
    parser.add_argument("--variant", choices=("full", "diagnostic", "completion", "archive"), default="full")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        elif args.route:
            result = route(args.route, issue=args.issue, variant=args.variant,
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
