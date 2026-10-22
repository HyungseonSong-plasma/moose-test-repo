#!/usr/bin/env python3
"""Quality-preserving interior diagonal flips for the radial graded mesh."""
from __future__ import annotations
from collections import defaultdict
import math

def improve(nodes, el, max_pass=15):
    fixed={tuple(sorted(c)) for k,t,c in el if k==1}
    all_el=list(el)
    def area(c):
        a,b,c=[nodes[v] for v in c]
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def angle(c):
        pts=[nodes[v] for v in c];a=[]
        for j in range(3):
            x,y,z=pts[j],pts[(j+1)%3],pts[(j+2)%3]
            e=(y[0]-x[0],y[1]-x[1]);f=(z[0]-x[0],z[1]-x[1])
            m=math.hypot(*e)*math.hypot(*f)
            a.append(math.degrees(math.acos(max(-1,min(1,(e[0]*f[0]+e[1]*f[1])/m)))))
        return min(a)
    def orient(c):
        if area(c)<0:return (c[0],c[2],c[1])
        return c
    for iteration in range(max_pass):
        edge_tris=defaultdict(list)
        for j,(k,t,c) in enumerate(all_el):
            if k==2:
                for i in range(3):
                    edge_tris[tuple(sorted((c[i],c[(i+1)%3])))].append(j)
        score=[]
        for e,adj in edge_tris.items():
            if len(adj)!=2 or e in fixed:continue
            k1,k2=adj;_,t1,c1=all_el[k1];_,t2,c2=all_el[k2]
            if t1!=t2:continue
            w1=next(x for x in c1 if x not in e);w2=next(x for x in c2 if x not in e)
            if w1==w2 or tuple(sorted((w1,w2))) in edge_tris:continue
            a,b=e
            def side(u,v,w):
                A=nodes[u];B=nodes[v];C=nodes[w]
                return (B[0]-A[0])*(C[1]-A[1])-(B[1]-A[1])*(C[0]-A[0])
            if side(a,b,w1)*side(a,b,w2)>=-1e-14 or side(w1,w2,a)*side(w1,w2,b)>=-1e-14:continue
            new1=orient((w1,w2,a));new2=orient((w2,w1,b))
            if area(new1)<1e-13 or area(new2)<1e-13:continue
            oldmin=min(angle(c1),angle(c2));newmin=min(angle(new1),angle(new2))
            if newmin>oldmin+1e-4:
                score.append((newmin-oldmin,k1,k2,new1,new2))
        if not score:break
        changed=set();flips=0
        for gain,k1,k2,c1,c2 in sorted(score,reverse=True):
            if k1 in changed or k2 in changed:continue
            all_el[k1]=(2,all_el[k1][1],c1);all_el[k2]=(2,all_el[k2][1],c2)
            changed.update((k1,k2));flips+=1
        print('quality_flip_pass',iteration,'flips',flips)
        if not flips:break
    return all_el
