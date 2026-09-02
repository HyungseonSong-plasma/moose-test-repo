#!/usr/bin/env python3
from pathlib import Path
from collections import defaultdict
import hashlib, re, sys

HERE=Path(__file__).resolve().parent
QVT=HERE/"qvt.msh"
MESH_I=HERE/"mesh.i"
EXPECTED_QVT="a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
EXPECTED_MESH_I="b31a8cbc41fd8eea60b6bc036b6a5841342c065152a91416063ff5afbec9137d"

def evaluate(qvt_bytes, mesh_text, enforce_identity=True):
    if enforce_identity:
        if hashlib.sha256(qvt_bytes).hexdigest()!=EXPECTED_QVT:
            return False, "qvt.msh SHA mismatch"
        if hashlib.sha256(mesh_text.encode()).hexdigest()!=EXPECTED_MESH_I:
            return False, "mesh.i SHA mismatch"
    try:
        lines=qvt_bytes.decode("utf-8").splitlines()
    except Exception:
        return False, "unexpected non-ASCII mesh"

    def sec(name):
        try:
            i=lines.index(f"${name}")
        except ValueError:
            raise RuntimeError(f"missing ${name}")
        out=[]
        for x in lines[i+1:]:
            if x.strip()==f"$End{name}":
                return out
            out.append(x.rstrip())
        raise RuntimeError(f"unterminated ${name}")

    try:
        fmt=sec("MeshFormat")[0].split()
        if fmt[:2]!=["4.1","0"]:
            return False, f"unexpected mesh format {fmt}"

        phys={}
        s=sec("PhysicalNames")
        n=int(s[0])
        for ln in s[1:1+n]:
            p=ln.split(maxsplit=2)
            phys[(int(p[0]),int(p[1]))]=p[2].strip().strip('"')

        ent=sec("Entities")
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

        curve_to_surfs=defaultdict(set)
        for (dim,stag),v in entities.items():
            if dim==2 and stag in surface_name:
                for c in v["bounds"]:
                    curve_to_surfs[abs(c)].add(surface_name[stag])

        pairs=set()
        for names in curve_to_surfs.values():
            ns=sorted(names)
            for i in range(len(ns)):
                for j in range(i+1,len(ns)):
                    pairs.add((ns[i],ns[j]))

        gens=[]
        cur=None
        for line in mesh_text.splitlines():
            s=line.strip()
            m=re.match(r'^\[([A-Za-z0-9_]+)\]$',s)
            if m and m.group(1) not in ("Mesh","Materials"):
                cur={"name":m.group(1)}
                gens.append(cur)
                continue
            if s=="[]":
                cur=None
                continue
            if cur is not None:
                for k in ("type","primary_block","paired_block","new_boundary","input"):
                    mm=re.match(rf'^{k}\s*=\s*(.+)$',s)
                    if mm:
                        val=mm.group(1).strip()
                        val=val.strip("'")
                        val=val.strip('"')
                        cur[k]=val

        gens=[g for g in gens if g.get("type")=="SideSetsBetweenSubdomainsGenerator"]
        if len(gens)!=19:
            return False, f"expected 19 generators, got {len(gens)}"

        expected_input="main"
        expanded=0
        for g in gens:
            if g.get("input")!=expected_input:
                return False, f"generator chain break at {g['name']}"
            expected_input=g["name"]
            for b in g["paired_block"].split():
                expanded+=1
                key=tuple(sorted((g["primary_block"],b)))
                if key not in pairs:
                    return False, f"missing actual adjacency {key}"

        if expanded!=24:
            return False, f"expected 24 expanded block pairs, got {expanded}"
        return True, "PASS"
    except Exception as e:
        return False, str(e)


def validate_kernel_coverage(mesh_bytes, physics_text):
    """
    Reproduce the exact MOOSE construction invariant that failed in EVR #1:
    every top-dimensional subdomain must have at least one active Kernel.
    For this validation harness, a Kernel without `block` is global.
    """
    lines = mesh_bytes.decode("utf-8").splitlines()

    def sec(name):
        try:
            i = lines.index(f"${name}")
        except ValueError:
            raise RuntimeError(f"missing ${name}")
        out = []
        for x in lines[i+1:]:
            if x.strip() == f"$End{name}":
                return out
            out.append(x.rstrip())
        raise RuntimeError(f"unterminated ${name}")

    phys = {}
    s = sec("PhysicalNames")
    n = int(s[0])
    for ln in s[1:1+n]:
        p = ln.split(maxsplit=2)
        phys[(int(p[0]), int(p[1]))] = p[2].strip().strip('"')
    subdomains = sorted(name for (dim, _), name in phys.items() if dim == 2)

    # Parse nested [Kernels] objects conservatively.
    in_kernels = False
    current = None
    kernels = []
    for raw in physics_text.splitlines():
        s = raw.strip()
        if s == "[Kernels]":
            in_kernels = True
            continue
        if in_kernels and s == "[]":
            if current is None:
                in_kernels = False
            else:
                kernels.append(current)
                current = None
            continue
        if not in_kernels:
            continue
        m = re.match(r"^\[([A-Za-z0-9_]+)\]$", s)
        if m:
            current = {"name": m.group(1)}
            continue
        if current is not None:
            m = re.match(r"^block\s*=\s*(.+)$", s)
            if m:
                v = m.group(1).strip().strip("'").strip('"')
                current["block"] = v.split()

    if not kernels:
        return False, "no active Kernel objects parsed"

    covered = set()
    global_kernel = False
    for k in kernels:
        if "block" not in k:
            global_kernel = True
            covered.update(subdomains)
        else:
            covered.update(k["block"])

    missing = sorted(set(subdomains) - covered)
    if missing:
        return False, "subdomains without active Kernel: " + " ".join(missing)

    # This bundle's dummy variable must also be global if its Reaction Kernel is global.
    in_variables = False
    current = None
    dummy_block = None
    for raw in physics_text.splitlines():
        s = raw.strip()
        if s == "[Variables]":
            in_variables = True
            continue
        if in_variables and s == "[]":
            if current is None:
                in_variables = False
            else:
                current = None
            continue
        if not in_variables:
            continue
        m = re.match(r"^\[([A-Za-z0-9_]+)\]$", s)
        if m:
            current = m.group(1)
            continue
        if current == "dummy":
            m = re.match(r"^block\s*=\s*(.+)$", s)
            if m:
                dummy_block = m.group(1).strip()

    if global_kernel and dummy_block is not None:
        return False, "dummy variable is block-restricted while dummy kernel is global"

    return True, f"all {len(subdomains)} top-dimensional subdomains have active Kernel coverage"

ok,msg=evaluate(QVT.read_bytes(),MESH_I.read_text(),True)
if not ok:
    raise SystemExit(f"R18_STATIC_CONTRACT: FAIL {msg}")

# P0 mutations: identity changes must be rejected.
mut=MESH_I.read_text().replace("primary_block = plasma","primary_block = plasma_BAD",1)
ok,_=evaluate(QVT.read_bytes(),mut,True)
if ok:
    raise SystemExit("R18_STATIC_MUTATION_SELFTEST: FAIL mesh.i mutation escaped")

bad=bytearray(QVT.read_bytes())
bad[-2] ^= 1
ok,_=evaluate(bytes(bad),MESH_I.read_text(),True)
if ok:
    raise SystemExit("R18_STATIC_MUTATION_SELFTEST: FAIL qvt.msh mutation escaped")


PHYSICS = HERE/"physics.i"
ok,msg = validate_kernel_coverage(QVT.read_bytes(), PHYSICS.read_text())
if not ok:
    raise SystemExit(f"R18_KERNEL_COVERAGE: FAIL {msg}")

# Mutation reproduces EVR #1 harness bug: restrict the only dummy Kernel to plasma.
mut_phys = PHYSICS.read_text().replace(
    "    variable = dummy\n  []",
    "    variable = dummy\n    block = plasma\n  []",
    1,
)
ok_mut,_ = validate_kernel_coverage(QVT.read_bytes(), mut_phys)
if ok_mut:
    raise SystemExit("R18_KERNEL_COVERAGE_MUTATION_SELFTEST: FAIL restricted-kernel mutation escaped")

print("R18_KERNEL_COVERAGE: PASS")
print("R18_KERNEL_COVERAGE_MUTATION_SELFTEST: PASS")

print("R18_STATIC_CONTRACT: PASS")
print("R18_STATIC_MUTATION_SELFTEST: PASS")
print("SIDESET_GENERATORS=19")
print("EXPANDED_BLOCK_PAIR_CHECKS=24")
