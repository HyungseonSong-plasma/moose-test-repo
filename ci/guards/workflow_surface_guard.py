#!/usr/bin/env python3
"""Executable invariant for the GitHub Actions surface."""
from __future__ import annotations
import argparse, re, tempfile
from pathlib import Path

ENTRYPOINTS = {
    "ci.yml": {"push", "pull_request"},
    "harness-code.yml": {"push", "pull_request"},
    # Opt-in source scan: registered only for human workflow_dispatch.
    "harness-code-scan.yml": {"push", "workflow_dispatch"},
    "physics-code-ci.yml": {"push", "pull_request"},
    "physics-legacy-audit.yml": {"workflow_dispatch"},
    "physics-native-ci.yml": {"pull_request"},
    "repository-diagnostics.yml": {"workflow_dispatch"},
    "experiment.yml": {"workflow_dispatch"},
    "refactor.yml": {"workflow_dispatch"},
    "sol-runtime-integration.yml": {"push", "pull_request"},
    "ion-fvm-hybrid-staged-dt.yml": {"push", "pull_request", "workflow_dispatch"},
    "samuel-branch-delete.yml": {"push"},
    # Registered on main by PR #616: DD manual P3 is now REQUIRED.
    "issue541-arch-dd-p3-replay.yml": {"workflow_dispatch"},
    # Registered on main by PR #645: both S6 cases are now REQUIRED manual-only.
    "issue541-arch-s6-p3-p4-replay.yml": {"workflow_dispatch"},
}
REUSABLE = {
    "physics-build-base.yml": {"workflow_call"},
    "physics-runtime-producer.yml": {"workflow_call"},
    "physics-runtime-consumer.yml": {"workflow_call"},
    "physics-runtime-strip-estimate.yml": {"workflow_call"},
}
# Draft-lane routes are checked by exact filename and event when present, but
# are not required until their separately verified implementation is merged.
# No historical branch-only one-shot policy is waived.
OPTIONAL_ENTRYPOINTS = {
    # FLOW #548: source-bound P0/P1/P2 only (no push).
    "issue402-flow-native-p2-regression.yml": {"pull_request", "workflow_dispatch"},
}
FORBIDDEN_EVENTS = {
    "issue_comment", "issues", "discussion", "discussion_comment",
    "pull_request_review_comment",
}
REQUIRED_CI_PULL_REQUEST_TYPES = {"opened", "synchronize", "reopened", "edited"}
REQUIRED_CI_EDIT_FILTER_JOBS: set[str] = set()
REQUIRED_CI_UNCONDITIONAL_JOBS = {"validate"}
REQUIRED_CI_JOB_IF = (
    "github.event_name != 'pull_request' || "
    "github.event.action != 'edited' || "
    "github.event.changes.base != null"
)
TOP_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*(?:#.*)?$")
EVENT_KEY = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_-]*):")
ONE_SHOT_NAME = re.compile(r"^issue[1-9][0-9]*-[a-z0-9][a-z0-9-]*-once\.ya?ml$")

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
                    return {item.strip() for item in inner.split(",") if item.strip()}
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


def job_if_condition(text: str, name: str) -> str:
    block = job_block(text, name)
    if not block:
        return ""
    lines = block.splitlines()
    for i, line in enumerate(lines[1:], start=1):
        if not line.startswith("    if:"):
            continue
        value = line.split("if:", 1)[1].strip()
        if value not in {">", ">-", "|", "|-"}:
            return " ".join(value.split())
        parts: list[str] = []
        for child in lines[i + 1:]:
            if child.startswith("      "):
                parts.append(child.strip())
                continue
            if child.strip():
                break
        return " ".join(" ".join(parts).split())
    return ""


def one_shot_errors(name: str, text: str) -> list[str]:
    errors: list[str] = []
    observed = events(text)
    if observed != {"push"}:
        errors.append(
            f"{name}: one-shot events={sorted(observed)} expected=['push']"
        )
    if "branches: [main]" not in text:
        errors.append(f"{name}: one-shot must target branches: [main]")
    expected_path = f"paths: [.github/workflows/{name}]"
    if expected_path not in text:
        errors.append(
            f"{name}: one-shot must be self-path-triggered as {expected_path!r}"
        )
    return errors


def check(root: Path) -> list[str]:
    workflow_dir = root / ".github" / "workflows"
    actual = {p.name for p in workflow_dir.glob("*.yml")} | {p.name for p in workflow_dir.glob("*.yaml")}
    expected = set(ENTRYPOINTS) | set(REUSABLE)
    errors: list[str] = []
    one_shots = sorted(name for name in actual if ONE_SHOT_NAME.fullmatch(name))
    extra = sorted(actual - expected - set(OPTIONAL_ENTRYPOINTS) - set(one_shots))
    missing = sorted(expected - actual)
    if extra:
        errors.append(f"unauthorized workflow files: {extra}")
    for name in one_shots:
        path = workflow_dir / name
        errors.extend(one_shot_errors(name, path.read_text(encoding="utf-8")))
    if missing:
        errors.append(f"missing canonical workflow files: {missing}")
    for name, expected_events in {**ENTRYPOINTS, **REUSABLE, **OPTIONAL_ENTRYPOINTS}.items():
        path = workflow_dir / name
        if not path.is_file():
            continue
        observed = events(path.read_text(encoding="utf-8"))
        if observed != expected_events:
            errors.append(f"{name}: events={sorted(observed)} expected={sorted(expected_events)}")
        forbidden = observed & FORBIDDEN_EVENTS
        if forbidden:
            errors.append(f"{name}: forbidden conversational events={sorted(forbidden)}")
        if name == "harness-code-scan.yml":
            # The only push route is a deliberate request-file write on a
            # dedicated branch. Ordinary source pushes/PRs cannot trigger.
            workflow_text = path.read_text(encoding="utf-8")
            expected_push = (
                "  push:\n"
                "    branches: [issue-758-harness-scan-dispatch]\n"
                "    paths: [automation/harness-scan/request.json]\n"
            )
            if expected_push not in workflow_text:
                errors.append("harness-code-scan.yml: unauthorized request branch/path")
        if name == "ci.yml":
            workflow_text = path.read_text(encoding="utf-8")
            pr_types = pull_request_types(workflow_text)
            if pr_types != REQUIRED_CI_PULL_REQUEST_TYPES:
                errors.append("ci.yml: pull_request types=" f"{sorted(pr_types)} expected=" f"{sorted(REQUIRED_CI_PULL_REQUEST_TYPES)}")
            for job in sorted(REQUIRED_CI_UNCONDITIONAL_JOBS):
                block = job_block(workflow_text, job)
                if not block:
                    errors.append(f"ci.yml: required job missing: {job}")
                    continue
                condition = job_if_condition(workflow_text, job)
                if condition:
                    errors.append(f"ci.yml: {job} must not have job-level if={condition!r}")
    experiment = ((workflow_dir / "experiment.yml").read_text(encoding="utf-8") if (workflow_dir / "experiment.yml").is_file() else "")
    refactor = ((workflow_dir / "refactor.yml").read_text(encoding="utf-8") if (workflow_dir / "refactor.yml").is_file() else "")
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
            if name == "experiment.yml": body += "run-name: Issue_${{ inputs.issue }}_experiments${{ inputs.sequence }}\n"
            if name == "refactor.yml": body += "run-name: Issue_${{ inputs.issue }}_refactor${{ inputs.sequence }}\n"
            body += "on:\n"
            for event in sorted(allowed_events):
                if name == "ci.yml" and event == "pull_request":
                    body += "  pull_request:\n    branches: [main]\n    types: [" + ", ".join(sorted(REQUIRED_CI_PULL_REQUEST_TYPES)) + "]\n"
                elif name == "harness-code-scan.yml" and event == "push":
                    body += "  push:\n    branches: [issue-758-harness-scan-dispatch]\n    paths: [automation/harness-scan/request.json]\n"
                else:
                    body += f"  {event}:\n"
            if name == "ci.yml":
                body += "jobs:\n"
                for job in sorted(REQUIRED_CI_UNCONDITIONAL_JOBS):
                    body += f"  {job}:\n    runs-on: ubuntu-latest\n    steps: []\n"
            else:
                body += "jobs:\n  x:\n    runs-on: ubuntu-latest\n    steps: []\n"
            (workflow_dir / name).write_text(body)
        for name, allowed_events in REUSABLE.items():
            body = "name: x\non:\n" + "".join(f"  {event}:\n" for event in sorted(allowed_events)) + "jobs: {}\n"
            (workflow_dir / name).write_text(body)
        assert not check(root), check(root)
        # DD registration on default main is binding: absence, disabling or
        # adding push to its maintained manual trigger is a policy failure.
        # Dedicated request branch is the only allowed automated entrypoint.
        scan_manual = workflow_dir / "harness-code-scan.yml"
        scan_bytes = scan_manual.read_text(encoding="utf-8")
        scan_manual.unlink()
        assert any("missing canonical workflow files:" in error and
                   "harness-code-scan.yml" in error for error in check(root))
        scan_manual.write_text(
            scan_bytes.replace("  workflow_dispatch:", "  push:", 1),
            encoding="utf-8",
        )
        assert any("harness-code-scan.yml: events=" in error
                   for error in check(root))
        scan_manual.write_text(
            scan_bytes.replace("    branches: [issue-758-harness-scan-dispatch]",
                               "    branches: [main]", 1),
            encoding="utf-8",
        )
        assert any("unauthorized request branch/path" in error for error in check(root))
        scan_manual.write_text(
            scan_bytes.replace("    paths: [automation/harness-scan/request.json]",
                               "    paths: [README.md]", 1),
            encoding="utf-8",
        )
        assert any("unauthorized request branch/path" in error for error in check(root))
        scan_manual.write_text(scan_bytes, encoding="utf-8")
        assert not check(root), check(root)
        dd_manual = workflow_dir / "issue541-arch-dd-p3-replay.yml"
        dd_bytes = dd_manual.read_text(encoding="utf-8")
        dd_manual.unlink()
        assert any("missing canonical workflow files:" in error and
                   "issue541-arch-dd-p3-replay.yml" in error for error in check(root))
        dd_manual.write_text(dd_bytes.replace("  workflow_dispatch:", "  push:", 1), encoding="utf-8")
        assert any("issue541-arch-dd-p3-replay.yml: events=" in error for error in check(root))
        dd_manual.write_text(dd_bytes.replace("  workflow_dispatch:", "  workflow_dispatch:\n  push:", 1), encoding="utf-8")
        assert any("issue541-arch-dd-p3-replay.yml: events=" in error for error in check(root))
        dd_manual.write_text(dd_bytes, encoding="utf-8")
        assert not check(root), check(root)
        # S6 is now registered on main too: reject missing, changed or
        # additional automatic events independently of DD and FLOW.
        s6_manual = workflow_dir / "issue541-arch-s6-p3-p4-replay.yml"
        s6_bytes = s6_manual.read_text(encoding="utf-8")
        s6_manual.unlink()
        assert any("missing canonical workflow files:" in error and
                   "issue541-arch-s6-p3-p4-replay.yml" in error for error in check(root))
        s6_manual.write_text(s6_bytes.replace("  workflow_dispatch:", "  push:", 1), encoding="utf-8")
        assert any("issue541-arch-s6-p3-p4-replay.yml: events=" in error for error in check(root))
        s6_manual.write_text(s6_bytes.replace("  workflow_dispatch:", "  workflow_dispatch:\n  push:", 1), encoding="utf-8")
        assert any("issue541-arch-s6-p3-p4-replay.yml: events=" in error for error in check(root))
        s6_manual.write_text(s6_bytes, encoding="utf-8")
        assert not check(root), check(root)
        ci_path = workflow_dir / "ci.yml"
        valid_ci = ci_path.read_text(encoding="utf-8")
        ci_path.write_text(valid_ci.replace("edited, ", ""), encoding="utf-8")
        assert any("pull_request types=" in error for error in check(root))
        ci_path.write_text(valid_ci, encoding="utf-8")
        assert not check(root), check(root)
        invalid_filter_ci = valid_ci.replace(
            "  validate:\n    runs-on: ubuntu-latest\n",
            "  validate:\n    if: false\n    runs-on: ubuntu-latest\n",
            1,
        )
        ci_path.write_text(invalid_filter_ci, encoding="utf-8")
        filter_errors = [error for error in check(root) if "must not have job-level if=" in error]
        assert len(filter_errors) == 1, filter_errors
        ci_path.write_text(valid_ci, encoding="utf-8")
        assert not check(root), check(root)
        one_shot_name = "issue310-example-once.yml"
        (workflow_dir / one_shot_name).write_text(
            "name: One-shot Issue 310 example\n"
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
            f"    paths: [.github/workflows/{one_shot_name}]\n"
            "jobs: {}\n",
            encoding="utf-8",
        )
        assert not check(root), check(root)
        (workflow_dir / one_shot_name).write_text(
            "name: unsafe\n"
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
            "    paths: [README.md]\n"
            "jobs: {}\n",
            encoding="utf-8",
        )
        assert any("self-path-triggered" in error for error in check(root))
        (workflow_dir / one_shot_name).unlink()

        # FLOW remains optional; both registered DD and S6 are required.
        assert not check(root), check(root)
        for name, allowed_events in OPTIONAL_ENTRYPOINTS.items():
            path = workflow_dir / name
            body = "name: staged\non:\n" + "".join(
                f"  {event}:\n" for event in sorted(allowed_events)
            ) + "jobs: {}\n"
            path.write_text(body, encoding="utf-8")
            assert not check(root), (name, check(root))
            # A previously approved route with an extra push must fail.
            path.write_text(body.replace("on:\n", "on:\n  push:\n", 1), encoding="utf-8")
            assert any(f"{name}: events=" in error for error in check(root)), name
            path.write_text(body, encoding="utf-8")
        assert not check(root), check(root)
        rogue = workflow_dir / "issue541-arch-rogue-p3.yml"
        rogue.write_text("name: unsafe\non:\n  workflow_dispatch:\njobs: {}\n", encoding="utf-8")
        assert any("unauthorized workflow files:" in error for error in check(root))
        rogue.unlink()
        for name in OPTIONAL_ENTRYPOINTS:
            (workflow_dir / name).unlink()
        assert not check(root), check(root)

        (workflow_dir / "bad.yml").write_text("name: bad\non:\n  issue_comment:\njobs: {}\n")
        assert check(root)
    print("WORKFLOW_SURFACE_GUARD_SELF_TEST=PASS")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    errors = check(Path(args.root).resolve())
    if errors:
        print("WORKFLOW_SURFACE_GUARD=FAIL")
        for error in errors: print(error)
        return 1
    print("WORKFLOW_SURFACE_GUARD=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
