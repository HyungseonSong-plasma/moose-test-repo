#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

X_FOCUS_LEFT = 0.1395
X_FOCUS_RIGHT = 0.14175
Y_FOCUS_BOTTOM = 0.018
Y_FOCUS_IF = 0.099
N_Z = 18

PHYS_FOCUS_IF = 9
PHYS_PLASMA = 10
PHYS_FOCUS_GROUND = 14
PHYS_COVER = 20
PHYS_WAFER = 21
PHYS_FOCUS_RING = 22


def section(lines, start, end):
    i = lines.index(start)
    j = lines.index(end)
    return i, j, lines[i + 1:j]


def parse(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    pi, pj, pb = section(lines, "$PhysicalNames", "$EndPhysicalNames")
    ni, nj, nb = section(lines, "$Nodes", "$EndNodes")
    ei, ej, eb = section(lines, "$Elements", "$EndElements")
    physical = pb[1:]
    nodes = {}
    for line in nb[1:]:
        f = line.split()
        nodes[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))
    elements = []
    for line in eb[1:]:
        f = line.split()
        eid, etype, ntags = map(int, f[:3])
        tags = list(map(int, f[3:3 + ntags]))
        conn = list(map(int, f[3 + ntags:]))
        elements.append((eid, etype, tags, conn))
    return lines, (pi, pj, ni, nj, ei, ej), physical, nodes, elements


def add_focus_ring(nodes, elements):
    interface_edges = [
        e for e in elements
        if e[1] == 1 and e[2] and e[2][0] == PHYS_FOCUS_IF
    ]
    interface_nodes = sorted(
        {n for e in interface_edges for n in e[3]},
        key=lambda n: nodes[n][0],
    )
    if len(interface_edges) != 1 or len(interface_nodes) != 2:
        raise RuntimeError(
            "unexpected plasma_focus_ring interface discretization: "
            f"edges={len(interface_edges)} nodes={len(interface_nodes)}"
        )

    left_top, right_top = interface_nodes
    xl, yl, _ = nodes[left_top]
    xr, yr, _ = nodes[right_top]
    if not (
        abs(xl - X_FOCUS_LEFT) <= 1.0e-12
        and abs(xr - X_FOCUS_RIGHT) <= 1.0e-12
        and abs(yl - Y_FOCUS_IF) <= 1.0e-12
        and abs(yr - Y_FOCUS_IF) <= 1.0e-12
    ):
        raise RuntimeError(
            "plasma_focus_ring interface does not match canonical QVT geometry: "
            f"left=({xl},{yl}) right=({xr},{yr})"
        )

    all_nodes = dict(nodes)
    nid = max(all_nodes)
    levels = np.linspace(Y_FOCUS_BOTTOM, Y_FOCUS_IF, N_Z + 1)
    left = []
    right = []
    for y in levels[:-1]:
        nid += 1
        left.append(nid)
        all_nodes[nid] = (X_FOCUS_LEFT, float(y), 0.0)
        nid += 1
        right.append(nid)
        all_nodes[nid] = (X_FOCUS_RIGHT, float(y), 0.0)
    left.append(left_top)
    right.append(right_top)

    eid = max(e[0] for e in elements)
    new = []

    def add_line(a, b):
        nonlocal eid
        eid += 1
        new.append((eid, 1, [PHYS_FOCUS_GROUND, PHYS_FOCUS_GROUND], [a, b]))

    def add_tri(a, b, c):
        nonlocal eid
        eid += 1
        new.append((eid, 2, [PHYS_FOCUS_RING, PHYS_FOCUS_RING], [a, b, c]))

    for k in range(N_Z):
        l0, r0 = left[k], right[k]
        l1, r1 = left[k + 1], right[k + 1]
        add_tri(l0, r0, r1)
        add_tri(l0, r1, l1)

    add_line(left[0], right[0])
    for k in range(N_Z):
        add_line(left[k], left[k + 1])
        add_line(right[k], right[k + 1])

    return all_nodes, elements + new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("target", type=Path)
    args = ap.parse_args()

    lines, idxs, physical, nodes, elements = parse(args.source)
    pi, pj, ni, nj, ei, ej = idxs
    nodes, elements = add_focus_ring(nodes, elements)

    names = list(physical)
    used = {(int(x.split()[0]), int(x.split()[1])) for x in names}
    if (1, PHYS_FOCUS_GROUND) not in used:
        names.append(f'1 {PHYS_FOCUS_GROUND} "focus_ring_ground"')
    if (2, PHYS_FOCUS_RING) not in used:
        names.append(f'2 {PHYS_FOCUS_RING} "focus_ring"')

    def eline(e):
        eid, etype, tags, conn = e
        return " ".join(map(str, [eid, etype, len(tags), *tags, *conn]))

    out = []
    out.extend(lines[:pi])
    out += ["$PhysicalNames", str(len(names)), *names, "$EndPhysicalNames"]
    out.extend(lines[pj + 1:ni])
    sn = sorted(nodes.items())
    out += ["$Nodes", str(len(sn))]
    out += [f"{nid} {x:.16g} {y:.16g} {z:.16g}" for nid, (x, y, z) in sn]
    out += ["$EndNodes"]
    out.extend(lines[nj + 1:ei])
    se = sorted(elements, key=lambda e: e[0])
    out += ["$Elements", str(len(se)), *[eline(e) for e in se], "$EndElements"]
    out.extend(lines[ej + 1:])
    args.target.write_text("\n".join(out) + "\n", encoding="utf-8")

    counts = {}
    for e in se:
        if e[1] == 2 and e[2]:
            counts[e[2][0]] = counts.get(e[2][0], 0) + 1
    expected = {
        PHYS_PLASMA: 1826,
        PHYS_COVER: 303,
        PHYS_WAFER: 146,
        PHYS_FOCUS_RING: 36,
    }
    observed = {pid: counts.get(pid, 0) for pid in expected}
    if observed != expected:
        raise RuntimeError(
            f"unexpected triangle counts: expected={expected} observed={observed}"
        )

    print(
        "FOCUS_RING_BLOCK_MESH_PASS "
        f"nodes={len(sn)} elements={len(se)} "
        f"plasma_triangles={observed[PHYS_PLASMA]} "
        f"cover_triangles={observed[PHYS_COVER]} "
        f"wafer_triangles={observed[PHYS_WAFER]} "
        f"focus_ring_triangles={observed[PHYS_FOCUS_RING]} "
        f"focus_ring_bbox=({X_FOCUS_LEFT},{Y_FOCUS_BOTTOM})-"
        f"({X_FOCUS_RIGHT},{Y_FOCUS_IF})"
    )


if __name__ == "__main__":
    main()
