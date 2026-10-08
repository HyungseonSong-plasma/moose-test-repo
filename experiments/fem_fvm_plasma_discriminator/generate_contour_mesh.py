#!/usr/bin/env python3
from pathlib import Path
import math
import numpy as np
from scipy.spatial import Delaunay

HERE = Path(__file__).resolve().parent
OUT = HERE / "plasma_contour_l3_4p5mm.msh"
RNG = np.random.default_rng(20261008)

# Exact plasma outline from the real QVT geometry.
POLY = np.array([
    [0.0, 0.099],
    [0.0, 0.3195],
    [0.234, 0.3195],
    [0.234, 0.279],
    [0.243, 0.279],
    [0.243, 0.018],
    [0.144, 0.018],
    [0.144, 0.099],
    [0.14175, 0.099],
    [0.1395, 0.099],
    [0.135, 0.099],
], dtype=float)

SEGMENTS = [
    ("axis", (0.0, 0.099), (0.0, 0.3195)),
    ("plasma_cover", (0.0, 0.3195), (0.234, 0.3195)),
    ("inlet", (0.234, 0.3195), (0.234, 0.279)),
    ("plasma_right", (0.234, 0.279), (0.243, 0.279)),
    ("plasma_right", (0.243, 0.279), (0.243, 0.018)),
    ("outlet", (0.243, 0.018), (0.144, 0.018)),
    ("plasma_metal", (0.144, 0.018), (0.144, 0.099)),
    ("plasma_metal", (0.144, 0.099), (0.14175, 0.099)),
    ("plasma_focus_ring", (0.14175, 0.099), (0.1395, 0.099)),
    ("plasma_electrode", (0.1395, 0.099), (0.135, 0.099)),
    ("plasma_wafer", (0.135, 0.099), (0.0, 0.099)),
]

PHYS = {
    "axis": 1,
    "inlet": 2,
    "outlet": 3,
    "plasma_electrode": 4,
    "plasma_metal": 5,
    "plasma_right": 6,
    "plasma_cover": 7,
    "plasma_wafer": 8,
    "plasma_focus_ring": 9,
    "plasma": 10,
}

# Accepted 3-level design.
T3 = 0.0155       # L3 shell thickness [m]
T2 = 0.0190       # L2 shell thickness [m]
H1 = 0.0220       # L1 nominal spacing [m]
H2 = 0.0110       # L2 nominal spacing [m]
H3 = 0.0045       # L3 + physical boundary spacing [m]


def point_on_segment(p, a, b, tol=1e-11):
    p = np.asarray(p); a = np.asarray(a); b = np.asarray(b)
    ab = b - a
    ap = p - a
    cross = abs(ab[0] * ap[1] - ab[1] * ap[0])
    if cross > tol * max(1.0, np.linalg.norm(ab)):
        return False
    dot = np.dot(ap, ab)
    return -tol <= dot <= np.dot(ab, ab) + tol


def covers(p):
    # Boundary counts as inside.
    for i in range(len(POLY)):
        if point_on_segment(p, POLY[i], POLY[(i + 1) % len(POLY)]):
            return True
    x, y = float(p[0]), float(p[1])
    inside = False
    j = len(POLY) - 1
    for i in range(len(POLY)):
        xi, yi = POLY[i]
        xj, yj = POLY[j]
        hit = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
        if hit:
            inside = not inside
        j = i
    return inside


def segment_distance(p, a, b):
    p = np.asarray(p); a = np.asarray(a); b = np.asarray(b)
    ab = b - a
    t = np.dot(p - a, ab) / np.dot(ab, ab)
    t = min(1.0, max(0.0, float(t)))
    return float(np.linalg.norm(p - (a + t * ab)))


WALL_SEGMENTS = [(np.asarray(a, float), np.asarray(b, float)) for name, a, b in SEGMENTS if name != "axis"]


def wall_distance(p):
    return min(segment_distance(p, a, b) for a, b in WALL_SEGMENTS)


def zone(p):
    d = wall_distance(p)
    if d <= T3:
        return 3
    if d <= T3 + T2:
        return 2
    return 1


def h_target(p):
    return {1: H1, 2: H2, 3: H3}[zone(p)]


nodes = []
node_map = {}
line_elements = []


def add_node(p):
    p = np.asarray(p, float)
    key = (round(float(p[0]), 12), round(float(p[1]), 12))
    if key not in node_map:
        node_map[key] = len(nodes)
        nodes.append(p.copy())
    return node_map[key]


def add_boundary_segment(name, a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    ids = []
    if name != "axis":
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / H3)))
        ids = [add_node(a + (b - a) * (k / n)) for k in range(n + 1)]
    else:
        # Axis is symmetry, not a physical wall. Let wall distance determine its spacing.
        p = a.copy()
        ids = [add_node(p)]
        while p[1] < b[1] - 1e-12:
            h = h_target(p)
            dz = min(h, b[1] - p[1])
            if b[1] - (p[1] + dz) < 0.35 * h and p[1] + dz < b[1]:
                dz = b[1] - p[1]
            p = np.array([0.0, p[1] + dz])
            ids.append(add_node(p))
    for i in range(len(ids) - 1):
        line_elements.append((ids[i], ids[i + 1], name))


for item in SEGMENTS:
    add_boundary_segment(*item)

n_boundary_nodes = len(nodes)
boundary_points = np.asarray(nodes, float)

# Triangular-lattice candidates in each zone, with a small deterministic jitter.
candidates = []
for h in (H3, H2, H1):
    dy = math.sqrt(3.0) * 0.5 * h
    ys = np.arange(0.018 + 0.5 * dy, 0.3195, dy)
    for j, y in enumerate(ys):
        xoff = 0.5 * h if j % 2 else 0.0
        for x in np.arange(xoff, 0.243, h):
            p = np.array([
                x + RNG.uniform(-0.10 * h, 0.10 * h),
                y + RNG.uniform(-0.10 * h, 0.10 * h),
            ])
            if not covers(p):
                continue
            if abs(h_target(p) - h) > 1e-12:
                continue
            # Avoid points too close to the exact physical boundary nodes.
            if np.min(np.linalg.norm(boundary_points - p, axis=1)) < 0.72 * h:
                continue
            add_node(p)

P = np.asarray(nodes, float)
fixed = np.zeros(len(P), dtype=bool)
fixed[:n_boundary_nodes] = True
original_zone = np.array([zone(p) for p in P])


def triangulate(points):
    all_tri = Delaunay(points).simplices.copy()
    keep = []
    for tri in all_tri:
        q = points[tri]
        samples = [q.mean(axis=0), 0.5 * (q[0] + q[1]), 0.5 * (q[1] + q[2]), 0.5 * (q[2] + q[0])]
        if all(covers(s) for s in samples):
            keep.append(tri)
    return np.asarray(keep, dtype=int)


# Mild Laplacian smoothing, locking exact boundary nodes and keeping each point in its original level.
for _ in range(12):
    T = triangulate(P)
    nbr = [set() for _ in range(len(P))]
    for a, b, c in T:
        nbr[a].update((b, c)); nbr[b].update((a, c)); nbr[c].update((a, b))
    newP = P.copy()
    for i in range(len(P)):
        if fixed[i] or not nbr[i]:
            continue
        mean_nb = P[list(nbr[i])].mean(axis=0)
        trial = 0.65 * P[i] + 0.35 * mean_nb
        if covers(trial) and zone(trial) == original_zone[i]:
            newP[i] = trial
    P = newP

T = triangulate(P)

# Verify every named boundary line is an actual triangle side.
edge_set = set()
for tri in T:
    for i, j in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
        edge_set.add(tuple(sorted((int(i), int(j)))))
for i, j, name in line_elements:
    if tuple(sorted((i, j))) not in edge_set:
        raise RuntimeError(f"boundary edge missing from triangulation: {name} {i}-{j}")

# Triangle-quality diagnostics.
q = P[T]
a = np.linalg.norm(q[:, 1] - q[:, 2], axis=1)
b = np.linalg.norm(q[:, 0] - q[:, 2], axis=1)
c = np.linalg.norm(q[:, 0] - q[:, 1], axis=1)


def angle(opposite, s1, s2):
    cv = (s1 * s1 + s2 * s2 - opposite * opposite) / (2.0 * s1 * s2)
    return np.degrees(np.arccos(np.clip(cv, -1.0, 1.0)))


min_angle = np.minimum.reduce((angle(a, b, c), angle(b, a, c), angle(c, a, b)))
edge_ratio = np.maximum.reduce((a, b, c)) / np.minimum.reduce((a, b, c))

# Gmsh 2.2 ASCII with named physical curves and one plasma surface block.
out = []
out += ["$MeshFormat", "2.2 0 8", "$EndMeshFormat"]
out += ["$PhysicalNames", str(len(PHYS))]
for name, pid in PHYS.items():
    dim = 2 if name == "plasma" else 1
    out.append(f'{dim} {pid} "{name}"')
out += ["$EndPhysicalNames", "$Nodes", str(len(P))]
for i, (r, z) in enumerate(P, 1):
    out.append(f"{i} {r:.16g} {z:.16g} 0")
out += ["$EndNodes", "$Elements", str(len(line_elements) + len(T))]

eid = 1
for i, j, name in line_elements:
    pid = PHYS[name]
    out.append(f"{eid} 1 2 {pid} {pid} {i + 1} {j + 1}")
    eid += 1
for tri in T:
    pts = P[tri]
    signed = (pts[1, 0] - pts[0, 0]) * (pts[2, 1] - pts[0, 1]) - (pts[2, 0] - pts[0, 0]) * (pts[1, 1] - pts[0, 1])
    if signed < 0:
        tri = tri[[0, 2, 1]]
    out.append(f"{eid} 2 2 {PHYS['plasma']} 1 {tri[0] + 1} {tri[1] + 1} {tri[2] + 1}")
    eid += 1
out.append("$EndElements")
OUT.write_text("\n".join(out) + "\n", encoding="utf-8")

print(f"wrote {OUT}")
print(f"nodes={len(P)} triangles={len(T)}")
print(f"L1 h={H1*1e3:g} mm; L2 h={H2*1e3:g} mm; L3/boundary h={H3*1e3:g} mm")
print(f"L3 thickness={T3*1e3:g} mm; L2 thickness={T2*1e3:g} mm")
print(f"min_angle={min_angle.min():.3f} deg")
print(f"p05_min_angle={np.percentile(min_angle, 5):.3f} deg")
print(f"median_min_angle={np.median(min_angle):.3f} deg")
print(f"p95_edge_ratio={np.percentile(edge_ratio, 95):.3f}")
print(f"max_edge_ratio={edge_ratio.max():.3f}")
