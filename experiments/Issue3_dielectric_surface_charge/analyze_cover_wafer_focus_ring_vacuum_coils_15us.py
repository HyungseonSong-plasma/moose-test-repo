#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_ANALYZER = Path(__file__).with_name("analyze_cover_wafer_focus_ring_15us.py")
GROUND_COLUMNS = (
    "vacuum_outer_ground_potential",
    "cover_coil_ground_potential",
    "vacuum_coil_ground_potential",
)


def named_block(text: str, name: str) -> str:
    header = f"  [{name}]\n"
    start = text.index(header)
    end = text.index("\n  []", start) + len("\n  []")
    return text[start:end]


def parse_mesh(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    pi = lines.index("$PhysicalNames")
    pj = lines.index("$EndPhysicalNames")
    ni = lines.index("$Nodes")
    nj = lines.index("$EndNodes")
    ei = lines.index("$Elements")
    ej = lines.index("$EndElements")

    physical = {}
    for row in lines[pi+2:pj]:
        dim, pid, name = row.split(maxsplit=2)
        physical[(int(dim), int(pid))] = name.strip().strip('"')

    nodes = {}
    for row in lines[ni+2:nj]:
        f = row.split()
        nodes[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))

    elems = []
    for row in lines[ei+2:ej]:
        f = row.split()
        eid, etype, ntags = map(int, f[:3])
        tags = list(map(int, f[3:3+ntags]))
        conn = list(map(int, f[3+ntags:]))
        elems.append((eid, etype, tags, conn))
    return physical, nodes, elems


def coord_key(x: float, y: float):
    return (round(x, 13), round(y, 13))


def mesh_checks(mesh_path: Path):
    physical, nodes, elems = parse_mesh(mesh_path)
    name_to_pid = {(dim, name): pid for (dim,pid), name in physical.items()}
    checks = {}

    for name in ("vacuum", "coil1", "coil2", "coil3"):
        checks[f"mesh_has_{name}_block"] = (2, name) in name_to_pid
    checks["single_vacuum_physical_block"] = sum(
        1 for (dim,_pid), name in physical.items() if dim == 2 and name == "vacuum"
    ) == 1
    for name in ("vacuum_outer_ground", "cover_vacuum", "cover_coil_ground", "vacuum_coil_ground"):
        checks[f"mesh_has_{name}_boundary"] = (1, name) in name_to_pid

    tri_counts = {}
    for _eid, etype, tags, _conn in elems:
        if etype == 2 and tags:
            tri_counts[tags[0]] = tri_counts.get(tags[0], 0) + 1
    for name in ("vacuum", "coil1", "coil2", "coil3"):
        pid = name_to_pid.get((2,name))
        checks[f"{name}_triangles_positive"] = bool(pid and tri_counts.get(pid,0) > 0)

    def block_nodes(name, pred):
        pid = name_to_pid[(2,name)]
        ans = set()
        for _eid, etype, tags, conn in elems:
            if etype != 2 or not tags or tags[0] != pid:
                continue
            for nid in conn:
                x,y,_ = nodes[nid]
                if pred(x,y):
                    ans.add(coord_key(x,y))
        return ans

    cover_top = block_nodes("cover", lambda x,y: abs(y-0.342) < 1e-12)
    upper = block_nodes("vacuum", lambda x,y: abs(y-0.342) < 1e-12)
    for name in ("coil1","coil2","coil3"):
        upper |= block_nodes(name, lambda x,y: abs(y-0.342) < 1e-12)
    checks["cover_upper_interface_conforming"] = cover_top == upper and len(cover_top) > 0

    coil_boxes = {
        "coil1": (0.0495,0.0585,0.342,0.360),
        "coil2": (0.1125,0.1215,0.342,0.360),
        "coil3": (0.1710,0.1800,0.342,0.360),
    }
    vac_pid = name_to_pid[(2,"vacuum")]
    vac_tri = [e for e in elems if e[1] == 2 and e[2] and e[2][0] == vac_pid]
    for name,(a,b,y0,y1) in coil_boxes.items():
        coil_if = block_nodes(
            name,
            lambda x,y,a=a,b=b,y1=y1: abs(x-a)<1e-12 or abs(x-b)<1e-12 or abs(y-y1)<1e-12,
        )
        vac_if = set()
        for _eid,_etype,_tags,conn in vac_tri:
            for nid in conn:
                x,y,_ = nodes[nid]
                if (
                    ((abs(x-a)<1e-12 or abs(x-b)<1e-12) and y0-1e-12 <= y <= y1+1e-12)
                    or (abs(y-y1)<1e-12 and a-1e-12 <= x <= b+1e-12)
                ):
                    vac_if.add(coord_key(x,y))
        checks[f"vacuum_{name}_interface_conforming"] = coil_if == vac_if and len(coil_if) > 0

    return checks, tri_counts, physical


def main():
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: analyze_cover_wafer_focus_ring_vacuum_coils_15us.py output.csv input.i mesh.msh"
        )
    csv_path = Path(sys.argv[1])
    input_path = Path(sys.argv[2])
    mesh_path = Path(sys.argv[3])

    text = input_path.read_text(encoding="utf-8")
    rows = list(csv.DictReader(csv_path.open()))
    if not rows:
        raise SystemExit("empty csv")
    missing = [c for c in GROUND_COLUMNS if c not in rows[0]]
    if missing:
        raise SystemExit(f"missing CSV columns: {missing}")

    compat = text.replace(
        "block = 'plasma cover wafer focus_ring vacuum'",
        "block = 'plasma cover wafer focus_ring'",
    )
    with tempfile.NamedTemporaryFile("w", suffix=".i", delete=False) as tmp:
        tmp.write(compat)
        tmp_path = Path(tmp.name)
    try:
        proc = subprocess.run(
            [sys.executable, str(BASE_ANALYZER), str(csv_path), str(tmp_path)],
            text=True,
            capture_output=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    try:
        base = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"base analyzer produced non-JSON output: {proc.stdout}\n{proc.stderr}") from exc

    checks = dict(base.get("checks", {}))
    checks["base_focus_ring_science_pass"] = proc.returncode == 0
    checks["vacuum_eps_r_1"] = "prop_values = '1.0'" in named_block(text, "eps_vacuum")
    checks["potential_spans_vacuum"] = (
        "block = 'plasma cover wafer focus_ring vacuum'" in named_block(text, "potential")
        and "block = 'plasma cover wafer focus_ring vacuum'" in named_block(text, "phi_diffusion")
    )
    potential = named_block(text, "potential")
    checks["coils_are_grounded_conductors_not_unknown_domain"] = all(
        name not in potential for name in ("coil1","coil2","coil3")
    )
    ground = named_block(text, "grounded_potential")
    checks["vacuum_and_coil_ground_routing"] = all(
        token in ground for token in (
            "vacuum_outer_ground", "cover_coil_ground", "vacuum_coil_ground", "cover_outer_right"
        )
    ) and "cover_outer_ground" not in ground
    checks["ground_potential_zero_all_steps"] = all(
        all(abs(float(row[c])) <= 1.0e-10 for c in GROUND_COLUMNS)
        for row in rows
    )

    mesh_extra, tri_counts, physical = mesh_checks(mesh_path)
    checks.update(mesh_extra)

    result = {
        "classification": (
            "COVER_WAFER_FOCUS_RING_VACUUM_COILS_15US_PASS"
            if all(checks.values())
            else "COVER_WAFER_FOCUS_RING_VACUUM_COILS_15US_FAIL"
        ),
        "scope": (
            "15 us Issue #3 full electrostatic geometry: accepted plasma+cover+wafer+focus-ring science preserved; "
            "single conforming unstructured vacuum block eps_r=1; three solid coil blocks represented as grounded conductor obstacles; "
            "vacuum outer top/right grounded; cover-vacuum continuity through shared Lagrange nodes; SEE=0."
        ),
        "checks": checks,
        "diagnostics": {
            "base_analysis": base.get("diagnostics", {}),
            "final_ground_potentials_V": {c: float(rows[-1][c]) for c in GROUND_COLUMNS},
            "triangle_counts_by_physical_id": {str(k): v for k,v in sorted(tri_counts.items())},
            "physical_names": {f"{dim}:{pid}": name for (dim,pid),name in sorted(physical.items())},
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
