#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay

Y_COVER_IF = 0.3195
Y_COVER_TOP = 0.342
Y_COIL_TOP = 0.360
Y_VAC_TOP = 0.432
X_PLASMA_COVER_RIGHT = 0.234
X_RIGHT = 0.243

PHYS_AXIS = 1
PHYS_PLASMA_COVER = 7
PHYS_COVER_OUTER_GROUND = 11
PHYS_COVER_OUTER_RIGHT = 12
PHYS_PLASMA = 10
PHYS_COVER = 20
PHYS_WAFER = 21
PHYS_FOCUS_RING = 22
PHYS_VACUUM = 23
PHYS_COIL1 = 24
PHYS_COIL2 = 25
PHYS_COIL3 = 26

PHYS_VACUUM_OUTER_GROUND = 15
PHYS_COVER_VACUUM = 16
PHYS_COVER_COIL_GROUND = 17
PHYS_VACUUM_COIL_GROUND = 18

COILS = {
    PHYS_COIL1: (0.0495, 0.0585, Y_COVER_TOP, Y_COIL_TOP),
    PHYS_COIL2: (0.1125, 0.1215, Y_COVER_TOP, Y_COIL_TOP),
    PHYS_COIL3: (0.1710, 0.1800, Y_COVER_TOP, Y_COIL_TOP),
}
KEY_X = (0.0, 0.0495, 0.0585, 0.1125, 0.1215, 0.1710, 0.1800, X_RIGHT)


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


def key(x, y):
    return (round(float(x), 13), round(float(y), 13))


def subdivide(a, b, h):
    n = max(1, int(math.ceil((b - a) / h)))
    return np.linspace(a, b, n + 1)


def chain_x(xs, y):
    return [(float(x), float(y)) for x in xs]


def chain_y(x, ys):
    return [(float(x), float(y)) for y in ys]


def orient(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def point_in_triangle(p, a, b, c, tol=1e-13):
    o1 = orient(a, b, p)
    o2 = orient(b, c, p)
    o3 = orient(c, a, p)
    has_neg = (o1 < -tol) or (o2 < -tol) or (o3 < -tol)
    has_pos = (o1 > tol) or (o2 > tol) or (o3 > tol)
    return not (has_neg and has_pos)


def on_segment(a, b, p, tol=1e-13):
    if abs(orient(a, b, p)) > tol:
        return False
    return (
        min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol
        and min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol
    )


def segments_cross(a, b, c, d, tol=1e-13):
    o1, o2 = orient(a,b,c), orient(a,b,d)
    o3, o4 = orient(c,d,a), orient(c,d,b)
    if ((o1 > tol and o2 < -tol) or (o1 < -tol and o2 > tol)) and ((o3 > tol and o4 < -tol) or (o3 < -tol and o4 > tol)):
        return True
    return False


def point_in_open_rect(p, rect, tol=1e-13):
    x0,x1,y0,y1 = rect
    return x0+tol < p[0] < x1-tol and y0+tol < p[1] < y1-tol


def triangle_overlaps_rect(tri_pts, rect):
    x0,x1,y0,y1 = rect
    corners = [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
    if any(point_in_open_rect(p, rect) for p in tri_pts):
        return True
    a,b,c = tri_pts
    for q in corners:
        if point_in_triangle(q,a,b,c):
            if any(abs(q[0]-p[0]) < 1e-13 and abs(q[1]-p[1]) < 1e-13 for p in tri_pts):
                continue
            if any(on_segment(tri_pts[i], tri_pts[(i+1)%3], q) for i in range(3)):
                continue
            return True
    redges = [(corners[i], corners[(i+1)%4]) for i in range(4)]
    tedges = [(tri_pts[i], tri_pts[(i+1)%3]) for i in range(3)]
    for e1 in tedges:
        for e2 in redges:
            if segments_cross(e1[0],e1[1],e2[0],e2[1]):
                return True
    return False


def unique_points(chains):
    out=[]; seen=set()
    for ch in chains:
        for x,y in ch:
            k=key(x,y)
            if k not in seen:
                seen.add(k); out.append((float(x),float(y)))
    return out


def poisson_points(x0,x1,y0,y1,h,rng,accept,target_factor=0.66):
    area=(x1-x0)*(y1-y0)
    target=max(8,int(area/(h*h)*target_factor))
    pts=[]
    for _ in range(250000):
        if len(pts) >= target:
            break
        x=x0+(x1-x0)*rng.random(); y=y0+(y1-y0)*rng.random()
        if not accept(x,y):
            continue
        if min(x-x0,x1-x,y-y0,y1-y) < 0.28*h:
            continue
        if all((x-px)**2+(y-py)**2 >= (0.72*h)**2 for px,py in pts):
            pts.append((x,y))
    return pts


def triangulate_region(boundary_chains, interior, keep_triangle):
    boundary=unique_points(boundary_chains)
    pts=np.asarray(boundary+interior,dtype=float)
    simplices=Delaunay(pts).simplices.copy()
    kept=[]
    for s in simplices:
        tp=[tuple(pts[int(i)]) for i in s]
        if keep_triangle(tp):
            if orient(tp[0],tp[1],tp[2]) < 0:
                s=np.array([s[0],s[2],s[1]])
            kept.append(s)
    tri=np.asarray(kept,dtype=int)
    edges={tuple(sorted((int(a),int(b)))) for s in tri for a,b in ((s[0],s[1]),(s[1],s[2]),(s[2],s[0]))}
    pindex={key(*p):i for i,p in enumerate(boundary+interior)}
    for ch in boundary_chains:
        for a,b in zip(ch[:-1],ch[1:]):
            ia,ib=pindex[key(*a)],pindex[key(*b)]
            if tuple(sorted((ia,ib))) not in edges:
                raise RuntimeError(f"required boundary segment missing from Delaunay mesh: {a}->{b}")
    return pts,tri


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("source",type=Path)
    ap.add_argument("target",type=Path)
    args=ap.parse_args()
    lines,idxs,physical,nodes,elements=parse(args.source)
    pi,pj,ni,nj,ei,ej=idxs

    kept=[]
    for e in elements:
        phys=e[2][0] if e[2] else None
        ys=[nodes[n][1] for n in e[3]]
        remove=(
            (e[1] == 2 and phys == PHYS_COVER)
            or (e[1] == 1 and phys in (PHYS_COVER_OUTER_GROUND, PHYS_COVER_OUTER_RIGHT))
            or (e[1] == 1 and phys == PHYS_AXIS and max(ys) > Y_COVER_IF + 1e-12)
        )
        if not remove:
            kept.append(e)

    plasma_cover_edges=[e for e in kept if e[1]==1 and e[2] and e[2][0]==PHYS_PLASMA_COVER]
    interface_nodes=sorted({n for e in plasma_cover_edges for n in e[3]},key=lambda n:nodes[n][0])
    if len(plasma_cover_edges)!=53 or len(interface_nodes)!=54:
        raise RuntimeError("unexpected plasma_cover interface discretization")
    bottom=[(nodes[n][0],nodes[n][1]) for n in interface_nodes]
    if abs(bottom[0][0])>1e-12 or abs(bottom[-1][0]-X_PLASMA_COVER_RIGHT)>1e-12:
        raise RuntimeError("unexpected plasma_cover interface extent")
    bottom += [(float(x),Y_COVER_IF) for x in subdivide(X_PLASMA_COVER_RIGHT,X_RIGHT,0.0045)[1:]]

    master_x=[]
    for a,b in zip(KEY_X[:-1],KEY_X[1:]):
        xs=subdivide(a,b,0.0055)
        if master_x:
            xs=xs[1:]
        master_x.extend(xs.tolist())
    master_x=np.asarray(master_x)

    rng=np.random.default_rng(20261012)
    coord_to_nid={}; new_nodes={}
    def get_nid(x,y):
        k=key(x,y)
        if k not in coord_to_nid:
            nid=len(coord_to_nid)+1
            coord_to_nid[k]=nid
            new_nodes[nid]=(float(x),float(y),0.0)
        return coord_to_nid[k]

    new_kept=[]
    for e in kept:
        conn=[get_nid(nodes[n][0],nodes[n][1]) for n in e[3]]
        new_kept.append((e[0],e[1],list(e[2]),conn))

    eid=max(e[0] for e in new_kept)
    added=[]
    block_counts={}

    def add_triangulation(pid,pts,tri):
        nonlocal eid
        lg=[get_nid(p[0],p[1]) for p in pts]
        for s in tri:
            eid+=1
            added.append((eid,2,[pid,pid],[lg[int(s[0])],lg[int(s[1])],lg[int(s[2])]]))
            block_counts[pid]=block_counts.get(pid,0)+1

    def add_line(pid,a,b):
        nonlocal eid
        eid+=1
        added.append((eid,1,[pid,pid],[get_nid(*a),get_nid(*b)]))

    cover_top=chain_x(master_x,Y_COVER_TOP)
    cover_left=chain_y(0.0,subdivide(Y_COVER_IF,Y_COVER_TOP,0.0045))
    cover_right=chain_y(X_RIGHT,subdivide(Y_COVER_IF,Y_COVER_TOP,0.0045))
    cover_boundary=[bottom,cover_top,cover_left,cover_right]
    cover_int=poisson_points(0,X_RIGHT,Y_COVER_IF,Y_COVER_TOP,0.0052,rng,lambda x,y: True)
    cover_pts,cover_tri=triangulate_region(
        cover_boundary,cover_int,
        lambda tp: all(-1e-12 <= p[0] <= X_RIGHT+1e-12 and Y_COVER_IF-1e-12 <= p[1] <= Y_COVER_TOP+1e-12 for p in tp),
    )
    add_triangulation(PHYS_COVER,cover_pts,cover_tri)

    vac_chains=[]
    for a,b in ((0.0,0.0495),(0.0585,0.1125),(0.1215,0.1710),(0.1800,X_RIGHT)):
        xs=master_x[(master_x>=a-1e-12)&(master_x<=b+1e-12)]
        vac_chains.append(chain_x(xs,Y_COVER_TOP))
    vac_chains += [
        chain_x(master_x,Y_VAC_TOP),
        chain_y(0.0,subdivide(Y_COVER_TOP,Y_VAC_TOP,0.006)),
        chain_y(X_RIGHT,subdivide(Y_COVER_TOP,Y_VAC_TOP,0.006)),
    ]
    for rect in COILS.values():
        a,b,y0,y1=rect
        xs=master_x[(master_x>=a-1e-12)&(master_x<=b+1e-12)]
        ys=subdivide(y0,y1,0.0045)
        vac_chains += [chain_y(a,ys),chain_x(xs,y1),chain_y(b,ys)]

    def vac_accept(x,y):
        if not (0 < x < X_RIGHT and Y_COVER_TOP < y < Y_VAC_TOP):
            return False
        return not any(point_in_open_rect((x,y),r) for r in COILS.values())

    vac_int=poisson_points(0,X_RIGHT,Y_COVER_TOP,Y_VAC_TOP,0.0070,rng,vac_accept)
    def keep_vac(tp):
        if not all(-1e-12 <= p[0] <= X_RIGHT+1e-12 and Y_COVER_TOP-1e-12 <= p[1] <= Y_VAC_TOP+1e-12 for p in tp):
            return False
        cx=sum(p[0] for p in tp)/3; cy=sum(p[1] for p in tp)/3
        if any(point_in_open_rect((cx,cy),r) for r in COILS.values()):
            return False
        return not any(triangle_overlaps_rect(tp,r) for r in COILS.values())
    vac_pts,vac_tri=triangulate_region(vac_chains,vac_int,keep_vac)
    add_triangulation(PHYS_VACUUM,vac_pts,vac_tri)

    for pid,rect in COILS.items():
        a,b,y0,y1=rect
        xs=master_x[(master_x>=a-1e-12)&(master_x<=b+1e-12)]
        ys=subdivide(y0,y1,0.0045)
        chains=[chain_x(xs,y0),chain_x(xs,y1),chain_y(a,ys),chain_y(b,ys)]
        ints=poisson_points(a,b,y0,y1,0.0038,rng,lambda x,y: True)
        pts,tri=triangulate_region(chains,ints,lambda tp,a=a,b=b,y0=y0,y1=y1: all(a-1e-12<=p[0]<=b+1e-12 and y0-1e-12<=p[1]<=y1+1e-12 for p in tp))
        add_triangulation(pid,pts,tri)

    ach=chain_y(0.0,subdivide(Y_COVER_IF,Y_VAC_TOP,0.006))
    for a,b in zip(ach[:-1],ach[1:]): add_line(PHYS_AXIS,a,b)
    cr=chain_y(X_RIGHT,subdivide(Y_COVER_IF,Y_COVER_TOP,0.0045))
    for a,b in zip(cr[:-1],cr[1:]): add_line(PHYS_COVER_OUTER_RIGHT,a,b)
    for a,b in ((0.0,0.0495),(0.0585,0.1125),(0.1215,0.1710),(0.1800,X_RIGHT)):
        xs=master_x[(master_x>=a-1e-12)&(master_x<=b+1e-12)]
        ch=chain_x(xs,Y_COVER_TOP)
        for p,q in zip(ch[:-1],ch[1:]): add_line(PHYS_COVER_VACUUM,p,q)
    for rect in COILS.values():
        a,b,y0,y1=rect
        xs=master_x[(master_x>=a-1e-12)&(master_x<=b+1e-12)]
        ch=chain_x(xs,y0)
        for p,q in zip(ch[:-1],ch[1:]): add_line(PHYS_COVER_COIL_GROUND,p,q)
        ys=subdivide(y0,y1,0.0045)
        for ch2 in (chain_y(a,ys),chain_x(xs,y1),chain_y(b,ys)):
            for p,q in zip(ch2[:-1],ch2[1:]): add_line(PHYS_VACUUM_COIL_GROUND,p,q)
    for ch in (chain_x(master_x,Y_VAC_TOP),chain_y(X_RIGHT,subdivide(Y_COVER_TOP,Y_VAC_TOP,0.006))):
        for p,q in zip(ch[:-1],ch[1:]): add_line(PHYS_VACUUM_OUTER_GROUND,p,q)

    names=[]
    for row in physical:
        f=row.split(maxsplit=2)
        if int(f[0])==1 and int(f[1])==PHYS_COVER_OUTER_GROUND:
            continue
        names.append(row)
    used={(int(x.split()[0]),int(x.split()[1])) for x in names}
    additions=[
        (1,PHYS_VACUUM_OUTER_GROUND,'vacuum_outer_ground'),
        (1,PHYS_COVER_VACUUM,'cover_vacuum'),
        (1,PHYS_COVER_COIL_GROUND,'cover_coil_ground'),
        (1,PHYS_VACUUM_COIL_GROUND,'vacuum_coil_ground'),
        (2,PHYS_VACUUM,'vacuum'),
        (2,PHYS_COIL1,'coil1'),(2,PHYS_COIL2,'coil2'),(2,PHYS_COIL3,'coil3'),
    ]
    for dim,pid,name in additions:
        if (dim,pid) not in used:
            names.append(f'{dim} {pid} "{name}"')

    se=sorted(new_kept+added,key=lambda e:e[0])
    def eline(e):
        eid,etype,tags,conn=e
        return " ".join(map(str,[eid,etype,len(tags),*tags,*conn]))

    out=[]
    out.extend(lines[:pi])
    out += ["$PhysicalNames",str(len(names)),*names,"$EndPhysicalNames"]
    out.extend(lines[pj+1:ni])
    sn=sorted(new_nodes.items())
    out += ["$Nodes",str(len(sn))]
    out += [f"{nid} {x:.16g} {y:.16g} {z:.16g}" for nid,(x,y,z) in sn]
    out += ["$EndNodes"]
    out.extend(lines[nj+1:ei])
    out += ["$Elements",str(len(se)),*[eline(e) for e in se],"$EndElements"]
    out.extend(lines[ej+1:])
    args.target.write_text("\n".join(out)+"\n",encoding="utf-8")

    counts={}
    for e in se:
        if e[1]==2 and e[2]: counts[e[2][0]]=counts.get(e[2][0],0)+1
    expected_fixed={PHYS_PLASMA:1826,PHYS_WAFER:146,PHYS_FOCUS_RING:36}
    for pid,n in expected_fixed.items():
        if counts.get(pid,0)!=n:
            raise RuntimeError(f"preserved block count mismatch pid={pid}: {counts.get(pid,0)} != {n}")
    for pid in (PHYS_COVER,PHYS_VACUUM,PHYS_COIL1,PHYS_COIL2,PHYS_COIL3):
        if counts.get(pid,0)<=0:
            raise RuntimeError(f"missing generated block pid={pid}")

    def nodes_on(pid,pred):
        ans=set()
        for e in se:
            if e[1]!=2 or not e[2] or e[2][0]!=pid: continue
            for n in e[3]:
                x,y,_=new_nodes[n]
                if pred(x,y): ans.add(key(x,y))
        return ans
    cover_top_nodes=nodes_on(PHYS_COVER,lambda x,y: abs(y-Y_COVER_TOP)<1e-12)
    upper=nodes_on(PHYS_VACUUM,lambda x,y: abs(y-Y_COVER_TOP)<1e-12)
    for pid in (PHYS_COIL1,PHYS_COIL2,PHYS_COIL3):
        upper |= nodes_on(pid,lambda x,y: abs(y-Y_COVER_TOP)<1e-12)
    if cover_top_nodes != upper:
        raise RuntimeError("cover upper interface is not conforming")

    print(
        "VACUUM_COILS_BLOCK_MESH_PASS "
        f"nodes={len(sn)} elements={len(se)} "
        f"cover_triangles={counts.get(PHYS_COVER,0)} "
        f"vacuum_triangles={counts.get(PHYS_VACUUM,0)} "
        f"coil1_triangles={counts.get(PHYS_COIL1,0)} "
        f"coil2_triangles={counts.get(PHYS_COIL2,0)} "
        f"coil3_triangles={counts.get(PHYS_COIL3,0)} "
        f"shared_cover_upper_nodes={len(cover_top_nodes)} "
        "vacuum_physical_blocks=1 artificial_vacuum_subregions=0"
    )


if __name__ == "__main__":
    main()
