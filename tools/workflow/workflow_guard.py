#!/usr/bin/env python3
"""Executable invariant for the GitHub Actions surface."""
from __future__ import annotations
import argparse, re, tempfile
from pathlib import Path

ENTRYPOINTS = {
    "ci.yml": {"push", "pull_request"},
    "experiment.yml": {"workflow_dispatch"},
    "refactor.yml": {"workflow_dispatch"},\n    "branch-cleanup-prune-once.yml": {"push"},
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
            body += "on:\n" + "".join(
                f"  {event}:\n" for event in sorted(allowed_events)
            )
            body += "jobs:\n  x:\n    runs-on: ubuntu-latest\n    steps: []\n"
            (workflow_dir / name).write_text(body)
        for name, allowed_events in REUSABLE.items():
            body = "name: x\non:\n" + "".join(
                f"  {event}:\n" for event in sorted(allowed_events)
            )
            body += "jobs: {}\n"
            (workflow_dir / name).write_text(body)
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
