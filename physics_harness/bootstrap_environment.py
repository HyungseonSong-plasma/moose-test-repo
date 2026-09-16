"""Stdlib-only canonical import environment for Physics repository workflows.

This module owns the stable contract that repository-local Python packages are
imported from the repository root and optional bootstrap dependency targets are
searched before that root.  It emits shell-safe exports so a child Python
process can establish environment for its parent shell via ``eval``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
from typing import Mapping, Sequence


_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEPS_ROOT = _REPO_ROOT / ".physics-harness-deps"
_DEFAULT_PROFILE = "evidence"


def _dedupe_paths(paths: Sequence[str]) -> list[str]:
    """Return non-empty paths in first-occurrence order."""

    result: list[str] = []
    seen: set[str] = set()
    for entry in paths:
        if not entry or entry in seen:
            continue
        seen.add(entry)
        result.append(entry)
    return result


def build_environment(
    *, profile: str = _DEFAULT_PROFILE, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Build the canonical repository-local Python import environment."""

    source = os.environ if environ is None else environ
    dependency_target = (_DEPS_ROOT / profile).resolve()
    try:
        dependency_target.relative_to(_REPO_ROOT)
    except ValueError as error:
        raise ValueError(f"dependency target escapes repository root: {dependency_target}") from error

    existing = source.get("PYTHONPATH", "").split(os.pathsep)
    pythonpath = _dedupe_paths([str(dependency_target), str(_REPO_ROOT), *existing])
    return {
        "PHYSICS_REPO_ROOT": str(_REPO_ROOT),
        "PYTHONPATH": os.pathsep.join(pythonpath),
    }


def render_bash(environment: Mapping[str, str]) -> str:
    """Render shell-safe bash exports for ``eval $(...)`` consumption."""

    return "\n".join(
        f"export {name}={shlex.quote(value)}" for name, value in sorted(environment.items())
    )


def self_test() -> dict[str, object]:
    """Exercise repository-root, ordering, preservation, and quoting contracts."""

    checks: dict[str, bool] = {}
    env = build_environment(
        profile="evidence",
        environ={"PYTHONPATH": os.pathsep.join(("/existing/a", "/existing/b", str(_REPO_ROOT)))},
    )
    paths = env["PYTHONPATH"].split(os.pathsep)
    target = str((_DEPS_ROOT / "evidence").resolve())

    checks["repo_root_is_module_parent"] = _REPO_ROOT == Path(__file__).resolve().parents[1]
    checks["repo_root_contains_physics_harness"] = (_REPO_ROOT / "physics_harness").is_dir()
    checks["physics_repo_root_exported"] = env["PHYSICS_REPO_ROOT"] == str(_REPO_ROOT)
    checks["dependency_target_first"] = paths[0] == target
    checks["repo_root_second"] = len(paths) > 1 and paths[1] == str(_REPO_ROOT)
    checks["existing_entries_preserved"] = "/existing/a" in paths and "/existing/b" in paths
    checks["paths_are_deduplicated"] = len(paths) == len(set(paths))
    rendered = render_bash(env)
    checks["bash_exports_repo_root"] = "export PHYSICS_REPO_ROOT=" in rendered
    checks["bash_exports_pythonpath"] = "export PYTHONPATH=" in rendered

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "schema": "PHYSICS_BOOTSTRAP_ENV_SELF_TEST_V1",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=_DEFAULT_PROFILE)
    parser.add_argument("--shell", choices=("bash", "json"), default="bash")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.self_test:
        payload = self_test()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["status"] == "PASS" else 1

    environment = build_environment(profile=args.profile)
    if args.shell == "json":
        print(json.dumps(environment, indent=2, sort_keys=True))
    else:
        print(render_bash(environment))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
