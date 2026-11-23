"""Thin workflow CLI; bin/physics.py retains the sole public entrypoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from physics_harness.workflow.validator import WorkflowValidationError

ROOT = Path(__file__).resolve().parents[2]


def _dump(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _spec_path(raw: str) -> tuple[Path, str]:
    path = (ROOT / raw).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise WorkflowValidationError("SPEC_NOT_IN_REPOSITORY")
    return path, path.relative_to(ROOT).as_posix()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="physics workflow")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "matrix", "validate", "generate", "execute-build", "execute-case", "aggregate", "dispatch"):
        cmd = commands.add_parser(action)
        cmd.add_argument("--spec", required=True)
        if action == "generate":
            cmd.add_argument("--output")
        elif action == "execute-build":
            cmd.add_argument("--output-dir", required=True)
        elif action == "execute-case":
            cmd.add_argument("--case", required=True)
            cmd.add_argument("--build-dir", required=True)
            cmd.add_argument("--receipt", required=True)
        elif action == "aggregate":
            cmd.add_argument("--receipts", required=True)
            cmd.add_argument("--output", required=True)
        elif action == "dispatch":
            cmd.add_argument("--repository", required=True)
            cmd.add_argument("--workflow-file", required=True)
            cmd.add_argument("--ref", required=True)
            cmd.add_argument("--authorize", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("--repository", required=True)
    status.add_argument("--run-id", type=int, required=True)
    profiles = commands.add_parser("profiles")
    profiles.add_argument("mode", choices=("check", "self-test", "generate"))
    try:
        opt = parser.parse_args(args)
        if opt.action == "profiles":
            from physics_harness.workflow import profiles as legacy
            return legacy.main(["--" + opt.mode])
        if opt.action == "status":
            from physics_harness.workflow.provider import GitHubActionsProvider
            from physics_harness.workflow.monitor import snapshot
            _dump(snapshot(GitHubActionsProvider(opt.repository), opt.run_id))
            return 0

        from physics_harness.workflow.spec import load_spec
        spec_path, relative = _spec_path(opt.spec)
        spec = load_spec(spec_path)
        if opt.action == "plan":
            from physics_harness.workflow.planner import plan_dict
            _dump(plan_dict(spec))
        elif opt.action == "matrix":
            from physics_harness.workflow.matrix import build_matrix
            _dump(build_matrix(spec))
        elif opt.action == "validate":
            from physics_harness.workflow.validator import validate_executor_files
            if spec.build_script:
                validate_executor_files(spec, ROOT)
            _dump({"status": "VALID", "cases": [case.id for case in spec.cases],
                   "execution_authorized": False, "science_status": "HOLD"})
        elif opt.action == "generate":
            from physics_harness.workflow.generator import render
            result = render(spec, spec_path=relative, root=ROOT)
            if opt.output is None:
                sys.stdout.write(result)
            else:
                path = (ROOT / opt.output).resolve()
                if not path.is_relative_to(ROOT / ".github/workflows"):
                    raise WorkflowValidationError("OUTPUT_OUTSIDE_WORKFLOWS")
                if path.exists():
                    raise WorkflowValidationError("WORKFLOW_OUTPUT_ALREADY_EXISTS")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(result, encoding="utf-8")
                _dump({"status": "GENERATED_FOR_REVIEW", "path": path.relative_to(ROOT).as_posix()})
        elif opt.action == "execute-build":
            from physics_harness.workflow.runner import execute_build
            return execute_build(spec, root=ROOT, output_dir=Path(opt.output_dir).resolve())
        elif opt.action == "execute-case":
            from physics_harness.workflow.runner import execute_case
            return execute_case(spec, root=ROOT, case_id=opt.case,
                                build_dir=Path(opt.build_dir).resolve(),
                                receipt=Path(opt.receipt).resolve())
        elif opt.action == "aggregate":
            from physics_harness.workflow.aggregator import write_summary
            summary = write_summary(spec, Path(opt.receipts), Path(opt.output))
            _dump(summary)
            return 0 if summary["execution_status"] == "EXIT_ZERO_UNVERIFIED" else 3
        elif opt.action == "dispatch":
            from physics_harness.workflow.provider import GitHubActionsProvider
            from physics_harness.workflow.dispatcher import dispatch
            from physics_harness.workflow.validator import validate_executor_files
            validate_executor_files(spec, ROOT)
            _dump(dispatch(GitHubActionsProvider(opt.repository),
                           workflow_file=opt.workflow_file, ref=opt.ref,
                           authorize=opt.authorize))
        else:
            raise WorkflowValidationError("UNRECOGNIZED_COMMAND")
    except (WorkflowValidationError, OSError, ValueError) as exc:
        print("PHYSICS_WORKFLOW_HOLD: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
