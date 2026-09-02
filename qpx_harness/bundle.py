"""Declarative local-QPX profiling bundle builder."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from .evidence import sha256_file


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text())
    if int(spec.get("schema", 0)) != 1:
        raise SystemExit(f"unsupported bundle spec schema in {path}")
    return spec


def validate_case(case: Path, spec: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    case_spec = spec["case"]
    required_files = case_spec.get("required_files", ["input.i"])
    for name in required_files:
        if not (case / name).is_file():
            reasons.append(f"missing {name}")
    if reasons:
        return False, reasons

    for name, expected in case_spec.get("sha256", {}).items():
        actual = sha256_file(case / name)
        if actual != expected:
            reasons.append(f"{name} sha256 mismatch: {actual}")

    input_name = case_spec.get("input", "input.i")
    text = (case / input_name).read_text(errors="replace")
    missing = [
        signature
        for signature in case_spec.get("input_signatures", [])
        if signature not in text
    ]
    if missing:
        reasons.append(f"{input_name} missing signatures: " + ", ".join(missing))

    lineage_any = case_spec.get("lineage_any", [])
    if lineage_any and not any(marker in text for marker in lineage_any):
        reasons.append(f"{input_name} lacks lineage marker from {lineage_any}")

    return not reasons, reasons


def discover_case(qpx_root: Path, spec: dict) -> Path:
    case_spec = spec["case"]
    checked: list[tuple[Path, list[str]]] = []

    for relative in case_spec.get("preferred_paths", []):
        case = qpx_root / relative
        ok, reasons = validate_case(case, spec)
        checked.append((case, reasons))
        if ok:
            return case

    for name in case_spec.get("search_names", []):
        for case in sorted(qpx_root.rglob(name)):
            if not case.is_dir():
                continue
            ok, reasons = validate_case(case, spec)
            checked.append((case, reasons))
            if ok:
                return case

    lines = [f"Could not locate accepted case for spec {spec.get('name')}."]
    for case, reasons in checked[:30]:
        lines.append(f"  {case}: " + ("; ".join(reasons) if reasons else "not accepted"))
    raise SystemExit("\n".join(lines))


def _write_run_script(path: Path, spec: dict) -> None:
    profile = spec.get("profile", {})
    env_name = spec.get("runtime", {}).get("conda_env")
    issue = profile.get("issue")

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        'if [ "$#" -lt 1 ]; then',
        '  echo "usage: $0 /path/to/qpx-opt [LABEL]" >&2',
        "  exit 2",
        "fi",
        "",
    ]
    if env_name:
        lines.extend(
            [
                f'if [ "${{CONDA_DEFAULT_ENV:-}}" != "{env_name}" ]; then',
                f'  echo "ERROR: accepted QPX runtime requires: conda activate {env_name}" >&2',
                '  echo "CONDA_DEFAULT_ENV=${CONDA_DEFAULT_ENV:-UNSET}" >&2',
                "  exit 3",
                "fi",
                "",
            ]
        )

    lines.extend(
        [
            'QPX="$(realpath "$1")"',
            f'LABEL="${{2:-{profile.get("label", "profile")}}}"',
            'HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'export PYTHONPATH="${HERE}${PYTHONPATH:+:${PYTHONPATH}}"',
            "",
            'exec python3 -m qpx_harness.performance.profiling \\',
            '  --qpx "${QPX}" \\',
            '  --case-dir "${HERE}/case" \\',
            f'  --input "{profile.get("input", "input.i")}" \\',
            '  --label "${LABEL}" \\',
        ]
    )
    if issue is not None:
        lines.append(f'  --issue "{issue}" \\')
    lines.extend(
        [
            f'  --prefix "{profile.get("prefix", "qpxh")}" \\',
            f'  --output-namespace "{profile.get("output_namespace", "profiles")}" \\',
            f'  --num-steps "{profile.get("num_steps", 1)}"',
            "",
        ]
    )
    path.write_text("\n".join(lines))
    path.chmod(0o755)


def build_bundle(
    *,
    spec_path: Path,
    qpx_root: Path,
    output: Path,
    package_root: Path | None = None,
) -> Path:
    spec_path = spec_path.expanduser().resolve()
    qpx_root = qpx_root.expanduser().resolve()
    output = output.expanduser().resolve()
    spec = load_spec(spec_path)
    case = discover_case(qpx_root, spec)
    print(f"ACCEPTED_CASE={case}")

    package_root = (package_root or Path(__file__).resolve().parents[1]).resolve()
    staging = output.parent / (output.stem + "_staging")
    if staging.exists():
        shutil.rmtree(staging)

    bundle_name = spec.get("bundle_name", spec.get("name", "qpx_profile_bundle"))
    bundle_dir = staging / bundle_name
    case_dst = bundle_dir / "case"
    pkg_dst = bundle_dir / "qpx_harness"
    case_dst.mkdir(parents=True)
    pkg_dst.mkdir(parents=True)

    required_files = spec["case"].get("required_files", ["input.i"])
    for name in required_files:
        shutil.copy2(case / name, case_dst / name)

    for name in ("__init__.py", "runtime.py", "evidence.py", "profiling.py"):
        shutil.copy2(package_root / "qpx_harness" / name, pkg_dst / name)

    shutil.copy2(spec_path, bundle_dir / "bundle_spec.json")
    _write_run_script(bundle_dir / "run.sh", spec)

    manifest_targets = [
        *sorted(case_dst.iterdir()),
        *sorted(pkg_dst.iterdir()),
        bundle_dir / "bundle_spec.json",
        bundle_dir / "run.sh",
    ]
    (bundle_dir / "MANIFEST_SHA256.txt").write_text(
        "".join(
            f"{sha256_file(item)}  {item.relative_to(bundle_dir)}\n"
            for item in manifest_targets
            if item.is_file()
        )
    )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(bundle_dir.rglob("*")):
            if item.is_file():
                archive.write(item, item.relative_to(bundle_dir.parent))

    print(f"WROTE={output}")
    print(f"ZIP_SHA256={sha256_file(output)}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--qpx-root", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    spec = load_spec(spec_path)
    output = Path(args.output) if args.output else Path(
        spec.get("default_output", f"{spec.get('bundle_name', 'qpx_profile_bundle')}.zip")
    )
    build_bundle(spec_path=spec_path, qpx_root=Path(args.qpx_root), output=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
