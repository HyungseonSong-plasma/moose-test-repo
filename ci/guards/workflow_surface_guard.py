#!/usr/bin/env python3
"""Executable invariant for the GitHub Actions surface."""
from __future__ import annotations
import argparse, re, tempfile
from pathlib import Path

ENTRYPOINTS = {
    "ci.yml": {"push", "pull_request"},
    "experiment.yml": {"workflow_dispatch"},
    "refactor.yml": {"workflow_dispatch"},
}
REUSABLE = {
    "physics-build-base.yml": {"workflow_call"},
    "physics-runtime-producer.yml": {"workflow_call"},
    "physics-runtime-consumer.yml": {"workflow_call"},
    "physics-runtime-strip-estimate.yml": {"workflow_call"},
}
FORBIDDEN_EVENTS = {
    "issue_comment", "issues", "discussion", "discussion_comment",
    "pull_request_review_comment",
}
REQUIRED_CI_PULL_REQUEST_TYPES = {"opened", "synchronize", "reopened", "edited"}
REQUIRED_CI_EDIT_FILTER_JOBS = {"validate", "runtime-smoke"}
REQUIRED_CI_CONCURRENCY_GROUP = "repository-ci-${{ github.event.pull_request.number || github.ref }}"
TOP_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*(?:#.*)?$")
EVENT_KEY = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_-]*):")

def events(text: str) -> set[str]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("on: ["):
            inner = line.split("[", 1)[1].rsplit("]", 1)[0]
            return {item.strip() for item in inner.split(",") if item.strip()}
        if line == "on:":
            result: set[str] = set()
            for child in lines[i + 1:]:
                if child and not child.startswith(" ") and TOP_KEY.match(child):
                    break
                match = EVENT_KEY.match(child)
                if match:
                    result.add(match.group(1))
            return result
    return set()

def pull_request_types(text: str) -> set[str]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line == "  pull_request:":
            for child in lines[i + 1:]:
                if child.startswith("  ") and not child.startswith("    "):
                    break
                stripped = child.strip()
                if stripped.startswith("types: [") and stripped.endswith("]"):
                    inner = stripped.split("[", 1)[1].rsplit("]", 1)[0]
                    return {
                        item.strip()
                        for item in inner.split(",")
                        if item.strip()
                    }
            return set()
    return set()


def job_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line == f"  {name}:":
            start = i
            break
    if start is None:
        return ""
    out = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        out.append(line)
    return "\n".join(out)


def check(root: Path) -> list[str]:
    workflow_dir = root / ".github" / "workflows"
    actual = {p.name for p in workflow_dir.glob("*.yml")} | {
        p.name for p in workflow_dir.glob("*.yaml")
    }
    expected = set(ENTRYPOINTS) | set(REUSABLE)
    errors: list[str] = []
    extra = sorted(actual - expected)
    missing = sorted(expected - actual)
    if extra:
        errors.append(f"unauthorized workflow files: {extra}")
    if missing:
        errors.append(f"missing canonical workflow files: {missing}")
    for name, expected_events in {**ENTRYPOINTS, **REUSABLE}.items():
        path = workflow_dir / name
        if not path.is_file():
            continue
        observed = events(path.read_text(encoding="utf-8"))
        if observed != expected_events:
            errors.append(
                f"{name}: events={sorted(observed)} expected={sorted(expected_events)}"
            )
        forbidden = observed & FORBIDDEN_EVENTS
        if forbidden:
            errors.append(
                f"{name}: forbidden conversational events={sorted(forbidden)}"
            )
        if name == "ci.yml":
            workflow_text = path.read_text(encoding="utf-8")
            if f"group: {REQUIRED_CI_CONCURRENCY_GROUP}" not in workflow_text:
                errors.append("ci.yml: canonical concurrency group missing")
            if "cancel-in-progress: true" not in workflow_text:
                errors.append("ci.yml: cancel-in-progress must be true")
            pr_types = pull_request_types(workflow_text)
            if pr_types != REQUIRED_CI_PULL_REQUEST_TYPES:
                errors.append(
                    "ci.yml: pull_request types="
                    f"{sorted(pr_types)} expected="
                    f"{sorted(REQUIRED_CI_PULL_REQUEST_TYPES)}"
                )
            for job in sorted(REQUIRED_CI_EDIT_FILTER_JOBS):
                block = job_block(workflow_text, job)
                if not block:
                    errors.append(f"ci.yml: required job missing: {job}")
                    continue
                if "github.event.action != 'edited'" not in block:
                    errors.append(f"ci.yml: {job} missing edited-action filter")
                if "github.event.changes.base != null" not in block:
                    errors.append(f"ci.yml: {job} missing base-change edit filter")
    experiment = (
        (workflow_dir / "experiment.yml").read_text(encoding="utf-8")
        if (workflow_dir / "experiment.yml").is_file() else ""
    )
    refactor = (
        (workflow_dir / "refactor.yml").read_text(encoding="utf-8")
        if (workflow_dir / "refactor.yml").is_file() else ""
    )
    if "Issue_${{ inputs.issue }}_experiments${{ inputs.sequence }}" not in experiment:
        errors.append("experiment.yml: canonical dynamic run-name missing")
    if "Issue_${{ inputs.issue }}_refactor${{ inputs.sequence }}" not in refactor:
        errors.append("refactor.yml: canonical dynamic run-name missing")
    return errors

def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        for name, allowed_events in ENTRYPOINTS.items():
            body = "name: x\n"
            if name == "experiment.yml":
                body += "run-name: Issue_${{ inputs.issue }}_experiments${{ inputs.sequence }}\n"
            if name == "refactor.yml":
                body += "run-name: Issue_${{ inputs.issue }}_refactor${{ inputs.sequence }}\n"
            if name == "ci.yml":
                body += "concurrency:\n"
                body += f"  group: {REQUIRED_CI_CONCURRENCY_GROUP}\n"
                body += "  cancel-in-progress: true\n"
            body += "on:\n"
            for event in sorted(allowed_events):
                if name == "ci.yml" and event == "pull_request":
                    body += "  pull_request:\n"
                    body += "    branches: [main]\n"
                    body += (
                        "    types: ["
                        + ", ".join(sorted(REQUIRED_CI_PULL_REQUEST_TYPES))
                        + "]\n"
                    )
                else:
                    body += f"  {event}:\n"
            if name == "ci.yml":
                body += "jobs:\n"
                for job in sorted(REQUIRED_CI_EDIT_FILTER_JOBS):
                    body += f"  {job}:\n"
                    body += "    if: >-\n"
                    body += "      github.event_name != 'pull_request' ||\n"
                    body += "      github.event.action != 'edited' ||\n"
                    body += "      github.event.changes.base != null\n"
                    body += "    runs-on: ubuntu-latest\n"
                    body += "    steps: []\n"
            else:
                body += "jobs:\n  x:\n    runs-on: ubuntu-latest\n    steps: []\n"
            (workflow_dir / name).write_text(body)
        for name, allowed_events in REUSABLE.items():
            body = "name: x\non:\n" + "".join(
                f"  {event}:\n" for event in sorted(allowed_events)
            )
            body += "jobs: {}\n"
            (workflow_dir / name).write_text(body)
        assert not check(root), check(root)
        ci_path = workflow_dir / "ci.yml"
        valid_ci = ci_path.read_text(encoding="utf-8")
        ci_path.write_text(
            valid_ci.replace("edited, ", ""),
            encoding="utf-8",
        )
        assert any("pull_request types=" in error for error in check(root))
        ci_path.write_text(valid_ci, encoding="utf-8")
        assert not check(root), check(root)
        ci_path.write_text(
            valid_ci.replace("  cancel-in-progress: true\n", "  cancel-in-progress: false\n"),
            encoding="utf-8",
        )
        assert any("cancel-in-progress must be true" in error for error in check(root))
        ci_path.write_text(valid_ci, encoding="utf-8")
        assert not check(root), check(root)
        ci_path.write_text(
            valid_ci.replace(
                "      github.event.changes.base != null\n",
                "      true\n",
                1,
            ),
            encoding="utf-8",
        )
        filter_errors = [
            error for error in check(root)
            if "missing base-change edit filter" in error
        ]
        assert len(filter_errors) == 1, filter_errors
        ci_path.write_text(valid_ci, encoding="utf-8")
        assert not check(root), check(root)
        (workflow_dir / "bad.yml").write_text(
            "name: bad\non:\n  issue_comment:\njobs: {}\n"
        )
        assert check(root)
    print("WORKFLOW_SURFACE_GUARD_SELF_TEST=PASS")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--root", default=str(Path(__file__).resolve().parents[2])
    )
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    errors = check(Path(args.root).resolve())
    if errors:
        print("WORKFLOW_SURFACE_GUARD=FAIL")
        for error in errors:
            print(error)
        return 1
    print("WORKFLOW_SURFACE_GUARD=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
