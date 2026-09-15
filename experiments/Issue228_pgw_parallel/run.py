#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, shutil
from pathlib import Path
from typing import Any

import numpy as np

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue211_science_factorial import run as sci
from experiments.Issue228_axis_bc_10step import run as axis
from physics_harness.execution.cases import validate_case_references

DT_S = axis.DT_S
END_TIME_S = axis.END_TIME_S
EXPECTED_STEPS = axis.EXPECTED_STEPS
WAFER_NODE_TAG = 1500
WAFER_NODE_OLD = (0.04902151441154943, 0.1036438823016045)
WAFER_NODE_TARGETS = {
    'wafer_moderate': (WAFER_NODE_OLD[0], 0.1045),
    'wafer_matched': (WAFER_NODE_OLD[0], 0.1050),
}
WAFER_Z_M = 0.099
E_CHARGE = 1.602176634e-19
EPS0 = 8.8541878128e-12
NA = 6.02214076e23
R_GAS = 8.31446
TG_K = 600.0
N_REF = 1.2979134666850255e18


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _move_gmsh_node(path: Path, tag: int, old_xy: tuple[float,float], new_xy: tuple[float,float]) -> dict[str,Any]:
    lines = path.read_text(encoding='utf-8').splitlines()
    i0 = lines.index('$Nodes'); i1 = lines.index('$EndNodes', i0 + 1)
    nblocks = int(lines[i0+1].split()[0]); pos=i0+2; found=None
    for _ in range(nblocks):
        entity_dim, entity_tag, parametric, n = map(int, lines[pos].split()); pos += 1
        tags=[int(lines[pos+j]) for j in range(n)]; pos += n
        c0=pos
        if tag in tags:
            j=tags.index(tag); fields=lines[c0+j].split(); old=(float(fields[0]),float(fields[1]),float(fields[2]))
            if not (math.isclose(old[0],old_xy[0],abs_tol=1e-12) and math.isclose(old[1],old_xy[1],abs_tol=1e-12)):
                raise RuntimeError(f'node {tag} coordinate mismatch: {old} vs {old_xy}')
            fields[0]=f'{new_xy[0]:.17g}'; fields[1]=f'{new_xy[1]:.17g}'; lines[c0+j]=' '.join(fields)
            found={'tag':tag,'old_xyz':old,'new_xyz':(new_xy[0],new_xy[1],old[2]),'entity_dim':entity_dim,'entity_tag':entity_tag,'parametric':parametric}
        pos += n
    if found is None or pos != i1: raise RuntimeError(f'Gmsh node edit failed for {tag}')
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return found


def build_runtime_case(mode: str) -> tuple[str,dict[str,Any]]:
    if mode not in ('baseline', *WAFER_NODE_TARGETS): raise ValueError(mode)
    text, meta = axis.build_case()
    target = WAFER_NODE_TARGETS.get(mode)
    old_depth=(WAFER_NODE_OLD[1]-WAFER_Z_M)/3.0
    new_depth=((target[1] if target else WAFER_NODE_OLD[1])-WAFER_Z_M)/3.0
    return text, {**meta,'issue':228,'claim':'pgw_parallel_campaign','diagnostic_only':True,'mode':mode,
                  'axis_grounding_removed':True,'mesh_topology_changed':False,'physics_changed':False,
                  'wafer_node_tag':WAFER_NODE_TAG if target else None,'wafer_node_old_xy_m':WAFER_NODE_OLD if target else None,
                  'wafer_node_new_xy_m':target,'wafer_cell2387_depth_old_m':old_depth,'wafer_cell2387_depth_new_m':new_depth}


def runtime_self_test() -> dict[str,Any]:
    checks={}
    for m in ('baseline',*WAFER_NODE_TARGETS):
        _,meta=build_runtime_case(m)
        checks[f'{m}:axis_free']=meta['diagnostic_ground_boundary']==axis.GROUND_NONAXIS
        checks[f'{m}:steps']=int(meta['expected_steps'])==EXPECTED_STEPS
        checks[f'{m}:dt']=math.isclose(float(meta['dt_s']),DT_S,rel_tol=0,abs_tol=1e-24)
    checks['wafer:moderate_depth_increase']=(WAFER_NODE_TARGETS['wafer_moderate'][1]-WAFER_Z_M)/3 > (WAFER_NODE_OLD[1]-WAFER_Z_M)/3
    checks['wafer:matched_depth_increase']=(WAFER_NODE_TARGETS['wafer_matched'][1]-WAFER_Z_M)/3 > (WAFER_NODE_TARGETS['wafer_moderate'][1]-WAFER_Z_M)/3
    failed=sorted(k for k,v in checks.items() if not v)
    return {'status':'PASS' if not failed else 'FAIL','checks':checks,'failed_checks':failed}


def run_runtime(args: argparse.Namespace) -> int:
    exe=args.physics_opt.resolve(); out=args.results_root.resolve(); mode=args.mode
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    p0=runtime_self_test(); _write(out/'self_test.json',p0)
    if p0['status']!='PASS': raise RuntimeError(p0)
    text,meta=build_runtime_case(mode); case=out/'case'; logs=out/'logs'; logs.mkdir()
    summary={'status':'RUNNING','meta':meta}
    try:
        summary['stage']=sci._stage(case,text,meta)
        if mode in WAFER_NODE_TARGETS:
            summary['mesh_edit']=_move_gmsh_node(case/'qvt.msh',WAFER_NODE_TAG,WAFER_NODE_OLD,WAFER_NODE_TARGETS[mode])
            refs=validate_case_references(case)
            if not isinstance(refs,list): raise TypeError('validate_case_references must return list')
            summary['references_after_mesh_edit']=refs
    except Exception as exc:
        summary['status']='HARNESS_FAIL'; summary['error']=f'{type(exc).__name__}: {exc}'; _write(out/'summary.json',summary); return 1
    p2=s5r._p2(exe,case,logs/'p2.log',timeout=min(float(args.timeout),300.0)); summary['p2']=p2
    if p2.get('returncode')!=0: summary['status']='P2_FAIL'; _write(out/'summary.json',summary); return 1
    rt=sci._runtime(exe,case,logs/'runtime.log',logs/'time_v.log',float(args.timeout)); summary['runtime']=rt
    try:
        result=axis._analyse(case,text,meta,rt); summary['result']=result
        good=result['runtime_returncode']==0 and not result['timed_out'] and result['physical_steps']==EXPECTED_STEPS and result['all_steps_hard_pass']
        summary['status']='PASS' if good else 'FAIL'
    except Exception as exc:
        good=False; summary['status']='ANALYSIS_FAIL'; summary['error']=f'{type(exc).__name__}: {exc}'
    _write(out/'summary.json',summary); return 0 if good else 1


def _decode_names(a) -> list[str]:
    return [bytes(row).split(b'\0')[0].decode(errors='ignore').strip() for row in a]


def _load_snapshot(root: Path, step_index: int):
    from scipy.io import netcdf_file
    epath=root/'case'/'input_out.e'
    if not epath.is_file():
        matches=list(root.rglob('input_out.e'))
        if len(matches)!=1: raise RuntimeError(f'expected one input_out.e under {root}, got {matches}')
        epath=matches[0]
    f=netcdf_file(str(epath),'r',mmap=False)
    coords=np.c_[f.variables['coordx'].data.copy(),f.variables['coordy'].data.copy()]
    conn=f.variables['connect1'].data.copy().astype(int)
    elem_map=f.variables['elem_num_map'].data.copy().astype(int)[:len(conn)]
    names=_decode_names(f.variables['name_elem_var'].data.copy())
    ev={name:f.variables[f'vals_elem_var{i+1}eb1'].data.copy() for i,name in enumerate(names)}
    times=f.variables['time_whole'].data.copy()
    if step_index<0: step_index=len(times)+step_index
    if step_index<=0 or step_index>=len(times): raise ValueError(f'step_index must select a physical step 1..{len(times)-1}')
    vals={k:v[step_index].astype(float) for k,v in ev.items()}
    ss_names=_decode_names(f.variables['ss_names'].data.copy())
    sidesets=[]
    for i,name in enumerate(ss_names,1):
        sidesets.append((name,f.variables[f'elem_ss{i}'].data.copy().astype(int),f.variables[f'side_ss{i}'].data.copy().astype(int)))
    f.close()
    return coords,conn,elem_map,vals,float(times[step_index]),sidesets


def _charge_density(vals):
    p=vals['p']; wO=vals['w_O']; wO2p=vals['w_O2p']; wO2s=vals['w_O2s']; wOm=vals['w_Om']; wOp=vals['w_Op']; wOs=vals['w_Os']
    wO2=1.0-(wO2p+wO2s+wO+wOm+wOp+wOs)
    Mn=1.0/(wO2/0.032+wO2s/0.032+wO2p/0.032+wO/0.016+wOm/0.016+wOp/0.016+wOs/0.016)
    rho=p*Mn/(R_GAS*TG_K)
    return E_CHARGE*(rho*wO2p*NA/0.032-rho*wOm*NA/0.016+rho*wOp*NA/0.016-N_REF*vals['n_e'])


def _geom(coords,conn):
    tri=coords[conn-1]; a=tri[:,1]-tri[:,0]; b=tri[:,2]-tri[:,0]
    area=np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])/2.0
    rcent=tri[:,:,0].mean(axis=1); vol=2*math.pi*area*rcent
    return tri,area,rcent,vol


def _boundary_nodes(conn,sidesets,boundary_name):
    side_nodes={1:(0,1),2:(1,2),3:(2,0)}
    for name,elems,sides in sidesets:
        if name==boundary_name:
            out=set()
            for e,s in zip(elems,sides):
                if 1<=e<=len(conn):
                    for j in side_nodes[int(s)]: out.add(int(conn[e-1,j]-1))
            return out
    raise RuntimeError(f'missing sideset {boundary_name}')


def _solve_fe(coords,conn,rhoq,sidesets):
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    plasma_nodes=np.unique(conn.flatten()-1); pidx={int(n):i for i,n in enumerate(plasma_nodes)}; npn=len(plasma_nodes)
    rows=[]; cols=[]; data=[]; rhs=np.zeros(npn)
    for ei,row in enumerate(conn):
        gids=row-1; ids=np.array([pidx[int(n)] for n in gids]); pts=coords[gids]; x=pts[:,0]; y=pts[:,1]
        M=np.c_[np.ones(3),x,y]; det=np.linalg.det(M); A=abs(det)/2.0; inv=np.linalg.inv(M)
        grads=np.array([[inv[1,i],inv[2,i]] for i in range(3)])
        Ke=2*math.pi*A*x.mean()*(grads@grads.T); src=rhoq[ei]/EPS0
        for i in range(3):
            rhs[ids[i]] += 2*math.pi*src*A*(x.sum()+x[i])/12.0
            for j in range(3): rows.append(ids[i]); cols.append(ids[j]); data.append(Ke[i,j])
    K=sp.csr_matrix((data,(rows,cols)),shape=(npn,npn))
    dir_global=_boundary_nodes(conn,sidesets,'r228_phi_ground_nonaxis'); dir_local=[pidx[n] for n in dir_global if n in pidx]
    free=np.ones(npn,dtype=bool); free[dir_local]=False; phi=np.zeros(npn)
    phi[free]=spla.spsolve(K[free][:,free],rhs[free])
    cell=np.empty(len(conn))
    for i,row in enumerate(conn): cell[i]=phi[[pidx[int(n)] for n in row-1]].mean()
    return phi,cell,plasma_nodes


def _wall_cells_and_neighbors(conn,sidesets):
    physical={'plasma_electrode','plasma_metal','plasma_right','plasma_cover','plasma_wafer','plasma_focus_ring'}
    wall=set()
    for name,elems,_sides in sidesets:
        if name in physical:
            wall.update(int(e-1) for e in elems if 1<=e<=len(conn))
    edge_map={}
    for i,row in enumerate(conn):
        ids=[int(x-1) for x in row]
        for a,b in ((ids[0],ids[1]),(ids[1],ids[2]),(ids[2],ids[0])):
            edge_map.setdefault(tuple(sorted((a,b))),[]).append(i)
    neigh={i:set() for i in wall}
    for _edge,cells in edge_map.items():
        if len(cells)==2:
            a,b=cells
            if a in wall and b not in wall: neigh[a].add(b)
            if b in wall and a not in wall: neigh[b].add(a)
    for i in wall:
        if neigh[i]: continue
        for _edge,cells in edge_map.items():
            if i in cells and len(cells)==2:
                j=cells[0] if cells[1]==i else cells[1]
                if j!=i: neigh[i].add(j)
    return wall,neigh


def _relocate_positive_wall_charge(rhoq,vol,conn,sidesets,fraction):
    out=rhoq.copy(); wall,neigh=_wall_cells_and_neighbors(conn,sidesets); moved=0.0; used=0
    for i in sorted(wall):
        if rhoq[i] <= 0 or not neigh[i]: continue
        q=fraction*rhoq[i]*vol[i]
        out[i]-=q/vol[i]
        js=sorted(neigh[i]); vtot=sum(vol[j] for j in js)
        for j in js: out[j]+=q/vtot
        moved += q; used += 1
    return out,{'fraction':fraction,'wall_cells_considered':len(wall),'positive_wall_cells_relocated':used,'moved_charge_C':moved,
                'q_before_C':float(np.dot(rhoq,vol)),'q_after_C':float(np.dot(out,vol)),
                'charge_conservation_abs_C':float(abs(np.dot(out-rhoq,vol)))}


def _hotspot_table(elem_map,fv,fe,rhoq,coords,conn):
    result={}
    for eid in (2401,2424,2387):
        hits=np.where(elem_map==eid)[0]
        if len(hits)!=1: continue
        i=int(hits[0]); result[str(eid)]={'fv_phi_V':float(fv[i]),'fe_cell_phi_V':float(fe[i]),'rho_q_C_m3':float(rhoq[i]),'centroid_m':coords[conn[i]-1].mean(axis=0).tolist()}
    return result


def run_frozen(args: argparse.Namespace) -> int:
    root=args.snapshot_root.resolve(); out=args.results_root.resolve()
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    coords,conn,emap,vals,t,sidesets=_load_snapshot(root,args.step_index)
    rhoq=_charge_density(vals); _tri,_area,_rcent,vol=_geom(coords,conn); fv=vals['potential_plasma']
    base_phi_nodes,base_fe,_=_solve_fe(coords,conn,rhoq,sidesets)
    frac=float(args.relocate_fraction)
    rho_use=rhoq; relocate=None
    if frac>0:
        rho_use,relocate=_relocate_positive_wall_charge(rhoq,vol,conn,sidesets,frac)
    phi_nodes,fe,_=_solve_fe(coords,conn,rho_use,sidesets)
    summary={'status':'PASS','claim':'frozen_poisson_and_charge_support_discriminator','step_index':args.step_index,'time_s':t,'relocate_fraction':frac,
             'input_charge_C':float(np.dot(rhoq,vol)),'used_charge_C':float(np.dot(rho_use,vol)),
             'fv_phi_min_V':float(fv.min()),'fv_phi_max_V':float(fv.max()),'fv_phi_span_V':float(fv.max()-fv.min()),
             'fe_baseline_node_max_V':float(base_phi_nodes.max()),'fe_baseline_cell_min_V':float(base_fe.min()),'fe_baseline_cell_max_V':float(base_fe.max()),
             'fe_used_node_max_V':float(phi_nodes.max()),'fe_used_cell_min_V':float(fe.min()),'fe_used_cell_max_V':float(fe.max()),
             'fe_used_span_V':float(fe.max()-fe.min()),'relocation':relocate,
             'hotspots_baseline':_hotspot_table(emap,fv,base_fe,rhoq,coords,conn),
             'hotspots_used':_hotspot_table(emap,fv,fe,rho_use,coords,conn)}
    if relocate:
        summary['fe_cell_max_change_V']=float(fe.max()-base_fe.max()); summary['fe_node_max_change_V']=float(phi_nodes.max()-base_phi_nodes.max())
    _write(out/'summary.json',summary)
    return 0


def main() -> int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    r=sub.add_parser('runtime'); r.add_argument('--mode',choices=('baseline',*WAFER_NODE_TARGETS),required=True); r.add_argument('--physics-opt',type=Path,required=True); r.add_argument('--results-root',type=Path,required=True); r.add_argument('--timeout',type=float,default=1800); r.add_argument('--self-test',action='store_true')
    q=sub.add_parser('frozen'); q.add_argument('--snapshot-root',type=Path,required=True); q.add_argument('--step-index',type=int,required=True); q.add_argument('--relocate-fraction',type=float,default=0.0); q.add_argument('--results-root',type=Path,required=True)
    a=p.parse_args()
    if a.cmd=='runtime' and a.self_test:
        x=runtime_self_test(); print(json.dumps(x,indent=2,sort_keys=True)); return 0 if x['status']=='PASS' else 1
    return run_runtime(a) if a.cmd=='runtime' else run_frozen(a)

if __name__=='__main__': raise SystemExit(main())
