#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay

Y_COVER_IF = 0.3195
Y_COVER_TOP = 0.342
X_COVER_RIGHT = 0.234
Y_WAFER_BOTTOM = 0.090
Y_WAFER_IF = 0.099
X_WAFER_RIGHT = 0.135

PHYS_AXIS = 1
PHYS_COVER_IF = 7
PHYS_WAFER_IF = 8
PHYS_COVER_TOP = 11
PHYS_COVER_RIGHT = 12
PHYS_WAFER_ELECTRODE = 13
PHYS_PLASMA = 10
PHYS_COVER = 20
PHYS_WAFER = 21


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


def add_unstructured_cover(nodes, elements):
    interface_edges = [e for e in elements if e[1] == 1 and e[2] and e[2][0] == PHYS_COVER_IF]
    interface_nodes = sorted({n for e in interface_edges for n in e[3]}, key=lambda n: nodes[n][0])
    if len(interface_edges) != 53 or len(interface_nodes) != 54:
        raise RuntimeError("unexpected plasma_cover interface discretization")

    kept = []
    for e in elements:
        phys = e[2][0] if e[2] else None
        ys = [nodes[n][1] for n in e[3]]
        remove = (
            phys == PHYS_COVER
            or phys in (PHYS_COVER_TOP, PHYS_COVER_RIGHT)
            or (phys == PHYS_AXIS and max(ys) > Y_COVER_IF + 1e-12)
        )
        if not remove:
            kept.append(e)
    kept_nodes = {nid: xyz for nid, xyz in nodes.items() if xyz[1] <= Y_COVER_IF + 1e-12}

    xs = np.array([kept_nodes[n][0] for n in interface_nodes])
    rng = np.random.default_rng(20261012)
    pts = [(float(x), Y_COVER_IF) for x in xs]
    top_x = np.linspace(0.0, X_COVER_RIGHT, 21)
    pts += [(float(x), Y_COVER_TOP) for x in top_x[1:-1]]
    side_y = [0.3230, 0.3285, 0.3350]
    for y in side_y:
        pts += [(0.0, y), (X_COVER_RIGHT, y)]
    pts += [(0.0, Y_COVER_TOP), (X_COVER_RIGHT, Y_COVER_TOP)]

    def h(y):
        eta = (y - Y_COVER_IF) / (Y_COVER_TOP - Y_COVER_IF)
        return 0.0038 + 0.0082 * eta ** 0.85

    interior = 0
    for _ in range(30000):
        y = Y_COVER_IF + (Y_COVER_TOP - Y_COVER_IF) * rng.random() ** 1.5
        x = X_COVER_RIGHT * rng.random()
        if x < 0.0015 or x > X_COVER_RIGHT - 0.0015:
            continue
        if y < Y_COVER_IF + 0.0012 or y > Y_COVER_TOP - 0.0015:
            continue
        hc = h(y)
        if all((x-xp)**2 + (y-yp)**2 >= (0.72*min(hc, h(yp)))**2 for xp, yp in pts):
            pts.append((x, y))
            interior += 1
        if interior >= 112:
            break

    arr = np.array(pts)
    simplices = Delaunay(arr).simplices.copy()
    edges = {tuple(sorted((int(a), int(b)))) for s in simplices for a, b in ((s[0],s[1]),(s[1],s[2]),(s[2],s[0]))}
    c2i = {tuple(p): i for i, p in enumerate(pts)}
    chains = [
        list(range(54)),
        [c2i[(float(x), Y_COVER_TOP)] for x in top_x],
        [c2i[(0.0, Y_COVER_IF)], *[c2i[(0.0, y)] for y in side_y], c2i[(0.0, Y_COVER_TOP)]],
        [c2i[(X_COVER_RIGHT, Y_COVER_IF)], *[c2i[(X_COVER_RIGHT, y)] for y in side_y], c2i[(X_COVER_RIGHT, Y_COVER_TOP)]],
    ]
    for chain in chains:
        for a, b in zip(chain[:-1], chain[1:]):
            if tuple(sorted((a, b))) not in edges:
                raise RuntimeError("cover Delaunay boundary segment missing")

    all_nodes = dict(kept_nodes)
    local_to_global = {i: n for i, n in enumerate(interface_nodes)}
    nid = max(all_nodes)
    for i in range(54, len(pts)):
        nid += 1
        local_to_global[i] = nid
        x, y = pts[i]
        all_nodes[nid] = (float(x), float(y), 0.0)

    eid = max(e[0] for e in kept)
    new = []
    def add_line(phys, a, b):
        nonlocal eid
        eid += 1
        new.append((eid, 1, [phys, phys], [local_to_global[a], local_to_global[b]]))
    def add_tri(s):
        nonlocal eid
        a, b, c = map(int, s)
        pa, pb, pc = arr[a], arr[b], arr[c]
        area2 = (pb[0]-pa[0])*(pc[1]-pa[1]) - (pb[1]-pa[1])*(pc[0]-pa[0])
        if area2 < 0:
            b, c = c, b
        eid += 1
        new.append((eid, 2, [PHYS_COVER, PHYS_COVER], [local_to_global[a], local_to_global[b], local_to_global[c]]))
    for s in simplices:
        add_tri(s)
    top, axis, right = chains[1], chains[2], chains[3]
    for a, b in zip(axis[:-1], axis[1:]):
        add_line(PHYS_AXIS, a, b)
    for a, b in zip(right[:-1], right[1:]):
        add_line(PHYS_COVER_RIGHT, a, b)
    for a, b in zip(top[:-1], top[1:]):
        add_line(PHYS_COVER_TOP, a, b)
    return all_nodes, kept + new


def add_unstructured_wafer(nodes, elements):
    interface_edges = [e for e in elements if e[1] == 1 and e[2] and e[2][0] == PHYS_WAFER_IF]
    interface_nodes = sorted({n for e in interface_edges for n in e[3]}, key=lambda n: nodes[n][0])
    if len(interface_edges) != 31 or len(interface_nodes) != 32:
        raise RuntimeError("unexpected plasma_wafer interface discretization")

    rng = np.random.default_rng(20261068)
    pts = [(nodes[n][0], Y_WAFER_IF) for n in interface_nodes]
    bottom_x = [0.0]
    x = 0.0
    toggle = 0
    while x < X_WAFER_RIGHT - 1e-12:
        step = 0.0070 + (0.0012 if toggle % 2 == 0 else -0.0005)
        x = min(X_WAFER_RIGHT, x + step)
        bottom_x.append(float(x))
        toggle += 1
    pts += [(x, Y_WAFER_BOTTOM) for x in bottom_x[1:]]
    pts += [(X_WAFER_RIGHT, 0.0952), (0.0, 0.0948)]
    if (0.0, Y_WAFER_BOTTOM) not in pts:
        pts.append((0.0, Y_WAFER_BOTTOM))

    def h(y):
        eta = (Y_WAFER_IF-y) / (Y_WAFER_IF-Y_WAFER_BOTTOM)
        return 0.0037 + 0.0028 * eta ** 0.85

    interior = 0
    for _ in range(20000):
        y = Y_WAFER_IF - (Y_WAFER_IF-Y_WAFER_BOTTOM) * rng.random() ** 1.7
        x = X_WAFER_RIGHT * rng.random()
        if x < 0.0012 or x > X_WAFER_RIGHT - 0.0012:
            continue
        if y < Y_WAFER_BOTTOM + 0.0011 or y > Y_WAFER_IF - 0.0010:
            continue
        hc = h(y)
        if all((x-xp)**2 + (y-yp)**2 >= (0.70*min(hc, h(yp)))**2 for xp, yp in pts):
            pts.append((x, y))
            interior += 1
        if interior >= 47:
            break

    arr = np.array(pts)
    simplices = Delaunay(arr).simplices.copy()
    edges = {tuple(sorted((int(a), int(b)))) for s in simplices for a, b in ((s[0],s[1]),(s[1],s[2]),(s[2],s[0]))}
    c2i = {tuple(p): i for i, p in enumerate(pts)}
    interface = list(range(len(interface_nodes)))
    bottom = [c2i[(float(x), Y_WAFER_BOTTOM)] for x in bottom_x]
    axis = [c2i[(0.0, Y_WAFER_IF)], c2i[(0.0, 0.0948)], c2i[(0.0, Y_WAFER_BOTTOM)]]
    right = [c2i[(X_WAFER_RIGHT, Y_WAFER_IF)], c2i[(X_WAFER_RIGHT, 0.0952)], c2i[(X_WAFER_RIGHT, Y_WAFER_BOTTOM)]]
    for chain in (interface, bottom, axis, right):
        for a, b in zip(chain[:-1], chain[1:]):
            if tuple(sorted((a, b))) not in edges:
                raise RuntimeError("wafer Delaunay boundary segment missing")

    all_nodes = dict(nodes)
    local_to_global = {i: n for i, n in enumerate(interface_nodes)}
    nid = max(all_nodes)
    for i in range(len(interface_nodes), len(pts)):
        nid += 1
        local_to_global[i] = nid
        x, y = pts[i]
        all_nodes[nid] = (float(x), float(y), 0.0)

    eid = max(e[0] for e in elements)
    new = []
    def add_line(phys, a, b):
        nonlocal eid
        eid += 1
        new.append((eid, 1, [phys, phys], [local_to_global[a], local_to_global[b]]))
    def add_tri(s):
        nonlocal eid
        a, b, c = map(int, s)
        pa, pb, pc = arr[a], arr[b], arr[c]
        area2 = (pb[0]-pa[0])*(pc[1]-pa[1]) - (pb[1]-pa[1])*(pc[0]-pa[0])
        if area2 < 0:
            b, c = c, b
        eid += 1
        new.append((eid, 2, [PHYS_WAFER, PHYS_WAFER], [local_to_global[a], local_to_global[b], local_to_global[c]]))
    for s in simplices:
        add_tri(s)
    for a, b in zip(axis[:-1], axis[1:]):
        add_line(PHYS_AXIS, a, b)
    for chain in (bottom, right):
        for a, b in zip(chain[:-1], chain[1:]):
            add_line(PHYS_WAFER_ELECTRODE, a, b)
    return all_nodes, elements + new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path, help="fine plasma+cover mesh from extend_cover_mesh.py")
    ap.add_argument("target", type=Path)
    args = ap.parse_args()

    lines, idxs, physical, nodes, elements = parse(args.source)
    pi, pj, ni, nj, ei, ej = idxs
    nodes, elements = add_unstructured_cover(nodes, elements)
    nodes, elements = add_unstructured_wafer(nodes, elements)

    names = list(physical)
    used = {(int(x.split()[0]), int(x.split()[1])) for x in names}
    if (1, PHYS_WAFER_ELECTRODE) not in used:
        names.append(f'1 {PHYS_WAFER_ELECTRODE} "wafer_electrode"')
    if (2, PHYS_WAFER) not in used:
        names.append(f'2 {PHYS_WAFER} "wafer"')

    def eline(e):
        eid, etype, tags, conn = e
        return " ".join(map(str, [eid, etype, len(tags), *tags, *conn]))

    out = []
    out.extend(lines[:pi])
    out += ["$PhysicalNames", str(len(names)), *names, "$EndPhysicalNames"]
    out.extend(lines[pj+1:ni])
    sn = sorted(nodes.items())
    out += ["$Nodes", str(len(sn))]
    out += [f"{nid} {x:.16g} {y:.16g} {z:.16g}" for nid, (x, y, z) in sn]
    out += ["$EndNodes"]
    out.extend(lines[nj+1:ei])
    se = sorted(elements, key=lambda e: e[0])
    out += ["$Elements", str(len(se)), *[eline(e) for e in se], "$EndElements"]
    out.extend(lines[ej+1:])
    args.target.write_text("\n".join(out) + "\n", encoding="utf-8")

    counts = {}
    for e in se:
        if e[1] == 2 and e[2]:
            counts[e[2][0]] = counts.get(e[2][0], 0) + 1
    if (counts.get(PHYS_PLASMA), counts.get(PHYS_COVER), counts.get(PHYS_WAFER)) != (1826, 303, 146):
        raise RuntimeError(f"unexpected triangle counts: {counts}")
    print(
        "UNSTRUCTURED_COVER_WAFER_MESH_PASS "
        f"nodes={len(sn)} elements={len(se)} "
        f"plasma_triangles={counts.get(PHYS_PLASMA,0)} "
        f"cover_triangles={counts.get(PHYS_COVER,0)} "
        f"wafer_triangles={counts.get(PHYS_WAFER,0)}"
    )


if __name__ == "__main__":
    main()
