"""Stdlib-only dependency bootstrap for Physics harness workflows.

The committed requirements files own dependency constraints. This module owns
when and where those constraints are installed, verifies importability from the
explicit target, and emits a provenance manifest. It intentionally imports only
Python's standard library so it can run before third-party dependencies exist.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence


class BootstrapError(RuntimeError):
    """Raised when a bootstrap profile cannot be resolved or verified."""


@dataclass(frozen=True)
class Profile:
    """Canonical dependency profile backed by a committed requirements file."""

    requirements: str
    imports: tuple[str, ...]
    distributions: tuple[str, ...]


PROFILES: dict[str, Profile] = {
    "evidence": Profile(
        requirements="requirements-evidence-engine.txt",
        imports=("duckdb", "polars", "pyarrow", "pydantic", "z3"),
        distributions=("duckdb", "polars", "pyarrow", "pydantic", "z3-solver"),
    ),
}

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEPS_ROOT = _REPO_ROOT / ".physics-harness-deps"


def _profile(name: str) -> Profile:
    """Return a named profile or fail with the available profile names."""

    try:
        return PROFILES[name]
    except KeyError as error:
        choices = ", ".join(sorted(PROFILES))
        raise BootstrapError(f"unknown bootstrap profile {name!r}; choose from: {choices}") from error


def _requirements_path(profile: Profile) -> Path:
    """Resolve and validate the committed requirements file for a profile."""

    path = (_REPO_ROOT / profile.requirements).resolve()
    try:
        path.relative_to(_REPO_ROOT)
    except ValueError as error:
        raise BootstrapError(f"requirements path escapes repository root: {path}") from error
    if not path.is_file():
        raise BootstrapError(f"requirements file not found: {path}")
    return path


def _target_path(name: str) -> Path:
    """Return the repository-local dependency target for a profile."""

    target = (_DEPS_ROOT / name).resolve()
    try:
        target.relative_to(_REPO_ROOT)
    except ValueError as error:
        raise BootstrapError(f"dependency target escapes repository root: {target}") from error
    return target


def _sha256(path: Path) -> str:
    """Return a SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _uv_install_command(uv: str, requirements: Path, target: Path) -> list[str]:
    """Build a uv command that installs into an explicit repository-local target."""

    return [
        uv,
        "pip",
        "install",
        "--python",
        sys.executable,
        "--target",
        str(target),
        "-r",
        str(requirements),
    ]


def _pip_install_command(requirements: Path, target: Path) -> list[str]:
    """Build a pip command that installs into an explicit repository-local target."""

    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--target",
        str(target),
        "-r",
        str(requirements),
    ]


def _installer_command(requirements: Path, target: Path, installer: str = "auto") -> list[str]:
    """Build the install command for the explicit dependency target."""

    selected = installer
    uv = shutil.which("uv")
    if selected == "auto":
        selected = "uv" if uv else "pip"

    if selected == "uv":
        if not uv:
            raise BootstrapError("installer 'uv' requested but uv is not available on PATH")
        return _uv_install_command(uv, requirements, target)

    if selected == "pip":
        return _pip_install_command(requirements, target)

    raise BootstrapError(f"unsupported installer: {installer!r}")


def _prepare_target(target: Path) -> None:
    """Create a clean dependency target so stale wheels cannot contaminate evidence."""

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


def _activate_target(target: Path) -> None:
    """Put the explicit dependency target first on this process's import path."""

    target_text = str(target)
    if target_text in sys.path:
        sys.path.remove(target_text)
    sys.path.insert(0, target_text)
    importlib.invalidate_caches()


def _verify_imports(modules: Iterable[str], target: Path) -> dict[str, str]:
    """Import required modules and prove they resolve from the explicit target."""

    resolved: dict[str, str] = {}
    failures: list[str] = []
    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
        except Exception as error:  # import failures need full diagnostic context
            failures.append(f"{module_name}: {type(error).__name__}: {error}")
            continue

        location = getattr(module, "__file__", None)
        if not location:
            failures.append(f"{module_name}: imported module has no file location")
            continue
        path = Path(location).resolve()
        try:
            path.relative_to(target)
        except ValueError:
            failures.append(f"{module_name}: resolved outside target at {path}")
            continue
        resolved[module_name] = str(path)

    if failures:
        raise BootstrapError("dependency import smoke test failed: " + "; ".join(failures))
    return resolved


def _distribution_versions(names: Iterable[str], target: Path) -> dict[str, str]:
    """Return versions from distribution metadata stored in the explicit target."""

    found = {
        dist.metadata["Name"].lower().replace("_", "-"): dist.version
        for dist in importlib.metadata.distributions(path=[str(target)])
        if dist.metadata.get("Name")
    }
    versions: dict[str, str] = {}
    failures: list[str] = []
    for name in names:
        key = name.lower().replace("_", "-")
        if key not in found:
            failures.append(name)
        else:
            versions[name] = found[key]
    if failures:
        raise BootstrapError("target distribution metadata missing: " + ", ".join(failures))
    return versions


def _manifest(name: str, profile: Profile, requirements: Path, target: Path) -> dict[str, object]:
    """Build the bootstrap provenance manifest after target verification."""

    _activate_target(target)
    imports = _verify_imports(profile.imports, target)
    versions = _distribution_versions(profile.distributions, target)
    return {
        "schema": "PHYSICS_HARNESS_BOOTSTRAP_V1",
        "profile": name,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "requirements_file": profile.requirements,
        "requirements_sha256": _sha256(requirements),
        "target": str(target),
        "imports": imports,
        "distributions": versions,
    }


def ensure(
    name: str,
    *,
    installer: str = "auto",
    manifest_out: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Install a canonical profile into its target, verify it, and return provenance."""

    profile = _profile(name)
    requirements = _requirements_path(profile)
    target = _target_path(name)
    command = _installer_command(requirements, target, installer)

    if dry_run:
        payload: dict[str, object] = {
            "schema": "PHYSICS_HARNESS_BOOTSTRAP_V1",
            "profile": name,
            "requirements_file": profile.requirements,
            "requirements_sha256": _sha256(requirements),
            "target": str(target),
            "installer_command": command,
            "dry_run": True,
        }
    else:
        _prepare_target(target)
        subprocess.run(command, cwd=_REPO_ROOT, check=True)
        payload = _manifest(name, profile, requirements, target)
        payload["installer"] = "uv" if Path(command[0]).name == "uv" else "pip"
        payload["installer_command"] = command

    if manifest_out is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def check(name: str, *, manifest_out: Path | None = None) -> dict[str, object]:
    """Verify an already-prepared explicit target without installing anything."""

    profile = _profile(name)
    requirements = _requirements_path(profile)
    target = _target_path(name)
    if not target.is_dir():
        raise BootstrapError(f"dependency target not found: {target}")
    payload = _manifest(name, profile, requirements, target)
    payload["installer"] = None
    if manifest_out is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def self_test() -> dict[str, object]:
    """Exercise stdlib-only profile, target, and command construction contracts."""

    checks: dict[str, bool] = {}
    evidence = _profile("evidence")
    requirements = _requirements_path(evidence)
    target = _target_path("evidence")
    checks["evidence_requirements_exists"] = requirements.name == "requirements-evidence-engine.txt"
    checks["evidence_requirements_inside_repo"] = _REPO_ROOT in requirements.parents
    checks["evidence_requirements_digest"] = len(_sha256(requirements)) == 64
    checks["target_inside_repo"] = _REPO_ROOT in target.parents
    checks["target_is_profile_scoped"] = target.name == "evidence" and target.parent.name == ".physics-harness-deps"
    checks["polars_import_declared"] = "polars" in evidence.imports
    checks["pyarrow_import_declared"] = "pyarrow" in evidence.imports
    checks["z3_distribution_mapping"] = "z3" in evidence.imports and "z3-solver" in evidence.distributions

    try:
        _profile("__missing_profile__")
    except BootstrapError:
        checks["unknown_profile_rejected"] = True
    else:
        checks["unknown_profile_rejected"] = False

    auto_command = _installer_command(requirements, target, "auto")
    checks["installer_uses_current_python_or_uv"] = (
        (Path(auto_command[0]).name == "uv" and sys.executable in auto_command)
        or auto_command[:3] == [sys.executable, "-m", "pip"]
    )
    checks["installer_binds_requirements_file"] = auto_command[-1] == str(requirements)
    checks["installer_binds_explicit_target"] = "--target" in auto_command and str(target) in auto_command
    checks["installer_avoids_user_and_system_sites"] = "--user" not in auto_command and "--system" not in auto_command

    uv_command = _uv_install_command("/test/uv", requirements, target)
    checks["uv_binds_current_python"] = sys.executable in uv_command
    checks["uv_binds_explicit_target"] = "--target" in uv_command and str(target) in uv_command
    checks["uv_avoids_user_and_system_sites"] = "--user" not in uv_command and "--system" not in uv_command

    pip_command = _pip_install_command(requirements, target)
    checks["pip_binds_current_python"] = pip_command[:3] == [sys.executable, "-m", "pip"]
    checks["pip_binds_explicit_target"] = "--target" in pip_command and str(target) in pip_command
    checks["pip_avoids_user_and_system_sites"] = "--user" not in pip_command and "--system" not in pip_command
    checks["pip_binds_requirements_file"] = pip_command[-1] == str(requirements)

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "schema": "PHYSICS_HARNESS_BOOTSTRAP_SELF_TEST_V1",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run stdlib-only bootstrap self-test")
    subparsers = parser.add_subparsers(dest="command")

    for command in ("ensure", "check"):
        sub = subparsers.add_parser(command)
        sub.add_argument("profile", choices=sorted(PROFILES))
        sub.add_argument("--manifest-out", type=Path)
        if command == "ensure":
            sub.add_argument("--installer", choices=("auto", "uv", "pip"), default="auto")
            sub.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("profiles")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for dependency bootstrap and verification."""

    parser = _parser()
    args = parser.parse_args(argv)

    if args.self_test:
        payload = self_test()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["status"] == "PASS" else 1

    try:
        if args.command == "ensure":
            payload = ensure(
                args.profile,
                installer=args.installer,
                manifest_out=args.manifest_out,
                dry_run=args.dry_run,
            )
        elif args.command == "check":
            payload = check(args.profile, manifest_out=args.manifest_out)
        elif args.command == "profiles":
            payload = {
                name: {
                    "requirements_file": profile.requirements,
                    "target": str(_target_path(name)),
                    "imports": list(profile.imports),
                    "distributions": list(profile.distributions),
                }
                for name, profile in sorted(PROFILES.items())
            }
        else:
            parser.print_help()
            return 2
    except (BootstrapError, subprocess.CalledProcessError) as error:
        print(
            json.dumps(
                {
                    "schema": "PHYSICS_HARNESS_BOOTSTRAP_V1",
                    "status": "FAIL",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
