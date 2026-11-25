"""Runner entry point. No credentials accepted in request files or artifacts."""
import json
import os
from pathlib import Path
import subprocess

from chatgpt_operation.github.actions_runtime import GitHubActionsTransport
from physics_harness.execution.controller_contract_ingress import REPO, execute


def main():
    root = Path(__file__).resolve().parents[2]
    env = os.environ
    event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_bytes())
    if env["GITHUB_EVENT_NAME"] != "workflow_run" or env["GITHUB_REPOSITORY"] != REPO or env["GITHUB_REF"] != "refs/heads/main":
        raise ValueError("UNTRUSTED_RUNNER_EVENT")
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != env["GITHUB_SHA"]:
        raise ValueError("RUNNER_SOURCE_MISMATCH")
    transport = GitHubActionsTransport(REPO, env["GITHUB_TOKEN"])
    execute(transport, root=root, main_sha=head, upstream_id=event["workflow_run"]["id"],
            ingress_id=int(env["GITHUB_RUN_ID"]), ingress_attempt=int(env["GITHUB_RUN_ATTEMPT"]),
            output=Path(env["RUNNER_TEMP"]) / "checkpoint-dispatch.json")


if __name__ == "__main__":
    main()
