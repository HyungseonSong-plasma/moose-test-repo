#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def replace_once(text, old, new, label):
    n=text.count(old)
    if n!=1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old,new,1)


def block(text,name):
    h=f"  [{name}]\n"
    s=text.index(h)
    e=text.index("\n  []",s)+len("\n  []")
    return text[s:e]


def replace_in_block(text,name,old,new):
    cur=block(text,name)
    if old not in cur:
        raise RuntimeError(f"{name}: token not present: {old!r}")
    return replace_once(text,cur,cur.replace(old,new,1),name)


def append_after_block(text,name,addition):
    cur=block(text,name)
    return replace_once(text,cur,cur+"\n"+addition,f"append after {name}")


def update_boundary(text,name,remove=(),add=()):
    cur=block(text,name)
    m=re.search(r"(?m)^(\s*boundary\s*=\s*')([^']*)(')\s*$",cur)
    if not m:
        raise RuntimeError(f"{name}: single-quoted boundary list not found")
    tokens=m.group(2).split()
    for tok in remove:
        if tok not in tokens:
            raise RuntimeError(f"{name}: boundary {tok!r} not present")
        tokens.remove(tok)
    for tok in add:
        if tok in tokens:
            raise RuntimeError(f"{name}: boundary {tok!r} already present")
        tokens.append(tok)
    repl=m.group(1)+" ".join(tokens)+m.group(3)
    upd=cur[:m.start()]+repl+cur[m.end():]
    return replace_once(text,cur,upd,f"boundary routing {name}")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("input",type=Path)
    args=ap.parse_args()
    text=args.input.read_text(encoding="utf-8")

    for name in ("potential","phi_diffusion"):
        text=replace_in_block(
            text,name,
            "block = 'plasma cover wafer focus_ring'",
            "block = 'plasma cover wafer focus_ring vacuum'",
        )

    eps_vac="""  [eps_vacuum]
    type = ADGenericConstantMaterial
    prop_names = 'relative_permittivity'
    prop_values = '1.0'
    block = vacuum
  []"""
    text=append_after_block(text,"eps_focus_ring",eps_vac)

    text=update_boundary(
        text,"grounded_potential",
        remove=("cover_outer_ground",),
        add=("vacuum_outer_ground","cover_coil_ground","vacuum_coil_ground"),
    )

    ground_pp = """  [vacuum_outer_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = vacuum_outer_ground
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [cover_coil_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = cover_coil_ground
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [vacuum_coil_ground_potential]
    type = SideAverageValue
    variable = potential
    boundary = vacuum_coil_ground
    execute_on = 'INITIAL TIMESTEP_END'
  []"""
    text=append_after_block(text,"focus_ring_ground_potential",ground_pp)

    pot=block(text,"potential")
    phi=block(text,"phi_diffusion")
    gnd=block(text,"grounded_potential")
    if "block = 'plasma cover wafer focus_ring vacuum'" not in pot:
        raise RuntimeError("potential does not span vacuum")
    if "block = 'plasma cover wafer focus_ring vacuum'" not in phi:
        raise RuntimeError("phi_diffusion does not span vacuum")
    if "prop_values = '1.0'" not in block(text,"eps_vacuum"):
        raise RuntimeError("vacuum relative permittivity is not 1.0")
    for token in ("vacuum_outer_ground","cover_coil_ground","vacuum_coil_ground","cover_outer_right"):
        if token not in gnd:
            raise RuntimeError(f"missing grounded potential boundary: {token}")
    if "cover_outer_ground" in gnd:
        raise RuntimeError("obsolete cover_outer_ground still routed as ground")
    if "coil1" in pot or "coil2" in pot or "coil3" in pot:
        raise RuntimeError("coil solid blocks must not carry the electrostatic unknown")

    args.input.write_text(text,encoding="utf-8")
    print(
        "VACUUM_COILS_15US_PROMOTION_PASS "
        "vacuum_block=true vacuum_eps_r=1.0 "
        "vacuum_outer_ground_V=0 coil_ground_V=0 "
        "cover_vacuum_continuity=conforming_shared_nodes "
        "coils_electrostatic_unknown=false"
    )

if __name__=="__main__":
    main()
