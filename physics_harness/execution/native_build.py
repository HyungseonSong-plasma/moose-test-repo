#!/usr/bin/env python3
"""Fail-closed, application-scoped MOOSE Native P1 build harness.

This module runs *inside* a reviewed, immutable OCI build image. It does not
pull images, change dependencies, change physics, or install workflows. The
caller must pin and verify the image and provide a clean exact-source checkout.
Use: python3 native_build.py --source-root /app --expected-sha <40-hex-sha>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Sequence

VENDOR_ROOT = Path("/opt/physics_vendor")
VENDORS = ("moose", "crane", "squirrel", "zapdos")
UNITY_RE = re.compile(r"(?:^|[/\s])([A-Za-z0-9_-]+)_Unity[.]C\b")
HEX_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DEFAULT_SCOPED_DIRS = ("src/utils",)
DEFAULT_MAX_JOBS = 4
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MIN_FREE_BYTES = 1024 * 1024 * 1024  # 1 GiB free before P1
DEFAULT_MIN_FREE_INODES = 2000


class NativeBuildError(RuntimeError):
    def __init__(self, stage: str, classification: str, detail: str):
        super().__init__(detail)
        self.stage = stage
        self.classification = classification


def available_memory_kb(
    proc_meminfo: Path = Path("/proc/meminfo"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> int:
    """Return the effective host/cgroup available memory, or 0 if unknown."""
    readings: list[int] = []
    try:
        for line in proc_meminfo.read_text().splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                readings.append(int(parts[1]))
                break
    except (OSError, IndexError, ValueError):
        pass
    # Cgroup v2 limit matters even if /proc/meminfo reports host RAM.
    try:
        raw_limit = (cgroup_root / "memory.max").read_text().strip()
        if raw_limit != "max":
            remaining = int(raw_limit) - int((cgroup_root / "memory.current").read_text().strip())
            readings.append(max(0, remaining // 1024))
    except (OSError, ValueError):
        pass
    # Older hosted runners may use a cgroup v1 hard limit.
    try:
        root = cgroup_root / "memory"
        raw = int((root / "memory.limit_in_bytes").read_text().strip())
        used = int((root / "memory.usage_in_bytes").read_text().strip())
        if raw < (1 << 60):
            readings.append(max(0, (raw - used) // 1024))
    except (OSError, ValueError):
        pass
    return min(readings) if readings else 0


def quota_cpus(cgroup_root: Path = Path("/sys/fs/cgroup")) -> int | None:
    """Read CPU quota from cgroup v2 or v1; return None for unlimited/unknown."""
    try:
        parts = (cgroup_root / "cpu.max").read_text().split()
        if len(parts) == 2 and parts[0] != "max":
            quota, period = map(int, parts)
            if quota >= 0 and period > 0:
                return max(1, (quota + period - 1) // period)
    except (OSError, ValueError):
        pass
    try:
        group = cgroup_root / "cpu"
        quota = int((group / "cpu.cfs_quota_us").read_text())
        period = int((group / "cpu.cfs_period_us").read_text())
        if quota >= 0 and period > 0:
            return max(1, (quota + period - 1) // period)
    except (OSError, ValueError):
        pass
    return None


def available_cpus(cgroup_root: Path = Path("/sys/fs/cgroup")) -> int:
    """Honor CPU affinity and any active container quota."""
    try:
        cpus = max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        cpus = max(1, os.cpu_count() or 1)
    quota = quota_cpus(cgroup_root)
    return min(cpus, quota) if quota is not None else cpus


def check_build_storage(
    app: Path,
    *,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
    min_free_inodes: int = DEFAULT_MIN_FREE_INODES,
) -> dict[str, int | None]:
    """Fail before compile when app filesystem cannot safely create artifacts.

    Filesystems with f_files=0 expose unknown inode accounting; skip the inode
    threshold there rather than falsely calling the build full.
    """
    if min_free_bytes < 0 or min_free_inodes < 0:
        raise NativeBuildError("P0", "INVALID_STORAGE_POLICY", "storage thresholds cannot be negative")
    try:
        free = shutil.disk_usage(app).free
        stat = os.statvfs(app)
        inodes = stat.f_favail if stat.f_files else None
    except OSError as exc:
        raise NativeBuildError("P0", "STORAGE_PREFLIGHT_FAILURE", "cannot inspect app filesystem") from exc
    if free < min_free_bytes:
        raise NativeBuildError("P0", "DISK_CAPACITY_INSUFFICIENT", "not enough free space for Native P1")
    if inodes is not None and inodes < min_free_inodes:
        raise NativeBuildError("P0", "INODE_CAPACITY_INSUFFICIENT", "not enough free inodes for Native P1")
    return {"free_bytes": free, "free_inodes": inodes}



def choose_jobs(cpus: int, memory_kb: int, max_jobs: int = DEFAULT_MAX_JOBS) -> int:
    """Conservative memory-aware cap; never request all host cores blindly."""
    if cpus < 1 or max_jobs < 1:
        raise ValueError("CPU count and max_jobs must be positive")
    if memory_kb <= 0 or memory_kb < 4_000_000:
        memory_jobs = 1
    elif memory_kb < 10_000_000:
        memory_jobs = 2
    else:
        memory_jobs = max(2, memory_kb // 3_000_000)
    return max(1, min(cpus, max_jobs, memory_jobs))


def _checked_subdir(app: Path, relative: str) -> str:
    """Only permit existing application source directories; no vendor escapes."""
    p = Path(relative)
    if (p.is_absolute() or len(p.parts) < 2 or p.parts[0] != "src"
            or any(part in ("..", ".", "") for part in p.parts)):
        raise NativeBuildError("P0", "INVALID_BUILD_PROFILE", "non-unity directory must be beneath app src/")
    target = (app / p).resolve()
    root = (app / "src").resolve()
    if not target.is_dir() or not target.is_relative_to(root):
        raise NativeBuildError("P0", "INVALID_BUILD_PROFILE", "non-unity directory is absent or escapes app src/")
    return str(target)


def resolve_scoped_dirs(app: Path, directories: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({_checked_subdir(app, item) for item in directories}))


def make_argv(app: Path, jobs: int, scoped_dirs: Sequence[str]) -> list[str]:
    """Pass one make variable per argv entry; never shell-evaluate user paths."""
    argv = ["make", "-C", str(app), "-j" + str(jobs), "MOOSE_UNITY=true"]
    if scoped_dirs:
        argv.append("app_non_unity_dirs=" + " ".join(scoped_dirs))
    return argv


def classify_failure(log_text: str) -> str:
    """Classify confirmed errors, not speculative text or suggested compiler flags."""
    lower = log_text.lower()
    # Terminal failures always take precedence over Unity-redefinition recovery.
    if "feproblembase" in lower and "squirrel" in lower:
        return "VENDOR_SOURCE_OR_ABI_FAILURE"
    if "no free inodes" in lower or "inode exhaustion" in lower:
        return "INODE_CAPACITY_EXHAUSTED"
    if "no space left on device" in lower or "disk quota exceeded" in lower:
        return "DISK_CAPACITY_EXHAUSTED"
    if ("killed signal terminated program" in lower or "out of memory" in lower
            or "cannot allocate memory" in lower or "exit status 137" in lower):
        return "RESOURCE_EXHAUSTION"
    if "glibcxx_" in lower or "cxxabi_" in lower or "undefined symbol:" in lower:
        return "RUNTIME_ABI_MISMATCH"
    if "undefined reference to" in lower or "multiple definition of" in lower:
        return "LINKER_SYMBOL_FAILURE"
    if re.search(r"fatal error: [^\n]*no such file or directory", lower):
        return "HEADER_OR_GENERATED_FILE_MISSING"
    if "unbound variable" in lower:
        return "SHELL_QUOTING_OR_UNSET_VARIABLE"
    if ("error: redefinition of" in lower or "error: 'redefinition" in lower) and UNITY_RE.search(log_text):
        return "APP_UNITY_SYMBOL_COLLISION"
    if "error:" in lower or "fatal error:" in lower:
        return "SOURCE_COMPILATION_FAILURE"
    return "BUILD_FAILURE_UNCLASSIFIED"


def collision_directories(log_text: str, app: Path) -> tuple[str, ...]:
    """Infer only real, non-symlink-escaping application Unity directories."""
    if classify_failure(log_text) != "APP_UNITY_SYMBOL_COLLISION":
        return ()
    found: set[str] = set()
    for name in UNITY_RE.findall(log_text):
        try:
            found.add(_checked_subdir(app, "src/" + name))
        except NativeBuildError:
            # Reject missing dirs, directory symlinks and vendor/cache escapes.
            continue
    return tuple(sorted(found))


def _run_logged(args: Sequence[str], *, cwd: Path, log: Path, timeout_s: int) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(list(args), cwd=cwd, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout_s, check=False)
        return int(result.returncode)
    except subprocess.TimeoutExpired as exc:
        raise NativeBuildError("P1", "BUILD_TIMEOUT", "Native P1 build exceeded timeout") from exc
    except OSError as exc:
        raise NativeBuildError("P1", "BUILD_ENVIRONMENT_FAILURE", str(exc)) from exc


def _verify_source(source_root: Path, expected_sha: str, binary: Path) -> None:
    if not HEX_SHA_RE.fullmatch(expected_sha):
        raise NativeBuildError("P0", "INVALID_SOURCE_SHA", "expected source SHA must be 40 lowercase hex characters")
    if not (source_root / ".git").exists():
        raise NativeBuildError("P0", "MISSING_GIT_CHECKOUT", "source root has no .git")
    for directory in (source_root, *(VENDOR_ROOT / name for name in VENDORS)):
        if directory.is_dir():
            subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(directory)],
                           check=True, capture_output=True)
    try:
        actual_sha = subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=all",
             "--", "physics_app"], text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise NativeBuildError("P0", "SOURCE_IDENTITY_FAILURE", "cannot verify source identity") from exc
    if actual_sha != expected_sha:
        raise NativeBuildError("P0", "SOURCE_SHA_MISMATCH", "candidate HEAD differs from reviewed source")
    if dirty.strip() or binary.exists():
        raise NativeBuildError("P0", "DIRTY_OR_STALE_APP", "app is dirty or already has a binary; use a fresh checkout")


def _verify_vendor_environment() -> None:
    for name in VENDORS:
        expected = VENDOR_ROOT / name
        if os.environ.get(name.upper() + "_DIR") != str(expected) or not expected.is_dir():
            raise NativeBuildError("P0", "VENDOR_CACHE_IDENTITY_FAILURE",
                                   "pinned vendor directory missing or unexpected: " + name)
    if os.environ.get("METHOD") != "opt":
        raise NativeBuildError("P0", "METHOD_MISMATCH", "Native P1 requires METHOD=opt")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build(
    *,
    source_root: Path,
    expected_sha: str,
    log_dir: Path,
    report_path: Path,
    profile: str = "auto",
    extra_non_unity_dirs: Sequence[str] = (),
    max_jobs: int = DEFAULT_MAX_JOBS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout_s: int = 3600,
    smoke_input: str | None = None,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
    min_free_inodes: int = DEFAULT_MIN_FREE_INODES,
) -> dict:
    """Build application only. Retry *only* newly identified app Unity collisions."""
    source_root = source_root.resolve()
    app = source_root / "physics_app"
    binary = app / "physics-opt"
    if profile not in ("auto", "scoped", "unity") or max_attempts < 1 or timeout_s < 1:
        raise NativeBuildError("P0", "INVALID_BUILD_PROFILE", "invalid profile or positive limits")
    if not app.is_dir():
        raise NativeBuildError("P0", "MISSING_APP", "physics_app does not exist")
    _verify_source(source_root, expected_sha, binary)
    _verify_vendor_environment()
    if profile == "unity":
        if extra_non_unity_dirs:
            raise NativeBuildError("P0", "INVALID_BUILD_PROFILE", "unity profile cannot specify non-unity dirs")
        initial_dirs: tuple[str, ...] = ()
    else:
        defaults = [name for name in DEFAULT_SCOPED_DIRS if (app / name).is_dir()] if profile == "auto" else []
        initial_dirs = resolve_scoped_dirs(app, [*defaults, *extra_non_unity_dirs])
    cpus, mem_kb = available_cpus(), available_memory_kb()
    jobs = choose_jobs(cpus, mem_kb, max_jobs)
    scoped = set(initial_dirs)
    log_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "NOT_RUN", "stage": "P1", "classification": None,
        "source_sha": expected_sha, "profile": profile,
        "vendor_cache": "PRESERVED", "unity": True,
        "cpus": cpus, "memory_available_kb": mem_kb, "jobs": jobs,
        "attempts": [], "science": "HOLD", "storage": None,
    }

    def write_report() -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    try:
        report["storage"] = check_build_storage(
            app, min_free_bytes=min_free_bytes, min_free_inodes=min_free_inodes)
        for number in range(1, max_attempts + 1):
            # Do not continue a retry if previous compilation consumed the
            # remaining free space/inodes. Do not delete vendor or app caches.
            report["storage"] = check_build_storage(
                app, min_free_bytes=min_free_bytes, min_free_inodes=min_free_inodes)
            selected = sorted(scoped)
            argv = make_argv(app, jobs, selected)
            log = log_dir / ("P1_build_attempt%02d.log" % number)
            entry = {"attempt": number, "scoped_dirs": selected,
                     "make_argv": argv, "log": str(log)}
            report["attempts"].append(entry)
            rc = _run_logged(argv, cwd=source_root, log=log, timeout_s=timeout_s)
            entry["exit_code"] = rc
            if rc == 0:
                if not binary.is_file() or not os.access(binary, os.X_OK):
                    raise NativeBuildError("P1", "MISSING_NATIVE_EXECUTABLE",
                                           "make returned success without executable")
                if smoke_input is not None:
                    input_path = (app / smoke_input).resolve()
                    if not input_path.is_file() or not input_path.is_relative_to(app.resolve()):
                        raise NativeBuildError("P1", "INVALID_SMOKE_INPUT", "smoke input missing or outside app")
                    smoke_rc = _run_logged(["./physics-opt", "--check-input", "-i", smoke_input],
                                           cwd=app, log=log_dir / "P1_smoke.log", timeout_s=300)
                    if smoke_rc:
                        raise NativeBuildError("P1", "NATIVE_SMOKE_FAILURE",
                                               "native --check-input smoke failed")
                report.update(status="PASS", classification="BUILT",
                              executable_sha256=sha256(binary), scoped_dirs=selected)
                write_report()
                return report
            # Never retry a missing dependency, OOM, arbitrary compiler error, or solver failure.
            tail = log.read_text(errors="replace")[-256 * 1024:]
            kind = classify_failure(tail)
            entry["classification"] = kind
            if kind != "APP_UNITY_SYMBOL_COLLISION" or profile != "auto":
                raise NativeBuildError("P1", kind, "Native P1 build failed; see per-attempt restricted log")
            newly_detected = set(collision_directories(tail, app)) - scoped
            if not newly_detected:
                raise NativeBuildError("P1", "UNITY_COLLISION_UNRESOLVED",
                                       "Unity conflict persisted; no new safe application dirs to exclude")
            if number == max_attempts:
                raise NativeBuildError("P1", "RETRY_BUDGET_EXHAUSTED",
                                       "Unity conflict requires more attempts than approved")
            scoped.update(newly_detected)
        raise NativeBuildError("P1", "RETRY_BUDGET_EXHAUSTED", "no build succeeded")
    except NativeBuildError as exc:
        report.update(status="FAILED", stage=exc.stage, classification=exc.classification)
        write_report()
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--log-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--profile", choices=("auto", "scoped", "unity"), default="auto")
    parser.add_argument("--non-unity-dir", action="append", default=[])
    parser.add_argument("--max-jobs", type=int, default=DEFAULT_MAX_JOBS)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--smoke-input", default=None)
    parser.add_argument("--min-free-mib", type=int, default=DEFAULT_MIN_FREE_BYTES // (1024 * 1024))
    parser.add_argument("--min-free-inodes", type=int, default=DEFAULT_MIN_FREE_INODES)
    args = parser.parse_args(argv)
    try:
        result = build(source_root=args.source_root, expected_sha=args.expected_sha,
                       log_dir=args.log_dir, report_path=args.report,
                       profile=args.profile, extra_non_unity_dirs=args.non_unity_dir,
                       max_jobs=args.max_jobs, max_attempts=args.max_attempts,
                       timeout_s=args.timeout_seconds, smoke_input=args.smoke_input,
                       min_free_bytes=args.min_free_mib * 1024 * 1024,
                       min_free_inodes=args.min_free_inodes)
    except (NativeBuildError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        classification = getattr(exc, "classification", "BUILD_HARNESS_ERROR")
        print(json.dumps({"P1": "FAILED", "class": classification, "science": "HOLD"}),
              file=sys.stderr)
        return 2
    print(json.dumps({"P1": "PASS", "jobs": result["jobs"],
                      "attempts": len(result["attempts"]),
                      "executable_sha256": result["executable_sha256"],
                      "science": "HOLD"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
