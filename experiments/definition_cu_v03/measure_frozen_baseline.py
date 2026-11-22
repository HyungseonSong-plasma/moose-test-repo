"""Recalculate v0.3 cue burden over pinned baseline source-API snapshot.

This is a separately labeled proxy replay: behavior-role hypotheses were
matched to exact lines in source; this does not execute the AST extractor on
those complete files and must not be represented as that run.
"""
from __future__ import annotations
import json
from pathlib import Path
from libs.code_understandability.definition_metrics import DefinitionClause, measure_definition
from physics_harness.code.analysis.definition_inference import SourceSymbol, make_folder_cues

BASELINE = '4f873e71f8503943c9fce2dd30fcc96c28d6f631'
ROLES = {
 'graph':('GRAPH_MODEL',('record','relation','invariant'),'physics_harness/code/graph/edge.py',25,'a3cf19f4d416cae10d604284d78cce995164466c'),
 'diagnostics':('SOURCE_FACT_COLLECTION',('source','parse','evidence'),'physics_harness/code/diagnostics/providers/python_ast.py',68,'8a4de081c3b3f722ca3d651e84b6e01dc14c7978'),
 'analysis':('GRAPH_ANALYSIS',('graph','analysis','result'),'physics_harness/code/analysis/impact.py',53,'6772dbef8a19813fbcb288e4195ea1631189e019'),
 'refactor':('CHANGE_PLANNING',('option','constraint','review'),'physics_harness/code/refactor/alternatives.py',48,'0c0986dee3e7cb6b3dd07d8a69636830b81bcea3'),
 'verification':('SOURCE_VERIFICATION',('source','provenance','verification'),'physics_harness/code/verification/consistency.py',149,'42e8caa55d8289b6c2b1005d744702c11ba54770'),
}

def run(manifest:dict)->dict:
    if manifest['revision']!=BASELINE: raise ValueError('EXACT_BASELINE_REQUIRED')
    results=[]
    for target in manifest['targets']:
        name=target['path'].split('/')[-1]
        result={'target':name,'path':target['path'],'role':None,'status':'UNRESOLVED','metrics':None}
        if name in ROLES:
            role,concepts,path,line,blob=ROLES[name]
            refs=(f'{path}:{line}@{blob}',)
            clauses=tuple(DefinitionClause(c,refs) for c in concepts)
            symbols=tuple(SourceSymbol(s,f'{target["path"]}/__init__.py@{target["blob_sha"]}') for s in target['public_symbols'])
            cues=make_folder_cues(target['path'],symbols,tuple(target['module_names']))
            v=measure_definition(clauses,cues)
            result.update({'role':role,'status':'SOURCE_ANCHORED_PROXY_REPLAY',
                'role_source_ref':refs[0],
                'metrics':{'DEB':v.definition_explanation_burden,
                           'DEB_denominator':v.total_concepts,
                           'MRC_extra_cues':v.minimum_required_context,
                           'MRC_tier':v.minimum_context_tier,
                           'MRC_cues':list(v.selected_context_cues),
                           'unpredicted_baseline':list(v.unpredicted_concepts),
                           'not_recoverable_in_scope':list(v.still_unrecoverable)}})
        results.append(result)
    return {'schema_version':'0.3-baseline-proxy','baseline':BASELINE,
            'input_kind':'pinned_source_anchored_role_hypotheses_and_frozen_api_cues',
            'full_source_ast_scanned':False,'human_cu_calibrated':False,
            'results':results}

def main()->None:
    p=Path(__file__).resolve().parents[1]/'definition_cu_v02'/'pilot_inputs.json'
    # Frozen snapshot lives in the v0.2 experiment folder in the repository.
    manifest=json.loads(p.read_text(encoding='utf-8'))
    print(json.dumps(run(manifest),indent=2)+'\n',end='')

if __name__=='__main__':main()
