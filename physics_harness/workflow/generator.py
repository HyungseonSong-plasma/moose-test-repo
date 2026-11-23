"""Compose reviewed, generic Actions YAML from workflow/job/step fragments.

This renders reviewable YAML; GitHub only executes committed, registered workflows.
The default profiles and historical one-shots are still owned by profiles.py.
"""
from __future__ import annotations

from pathlib import Path
import re

from physics_harness.workflow.matrix import build_matrix
from physics_harness.workflow.validator import (
    WorkflowValidationError, safe_repo_path, validate_executor_files,
)

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
TOKEN = re.compile(r"@@[A-Z_]+@@")


def fragment(name: str) -> str:
    path = TEMPLATES / name
    return path.read_text(encoding="utf-8").rstrip("\n")


def fill(source: str, fields: dict[str, str]) -> str:
    for name, value in fields.items():
        source = source.replace("@@" + name + "@@", value)
    if TOKEN.search(source):
        raise WorkflowValidationError("UNRESOLVED_WORKFLOW_TEMPLATE_TOKEN")
    return source


def render(spec, *, spec_path: str, root: Path) -> str:
    """Produce static registration YAML with a case matrix (never dispatch)."""
    safe_repo_path(spec_path, roots={"ci", "experiments", "physics_harness"})
    if not spec_path.endswith(".json"):
        raise WorkflowValidationError("SPEC_PATH_NOT_JSON")
    root = root.resolve()
    if not (root / spec_path).is_file() or not (root / spec_path).resolve().is_relative_to(root):
        raise WorkflowValidationError("SPEC_NOT_IN_REPOSITORY")
    validate_executor_files(spec, root)
    common = {
        "SOURCE_SHA": spec.source_sha, "SPEC_PATH": spec_path,
        "PREFIX": spec.artifact_prefix, "NAME": spec.name,
    }
    checkout = fill(fragment("steps/checkout.yml"), common)
    build_steps = checkout + "\n" + fill(fragment("steps/build.yml"), common)
    build_body = "    runs-on: ubuntu-24.04\n    timeout-minutes: 120\n    steps:\n" + build_steps
    build_job = fill(fragment("job.yml"), {"JOB_NAME": "build", "JOB_BODY": build_body})
    matrix_rows = "\n".join(
        "          - case: '" + item["case"] + "'" for item in build_matrix(spec)["include"]
    )
    case_steps = (checkout + "\n" + fill(fragment("steps/execute.yml"), common)
                  + "\n" + fill(fragment("steps/artifacts.yml"), common))
    case_body = (
        "    needs: [build]\n"
        "    runs-on: ubuntu-24.04\n"
        f"    timeout-minutes: {spec.timeout_minutes}\n"
        "    strategy:\n"
        "      fail-fast: false\n"
        f"      max-parallel: {spec.max_parallel}\n"
        "      matrix:\n"
        "        include:\n" + matrix_rows + "\n"
        "    steps:\n" + case_steps
    )
    case_job = fill(fragment("job.yml"), {"JOB_NAME": "cases", "JOB_BODY": case_body})
    summary_body = (
        "    if: always()\n"
        "    needs: [build, cases]\n"
        "    runs-on: ubuntu-24.04\n"
        "    timeout-minutes: 10\n"
        "    steps:\n" + checkout + "\n"
        "      - name: Download isolated case receipts\n"
        "        uses: actions/download-artifact@v4\n"
        "        with:\n"
        f"          pattern: {spec.artifact_prefix}-case-*\n"
        "          path: " + "$" + "{{ runner.temp }}/physics-case-receipts\n"
        "          merge-multiple: true\n"
        "      - name: Aggregate all required case receipts\n"
        "        run: |\n"
        f"          python3 bin/physics.py workflow aggregate --spec {spec_path} "
        '--receipts "$RUNNER_TEMP/physics-case-receipts" '
        '--output "$RUNNER_TEMP/physics-summary.json"\n'
        "      - name: Publish bounded execution summary\n"
        "        if: always()\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        f"          name: {spec.artifact_prefix}-summary\n"
        "          path: " + "$" + "{{ runner.temp }}/physics-summary.json\n"
        "          if-no-files-found: warn\n"
    )
    summary_job = fill(fragment("job.yml"), {"JOB_NAME": "aggregate", "JOB_BODY": summary_body.rstrip("\n")})
    result = fill(fragment("workflow.yml"), {"NAME": spec.name, "JOBS": "\n".join(
        (build_job, case_job, summary_job))})
    if "secrets." in result or "pull_request:" in result:
        raise WorkflowValidationError("UNAUTHORIZED_SECRET_OR_PR_EXECUTION")
    return result + "\n"
