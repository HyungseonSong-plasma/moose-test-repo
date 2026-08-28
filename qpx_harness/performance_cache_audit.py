"""Static cache-feasibility audit for QPXThermalDiffusionMaterial D_mix functors."""
from __future__ import annotations
import argparse, hashlib, json, re, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MATERIAL_RELATIVE = Path('src/materials/QPXThermalDiffusionMaterial.C')
TEXT_SUFFIXES = {'.C','.cc','.cpp','.cxx','.h','.hh','.hpp'}
CACHE_ELIGIBLE_SPACE_ARGS = {'ElemQpArg','ElemSideQpArg'}
CACHE_INELIGIBLE_SPACE_ARGS = {'ElemArg','FaceArg'}
class CacheAuditError(RuntimeError): pass

def _sha256_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()

def _line_number(text, offset): return text.count('\n',0,offset)+1

def _mask_cpp(text):
    out=list(text); i=0; state='code'; quote=''
    while i<len(text):
        c=text[i]; n=text[i+1] if i+1<len(text) else ''
        if state=='code':
            if c=='/' and n=='/': out[i]=out[i+1]=' '; i+=2; state='line'; continue
            if c=='/' and n=='*': out[i]=out[i+1]=' '; i+=2; state='block'; continue
            if c in {'"',"'"}: quote=c; out[i]=' '; i+=1; state='string'; continue
            i+=1; continue
        if state=='line':
            if c=='\n': state='code'
            else: out[i]=' '
            i+=1; continue
        if state=='block':
            if c=='*' and n=='/': out[i]=out[i+1]=' '; i+=2; state='code'
            else:
                if c!='\n': out[i]=' '
                i+=1
            continue
        if state=='string':
            if c=='\\':
                out[i]=' '
                if i+1<len(text):
                    if text[i+1]!='\n': out[i+1]=' '
                    i+=2
                else: i+=1
                continue
            out[i]='\n' if c=='\n' else ' '; i+=1
            if c==quote: state='code'
    return ''.join(out)

def _matching_paren(masked, open_idx):
    depth=0
    for i in range(open_idx,len(masked)):
        if masked[i]=='(': depth+=1
        elif masked[i]==')':
            depth-=1
            if depth==0:return i
    raise CacheAuditError('unmatched parenthesis')

def _split_top_level_args(text):
    args=[]; start=0; p=b=r=0
    for i,c in enumerate(text):
        if c=='(':p+=1
        elif c==')':p=max(0,p-1)
        elif c=='[':b+=1
        elif c==']':b=max(0,b-1)
        elif c=='{':r+=1
        elif c=='}':r=max(0,r-1)
        elif c==',' and not(p or b or r): args.append(text[start:i].strip()); start=i+1
    tail=text[start:].strip()
    if tail:args.append(tail)
    return args

def _extract_dmix_declaration(text):
    masked=_mask_cpp(text); matches=[]
    for m in re.finditer(r'addFunctorProperty\s*<\s*ADReal\s*>\s*\(',masked):
        oi=masked.find('(',m.start()); ci=_matching_paren(masked,oi); raw=text[m.start():ci+1]
        if '_D_mix_names' not in raw: continue
        args=_split_top_level_args(raw[raw.find('(')+1:-1]); flags=sorted(set(re.findall(r'\bEXEC_[A-Z0-9_]+\b',raw)))
        kind='DEFAULT_ALWAYS_EVALUATE'
        if flags:
            if 'EXEC_ALWAYS' in flags: kind='EXPLICIT_ALWAYS_EVALUATE'
            elif {'EXEC_LINEAR','EXEC_NONLINEAR'}.issubset(flags): kind='EXPLICIT_LINEAR_NONLINEAR_CLEARANCE'
            else: kind='EXPLICIT_OTHER_CLEARANCE'
        matches.append({'line':_line_number(text,m.start()),'argument_count':len(args),'schedule_kind':kind,'schedule_tokens':flags,'calls_full_evaluate':bool(re.search(r'\bevaluate\s*\([^)]*\)\s*\.D_mix\s*\[',raw,re.S)),'snippet':' '.join(raw.split())[:500]})
    if len(matches)!=1: raise CacheAuditError(f'expected exactly one D_mix addFunctorProperty declaration, found {len(matches)}')
    return matches[0]

def _space_arg_bindings(text):
    masked=_mask_cpp(text); out={}
    pats={
      'ElemQpArg':[r'\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemQpArg\s*\(',r'\b(?:Moose::)?ElemQpArg\s+([A-Za-z_]\w*)'],
      'ElemSideQpArg':[r'\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemSideQpArg\s*\(',r'\b(?:Moose::)?ElemSideQpArg\s+([A-Za-z_]\w*)'],
      'ElemArg':[r'\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemArg\s*\(',r'\b(?:Moose::)?ElemArg\s+([A-Za-z_]\w*)'],
      'FaceArg':[r'\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*(?:makeFace|makeFaceArg)\s*\(',r'\b(?:Moose::)?FaceArg\s+([A-Za-z_]\w*)']}
    for kind,ps in pats.items():
        for p in ps:
            for m in re.finditer(p,masked):out[m.group(1)]=kind
    return out

def _infer_space_arg(expr, bindings):
    s=expr.strip()
    for kind,toks in [('ElemSideQpArg',('makeElemSideQpArg','ElemSideQpArg')),('ElemQpArg',('makeElemQpArg','ElemQpArg')),('FaceArg',('makeFaceArg','makeFace','FaceArg')),('ElemArg',('makeElemArg','ElemArg'))]:
        if any(t in s for t in toks):return kind
    if re.fullmatch(r'[A-Za-z_]\w*',s) and s in bindings:return bindings[s]
    return 'UNKNOWN'

def _find_dmix_functor_variables(text):
    masked=_mask_cpp(text); out=set()
    pats=[r'\b(?:const\s+)?auto\s*&?\s*([A-Za-z_]\w*)\s*=\s*getFunctor\s*<\s*ADReal\s*>\s*\([^;]*D_mix',r'\b([A-Za-z_]\w*D_mix[A-Za-z_0-9]*)\b',r'\b(_D_mix[A-Za-z_0-9]*)\b']
    for p in pats:
        for m in re.finditer(p,masked,re.I):out.add(m.group(1))
    return out

def _consumer_calls(path,text):
    masked=_mask_cpp(text); bindings=_space_arg_bindings(text); rows=[]
    for var in sorted(_find_dmix_functor_variables(text),key=len,reverse=True):
        for m in re.finditer(rf'\b{re.escape(var)}\s*\(',masked):
            oi=masked.find('(',m.start()); ci=_matching_paren(masked,oi); args=_split_top_level_args(text[oi+1:ci])
            if not args:continue
            first=args[0]; kind=_infer_space_arg(first,bindings); ls=text.rfind('\n',0,m.start())+1; le=text.find('\n',ci); le=len(text) if le<0 else le
            rows.append({'path':str(path),'line':_line_number(text,m.start()),'functor_variable':var,'first_argument':first.strip()[:200],'space_arg':kind,'cache_eligible':kind in CACHE_ELIGIBLE_SPACE_ARGS,'snippet':' '.join(text[ls:le].split())[:500]})
    unique={}
    for row in rows: unique[(row['path'],row['line'],row['snippet'])]=row
    return list(unique.values())

def _source_files(root):
    out=[]
    for base_name in ('src','include'):
        base=root/base_name
        if base.is_dir():
            out += [p for p in base.rglob('*') if p.is_file() and p.suffix in TEXT_SUFFIXES]
    return sorted(out)

def audit_qpx_tree(qpx_root):
    root=qpx_root.resolve(); material=root/MATERIAL_RELATIVE
    if not material.is_file(): raise CacheAuditError(f'missing material source: {material}')
    declaration=_extract_dmix_declaration(material.read_text(errors='replace')); consumers=[]; lexical=[]
    for path in _source_files(root):
        if path.resolve()==material.resolve():continue
        text=path.read_text(errors='replace')
        if 'D_mix' not in text and '_D_mix' not in text:continue
        lexical.append(str(path.relative_to(root))); consumers += _consumer_calls(path.relative_to(root),text)
    counts={}
    for row in consumers:counts[row['space_arg']]=counts.get(row['space_arg'],0)+1
    if not consumers: status='INCONCLUSIVE'; rec='INCONCLUSIVE'; reason='D_mix declaration found but no traceable D_mix consumer call identified'; eligible=None
    elif any(r['space_arg'] in CACHE_INELIGIBLE_SPACE_ARGS for r in consumers): status='PASS'; rec='MATERIAL_SHARED_RESULT_REQUIRED'; reason='at least one D_mix consumer uses ElemArg/FaceArg, outside the native quadrature-point cache path'; eligible=False
    elif any(r['space_arg']=='UNKNOWN' for r in consumers): status='INCONCLUSIVE'; rec='INCONCLUSIVE'; reason='one or more D_mix consumer spatial arguments could not be classified without guessing'; eligible=None
    else:
        eligible=True; status='PASS'
        if declaration['schedule_kind']=='EXPLICIT_LINEAR_NONLINEAR_CLEARANCE': rec='NATIVE_CACHE_ALREADY_CONFIGURED'; reason='all observed D_mix consumers use quadrature-point arguments and LINEAR/NONLINEAR clearance is already configured'
        else: rec='NATIVE_FUNCTOR_CACHE_CANDIDATE'; reason='all observed D_mix consumers use ElemQpArg/ElemSideQpArg and expected LINEAR/NONLINEAR clearance is not configured'
    return {'schema_version':1,'analysis_status':status,'qpx_root':str(root),'material_source':str(material),'material_sha256':_sha256_file(material),'dmix_declaration':declaration,'consumer_lexical_files':lexical,'consumers':consumers,'space_arg_counts':counts,'native_cache_eligible':eligible,'recommendation':rec,'reason':reason,'framework_contract':{'default_functor_behavior':'always evaluate unless cache clearance is configured','native_qp_cache_space_args':sorted(CACHE_ELIGIBLE_SPACE_ARGS),'non_qp_space_args_not_claimed_cacheable':sorted(CACHE_INELIGIBLE_SPACE_ARGS),'ad_correctness_guard':'candidate native cache must clear at LINEAR and NONLINEAR before production promotion'},'runtime_executed':False,'production_source_mutated':False}

def _synthetic_material(schedule=''):
    extra=f', {schedule}' if schedule else ''
    return f'''#include "QPXThermalDiffusionMaterial.h"\nQPXThermalDiffusionMaterial::QPXThermalDiffusionMaterial()\n{{\n addFunctorProperty<ADReal>(_D_mix_names[i], [this, i](const auto & r, const auto & state) {{ return evaluate(r, state).D_mix[i]; }}{extra});\n}}\n'''
def _write_tree(root,consumer,schedule=''):
    p=root/MATERIAL_RELATIVE;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(_synthetic_material(schedule)); k=root/'src/fvkernels/QPXFVMixtureAveragedDiffusion.C';k.parent.mkdir(parents=True,exist_ok=True);k.write_text(consumer)
def self_test():
    try:
      cases=[('''void K::f(){ const auto qp_arg=makeElemQpArg(_qp); const auto & _D_mix=getFunctor<ADReal>("D_mix_O2"); auto v=_D_mix(qp_arg, determineState()); }''','', 'NATIVE_FUNCTOR_CACHE_CANDIDATE',{'ElemQpArg':1}),('''void K::f(){ const auto face=makeFace(*_face_info, limiter, true); const auto & _D_mix=getFunctor<ADReal>("D_mix_O2"); auto v=_D_mix(face, determineState()); }''','', 'MATERIAL_SHARED_RESULT_REQUIRED',{'FaceArg':1}),('''void K::f(){ const auto & _D_mix=getFunctor<ADReal>("D_mix_O2"); auto v=_D_mix(location, determineState()); }''','', 'INCONCLUSIVE',{'UNKNOWN':1}),('''void K::f(){ Moose::ElemSideQpArg side_qp; const auto & _D_mix=getFunctor<ADReal>("D_mix_O2"); auto v=_D_mix(side_qp, determineState()); }''','{EXEC_LINEAR, EXEC_NONLINEAR}', 'NATIVE_CACHE_ALREADY_CONFIGURED',{'ElemSideQpArg':1})]
      for consumer,sched,rec,counts in cases:
        with tempfile.TemporaryDirectory() as td:
          root=Path(td);_write_tree(root,consumer,sched);r=audit_qpx_tree(root)
          assert r['recommendation']==rec,(r,rec);assert r['space_arg_counts']==counts,(r,counts)
      with tempfile.TemporaryDirectory() as td:
        root=Path(td);_write_tree(root,cases[0][0]);p=root/MATERIAL_RELATIVE;p.write_text(p.read_text().replace('return evaluate(r, state).D_mix[i];','return cached_Dmix[i];'));r=audit_qpx_tree(root);assert not r['dmix_declaration']['calls_full_evaluate']
      print('QPX_CACHE_AUDIT_SELFTEST: PASS');return 0
    except Exception as exc: print(f'QPX_CACHE_AUDIT_SELFTEST: FAIL: {exc}');return 1

def _new_run_root(results):
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');base=results/f'cache_audit_{stamp}';cand=base;i=1
    while cand.exists():cand=Path(f'{base}_{i:02d}');i+=1
    cand.mkdir(parents=True);return cand

def main(argv:Iterable[str]|None=None):
    p=argparse.ArgumentParser(prog='qpx cache-audit');p.add_argument('--qpx');p.add_argument('--results-root');p.add_argument('--self-test',action='store_true');a=p.parse_args(list(argv) if argv is not None else None)
    if a.self_test:return self_test()
    if not a.qpx:p.error('--qpx is required unless --self-test is used')
    qpx=Path(a.qpx).expanduser().resolve()
    if not qpx.is_file():print(f'QPX_CACHE_AUDIT_ERROR: qpx executable not found: {qpx}',file=sys.stderr);return 2
    try:
      result=audit_qpx_tree(qpx.parent); results=Path(a.results_root).expanduser().resolve() if a.results_root else qpx.parent/'temp'/'results';root=_new_run_root(results);result['qpx_executable']=str(qpx);summary=root/'cache_audit.json';summary.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    except Exception as exc:print(f'QPX_CACHE_AUDIT_ERROR: {exc}',file=sys.stderr);return 2
    print(f'QPX_CACHE_AUDIT_ROOT: {root}');print(f"QPX_CACHE_AUDIT_STATUS: {result['analysis_status']}");print(f"QPX_CACHE_MATERIAL_SHA256: {result['material_sha256']}");print(f"QPX_CACHE_DMIX_DECLARATION: {result['dmix_declaration']['schedule_kind']}");print('QPX_CACHE_DMIX_CALLS_FULL_EVALUATE:',result['dmix_declaration']['calls_full_evaluate']);print('QPX_CACHE_SPACE_ARGS:',json.dumps(result['space_arg_counts'],sort_keys=True));print(f"QPX_CACHE_NATIVE_ELIGIBLE: {result['native_cache_eligible']}");print(f"QPX_CACHE_RECOMMENDATION: {result['recommendation']}");print(f"QPX_CACHE_REASON: {result['reason']}");print(f'QPX_CACHE_SUMMARY: {summary}');return 0 if result['analysis_status']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
