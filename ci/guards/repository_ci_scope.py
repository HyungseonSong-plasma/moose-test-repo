#!/usr/bin/env python3
"""Repository Integration Contract Verification: exactly one owner per old gate.

The checked-in contract inventories the formerly overbroad general CI.
Static source checks never claim runtime, scientific or semantic equivalence.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = Path("ci/contracts/repository_ci_scope_v1.json")
JOBS = re.compile(r"^  ([a-z][a-z0-9_-]*):\s*$", re.MULTILINE)
STEPS = re.compile(r"^      - (?:name|uses): (.+)$", re.MULTILINE)


def job_block(source: str, name: str) -> str:
    match = re.search(r"^  " + re.escape(name) + r":\s*$",
                      source, re.MULTILINE)
    if not match:
        return ""
    tail = source[match.start():]
    second = JOBS.search(tail, match.end() - match.start())
    return tail[:second.start()] if second else tail


def inspect(sources: dict[str, str], contract: dict) -> list[str]:
    problems: list[str] = []
    if (contract.get("schema_version") != 1
            or contract.get("contract") != "repository.integration.v0.1"):
        return ["INVALID_REPOSITORY_CI_CONTRACT"]
    owners = contract["workflow_owners"]
    if set(owners) != set(sources):
        return ["OWNER_WORKFLOW_SET_MISMATCH"]

    all_jobs: dict[str, str] = {}
    for path, expected in owners.items():
        source = sources[path]
        if "\njobs:\n" not in source:
            problems.append(f"{path}: JOBS_MISSING")
            continue
        actual = set(JOBS.findall(source.split("\njobs:\n", 1)[1]))
        required = set(expected["jobs"])
        if actual != required:
            problems.append(
                f"{path}: JOB_OWNER_MISMATCH expected={sorted(required)} "
                f"actual={sorted(actual)}"
            )
        for job in actual:
            if job in all_jobs:
                problems.append(
                    f"DUPLICATE_JOB_OWNER:{job}:{all_jobs[job]}:{path}"
                )
            all_jobs[job] = path
        if "required_steps" in expected:
            target = ("validate" if path.endswith("/ci.yml")
                      else "physics_code_validate")
            block = job_block(source, target)
            found = STEPS.findall(block)
            if len(found) != len(set(found)):
                problems.append(f"{path}: DUPLICATE_VALIDATE_STEP")
            if set(found) != set(expected["required_steps"]):
                problems.append(
                    f"{path}: VALIDATION_STEP_OWNER_MISMATCH "
                    f"missing={sorted(set(expected['required_steps']) - set(found))} "
                    f"extra={sorted(set(found) - set(expected['required_steps']))}"
                )

    core = sources[".github/workflows/ci.yml"]
    if ("paths-ignore:" in core or
            re.search(r"^    paths:\s*$", core, re.MULTILINE)):
        problems.append("REPOSITORY_CI_MUST_RUN_FOR_ALL_CHANGES")
    if ("  push:\n    branches: [main]" not in core
            or "  pull_request:\n    branches: [main]" not in core):
        problems.append("CORE_TRIGGER_MISSING")
    if set(JOBS.findall(core.split("\njobs:\n", 1)[1])) != {"validate"}:
        problems.append("REPOSITORY_CI_NOT_INTEGRATION_ONLY")
    main_job = job_block(core, "validate")
    if re.search(r"^    if:", main_job, re.MULTILINE):
        problems.append("REQUIRED_CORE_GATE_CONDITIONALLY_SKIPPED")
    exact_ref = "ref: $" + "{{ github.event.pull_request.head.sha || github.sha }}"
    if exact_ref not in main_job:
        problems.append("CORE_NOT_EXACT_HEAD")

    for workflow, required_paths in contract["domain_required_path_coverage"].items():
        contents = sources[workflow]
        if "    types: [opened, synchronize, reopened]" not in contents:
            problems.append(f"{workflow}: CONTENT_PR_EVENTS_MISSING")
        for pattern in required_paths:
            if f"      - '{pattern}'" not in contents:
                problems.append(f"{workflow}: CHANGED_SOURCE_PATH_UNROUTED:{pattern}")
    diagnostics = sources[".github/workflows/repository-diagnostics.yml"]
    if "  workflow_dispatch:\n" not in diagnostics:
        problems.append("DIAGNOSTIC_MANUAL_TRIGGER_ABSENT")
    if re.search(r"^  (?:pull_request|push):", diagnostics, re.MULTILINE):
        problems.append("HISTORICAL_DIAGNOSTIC_AUTOMATICALLY_TRIGGERED")
    return sorted(problems)


def self_test(sources: dict[str, str], contract: dict) -> None:
    if failures := inspect(sources, contract):
        raise AssertionError(f"BASELINE_SCOPE_CONTRACT_INVALID: {failures}")
    ci = ".github/workflows/ci.yml"
    mutated = dict(sources)
    mutated[ci] = sources[ci].replace(
        "  validate:\n", "  validate:\n    if: false\n", 1
    )
    assert "REQUIRED_CORE_GATE_CONDITIONALLY_SKIPPED" in inspect(mutated, contract)
    mutated[ci] = sources[ci].replace(
        "jobs:\n", "jobs:\n  rogue_job:\n    runs-on: ubuntu-latest\n", 1
    )
    assert any("JOB_OWNER_MISMATCH" in issue for issue in inspect(mutated, contract))
    path = ".github/workflows/physics-code-ci.yml"
    expected = contract["workflow_owners"][path]["required_steps"][0]
    mutated = dict(sources)
    if "      - name: " + expected in sources[path]:
        mutated[path] = sources[path].replace(
            "      - name: " + expected, "      - name: REMOVED_" + expected, 1
        )
    else:
        mutated[path] = sources[path].replace(
            "      - uses: " + expected, "      - uses: REMOVED_" + expected, 1
        )
    assert any("VALIDATION_STEP_OWNER_MISMATCH" in item
               for item in inspect(mutated, contract)), expected
    mutated = dict(sources)
    mutated[ci] = sources[ci].replace(
        "  pull_request:\n",
        "  pull_request:\n    paths-ignore: ['**']\n",
        1,
    )
    assert "REPOSITORY_CI_MUST_RUN_FOR_ALL_CHANGES" in inspect(mutated, contract)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
        sources = {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in contract["workflow_owners"]
        }
        if args.self_test:
            self_test(sources, contract)
            print("REPOSITORY_CI_SCOPE_SELF_TEST=PASS")
            return 0
        errors = inspect(sources, contract)
    except (OSError, TypeError, KeyError, ValueError, AssertionError) as exc:
        print(f"REPOSITORY_CI_SCOPE=FAIL: {type(exc).__name__}: {exc}")
        return 1
    if errors:
        print("REPOSITORY_CI_SCOPE=FAIL")
        print("\n".join(errors))
        return 1
    print("REPOSITORY_CI_SCOPE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
