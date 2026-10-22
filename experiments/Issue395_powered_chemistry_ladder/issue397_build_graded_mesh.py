#!/usr/bin/env python3
"""Create self-consistent Case B graded-mesh Levels 1, 2 and 3 from pre-local-2x.

Only plasma/wafer mesh is changed. Axis-centered radial coarsening has a
continuous cosine taper to original mesh density, with multilayer taper in
both plasma and wafer-solid material. Every job starts from the SAME source
mesh and emits exactly one level. Historical mesh SHA and published level
mesh SHA are independently audited.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from issue397_graded_mesh_geometry import (
    parse, physical_faces, contract, area_groups, boundary_groups, validate,
    write, min_angle, earclip,
)
from issue397_graded_mesh_quality import improve

ACCEPTED_PRE2X_SHA256="91299b6fc16136dfc9c4426148113b07ddfd7e95839da7abf5f14c36a4eac9cf"
PARAMS={
    1:dict(axis_fac=1.9,taper_r=.070,band_above=.019,band_below=.009),
    2:dict(axis_fac=2.45,taper_r=.085,band_above=.024,band_below=.009),
    3:dict(axis_fac=3.0,taper_r=.100,band_above=.030,band_below=.009),
}
EXPECTED={
    1:dict(sha256="ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc",faces=27,nodes=1739,triangles=3155,max_width_mm=8.70967742,min_local_angle_deg=14.10559),
    2:dict(sha256="8ef865275192a297f8903e9f4abc53a74cfc2b97d49647a326f1c87496f25b9f",faces=25,nodes=1728,triangles=3133,max_width_mm=8.70967742,min_local_angle_deg=14.10559),
    3:dict(sha256="a133ad1c7a56d4ee337bd54009155b17b4e994a164268230cdb9a884100e7434",faces=22,nodes=1710,triangles=3097,max_width_mm=13.06451613,min_local_angle_deg=12.77542),
}

def smooth_taper(x):
    if x>=1:return 0.
    if x<=0:return 1.
    return .5*(1+math.cos(math.pi*x))

def factor(r,z,par):
    d=abs(z-.099)
    band=par['band_above'] if z>=.099 else par['band_below']
    return 1+(par['axis_fac']-1)*smooth_taper(r/par['taper_r'])*smooth_taper(d/band)

def target_indices(nodes,vertices,par):
    idx=[0]
    last=len(vertices)-1
    while idx[-1]<last:
        i=idx[-1]
        r=nodes[vertices[i]][0]
        jump=1
        for j in [3,2]:
            if i+j>last:continue
            rm=.5*(r+nodes[vertices[i+j]][0])
            fac=factor(rm,.099,par)
            if j<=fac+.48 and j<=3:
                jump=j
                break
        idx.append(min(i+jump,last))
    return idx

def loop_from_opposite(es,v,tag):
    triangles=[c for kind,t,c in es if kind==2 and t[0]==tag and v in c]
    if len(triangles)<3:return None
    nbr=collections.defaultdict(list)
    for c in triangles:
        a,b=(x for x in c if x!=v)
        nbr[a].append(b);nbr[b].append(a)
    if any(len(vv)!=2 for vv in nbr.values()):return None
    start=min(nbr)
    cyc=[start];prev=None
    while True:
        possible=[a for a in nbr[cyc[-1]] if a!=prev]
        if not possible:return None
        follow=possible[0]
        if follow==start:break
        if follow in cyc or len(cyc)>len(nbr):return None
        prev=cyc[-1];cyc.append(follow)
    if len(cyc)!=len(nbr):return None
    return cyc

def remove_interior(nodes,el,v,pid,min_local_angle=8.):
    incident=[(k,t,c) for k,t,c in el if v in c]
    if any(k!=2 or t[0]!=pid for k,t,c in incident):return el,False
    tags={t for k,t,c in incident}
    if len(tags)!=1:return el,False
    loop=loop_from_opposite(el,v,pid)
    if loop is None:return el,False
    try:
        tris=earclip(nodes,loop)
    except (ValueError,StopIteration):
        return el,False
    if any(min_angle(nodes,c)<min_local_angle for c in tris):return el,False
    new=[(k,t,c) for k,t,c in el if v not in c]
    new.extend((2,next(iter(tags)),c) for c in tris)
    return new,True

def multi_layer_thin(nodes,elems,par):
    bnode={n for k,t,c in elems if k==1 for n in c}
    owner=collections.defaultdict(set)
    for k,t,c in elems:
        if k==2:
            for v in c:owner[v].add(t[0])
    candidates=[]
    for v,pids in owner.items():
        if v in bnode or len(pids)!=1 or next(iter(pids)) not in (10,21):continue
        r,z=nodes[v][:2]
        f=factor(r,z,par)
        if f<1.20:continue
        digest=int(hashlib.sha256(f'{v}:issue397'.encode()).hexdigest()[:10],16)/0xffffffffff
        threshold=max(0.,1-1/f**2)
        if digest<threshold:
            candidates.append((round(r,8),round(abs(z-.099),8),v,next(iter(pids)),f))
    candidates.sort(key=lambda x:(x[0]+2*x[1],x[1],x[2]))
    deleted=[]
    el=elems
    for r,dz,v,pid,f in candidates:
        oldinc=[c for k,t,c in el if k==2 and t[0]==pid and v in c]
        if len(oldinc)<3:continue
        others=set(w for c in oldinc for w in c if w!=v)
        if not others:continue
        dist=[math.dist(nodes[v][:2],nodes[w][:2]) for w in others]
        if min(dist)>0.008*f/2.:continue
        res,ok=remove_interior(nodes,el,v,pid,min_local_angle=11.)
        if ok:
            el=res;deleted.append((v,r,dz,pid,f))
    return el,deleted,len(candidates)

def local_quality(nodes,el,par):
    region=[]
    for k,t,c in el:
        if k!=2 or t[0] not in (10,21):continue
        r=sum(nodes[v][0] for v in c)/3
        z=sum(nodes[v][1] for v in c)/3
        if r<par['taper_r'] and abs(z-.099)<(.01 if z<.099 else par['band_above']):
            region.append(min_angle(nodes,c))
    return dict(min_angle_deg=float(min(region)),p05_angle_deg=float(np.percentile(region,5)),count=len(region))

def run(source_path:Path,target_path:Path,level:int)->dict:
    sha=hashlib.sha256(source_path.read_bytes()).hexdigest()
    if sha!=ACCEPTED_PRE2X_SHA256:
        raise RuntimeError(f"Pre-2x mesh provenance mismatch: {sha}; expected {ACCEPTED_PRE2X_SHA256}")
    source,nodes,baseline=parse(source_path)
    phys={t[0] for k,t,c in baseline}
    areas=area_groups(nodes,baseline)
    perimeter=boundary_groups(nodes,baseline)
    original=validate(nodes,baseline,phys,areas,perimeter,31)
    if original['nodes']!=1762 or original['triangles']!=3201:
        raise RuntimeError(f"Unexpected pre-local2x mesh: {original}")
    par=PARAMS[level]
    el=list(baseline)
    _,vertices=physical_faces(nodes,baseline)
    indices=target_indices(nodes,vertices,par)
    selected={vertices[i] for i in indices}
    removed=[v for v in vertices[1:-1] if v not in selected]
    for v in removed:
        el=contract(nodes,el,v)
    el,deleted,numc=multi_layer_thin(nodes,el,par)
    el=improve(nodes,el,max_pass=15)
    result=validate(nodes,el,phys,areas,perimeter,len(indices)-1)
    widths=result["wafer_widths_mm"]
    if max(widths)>13.06451615 or widths[-1]>4.35483872:
        raise RuntimeError(f"Level {level}: excessive wafer face/abrupt taper")
    quality=local_quality(nodes,el,par)
    if quality['min_angle_deg']<11.0:
        raise RuntimeError(f"Level {level}: excessive skinny modified cells {quality}")
    target_path.parent.mkdir(parents=True,exist_ok=True)
    write(target_path,source,nodes,el)
    _,rnodes,relems=parse(target_path)
    audit=validate(rnodes,relems,phys,areas,perimeter,len(indices)-1)
    if result['triangles']!=audit['triangles'] or result['nodes']!=audit['nodes']:
        raise RuntimeError("Gmsh roundtrip mismatch")
    digest=hashlib.sha256(target_path.read_bytes()).hexdigest()
    expected=EXPECTED[level]
    if (digest!=expected['sha256'] or result['wafer_faces']!=expected['faces']
        or result['nodes']!=expected['nodes'] or result['triangles']!=expected['triangles']
        or abs(max(widths)-expected['max_width_mm'])>1e-5
        or quality['min_angle_deg']+1e-4<expected['min_local_angle_deg']):
        raise RuntimeError(f"Published mesh mismatch level={level} sha={digest} result={result} quality={quality}")
    summary={
      "status":"ISSUE397_GRADED_COARSE_MESH_PASS","level":level,
      "source_sha256":sha,"generated_sha256":digest,
      "wafer_faces":result['wafer_faces'],"nodes":result['nodes'],
      "triangles":result['triangles'],"modified_region_min_angle_deg":quality['min_angle_deg'],
      "max_wafer_width_mm":max(widths),"plasma_depth_mm":par['band_above']*1e3,
      "wafer_depth_mm":par['band_below']*1e3,"radius_taper_mm":par['taper_r']*1e3,
      "interior_removed_nodes":len(deleted),
    }
    return summary

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("source",type=Path)
    ap.add_argument("target",type=Path)
    ap.add_argument("--level",type=int,choices=(1,2,3),required=True)
    args=ap.parse_args()
    info=run(args.source,args.target,args.level)
    print(info["status"],"level="+str(args.level))
    print(json.dumps(info,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
