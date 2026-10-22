#!/usr/bin/env python3
"""Materialize the canonical Issue #397 graded-coarse L1 plasma/wafer mesh.

This utility is the authoritative mesh-selection entry point for NEW Issue
#397 200 W EI17 experiments. It never edits upstream dielectric meshes, does
not change any species/sheath BC, and refuses a mesh with an unexpected hash.

Usage:
  python3 issue397_materialize_l1_baseline.py SOURCE_PRE2X.msh OUTPUT.msh
  python3 issue397_materialize_l1_baseline.py SOURCE_PRE2X.msh OUTPUT.msh --check-only
  python3 issue397_materialize_l1_baseline.py --verify-existing BASELINE_L1.msh

SOURCE_PRE2X.msh must come from the original geometry preparation chain.
OUTPUT.msh should be the transient simulation mesh path in Issue395.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from issue397_build_graded_mesh import run
from issue397_graded_mesh_geometry import parse, physical_faces, plasma_wafer_interface_ownership, validate, area_groups, boundary_groups


CONTRACT = Path(__file__).with_name("issue397_baseline_mesh.json")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(128 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _manifest() -> dict:
    spec = json.loads(CONTRACT.read_text(encoding="utf8"))
    assert spec["role"] == "ACTIVE_EXPERIMENT_BASELINE_MESH"
    assert spec["baseline_level"] == 1
    return spec


def verify(path: Path, manifest: dict) -> dict:
    meta = manifest["baseline_mesh"]
    digest = _sha(path)
    if digest != meta["sha256"]:
        raise RuntimeError(
            f"Wrong Issue397 L1 mesh sha256={digest}; required={meta['sha256']}"
        )
    _, nodes, elems = parse(path)
    wafer, _ = physical_faces(nodes, elems)
    used_nodes = {node for _, _, conn in elems for node in conn}
    tri_count = sum(kind == 2 for kind, _, _ in elems)
    physics = {tags[0] for _, tags, _ in elems}
    expected = (meta["nodes"], meta["triangles_2d"], meta["wafer_faces"],
                meta["physical_groups"])
    actual = (len(used_nodes), tri_count, len(wafer), len(physics))
    if actual != expected:
        raise RuntimeError(f"Mesh topology mismatch: actual={actual} expected={expected}")
    n=plasma_wafer_interface_ownership(elems)
    if n != meta["wafer_faces"]:
        raise RuntimeError("Not all wafer faces have plasma-side ownership")
    if abs(wafer[0][0]) > 1e-12 or abs(wafer[-1][1]-.135)>1e-12:
        raise RuntimeError("Wafer extent must be [0, 135] mm")
    return dict(sha256=digest,nodes=len(used_nodes),triangles=tri_count,
                wafer_faces=len(wafer),physical_groups=len(physics),
                plasma_sided_wafer_faces=n)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path, nargs="?")
    p.add_argument("target", type=Path, nargs="?")
    p.add_argument("--check-only", action="store_true",
                   help="generate/check the pinned L1 in a temporary file; do not overwrite output")
    p.add_argument("--verify-existing", type=Path,
                   help="only verify an existing archived L1 .msh against the baseline manifest")
    args=p.parse_args()
    manifest=_manifest()
    if args.verify_existing is not None:
        if args.source or args.target:
            p.error("--verify-existing does not take source/target")
        result=verify(args.verify_existing,manifest)
    else:
        if args.source is None or args.target is None:
            p.error("source and target are required unless --verify-existing")
        if args.source.resolve() == args.target.resolve():
            raise RuntimeError("Refuse to overwrite the historical SOURCE mesh")
        src_sha=_sha(args.source)
        expected=manifest["source_mesh"]["sha256"]
        if src_sha != expected:
            raise RuntimeError(f"Historical source hash mismatch: {src_sha} != {expected}")
        args.target.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp_name=tempfile.mkstemp(prefix=".issue397_l1_",suffix=".msh",
                                     dir=str(args.target.parent))
        os.close(fd)
        temp=Path(tmp_name)
        try:
            # Rebuild the exact validated mesh; run() enforces historical
            # source, 27 faces, material areas, quality, and final SHA.
            run(args.source,temp,level=manifest["baseline_level"])
            result=verify(temp,manifest)
            if not args.check_only:
                temp.replace(args.target)
        finally:
            temp.unlink(missing_ok=True)
    print("ISSUE397_BASELINE_L1_MESH_PASS")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
