#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, shlex, shutil, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path

EXPECTED_QPX_HEAD = "4f42575257e6c4d52fee8617edaf34c9956457f2"
EXPECTED_QVT_SHA = "a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
EXPECTED_ELECTRON_TABLE_SHA = "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
EXPECTED_TRANSPORT_SHA = "2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d"
GROUND_BCS = ["plasma_metal", "plasma_electrode", "plasma_right", "inlet", "outlet"]
SOLVED_HEAVY = ["w_O2s","w_O2p","w_O","w_Om","w_Op","w_Os"]
SHARED_BINDINGS = {"gas_temperature":"T_g", "pressure":"p"}
MATERIAL_SECTIONS = ("FunctorMaterials", "Materials", "ADMaterials", "FVMaterials")

@dataclass
class Block:
    name: str
    start: int
    end: int
    raw: str
    params: dict[str,str]

@dataclass(frozen=True)
class Provider:
    name: str
    blocks: tuple[str,...]
    section: str
    object_name: str
    source: str


def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024), b''):
            h.update(c)
    return h.hexdigest()


def run(cmd, cwd=None, log=None):
    cp=subprocess.run([str(x) for x in cmd], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log: Path(log).write_text(cp.stdout, errors='replace')
    return cp


def stripq(s: str) -> str:
    s=s.strip()
    if len(s)>=2 and s[0]==s[-1] and s[0] in "'\"": return s[1:-1]
    return s


def parse_params(raw: str) -> dict[str,str]:
    d={}
    for line in raw.splitlines():
        s=line.split('#',1)[0].strip()
        if '=' in s and not s.startswith('['):
            k,v=s.split('=',1); d[k.strip()]=v.strip()
    return d


def section_bounds(lines, sec):
    start=None; depth=0
    for i,line in enumerate(lines):
        s=line.split('#',1)[0].strip()
        if start is None:
            if s==f'[{sec}]': start=i; depth=1
            continue
        if re.fullmatch(r'\[(?!\.\./)([^\]]+)\]',s): depth += 1
        elif s=='[]':
            depth -= 1
            if depth==0: return start,i
    return None


def child_blocks(text: str, sec: str) -> list[Block]:
    lines=text.splitlines(); b=section_bounds(lines,sec)
    if not b: return []
    ss,se=b; out=[]; depth=1; cs=None; cn=None
    for i in range(ss+1,se):
        s=lines[i].split('#',1)[0].strip()
        m=re.fullmatch(r'\[(?!\.\./)([^\]]+)\]',s)
        if m:
            depth += 1
            if depth==2: cs=i; cn=m.group(1)
        elif s=='[]':
            if depth==2 and cs is not None:
                raw='\n'.join(lines[cs:i+1])+'\n'
                out.append(Block(cn,cs,i,raw,parse_params(raw)))
                cs=None; cn=None
            depth -= 1
    return out


def remove_blocks(text, sec, pred):
    lines=text.splitlines(); idx=set()
    for b in child_blocks(text,sec):
        if pred(b): idx.update(range(b.start,b.end+1))
    return '\n'.join(x for i,x in enumerate(lines) if i not in idx)+'\n'


def append_blocks(text, sec, raws):
    if not raws: return text
    lines=text.splitlines(); b=section_bounds(lines,sec); payload=[]
    for raw in raws:
        payload += [('  '+x if x.strip() else x) for x in raw.rstrip('\n').splitlines()]
    if b:
        _,se=b; lines=lines[:se]+payload+lines[se:]
    else:
        lines += ['',f'[{sec}]']+payload+['[]']
    return '\n'.join(lines)+'\n'


def rename_word(raw, old, new):
    return re.sub(rf'\b{re.escape(old)}\b',new,raw)


def set_param(raw,key,value):
    pat=rf'(?m)^(\s*{re.escape(key)}\s*=\s*).*$'
    if re.search(pat,raw): return re.sub(pat,rf'\g<1>{value}',raw)
    lines=raw.rstrip('\n').splitlines(); lines.insert(-1,f'  {key} = {value}')
    return '\n'.join(lines)+'\n'


def rename_header(raw,newname):
    return re.sub(r'(?m)^(\s*)\[[^\]]+\]\s*$',rf'\1[{newname}]',raw,count=1)


def find_input(case: Path):
    tj=case/'test.json'
    if tj.exists():
        try:
            j=json.loads(tj.read_text())
            if j.get('input') and (case/j['input']).exists(): return case/j['input']
        except Exception: pass
    if (case/'input.i').exists(): return case/'input.i'
    fs=sorted(case.glob('*.i'))
    if fs: return fs[0]
    raise RuntimeError(f'no .i input in {case}')


def top_substitutions(text):
    out={}; depth=0
    for line in text.splitlines():
        s=line.split('#',1)[0].strip()
        if not s: continue
        if re.fullmatch(r'\[(?!\.\./)([^\]]+)\]',s): depth += 1; continue
        if s=='[]': depth=max(0,depth-1); continue
        if depth==0 and '=' in s:
            k,v=s.split('=',1)
            if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',k.strip()): out[k.strip()]=v.strip()
    return out


def inline_subs(raw, subs):
    for _ in range(8):
        changed=False
        def repl(m):
            nonlocal changed
            k=m.group(1)
            if k in subs:
                changed=True; return stripq(subs[k])
            return m.group(0)
        nr=re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}',repl,raw)
        raw=nr
        if not changed: break
    return raw


def block_tokens(v):
    if not v: return ('*',)
    s=stripq(v)
    toks=tuple(x for x in re.split(r'[\s,]+',s) if x)
    return toks or ('*',)


def provided_names(block: Block, section: str):
    out=set()
    if section in ('Variables','AuxVariables','Functions'):
        out.add(block.name)
    if 'property_name' in block.params:
        out.add(stripq(block.params['property_name']))
    if 'prop_names' in block.params:
        out |= set(split_words(block.params['prop_names']))

    typ=stripq(block.params.get('type',''))
    if typ=='QPXElectronTransportLookupMaterial':
        out |= {
            'neutral_number_density',
            'electron_reduced_mobility',
            'electron_reduced_diffusion',
            'electron_mobility',
            'electron_diffusion',
        }
    if typ=='QPXPlasmaChargeDensityMaterial':
        out |= {'charge_number_density','charge_density','poisson_charge_source'}
    # Do NOT infer functor providers from arbitrary input parameters.
    # BaseMaterial.relative_permittivity is input metadata here, not a named functor.
    return out


def providers_from_text(text: str, source: str):
    out=[]
    for sec in ('Variables','AuxVariables','Functions') + MATERIAL_SECTIONS:
        for b in child_blocks(text,sec):
            if sec=='Functions':
                blocks=('*',)
            else:
                blocks=block_tokens(b.params.get('block',''))
            for name in provided_names(b,sec):
                out.append(Provider(name,blocks,sec,b.name,source))
    return out


def _include_targets(text: str):
    """Return MOOSE !include targets in execution order."""
    out=[]
    for line in text.splitlines():
        s=line.split('#',1)[0].strip()
        if not s.startswith('!include'):
            continue
        rest=s[len('!include'):].strip()
        if not rest:
            continue
        if len(rest)>=2 and rest[0] in "'\"" and rest[-1]==rest[0]:
            rest=rest[1:-1]
        else:
            rest=rest.split()[0]
        out.append(rest)
    return out


def execution_source_view(case: Path, entry_path: Path|None=None, override_text: str|None=None):
    """Return only input files reachable from the actual QPX entry input.

    Do not scan every *.i in the case directory: accepted workspaces may retain
    generated/assembled input.i alongside source fragments such as physics.i.
    Counting both is not the MOOSE execution graph and false-doubles providers.
    """
    entry=(entry_path or find_input(case)).resolve()
    case=case.resolve()
    seen=set(); ordered=[]

    def visit(path: Path, text_override: str|None=None):
        rp=path.resolve()
        if rp in seen:
            return
        if not rp.exists() and text_override is None:
            raise RuntimeError(f'included input does not exist: {rp}')
        seen.add(rp)
        txt=text_override if text_override is not None else rp.read_text(errors='replace')
        try:
            source=str(rp.relative_to(case))
        except ValueError:
            source=str(rp)
        ordered.append((rp,source,txt))
        for rel in _include_targets(txt):
            child=(rp.parent/rel).resolve()
            visit(child,None)

    visit(entry, override_text if entry_path is not None and entry==entry_path.resolve() else None)
    return ordered


def providers_from_case(case: Path, override_path: Path|None=None, override_text: str|None=None):
    out=[]
    entry=override_path or find_input(case)
    for _,source,txt in execution_source_view(case,entry,override_text):
        out.extend(providers_from_text(txt,source))
    return out


def applies(p: Provider, consumer_blocks: tuple[str,...]):
    if '*' in p.blocks or '*' in consumer_blocks: return True
    return bool(set(p.blocks)&set(consumer_blocks))


def applicable(providers,name,consumer_blocks):
    return [p for p in providers if p.name==name and applies(p,consumer_blocks)]


def provider_signature(providers,names):
    return sorted((p.name,p.blocks,p.section,p.object_name,p.source) for p in providers if p.name in names)


def locate_provider_block(text: str, name: str):
    found=[]
    for sec in ('Variables','AuxVariables','Functions') + MATERIAL_SECTIONS:
        for b in child_blocks(text,sec):
            if name in provided_names(b,sec): found.append((sec,b))
    return found


def split_words(v):
    s=stripq(v)
    try:
        return shlex.split(s)
    except Exception:
        return [x for x in re.split(r'[\s,]+',s) if x]


def is_literal_functor(v):
    s=stripq(v)
    try:
        float(s); return True
    except Exception:
        return s in {'1','0','one','zero'}


def ref_items(v):
    return [(x, is_literal_functor(x)) for x in split_words(v)]


def external_refs_for_block(section: str, b: Block):
    """Return (role, ref, ref_kind) for integration-relevant object APIs.

    ref_kind='variable' means the MOOSE parameter requires a variable object.
    ref_kind='functor' means variables/functions/material functors are valid.
    """
    typ=stripq(b.params.get('type',''))
    refs=[]
    def one(key,kind='functor'):
        if key in b.params:
            refs.append((key,stripq(b.params[key]),kind))
    def many(key,kind='functor'):
        if key in b.params:
            refs.extend((key,x,kind) for x in split_words(b.params[key]))

    if section in MATERIAL_SECTIONS:
        if typ=='QPXElectronTransportLookupMaterial':
            for k in ('mean_energy','pressure','gas_temperature'): one(k)
        elif typ=='QPXPlasmaChargeDensityMaterial':
            for k in ('density','electron_density'): one(k)
            many('ion_mass_fractions')
        elif typ in {'ADParsedFunctorMaterial','ParsedFunctorMaterial'}:
            many('functor_names')
        elif typ in {'ADGenericFunctorMaterial','GenericFunctorMaterial'}:
            many('prop_values')
    elif section=='FVKernels':
        if typ=='FVTimeKernel':
            one('variable','variable')
        elif typ=='FVDiffusion':
            one('variable','variable'); one('coeff')
        elif typ=='FVCoupledForce':
            one('variable','variable'); one('v')
        elif typ=='QPXFVElectrostaticDrift':
            one('variable','variable')
            for k in ('potential','mobility','carrier'): one(k)
        elif typ=='QPXFVHeavyMassElectromigrationCorrection':
            one('variable','variable'); one('potential'); one('rho')
            many('ion_mass_fractions'); many('ion_mobilities')
    elif section=='FVBCs' and typ=='FVDirichletBC':
        one('variable','variable')
    return refs


def integration_blocks(text: str, extra_names=()):
    extra=set(extra_names)
    out=[]
    for sec in ('Variables','AuxVariables','Functions') + MATERIAL_SECTIONS + ('FVKernels','FVBCs'):
        for b in child_blocks(text,sec):
            if b.name.startswith('r30_') or b.name in extra or b.name in {'n_e_solved','potential_plasma'}:
                out.append((sec,b))
    return out


def variable_matches(providers,name,consumer_blocks):
    return [p for p in applicable(providers,name,consumer_blocks) if p.section in {'Variables','AuxVariables'}]


def external_reference_inventory(text: str, providers, interface):
    errs=[]; rows=[]
    for sec,b in integration_blocks(text,interface.get('extra_names',())):
        cblocks=block_tokens(b.params.get('block',''))
        for role,ref,kind in external_refs_for_block(sec,b):
            if is_literal_functor(ref):
                rows.append((sec,b.name,role,ref,'literal'))
                continue
            matches=(variable_matches(providers,ref,cblocks) if kind=='variable'
                     else applicable(providers,ref,cblocks))
            rows.append((sec,b.name,role,ref,str(len(matches))))
            if len(matches)!=1:
                detail='; '.join(f"{p.source}:{p.section}/{p.object_name}@{','.join(p.blocks)}" for p in matches) or '<none>'
                errs.append(f'{sec}/{b.name} {role}={ref!r} kind={kind}: provider_count={len(matches)} expected=1 matches={detail}')
    return errs,rows


def lookup_binding_errors(text: str):
    errs=[]
    look=[b for b in child_blocks(text,'FunctorMaterials')
          if stripq(b.params.get('type',''))=='QPXElectronTransportLookupMaterial']
    if len(look)!=1:
        return [f'electron lookup count={len(look)} expected=1']
    lk=look[0]
    for role,target in SHARED_BINDINGS.items():
        actual=stripq(lk.params.get(role,''))
        if actual!=target:
            errs.append(f'lookup semantic binding {role}={actual!r}, expected {target!r}')
    return errs


def forbidden_alias_errors(text: str, providers, interface):
    errs=[]
    forbidden={a for role,a in interface.get('source_aliases',{}).items()
               if a and not is_literal_functor(a) and a!=interface['bindings'].get(role)}
    # Only source-local shared aliases are globally forbidden. The old electron
    # variable name can legitimately exist in the frozen heavy baseline (e.g. n_e).
    for alias in sorted(forbidden):
        hits=[p for p in providers if p.name==alias]
        if hits:
            detail='; '.join(f'{p.source}:{p.section}/{p.object_name}' for p in hits)
            errs.append(f'forbidden standalone shared alias provider {alias!r} survives candidate: {detail}')
        for sec,b in integration_blocks(text,interface.get('extra_names',())):
            for role,ref,kind in external_refs_for_block(sec,b):
                if ref==alias:
                    errs.append(f'forbidden standalone shared alias reference {alias!r} in {sec}/{b.name} role={role}')
    olde=interface.get('source_evar','')
    if olde and olde!='n_e_solved':
        for sec,b in integration_blocks(text,interface.get('extra_names',())):
            for role,ref,kind in external_refs_for_block(sec,b):
                if ref==olde:
                    errs.append(f'source electron variable alias {olde!r} leaked into {sec}/{b.name} role={role}')
    for alias in interface.get('forbidden_electron_aliases',()):
        if not alias or is_literal_functor(alias):
            continue
        hits=[p for p in providers if p.name==alias]
        if hits:
            detail='; '.join(f'{p.source}:{p.section}/{p.object_name}' for p in hits)
            errs.append(f'forbidden source-local electron provider {alias!r} survives candidate: {detail}')
        for sec,b in integration_blocks(text,interface.get('extra_names',())):
            for role,ref,kind in external_refs_for_block(sec,b):
                if ref==alias:
                    errs.append(f'forbidden source-local electron reference {alias!r} in {sec}/{b.name} role={role}')
    return errs


def extract_generic_constant(text: str, name: str):
    """Resolve one accepted generic-functor constant by semantic value.

    Returns (value_float, raw_value_token, provider_block, section). This is
    intentionally narrow: #2 accepted mean-energy/carrier constants are owned by
    ADGenericFunctorMaterial. If source representation changes, stop at P0.
    """
    subs=top_substitutions(text)
    loc=locate_provider_block(text,name)
    if len(loc)!=1:
        raise RuntimeError(f'constant provider {name!r} count={len(loc)} expected=1')
    sec,b=loc[0]
    typ=stripq(b.params.get('type',''))
    if sec not in MATERIAL_SECTIONS or typ not in {'ADGenericFunctorMaterial','GenericFunctorMaterial'}:
        raise RuntimeError(f'constant provider {name!r} has unsupported representation {sec}/{typ}')
    names=split_words(b.params.get('prop_names',''))
    vals=split_words(inline_subs(b.params.get('prop_values',''),subs))
    if len(names)!=len(vals):
        raise RuntimeError(f'constant provider {name!r} prop_names/prop_values length mismatch')
    if name not in names:
        raise RuntimeError(f'constant provider block no longer contains {name!r}')
    token=vals[names.index(name)]
    try: val=float(stripq(token))
    except Exception: raise RuntimeError(f'constant provider {name!r} value is not numeric: {token!r}')
    return val,stripq(token),b,sec


def carrier_semantic_value(etext: str, drift: Block):
    ref=stripq(drift.params.get('carrier','1'))
    if is_literal_functor(ref):
        try: val=float(ref)
        except Exception:
            val=1.0 if ref=='one' else 0.0 if ref=='zero' else float('nan')
        return ref,val,'literal'
    val,token,b,sec=extract_generic_constant(etext,ref)
    return ref,val,f'{sec}/{b.name}'


def interface_mutation_selftests():
    import tempfile
    results=[]
    tg="""[FunctorMaterials]\n  [tg]\n    type = ADGenericFunctorMaterial\n    prop_names = 'T_g'\n    prop_values = '600'\n    block = plasma\n  []\n[]\n"""
    ps=providers_from_text(tg,'input.i')
    results.append(('M1_TRUE_DUPLICATE_TG', len(applicable(ps+ps,'T_g',('plasma',)))==2))
    results.append(('M2_MISSING_TG', len(applicable([], 'T_g',('plasma',)))==0))
    with tempfile.TemporaryDirectory() as td:
        c=Path(td); (c/'input.i').write_text(tg); (c/'physics.i').write_text(tg)
        results.append(('M3_UNREACHABLE_SIBLING_IGNORED', len(applicable(providers_from_case(c),'T_g',('plasma',)))==1))
        (c/'input.i').write_text('!include physics.i\n')
        results.append(('M4_REACHABLE_INCLUDE_ONCE', len(applicable(providers_from_case(c),'T_g',('plasma',)))==1))
    hv="""[Variables]\n  [p]\n    type = MooseVariableFVReal\n    block = plasma\n  []\n[]\n[FunctorMaterials]\n  [tg]\n    type = ADGenericFunctorMaterial\n    prop_names = 'T_g'\n    prop_values = '600'\n    block = plasma\n  []\n[]\n"""
    hp=providers_from_text(hv,'heavy.i')
    results.append(('M5_VARIABLE_P_AS_FUNCTOR', len(applicable(hp,'p',('plasma',)))==1))
    elook="""[e_lookup]\n  type = QPXElectronTransportLookupMaterial\n  mean_energy = meanE\n  pressure = p_abs\n  gas_temperature = T_g_source\n  property_table_file = table.txt\n  block = plasma\n[]\n"""
    bound=set_param(set_param(elook,'pressure','p'),'gas_temperature','T_g')
    syn="[FunctorMaterials]\n"+'\n'.join('  '+x if x.strip() else x for x in bound.splitlines())+"\n[]\n"
    results.append(('M6_SEMANTIC_REMAP_PABS_TO_P', lookup_binding_errors(syn)==[]))
    bad=set_param(bound,'pressure','p_abs')
    synbad="[FunctorMaterials]\n"+'\n'.join('  '+x if x.strip() else x for x in bad.splitlines())+"\n[]\n"
    results.append(('M7_RETAINED_PABS_REJECTED', bool(lookup_binding_errors(synbad))))
    alias_provider=Provider('p_abs',('plasma',),'FunctorMaterials','r30_bad_p_abs','input.i')
    iface={'bindings':dict(SHARED_BINDINGS),'source_aliases':{'pressure':'p_abs','gas_temperature':'T_g_source'},
           'source_evar':'e_src','extra_names':[]}
    results.append(('M8_IMPORTED_PABS_PROVIDER_REJECTED', bool(forbidden_alias_errors(syn,hp+[alias_provider],iface))))

    # M8-M11 carrier semantic contract: both accepted named constant and literal 1
    # are valid encodings, but wrong/unresolved named carriers are rejected.
    carrier_src="""[FunctorMaterials]\n  [electron_constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'carrier_one carrier_bad'\n    prop_values = '1.0 0.5'\n    block = plasma\n  []\n[]\n[FVKernels]\n  [drift]\n    type = QPXFVElectrostaticDrift\n    variable = n_e\n    potential = phi\n    mobility = mu\n    carrier = carrier_one\n    charge_number = -1\n    block = plasma\n  []\n[]\n"""
    d=child_blocks(carrier_src,'FVKernels')[0]
    _,v,_=carrier_semantic_value(carrier_src,d)
    results.append(('M9_NAMED_CARRIER_ONE_SEMANTIC_PASS', abs(v-1.0)<=1e-15))
    d_bad=Block(d.name,d.start,d.end,set_param(d.raw,'carrier','carrier_bad'),parse_params(set_param(d.raw,'carrier','carrier_bad')))
    _,vbad,_=carrier_semantic_value(carrier_src,d_bad)
    results.append(('M10_WRONG_CARRIER_VALUE_REJECTED', abs(vbad-1.0)>1e-15))
    unresolved_ok=False
    try:
        d_miss=Block(d.name,d.start,d.end,set_param(d.raw,'carrier','carrier_missing'),parse_params(set_param(d.raw,'carrier','carrier_missing')))
        carrier_semantic_value(carrier_src,d_miss)
    except Exception:
        unresolved_ok=True
    results.append(('M11_UNRESOLVED_CARRIER_REJECTED', unresolved_ok))
    d_lit=Block(d.name,d.start,d.end,set_param(d.raw,'carrier','1'),parse_params(set_param(d.raw,'carrier','1')))
    _,vlit,_=carrier_semantic_value(carrier_src,d_lit)
    results.append(('M12_LITERAL_CARRIER_ONE_SEMANTIC_PASS', abs(vlit-1.0)<=1e-15))

    failed=[name for name,ok in results if not ok]
    for name,ok in results:
        print(f'P0 {name}: {"PASS" if ok else "FAIL"}')
    if failed:
        raise RuntimeError('M1-M12 self-test failures: '+', '.join(failed))
    print('P0 M1_M12_INTERFACE_MUTATIONS: PASS')
    return True

def accepted_plasma_relative_permittivity(text: str):
    """Read accepted plasma epsilon_r metadata without treating it as a functor."""
    hits=[]
    for b in child_blocks(text,'Materials'):
        typ=stripq(b.params.get('type',''))
        if typ!='BaseMaterial' or 'relative_permittivity' not in b.params:
            continue
        mname=stripq(b.params.get('material_name',''))
        btoks=block_tokens(b.params.get('block',''))
        if not (b.name=='plasma' or mname=='plasma' or 'plasma' in btoks):
            continue
        tok=stripq(b.params['relative_permittivity'])
        try:
            val=float(tok)
        except Exception:
            raise RuntimeError(f'accepted plasma relative_permittivity is not numeric: {tok!r}')
        hits.append((val,tok,b.name))
    if len(hits)!=1:
        raise RuntimeError(f'accepted plasma relative_permittivity metadata count={len(hits)} expected=1')
    return hits[0]


def electron_components(etext, heavy_providers, root):
    eblocks=child_blocks(etext,'FVKernels')
    drift=None
    for b in eblocks:
        if stripq(b.params.get('type',''))=='QPXFVElectrostaticDrift':
            try: z=float(stripq(b.params.get('charge_number','nan')))
            except: z=999
            if z<0: drift=b; break
    if drift is None:
        raise RuntimeError('cannot identify accepted negative-electron drift kernel')
    evar=stripq(drift.params.get('variable',''))
    vars_=[b for b in child_blocks(etext,'Variables') if b.name==evar]
    if len(vars_)!=1:
        raise RuntimeError(f'electron variable {evar!r} not unique')
    efv=[b for b in eblocks if stripq(b.params.get('variable',''))==evar]
    types=[stripq(b.params.get('type','')) for b in efv]
    allowed={'FVTimeKernel','FVDiffusion','QPXFVElectrostaticDrift'}
    unknown=[t for t in types if t not in allowed]
    if unknown:
        raise RuntimeError(f'un-audited electron kernel types in accepted #2 path: {unknown}')
    if types.count('FVTimeKernel')!=1 or types.count('FVDiffusion')!=1 or types.count('QPXFVElectrostaticDrift')!=1:
        raise RuntimeError(f'accepted electron kernel inventory unexpected: {types}')
    diff=next(b for b in efv if stripq(b.params.get('type',''))=='FVDiffusion')
    if stripq(diff.params.get('coeff',''))!='electron_diffusion':
        raise RuntimeError(f'accepted electron diffusion coeff changed: {diff.params.get("coeff")}')
    if stripq(drift.params.get('mobility',''))!='electron_mobility':
        raise RuntimeError(f'accepted electron mobility ref changed: {drift.params.get("mobility")}')

    carrier_ref,carrier_val,carrier_src=carrier_semantic_value(etext,drift)
    if abs(carrier_val-1.0)>1e-15:
        raise RuntimeError(f'accepted electron carrier semantic value changed: ref={carrier_ref!r} value={carrier_val}')

    look=[b for b in child_blocks(etext,'FunctorMaterials')
          if stripq(b.params.get('type',''))=='QPXElectronTransportLookupMaterial']
    if len(look)!=1:
        raise RuntimeError(f'expected one QPXElectronTransportLookupMaterial, got {len(look)}')
    lk=look[0]; subs=top_substitutions(etext)

    source_shared_refs={}; shared_refs=dict(SHARED_BINDINGS)
    cblocks=block_tokens(lk.params.get('block',''))
    for key,target in shared_refs.items():
        if key not in lk.params: raise RuntimeError(f'electron lookup missing {key}')
        source_shared_refs[key]=stripq(lk.params[key])
        matches=applicable(heavy_providers,target,cblocks)
        if len(matches)!=1:
            detail='; '.join(f"{p.source}:{p.section}/{p.object_name}@{','.join(p.blocks)}" for p in matches) or '<none>'
            raise RuntimeError(f'integrated shared binding {key}->{target!r} has {len(matches)} applicable heavy-qvt providers; expected exactly 1; source_alias={source_shared_refs[key]!r}; matches={detail}')

    # Resolve electron-specific semantic constants from the accepted source, then
    # rebuild only those constants. Never copy the multi-property source block
    # containing p_abs/T_g/shared state.
    mean_ref=stripq(lk.params.get('mean_energy',''))
    if not mean_ref: raise RuntimeError('electron lookup missing mean_energy')
    props=[]; vals=[]; forbidden=[]
    if is_literal_functor(mean_ref):
        mean_target=mean_ref; mean_value=float(mean_ref)
    else:
        mean_value,mean_token,mb,msec=extract_generic_constant(etext,mean_ref)
        mean_target='r30_mean_energy'; props.append(mean_target); vals.append(mean_token); forbidden.append(mean_ref)

    if is_literal_functor(carrier_ref):
        carrier_target='1'
    else:
        # carrier_semantic_value already proved this source provider resolves and
        # equals one. Rebuild as an electron-specific isolated constant functor.
        _,carrier_token,cb,csec=extract_generic_constant(etext,carrier_ref)
        carrier_target='r30_carrier_one'; props.append(carrier_target); vals.append(carrier_token); forbidden.append(carrier_ref)

    extra=[]; extra_names=[]
    if props:
        cblock=' '.join(cblocks if '*' not in cblocks else ('plasma',))
        eraw=f"""[r30_electron_constants]\n  type = ADGenericFunctorMaterial\n  prop_names = '{' '.join(props)}'\n  prop_values = '{' '.join(vals)}'\n  block = {cblock}\n[]\n"""
        extra.append(('FunctorMaterials',eraw,set(props),None)); extra_names.append('r30_electron_constants')

    lraw=inline_subs(lk.raw,subs)
    lraw=rename_header(lraw,'r30_electron_transport_lookup')
    lraw=set_param(lraw,'gas_temperature',shared_refs['gas_temperature'])
    lraw=set_param(lraw,'pressure',shared_refs['pressure'])
    lraw=set_param(lraw,'mean_energy',mean_target)
    lraw=set_param(lraw,'property_table_file',f"'{root/'examples/modular/chemistry/bolsig-/O2/table/electron_moments.txt'}'")
    vraw=inline_subs(vars_[0].raw,subs)
    interface={
        'bindings':shared_refs,
        'source_aliases':source_shared_refs,
        'source_evar':evar,
        'mean_ref':mean_ref,
        'mean_value':mean_value,
        'carrier_ref':carrier_ref,
        'carrier_value':carrier_val,
        'carrier_source':carrier_src,
        'carrier_target':carrier_target,
        'forbidden_electron_aliases':forbidden,
        'extra_names':extra_names,
    }
    return evar,vraw,efv,lraw,extra,interface


def build_case(base_text, etext, heavy_case: Path, case_name, heavy_on, electron_on, root):
    text=base_text
    # Prescribed-field driver is replaced only by solved-potential path.
    text=re.sub(r'(?m)^\s*E0_migration\s*=.*\n?','',text)
    text=remove_blocks(text,'Functions',lambda b:b.name=='phi_prescribed')
    original_hfv=child_blocks(base_text,'FVKernels')
    heavy_es=[b for b in original_hfv if stripq(b.params.get('type','')) in {'QPXFVElectrostaticDrift','QPXFVHeavyMassElectromigrationCorrection'}]
    text=remove_blocks(text,'FVKernels',lambda b:stripq(b.params.get('type','')) in {'QPXFVElectrostaticDrift','QPXFVHeavyMassElectromigrationCorrection'})

    hprov=providers_from_case(heavy_case)
    evar,vraw,efv,lraw,extra,interface=electron_components(etext,hprov,root)
    enew='n_e_solved'

    text=remove_blocks(text,'Variables',lambda b:b.name in {enew,'potential_plasma'})
    text=remove_blocks(text,'FVKernels',lambda b:b.name.startswith('r30_') or stripq(b.params.get('variable',''))==enew)
    text=remove_blocks(text,'FunctorMaterials',lambda b:b.name.startswith('r30_') or stripq(b.params.get('type',''))=='QPXElectronTransportLookupMaterial')
    text=remove_blocks(text,'FVBCs',lambda b:b.name.startswith('r30_phi_'))

    vraw=rename_word(vraw,evar,enew)
    pv="""[potential_plasma]
  type = MooseVariableFVReal
  initial_condition = 0
  block = plasma
[]
"""
    text=append_blocks(text,'Variables',[vraw,pv])

    # Import only the electron-specific fixed mean-energy provider, if needed.
    for sec,raw,outs,pb in extra:
        raw=rename_word(raw,evar,enew)
        text=append_blocks(text,sec,[raw])
    text=append_blocks(text,'FunctorMaterials',[rename_word(lraw,evar,enew)])

    charge="""[r30_charge_density]
  type = QPXPlasmaChargeDensityMaterial
  density = rho_mat
  electron_density = n_e_solved
  ion_ids = 'O2p Om Op'
  ion_mass_fractions = 'w_O2p w_Om w_Op'
  ion_molar_masses = '0.032 0.016 0.016'
  ion_charges = '1 -1 1'
  block = plasma
[]
"""
    text=append_blocks(text,'FunctorMaterials',[charge])

    eps_value,eps_token,eps_source=accepted_plasma_relative_permittivity(base_text)
    eps_raw=f"""[r30_poisson_relative_permittivity]
  type = ADGenericFunctorMaterial
  prop_names = 'r30_relative_permittivity'
  prop_values = '{eps_token}'
  block = plasma
[]
"""
    text=append_blocks(text,'FunctorMaterials',[eps_raw])
    interface['eps_value']=eps_value
    interface['eps_token']=eps_token
    interface['eps_source']=eps_source

    raws=["""[r30_phi_diffusion]
  type = FVDiffusion
  variable = potential_plasma
  coeff = r30_relative_permittivity
  block = plasma
[]
[r30_phi_charge_source]
  type = FVCoupledForce
  variable = potential_plasma
  v = poisson_charge_source
  coef = 1
  block = plasma
[]
"""]
    for b in efv:
        typ=stripq(b.params.get('type',''))
        if typ=='QPXFVElectrostaticDrift' and not electron_on: continue
        raw=rename_word(inline_subs(b.raw,top_substitutions(etext)),evar,enew)
        raw=rename_header(raw,'r30_e_'+b.name)
        if typ=='QPXFVElectrostaticDrift':
            raw=set_param(raw,'potential','potential_plasma')
            raw=set_param(raw,'carrier',interface['carrier_target'])
        raws.append(raw)
    if heavy_on:
        for b in heavy_es:
            raw=rename_header(b.raw,'r30_h_'+b.name)
            raw=set_param(raw,'potential','potential_plasma')
            raws.append(raw)
    text=append_blocks(text,'FVKernels',raws)

    bcs=[]
    for bc in GROUND_BCS:
        bcs.append(f"""[r30_phi_{bc}]
  type = FVDirichletBC
  variable = potential_plasma
  boundary = {bc}
  value = 0
[]
""")
    text=append_blocks(text,'FVBCs',bcs)
    return text,interface


def static_case_checks(base_providers,cand_providers,text,heavy_on,electron_on,interface):
    errs=[]
    if 'phi_prescribed' in text: errs.append('prescribed phi remains')
    if re.search(r'(?m)^\s*E0_migration\s*=',text): errs.append('E0_migration remains')
    if text.count('type = QPXPlasmaChargeDensityMaterial')!=1: errs.append('charge material count != 1')
    if text.count('type = QPXElectronTransportLookupMaterial')!=1: errs.append('electron lookup count != 1')
    errs += lookup_binding_errors(text)
    if 'electron_density = n_e_solved' not in text: errs.append('charge material not bound to n_e_solved')
    if 'v = poisson_charge_source' not in text: errs.append('Poisson source missing')
    for bc in GROUND_BCS:
        if f'boundary = {bc}' not in text: errs.append(f'missing phi ground {bc}')
    for bc in ('plasma_cover','plasma_wafer','plasma_focus_ring'):
        if re.search(rf'\[r30_phi_[^\]]+\][\s\S]*?boundary\s*=\s*{bc}\b',text): errs.append(f'forbidden dielectric ground {bc}')

    hcount=sum(1 for b in child_blocks(text,'FVKernels')
               if stripq(b.params.get('type','')) in {'QPXFVElectrostaticDrift','QPXFVHeavyMassElectromigrationCorrection'}
               and stripq(b.params.get('variable','')) in set(SOLVED_HEAVY))
    ed=[b for b in child_blocks(text,'FVKernels')
        if stripq(b.params.get('type',''))=='QPXFVElectrostaticDrift'
        and stripq(b.params.get('variable',''))=='n_e_solved']
    if heavy_on and hcount<9: errs.append(f'heavy solved-field path incomplete count={hcount}')
    if not heavy_on and hcount!=0: errs.append(f'heavy path should be OFF count={hcount}')
    if electron_on and len(ed)!=1: errs.append(f'electron drift should be ON count={len(ed)}')
    if not electron_on and ed: errs.append('electron drift should be OFF')

    shared_names=set(interface['bindings'].values()) | {'rho_mat'}
    if provider_signature(base_providers,shared_names)!=provider_signature(cand_providers,shared_names):
        errs.append('shared provider graph changed during electron/Poisson composition')
    for name,blocks in [('T_g',('plasma',)),('p',('plasma',)),('rho_mat',('plasma',))]:
        n=len(applicable(cand_providers,name,blocks))
        if n!=1:
            errs.append(f'provider ownership {name}@{blocks}: count={n}, expected=1')
    eps_hits=applicable(cand_providers,'r30_relative_permittivity',('plasma',))
    if len(eps_hits)!=1:
        errs.append(f'Poisson epsilon functor provider count={len(eps_hits)} expected=1')
    else:
        try:
            eps_val,_,_,_=extract_generic_constant(text,'r30_relative_permittivity')
            expected=interface.get('eps_value',eps_val)
            if abs(eps_val-expected)>1e-15:
                errs.append(f'Poisson epsilon value changed: {eps_val} expected {expected}')
        except Exception as e:
            errs.append(f'Poisson epsilon functor invalid: {e}')
    if 'coeff = relative_permittivity' in text:
        errs.append('invalid legacy Poisson coeff=relative_permittivity remains')

    inv_errs,rows=external_reference_inventory(text,cand_providers,interface)
    errs += inv_errs
    errs += forbidden_alias_errors(text,cand_providers,interface)
    return errs,rows


def provider_validator_selftest(base_providers,tname):
    cand=applicable(base_providers,tname,('plasma',))
    if len(cand)!=1: raise RuntimeError(f'cannot self-test {tname}: baseline applicable provider count={len(cand)}')
    duplicated=list(base_providers)+[cand[0]]
    if len(applicable(duplicated,tname,('plasma',)))==1: raise RuntimeError('duplicate-provider mutation not detected')
    missing=[p for p in base_providers if not (p.name==tname and applies(p,('plasma',)))]
    if len(applicable(missing,tname,('plasma',)))!=0: raise RuntimeError('missing-provider mutation not detected')
    return True


def self_test_only():
    interface_mutation_selftests()

    # Full synthetic integration using the same single-section structure that
    # append_blocks() produces in the real candidate.
    cand="""[Variables]
  [p]
    type = MooseVariableFVReal
    block = plasma
  []
  [w_O2p]
    type = MooseVariableFVReal
    block = plasma
  []
  [w_Om]
    type = MooseVariableFVReal
    block = plasma
  []
  [w_Op]
    type = MooseVariableFVReal
    block = plasma
  []
  [n_e_solved]
    type = MooseVariableFVReal
    block = plasma
  []
  [potential_plasma]
    type = MooseVariableFVReal
    block = plasma
  []
[]
[FunctorMaterials]
  [tg]
    type = ADGenericFunctorMaterial
    prop_names = 'T_g rho_mat'
    prop_values = '600 1.0'
    block = plasma
  []
  [mu]
    type = ADGenericFunctorMaterial
    prop_names = 'mu_O2p mu_Om mu_Op'
    prop_values = '1 1 1'
    block = plasma
  []
  [meanE]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_energy_const r30_carrier_one r30_relative_permittivity'
    prop_values = '5.73276 1.0 1.0'
    block = plasma
  []
  [r30_electron_transport_lookup]
    type = QPXElectronTransportLookupMaterial
    mean_energy = mean_energy_const
    pressure = p
    gas_temperature = T_g
    property_table_file = table.txt
    block = plasma
  []
  [r30_charge_density]
    type = QPXPlasmaChargeDensityMaterial
    density = rho_mat
    electron_density = n_e_solved
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    block = plasma
  []
[]
[Materials]
  [plasma]
    type = BaseMaterial
    relative_permittivity = 1
    block = plasma
  []
[]
[FVKernels]
  [r30_e_time]
    type = FVTimeKernel
    variable = n_e_solved
    block = plasma
  []
  [r30_e_diff]
    type = FVDiffusion
    variable = n_e_solved
    coeff = electron_diffusion
    block = plasma
  []
  [r30_e_drift]
    type = QPXFVElectrostaticDrift
    variable = n_e_solved
    potential = potential_plasma
    mobility = electron_mobility
    carrier = r30_carrier_one
    charge_number = -1
    block = plasma
  []
  [r30_phi_diffusion]
    type = FVDiffusion
    variable = potential_plasma
    coeff = r30_relative_permittivity
    block = plasma
  []
  [r30_phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = poisson_charge_source
    block = plasma
  []
[]
"""
    iface={'bindings':dict(SHARED_BINDINGS),'source_aliases':{'pressure':'p_abs','gas_temperature':'T_g_src'},
           'source_evar':'e_src','mean_ref':'mean_energy_const','forbidden_electron_aliases':[],'extra_names':['meanE']}
    prov=providers_from_text(cand,'synthetic_candidate.i')
    assert len(applicable(prov,'relative_permittivity',('plasma',)))==0
    assert len(applicable(prov,'r30_relative_permittivity',('plasma',)))==1
    epsv,_,_,_=extract_generic_constant(cand,'r30_relative_permittivity')
    assert abs(epsv-1.0)<=1e-15
    print('P0 BASEMATERIAL_PARAMETER_NOT_FUNCTOR_SELFTEST: PASS')
    print('P0 EXPLICIT_POISSON_EPS_FUNCTOR_SELFTEST: PASS')
    errs,rows=external_reference_inventory(cand,prov,iface)
    assert not errs, errs
    assert not forbidden_alias_errors(cand,prov,iface)
    assert not lookup_binding_errors(cand)

    # Accepted-#2-shaped source regression: mean_en, p_abs, T_g and carrier_one
    # share one source material. Integration must isolate only mean/carrier
    # semantic constants and must not transplant p_abs/T_g.
    esrc="""[Variables]\n  [n_e]\n    type = MooseVariableFVReal\n    block = plasma\n  []\n[]\n[FunctorMaterials]\n  [electron_constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'mean_en p_abs T_g carrier_one'\n    prop_values = '5.73276 1.33322 600.0 1.0'\n    block = plasma\n  []\n  [electron_transport]\n    type = QPXElectronTransportLookupMaterial\n    property_table_file = electron_moments.txt\n    mean_energy = mean_en\n    pressure = p_abs\n    gas_temperature = T_g\n    block = plasma\n  []\n[]\n[FVKernels]\n  [time]\n    type = FVTimeKernel\n    variable = n_e\n    block = plasma\n  []\n  [diffusion]\n    type = FVDiffusion\n    variable = n_e\n    coeff = electron_diffusion\n    block = plasma\n  []\n  [drift]\n    type = QPXFVElectrostaticDrift\n    variable = n_e\n    potential = phi_prescribed\n    mobility = electron_mobility\n    carrier = carrier_one\n    charge_number = -1\n    block = plasma\n  []\n[]\n"""
    hv="""[Variables]\n  [p]\n    type = MooseVariableFVReal\n    block = plasma\n  []\n[]\n[FunctorMaterials]\n  [state]\n    type = ADGenericFunctorMaterial\n    prop_names = 'T_g'\n    prop_values = '600'\n    block = plasma\n  []\n[]\n[Materials]\n  [plasma]\n    type = BaseMaterial\n    material_name = plasma\n    relative_permittivity = 1\n    conductivity = 0\n    block = plasma\n  []\n[]\n"""
    hprov=providers_from_text(hv,'heavy.i')
    ev,etok,eps_src_name=accepted_plasma_relative_permittivity(hv)
    assert abs(ev-1.0)<=1e-15 and etok=='1'
    assert len(applicable(hprov,'relative_permittivity',('plasma',)))==0
    print('P0 ACCEPTED_PLASMA_EPS_METADATA_SELFTEST: PASS')
    evar,vraw,efv,lraw,extra,iface2=electron_components(esrc,hprov,Path('/tmp'))
    assert iface2['carrier_ref']=='carrier_one' and abs(iface2['carrier_value']-1.0)<=1e-15
    assert iface2['carrier_target']=='r30_carrier_one'
    assert iface2['mean_ref']=='mean_en' and abs(iface2['mean_value']-5.73276)<=1e-15
    assert len(extra)==1
    eraw=extra[0][1]
    assert 'r30_mean_energy' in eraw and 'r30_carrier_one' in eraw
    assert 'p_abs' not in eraw and "prop_names = 'T_g" not in eraw
    assert "pressure = p" in lraw and "gas_temperature = T_g" in lraw and "mean_energy = r30_mean_energy" in lraw
    draw=next(b.raw for b in efv if stripq(b.params.get('type',''))=='QPXFVElectrostaticDrift')
    draw=set_param(draw,'carrier',iface2['carrier_target'])
    assert 'carrier = r30_carrier_one' in draw
    print('P0 ACCEPTED_ELECTRON_CONSTANT_ISOLATION_SELFTEST: PASS')
    print(f'P0 FULL_EXTERNAL_REFERENCE_INVENTORY_SELFTEST: PASS refs={len(rows)}')
    print('R30_PROVIDER_GRAPH_SELFTEST: PASS')
    return 0


def check_input(label,case,inp,qpx,logs):
    cp=run([qpx,'-i',inp.name,'--check-input'],cwd=case,log=logs/f'{label}_check_input.log')
    if cp.returncode==0:
        print(f'P2 {label}: PASS'); return True
    print(f'P2 {label}: FAIL')
    lines=cp.stdout.splitlines()
    print('--- FIRST ERROR / LOG TAIL ---')
    hits=[x for x in lines if re.search(r'error|failed|no insertion|missing|unknown|invalid|required|duplicate|functor',x,re.I)]
    for x in (hits[-20:] if hits else lines[-60:]): print(x)
    print('--- END ERROR ---')
    return False


def runtime_eps_functor_smoke(qpx: Path, work: Path, logs: Path, eps_token: str):
    d=work/'EPS_FUNCTOR_SMOKE'; d.mkdir(parents=True,exist_ok=True)
    inp=d/'input.i'
    inp.write_text(f"""[Mesh]\n  [gen]\n    type = GeneratedMeshGenerator\n    dim = 1\n    nx = 2\n    xmin = 0\n    xmax = 1\n  []\n[]\n[Variables]\n  [u]\n    type = MooseVariableFVReal\n  []\n[]\n[FunctorMaterials]\n  [eps]\n    type = ADGenericFunctorMaterial\n    prop_names = 'r30_relative_permittivity'\n    prop_values = '{eps_token}'\n  []\n[]\n[FVKernels]\n  [diff]\n    type = FVDiffusion\n    variable = u\n    coeff = r30_relative_permittivity\n  []\n[]\n[FVBCs]\n  [left]\n    type = FVDirichletBC\n    variable = u\n    boundary = left\n    value = 0\n  []\n  [right]\n    type = FVDirichletBC\n    variable = u\n    boundary = right\n    value = 0\n  []\n[]\n[Executioner]\n  type = Steady\n  solve_type = NEWTON\n[]\n""")
    cp=run([qpx,'-i',inp.name],cwd=d,log=logs/'EPS_FUNCTOR_SMOKE_run.log')
    if cp.returncode==0:
        print('P2R POISSON_EPS_FUNCTOR_RUNTIME_SMOKE: PASS')
        return True
    print('P2R POISSON_EPS_FUNCTOR_RUNTIME_SMOKE: FAIL')
    lines=cp.stdout.splitlines()
    hits=[x for x in lines if re.search(r'error|failed|functor|exception|invalid',x,re.I)]
    for x in (hits[-30:] if hits else lines[-80:]): print(x)
    return False


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('qpx_opt',nargs='?')
    ap.add_argument('--root')
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--prepare-only',action='store_true')
    a=ap.parse_args()
    if a.self_test: return self_test_only()
    if not a.qpx_opt: ap.error('qpx_opt required unless --self-test')

    qpx=Path(a.qpx_opt).expanduser().resolve()
    if not qpx.is_file(): raise SystemExit(f'missing qpx-opt: {qpx}')
    root=Path(a.root).expanduser().resolve() if a.root else qpx.parent.resolve()
    heavy=root/'temp/regression_workspace/tests/heavy_transport/qvt_six_species_charged_migration'
    electron=root/'temp/test_workspace/electron_transport/r2_electron_drift_diffusion/qvt_prepoisson'
    etable=root/'examples/modular/chemistry/bolsig-/O2/table/electron_moments.txt'
    for p in (heavy,electron,etable):
        if not p.exists():
            print(f'P0 MISSING_REQUIRED_ASSET: {p}'); print('NO_QPX_EXECUTED'); return 20

    ts=time.strftime('%Y%m%d_%H%M%S'); out=root/'temp/results/r30_semantic_interface_construction'/ts
    work=out/'work'; logs=out/'logs'; work.mkdir(parents=True); logs.mkdir()
    print('R30_RUNNER_REVISION=v2_runtime_functor_contract')
    print(f'QPX_OPT_REALPATH={qpx}')
    print(f'QPX_ROOT={root}')
    print(f'RESULT_DIR={out}')

    git=run(['git','-C',root,'rev-parse','HEAD'])
    head=git.stdout.strip() if git.returncode==0 else ''
    print(f'QPX_GIT_HEAD={head}')
    if head!=EXPECTED_QPX_HEAD:
        print(f'P1 SOURCE_IDENTITY_FAIL expected={EXPECTED_QPX_HEAD}'); print('NO_QPX_EXECUTED'); return 21
    for label,case in [('HEAVY',heavy),('ELECTRON',electron)]:
        mesh=case/'qvt.msh'
        if not mesh.exists() or sha256(mesh)!=EXPECTED_QVT_SHA:
            print(f'P1 {label}_QVT_SHA_FAIL'); print('NO_QPX_EXECUTED'); return 22
    if sha256(etable)!=EXPECTED_ELECTRON_TABLE_SHA:
        print('P1 ELECTRON_TABLE_SHA_FAIL'); print('NO_QPX_EXECUTED'); return 23
    tdata=heavy/'transport_data.txt'
    if tdata.exists() and sha256(tdata)!=EXPECTED_TRANSPORT_SHA:
        print('P1 HEAVY_TRANSPORT_DATA_SHA_FAIL'); print('NO_QPX_EXECUTED'); return 24
    print('P1 SOURCE_AND_ASSET_IDENTITY: PASS')

    hi=find_input(heavy); ei=find_input(electron)
    htext=hi.read_text(errors='replace'); etext=ei.read_text(errors='replace')
    base_prov=providers_from_case(heavy)
    try:
        eps_value,eps_token,eps_source=accepted_plasma_relative_permittivity(htext)
    except Exception as e:
        print(f'P0 PLASMA_EPS_PROVENANCE: FAIL: {e}'); print('NO_PHYSICS_EXECUTED'); return 24
    print(f'P0 PLASMA_EPS_PROVENANCE: PASS value={eps_value} source=Materials/{eps_source}')
    if applicable(base_prov,'relative_permittivity',('plasma',)):
        print('P0 BASEMATERIAL_PARAMETER_NOT_FUNCTOR: FAIL'); print('NO_PHYSICS_EXECUTED'); return 24
    print('P0 BASEMATERIAL_PARAMETER_NOT_FUNCTOR: PASS')

    # Resolve shared lookup inputs from the real heavy provider graph before generating cases.
    try:
        _,_,_,_,_,interface=electron_components(etext,base_prov,root)
        provider_validator_selftest(base_prov,'T_g')
        interface_mutation_selftests()
        print('P0 ELECTRON_INTERFACE_BINDINGS: gas_temperature=T_g pressure=p carrier_semantic=1')
        print(f"P0 SOURCE_ALIAS_PROVENANCE: gas_temperature={interface['source_aliases'].get('gas_temperature')} pressure={interface['source_aliases'].get('pressure')} carrier={interface.get('carrier_ref')}")
    except Exception as e:
        print(f'P0 PROVIDER_GRAPH_PREFLIGHT: FAIL: {e}'); print('NO_QPX_EXECUTED'); return 25
    print('P0 DUPLICATE_SHARED_PROVIDER_MUTATION: PASS')
    print('P0 MISSING_SHARED_PROVIDER_MUTATION: PASS')

    cases={'Q0':(False,False),'QH':(True,False),'QE':(False,True),'QF':(True,True)}
    built_cases={}
    for name,(hon,eon) in cases.items():
        d=work/name; shutil.copytree(heavy,d)
        inp=d/hi.name
        try: built,interface=build_case(htext,etext,heavy,name,hon,eon,root)
        except Exception as e:
            print(f'P0 {name} BUILD: FAIL: {e}'); print('NO_QPX_EXECUTED'); return 26
        inp.write_text(built)
        cand_prov=providers_from_case(d,inp,built)
        errs,inv_rows=static_case_checks(base_prov,cand_prov,built,hon,eon,interface)
        if errs:
            print(f'P0 {name} PROVIDER/STRUCTURE: FAIL')
            for e in errs: print('  -',e)
            print('NO_QPX_EXECUTED'); return 27
        ps=root/'scripts/validate_parser_symbols.py'
        if ps.exists():
            cp=run([sys.executable,ps,inp],cwd=d,log=logs/f'{name}_parser_symbols.log')
            if cp.returncode:
                print(f'P0 {name} PARSER_NAMESPACE: FAIL'); print('NO_QPX_EXECUTED'); return 28
        built_cases[name]=(d,inp)
        print(f'P0 {name} ELECTRON_EXTERNAL_REFERENCE_INVENTORY: PASS refs={len(inv_rows)}')
        print(f'P0 {name} PROVIDER/STRUCTURE: PASS')
    print('P0 ELECTRON_EXTERNAL_REFERENCE_INVENTORY: PASS')
    print('P0 BLOCK_QUALIFIED_PROVIDER_OWNERSHIP: PASS')
    print('P1 STATIC_CONSTRUCTION: PASS')

    if a.prepare_only:
        print('PREPARE_ONLY: PASS'); print('NO_QPX_EXECUTED'); return 0

    if not runtime_eps_functor_smoke(qpx,work,logs,eps_token):
        print('CLASSIFICATION_HINT=RUNTIME_CONSTRUCTION_FAIL')
        print('NO_PHYSICS_EXECUTED'); return 29

    total=6; passed=0
    # Known-good construction controls only: no prepare.py, no P3, no checker.
    for label,case in [('KG-H',heavy),('KG-E',electron)]:
        inp=find_input(case)
        if check_input(label,case,inp,qpx,logs): passed+=1
        else:
            print(f'R30 P2 TOTAL: {total} PASS: {passed} FAIL: 1 (stopped)')
            print('CLASSIFICATION_HINT=ENVIRONMENT_OR_UPSTREAM_CONSTRUCTION_FAIL')
            print('NO_P3_EXECUTED'); return 30
    for label in ('Q0','QH','QE','QF'):
        d,inp=built_cases[label]
        if check_input(label,d,inp,qpx,logs): passed+=1
        else:
            print(f'R30 P2 TOTAL: {total} PASS: {passed} FAIL: 1 (stopped)')
            print('CLASSIFICATION_HINT=HARNESS_OR_CONSTRUCTION_FAIL')
            print('NO_P3_EXECUTED'); return 31
    print(f'R30 P2 TOTAL: {total} PASS: {passed} FAIL: {total-passed}')
    print('CLASSIFICATION_HINT=CONSTRUCTION_READY_FOR_ISSUE_29')
    print('NO_PLASMA_PHYSICS_EXECUTED')
    print(f'RESULT_DIR={out}')
    return 0

if __name__=='__main__': raise SystemExit(main())
