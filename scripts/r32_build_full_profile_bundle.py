#!/usr/bin/env python3
"""Build the issue #32 full profiling bundle from the exact accepted local QVT case."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import zipfile
from pathlib import Path

EXPECTED_MESH_SHA256 = "a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
EXPECTED_TRANSPORT_SHA256 = "2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d"

REQUIRED_INPUT_SIGNATURES = [
    "QPXThermalDiffusionMaterial",
    "transport_data_file = transport_data.txt",
    "QPXFVMixtureAveragedDiffusion",
    "QPXFVConservativeMassFractionTimeDerivative",
    "WCNSFVMassTimeDerivative",
    "w_O2_constraint",
    "rho_mat",
]

PREFERRED_RELATIVE_CASES = [
    "temp/regression_workspace/tests/heavy_transport/qvt_six_species_transient_inventory",
    "temp/test_workspace/heavy_transport/qvt_six_species_transient_inventory",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_case(case: Path) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    input_path = case / "input.i"
    mesh = case / "qvt.msh"
    transport = case / "transport_data.txt"

    for path in (input_path, mesh, transport):
        if not path.is_file():
            reasons.append(f"missing {path.name}")
    if reasons:
        return False, reasons

    mesh_sha = sha256(mesh)
    transport_sha = sha256(transport)
    if mesh_sha != EXPECTED_MESH_SHA256:
        reasons.append(f"qvt.msh sha256 mismatch: {mesh_sha}")
    if transport_sha != EXPECTED_TRANSPORT_SHA256:
        reasons.append(f"transport_data.txt sha256 mismatch: {transport_sha}")

    text = input_path.read_text(errors="replace")
    missing = [signature for signature in REQUIRED_INPUT_SIGNATURES if signature not in text]
    if missing:
        reasons.append("input.i missing signatures: " + ", ".join(missing))
    if "R22" not in text and "transient six-species" not in text:
        reasons.append("input.i lacks R22/transient-six-species lineage marker")

    return not reasons, reasons


def discover(qpx_root: Path) -> Path:
    checked: list[tuple[Path, list[str]]] = []

    for relative in PREFERRED_RELATIVE_CASES:
        case = qpx_root / relative
        ok, reasons = validate_case(case)
        checked.append((case, reasons))
        if ok:
            return case

    for case in sorted(qpx_root.rglob("qvt_six_species_transient_inventory")):
        if not case.is_dir():
            continue
        ok, reasons = validate_case(case)
        checked.append((case, reasons))
        if ok:
            return case

    lines = ["Could not locate the exact accepted qvt_six_species_transient_inventory case."]
    for case, reasons in checked[:20]:
        lines.append(f"  {case}: " + ("; ".join(reasons) if reasons else "not accepted"))
    raise SystemExit("\n".join(lines))


def write_run_script(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 /path/to/qpx-opt [LABEL]" >&2
  exit 2
fi

if [ "${CONDA_DEFAULT_ENV:-}" != "moose" ]; then
  echo "ERROR: accepted QPX runtime requires: conda activate moose" >&2
  echo "CONDA_DEFAULT_ENV=${CONDA_DEFAULT_ENV:-UNSET}" >&2
  exit 3
fi

QPX="$(realpath "$1")"
LABEL="${2:-T2-heavy}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "${HERE}/r32_profile_qpx_case.py" \\
  --qpx "${QPX}" \\
  --case-dir "${HERE}/case" \\
  --input input.i \\
  --label "${LABEL}"
"""
    )
    path.chmod(0o755)


def make_zip(bundle_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, path.relative_to(bundle_dir.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpx-root", required=True, help="Local QPX source/workspace root")
    parser.add_argument("--output", default="r32_full_profile_case.zip")
    parser.add_argument(
        "--profiler",
        default=str(Path(__file__).resolve().parent / "r32_profile_qpx_case.py"),
        help="Profiler script to copy into the bundle",
    )
    args = parser.parse_args()

    qpx_root = Path(args.qpx_root).expanduser().resolve()
    if not qpx_root.is_dir():
        raise SystemExit(f"QPX root does not exist: {qpx_root}")

    profiler = Path(args.profiler).expanduser().resolve()
    if not profiler.is_file():
        raise SystemExit(f"profiler script does not exist: {profiler}")

    case = discover(qpx_root)
    print(f"ACCEPTED_CASE={case}")

    output = Path(args.output).expanduser().resolve()
    staging = output.parent / (output.stem + "_staging")
    if staging.exists():
        shutil.rmtree(staging)

    bundle = staging / "r32_full_profile_case"
    case_dst = bundle / "case"
    case_dst.mkdir(parents=True)

    for name in ("input.i", "qvt.msh", "transport_data.txt"):
        shutil.copy2(case / name, case_dst / name)

    shutil.copy2(profiler, bundle / "r32_profile_qpx_case.py")
    (bundle / "r32_profile_qpx_case.py").chmod(0o755)
    write_run_script(bundle / "run.sh")

    manifest_targets = [
        case_dst / "input.i",
        case_dst / "qvt.msh",
        case_dst / "transport_data.txt",
        bundle / "r32_profile_qpx_case.py",
        bundle / "run.sh",
    ]
    (bundle / "MANIFEST_SHA256.txt").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(bundle)}\n" for path in manifest_targets)
    )

    assert sha256(case_dst / "qvt.msh") == EXPECTED_MESH_SHA256
    assert sha256(case_dst / "transport_data.txt") == EXPECTED_TRANSPORT_SHA256

    make_zip(bundle, output)
    print(f"WROTE={output}")
    print(f"ZIP_SHA256={sha256(output)}")
    print("RUN_AFTER_UNZIP:")
    print("  conda activate moose")
    print("  ./r32_full_profile_case/run.sh /path/to/qpx-opt T2-heavy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
