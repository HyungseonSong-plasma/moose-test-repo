#!/usr/bin/env python3
"""Conforming multiregion Gmsh v2 geometry operators for Issue #397 graded coarsening."""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import math

WAFER=8
PLASMA,WAFER_SOLID=10,21
TOL=1e-11
AREATOL=1e-14

def parse(path):
    lines=Path(path).read_text(encoding='utf8').splitlines()
    a=lines.index('$Nodes');b=lines.index('$Elements')
    nodes={}
    for l in lines[a+2:a+2+int(lines[a+1])]:
        x=l.split();nodes[int(x[0])]=tuple(map(float,x[1:4]))
    el=[]
    for l in lines[b+2:b+2+int(lines[b+1])]:
        x=list(map(int,l.split()));el.append((x[1],tuple(x[3:3+x[2]]),tuple(x[3+x[2]:])))
    return lines,nodes,el

def edge(a,b):return (a,b) if a<b else (b,a)
def xy(nodes,v):return nodes[v][:2]
def cross(a,b,c,nodes):
    x,y=xy(nodes,a),xy(nodes,b);z=xy(nodes,c)
    return (y[0]-x[0])*(z[1]-x[1])-(y[1]-x[1])*(z[0]-x[0])
def tarea(nodes,c):return .5*cross(*c,nodes)
def length(nodes,c):
    a,b=xy(nodes,c[0]),xy(nodes,c[1]);return math.hypot(a[0]-b[0],a[1]-b[1])
def min_angle(nodes,conn):
    ps=[xy(nodes,x) for x in conn]
    ang=[]
    for i in range(3):
        x,y,z=ps[i],ps[(i+1)%3],ps[(i+2)%3]
        vx=(y[0]-x[0],y[1]-x[1]);wx=(z[0]-x[0],z[1]-x[1]);ll=math.hypot(*vx)*math.hypot(*wx)
        if ll<1e-18:return 0
        co=(vx[0]*wx[0]+vx[1]*wx[1])/ll
        ang.append(math.degrees(math.acos(min(1,max(-1,co)))))
    return min(ang)

def physical_faces(nodes,el):
    faces=[]
    for k,t,c in el:
        if k==1 and t[0]==WAFER:
            if any(abs(nodes[n][1]-0.099)>1e-9 for n in c):raise ValueError('wafer not at 99mm')
            faces.append((min(nodes[n][0] for n in c),max(nodes[n][0] for n in c),c))
    faces.sort()
    if abs(faces[0][0])>TOL or abs(faces[-1][1]-.135)>TOL:raise ValueError('wafer extent')
    if any(abs(p[1]-q[0])>TOL for p,q in zip(faces,faces[1:])):raise ValueError('wafer gap')
    vert=[next(n for n in c if abs(nodes[n][0]-lo)<TOL) for lo,hi,c in faces]
    vert.append(next(n for n in faces[-1][2] if abs(nodes[n][0]-faces[-1][1])<TOL))
    return faces,vert

def area_groups(nodes,elems):
    sums=defaultdict(float)
    for k,t,c in elems:
        if k==2:sums[t[0]]+=abs(tarea(nodes,c))
    return sums

def boundary_groups(nodes,elems):
    sums=defaultdict(float)
    for k,t,c in elems:
        if k==1:sums[t[0]]+=length(nodes,c)
    return sums

def chain_from_opposite(es,v,tag):
    opp=[]
    for k,t,c in es:
        if k==2 and t[0]==tag and v in c:
            opp.append(tuple(x for x in c if x!=v))
    if not opp:raise ValueError('empty incident triangle star')
    nbr=defaultdict(list)
    for a,b in opp:
        nbr[a].append(b);nbr[b].append(a)
    ends=[x for x,neighbors in nbr.items() if len(neighbors)==1]
    if len(ends)!=2 or any(len(n)!=2 for x,n in nbr.items() if x not in ends):
        raise ValueError(f'non simple star: {tag} degs {dict(nbr)}')
    path=[ends[0]]
    while path[-1]!=ends[1]:
        nexts=[x for x in nbr[path[-1]] if len(path)<2 or x!=path[-2]]
        if len(nexts)!=1 or nexts[0] in path:raise ValueError('star loop')
        path.append(nexts[0])
    if len(path)!=len(nbr):raise ValueError('star not one path')
    return path

def point_in_triangle(nodes,p,a,b,c):
    cp=[cross(a,b,p,nodes),cross(b,c,p,nodes),cross(c,a,p,nodes)]
    return min(cp)>=-5e-15

def earclip(nodes,path):
    path=path[:]
    if len(path)<3:raise ValueError('short cavity')
    poly_area=sum(nodes[path[i]][0]*nodes[path[(i+1)%len(path)]][1]-nodes[path[(i+1)%len(path)]][0]*nodes[path[i]][1] for i in range(len(path)))/2
    if abs(poly_area)<AREATOL:raise ValueError('collapsed cavity')
    if poly_area<0:path.reverse()
    result=[]
    while len(path)>3:
        eligible=[]
        for i in range(len(path)):
            a,b,c=path[(i-1)%len(path)],path[i],path[(i+1)%len(path)]
            if cross(a,b,c,nodes)<1e-13:continue
            if any(point_in_triangle(nodes,p,a,b,c) for p in path if p not in (a,b,c)):continue
            eligible.append((min_angle(nodes,(a,b,c)),i,(a,b,c)))
        if not eligible:raise ValueError(f'no valid ear in path {path}')
        eligible.sort(reverse=True)
        _,i,tri=eligible[0]
        result.append(tri);path.pop(i)
    if tarea(nodes,path)<AREATOL:raise ValueError('bad final triangle')
    result.append(tuple(path))
    if not math.isclose(sum(tarea(nodes,c) for c in result),abs(poly_area),rel_tol=1e-8,abs_tol=2e-13):raise ValueError('triangulation lost area')
    return result

def contract(nodes,elems,v):
    faces,verts=physical_faces(nodes,elems)
    if v not in verts[1:-1]:raise ValueError('non interior wafer vertex')
    k=verts.index(v);l,r=verts[k-1:k+2:2]
    result=[];changed={}
    for tag in [PLASMA,WAFER_SOLID]:
        chain=chain_from_opposite(elems,v,tag)
        if {chain[0],chain[-1]}!={l,r}:raise ValueError('incorrect fan end vertices')
        oldtags={t for kind,t,c in elems if kind==2 and t[0]==tag and v in c}
        if len(oldtags)!=1:raise ValueError('mixed child tags')
        changed[tag]=(next(iter(oldtags)),earclip(nodes,chain))
    wafer_tags={t for kind,t,c in elems if kind==1 and t[0]==WAFER and v in c}
    if len(wafer_tags)!=1:raise ValueError('mixed wafer tags')
    removed_lines=0
    for kind,t,c in elems:
        if v not in c:result.append((kind,t,c))
        elif kind==1 and t[0]==WAFER:removed_lines+=1
        elif kind==2 and t[0] in changed:pass
        else:raise ValueError(f'Unexpected boundary/2d owner at wafer v={v}, type={kind}, tags={t}')
    if removed_lines!=2:raise ValueError(f'expect two adjacent wafer lines, got {removed_lines}')
    result.append((1,next(iter(wafer_tags)),(l,r)))
    for tag,(tags,tris) in changed.items():
        result.extend((2,tags,c) for c in tris)
    return result

def validate(nodes,el,physical,base_group_area,base_group_perimeter,expected_faces,thorough=True):
    faces,_=physical_faces(nodes,el)
    if len(faces)!=expected_faces:raise AssertionError(f'wafer faces {len(faces)} != {expected_faces}')
    used=set(x for _,_,c in el for x in c)
    if not used.issubset(nodes):raise ValueError('bad connectivity')
    if any(len(set(c))!=len(c) for k,t,c in el):raise ValueError('degenerate element topology')
    if any(tarea(nodes,c)<=AREATOL for k,t,c in el if k==2):raise ValueError('inverted or tiny triangle')
    if {t[0] for k,t,c in el}!=physical:raise ValueError('physical IDs changed')
    if thorough:
        triedges=Counter(edge(c[i],c[(i+1)%3]) for k,t,c in el if k==2 for i in range(3))
        if max(triedges.values())>2:raise ValueError('nonmanifold edge')
        boundaries=Counter(edge(*c) for k,t,c in el if k==1)
        if max(boundaries.values())>1:raise ValueError('repeated 1d boundary')
        missing=[(t[0],c) for k,t,c in el if k==1 and edge(*c) not in triedges]
        if any(pid!=1 for pid,c in missing):raise ValueError(f'boundary hanging/orphan (non-axis): {missing[:5]}')
        for got,ref in [(area_groups(nodes,el),base_group_area),(boundary_groups(nodes,el),base_group_perimeter)]:
            for group in ref:
                if not math.isclose(got[group],ref[group],abs_tol=1e-10,rel_tol=1e-8):
                    raise ValueError(f'group {group} quantity changed {got[group]} vs {ref[group]}')
    return dict(nodes=len(used),triangles=sum(k==2 for k,t,c in el),all_elements=len(el),
                wafer_faces=len(faces),wafer_widths_mm=[round((hi-lo)*1e3,8) for lo,hi,_ in faces],
                min_angle_deg=min(min_angle(nodes,c) for k,t,c in el if k==2),
                plasma_triangles=sum(k==2 and t[0]==10 for k,t,c in el))

def plasma_wafer_interface_ownership(el):
    """Audit both material neighbours AND deterministic Gmsh first-side ownership.

    The production lower-D wafer surface is generated on the PLASMA-owned
    interface sideset. Gmsh file-mesh physical 1-D line association must also
    resolve to the plasma side so that sigma_wafer lives on every plasma_wafer
    boundary face; geometry-only interface conformity does not ensure this.
    """
    edge_owners=defaultdict(list)
    for idx,(kind,tags,conn) in enumerate(el):
        if kind!=2:continue
        for i in range(3):
            e=tuple(sorted((conn[i],conn[(i+1)%3])))
            edge_owners[e].append((idx,tags[0]))
    wafer=[tuple(sorted(conn)) for kind,tags,conn in el if kind==1 and tags[0]==WAFER]
    wrong=[]
    for e in wafer:
        owners=edge_owners[e]
        ids=Counter(tag for _,tag in owners)
        if ids!=Counter((PLASMA,WAFER_SOLID)):
            raise ValueError(f"Nonconforming plasma/wafer side at {e}: {owners}")
        if min(owners)[1]!=PLASMA:
            wrong.append((e,owners))
    if wrong:
        raise ValueError(f"Gmsh wafer boundary ownership is not plasma-sided on "
                         f"{len(wrong)} of {len(wafer)} faces: {wrong[:4]}")
    return len(wafer)


def write(path,source,nodes,el):
    # All original physical lines first; plasma triangles precede every
    # adjacent wafer-solid triangle. Without this, contracted interface edges
    # can be assigned to the wafer side by libMesh's Gmsh sideset importer,
    # while LowerDBlockFromSidesetGenerator makes sigma_wafer on the plasma side.
    # This was the cause of the three initialSetup boundary-integrity failures.
    ordered=([item for item in el if item[0]==1] +
             [item for item in el if item[0]==2 and item[1][0]==PLASMA] +
             [item for item in el if item[0]==2 and item[1][0]!=PLASMA])
    if len(ordered)!=len(el):
        raise RuntimeError("Unexpected Gmsh element type during canonicalization")
    plasma_wafer_interface_ownership(ordered)
    use=sorted({n for _,_,c in ordered for n in c});idmap={n:k+1 for k,n in enumerate(use)}
    a=source.index('$Nodes');end=source.index('$EndElements')
    lines=source[:a]+['$Nodes',str(len(use))]
    lines += [f'{idmap[n]} {nodes[n][0]:.17g} {nodes[n][1]:.17g} {nodes[n][2]:.17g}' for n in use]
    lines+=['$EndNodes','$Elements',str(len(ordered))]
    for i,(kind,tags,conn) in enumerate(ordered,1):
        lines.append(' '.join(map(str,(i,kind,len(tags),*tags,*[idmap[n] for n in conn]))))
    lines+=['$EndElements']+source[end+1:]
    Path(path).write_text('\n'.join(lines)+'\n',encoding='utf8')
