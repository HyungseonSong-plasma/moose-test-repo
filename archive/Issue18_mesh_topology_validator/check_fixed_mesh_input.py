#!/usr/bin/env python3
from pathlib import Path
from collections import defaultdict
import hashlib, re, sys

HERE=Path(__file__).resolve().parent
MESH=HERE/"qvt.msh"
INPUT=HERE/"mesh.i"

EXPECTED_MESH_SHA="a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
EXPECTED_INPUT_SHA="b31a8cbc41fd8eea60b6bc036b6a5841342c065152a91416063ff5afbec9137d"

def fail(msg):
    print("R18_FIXED_MESH_INPUT_FAIL:", msg, file=sys.stderr)
    raise SystemExit(2)

if hashlib.sha256(MESH.read_bytes()).hexdigest()!=EXPECTED_MESH_SHA:
    fail("qvt.msh SHA changed")
if hashlib.sha256(INPUT.read_bytes()).hexdigest()!=EXPECTED_INPUT_SHA:
    fail("mesh.i SHA changed")

# Parse declared SideSetsBetweenSubdomainsGenerator contracts from fixed input.
txt=INPUT.read_text()
gens=[]
current=None
for line in txt.splitlines():
    s=line.strip()
    m=re.match(r'^\[([A-Za-z0-9_]+)\]$',s)
    if m and m.group(1) not in ("Mesh","Materials"):
        current={"name":m.group(1)}
        gens.append(current)
        continue
    if s=="[]":
        current=None
        continue
    if current is not None:
        for key in ("type","primary_block","paired_block","new_boundary","input"):
            mm=re.match(rf'^{key}\s*=\s*(.+)$',s)
            if mm:
                current[key]=mm.group(1).strip().strip("'\"")

gens=[g for g in gens if g.get("type")=="SideSetsBetweenSubdomainsGenerator"]
if len(gens)!=19:
    fail(f"expected 19 SideSetsBetweenSubdomainsGenerator objects, got {len(gens)}")

# Parse Gmsh 4.1 ASCII surface adjacency.
lines=MESH.read_text().splitlines()
def section(name):
    try: i=lines.index(f"${name}")
    except ValueError: fail(f"missing ${name}")
    out=[]
    for x in lines[i+1:]:
        if x.strip()==f"$End{name}":
            return out
        out.append(x.rstrip())
    fail(f"unterminated ${name}")

fmt=section("MeshFormat")[0].split()
if fmt[:2] != ["4.1","0"]:
    fail(f"unexpected mesh format: {' '.join(fmt)}")

phys={}
s=section("PhysicalNames")
n=int(s[0])
for ln in s[1:1+n]:
    p=ln.split(maxsplit=2)
    dim,tag=int(p[0]),int(p[1])
    name=p[2].strip().strip('"')
    phys[(dim,tag)]=name

ent=section("Entities")
npts,ncur,nsurf,nvol=map(int,ent[0].split())
idx=1
entities={}
for dim,count in enumerate([npts,ncur,nsurf,nvol]):
    for _ in range(count):
        a=ent[idx].split(); idx+=1
        tag=int(a[0])
        off=4 if dim==0 else 7
        nphys=int(a[off])
        ptags=list(map(int,a[off+1:off+1+nphys]))
        pos=off+1+nphys
        bounds=[]
        if dim>0:
            nb=int(a[pos])
            bounds=list(map(int,a[pos+1:pos+1+nb]))
        entities[(dim,tag)]={"phys":ptags,"bounds":bounds}

surface_name={}
for (dim,tag),v in entities.items():
    if dim==2:
        names=[phys[(2,p)] for p in v["phys"] if (2,p) in phys]
        if len(names)==1:
            surface_name[tag]=names[0]

curve_to_surfaces=defaultdict(set)
for (dim,stag),v in entities.items():
    if dim==2:
        for c in v["bounds"]:
            if stag in surface_name:
                curve_to_surfaces[abs(c)].add(surface_name[stag])

pair_curves=defaultdict(list)
for c,names in curve_to_surfaces.items():
    ns=sorted(names)
    for i in range(len(ns)):
        for j in range(i+1,len(ns)):
            pair_curves[(ns[i],ns[j])].append(c)

checks=[]
for g in gens:
    primary=g["primary_block"]
    for paired in g["paired_block"].split():
        key=tuple(sorted((primary,paired)))
        curves=sorted(pair_curves.get(key,[]))
        if not curves:
            fail(f"no actual mesh interface for {g['name']}: {primary}<->{paired}")
        checks.append((g["name"],primary,paired,curves))

if len(checks)!=24:
    fail(f"expected 24 expanded adjacency checks, got {len(checks)}")

# Verify generator chain remains deterministic.
expected_input="main"
for g in gens:
    if g.get("input") != expected_input:
        fail(f"generator chain break at {g['name']}: input={g.get('input')} expected={expected_input}")
    expected_input=g["name"]

print("R18_FIXED_MESH_INPUT")
print(f"QVT_MSH_SHA256={EXPECTED_MESH_SHA}")
print(f"MESH_I_SHA256={EXPECTED_INPUT_SHA}")
print("MESH_FORMAT=Gmsh 4.1 ASCII")
print("SIDESET_GENERATORS=19")
print("EXPANDED_BLOCK_PAIR_CHECKS=24")
for name,a,b,curves in checks:
    print(f"  {name}: {a}<->{b} curves={curves}")
print("GENERATOR_CHAIN=PASS")
print("BLOCK_PAIR_ADJACENCY=24/24 PASS")
print("R18_FIXED_MESH_INPUT: PASS")
